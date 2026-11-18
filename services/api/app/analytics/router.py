import asyncio
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.analytics.engine import (
    analyze_cohorts,
    analyze_correlations,
    analyze_customers,
    analyze_overview,
    analyze_products,
    analyze_time,
)
from app.core.auth import CurrentUser
from app.db.supabase_rest import SupabaseAdmin

router = APIRouter(prefix="/datasets/{dataset_id}/analytics", tags=["analytics"])


async def _run(dataset_id: uuid.UUID, user: CurrentUser, function: Callable[..., dict[str, Any]], snapshot_section: str, **kwargs: Any) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    datasets = await admin.request("GET", "datasets", params={
        "select": "id,active_version,status,source_type", "id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
    })
    if not datasets:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    dataset = datasets[0]
    if dataset["status"] != "ready" or not dataset["active_version"]:
        raise HTTPException(status_code=409, detail="Process this dataset before requesting analytics.")
    if dataset.get("source_type") == "kaggle":
        versions = await admin.request("GET", "dataset_versions", params={
            "select": "id", "dataset_id": f"eq.{dataset_id}", "version_number": f"eq.{dataset['active_version']}", "limit": "1",
        })
        if not versions:
            raise HTTPException(status_code=409, detail="The analytics snapshot for this dataset version is unavailable.")
        snapshots = await admin.request("GET", "dataset_analytics_snapshots", params={
            "select": "snapshot", "dataset_id": f"eq.{dataset_id}",
            "dataset_version_id": f"eq.{versions[0]['id']}", "owner_id": f"eq.{owner_id}", "limit": "1",
        })
        if not snapshots:
            raise HTTPException(status_code=409, detail="The analytics snapshot for this dataset version is unavailable.")
        result = snapshots[0]["snapshot"][snapshot_section]
        limit = kwargs.get("limit")
        if snapshot_section == "products" and limit:
            result = {**result}
            for key in ("products", "brands", "categories"):
                if key in result and "items" in result[key]:
                    result[key] = {**result[key], "items": result[key]["items"][:limit]}
                if key in result and "top_by_event" in result[key]:
                    result[key] = {**result[key], "top_by_event": {measure: items[:limit] for measure, items in result[key]["top_by_event"].items()}}
                if key == "products" and key in result:
                    for field in ("top_viewed", "top_cart", "top_purchased", "top_conversion"):
                        if field in result[key]:
                            result[key] = {**result[key], field: result[key][field][:limit]}
        return result
    versions = await admin.request("GET", "dataset_versions", params={
        "select": "processed_storage_key", "dataset_id": f"eq.{dataset_id}",
        "version_number": f"eq.{dataset['active_version']}", "limit": "1",
    })
    if not versions or not versions[0].get("processed_storage_key"):
        raise HTTPException(status_code=409, detail="The active processed dataset version is unavailable.")
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="meridian-analysis-", suffix=".parquet", delete=False) as temp:
            path = Path(temp.name)
        await admin.download_to_path(versions[0]["processed_storage_key"], path)
        return await asyncio.to_thread(function, path, str(dataset_id), int(dataset["active_version"]), **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="This processed dataset could not be analyzed.") from exc
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)


@router.get("/overview")
async def overview(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_overview, "overview")


@router.get("/products")
async def products(dataset_id: uuid.UUID, user: CurrentUser, limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_products, "products", limit=limit)


@router.get("/time")
async def time_series(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_time, "time")


@router.get("/customers")
async def customers(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_customers, "customers")


@router.get("/cohorts")
async def cohorts(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_cohorts, "cohorts")


@router.get("/correlations")
async def correlations(dataset_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return await _run(dataset_id, user, analyze_correlations, "correlations")
