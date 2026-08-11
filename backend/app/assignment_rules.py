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
    category_loads: dict[tuple[str, str], int] = defaultdict(int)
    for (_source_type, _batch, main_sku, _site), items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0][2], pair[0][3])):
        chosen, reason = _choose_profile(items, enabled_profiles, loads, recency, category_loads)
        count = len(items)
        if chosen is not None:
            loads[chosen.operator_name] += 1
            category_loads[(chosen.operator_name, _category_key(items))] += 1
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


def _choose_profile(
    items: list[Any],
    profiles: list[Any],
    loads: dict[str, int],
    recency: dict[str, float],
    category_loads: dict[tuple[str, str], int],
) -> tuple[Any | None, str]:
    site = _first_text(items, "site") or _first_text(items, "country")
    category = _first_text(items, "category_level1")
    category_level2 = _first_text(items, "category_level2")
    category_key = _category_key(items)
    site_profiles = [profile for profile in profiles if _same_site(getattr(profile, "key_site", None), site)]
    if not site_profiles:
        return None, "无站点匹配"
    ranked_profiles = [(profile, _category_rank(profile, category, category_level2)) for profile in site_profiles]
    best_rank = min((rank for _profile, rank in ranked_profiles), default=2)
    if category and best_rank < 2:
        pool = [(profile, rank) for profile, rank in ranked_profiles if rank == best_rank]
        reason = _reason(best_rank)
    else:
        pool = [(profile, 2) for profile in site_profiles]
        reason = "无类目-均衡分配"

    scored = []
    for profile, category_rank in pool:
        name = getattr(profile, "operator_name")
        scored.append(
            (
                loads[name],
                category_loads[(name, category_key)],
                -_int_attr(profile, "assignment_priority"),
                recency[name],
                _int_attr(profile, "display_order"),
                name,
                profile,
                category_rank,
            )
        )

    _load, _category_load, _priority, _recency, _order, _name, chosen, _best_category_rank = min(scored)
    return chosen, reason


def _category_rank(profile: Any, category: str | None, category_level2: str | None = None) -> int:
    if not category:
        return 2
    selection_rank = _key_categories_rank(getattr(profile, "key_categories", None), category, category_level2)
    if selection_rank < 2:
        return selection_rank
    if _same_category(getattr(profile, "key_category1", None), category):
        return 1
    if _same_category(getattr(profile, "key_category2", None), category):
        return 1
    return 2


def _key_categories_rank(selections: Any, category: str | None, category_level2: str | None) -> int:
    if not selections:
        return 2
    best_rank = 2
    for selection in selections:
        if not isinstance(selection, dict):
            continue
        level1 = selection.get("level1")
        level2 = selection.get("level2")
        if not _same_category(level1, category):
            continue
        if level2 and category_level2:
            if _same_category(level2, category_level2):
                best_rank = min(best_rank, 0)
            continue
        best_rank = min(best_rank, 1)
    return best_rank


def _reason(category_rank: int) -> str:
    if category_rank == 0:
        return "二级类目命中"
    if category_rank == 1:
        return "一级类目命中"
    return "无类目-均衡分配"


def _category_key(items: list[Any]) -> str:
    return "|".join(
        value or ""
        for value in (
            _norm_category(_first_text(items, "category_level1")),
            _norm_category(_first_text(items, "category_level2")),
        )
    )


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
