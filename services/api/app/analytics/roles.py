import re
from collections.abc import Iterable

ROLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "event_time": ("event_time", "timestamp", "event_timestamp", "datetime", "created_at", "date"),
    "event_type": ("event_type", "event", "action", "activity", "event_name"),
    "product_id": ("product_id", "item_id", "sku", "product", "item"),
    "category": ("category_code", "category", "category_name", "category_id", "product_category"),
    "brand": ("brand", "brand_name", "manufacturer"),
    "price": ("price", "unit_price", "item_price", "amount", "value"),
    "user_id": ("user_id", "customer_id", "visitor_id", "account_id"),
    "session_id": ("user_session", "session_id", "session", "visit_id"),
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def map_roles(columns: Iterable[str]) -> dict[str, str | None]:
    actual = list(columns)
    normalized = {_normalize(name): name for name in actual}
    result: dict[str, str | None] = {}
    for role, aliases in ROLE_SYNONYMS.items():
        result[role] = next((normalized[_normalize(alias)] for alias in aliases if _normalize(alias) in normalized), None)
    return result
