from __future__ import annotations

from collections import defaultdict
from typing import Any

from app import schemas
from app.site_codes import normalize_site_code


def preview_main_sku_assignment_groups(opportunities: list[Any], profiles: list[Any]) -> list[schemas.AssignmentPreviewItem]:
    enabled_profiles = [profile for profile in profiles if getattr(profile, "enabled", True)]
    if not enabled_profiles:
        return []

    grouped: dict[tuple[str | None, str | None, str], list[Any]] = defaultdict(list)
    for opportunity in opportunities:
        grouped[
            (
                getattr(opportunity, "source_type", None),
                getattr(opportunity, "batch", None),
                getattr(opportunity, "main_sku"),
            )
        ].append(opportunity)

    loads = {getattr(profile, "operator_name"): 0 for profile in enabled_profiles}
    output: list[schemas.AssignmentPreviewItem] = []
    for (_source_type, _batch, main_sku), items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0][2])):
        chosen, reason = _choose_profile(items, enabled_profiles, loads)
        count = len(items)
        if chosen is not None:
            loads[chosen.operator_name] += count
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


def _choose_profile(items: list[Any], profiles: list[Any], loads: dict[str, int]) -> tuple[Any | None, str]:
    site = _first_text(items, "site") or _first_text(items, "country")
    category = _first_text(items, "category_level1")
    site_profiles = [profile for profile in profiles if _same_site(getattr(profile, "key_site", None), site)]
    if not site_profiles:
        return None, "无站点匹配"

    scored = []
    for profile in site_profiles:
        category_rank = _category_rank(profile, category)
        priority = (category_rank,)
        scored.append((priority, loads[getattr(profile, "operator_name")], getattr(profile, "operator_name"), profile))

    best_priority, best_load, _name, chosen = min(scored)
    same_priority_loads = [load for priority, load, _profile_name, _profile in scored if priority == best_priority]
    reason = _reason(best_priority[0])
    if best_priority[0] != 2 and len(set(same_priority_loads)) > 1 and best_load == min(same_priority_loads):
        reason = f"{reason}；负载更低"
    return chosen, reason


def _category_rank(profile: Any, category: str | None) -> int:
    if _same_category(getattr(profile, "key_category1", None), category):
        return 0
    if _same_category(getattr(profile, "key_category2", None), category):
        return 1
    return 2


def _reason(category_rank: int) -> str:
    parts = ["重点站点匹配"]
    if category_rank == 0:
        parts.append("重点品类1匹配")
    elif category_rank == 1:
        parts.append("重点品类2匹配")
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
