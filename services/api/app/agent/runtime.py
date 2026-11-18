import re
from pathlib import Path
from typing import Any

from app.agent.planner import AnalysisPlan
from app.analytics.engine import analyze_overview, analyze_ranking, analyze_time


def execute_plan(path: Path, dataset_id: str, version: int, plan: AnalysisPlan) -> dict[str, Any]:
    if plan.action == "overview":
        return analyze_overview(path, dataset_id, version)
    if plan.action == "ranking":
        return analyze_ranking(path, dataset_id, version, plan.dimension or "product_id", plan.event or "view", plan.limit)
    if plan.action == "trend":
        result = analyze_time(path, dataset_id, version)
        if result.get("supported"):
            grain = plan.time_grain or "daily"
            series = result.get(grain, [])
            truncated = grain == "daily" and len(series) > 366
            result["selected_grain"] = grain
            result["selected_series"] = series[-366:] if truncated else series
            result["hourly"] = result.get("hourly", []) if grain == "hourly" else []
            result["daily"] = result.get("daily", [])[-366:] if grain == "daily" else []
            result["series_truncated"] = truncated
            result["definition"] = f"Observed event counts grouped by {grain} time periods." + (" Showing the most recent 366 daily periods." if truncated else "")
        return result
    return {"supported": False, "reason": "This analysis is not in the supported tool catalogue.", "evidence": []}


def execute_snapshot_plan(snapshot: dict[str, Any], dataset_id: str, version: int, plan: AnalysisPlan) -> dict[str, Any]:
    if plan.action == "overview":
        return snapshot["overview"]
    if plan.action == "trend":
        result = dict(snapshot["time"])
        if result.get("supported"):
            grain = plan.time_grain or "daily"
            series = result.get(grain, [])
            truncated = grain == "daily" and len(series) > 366
            result.update({
                "selected_grain": grain,
                "selected_series": series[-366:] if truncated else series,
                "hourly": series if grain == "hourly" else [],
                "daily": series[-366:] if grain == "daily" else [],
                "series_truncated": truncated,
                "definition": f"Observed event counts grouped by {grain} time periods." + (" Showing the most recent 366 daily periods." if truncated else ""),
            })
        return result
    if plan.action == "ranking":
        catalog = snapshot.get("rankings", {}).get(plan.dimension or "", {})
        result = catalog.get(plan.event or "")
        if not result:
            return {"supported": False, "reason": "The requested dataset ranking was not present in the computed snapshot.", "items": [], "evidence": []}
        output = dict(result)
        output["dataset_id"] = dataset_id
        output["version"] = version
        output["items"] = output.get("items", [])[:plan.limit]
        return output
    return {"supported": False, "reason": "This analysis is not in the supported tool catalogue.", "evidence": []}


def local_answer(question: str, plan: AnalysisPlan | None, results: dict[str, Any]) -> str:
    if plan is None:
        return (
            "I can answer questions about event totals and session funnel metrics, rank products/brands/categories by views, carts, purchases or session conversion, and summarize hourly or daily trends. "
            "Try narrowing your question to one of those analyses."
        )
    evidence = results.get("evidence", [])
    citations = " ".join(f"[{item['id']}]" for item in evidence)
    if results.get("supported") is False:
        return f"This analysis is unavailable for this dataset: {results.get('reason', 'required fields were not detected.')}{(' ' + citations) if citations else ''}"
    if plan.action == "ranking":
        items = results.get("items", [])
        if not items:
            return f"No ranked values were available after excluding rows without a {plan.dimension} value. {citations}".strip()
        top = items[0]
        value = top.get(results.get("value_key", ""))
        field = results.get("dimension_column", plan.dimension)
        if plan.event == "conversion":
            formatted = f"{float(value):.1%}" if value is not None else "unavailable"
            result_label = "session conversion rate"
        else:
            formatted = f"{int(value):,}" if value is not None else "0"
            result_label = f"{plan.event} events"
        return f"The leading {field.replace('_', ' ')} by {result_label} is {top.get(field)} ({formatted}). {results.get('definition', '')} {citations}".strip()
    if plan.action == "trend":
        series = results.get("selected_series", [])
        if not series:
            return f"No valid timestamps were available for this trend. {results.get('reason', '')} {citations}".strip()
        key = "hour" if plan.time_grain == "hourly" else "date"
        peak = max(series, key=lambda row: row.get("events", 0))
        label = f"{peak.get(key)}:00" if key == "hour" else peak.get(key)
        return f"The highest observed {plan.time_grain} activity was {label}, with {peak.get('events', 0):,} events. This is a descriptive peak in the uploaded data, not a forecast. {citations}".strip()

    metrics = results.get("metrics", {})
    request = question.casefold()
    preferred = "cart_abandonment_rate" if "abandon" in request else "session_conversion_rate" if "conversion" in request else "observed_purchase_event_value" if any(word in request for word in ("revenue", "sales value", "purchase value")) else None
    if preferred:
        item = metrics.get(preferred, {})
        if not item.get("supported"):
            return f"{item.get('reason', 'The required fields were not detected.')} {citations}".strip()
        value = item.get("value")
        formatted = f"{float(value):.1%}" if isinstance(value, (float, int)) and preferred.endswith("rate") else f"{value:,.2f}" if isinstance(value, (float, int)) else str(value)
        return f"{item.get('definition')} Observed value: {formatted}. {citations}".strip()
    summary = []
    for name in ("total_events", "unique_users", "unique_sessions", "product_views", "add_to_cart_events", "purchase_events"):
        item = metrics.get(name, {})
        if item.get("supported"):
            refs = " ".join(f"[{reference}]" for reference in item.get("evidence_ids", []))
            summary.append(f"{name.replace('_', ' ').capitalize()}: {item.get('value'):,} {refs}".strip())
    if not summary:
        return "The selected dataset does not contain enough compatible fields for a general e-commerce summary. " + citations
    return "Computed dataset summary: " + "; ".join(summary) + "."


def contextual_local_plan(question: str, history: list[dict[str, Any]]) -> AnalysisPlan | None:
    from app.agent.planner import local_plan

    plan = local_plan(question)
    if plan:
        return plan
    text = question.casefold()
    if not any(term in text for term in ("what about", "and ", "those", "that", "them", "same", "instead")):
        return None
    previous = next((item for item in reversed(history) if item.get("role") == "assistant"), None)
    previous_plan = ((previous or {}).get("tool_reference") or {}).get("plan", {})
    try:
        prior = AnalysisPlan.model_validate(previous_plan)
    except (ValueError, TypeError):
        return None
    if prior.action == "ranking":
        dimension = "brand" if "brand" in text else "category" if "categor" in text else "product_id" if "product" in text else prior.dimension
        event = "conversion" if "conversion" in text else "purchase" if any(word in text for word in ("purchase", "bought", "sales")) else "cart" if "cart" in text else "view" if any(word in text for word in ("view", "seen")) else prior.event
        limit_match = re.search(r"\b(?:top|first)\s+(\d{1,2})\b", text)
        limit = max(1, min(20, int(limit_match.group(1)))) if limit_match else prior.limit
        return AnalysisPlan(action="ranking", dimension=dimension, event=event, limit=limit)
    if prior.action == "trend":
        return prior
    return prior
