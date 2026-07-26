from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_status_classification import classify_historical_statuses


def market_record(
    main_sku: str,
    child_sku: str,
    salesperson: str = "销售A",
    *,
    conclusion: str | None = None,
    positioning: str | None = None,
    target_daily_sales: float | None = None,
    selling_points: str | None = None,
) -> dict:
    return {
        "main_sku": main_sku,
        "child_sku": child_sku,
        "country": "PH",
        "salesperson": salesperson,
        "secondary_conclusion": conclusion,
        "positioning": positioning,
        "target_daily_sales": target_daily_sales,
        "selling_points": selling_points,
        "source_reference": {"source_row": 1},
    }


def plm_match(child_sku: str, salesperson: str = "销售A") -> dict:
    return {
        "country": "PH",
        "child_sku": child_sku,
        "main_sku": child_sku.removesuffix("-SUB"),
        "salesperson_name": salesperson,
        "latest_storage_time": "2026-07-10 09:00:00",
        "source_row": 10,
    }


def listing(main_sku: str, item: str = "ITEM-1", source: str = "historical_listing") -> dict:
    return {
        "country": "PH",
        "main_sku": main_sku,
        "salesperson": "销售A",
        "shop": "Shopee-PH",
        "item": item,
        "source": source,
        "has_any_week_metrics": False,
        "source_reference": {"source_row": 20},
    }


def finebi(main_sku: str, item: str = "ITEM-1", shop: str = "Shopee-PH") -> dict:
    return {
        "country": "PH",
        "main_sku": main_sku,
        "shop": shop,
        "item_id": item,
        "row_count": 2,
    }


def test_classifies_the_seven_historical_next_action_states() -> None:
    market_records = [
        market_record("MAIN-WAIT", "MAIN-WAIT-SUB"),
        market_record("MAIN-SUSPICIOUS", "MAIN-SUSPICIOUS-SUB"),
        market_record("MAIN-SECONDARY", "MAIN-SECONDARY-SUB"),
        market_record(
            "MAIN-LISTING",
            "MAIN-LISTING-SUB",
            conclusion="可做",
            positioning="利润款",
            target_daily_sales=5,
            selling_points="轻便",
        ),
        market_record(
            "MAIN-DISABLED",
            "MAIN-DISABLED-SUB",
            conclusion="不做",
            positioning="淘汰款",
            target_daily_sales=1,
            selling_points="弱",
        ),
        market_record(
            "MAIN-METRICS",
            "MAIN-METRICS-SUB",
            conclusion="可做",
            positioning="引流款",
            target_daily_sales=8,
            selling_points="价格优势",
        ),
        market_record("MAIN-MISSING-SECONDARY", "MAIN-MISSING-SECONDARY-SUB"),
    ]

    report = classify_historical_statuses(
        market_records=market_records,
        plm_matches=[
            plm_match("MAIN-SECONDARY-SUB"),
            plm_match("MAIN-LISTING-SUB"),
            plm_match("MAIN-DISABLED-SUB"),
            plm_match("MAIN-METRICS-SUB"),
            plm_match("MAIN-MISSING-SECONDARY-SUB"),
        ],
        historical_listings=[
            listing("MAIN-SUSPICIOUS", "ITEM-SUS"),
            listing("MAIN-METRICS", "ITEM-MET"),
            listing("MAIN-MISSING-SECONDARY", "ITEM-MISS"),
        ],
        finebi_candidates=[finebi("MAIN-METRICS", "ITEM-MET")],
    )

    statuses = {row["main_sku"]: row["classification_status"] for row in report["records"]}
    assert statuses == {
        "MAIN-WAIT": "到货监控中",
        "MAIN-SUSPICIOUS": "未到货但疑似已刊登",
        "MAIN-SECONDARY": "已到货待补二次调研",
        "MAIN-LISTING": "已到货待刊登",
        "MAIN-DISABLED": "不进入刊登",
        "MAIN-METRICS": "已刊登待补观察数据",
        "MAIN-MISSING-SECONDARY": "已刊登但二次调研缺失",
    }
    assert report["summary"]["status_counts"]["已刊登待补观察数据"] == 1


