import math
from pathlib import Path
from typing import Any

import polars as pl

from app.analytics.roles import map_roles


def _metric(value: Any = None, *, definition: str, supported: bool = True, reason: str | None = None) -> dict[str, Any]:
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    return {"value": value, "supported": supported, "definition": definition, "reason": reason}


def _scan_parquet(path: Path | list[Path] | tuple[Path, ...]) -> pl.LazyFrame:
    source = [str(item) for item in path] if isinstance(path, (list, tuple)) else path
    return pl.scan_parquet(source)


def _collect(frame: pl.LazyFrame, expressions: list[pl.Expr]) -> dict[str, Any]:
    result = frame.select(expressions).collect(engine="streaming")
    return result.row(0, named=True)


def _datetime_expr(column: str, dtype: pl.DataType) -> pl.Expr:
    value = pl.col(column)
    if dtype == pl.String:
        # Normalize common CSV timestamps before explicit parses: Kaggle uses a literal
        # " UTC" suffix, while other sources use RFC3339 Z/+00:00 or naive timestamps.
        normalized = (
            value.str.strip_chars()
            .str.replace(r"^(\d{4}-\d{2}-\d{2})\s+", "${1}T")
            .str.replace(r"\s+UTC$", "Z")
        )
        return pl.coalesce([
            normalized.str.to_datetime(format="%+", strict=False),
            normalized.str.to_datetime(format="%Y-%m-%dT%H:%M:%S%.f", time_zone="UTC", strict=False),
            normalized.str.to_datetime(format="%Y-%m-%d", time_zone="UTC", strict=False),
        ])
    return value.cast(pl.Datetime, strict=False)


