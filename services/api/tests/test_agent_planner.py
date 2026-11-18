import polars as pl
import pytest
from pydantic import ValidationError

from app.agent.planner import AnalysisPlan, local_plan
from app.agent.runtime import contextual_local_plan, execute_plan, local_answer


def ecommerce_fixture(tmp_path):
    path = tmp_path / "agent_fixture.parquet"
    pl.DataFrame({"event_type": ["view", "purchase", "view"], "category_code": ["home", "home", "beauty"],
                  "product_id": [1, 1, 2], "brand": ["A", "A", "B"], "user_session": ["s1", "s1", "s2"]}).write_parquet(path)
    return path


@pytest.mark.parametrize(("question", "action", "dimension", "event"), [
    ("Which category has the highest purchases?", "ranking", "category", "purchase"),
    ("Top 10 most viewed products", "ranking", "product_id", "view"),
    ("Which brands have highest conversion rates?", "ranking", "brand", "conversion"),
])
def test_local_planner_maps_catalog_questions(question, action, dimension, event):
    plan = local_plan(question)
    assert plan is not None
    assert (plan.action, plan.dimension, plan.event) == (action, dimension, event)


def test_local_planner_handles_trends_and_rejects_unknown_requests():
    assert local_plan("How does activity vary throughout the day?").time_grain == "hourly"
    assert local_plan("Tell me a joke") is None


def test_local_followup_uses_prior_analysis_context():
    history = [{"role": "assistant", "tool_reference": {"plan": {
        "action": "ranking", "dimension": "product_id", "event": "view", "time_grain": None, "limit": 10,
    }}}]
    followup = contextual_local_plan("What about brands?", history)
    assert followup is not None
    assert followup.dimension == "brand"
    assert followup.event == "view"


def test_catalog_plan_validation_rejects_unbounded_or_incomplete_tools():
    with pytest.raises(ValidationError):
        AnalysisPlan(action="ranking", dimension="category", event=None)
    with pytest.raises(ValidationError):
        AnalysisPlan(action="ranking", dimension="category", event="purchase", limit=100)


def test_agent_executes_against_processed_rows_and_returns_evidence(tmp_path):
    path = ecommerce_fixture(tmp_path)
    plan = local_plan("Which category has the highest purchases?")
    result = execute_plan(path, "dataset-1", 1, plan)
    assert result["items"][0]["category_code"] == "home"
    assert result["items"][0]["purchases"] == 1
    answer = local_answer("Which category has the highest purchases?", plan, result)
    assert "home" in answer and "R-001" in answer
