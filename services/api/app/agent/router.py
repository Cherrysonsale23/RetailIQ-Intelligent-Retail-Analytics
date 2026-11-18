import asyncio
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.planner import AnalysisPlan, llm_narrative, llm_plan
from app.agent.runtime import (
    contextual_local_plan,
    execute_plan,
    execute_snapshot_plan,
    local_answer,
)
from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.db.supabase_rest import SupabaseAdmin

router = APIRouter(prefix="/agent", tags=["AI analytics agent"])


class CreateConversation(BaseModel):
    dataset_id: uuid.UUID
    title: str = Field(default="New analysis", max_length=120)


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)
    allow_external_processing: bool = False


@router.get("/status")
async def agent_status(user: CurrentUser) -> dict[str, Any]:
    settings = get_settings()
    return {
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
        "model": settings.llm_model if settings.llm_api_key else None,
        "local_analysis_available": True,
        "external_data_disclosure": "If enabled for a message, the user's question, dataset field names/types, recent conversation context, and computed aggregate results are sent to the configured LLM provider. Raw dataset rows are not sent.",
    }


@router.get("/conversations")
async def list_conversations(user: CurrentUser, dataset_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    owner_id = str(uuid.UUID(user["sub"]))
    params = {"select": "id,dataset_id,title,created_at,updated_at", "owner_id": f"eq.{owner_id}", "order": "updated_at.desc", "limit": "50"}
    if dataset_id:
        params["dataset_id"] = f"eq.{dataset_id}"
    return await SupabaseAdmin().request("GET", "agent_conversations", params=params)


@router.post("/conversations", status_code=201)
async def create_conversation(body: CreateConversation, user: CurrentUser) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    datasets = await admin.request("GET", "datasets", params={
        "select": "id,status", "id": f"eq.{body.dataset_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
    })
    if not datasets:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if datasets[0]["status"] != "ready":
        raise HTTPException(status_code=409, detail="Process this dataset before asking it questions.")
    rows = await admin.request("POST", "agent_conversations", json={
        "owner_id": owner_id, "dataset_id": str(body.dataset_id), "title": body.title.strip() or "New analysis",
    }, params={"select": "id,dataset_id,title,created_at,updated_at"}, headers={"Prefer": "return=representation"})
    return rows[0]


async def _owned_conversation(conversation_id: uuid.UUID, owner_id: str, admin: SupabaseAdmin) -> dict[str, Any]:
    rows = await admin.request("GET", "agent_conversations", params={
        "select": "id,dataset_id,title,owner_id", "id": f"eq.{conversation_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return rows[0]


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: uuid.UUID, user: CurrentUser, limit: int = Query(default=100, ge=1, le=200)) -> list[dict[str, Any]]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    await _owned_conversation(conversation_id, owner_id, admin)
    return await admin.request("GET", "agent_messages", params={
        "select": "id,role,content,tool_reference,evidence_ids,created_at", "conversation_id": f"eq.{conversation_id}",
        "owner_id": f"eq.{owner_id}", "order": "created_at.asc", "limit": str(limit),
    })


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(conversation_id: uuid.UUID, body: SendMessage, user: CurrentUser) -> dict[str, Any]:
    owner_id = str(uuid.UUID(user["sub"]))
    admin = SupabaseAdmin()
    settings = get_settings()
    if body.allow_external_processing and not (settings.llm_api_key and settings.llm_model):
        raise HTTPException(status_code=409, detail="External LLM processing is not configured. Use local supported questions or configure the backend provider first.")
    conversation = await _owned_conversation(conversation_id, owner_id, admin)
    dataset_id = conversation.get("dataset_id")
    if not dataset_id:
        raise HTTPException(status_code=409, detail="Choose a dataset for this conversation.")
    datasets = await admin.request("GET", "datasets", params={
        "select": "id,status,active_version,detected_schema,source_type", "id": f"eq.{dataset_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
    })
    if not datasets:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    dataset = datasets[0]
    if dataset["status"] != "ready" or not dataset.get("active_version"):
        raise HTTPException(status_code=409, detail="Process this dataset before asking it questions.")
    safe_question = body.content.strip()
    if not safe_question:
        raise HTTPException(status_code=422, detail="Enter a question before sending.")

    now = datetime.now(UTC).isoformat()
    user_message_id = str(uuid.uuid4())
    await admin.request("POST", "agent_messages", json={
        "id": user_message_id, "conversation_id": str(conversation_id), "owner_id": owner_id,
        "role": "user", "content": safe_question, "created_at": now,
    }, headers={"Prefer": "return=minimal"})
    history = await admin.request("GET", "agent_messages", params={
        "select": "role,content,tool_reference", "conversation_id": f"eq.{conversation_id}", "owner_id": f"eq.{owner_id}",
        "id": f"neq.{user_message_id}",
        "order": "created_at.desc", "limit": "8",
    })
    history = list(reversed(history))
    schema = [{"name": column.get("name"), "type": column.get("inferred_type")} for column in dataset.get("detected_schema", [])]
    plan: AnalysisPlan | None
    if body.allow_external_processing:
        try:
            plan = await llm_plan(safe_question, schema, history, settings)
        except (httpx.HTTPError, ValueError, RuntimeError, KeyError):
            plan = contextual_local_plan(safe_question, history)
    else:
        plan = contextual_local_plan(safe_question, history)

    if plan is None:
        result = {"supported": False, "reason": "The local planner could not map this question to the available analyses.", "evidence": []}
        answer = local_answer(safe_question, None, result)
        plan_json = {"action": "unsupported_local_question"}
        evidence = []
        version_id = None
    else:
        versions = await admin.request("GET", "dataset_versions", params={
            "select": "id,processed_storage_key", "dataset_id": f"eq.{dataset_id}",
            "version_number": f"eq.{dataset['active_version']}", "limit": "1",
        })
        if not versions:
            raise HTTPException(status_code=409, detail="The selected dataset version is unavailable.")
        version_id = versions[0]["id"]
        if dataset.get("source_type") == "kaggle":
            snapshots = await admin.request("GET", "dataset_analytics_snapshots", params={
                "select": "snapshot", "dataset_id": f"eq.{dataset_id}",
                "dataset_version_id": f"eq.{version_id}", "owner_id": f"eq.{owner_id}", "limit": "1",
            })
            if not snapshots:
                raise HTTPException(status_code=409, detail="The analytics snapshot for this dataset version is unavailable.")
            result = execute_snapshot_plan(snapshots[0]["snapshot"], str(dataset_id), int(dataset["active_version"]), plan)
        else:
            if not versions[0].get("processed_storage_key"):
                raise HTTPException(status_code=409, detail="The processed dataset version is unavailable.")
            parquet_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(prefix="meridian-agent-", suffix=".parquet", delete=False) as temp:
                    parquet_path = Path(temp.name)
                await admin.download_to_path(versions[0]["processed_storage_key"], parquet_path)
                result = await asyncio.to_thread(execute_plan, parquet_path, str(dataset_id), int(dataset["active_version"]), plan)
            except Exception as exc:
                raise HTTPException(status_code=422, detail="The selected deterministic analysis could not be executed.") from exc
            finally:
                if parquet_path and parquet_path.exists():
                    parquet_path.unlink(missing_ok=True)
        evidence = result.get("evidence", [])
        answer = await llm_narrative(safe_question, result, settings) if body.allow_external_processing and result.get("supported", True) else None
        answer = answer or local_answer(safe_question, plan, result)
        plan_json = plan.model_dump()

    run_id = str(uuid.uuid4())
    await admin.request("POST", "analysis_runs", json={
        "id": run_id, "dataset_id": str(dataset_id), "owner_id": owner_id,
        "dataset_version_id": version_id, "question": safe_question, "plan": plan_json,
        "method_version": "meridian-analysis-catalog-v1", "status": "completed",
        "result": result, "evidence_index": evidence,
    }, headers={"Prefer": "return=minimal"})
    assistant_id = str(uuid.uuid4())
    assistant_message = await admin.request("POST", "agent_messages", json={
        "id": assistant_id, "conversation_id": str(conversation_id), "owner_id": owner_id,
        "role": "assistant", "content": answer,
        "tool_reference": {"analysis_run_id": run_id, "plan": plan_json, "result": result},
        "evidence_ids": [item["id"] for item in evidence],
    }, params={"select": "id,role,content,tool_reference,evidence_ids,created_at"}, headers={"Prefer": "return=representation"})
    title = conversation["title"]
    await admin.request("PATCH", "agent_conversations", params={"id": f"eq.{conversation_id}", "owner_id": f"eq.{owner_id}"}, json={
        "title": safe_question[:80] if title == "New analysis" else title, "updated_at": now,
    }, headers={"Prefer": "return=minimal"})
    return {"user_message_id": user_message_id, "assistant_message": assistant_message[0], "analysis_run_id": run_id, "plan": plan_json, "result": result}