def analyze_overview(path: Path, dataset_id: str, version: int) -> dict[str, Any]:
    frame = _scan_parquet(path)
    schema = frame.collect_schema()
    roles = map_roles(schema.names())
    metrics: dict[str, Any] = {}
    evidence = []
    row = _collect(frame, [pl.len().alias("total_events")])
    metrics["total_events"] = _metric(int(row["total_events"]), definition="Number of rows in the active processed dataset.")
    evidence.append({"id": "E-001", "computation": "Count rows from the active processed dataset.", "dataset_id": dataset_id, "version": version})

    for role, label in (("user_id", "unique_users"), ("session_id", "unique_sessions")):
        column = roles[role]
        metrics[label] = _metric(int(_collect(frame, [pl.col(column).drop_nulls().n_unique().alias("value")])["value"]), definition=f"Distinct non-null values in `{column}`.") if column else _metric(supported=False, definition=f"Count distinct {role.replace('_', ' ')} values.", reason="No compatible identifier column was detected.")
        if column:
            evidence.append({"id": f"E-{len(evidence)+1:03}", "computation": f"Count distinct non-null `{column}` values.", "dataset_id": dataset_id, "version": version})

    event_column = roles["event_type"]
    event_counts: dict[str, int] = {}
    if event_column:
        event = pl.col(event_column).cast(pl.Utf8).str.to_lowercase().str.strip_chars()
        counts = frame.group_by(event.alias("event")).len().collect(engine="streaming")
        event_counts = {str(item["event"]): int(item["len"]) for item in counts.to_dicts() if item["event"] is not None}
        total = sum(event_counts.values())
        for token, key, definition in (
            ("view", "product_views", "Rows whose event type is `view`."),
            ("cart", "add_to_cart_events", "Rows whose event type is `cart`."),
            ("purchase", "purchase_events", "Rows whose event type is `purchase`."),
        ):
            metrics[key] = _metric(event_counts.get(token, 0), definition=definition)
        metrics["event_distribution"] = _metric([{"event": name, "count": count} for name, count in sorted(event_counts.items(), key=lambda pair: pair[1], reverse=True)], definition=f"Row counts grouped by `{event_column}`.")
        evidence.append({"id": f"E-{len(evidence)+1:03}", "computation": f"Group row counts by normalized `{event_column}` values.", "dataset_id": dataset_id, "version": version})
        metrics["event_distribution"]["total"] = total
    else:
        for key, label in (("product_views", "view events"), ("add_to_cart_events", "cart events"), ("purchase_events", "purchase events")):
            metrics[key] = _metric(supported=False, definition=f"Count {label}.", reason="No compatible event type column was detected.")
        metrics["event_distribution"] = _metric(supported=False, definition="Rows grouped by event type.", reason="No compatible event type column was detected.")

    session_column = roles["session_id"]
    if event_column and session_column:
        event = pl.col(event_column).cast(pl.Utf8).str.to_lowercase().str.strip_chars()
        sessions = frame.group_by(session_column).agg([
            event.eq("cart").any().alias("has_cart"), event.eq("purchase").any().alias("has_purchase"),
        ]).collect(engine="streaming")
        cart_sessions = sessions.filter(pl.col("has_cart")).height
        purchase_sessions = sessions.filter(pl.col("has_purchase")).height
        abandoned = sessions.filter(pl.col("has_cart") & ~pl.col("has_purchase")).height
        metrics["session_conversion_rate"] = _metric(purchase_sessions / sessions.height if sessions.height else None, definition="Sessions with at least one purchase divided by all sessions.")
        metrics["cart_abandonment_rate"] = _metric(abandoned / cart_sessions if cart_sessions else None, definition="Sessions with a cart event but no purchase divided by sessions with a cart event.", reason="No cart sessions were observed." if not cart_sessions else None)
        evidence.append({"id": f"E-{len(evidence)+1:03}", "computation": f"Group on `{session_column}`; count sessions containing cart and/or purchase events.", "dataset_id": dataset_id, "version": version})
    else:
        missing = "No compatible session identifier column was detected." if not session_column else "No compatible event type column was detected."
        metrics["session_conversion_rate"] = _metric(supported=False, definition="Purchasing sessions divided by all sessions.", reason=missing)
        metrics["cart_abandonment_rate"] = _metric(supported=False, definition="Cart sessions without a purchase divided by cart sessions.", reason=missing)

    price_column = roles["price"]
    if price_column and event_column:
        event = pl.col(event_column).cast(pl.Utf8).str.to_lowercase().str.strip_chars()
        value = _collect(frame, [pl.when(event == "purchase").then(pl.col(price_column).cast(pl.Float64, strict=False)).otherwise(None).sum().alias("purchase_price_sum")])["purchase_price_sum"]
        metrics["observed_purchase_event_value"] = _metric(value, definition=f"Sum of `{price_column}` on rows labeled purchase; this is an event-level value, not verified order revenue.")
        evidence.append({"id": f"E-{len(evidence)+1:03}", "computation": f"Sum `{price_column}` where normalized `{event_column}` equals purchase.", "dataset_id": dataset_id, "version": version})
    else:
        metrics["observed_purchase_event_value"] = _metric(supported=False, definition="Sum price on purchase event rows.", reason="A compatible price and event type column are both required.")

    event_evidence = next((item["id"] for item in evidence if item["computation"].startswith("Group row counts by normalized")), None)
    session_evidence = next((item["id"] for item in evidence if item["computation"].startswith("Group on `")), None)
    revenue_evidence = next((item["id"] for item in evidence if item["computation"].startswith("Sum `")), None)
    evidence_for_metric = {
        "total_events": "E-001",
        "unique_users": next((item["id"] for item in evidence if item["computation"].startswith("Count distinct non-null") and roles["user_id"] and roles["user_id"] in item["computation"]), None),
        "unique_sessions": next((item["id"] for item in evidence if item["computation"].startswith("Count distinct non-null") and roles["session_id"] and roles["session_id"] in item["computation"]), None),
        "product_views": event_evidence,
        "add_to_cart_events": event_evidence,
        "purchase_events": event_evidence,
        "event_distribution": event_evidence,
        "session_conversion_rate": session_evidence,
        "cart_abandonment_rate": session_evidence,
        "observed_purchase_event_value": revenue_evidence,
    }
    for metric_name, evidence_id in evidence_for_metric.items():
        if evidence_id and metric_name in metrics and metrics[metric_name]["supported"]:
            metrics[metric_name]["evidence_ids"] = [evidence_id]
    return {"dataset_id": dataset_id, "version": version, "roles": roles, "metrics": metrics, "evidence": evidence}


