import hashlib
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from app.workers.pipeline import process_job


class MemoryAdmin:
    def __init__(self, raw: bytes) -> None:
        self.objects = {"user/dataset/raw/events.csv": raw}
        self.dataset = {
            "id": "dataset-id", "owner_id": "user-id", "storage_key": "user/dataset/raw/events.csv",
            "content_sha256": hashlib.sha256(raw).hexdigest(), "active_version": 0,
        }
        self.job = {"id": "job-id", "dataset_id": "dataset-id", "owner_id": "user-id"}
        self.versions: list[dict[str, Any]] = []
        self.reports: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []

    async def request(self, method: str, table: str, **kwargs: Any) -> Any:
        if method == "GET" and table == "datasets":
            return [self.dataset]
        if method == "PATCH" and table == "datasets":
            self.dataset.update(kwargs["json"])
            return None
        if method == "PATCH" and table == "processing_jobs":
            self.job.update(kwargs["json"])
            return None
        if method == "POST" and table == "dataset_versions":
            row = kwargs["json"] | {"id": "version-id"}
            self.versions.append(row)
            return [{"id": "version-id"}]
        if method == "POST" and table == "data_quality_reports":
            self.reports.append(kwargs["json"])
            return None
        if method == "POST" and table == "processing_logs":
            self.logs.append(kwargs["json"])
            return None
        raise AssertionError(f"Unexpected query: {method} {table}")

    async def download_to_path(self, object_key: str, destination: Path) -> int:
        body = self.objects[object_key]
        destination.write_bytes(body)
        return len(body)

    async def upload_path(self, object_key: str, source: Path, content_type: str) -> None:
        assert content_type == "application/vnd.apache.parquet"
        self.objects[object_key] = source.read_bytes()


@pytest.mark.asyncio
async def test_worker_profiles_preserves_raw_and_publishes_parquet_version() -> None:
    raw = b"event_type,price,user_id\nview,1,1\nview,1,1\npurchase,200,2\n"
    admin = MemoryAdmin(raw)
    await process_job(admin.job, admin)  # type: ignore[arg-type]
    assert admin.dataset["status"] == "ready"
    assert admin.dataset["active_version"] == 1
    assert admin.dataset["row_count"] == 3
    assert admin.job["status"] == "succeeded"
    assert admin.job["progress"] == 100
    assert admin.versions[0]["transformation_config"]["raw_preserved"] is True
    assert admin.objects["user/dataset/raw/events.csv"] == raw
    assert len(admin.reports) == 1
    report = admin.reports[0]["summary"]
    assert report["duplicate_rows"] == 1
    assert report["automatic_cleaning_applied"] is False
    processed = pl.read_parquet(admin.objects["user-id/dataset-id/versions/1/data.parquet"])
    assert processed.height == 3
    assert len(admin.logs) >= 3
