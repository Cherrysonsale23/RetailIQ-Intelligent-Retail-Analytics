import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from app.core.config import Settings


class AnalysisPlan(BaseModel):
    action: Literal["overview", "ranking", "trend"]
    dimension: Literal["product_id", "brand", "category"] | None = None
    event: Literal["view", "cart", "purchase", "conversion"] | None = None
    time_grain: Literal["hourly", "daily"] | None = None
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_prerequisites(self):
        if self.action == "ranking" and (self.dimension is None or self.event is None):
            raise ValueError("Rankings require a dimension and measure.")
        if self.action == "trend" and self.time_grain is None:
            raise ValueError("Trends require a time grain.")
        return self


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class GroundedNarrative(BaseModel):
    claims: list[GroundedClaim] = Field(min_length=1, max_length=6)


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "select_dataset_analysis",
        "description": "Choose exactly one supported deterministic analysis based on the user's question and available dataset schema. Do not calculate or invent values.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["overview", "ranking", "trend"]},
                "dimension": {"type": ["string", "null"], "enum": ["product_id", "brand", "category", None]},
                "event": {"type": ["string", "null"], "enum": ["view", "cart", "purchase", "conversion", None]},
                "time_grain": {"type": ["string", "null"], "enum": ["hourly", "daily", None]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["action", "dimension", "event", "time_grain", "limit"],
            "additionalProperties": False,
        },
    },
}

NARRATIVE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "grounded_analytics_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
                        },
                        "required": ["text", "evidence_ids"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["claims"],
            "additionalProperties": False,
        },
    },
}


def local_plan(question: str) -> AnalysisPlan | None:
    text = question.casefold()
    ranking = any(term in text for term in ("top", "highest", "most", "best", "rank", "popular"))
    dimension = "brand" if "brand" in text else "category" if any(term in text for term in ("category", "categories")) else "product_id"
    if ranking:
        if any(term in text for term in ("conversion", "convert")):
            return AnalysisPlan(action="ranking", dimension=dimension, event="conversion", limit=_limit(text))
        event = "purchase" if any(term in text for term in ("purchase", "purchased", "bought", "sales")) else "cart" if any(term in text for term in ("cart", "basket")) else "view" if any(term in text for term in ("view", "viewed", "seen")) else None
        if event:
            return AnalysisPlan(action="ranking", dimension=dimension, event=event, limit=_limit(text))
    if any(term in text for term in ("hour", "hourly", "throughout the day", "daily", "day by day", "over time", "trend", "trends")):
        grain = "hourly" if any(term in text for term in ("hour", "throughout the day")) else "daily"
        return AnalysisPlan(action="trend", time_grain=grain)
    if any(term in text for term in ("insight", "overview", "conversion rate", "abandonment", "funnel", "how many", "total", "summary", "users", "sessions", "revenue")):
        return AnalysisPlan(action="overview")
    return None


def _limit(question: str) -> int:
    match = re.search(r"\btop\s+(\d{1,2})\b", question)
    return max(1, min(20, int(match.group(1)))) if match else 10


async def llm_plan(question: str, schema: list[dict], history: list[dict], settings: Settings) -> AnalysisPlan:
    messages = [
        {"role": "system", "content": "Select one analysis from the provided function schema. Available actions are overview, ranking, and trend. Do not calculate values. Only select dimensions and measures supported by the dataset columns. For follow-up questions, use the conversation context. If a request is outside the supported analysis catalogue, choose overview so the deterministic layer can report the relevant unavailable fields."},
        {"role": "user", "content": json.dumps({"dataset_schema": schema, "recent_conversation": history[-8:], "question": question}, ensure_ascii=False)},
    ]
    result = await _completion(settings, {"messages": messages, "tools": [TOOL_SCHEMA], "tool_choice": {"type": "function", "function": {"name": "select_dataset_analysis"}}, "parallel_tool_calls": False, "max_completion_tokens": 300})
    calls = result.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "select_dataset_analysis":
        raise ValueError("The planner did not return a supported analysis selection.")
    args = json.loads(calls[0]["function"]["arguments"])
    return AnalysisPlan.model_validate(args)


async def llm_narrative(question: str, results: dict, settings: Settings) -> str | None:
    evidence_ids = {item["id"] for item in results.get("evidence", [])}
    if not evidence_ids:
        return None
    messages = [
        {"role": "system", "content": "Explain the user's data question using only the provided deterministic results. Produce concise factual claims. Every claim must cite one or more exact evidence IDs present in the result. State limitations plainly. Do not infer causation, add facts, calculate numbers, or claim support where fields are missing."},
        {"role": "user", "content": json.dumps({"question": question, "computed_results": results}, ensure_ascii=False, default=str)},
    ]
    try:
        response = await _completion(settings, {"messages": messages, "response_format": NARRATIVE_SCHEMA, "max_completion_tokens": 500})
        raw = response["choices"][0]["message"]["content"]
        narrative = GroundedNarrative.model_validate_json(raw)
        if any(not set(claim.evidence_ids).issubset(evidence_ids) for claim in narrative.claims):
            return None
        return " ".join(f"{claim.text} [{', '.join(claim.evidence_ids)}]" for claim in narrative.claims)
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return None


async def _completion(settings: Settings, payload: dict) -> dict:
    if not settings.llm_api_key or not settings.llm_model:
        raise RuntimeError("The LLM provider is not configured.")
    request = {"model": settings.llm_model, **payload}
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
        response = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
            json=request,
        )
    response.raise_for_status()
    return response.json()
