import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.datasets.profiling import inspect_csv, timestamp_column_overrides, validate_csv_header
from app.db.supabase_rest import SupabaseAdmin

logger = logging.getLogger(__name__)


async def _log(admin: SupabaseAdmin, job_id: str, stage: str, severity: str, details: dict[str, Any]) -> None:
    await admin.request("POST", "processing_logs", json={"job_id": job_id, "stage": stage, "severity": severity, "details": details}, headers={"Prefer": "return=minimal"})


async def _patch(admin: SupabaseAdmin, table: str, query: dict[str, str], payload: dict[str, Any]) -> None:
    await admin.request("PATCH", table, params={**query, "select": "id"}, json=payload, headers={"Prefer": "return=minimal"})


def _to_parquet(source: Path, target: Path) -> None:
    frame = pl.scan_csv(source, infer_schema_length=10_000, try_parse_dates=True, schema_overrides=timestamp_column_overrides(validate_csv_header(source)), raise_if_empty=True)
    frame.sink_parquet(target, compression="zstd", engine="streaming")


async def process_job(job: dict[str, Any], admin: SupabaseAdmin) -> None:
    job_id = job["id"]
    dataset_id = job["dataset_id"]
    owner_id = job["owner_id"]
    dataset_rows = await admin.request("GET", "datasets", params={"select": "*", "id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}", "limit": "1"})
    if not dataset_rows:
        raise RuntimeError("Job dataset is missing or its owner does not match.")
    dataset = dataset_rows[0]
    if dataset.get("source_type") == "kaggle":
        from app.workers.kaggle_pipeline import process_kaggle_job

        await process_kaggle_job(job, dataset, admin)
        return
    raw_path: Path | None = None
    parquet_path: Path | None = None
    try:
        await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"stage": "extract", "progress": 10})
        await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {"status": "processing"})
        await _log(admin, job_id, "extract", "info", {"message": "Reading the preserved source file."})
        with tempfile.NamedTemporaryFile(prefix="meridian-raw-", suffix=".csv", delete=False) as raw_file:
            raw_path = Path(raw_file.name)
        await admin.download_to_path(dataset["storage_key"], raw_path)
        content_sha256 = await asyncio.to_thread(_hash_file, raw_path)
        if dataset.get("content_sha256") and dataset["content_sha256"] != content_sha256:
            raise ValueError("Source object hash does not match the upload metadata.")
        await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {"content_sha256": content_sha256})

        await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"stage": "profile", "progress": 35})
        profile = await asyncio.to_thread(inspect_csv, raw_path)
        await _log(admin, job_id, "profile", "info", {"row_count": profile["row_count"], "column_count": profile["column_count"], "duplicate_rows": profile["duplicate_rows"]})

        await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"stage": "transform", "progress": 65})
        parquet_path = raw_path.with_suffix(".parquet")
        await asyncio.to_thread(_to_parquet, raw_path, parquet_path)
        version_number = int(dataset.get("active_version") or 0) + 1
        await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"version_number": version_number})
        processed_key = f"{owner_id}/{dataset_id}/versions/{version_number}/data.parquet"
        await admin.upload_path(processed_key, parquet_path, "application/vnd.apache.parquet")

        version_rows = await admin.request("POST", "dataset_versions", json={
            "dataset_id": dataset_id,
            "version_number": version_number,
            "raw_storage_key": dataset["storage_key"],
            "processed_storage_key": processed_key,
            "schema_snapshot": profile["columns"],
            "row_count": profile["row_count"],
            "transformation_config": {"operation": "type_inference_to_parquet", "raw_preserved": True, "automatic_row_deletion": False},
        }, params={"select": "id"}, headers={"Prefer": "return=representation"})
        version_id = version_rows[0]["id"]
        quality = {
            "row_count": profile["row_count"],
            "column_count": profile["column_count"],
            "duplicate_rows": profile["duplicate_rows"],
            "missing_cells": sum(column["missing_count"] for column in profile["columns"]),
            "outlier_candidate_count": sum(column.get("outlier_candidate_count", 0) for column in profile["columns"]),
            "automatic_cleaning_applied": False,
            "suggestions": _suggestions(profile),
        }
        await admin.request("POST", "data_quality_reports", json={"dataset_version_id": version_id, "summary": quality, "column_report": {column["name"]: column for column in profile["columns"]}}, headers={"Prefer": "return=minimal"})
        await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {
            "status": "ready", "active_version": version_number, "row_count": profile["row_count"],
            "column_count": profile["column_count"], "detected_schema": profile["columns"],
        })
        await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"status": "succeeded", "stage": "complete", "progress": 100, "finished_at": datetime.now(UTC).isoformat()})
        await _log(admin, job_id, "complete", "info", {"message": "The typed dataset version and quality report are ready.", "version": version_number})
    except Exception as exc:
        logger.exception("Processing job %s failed", job_id)
        try:
            await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {"status": "failed"})
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"status": "failed", "stage": "failed", "progress": 100, "error_code": "PROCESSING_FAILED", "error_message": "Processing failed. Check the file and retry the job.", "finished_at": datetime.now(UTC).isoformat()})
            await _log(admin, job_id, "failed", "error", {"message": "Processing failed.", "error_type": type(exc).__name__})
        except Exception:
            logger.exception("Failed to persist job failure status for %s", job_id)
    finally:
        if raw_path and raw_path.exists():
            raw_path.unlink(missing_ok=True)
        if parquet_path and parquet_path.exists():
            parquet_path.unlink(missing_ok=True)


def _hash_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _suggestions(profile: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    if profile["duplicate_rows"]:
        suggestions.append({"kind": "duplicates", "count": profile["duplicate_rows"], "action": "Review and remove duplicate rows", "requires_approval": True})
    for column in profile["columns"]:
        if column["missing_count"]:
            suggestions.append({"kind": "missing_values", "column": column["name"], "count": column["missing_count"], "action": "Review missing-value handling", "requires_approval": True})
        if column.get("outlier_candidate_count"):
            suggestions.append({"kind": "outliers", "column": column["name"], "count": column["outlier_candidate_count"], "action": "Review IQR outlier candidates", "requires_approval": True})
    return suggestions
