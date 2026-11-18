import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.auth import CurrentUser
from app.db.supabase_rest import SupabaseAdmin

router = APIRouter(prefix="/jobs", tags=["processing"])


@router.get("/{job_id}")
async def get_job(job_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    rows = await admin.request("GET", "processing_jobs", params={
        "select": "id,dataset_id,status,stage,progress,error_code,error_message,retry_count,started_at,finished_at,created_at",
        "id": f"eq.{job_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    return rows[0]


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: uuid.UUID, user: CurrentUser) -> list[dict[str, Any]]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    jobs = await admin.request("GET", "processing_jobs", params={"select": "id", "id": f"eq.{job_id}", "owner_id": f"eq.{owner_id}", "limit": "1"})
    if not jobs:
        raise HTTPException(status_code=404, detail="Processing job not found.")
    return await admin.request("GET", "processing_logs", params={
        "select": "id,stage,severity,details,created_at", "job_id": f"eq.{job_id}", "order": "created_at.asc",
    })
