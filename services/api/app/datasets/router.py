import csv
import hashlib
import io
import logging
import re
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.datasets.kaggle import (
    KaggleSourceError,
    available_temp_bytes,
    list_dataset_files,
    parse_dataset_ref,
)
from app.datasets.profiling import CsvValidationError
from app.datasets.schemas import KaggleImportRequest, UploadAccepted, UploadIntent
from app.db.supabase_rest import SupabaseAdmin

router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


@router.get("/kaggle/files")
async def kaggle_files(user: CurrentUser, dataset_url: str = Query(min_length=1, max_length=500)) -> dict[str, Any]:
    del user
    try:
        dataset_ref = parse_dataset_ref(dataset_url)
        files = await list_dataset_files(dataset_ref)
    except KaggleSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"dataset_ref": dataset_ref, "files": files}


@router.post("/kaggle/import", status_code=status.HTTP_202_ACCEPTED)
async def import_kaggle_dataset(body: KaggleImportRequest, user: CurrentUser) -> dict[str, Any]:
    settings = get_settings()
    try:
        dataset_ref = parse_dataset_ref(body.dataset_url)
        manifest = await list_dataset_files(dataset_ref)
    except KaggleSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    by_name = {item["name"]: item for item in manifest}
    if len(set(body.files)) != len(body.files) or any(name not in by_name for name in body.files):
        raise HTTPException(status_code=422, detail="Refresh the Kaggle file list and select only files shown there.")
    selected = [by_name[name] for name in body.files]
    total_bytes = sum(item["total_bytes"] for item in selected)
    if total_bytes > settings.max_kaggle_import_bytes:
        max_gb = settings.max_kaggle_import_bytes / (1024 ** 3)
        raise HTTPException(status_code=413, detail=f"The selected files exceed the {max_gb:.0f} GB Kaggle import limit.")
    scratch = Path(tempfile.gettempdir())
    required = int(total_bytes * settings.kaggle_temp_disk_factor)
    if available_temp_bytes(scratch) < required:
        required_gb = required / (1024 ** 3)
        raise HTTPException(status_code=507, detail=f"The worker needs at least {required_gb:.1f} GB of temporary free disk for this import.")

    owner_id = str(uuid.UUID(user["sub"]))
    dataset_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    label = (body.name or f"Kaggle · {dataset_ref.rsplit('/', 1)[-1]}").strip()[:120]
    source_metadata = {"dataset_ref": dataset_ref, "files": selected, "raw_retained": False}
    admin = SupabaseAdmin()
    try:
        await admin.request("POST", "datasets", json={
            "id": dataset_id, "owner_id": owner_id, "name": label,
            "original_filename": ", ".join(item["name"] for item in selected)[:180],
            "storage_key": None, "byte_size": total_bytes, "content_sha256": None,
            "source_type": "kaggle", "source_metadata": source_metadata, "status": "queued",
            "detected_schema": [], "preview_data": {"columns": [], "rows": []},
            "row_count": None, "column_count": None,
        }, headers={"Prefer": "return=minimal"})
        await admin.request("POST", "processing_jobs", json={
            "id": job_id, "dataset_id": dataset_id, "owner_id": owner_id,
            "status": "queued", "stage": "queued", "progress": 0,
            "source_config": source_metadata,
        }, headers={"Prefer": "return=minimal"})
    except Exception as exc:
        try:
            await admin.request("DELETE", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"})
        except Exception:
            logger.exception("Could not clean up a failed Kaggle import setup")
        raise HTTPException(status_code=502, detail="The Kaggle import could not be queued. Retry after checking the database connection.") from exc
    return {"dataset_id": dataset_id, "job_id": job_id, "status": "queued", "file_count": len(selected), "byte_size": total_bytes}


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "dataset.csv").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:180]
    if not name or not name.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Only CSV uploads are supported in this release.")
    return name


