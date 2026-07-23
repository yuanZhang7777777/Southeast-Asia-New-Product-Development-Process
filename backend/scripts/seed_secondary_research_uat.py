from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.db import SessionLocal
from app.workflow_status import (
    CLAIM_DISABLED,
    CLAIM_LISTING_OBSERVATION,
    CLAIM_RESULT_CLAIM,
    CLAIM_WAITING_LISTING,
    CLAIM_WAITING_SECONDARY_RESEARCH,
    OPPORTUNITY_WAITING_ARRIVAL,
)

UAT_SOURCE_TYPE = "uat_secondary_research_seed"
UAT_SOURCE_FILE = "UAT-SR-20260723"
UAT_LISTING_SOURCE_TYPE = f"{UAT_SOURCE_TYPE}:{UAT_SOURCE_FILE}"
UAT_OWNER = "刘学城"
EXPECTED_COUNTS = {"opportunities": 54, "claims": 54, "listings": 6, "periods": 18}
COUNTRIES = ("TH", "VN", "PH")
CHILDREN = ("A", "B", "C")
POSITIONINGS = {
    3: ("利润款", "稳定款", "淘汰款"),
    4: ("清仓款", "利润款", "稳定款"),
    5: ("利润款", "稳定款", "引流款"),
    6: ("稳定款", "利润款", "引流款"),
}


def seed_secondary_research_uat(db) -> dict[str, int]:
    current = current_counts(db)
    if current == EXPECTED_COUNTS:
        return current
    if any(current.values()):
        raise ValueError(
            f"{UAT_SOURCE_FILE} data is incomplete: {current}; clean this exact source marker before reseeding"
        )

    now = datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc)
    source_row = 1
    for country in COUNTRIES:
        for group_number in range(1, 7):
            business_period = "UAT-SR-20260710" if group_number % 2 else "UAT-SR-20260717"
            main_sku = f"UAT-SR-{country}-{group_number:02d}"
            claims: list[models.SalesClaimForecast] = []
            for child_index, child in enumerate(CHILDREN):
                sub_sku = f"{main_sku}-{child}"
                opportunity = models.NewProductOpportunity(
                    id=models.new_id(),
                    source_type=UAT_SOURCE_TYPE,
                    source_file=UAT_SOURCE_FILE,
                    source_sheet=country,
                    source_row=source_row,
                    batch=business_period,
                    country=country,
                    site=country,
                    category_level1="家居用品",
                    keyword=f"{country} 新品测试关键词 {group_number}",
                    main_sku_name=f"{country} UAT新品 {group_number}",
                    main_sku=main_sku,
                    sub_sku_name=f"测试款式 {child}",
                    sub_sku=sub_sku,
                    product_type="海外仓新品",
                    reason="验证二次调研、纠错、筛选与观察历史",
                    current_status=OPPORTUNITY_WAITING_ARRIVAL,
                    snapshot=source_snapshot(country, group_number, child, source_row),
                )
                source_row += 1
                claim = build_claim(opportunity, UAT_OWNER, country, group_number, child_index, now)
                db.add_all([opportunity, claim])
                claims.append(claim)

            if group_number in {5, 6}:
                add_listing_history(db, claims, country, group_number, business_period, main_sku, now)

    db.flush()
    result = current_counts(db)
    if result != EXPECTED_COUNTS:
        raise RuntimeError(f"unexpected UAT seed counts: {result}")
    return result


def current_counts(db) -> dict[str, int]:
    opportunities = db.scalar(
        select(func.count()).select_from(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == UAT_SOURCE_TYPE,
            models.NewProductOpportunity.source_file == UAT_SOURCE_FILE,
        )
    ) or 0
    claims = db.scalar(
        select(func.count())
        .select_from(models.SalesClaimForecast)
        .join(models.NewProductOpportunity)
        .where(
            models.NewProductOpportunity.source_type == UAT_SOURCE_TYPE,
            models.NewProductOpportunity.source_file == UAT_SOURCE_FILE,
        )
    ) or 0
    listings = db.scalar(
        select(func.count()).select_from(models.ListingRecord).where(
            models.ListingRecord.source_type == UAT_LISTING_SOURCE_TYPE
        )
    ) or 0
    periods = db.scalar(
        select(func.count())
        .select_from(models.ItemObservationPeriod)
        .join(models.ListingRecord)
        .where(models.ListingRecord.source_type == UAT_LISTING_SOURCE_TYPE)
    ) or 0
    return {
        "opportunities": opportunities,
        "claims": claims,
        "listings": listings,
        "periods": periods,
    }


