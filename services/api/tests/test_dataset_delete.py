import uuid

import pytest
from fastapi import HTTPException

from app.datasets import router as dataset_routes

OWNER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DATASET = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


class MemoryAdmin:
    def __init__(self, active_jobs: bool = False) -> None:
        self.active_jobs = active_jobs
        self.objects = ["owner/dataset/raw/events.csv", "owner/dataset/versions/1/data.parquet"]
        self.deleted = False
        self.filters: list[dict] = []

    async def request(self, method: str, table: str, **kwargs):
        self.filters.append(kwargs.get("params", {}))
        if method == "GET" and table == "datasets":
            return [{"id": DATASET, "owner_id": OWNER, "storage_key": self.objects[0], "status": "ready"}]
        if method == "GET" and table == "processing_jobs":
            return [{"id": "job"}] if self.active_jobs else []
        if method == "GET" and table == "dataset_versions":
            return [{"raw_storage_key": self.objects[0], "processed_storage_key": self.objects[1]}]
        if method == "DELETE" and table == "datasets":
            self.deleted = True
            return None
        raise AssertionError((method, table))

    async def delete_object(self, key: str) -> None:
        self.objects.remove(key)


@pytest.mark.asyncio
async def test_delete_removes_owned_dataset_files_and_metadata(monkeypatch) -> None:
    memory = MemoryAdmin()
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)

    response = await dataset_routes.delete_dataset(uuid.UUID(DATASET), {"sub": OWNER})

    assert response.status_code == 204
    assert memory.objects == []
    assert memory.deleted
    assert any(params.get("owner_id") == f"eq.{OWNER}" for params in memory.filters)


@pytest.mark.asyncio
async def test_delete_is_rejected_while_processing(monkeypatch) -> None:
    memory = MemoryAdmin(active_jobs=True)
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)

    with pytest.raises(HTTPException) as error:
        await dataset_routes.delete_dataset(uuid.UUID(DATASET), {"sub": OWNER})

    assert error.value.status_code == 409
    assert not memory.deleted
    assert len(memory.objects) == 2