async def _hash_and_measure(upload: UploadFile, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    await upload.seek(0)
    while chunk := await upload.read(CHUNK_SIZE):
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB upload limit.")
        digest.update(chunk)
    await upload.seek(0)
    if total == 0:
        raise HTTPException(status_code=400, detail="The uploaded CSV is empty.")
    return digest.hexdigest(), total


async def _file_stream(upload: UploadFile):
    await upload.seek(0)
    while chunk := await upload.read(CHUNK_SIZE):
        yield chunk


def _sample_csv(upload: UploadFile, max_rows: int = 20) -> tuple[list[str], list[dict[str, str | None]]]:
    upload.file.seek(0)
    text = io.TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(text)
        headers = reader.fieldnames or []
        if not headers or not any(name.strip() for name in headers):
            raise CsvValidationError("The CSV must contain a header row.")
        if any("\x00" in name for name in headers):
            raise CsvValidationError("The uploaded file is not a valid UTF-8 CSV.")
        if len(set(headers)) != len(headers):
            raise CsvValidationError("Column names must be unique.")
        rows = []
        total_chars = 0
        for row in reader:
            if None in row:
                raise CsvValidationError("A row contains more fields than the CSV header.")
            safe_row = {key: (value[:2_000] if value is not None else None) for key, value in row.items()}
            row_chars = sum(len(value or "") for value in safe_row.values())
            if total_chars + row_chars > 256 * 1024:
                break
            rows.append(safe_row)
            total_chars += row_chars
            if len(rows) >= max_rows:
                break
        return headers, rows
    except (UnicodeDecodeError, csv.Error) as exc:
        raise CsvValidationError("The uploaded file is not a readable UTF-8 CSV.") from exc
    finally:
        text.detach()
        upload.file.seek(0)


@router.post("/upload", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_dataset(user: CurrentUser, file: Annotated[UploadFile, File()], name: str | None = Query(default=None)):
    filename = _safe_filename(file.filename)
    settings = get_settings()
    digest, size = await _hash_and_measure(file, settings.max_upload_bytes)
    try:
        headers, sample_rows = _sample_csv(file)
    except CsvValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    dataset_id = str(uuid.uuid4())
    owner_id = str(uuid.UUID(user["sub"]))
    object_key = f"{owner_id}/{dataset_id}/raw/{filename}"
    dataset_name = (name or filename.removesuffix(Path(filename).suffix)).strip()[:120] or filename
    now_fields = {
        "id": dataset_id,
        "owner_id": owner_id,
        "name": dataset_name,
        "original_filename": filename,
        "storage_key": object_key,
        "byte_size": size,
        "content_sha256": digest,
        "source_type": "upload",
        "status": "uploaded",
        "detected_schema": [],
        "preview_data": {"columns": headers, "rows": sample_rows},
        "row_count": None,
        "column_count": None,
    }
    admin = SupabaseAdmin()
    try:
        await admin.upload(object_key, _file_stream(file), size, "text/csv")
        datasets = await admin.request("POST", "datasets", json=now_fields, params={"select": "*"}, headers={"Prefer": "return=representation"})
    except Exception as exc:
        try:
            await admin.delete_object(object_key)
        except Exception as cleanup_exc:
            logger.warning("Storage cleanup failed for dataset upload", exc_info=cleanup_exc)
        try:
            await admin.request("DELETE", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"})
        except Exception as cleanup_exc:
            logger.warning("Metadata cleanup failed for dataset upload", exc_info=cleanup_exc)
        raise HTTPException(status_code=502, detail="The dataset could not be stored. Please retry the upload.") from exc
    return {"dataset": datasets[0], "status": "uploaded"}


@router.post("/upload-intents", status_code=status.HTTP_201_CREATED)
async def create_upload_intent(body: UploadIntent, user: CurrentUser) -> dict[str, Any]:
    filename = _safe_filename(body.filename)
    settings = get_settings()
    if body.byte_size < 1:
        raise HTTPException(status_code=400, detail="The selected file is empty.")
    if body.byte_size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.")
    owner_id = str(uuid.UUID(user["sub"]))
    dataset_id = str(uuid.uuid4())
    object_key = f"{owner_id}/{dataset_id}/raw/{filename}"
    dataset_name = (body.name or filename.removesuffix(Path(filename).suffix)).strip()[:120] or filename
    admin = SupabaseAdmin()
    await admin.request("POST", "datasets", json={
        "id": dataset_id, "owner_id": owner_id, "name": dataset_name,
        "original_filename": filename, "storage_key": object_key,
        "byte_size": body.byte_size, "content_sha256": None,
        "source_type": "upload", "status": "uploading", "detected_schema": [],
        "preview_data": {"columns": [], "rows": []}, "row_count": None, "column_count": None,
    }, params={"select": "id,owner_id,original_filename,byte_size"}, headers={"Prefer": "return=representation"})
    return {"dataset_id": dataset_id, "owner_id": owner_id, "object_key": object_key, "bucket": "private-datasets", "byte_size": body.byte_size}


@router.post("/{dataset_id}/complete-upload")
async def complete_upload(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    dataset = await get_dataset(dataset_id, user)
    if dataset.get("status") != "uploading":
        raise HTTPException(status_code=409, detail="This dataset is not waiting for an upload to complete.")
    try:
        actual_size = await admin.object_size(dataset["storage_key"])
        if actual_size != int(dataset["byte_size"]):
            await admin.delete_object(dataset["storage_key"])
            await admin.request("DELETE", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"})
            raise HTTPException(status_code=422, detail="The uploaded file size does not match the upload request.")
        prefix = await admin.download_prefix(dataset["storage_key"])
        upload = UploadFile(filename=dataset["original_filename"], file=io.BytesIO(prefix))
        headers, sample_rows = _sample_csv(upload)
    except HTTPException:
        raise
    except (CsvValidationError, UnicodeDecodeError, csv.Error) as exc:
        try:
            await admin.delete_object(dataset["storage_key"])
            await admin.request("DELETE", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"})
        except Exception:
            logger.exception("Failed to clean up invalid resumable upload")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The uploaded object could not be verified or previewed.") from exc
    preview = {"columns": headers, "rows": sample_rows}
    await admin.request("PATCH", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"}, json={
        "status": "uploaded", "preview_data": preview,
    }, headers={"Prefer": "return=minimal"})
    return {"dataset_id": str(dataset_id), "status": "uploaded", "preview": {"columns": headers, "rows": sample_rows}}


@router.post("/{dataset_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def start_processing(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, str]:
    dataset = await get_dataset(dataset_id, user)
    if dataset.get("status") in {"uploading", "queued", "processing"}:
        raise HTTPException(status_code=409, detail="Finish the upload or current processing job before starting another run.")
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    active_jobs = await admin.request("GET", "processing_jobs", params={
        "select": "id,status", "dataset_id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}",
        "status": "in.(queued,running)", "order": "created_at.desc", "limit": "1",
    })
    if active_jobs:
        return {"job_id": active_jobs[0]["id"], "status": active_jobs[0]["status"]}
    job_id = str(uuid.uuid4())
    try:
        await admin.request("POST", "processing_jobs", json={
            "id": job_id, "dataset_id": str(dataset_id), "owner_id": owner_id,
            "status": "queued", "stage": "extract", "progress": 0,
        }, headers={"Prefer": "return=minimal"})
        await admin.request("PATCH", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"},
                            json={"status": "queued"}, headers={"Prefer": "return=minimal"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The processing job could not be queued.") from exc
    return {"job_id": job_id, "status": "queued"}


@router.get("")
async def list_datasets(user: CurrentUser, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    return await admin.request("GET", "datasets", params={
        "select": "id,name,original_filename,byte_size,status,source_type,source_metadata,row_count,column_count,active_version,created_at,detected_schema",
        "owner_id": f"eq.{owner_id}", "order": "created_at.desc", "limit": str(limit), "offset": str(offset),
    })


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    rows = await admin.request("GET", "datasets", params={"select": "*", "id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}", "limit": "1"})
    if not rows:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return rows[0]


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(dataset_id: uuid.UUID, user: CurrentUser) -> Response:
    """Delete an owned dataset and its raw/processed storage objects."""
    owner_id = str(uuid.UUID(user["sub"]))
    dataset = await get_dataset(dataset_id, user)
    admin = SupabaseAdmin()

    active_jobs = await admin.request("GET", "processing_jobs", params={
        "select": "id", "dataset_id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}",
        "status": "in.(queued,running)", "limit": "1",
    })
    if active_jobs:
        raise HTTPException(status_code=409, detail="Wait for dataset processing to finish before deleting it.")

    versions = await admin.request("GET", "dataset_versions", params={
        "select": "raw_storage_key,processed_storage_key", "dataset_id": f"eq.{dataset_id}",
    })
    object_keys = {dataset["storage_key"]} if dataset.get("storage_key") else set()
    for version in versions:
        object_keys.update(key for key in (version.get("raw_storage_key"), version.get("processed_storage_key")) if key)

    try:
        for object_key in object_keys:
            try:
                await admin.delete_object(object_key)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != status.HTTP_404_NOT_FOUND:
                    raise
    except Exception as exc:
        logger.exception("Storage cleanup failed while deleting dataset %s", dataset_id)
        raise HTTPException(status_code=502, detail="Stored dataset files could not all be removed. Retry the delete action.") from exc

    try:
        await admin.request("DELETE", "datasets", params={"id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}"})
    except Exception as exc:
        logger.exception("Metadata cleanup failed while deleting dataset %s", dataset_id)
        raise HTTPException(status_code=502, detail="Dataset files were removed, but its record could not be deleted. Retry the delete action.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{dataset_id}/preview")
async def dataset_preview(dataset_id: uuid.UUID, user: CurrentUser, rows: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    dataset = await get_dataset(dataset_id, user)
    saved = dataset.get("preview_data") or {"columns": [], "rows": []}
    schema = {column.get("name"): column.get("inferred_type", "Pending processing") for column in dataset.get("detected_schema", [])}
    columns = [{"name": name, "inferred_type": schema.get(name, "Pending processing")} for name in saved.get("columns", [])]
    return {"dataset_id": str(dataset_id), "columns": columns, "preview": saved.get("rows", [])[:rows], "row_count": dataset.get("row_count")}


@router.get("/{dataset_id}/jobs")
async def dataset_jobs(dataset_id: uuid.UUID, user: CurrentUser) -> list[dict[str, Any]]:
    owner_id = str(uuid.UUID(user["sub"]))
    # Validate the parent ownership first; service-role queries are always owner-scoped.
    await get_dataset(dataset_id, user)
    admin = SupabaseAdmin()
    return await admin.request("GET", "processing_jobs", params={
        "select": "id,status,stage,progress,error_code,error_message,retry_count,started_at,finished_at,created_at",
        "dataset_id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}", "order": "created_at.desc",
    })


@router.get("/{dataset_id}/quality")
async def dataset_quality(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any] | None:
    dataset = await get_dataset(dataset_id, user)
    if not dataset.get("active_version"):
        return None
    admin = SupabaseAdmin()
    versions = await admin.request("GET", "dataset_versions", params={
        "select": "id,version_number,created_at", "dataset_id": f"eq.{dataset_id}",
        "version_number": f"eq.{dataset['active_version']}", "limit": "1",
    })
    if not versions:
        return None
    reports = await admin.request("GET", "data_quality_reports", params={
        "select": "summary,column_report,created_at", "dataset_version_id": f"eq.{versions[0]['id']}", "limit": "1",
    })
    return reports[0] if reports else None