def _dimension_aggregates(frame: pl.LazyFrame, dimension: str, event_column: str, session_column: str | None) -> list[dict[str, Any]]:
    event = pl.col(event_column).cast(pl.Utf8).str.to_lowercase().str.strip_chars()
    grouped = frame.filter(pl.col(dimension).is_not_null()).group_by(dimension).agg([
        (event == "view").cast(pl.UInt64).sum().alias("views"),
        (event == "cart").cast(pl.UInt64).sum().alias("carts"),
        (event == "purchase").cast(pl.UInt64).sum().alias("purchases"),
    ])
    if session_column:
        per_session = frame.filter(pl.col(dimension).is_not_null() & pl.col(session_column).is_not_null()).group_by([session_column, dimension]).agg([
            event.eq("view").any().alias("has_view"), event.eq("purchase").any().alias("has_purchase"),
        ])
        conversion = per_session.group_by(dimension).agg([
            pl.col("has_view").cast(pl.UInt64).sum().alias("view_sessions"),
            (pl.col("has_view") & pl.col("has_purchase")).cast(pl.UInt64).sum().alias("purchase_after_view_sessions"),
        ]).with_columns(
            pl.when(pl.col("view_sessions") > 0)
            .then(pl.col("purchase_after_view_sessions") / pl.col("view_sessions"))
            .otherwise(None).alias("session_conversion_rate")
        )
        grouped = grouped.join(conversion, on=dimension, how="left")
    return grouped.sort("purchases", descending=True).collect(engine="streaming").to_dicts()


def analyze_products(path: Path, dataset_id: str, version: int, limit: int = 10) -> dict[str, Any]:
    frame = _scan_parquet(path)
    roles = map_roles(frame.collect_schema().names())
    product = roles["product_id"]
    event_column = roles["event_type"]
    session_column = roles["session_id"]
    output: dict[str, Any] = {"dataset_id": dataset_id, "version": version, "roles": roles, "products": {}, "brands": {}, "categories": {}}
    if not product or not event_column:
        reason = "Product and event type columns are required for product event rankings."
        output["products"] = {"supported": False, "reason": reason, "top_viewed": [], "top_purchased": []}
    else:
        ranked = _dimension_aggregates(frame, product, event_column, session_column)
        output["products"] = {
            "supported": True,
            "top_viewed": sorted(ranked, key=lambda row: row.get("views", 0), reverse=True)[:limit],
            "top_cart": sorted(ranked, key=lambda row: row.get("carts", 0), reverse=True)[:limit],
            "top_purchased": ranked[:limit],
            "top_conversion": sorted(
                (row for row in ranked if row.get("view_sessions", 0)),
                key=lambda row: row["session_conversion_rate"], reverse=True,
            )[:limit],
            "conversion_supported": bool(session_column),
            "conversion_reason": None if session_column else "A compatible session identifier is required for session-level product conversion.",
            "top_by_event": {
                "view": sorted(ranked, key=lambda row: row.get("views", 0), reverse=True)[:limit],
                "cart": sorted(ranked, key=lambda row: row.get("carts", 0), reverse=True)[:limit],
                "purchase": ranked[:limit],
                "conversion": sorted((row for row in ranked if row.get("view_sessions", 0)), key=lambda row: row["session_conversion_rate"], reverse=True)[:limit],
            },
            "definition": "Event counts grouped by product identifier. Conversion is viewed product sessions that also contain a purchase, divided by viewed product sessions.",
        }
    for role, key in (("brand", "brands"), ("category", "categories")):
        column = roles[role]
        if not column or not event_column:
            output[key] = {"supported": False, "reason": f"No compatible {role} and event type columns were detected.", "items": []}
            continue
        rows = _dimension_aggregates(frame, column, event_column, session_column)
        output[key] = {
            "supported": True,
            "items": rows[:limit],
            "top_by_event": {
                "view": sorted(rows, key=lambda row: row.get("views", 0), reverse=True)[:limit],
                "cart": sorted(rows, key=lambda row: row.get("carts", 0), reverse=True)[:limit],
                "purchase": rows[:limit],
                "conversion": sorted((row for row in rows if row.get("view_sessions", 0)), key=lambda row: row["session_conversion_rate"], reverse=True)[:limit],
            },
            "conversion_supported": bool(session_column),
            "conversion_reason": None if session_column else "A compatible session identifier is required for session-level conversion.",
            "definition": f"View/cart/purchase event counts grouped by `{column}`; conversion uses viewed sessions that also contain a purchase.",
        }
    output["evidence"] = [{"id": "P-001", "computation": "Grouped observed view/cart/purchase rows by the detected product, brand, or category column.", "dataset_id": dataset_id, "version": version}]
    if session_column:
        output["evidence"].append({"id": "P-002", "computation": "Grouped by session and dimension; conversion requires both a view and purchase in that group.", "dataset_id": dataset_id, "version": version})
    return output


