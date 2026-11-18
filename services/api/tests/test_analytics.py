from pathlib import Path

import polars as pl

from app.analytics.engine import (
    analyze_cohorts,
    analyze_correlations,
    analyze_customers,
    analyze_overview,
    analyze_products,
    analyze_time,
)


def ecommerce_fixture(tmp_path: Path) -> Path:
    frame = pl.DataFrame({
        "event_time": ["2019-10-01 08:00:00", "2019-10-01 08:05:00", "2019-10-01 08:06:00", "2019-10-02 18:00:00", "2019-10-02 18:04:00"],
        "event_type": ["view", "cart", "purchase", "view", "cart"],
        "product_id": [10, 10, 10, 20, 20],
        "category_code": ["home", "home", "home", "beauty", "beauty"],
        "brand": ["A", "A", "A", "B", "B"],
        "price": [19.5, 19.5, 19.5, 9.0, 9.0],
        "discount_amount": [0.0, 1.0, 1.0, 0.0, 2.0],
        "user_id": [1, 1, 1, 2, 2],
        "user_session": ["s1", "s1", "s1", "s2", "s2"],
    })
    path = tmp_path / "events.parquet"
    frame.write_parquet(path)
    return path


def test_overview_uses_dataset_values_and_explicit_definitions(tmp_path: Path) -> None:
    result = analyze_overview(ecommerce_fixture(tmp_path), "dataset-1", 1)
    metrics = result["metrics"]
    assert metrics["total_events"]["value"] == 5
    assert metrics["unique_users"]["value"] == 2
    assert metrics["unique_sessions"]["value"] == 2
    assert metrics["product_views"]["value"] == 2
    assert metrics["add_to_cart_events"]["value"] == 2
    assert metrics["purchase_events"]["value"] == 1
    assert metrics["session_conversion_rate"]["value"] == 0.5
    assert metrics["cart_abandonment_rate"]["value"] == 0.5
    assert metrics["observed_purchase_event_value"]["value"] == 19.5
    assert "not verified order revenue" in metrics["observed_purchase_event_value"]["definition"]
    assert result["evidence"]


def test_product_and_time_aggregations_use_real_rows(tmp_path: Path) -> None:
    path = ecommerce_fixture(tmp_path)
    products = analyze_products(path, "dataset-1", 1)
    assert {row["product_id"] for row in products["products"]["top_viewed"]} == {10, 20}
    assert products["brands"]["items"][0]["brand"] == "A"
    series = analyze_time(path, "dataset-1", 1)
    assert series["supported"] is True
    assert len(series["hourly"]) == 2
    assert sum(row["events"] for row in series["daily"]) == 5


def test_unsupported_metrics_are_explained(tmp_path: Path) -> None:
    path = tmp_path / "generic.parquet"
    pl.DataFrame({"amount": [5, 8], "region": ["west", "east"]}).write_parquet(path)
    result = analyze_overview(path, "dataset-2", 1)
    assert result["metrics"]["unique_users"]["supported"] is False
    assert result["metrics"]["session_conversion_rate"]["supported"] is False
    assert analyze_time(path, "dataset-2", 1)["supported"] is False


def test_customer_cohort_and_correlation_analytics_are_data_driven(tmp_path: Path) -> None:
    path = ecommerce_fixture(tmp_path)
    customers = analyze_customers(path, "dataset-1", 1)
    assert customers["user_count"] == 2
    assert customers["returning_user_summary"] == {"returning_users": 0, "single_session_users": 2}
    assert sum(row["users"] for row in customers["engagement_segments"]) == 2
    cohorts = analyze_cohorts(path, "dataset-1", 1)
    assert cohorts["supported"] is True
    assert len(cohorts["cohorts"]) == 1
    assert cohorts["cohorts"][0]["active_users"] == 2
    assert all(row["retention_rate"] == 1.0 for row in cohorts["cohorts"])
    correlations = analyze_correlations(path, "dataset-1", 1)
    assert correlations["supported"] is True
    assert correlations["correlations"]
