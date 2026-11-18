import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class SupabaseAdmin:
    """Server-only Supabase REST/Storage client. Callers must pass owner-scoped filters."""

    def __init__(self) -> None:
        settings = get_settings()
        key = settings.supabase_secret_key or settings.supabase_service_role_key
        if not settings.supabase_url or not key:
            raise RuntimeError("Backend Supabase URL and secret key are required.")
        self.base = settings.supabase_url.rstrip("/")
        self.key = key
        self.use_legacy_jwt = not key.startswith("sb_secret_")

    def headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.key}
        if self.use_legacy_jwt:
            headers["Authorization"] = f"Bearer {self.key}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def request(self, method: str, table: str, **kwargs: Any) -> Any:
        request_headers = {**self.headers(), **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, f"{self.base}/rest/v1/{table}", headers=request_headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    async def upload(self, object_key: str, stream: Any, content_length: int, content_type: str) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20)) as client:
            response = await client.post(
                f"{self.base}/storage/v1/object/private-datasets/{object_key}",
                content=stream,
                headers={**self.headers(content_type=content_type), "Content-Length": str(content_length), "x-upsert": "false"},
            )
        response.raise_for_status()

    async def download_to_path(self, object_key: str, destination: Path) -> int:
        total = 0
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20)) as client,
            client.stream(
                "GET",
                f"{self.base}/storage/v1/object/private-datasets/{object_key}",
                headers=self.headers(),
            ) as response,
        ):
            response.raise_for_status()
            with destination.open("wb") as output:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    output.write(chunk)
        return total

    async def object_size(self, object_key: str) -> int:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.head(
                f"{self.base}/storage/v1/object/private-datasets/{object_key}",
                headers=self.headers(),
            )
        response.raise_for_status()
        return int(response.headers.get("content-length", "0"))

    async def download_prefix(self, object_key: str, max_bytes: int = 1024 * 1024) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client, client.stream(
            "GET",
            f"{self.base}/storage/v1/object/private-datasets/{object_key}",
            headers={**self.headers(), "Range": f"bytes=0-{max_bytes - 1}"},
        ) as response:
            response.raise_for_status()
            chunks = []
            remaining = max_bytes
            async for chunk in response.aiter_bytes(min(64 * 1024, max_bytes)):
                chunks.append(chunk[:remaining])
                remaining -= min(len(chunk), remaining)
                if remaining <= 0:
                    break
            return b"".join(chunks)

    async def upload_path(self, object_key: str, source: Path, content_type: str) -> None:
        async def chunks():
            with source.open("rb") as file:
                while chunk := await asyncio.to_thread(file.read, 1024 * 1024):
                    yield chunk
        await self.upload(object_key, chunks(), source.stat().st_size, content_type)

    async def delete_object(self, object_key: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(
                f"{self.base}/storage/v1/object/private-datasets/{object_key}",
                headers=self.headers(),
            )
        response.raise_for_status()
