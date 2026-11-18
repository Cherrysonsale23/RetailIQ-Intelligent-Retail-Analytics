import asyncio
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import httpx
import polars as pl

from app.datasets.profiling import timestamp_column_overrides, validate_csv_header

KAGGLE_API = "https://www.kaggle.com/api/v1"
DATASET_REF = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")


def _safe_file_path(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


class KaggleSourceError(ValueError):
    pass


def parse_dataset_ref(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname not in {"kaggle.com", "www.kaggle.com"}:
            raise KaggleSourceError("Enter a Kaggle dataset URL or owner/dataset-slug reference.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 3 or parts[0] != "datasets":
            raise KaggleSourceError("The URL must point to a Kaggle dataset page.")
        candidate = f"{parts[1]}/{parts[2]}"
    if not DATASET_REF.fullmatch(candidate):
        raise KaggleSourceError("Enter a valid Kaggle dataset reference such as owner/dataset-slug.")
    return candidate


async def list_dataset_files(dataset_ref: str) -> list[dict]:
    url = f"{KAGGLE_API}/datasets/list/{quote(dataset_ref, safe='/')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json", "User-Agent": "MeridianAnalytics/1.0"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise KaggleSourceError("Kaggle could not return this dataset's file list. Confirm the URL and that it is public.") from exc
    files = payload.get("datasetFiles", [])
    result = []
    for item in files:
        name = item.get("name") or item.get("nameNullable")
        size = item.get("totalBytes")
        if name and _safe_file_path(name) and name.lower().endswith(".csv") and isinstance(size, int):
            result.append({"name": name, "total_bytes": size, "created_at": item.get("creationDate")})
    if not result:
        message = payload.get("errorMessage") or "This Kaggle dataset has no accessible CSV files."
        raise KaggleSourceError(message)
    return result


async def download_csv(dataset_ref: str, file_name: str, directory: Path, expected_size: int) -> Path:
    safe_path = _safe_file_path(file_name)
    if not safe_path:
        raise KaggleSourceError("Kaggle returned an unsafe file path.")
    encoded_file = quote(file_name, safe="/")
    url = f"{KAGGLE_API}/datasets/download/{quote(dataset_ref, safe='/')}/{encoded_file}"
    csv_path = directory.joinpath(*safe_path.parts)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path = directory / f"{safe_path.name}.zip"
    try:
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(900, connect=30), follow_redirects=True) as client,
            client.stream("GET", url, headers={"User-Agent": "MeridianAnalytics/1.0"}) as response,
        ):
            response.raise_for_status()
            with zip_path.open("wb") as output:
                async for chunk in response.aiter_bytes(4 * 1024 * 1024):
                    await asyncio.to_thread(output.write, chunk)
        with zipfile.ZipFile(zip_path) as archive:
            candidates = [item for item in archive.infolist() if not item.is_dir() and _safe_file_path(item.filename) and PurePosixPath(item.filename).as_posix() == safe_path.as_posix()]
            if len(candidates) != 1:
                raise KaggleSourceError(f"Kaggle did not return the requested file {file_name} in its archive.")
            selected = candidates[0]
            if selected.file_size != expected_size:
                raise KaggleSourceError(f"The size reported by Kaggle for {file_name} changed; refresh the file list and retry.")
            with archive.open(selected) as source, csv_path.open("wb") as output:
                while chunk := await asyncio.to_thread(source.read, 4 * 1024 * 1024):
                    await asyncio.to_thread(output.write, chunk)
    except KaggleSourceError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, httpx.HTTPError) as exc:
        raise KaggleSourceError(f"Kaggle could not download {file_name}. The job can be retried after checking connectivity.") from exc
    finally:
        zip_path.unlink(missing_ok=True)
    if csv_path.stat().st_size != expected_size:
        csv_path.unlink(missing_ok=True)
        raise KaggleSourceError(f"The downloaded size for {file_name} did not match Kaggle's manifest.")
    return csv_path


def available_temp_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def csv_profile(path: Path, schema_overrides: dict[str, pl.DataType] | None = None) -> dict:
    try:
        overrides = timestamp_column_overrides(validate_csv_header(path))
        overrides.update(schema_overrides or {})
        frame = pl.scan_csv(path, infer_schema_length=10_000, try_parse_dates=True, schema_overrides=overrides, raise_if_empty=True)
        schema = frame.collect_schema()
        expressions = [pl.len().alias("row_count")]
        expressions.extend(pl.col(name).null_count().alias(f"missing_{index}") for index, name in enumerate(schema.names()))
        values = frame.select(expressions).collect(engine="streaming").row(0, named=True)
        preview = frame.limit(12).collect(engine="streaming").to_dicts()
        columns = [{
            "name": name,
            "inferred_type": str(dtype),
            "nullable": int(values[f"missing_{index}"]) > 0,
            "missing_count": int(values[f"missing_{index}"]),
            "distinct_count": None,
        } for index, (name, dtype) in enumerate(schema.items())]
        return {"row_count": int(values["row_count"]), "column_count": len(columns), "columns": columns, "preview": preview, "schema": schema}
    except Exception as exc:
        raise KaggleSourceError(f"Could not inspect the Kaggle CSV: {exc}") from exc


def csv_to_parquet(source: Path, target: Path, schema_overrides: dict[str, pl.DataType] | None = None) -> None:
    try:
        overrides = timestamp_column_overrides(validate_csv_header(source))
        overrides.update(schema_overrides or {})
        frame = pl.scan_csv(source, infer_schema_length=10_000, try_parse_dates=True, schema_overrides=overrides, raise_if_empty=True)
        frame.sink_parquet(target, compression="zstd", engine="streaming")
    except Exception as exc:
        raise KaggleSourceError(f"Could not convert {source.name} into a temporary analytics format: {exc}") from exc