def analyze_ranking(path: Path, dataset_id: str, version: int, dimension: str, event: str, limit: int = 10) -> dict[str, Any]:
    frame = _scan_parquet(path)
    roles = map_roles(frame.collect_schema().names())
    dimension_column = roles.get(dimension)
    event_column = roles.get("event_type")
    session_column = roles.get("session_id")
    allowed_dimensions = {"product_id", "brand", "category"}
    if dimension not in allowed_dimensions:
        return {"supported": False, "reason": "The requested ranking dimension is not in the analysis catalog.", "items": [], "evidence": []}
    if not dimension_column or not event_column:
        return {"supported": False, "reason": f"Compatible {dimension.replace('_', ' ')} and event type columns are required.", "items": [], "evidence": []}
    if event not in {"view", "cart", "purchase", "conversion"}:
        return {"supported": False, "reason": "The requested event measure is not supported.", "items": [], "evidence": []}
    rows = _dimension_aggregates(frame, dimension_column, event_column, session_column)
    if event == "conversion":
        if not session_column:
            return {"supported": False, "reason": "A compatible session identifier is required for session-level conversion.", "items": [], "evidence": []}
        rows = [row for row in rows if row.get("view_sessions", 0)]
        rows.sort(key=lambda row: row.get("session_conversion_rate") or 0, reverse=True)
        value_key = "session_conversion_rate"
        definition = "Sessions with both a view and purchase for the dimension, divided by sessions with a view for the dimension."
    else:
        value_key = {"view": "views", "cart": "carts", "purchase": "purchases"}[event]
        rows.sort(key=lambda row: row.get(value_key, 0), reverse=True)
        definition = f"`{event}` event counts grouped by `{dimension_column}`."
    evidence = [{"id": "R-001", "computation": definition, "dataset_id": dataset_id, "version": version}]
    return {"supported": True, "dimension": dimension, "dimension_column": dimension_column, "event": event, "value_key": value_key, "items": rows[:limit], "definition": definition, "evidence": evidence}


