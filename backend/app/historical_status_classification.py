from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.historical_monitoring_sources import item_text, normalize_country, normalize_sku, text_value

ACTIVE_POSITIONS = {"引流款", "利润款", "稳定款"}
DISABLED_POSITIONS = {"淘汰款", "清仓款"}


def classify_historical_statuses(
    *,
    market_records: list[dict[str, Any]],
    plm_matches: list[dict[str, Any]] | None = None,
    historical_listings: list[dict[str, Any]] | None = None,
    finebi_candidates: list[dict[str, Any]] | None = None,
    platform_listings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plm_by_child = _index_plm(plm_matches or [])
    platform_by_main = _index_listings(platform_listings or [])
    historical_by_main = _index_listings(historical_listings or [])
    finebi_by_main, finebi_exact, finebi_shared_shop_item_owners = _index_finebi(finebi_candidates or [])

    rows = []
    for record in market_records:
        row = _classify_record(record, plm_by_child, platform_by_main, historical_by_main, finebi_by_main, finebi_exact, finebi_shared_shop_item_owners)
        rows.append(row)
    status_counts = Counter(row["classification_status"] for row in rows)
    return {
        "summary": {
            "record_count": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
            "conflict_count": sum(1 for row in rows if row["conflict_reason"]),
            "finebi_fillable_count": sum(1 for row in rows if row["finebi_fillable"]),
        },
        "records": rows,
    }


def _classify_record(
    record: dict[str, Any],
    plm_by_child: dict[tuple[str | None, str | None], list[dict[str, Any]]],
    platform_by_main: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
    historical_by_main: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
    finebi_by_main: dict[tuple[str | None, str | None], list[dict[str, Any]]],
    finebi_exact: set[tuple[str | None, str | None, str | None, str | None]],
    finebi_shared_shop_item_owners: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
) -> dict[str, Any]:
    country = normalize_country(record.get("country"))
    main_sku = normalize_sku(record.get("main_sku"))
    child_sku = normalize_sku(record.get("child_sku"))
    historical_salesperson = text_value(record.get("salesperson"))
    plm_rows = plm_by_child.get((country, child_sku), [])
    plm = plm_rows[0] if plm_rows else None
    plm_salespeople = {text_value(row.get("salesperson_name") or row.get("salesperson")) for row in plm_rows}
    plm_salespeople.discard(None)
    plm_salesperson = text_value(plm.get("salesperson_name") or plm.get("salesperson")) if plm else None
    owner_for_action = plm_salesperson or historical_salesperson
    listing = _choose_listing(country, main_sku, historical_salesperson, platform_by_main, historical_by_main, finebi_by_main)
    listing_evidence_status = _listing_evidence_status(listing, finebi_exact, finebi_shared_shop_item_owners, country, main_sku)
    shared_item_owners = _shared_item_owners(listing, finebi_shared_shop_item_owners)
    conflicts = _conflicts(record, plm_salespeople, listing, listing_evidence_status)
    finebi_fillable = _finebi_fillable(listing, finebi_exact)
    has_listing_item = listing["has_listing_item"]
    metric_dimension = "item_summary" if has_listing_item else None
    metric_owner_main_sku = _metric_owner_main_sku(listing, main_sku, shared_item_owners) if has_listing_item else None
    secondary_complete = _secondary_complete(record)
    status = _status(bool(plm), has_listing_item, secondary_complete, text_value(record.get("positioning")))
    return {
        "main_sku": main_sku,
        "child_sku": child_sku,
        "country": country,
        "historical_salesperson": historical_salesperson,
        "plm_salesperson": plm_salesperson,
        "owner_for_action": owner_for_action,
        "arrival_time": text_value(plm.get("latest_storage_time") or plm.get("arrived_at")) if plm else None,
        "has_secondary_research": _has_secondary_research(record),
        "secondary_research_complete": secondary_complete,
        "has_listing_item": has_listing_item,
        "listing_source": listing["source"],
        "listing_evidence_status": listing_evidence_status,
        "shop": listing["shop"],
        "item": listing["item"],
        "finebi_fillable": finebi_fillable,
        "multi_item_candidates": _listing_candidates(listing["finebi"]),
        "shared_item_owners": shared_item_owners,
        "metric_dimension": metric_dimension,
        "metric_owner_main_sku": metric_owner_main_sku,
        "metrics_are_item_summary": metric_dimension == "item_summary",
        "classification_status": status,
        "suggested_action": _suggested_action(status),
        "conflict_reason": "；".join(conflicts),
        "product_bucket": text_value(record.get("product_bucket")),
        "product_name": text_value(record.get("product_name")),
        "category_level1": text_value(record.get("category_level1")),
        "category_level2": text_value(record.get("category_level2")),
        "keyword": text_value(record.get("keyword")),
        "product_type": text_value(record.get("product_type")),
        "sales_note": text_value(record.get("sales_note")),
        "reference_daily_sales": record.get("reference_daily_sales"),
        "reference_price": record.get("reference_price"),
        "claimed_daily_sales": record.get("claimed_daily_sales"),
        "competitors": record.get("competitors") or [],
        "secondary_research_at": text_value(record.get("secondary_research_at")),
        "secondary_competitor_url": text_value(record.get("secondary_competitor_url")),
        "secondary_conclusion": text_value(record.get("secondary_conclusion")),
        "positioning": text_value(record.get("positioning")),
        "target_daily_sales": record.get("target_daily_sales"),
        "selling_points": text_value(record.get("selling_points")),
        "arrival_note": text_value(record.get("arrival_note")),
        "source_reference": record.get("source_reference"),
    }


def _status(arrived: bool, has_listing_item: bool, secondary_complete: bool, positioning: str | None) -> str:
    if not arrived:
        return "未到货但疑似已刊登" if has_listing_item else "到货监控中"
    if has_listing_item and not secondary_complete:
        return "已刊登但二次调研缺失"
    if not secondary_complete:
        return "已到货待补二次调研"
    if positioning in DISABLED_POSITIONS:
        return "不进入刊登"
    if has_listing_item:
        return "已刊登待补观察数据"
    return "已到货待刊登"


def _suggested_action(status: str) -> str:
    return {
        "到货监控中": "继续等PLM到货，不要求运营补二次调研",
        "未到货但疑似已刊登": "人工核对PLM到货与Item来源",
        "已到货待补二次调研": "要求运营补二次调研",
        "已到货待刊登": "进入刊登任务",
        "不进入刊登": "保留档案，不生成刊登任务",
        "已刊登待补观察数据": "用FineBI补四周观察指标",
        "已刊登但二次调研缺失": "不回退刊登，补二次调研并继续补观察数据",
    }[status]


def _secondary_complete(record: dict[str, Any]) -> bool:
    positioning = text_value(record.get("positioning"))
    target = record.get("target_daily_sales")
    try:
        target_ok = target is not None and float(target) > 0
    except (TypeError, ValueError):
        target_ok = False
    return bool(
        text_value(record.get("secondary_conclusion"))
        and positioning in (ACTIVE_POSITIONS | DISABLED_POSITIONS)
        and target_ok
        and text_value(record.get("selling_points"))
    )


def _has_secondary_research(record: dict[str, Any]) -> bool:
    return any(
        text_value(record.get(field))
        for field in ("secondary_research_at", "secondary_competitor_url", "secondary_conclusion", "positioning", "selling_points")
    ) or record.get("target_daily_sales") is not None


def _choose_listing(
    country: str | None,
    main_sku: str | None,
    salesperson: str | None,
    platform_by_main: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
    historical_by_main: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
    finebi_by_main: dict[tuple[str | None, str | None], list[dict[str, Any]]],
) -> dict[str, Any]:
    platform = platform_by_main.get((country, main_sku, salesperson), []) + platform_by_main.get((country, main_sku, None), [])
    historical = historical_by_main.get((country, main_sku, salesperson), []) + historical_by_main.get((country, main_sku, None), [])
    finebi = finebi_by_main.get((country, main_sku), [])
    selected: dict[str, Any] | None = None
    source = None
    if platform:
        selected, source = platform[0], "platform"
    elif len(finebi) == 1:
        selected, source = finebi[0], "finebi"
    elif historical:
        selected, source = historical[0], "historical_listing"
    return {
        "has_listing_item": bool(platform or historical or finebi),
        "source": source,
        "shop": text_value(selected.get("shop")) if selected else None,
        "item": item_text(selected.get("item") or selected.get("item_id")) if selected else None,
        "platform": platform,
        "historical": historical,
        "finebi": finebi,
    }


def _conflicts(record: dict[str, Any], plm_salespeople: set[str | None], listing: dict[str, Any], listing_evidence_status: str) -> list[str]:
    conflicts = []
    items_by_source = {
        source: {item_text(row.get("item") or row.get("item_id")) for row in rows if item_text(row.get("item") or row.get("item_id"))}
        for source, rows in (
            ("platform", listing["platform"]),
            ("finebi", listing["finebi"]),
            ("historical_listing", listing["historical"]),
        )
    }
    all_items = set().union(*items_by_source.values()) if items_by_source else set()
    if listing["platform"] and len(all_items) > 1:
        conflicts.append("平台已有Item与历史来源不一致")
    return conflicts



def _listing_evidence_status(
    listing: dict[str, Any],
    finebi_exact: set[tuple[str | None, str | None, str | None, str | None]],
    finebi_shared_shop_item_owners: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
    country: str | None,
    main_sku: str | None,
) -> str:
    if not listing["has_listing_item"]:
        return "none"
    candidate_keys = {
        (normalize_country(row.get("country")), text_value(row.get("shop")), item_text(row.get("item_id") or row.get("item")))
        for row in listing["finebi"] + listing["platform"] + listing["historical"]
    }
    if candidate_keys & finebi_shared_shop_item_owners.keys():
        return "shared_item_binding"
    if listing["platform"]:
        return "confirmed_item"
    historical_exact = any(
        (country, main_sku, text_value(row.get("shop")), item_text(row.get("item") or row.get("item_id"))) in finebi_exact
        for row in listing["historical"]
    )
    if historical_exact:
        return "confirmed_item"
    if listing["historical"]:
        return "missing_finebi_evidence"
    if len(listing["finebi"]) > 1:
        return "multi_item_candidates"
    if listing["finebi"]:
        return "confirmed_item"
    return "missing_finebi_evidence"


def _listing_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "country": normalize_country(row.get("country")),
            "main_sku": normalize_sku(row.get("main_sku")),
            "shop": text_value(row.get("shop")),
            "item_id": item_text(row.get("item_id") or row.get("item")),
            "first_period": text_value(row.get("first_period")),
            "last_period": text_value(row.get("last_period")),
            "row_count": row.get("row_count"),
        }
        for row in rows
    ]