def test_prefers_platform_listing_and_reports_conflicting_sources() -> None:
    report = classify_historical_statuses(
        market_records=[
            market_record(
                "MAIN-CONFLICT",
                "MAIN-CONFLICT-SUB",
                conclusion="可做",
                positioning="利润款",
                target_daily_sales=5,
                selling_points="轻便",
            )
        ],
        plm_matches=[plm_match("MAIN-CONFLICT-SUB", salesperson="销售B")],
        platform_listings=[listing("MAIN-CONFLICT", "ITEM-PLATFORM", source="platform")],
        historical_listings=[listing("MAIN-CONFLICT", "ITEM-OLD")],
        finebi_candidates=[finebi("MAIN-CONFLICT", "ITEM-FBI")],
    )

    row = report["records"][0]
    assert row["listing_source"] == "platform"
    assert row["item"] == "ITEM-PLATFORM"
    assert row["plm_salesperson"] == "销售B"
    assert row["owner_for_action"] == "销售B"
    assert "平台已有Item与历史来源不一致" in row["conflict_reason"]


def test_plm_owner_difference_is_not_a_hard_conflict() -> None:
    report = classify_historical_statuses(
        market_records=[market_record("MAIN-OWNER", "MAIN-OWNER-SUB", salesperson="历史销售")],
        plm_matches=[plm_match("MAIN-OWNER-SUB", salesperson="PLM销售")],
    )

    row = report["records"][0]
    assert row["historical_salesperson"] == "历史销售"
    assert row["plm_salesperson"] == "PLM销售"
    assert row["owner_for_action"] == "PLM销售"
    assert row["conflict_reason"] == ""

def test_keeps_secondary_fields_for_historical_archive() -> None:
    report = classify_historical_statuses(
        market_records=[
            market_record(
                "MAIN-ARCHIVE",
                "MAIN-ARCHIVE-SUB",
                conclusion="可做",
                positioning="引流款",
                target_daily_sales=6,
                selling_points="轻便耐用",
            )
        ],
        plm_matches=[],
        historical_listings=[],
        finebi_candidates=[],
    )

    row = report["records"][0]
    assert row["secondary_conclusion"] == "可做"
    assert row["positioning"] == "引流款"
    assert row["target_daily_sales"] == 6
    assert row["selling_points"] == "轻便耐用"

def test_finebi_multiple_items_are_candidates_not_conflicts() -> None:
    report = classify_historical_statuses(
        market_records=[market_record("MAIN-MULTI", "MAIN-MULTI-SUB")],
        plm_matches=[],
        historical_listings=[],
        finebi_candidates=[
            finebi("MAIN-MULTI", "ITEM-1", shop="Shopee-1PH"),
            finebi("MAIN-MULTI", "ITEM-2", shop="Shopee-2PH"),
        ],
    )

    row = report["records"][0]
    assert row["classification_status"] == "未到货但疑似已刊登"
    assert row["listing_evidence_status"] == "multi_item_candidates"
    assert row["conflict_reason"] == ""
    assert [candidate["item_id"] for candidate in row["multi_item_candidates"]] == ["ITEM-1", "ITEM-2"]


def test_historical_listing_without_finebi_match_is_missing_evidence_not_conflict() -> None:
    report = classify_historical_statuses(
        market_records=[market_record("MAIN-OLD", "MAIN-OLD-SUB")],
        plm_matches=[],
        historical_listings=[listing("MAIN-OLD", "ITEM-OLD")],
        finebi_candidates=[],
    )

    row = report["records"][0]
    assert row["listing_source"] == "historical_listing"
    assert row["listing_evidence_status"] == "missing_finebi_evidence"
    assert row["conflict_reason"] == ""


def test_same_shop_item_owned_by_multiple_main_skus_is_shared_binding_not_conflict() -> None:
    report = classify_historical_statuses(
        market_records=[market_record("MAIN-A", "MAIN-A-SUB")],
        plm_matches=[],
        historical_listings=[],
        finebi_candidates=[
            finebi("MAIN-A", "ITEM-1", shop="Shopee-1PH"),
            finebi("MAIN-B", "ITEM-1", shop="Shopee-1PH"),
        ],
    )

    row = report["records"][0]
    assert row["listing_evidence_status"] == "shared_item_binding"
    assert row["conflict_reason"] == ""
    assert row["metric_dimension"] == "item_summary"
    assert row["metric_owner_main_sku"] == "MAIN-A"
    assert row["metrics_are_item_summary"] is True
    assert row["shared_item_owners"] == [
        {
            "country": "PH",
            "main_sku": "MAIN-A",
            "shop": "Shopee-1PH",
            "item_id": "ITEM-1",
            "first_period": None,
            "last_period": None,
            "row_count": 2,
        },
        {
            "country": "PH",
            "main_sku": "MAIN-B",
            "shop": "Shopee-1PH",
            "item_id": "ITEM-1",
            "first_period": None,
            "last_period": None,
            "row_count": 2,
        },
    ]

