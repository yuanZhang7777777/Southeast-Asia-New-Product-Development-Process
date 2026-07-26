from __future__ import annotations

from collections import defaultdict
from typing import Any

from app import schemas
from app.site_codes import normalize_site_code


def preview_main_sku_assignment_groups(
    opportunities: list[Any],
    profiles: list[Any],
    initial_loads: dict[str, int] | None = None,
    initial_last_assigned: dict[str, Any] | None = None,
) -> list[schemas.AssignmentPreviewItem]:
    enabled_profiles = [profile for profile in profiles if getattr(profile, "enabled", True)]
    if not enabled_profiles:
        return []

    grouped: dict[tuple[str | None, str | None, str, str], list[Any]] = defaultdict(list)
    for opportunity in opportunities:
        grouped[
            (
                getattr(opportunity, "source_type", None),
                getattr(opportunity, "batch", None),
                getattr(opportunity, "main_sku"),
                _site_key(opportunity),
            )
        ].append(opportunity)

    initial_loads = initial_loads or {}
    initial_last_assigned = initial_last_assigned or {}
    loads = {getattr(profile, "operator_name"): int(initial_loads.get(getattr(profile, "operator_name"), 0)) for profile in enabled_profiles}
    recency = {
        getattr(profile, "operator_name"): _recency_value(initial_last_assigned.get(getattr(profile, "operator_name")))
        for profile in enabled_profiles
    }
    next_recency = max([value for value in recency.values() if value != float("-inf")], default=0.0) + 1.0
    output: list[schemas.AssignmentPreviewItem] = []
    for (_source_type, _batch, main_sku, _site), items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0][2], pair[0][3])):
        chosen, reason = _choose_profile(items, enabled_profiles, loads, recency)
        count = len(items)
        if chosen is not None:
            loads[chosen.operator_name] += 1
            recency[chosen.operator_name] = next_recency
            next_recency += 1.0
        output.append(
            schemas.AssignmentPreviewItem(
                main_sku=main_sku,
                sub_sku_count=count,
                suggested_assignee=chosen.operator_name if chosen else None,
                match_reason=reason,
                opportunity_ids=[item.id for item in items],
            )
        )
    return output


def _choose_profile(items: list[Any], profiles: list[Any], loads: dict[str, int], recency: dict[str, float]) -> tuple[Any | None, str]:
    site = _first_text(items, "site") or _first_text(items, "country")
    category = _first_text(items, "category_level1")
    category_level2 = _first_text(items, "category_level2")
    site_profiles = [profile for profile in profiles if _same_site(getattr(profile, "key_site", None), site)]
    if not site_profiles:
        return None, "无站点匹配"

    scored = []
    for profile in site_profiles:
        category_rank = _category_rank(profile, category, category_level2)
        category_priority = 0 if category_rank < 2 else 2
        scored.append(
            (
                loads[getattr(profile, "operator_name")],
                category_priority,
                -_int_attr(profile, "assignment_priority"),
                recency[getattr(profile, "operator_name")],
                _int_attr(profile, "display_order"),
                getattr(profile, "operator_name"),
                profile,
                category_rank,
            )
        )

    best_load, best_category_priority, _priority, _recency, _order, _name, chosen, best_category_rank = min(scored)
    site_loads = [load for load, *_rest in scored]
    reason = _reason(best_category_rank)
    if best_category_priority != 2 and len(set(site_loads)) > 1 and best_load == min(site_loads):
        reason = f"{reason}；负载更低"
    return chosen, reason


def _category_rank(profile: Any, category: str | None, category_level2: str | None = None) -> int:
    if _matches_key_categories(getattr(profile, "key_categories", None), category, category_level2):
        return 0
    if _same_category(getattr(profile, "key_category1", None), category):
        return 0
    if _same_category(getattr(profile, "key_category2", None), category):
        return 0
    return 2


def _matches_key_categories(selections: Any, category: str | None, category_level2: str | None) -> bool:
    if not selections:
        return False
    for selection in selections:
        if not isinstance(selection, dict):
            continue
        level1 = selection.get("level1")
        level2 = selection.get("level2")
        if not _same_category(level1, category):
            continue
        if level2 and category_level2:
            return _same_category(level2, category_level2)
        return True
    return False


def _reason(category_rank: int) -> str:
    parts = ["重点站点匹配"]
    if category_rank == 0:
        parts.append("重点类目匹配")
    else:
        parts.append("品类未匹配")
        parts.append("负载均衡")
    return "；".join(parts)


def _first_text(items: list[Any], field: str) -> str | None:
    for item in items:
        value = _norm(getattr(item, field, None))
        if value:
            return value
    return None


def _site_key(item: Any) -> str:
    return normalize_site_code(getattr(item, "site", None) or getattr(item, "country", None)) or ""


def _same_site(left: Any, right: Any) -> bool:
    left_text = normalize_site_code(left)
    right_text = normalize_site_code(right)
    return bool(left_text and right_text and left_text == right_text)


def _same_category(left: Any, right: Any) -> bool:
    left_text = _norm_category(left)
    right_text = _norm_category(right)
    return bool(left_text and right_text and left_text == right_text)


def _norm_category(value: Any) -> str | None:
    text = _norm(value)
    if not text:
        return None
    compact = "".join(text.split())
    if "汽" in compact and "摩" in compact:
        return "汽摩配"
    if "家居" in compact or "厨卫" in compact:
        return "家居厨卫"
    if "商" in compact and ("办" in compact or "工业" in compact):
        return "商办工业"
    if "户外" in compact or "运动" in compact:
        return "户外运动"
    return compact


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_attr(item: Any, field: str) -> int:
    try:
        return int(getattr(item, field, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _recency_value(value: Any) -> float:
    """Sortable last-assigned marker: never assigned sorts first (earliest)."""
    if value is None:
        return float("-inf")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return value.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return float("-inf")