def build_claim(
    opportunity: models.NewProductOpportunity,
    owner: str,
    country: str,
    group_number: int,
    child_index: int,
    now: datetime,
) -> models.SalesClaimForecast:
    arrival_at = now - timedelta(days=country_offset(country) + group_number)
    claim = models.SalesClaimForecast(
        id=models.new_id(),
        opportunity_id=opportunity.id,
        platform="Shopee",
        group_name="集团八部",
        salesperson_name=owner,
        claim_result=CLAIM_RESULT_CLAIM,
        claim_daily_sales=8 + group_number + child_index,
        source_column="AJ",
        claim_source="uat_seed",
        first_submitted_at=arrival_at - timedelta(days=20),
        last_updated_at=arrival_at,
        note=UAT_SOURCE_FILE,
        downstream_status=CLAIM_WAITING_SECONDARY_RESEARCH,
        arrival_detected_at=arrival_at,
        secondary_evidence_images=[],
    )
    if group_number == 2:
        claim.secondary_research_at = arrival_at + timedelta(hours=2)
        if child_index < 2:
            claim.secondary_conclusion = f"{country} 部分草稿 {child_index + 1}"
        if child_index == 0:
            claim.product_positioning = "利润款"
        return claim
    if group_number == 1:
        return claim

    positioning = POSITIONINGS[group_number][child_index]
    claim.secondary_research_at = arrival_at + timedelta(hours=2)
    claim.secondary_competitor_url = f"https://example.com/uat/{country.lower()}/{group_number}/{child_index + 1}"
    claim.secondary_conclusion = f"{country} 第{group_number}组已提交调研，款式{CHILDREN[child_index]}"
    claim.product_positioning = positioning
    claim.secondary_research_submitted_at = arrival_at + timedelta(hours=3)
    if group_number in {5, 6}:
        claim.downstream_status = CLAIM_LISTING_OBSERVATION
    else:
        claim.downstream_status = CLAIM_DISABLED if positioning in {"淘汰款", "清仓款"} else CLAIM_WAITING_LISTING
    return claim


def add_listing_history(
    db,
    claims: list[models.SalesClaimForecast],
    country: str,
    group_number: int,
    business_period: str,
    main_sku: str,
    now: datetime,
) -> None:
    complete_first_round = group_number == 6
    week_count = 4 if complete_first_round else 2
    first_period_start = date(2026, 5, 21) if complete_first_round else date(2026, 6, 18)
    listing = models.ListingRecord(
        id=models.new_id(),
        source_group_key=f"{UAT_LISTING_SOURCE_TYPE}|{business_period}|{country}|{main_sku}|{UAT_OWNER}",
        source_claim_ids=[claim.id for claim in claims],
        source_type=UAT_LISTING_SOURCE_TYPE,
        business_period=business_period,
        country=country,
        site=country,
        main_sku=main_sku,
        main_sku_name=f"{country} UAT新品 {group_number}",
        salesperson_name=UAT_OWNER,
        shop=f"UAT-{country}-测试店铺-{group_number}",
        item=f"UAT-ITEM-{country}-{group_number:02d}",
        listing_strategy="UAT紧凑布局与四周观察验证",
        first_period_start=first_period_start,
        first_period_end=first_period_start + timedelta(days=6),
        status="active",
        tracking_status="active",
        initial_observation_completed_at=now - timedelta(days=1) if complete_first_round else None,
        created_by_name=UAT_OWNER,
    )
    db.add(listing)
    for week_number in range(1, week_count + 1):
        start = first_period_start + timedelta(days=(week_number - 1) * 7)
        revenue = float(600 + group_number * 100 + week_number * 75)
        db.add(
            models.ItemObservationPeriod(
                id=models.new_id(),
                listing_record_id=listing.id,
                week_number=week_number,
                period_start=start,
                period_end=start + timedelta(days=6),
                status="completed",
                order_count=5 + group_number + week_number,
                total_revenue=revenue,
                gross_profit_amount=round(revenue * (0.12 + week_number * 0.01), 2),
                product_positioning=("引流款", "利润款", "稳定款", "淘汰款")[week_number - 1],
                optimization_action=f"第{week_number}周优化记录：调整主图与关键词",
                four_week_summary="四周已完整复盘，可验证只读与纠错入口" if week_number == 4 else None,
                source_snapshot={"uat_source": UAT_SOURCE_FILE, "metric_source": "fixed_uat"},
                metrics_fetched_at=now - timedelta(days=8 - week_number),
                reviewed_at=now - timedelta(days=7 - week_number),
            )
        )


def source_snapshot(country: str, group_number: int, child: str, source_row: int) -> dict:
    return {
        "uat_source": UAT_SOURCE_FILE,
        "source_file": UAT_SOURCE_FILE,
        "source_sheet": country,
        "source_row": source_row,
        "headers_by_column": {
            "D": "类目",
            "E": "关键词",
            "Z": "市场容量",
            "AA": "竞争强度",
            "AJ": "认领单销",
        },
        "fields_by_column": {
            "D": "家居用品",
            "E": f"{country} 测试关键词 {group_number}",
            "Z": 1200 + group_number * 100,
            "AA": "中等",
            "AJ": 8 + group_number,
            "AL": "二次调研时间",
            "AM": "竞品链接",
            "AN": "调研结论",
            "AO": "商品定位",
        },
        "cells": {"B": child},
    }


def country_offset(country: str) -> int:
    return {"TH": 0, "VN": 3, "PH": 6}[country]


def ensure_development_environment(settings) -> None:
    if settings.app_env.strip().lower() != "development":
        raise RuntimeError("UAT seed is allowed only when APP_ENV=development")


def main() -> None:
    ensure_development_environment(Settings())
    with SessionLocal() as db:
        result = seed_secondary_research_uat(db)
        db.commit()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
