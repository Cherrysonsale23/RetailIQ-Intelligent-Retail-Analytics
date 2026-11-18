import uuid
from io import BytesIO
from typing import Any

import pytest
from fastapi import HTTPException, UploadFile

from app.datasets import router as dataset_routes
from app.datasets.schemas import UploadIntent


class MemorySupabase:
    def __init__(self) -> None:
        self.raw = b""
        self.rows: dict[str, Any] = {}

    async def upload(self, object_key: str, stream: Any, content_length: int, content_type: str) -> None:
        self.raw = b"".join([chunk async for chunk in stream])
        assert len(self.raw) == content_length
        assert content_type == "text/csv"

    async def request(self, method: str, table: str, **kwargs: Any) -> Any:
        if method == "POST" and table == "datasets":
            self.rows = kwargs["json"] | {"created_at": "2026-11-01T00:00:00Z"}
            return [self.rows]
        return None

    async def delete_object(self, object_key: str) -> None:
        self.raw = b""


@pytest.mark.asyncio
async def test_csv_upload_preserves_raw_and_saves_small_preview(monkeypatch) -> None:
    memory = MemorySupabase()
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)
    source = b"event_type,price,user_id\nview,12.5,1\npurchase,15.0,1\n"
    upload = UploadFile(filename="events.csv", file=BytesIO(source))
    result = await dataset_routes.upload_dataset(
        {"sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}, upload, name=None,
    )
    assert result["status"] == "uploaded"
    assert memory.raw == source
    assert result["dataset"]["preview_data"]["columns"] == ["event_type", "price", "user_id"]
    assert result["dataset"]["preview_data"]["rows"][1]["event_type"] == "purchase"
    assert result["dataset"]["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_rejects_duplicate_header_before_storage(monkeypatch) -> None:
    memory = MemorySupabase()
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)
    upload = UploadFile(filename="duplicate.csv", file=BytesIO(b"item,item\na,b\n"))
    with pytest.raises(HTTPException) as raised:
        await dataset_routes.upload_dataset(
            {"sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}, upload, name=None,
        )
    assert raised.value.status_code == 422
    assert memory.raw == b""


@pytest.mark.asyncio
async def test_large_upload_intent_is_owner_scoped_and_deferred_until_tus_finalize(monkeypatch) -> None:
    memory = MemorySupabase()
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)
    result = await dataset_routes.create_upload_intent(
        UploadIntent(filename="events.csv", byte_size=5_000_000_000),
        {"sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    )
    assert result["bucket"] == "private-datasets"
    assert result["byte_size"] == 5_000_000_000
    assert memory.rows["status"] == "uploading"
    assert memory.raw == b""


@pytest.mark.asyncio
async def test_tus_finalize_verifies_object_and_extracts_a_bounded_preview(monkeypatch) -> None:
    class FinalizeSupabase(MemorySupabase):
        async def request(self, method: str, table: str, **kwargs: Any) -> Any:
            if method == "GET" and table == "datasets":
                return [{"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "owner_id": owner,
                         "storage_key": f"{owner}/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/raw/events.csv",
                         "original_filename": "events.csv", "byte_size": len(source), "status": "uploading"}]
            return kwargs.get("json")

        async def object_size(self, object_key: str) -> int:
            return len(source)

        async def download_prefix(self, object_key: str, max_bytes: int = 1024 * 1024) -> bytes:
            return source[:max_bytes]

    owner = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    source = b"event_type,price\nview,12.5\npurchase,15.0\n"
    memory = FinalizeSupabase()
    monkeypatch.setattr(dataset_routes, "SupabaseAdmin", lambda: memory)
    result = await dataset_routes.complete_upload(uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"), {"sub": owner})
    assert result["status"] == "uploaded"
    assert result["preview"]["columns"] == ["event_type", "price"]
    assert len(result["preview"]["rows"]) == 2
