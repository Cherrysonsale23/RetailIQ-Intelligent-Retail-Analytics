import asyncio
import logging
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.analytics.engine import (
    analyze_cohorts,
    analyze_correlations,
    analyze_customers,
    analyze_overview,
    analyze_products,
    analyze_time,
)
from app.datasets.kaggle import (
    KaggleSourceError,
    available_temp_bytes,
    csv_profile,
    csv_to_parquet,
    download_csv,
    list_dataset_files,
)
from app.db.supabase_rest import SupabaseAdmin

logger = logging.getLogger(__name__)


async def _patch(admin: SupabaseAdmin, table: str, query: dict[str, str], payload: dict[str, Any]) -> None:
    await admin.request("PATCH", table, params={**query, "select": "id"}, json=payload, headers={"Prefer": "return=minimal"})


async def _log(admin: SupabaseAdmin, job_id: str, stage: str, details: dict[str, Any], severity: str = "info") -> None:
    await admin.request("POST", "processing_logs", json={
        "job_id": job_id, "stage": stage, "severity": severity, "details": details,
    }, headers={"Prefer": "return=minimal"})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rankings(products: dict[str, Any], dataset_id: str, version: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    value_keys = {"view": "views", "cart": "carts", "purchase": "purchases", "conversion": "session_conversion_rate"}
    for dimension, section in (("product_id", "products"), ("brand", "brands"), ("category", "categories")):
        group = products.get(section, {})
        output[dimension] = {}
        if not group.get("supported"):
            for event in value_keys:
                output[dimension][event] = {"supported": False, "reason": group.get("reason"), "items": [], "evidence": []}
            continue
        by_event = group.get("top_by_event", {})
        for event, value_key in value_keys.items():
            supported = event != "conversion" or group.get("conversion_supported", False)
            output[dimension][event] = {
                "supported": supported,
                "dataset_id": dataset_id,
                "version": version,
                "dimension": dimension,
                "dimension_column": products.get("roles", {}).get(dimension),
                "event": event,
                "value_key": value_key,
                "items": by_event.get(event, []),
                "definition": group.get("definition"),
                "reason": None if supported else group.get("conversion_reason"),
                "evidence": [{"id": f"K-{dimension}-{event}", "computation": group.get("definition", "Computed from Kaggle source rows."), "dataset_id": dataset_id, "version": version}],
            }
    return output


async def process_kaggle_job(job: dict[str, Any], dataset: dict[str, Any], admin: SupabaseAdmin) -> None:
    job_id, dataset_id, owner_id = job["id"], dataset["id"], dataset["owner_id"]
    source = job.get("source_config") or dataset.get("source_metadata") or {}
    dataset_ref = source.get("dataset_ref")
    selected = source.get("files") or []
    raw_total = sum(int(item.get("total_bytes", 0)) for item in selected)
    try:
        if not dataset_ref or not selected:
            raise KaggleSourceError("This Kaggle import is missing its dataset reference or selected files.")
        manifest = {item["name"]: item for item in await list_dataset_files(dataset_ref)}
        for item in selected:
            current = manifest.get(item.get("name"))
            if not current or int(current["total_bytes"]) != int(item.get("total_bytes", -1)):
                raise KaggleSourceError(f"Kaggle's file manifest changed for {item.get('name')}. Create a fresh import to continue.")
        required = int(raw_total * 1.5)
        with tempfile.TemporaryDirectory(prefix="meridian-kaggle-") as temp_dir:
            temp_root = Path(temp_dir)
            if available_temp_bytes(temp_root) < required:
                raise KaggleSourceError(f"The worker needs at least {required / (1024 ** 3):.1f} GB of temporary free disk for this import.")
            parquet_paths: list[Path] = []
            first_schema: pl.Schema | None = None
            preview_data: dict[str, Any] | None = None
            detected_columns: list[dict[str, Any]] = []
            total_rows, missing_cells = 0, 0
            files_metadata = []

            await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {"status": "processing"})
            for index, item in enumerate(selected):
                name = item["name"]
                await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {
                    "stage": "download", "progress": int(10 + index / len(selected) * 38),
                })
                await _log(admin, job_id, "download", {"file": name, "file_number": index + 1, "file_count": len(selected), "message": "Downloading this public Kaggle CSV to temporary worker storage."})
                csv_path = await download_csv(dataset_ref, name, temp_root, int(item["total_bytes"]))
                overrides = dict(first_schema.items()) if first_schema is not None else None
                profile = await asyncio.to_thread(csv_profile, csv_path, overrides)
                if first_schema is None:
                    first_schema = profile["schema"]
                    detected_columns = profile["columns"]
                    preview_data = {"columns": first_schema.names(), "rows": [_json_safe(row) for row in profile["preview"]]}
                    missing_cells += sum(column["missing_count"] for column in detected_columns)
                elif first_schema.names() != profile["schema"].names():
                    raise KaggleSourceError(f"{name} has a different set or order of columns from the first selected CSV.")
                else:
                    for column, measured in zip(detected_columns, profile["columns"], strict=True):
                        column["missing_count"] += measured["missing_count"]
                        column["nullable"] = column["nullable"] or measured["nullable"]
                        missing_cells += measured["missing_count"]
                total_rows += profile["row_count"]
                parquet_path = temp_root / f"month-{index + 1:02d}.parquet"
                await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {
                    "stage": "transform", "progress": int(15 + (index + 1) / len(selected) * 38),
                })
                await asyncio.to_thread(csv_to_parquet, csv_path, parquet_path, overrides)
                csv_path.unlink(missing_ok=True)
                parquet_paths.append(parquet_path)
                files_metadata.append({"name": name, "total_bytes": int(item["total_bytes"]), "row_count": profile["row_count"], "created_at": item.get("created_at")})
                await _log(admin, job_id, "transform", {"file": name, "rows": profile["row_count"], "columns": profile["column_count"], "message": "Converted to a temporary streaming-friendly format; source CSV removed from scratch."})

            if not first_schema or not parquet_paths:
                raise KaggleSourceError("No selected Kaggle CSV files were processed.")

            version_number = int(dataset.get("active_version") or 0) + 1
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"stage": "analytics", "progress": 60, "version_number": version_number})
            await _log(admin, job_id, "analytics", {"message": "Computing the complete dataset analytics snapshot across all selected months."})
            path_arg = parquet_paths
            overview = await asyncio.to_thread(analyze_overview, path_arg, dataset_id, version_number)
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"progress": 66})
            products = await asyncio.to_thread(analyze_products, path_arg, dataset_id, version_number, limit=500)
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"progress": 73})
            time_data = await asyncio.to_thread(analyze_time, path_arg, dataset_id, version_number)
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"progress": 79})
            customers = await asyncio.to_thread(analyze_customers, path_arg, dataset_id, version_number)
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"progress": 85})
            cohorts = await asyncio.to_thread(analyze_cohorts, path_arg, dataset_id, version_number)
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"progress": 91})
            correlations = await asyncio.to_thread(analyze_correlations, path_arg, dataset_id, version_number)
            # The snapshot stores group-level customer metrics, never raw user identifiers.
            customers["top_users"] = []
            snapshot = {
                "overview": overview,
                "products": products,
                "time": time_data,
                "customers": customers,
                "cohorts": cohorts,
                "correlations": correlations,
                "rankings": _rankings(products, dataset_id, version_number),
            }
            snapshot = _json_safe(snapshot)

            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {"stage": "persist", "progress": 88})
            version_rows = await admin.request("POST", "dataset_versions", json={
                "dataset_id": dataset_id,
                "version_number": version_number,
                "raw_storage_key": None,
                "processed_storage_key": None,
                "schema_snapshot": detected_columns,
                "row_count": total_rows,
                "transformation_config": {
                    "operation": "kaggle_streaming_analytics_snapshot",
                    "source_files": [item["name"] for item in files_metadata],
                    "raw_retained": False,
                    "processed_retained": False,
                    "duplicate_detection": "not_run_for_large_source",
                    "automatic_cleaning_applied": False,
                },
            }, params={"select": "id"}, headers={"Prefer": "return=representation"})
            version_id = version_rows[0]["id"]
            await admin.request("POST", "dataset_analytics_snapshots", json={
                "dataset_id": dataset_id, "dataset_version_id": version_id, "owner_id": owner_id, "snapshot": snapshot,
            }, headers={"Prefer": "return=minimal"})
            quality = {
                "row_count": total_rows,
                "column_count": len(detected_columns),
                "duplicate_rows": None,
                "missing_cells": missing_cells,
                "outlier_candidate_count": None,
                "automatic_cleaning_applied": False,
                "suggestions": [],
                "metrics_not_computed": ["Exact duplicate-row detection", "Outlier candidates", "Per-column distinct counts"],
            }
            await admin.request("POST", "data_quality_reports", json={
                "dataset_version_id": version_id, "summary": quality,
                "column_report": {column["name"]: column for column in detected_columns},
            }, headers={"Prefer": "return=minimal"})
            source["files"] = files_metadata
            source["raw_retained"] = False
            source["imported_at"] = datetime.now(UTC).isoformat()
            await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {
                "status": "ready", "active_version": version_number, "row_count": total_rows,
                "column_count": len(detected_columns), "detected_schema": detected_columns,
                "preview_data": preview_data, "source_metadata": source,
            })
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {
                "status": "succeeded", "stage": "complete", "progress": 100,
                "finished_at": datetime.now(UTC).isoformat(),
            })
            await _log(admin, job_id, "complete", {"message": "Analytics snapshot is ready; raw and transformed temporary files were removed.", "rows": total_rows, "file_count": len(files_metadata)})
    except Exception as exc:
        logger.exception("Kaggle processing job %s failed", job_id)
        try:
            await _patch(admin, "datasets", {"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, {"status": "failed"})
            await _patch(admin, "processing_jobs", {"id": f"eq.{job_id}"}, {
                "status": "failed", "stage": "failed", "progress": 100,
                "error_code": "KAGGLE_IMPORT_FAILED",
                "error_message": str(exc)[:800] if isinstance(exc, KaggleSourceError) else "Kaggle import failed while downloading or analyzing the selected files.",
                "finished_at": datetime.now(UTC).isoformat(),
            })
            await _log(admin, job_id, "failed", {"error_type": type(exc).__name__, "message": str(exc)[:500]}, "error")
        except Exception:
            logger.exception("Could not persist failure status for Kaggle job %s", job_id)