def _metric_owner_main_sku(listing: dict[str, Any], main_sku: str | None, shared_item_owners: list[dict[str, Any]]) -> str | None:
    for source in ("platform", "historical"):
        if listing[source]:
            return normalize_sku(listing[source][0].get("main_sku")) or main_sku
    if shared_item_owners:
        return normalize_sku(shared_item_owners[0].get("main_sku")) or main_sku
    if listing["finebi"]:
        return normalize_sku(listing["finebi"][0].get("main_sku")) or main_sku
    return main_sku


def _shared_item_owners(
    listing: dict[str, Any],
    finebi_shared_shop_item_owners: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    candidate_keys = {
        (normalize_country(row.get("country")), text_value(row.get("shop")), item_text(row.get("item_id") or row.get("item")))
        for row in listing["finebi"] + listing["platform"] + listing["historical"]
    }
    owners = {
        (owner.get("country"), owner.get("main_sku"), owner.get("shop"), owner.get("item_id")): owner
        for key in candidate_keys & finebi_shared_shop_item_owners.keys()
        for owner in finebi_shared_shop_item_owners[key]
    }
    return sorted(
        owners.values(),
        key=lambda owner: (
            owner.get("country") or "",
            owner.get("main_sku") or "",
            owner.get("shop") or "",
            owner.get("item_id") or "",
        ),
    )

def _finebi_fillable(listing: dict[str, Any], finebi_exact: set[tuple[str | None, str | None, str | None, str | None]]) -> bool:
    if listing["source"] == "finebi":
        return True
    selected = (listing["shop"], listing["item"])
    if not all(selected):
        return False
    for row in listing["platform"] + listing["historical"]:
        key = (
            normalize_country(row.get("country")),
            normalize_sku(row.get("main_sku")),
            text_value(row.get("shop")),
            item_text(row.get("item")),
        )
        if key in finebi_exact:
            return True
    return False


def _index_plm(rows: list[dict[str, Any]]) -> dict[tuple[str | None, str | None], list[dict[str, Any]]]:
    result: dict[tuple[str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[(normalize_country(row.get("country")), normalize_sku(row.get("child_sku") or row.get("sub_sku")))].append(row)
    for values in result.values():
        values.sort(key=lambda item: text_value(item.get("latest_storage_time") or item.get("date")) or "", reverse=True)
    return result


def _index_listings(rows: list[dict[str, Any]]) -> dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]]:
    result: dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not item_text(row.get("item")):
            continue
        result[(normalize_country(row.get("country")), normalize_sku(row.get("main_sku")), text_value(row.get("salesperson")))].append(row)
    return result


def _index_finebi(rows: list[dict[str, Any]]) -> tuple[
    dict[tuple[str | None, str | None], list[dict[str, Any]]],
    set[tuple[str | None, str | None, str | None, str | None]],
    dict[tuple[str | None, str | None, str | None], list[dict[str, Any]]],
]:
    by_main: dict[tuple[str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    exact = set()
    owners_by_shop_item: dict[tuple[str | None, str | None, str | None], dict[str | None, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (normalize_country(row.get("country")), normalize_sku(row.get("main_sku")))
        by_main[key].append(row)
        shop = text_value(row.get("shop"))
        item = item_text(row.get("item_id") or row.get("item"))
        exact.add((key[0], key[1], shop, item))
        owners_by_shop_item[(key[0], shop, item)][key[1]] = {
            "country": key[0],
            "main_sku": key[1],
            "shop": shop,
            "item_id": item,
            "first_period": text_value(row.get("first_period")),
            "last_period": text_value(row.get("last_period")),
            "row_count": row.get("row_count"),
        }
    shared_shop_item_owners = {
        key: [owners[main_sku] for main_sku in sorted(owners, key=lambda value: value or "")]
        for key, owners in owners_by_shop_item.items()
        if all(key) and len(owners) > 1
    }
    return by_main, exact, shared_shop_item_owners


def write_markdown_summary(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 历史到货 / 二次调研 / 刊登状态归类报告",
        "",
        "## 汇总",
        "",
        f"- 归类记录数：{report['summary']['record_count']}",
        f"- 冲突记录数：{report['summary']['conflict_count']}",
        f"- FineBI 可补观察指标：{report['summary']['finebi_fillable_count']}",
        "",
        "| 状态 | 数量 |",
        "|---|---:|",
    ]
    for status, count in report["summary"]["status_counts"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## 样例", "", "| 主SKU | 子SKU | 负责人 | 状态 | 建议动作 | 冲突 |", "|---|---|---|---|---|---|"])
    for row in report["records"][:50]:
        lines.append(
            f"| {row['main_sku'] or ''} | {row['child_sku'] or ''} | {row['owner_for_action'] or ''} | "
            f"{row['classification_status']} | {row['suggested_action']} | {row['conflict_reason']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify historical arrival, secondary research and listing status.")
    parser.add_argument("--historical-audit", required=True, type=Path)
    parser.add_argument("--plm-matches", type=Path)
    parser.add_argument("--finebi-candidates", type=Path)
    parser.add_argument("--platform-listings", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()

    audit = json.loads(args.historical_audit.read_text(encoding="utf-8"))
    plm = json.loads(args.plm_matches.read_text(encoding="utf-8")).get("matches", []) if args.plm_matches else []
    finebi = json.loads(args.finebi_candidates.read_text(encoding="utf-8")).get("candidates", []) if args.finebi_candidates else []
    platform = json.loads(args.platform_listings.read_text(encoding="utf-8")).get("records", []) if args.platform_listings else []
    report = classify_historical_statuses(
        market_records=audit["market_monitor"]["records"],
        plm_matches=plm,
        historical_listings=audit["listing_monitor"]["records"],
        finebi_candidates=finebi,
        platform_listings=platform,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    if args.output_md:
        write_markdown_summary(report, args.output_md)


if __name__ == "__main__":
    main()
