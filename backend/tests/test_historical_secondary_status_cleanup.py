import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_secondary_status_cleanup.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_secondary_status_cleanup import (  # noqa: E402
    cleanup_historical_secondary_statuses,
    reopen_mislocked_historical_secondary_statuses,
)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_cleanup_moves_only_pre_0727_historical_waiting_rows() -> None:
    with SessionLocal() as db:
        submitted = add_claim(db, "开发0512期", "SUB-SUBMITTED", submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc))
        submitted_without_period = add_claim(db, "", "SUB-SUBMITTED-NO-PERIOD", submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc))
        arrived = add_claim(db, "开发0512期", "SUB-ARRIVED", arrival_at=datetime(2026, 5, 20, 9, tzinfo=timezone.utc))
        current = add_claim(db, "PLM到货20260727-0803", "SUB-CURRENT", arrival_at=datetime(2026, 7, 28, 9, tzinfo=timezone.utc))
        untouched = add_claim(db, "开发0512期", "SUB-NO-EVIDENCE")
        db.commit()

        dry_run = cleanup_historical_secondary_statuses(db, apply=False)
        assert dry_run == {
            "submitted_waiting_to_history": 2,
            "historic_arrived_waiting_to_history": 1,
            "unchanged_waiting_current": 1,
            "unchanged_no_evidence": 1,
        }
        assert db.get(models.SalesClaimForecast, submitted).downstream_status == "waiting_secondary_research"

        result = cleanup_historical_secondary_statuses(db, apply=True)
        assert result == dry_run

        submitted_claim = db.get(models.SalesClaimForecast, submitted)
        submitted_without_period_claim = db.get(models.SalesClaimForecast, submitted_without_period)
        arrived_claim = db.get(models.SalesClaimForecast, arrived)
        current_claim = db.get(models.SalesClaimForecast, current)
        untouched_claim = db.get(models.SalesClaimForecast, untouched)

    assert submitted_claim.downstream_status == "historical_secondary_submitted"
    assert submitted_claim.secondary_research_submitted_at == datetime(2026, 7, 31, 10)
    assert submitted_without_period_claim.downstream_status == "historical_secondary_submitted"
    assert arrived_claim.downstream_status == "historical_secondary_submitted"
    assert arrived_claim.secondary_research_submitted_at == datetime(2026, 5, 20, 9)
    assert "历史 PLM 到货反推二调已完成" in arrived_claim.note
    assert current_claim.downstream_status == "waiting_secondary_research"
    assert untouched_claim.downstream_status == "waiting_secondary_research"


def test_reopen_mislocked_historical_secondary_requires_complete_fields_or_listing() -> None:
    with SessionLocal() as db:
        reopened = add_claim(
            db,
            "开发0616期",
            "SUB-REOPEN",
            submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
            downstream_status="historical_secondary_submitted",
        )
        reopened_partial = add_claim(
            db,
            "开发0616期",
            "SUB-PARTIAL",
            submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
            downstream_status="historical_secondary_submitted",
            secondary_conclusion="已调研",
        )
        kept_with_listing = add_claim(
            db,
            "开发0616期",
            "SUB-LISTED",
            submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
            downstream_status="historical_secondary_submitted",
        )
        kept_with_complete_fields = add_claim(
            db,
            "开发0616期",
            "SUB-FIELDS",
            submitted_at=datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
            downstream_status="historical_secondary_submitted",
            secondary_conclusion="已调研",
            product_positioning="利润款",
            secondary_target_daily_sales=12,
            secondary_selling_points="卖点明确",
        )
        add_listing_for_claim(db, kept_with_listing)
        db.commit()

        dry_run = reopen_mislocked_historical_secondary_statuses(db, apply=False)
        assert dry_run["reopened"] == 2
        assert db.get(models.SalesClaimForecast, reopened).downstream_status == "historical_secondary_submitted"

        result = reopen_mislocked_historical_secondary_statuses(db, apply=True)
        assert result["reopened"] == 2

        reopened_claim = db.get(models.SalesClaimForecast, reopened)
        partial_claim = db.get(models.SalesClaimForecast, reopened_partial)
        listed_claim = db.get(models.SalesClaimForecast, kept_with_listing)
        fields_claim = db.get(models.SalesClaimForecast, kept_with_complete_fields)

    assert reopened_claim.downstream_status == "waiting_secondary_research"
    assert reopened_claim.secondary_research_submitted_at is None
    assert partial_claim.downstream_status == "waiting_secondary_research"
    assert partial_claim.secondary_conclusion == "已调研"
    assert partial_claim.secondary_research_submitted_at is None
    assert listed_claim.downstream_status == "historical_secondary_submitted"
    assert fields_claim.downstream_status == "historical_secondary_submitted"


def add_claim(
    db,
    batch: str,
    sub_sku: str,
    submitted_at: datetime | None = None,
    arrival_at: datetime | None = None,
    downstream_status: str = "waiting_secondary_research",
    secondary_conclusion: str | None = None,
    product_positioning: str | None = None,
    secondary_target_daily_sales: float | None = None,
    secondary_selling_points: str | None = None,
) -> str:
    opportunity = models.NewProductOpportunity(
        source_type="history_selection1",
        batch=batch,
        country="菲律宾",
        site="菲律宾",
        main_sku=f"MAIN-{sub_sku}",
        sub_sku=sub_sku,
        current_status="claim_submitted",
    )
    db.add(opportunity)
    db.flush()
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name="运营A",
        claim_result="claim",
        source_column="history_selection1",
        claim_source="history_selection1",
        downstream_status=downstream_status,
        arrival_detected_at=arrival_at,
        secondary_research_submitted_at=submitted_at,
        secondary_conclusion=secondary_conclusion,
        product_positioning=product_positioning,
        secondary_target_daily_sales=secondary_target_daily_sales,
        secondary_selling_points=secondary_selling_points,
    )
    db.add(claim)
    db.flush()
    if arrival_at:
      db.add(models.ArrivalRecord(
          opportunity_id=opportunity.id,
          claim_record_id=claim.id,
          salesperson_name="运营A",
          country="菲律宾",
          arrived_at=arrival_at,
      ))
    return claim.id


def add_listing_for_claim(db, claim_id: str) -> None:
    claim = db.get(models.SalesClaimForecast, claim_id)
    opportunity = db.get(models.NewProductOpportunity, claim.opportunity_id)
    listing = models.ListingRecord(
        source_group_key=f"history:{opportunity.main_sku}",
        source_claim_ids=[claim.id],
        source_type="history_listing",
        business_period=opportunity.batch,
        country=opportunity.country,
        site=opportunity.site,
        main_sku=opportunity.main_sku,
        salesperson_name=claim.salesperson_name,
        shop="Shopee-PH",
        item="123456",
        listing_strategy="history",
        status="active",
        tracking_status="active",
    )
    db.add(listing)
    db.flush()
    db.add(models.ListingSkuBinding(
        listing_record_id=listing.id,
        main_sku=opportunity.main_sku,
        sub_sku=opportunity.sub_sku,
        salesperson_name=claim.salesperson_name,
        opportunity_id=opportunity.id,
        claim_record_id=claim.id,
        binding_source="history_listing",
    ))