def analyze_time(path: Path, dataset_id: str, version: int) -> dict[str, Any]:
    frame = _scan_parquet(path)
    roles = map_roles(frame.collect_schema().names())
    time_column = roles["event_time"]
    event_column = roles["event_type"]
    if not time_column:
        return {"dataset_id": dataset_id, "version": version, "supported": False, "reason": "No compatible timestamp column was detected.", "hourly": [], "daily": []}
    time_dtype = frame.collect_schema()[time_column]
    date_expr = _datetime_expr(time_column, time_dtype)
    expressions = [pl.len().alias("events")]
    if event_column:
        expressions.append(pl.col(event_column).cast(pl.Utf8).str.to_lowercase().eq("purchase").cast(pl.UInt64).sum().alias("purchases"))
    base = frame.with_columns(date_expr.alias("__analysis_time")).filter(pl.col("__analysis_time").is_not_null())
    hourly = base.group_by(pl.col("__analysis_time").dt.hour().alias("hour")).agg(expressions).sort("hour").collect(engine="streaming").to_dicts()
    daily = base.group_by(pl.col("__analysis_time").dt.date().alias("date")).agg(expressions).sort("date").collect(engine="streaming").to_dicts()
    daily = [{key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()} for row in daily]
    return {"dataset_id": dataset_id, "version": version, "supported": True, "timestamp_column": time_column, "hourly": hourly, "daily": daily, "definition": "Events grouped by detected timestamp hour and calendar date.", "evidence": [{"id": "T-001", "computation": f"Grouped valid timestamps in `{time_column}` by calendar hour and date.", "dataset_id": dataset_id, "version": version}]}


def analyze_customers(path: Path, dataset_id: str, version: int, limit: int = 20) -> dict[str, Any]:
    frame = _scan_parquet(path)
    roles = map_roles(frame.collect_schema().names())
    user_column, session_column, event_column = roles["user_id"], roles["session_id"], roles["event_type"]
    if not user_column:
        return {"dataset_id": dataset_id, "version": version, "supported": False, "reason": "A compatible user or customer identifier is required.", "segments": [], "top_users": [], "evidence": []}
    event = pl.col(event_column).cast(pl.Utf8).str.to_lowercase().str.strip_chars() if event_column else None
    aggregations = [pl.len().alias("events")]
    if session_column:
        aggregations.append(pl.col(session_column).drop_nulls().n_unique().alias("sessions"))
    if event is not None:
        aggregations.append(event.eq("purchase").cast(pl.UInt64).sum().alias("purchases"))
    users = frame.filter(pl.col(user_column).is_not_null()).group_by(user_column).agg(aggregations).collect(engine="streaming")
    count = users.height
    if count:
        quantiles = users.select([pl.col("events").quantile(1 / 3, interpolation="linear").alias("lower"), pl.col("events").quantile(2 / 3, interpolation="linear").alias("upper")]).row(0)
        lower, upper = float(quantiles[0] or 0), float(quantiles[1] or 0)
        users = users.with_columns(pl.when(pl.col("events") <= lower).then(pl.lit("lower engagement")).when(pl.col("events") <= upper).then(pl.lit("moderate engagement")).otherwise(pl.lit("higher engagement")).alias("engagement_segment"))
    returning = []
    if session_column:
        returning = users.select((pl.col("sessions") > 1).sum().alias("returning_users"), (pl.col("sessions") <= 1).sum().alias("single_session_users")).to_dicts()[0]
    segment_counts = users.group_by("engagement_segment").agg(pl.len().alias("users")).sort("engagement_segment").to_dicts() if count else []
    sort_column = "purchases" if "purchases" in users.columns else "events"
    top_users = users.sort(sort_column, descending=True).head(limit).to_dicts()
    evidence = [{"id": "C-001", "computation": f"Aggregated non-null `{user_column}` values into event counts per observed user; engagement bands use dataset tertiles.", "dataset_id": dataset_id, "version": version}]
    if session_column:
        evidence.append({"id": "C-002", "computation": f"Counted distinct non-null `{session_column}` values per user; returning users have more than one observed session in this dataset.", "dataset_id": dataset_id, "version": version})
    return {"dataset_id": dataset_id, "version": version, "supported": True, "user_column": user_column, "session_column": session_column, "user_count": count, "returning_user_summary": returning if session_column else {"supported": False, "reason": "A compatible session identifier is required."}, "engagement_segments": segment_counts, "engagement_definition": "Observed user event counts divided into lower, moderate, and higher engagement bands using one-third and two-third dataset quantiles; descriptive only.", "top_users": top_users, "evidence": evidence}


