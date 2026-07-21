import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app import workflow_status  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_stocking_calculations_use_ceil_and_exact_totals() -> None:
    assert services.stocking_quantity(2) == 60
    assert services.stocking_quantity(2.01) == 61

    amount, volume = services.stocking_totals(12.5, 0.002, 61)

    assert amount == 762.5
    assert volume == 0.122


def test_stocking_draft_is_unique_per_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="period-1",
            source_row=2,
            country="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        db.add(opportunity)
        db.flush()
        claims = [
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name=name,
                claim_result="claim",
                claim_daily_sales=daily_sales,
                source_column="platform",
            )
            for name, daily_sales in (("Sales A", 2), ("Sales B", 2.01))
        ]
        db.add_all(claims)
        db.flush()

        first = services.create_stocking_draft_for_claim(db, claims[0].id, "Manager A")
        second = services.create_stocking_draft_for_claim(db, claims[1].id, "Manager A")
        repeated = services.create_stocking_draft_for_claim(db, claims[0].id, "Manager A")
        db.commit()

        assert repeated.id == first.id
        assert first.id != second.id
        assert [first.claim_record_id, second.claim_record_id] == [claims[0].id, claims[1].id]
        assert [first.quantity, second.quantity] == [60, 61]
        assert first.application_date == datetime.now(services.EXCEL_TIMEZONE).date()
        assert db.query(models.StockingRequest).count() == 2


def test_review_approval_creates_one_draft_for_each_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_file="selection2.xlsx",
            source_sheet="period-2",
            source_row=2,
            current_status="claim_submitted",
            country="TH",
            main_sku="MAIN-2",
            sub_sku="SUB-2",
        )
        db.add(opportunity)
        db.flush()
        claims = [
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name=name,
                claim_result="claim",
                claim_daily_sales=daily_sales,
                source_column="platform",
            )
            for name, daily_sales in (("Sales A", 1), ("Sales B", 1.5))
        ]
        db.add_all(claims)
        db.flush()

        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                reviewer_name="Manager A",
                review_status="approved",
            ),
        )
        db.commit()

        requests = db.query(models.StockingRequest).order_by(models.StockingRequest.quantity).all()
        assert {request.claim_record_id for request in requests} == {claim.id for claim in claims}
        assert [request.quantity for request in requests] == [30, 45]
        assert {claim.downstream_status for claim in claims} == {workflow_status.CLAIM_WAITING_STOCKING_REQUEST}