def analyze_cohorts(path: Path, dataset_id: str, version: int) -> dict[str, Any]:
    frame = _scan_parquet(path)
    roles = map_roles(frame.collect_schema().names())
    user_column, time_column = roles["user_id"], roles["event_time"]
    if not user_column or not time_column:
        missing = "user/customer identifier" if not user_column else "timestamp"
        return {"dataset_id": dataset_id, "version": version, "supported": False, "reason": f"A compatible {missing} column is required for activity cohorts.", "cohorts": [], "evidence": []}
    time_dtype = frame.collect_schema()[time_column]
    date_expr = _datetime_expr(time_column, time_dtype)
    observed = frame.select([pl.col(user_column), date_expr.alias("__cohort_time")]).filter(pl.col(user_column).is_not_null() & pl.col("__cohort_time").is_not_null()).with_columns(pl.col("__cohort_time").dt.truncate("1mo").alias("activity_month"))
    first = observed.group_by(user_column).agg(pl.col("activity_month").min().alias("cohort_month"))
    cohort_rows = observed.join(first, on=user_column, how="inner").group_by(["cohort_month", "activity_month"]).agg(pl.col(user_column).n_unique().alias("active_users")).sort(["cohort_month", "activity_month"]).collect(engine="streaming").to_dicts()
    sizes = {row["cohort_month"]: row["active_users"] for row in cohort_rows if row["cohort_month"] == row["activity_month"]}
    for row in cohort_rows:
        cohort_size = sizes.get(row["cohort_month"], 0)
        row["cohort_month"] = row["cohort_month"].strftime("%Y-%m")
        row["activity_month"] = row["activity_month"].strftime("%Y-%m")
        row["cohort_size"] = cohort_size
        row["retention_rate"] = row["active_users"] / cohort_size if cohort_size else None
    return {"dataset_id": dataset_id, "version": version, "supported": True, "definition": "Activity cohort = month of each user's first observed event; retention = distinct users active in a later month divided by the cohort's distinct users in its first month.", "cohorts": cohort_rows, "evidence": [{"id": "H-001", "computation": f"Grouped distinct users from `{user_column}` by first observed calendar month in `{time_column}` and each active calendar month.", "dataset_id": dataset_id, "version": version}]}


def analyze_correlations(path: Path, dataset_id: str, version: int, max_columns: int = 12) -> dict[str, Any]:
    frame = _scan_parquet(path)
    schema = frame.collect_schema()
    detected_roles = map_roles(schema.names())
    role_ids = {detected_roles[role] for role in ("product_id", "user_id", "session_id") if detected_roles[role]}
    numeric = [name for name, dtype in schema.items() if dtype.is_numeric() and name not in role_ids and not name.casefold().endswith("_id")][:max_columns]
    if len(numeric) < 2:
        return {"dataset_id": dataset_id, "version": version, "supported": False, "reason": "At least two non-identifier numeric columns are required for correlation analysis.", "columns": numeric, "correlations": [], "evidence": []}
    expressions = [pl.corr(pl.col(left).cast(pl.Float64, strict=False), pl.col(right).cast(pl.Float64, strict=False), method="pearson").alias(f"{i}:{j}") for i, left in enumerate(numeric) for j, right in enumerate(numeric) if j > i]
    values = frame.select(expressions).collect(engine="streaming").row(0, named=True)
    correlations = [{"left": numeric[int(key.split(":")[0])], "right": numeric[int(key.split(":")[1])], "pearson_r": value} for key, value in values.items() if value is not None]
    return {"dataset_id": dataset_id, "version": version, "supported": True, "columns": numeric, "correlations": correlations, "definition": "Pairwise Pearson correlation across available numeric, non-identifier columns using rows with valid values for each pair. Correlation is descriptive and does not imply causation.", "evidence": [{"id": "N-001", "computation": "Calculated pairwise Pearson correlations for the selected numeric non-identifier columns.", "dataset_id": dataset_id, "version": version}]}
