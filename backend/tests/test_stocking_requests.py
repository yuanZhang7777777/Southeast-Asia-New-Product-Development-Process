import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import workflow_status  # noqa: E402


client = TestClient(app)


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
        assert services.list_available_stocking_items(db) == []


def test_stocking_request_post_requires_claim_record_id() -> None:
    response = client.post(
        "/stocking/requests",
        json={"opportunity_id": "opportunity-1", "daily_sales": 1},
    )

    assert response.status_code == 422


def test_stocking_request_post_reuses_claim_draft_and_rejects_mismatched_opportunity() -> None:
    with SessionLocal() as db:
        opportunities = [
            models.NewProductOpportunity(
                source_type="manual",
                source_row=index,
                main_sku=f"MAIN-{index}",
                sub_sku=f"SUB-{index}",
            )
            for index in (1, 2)
        ]
        db.add_all(opportunities)
        db.flush()
        claim = models.SalesClaimForecast(
            opportunity_id=opportunities[0].id,
            salesperson_name="Sales A",
            claim_result="claim",
            claim_daily_sales=2,
        )
        db.add(claim)
        db.flush()
        existing = services.create_stocking_draft_for_claim(db, claim.id)
        db.commit()
        ids = (opportunities[0].id, opportunities[1].id, claim.id, existing.id)

    mismatch = client.post(
        "/stocking/requests",
        json={"opportunity_id": ids[1], "claim_record_id": ids[2], "daily_sales": 99},
    )
    valid = client.post(
        "/stocking/requests",
        json={"opportunity_id": ids[0], "claim_record_id": ids[2], "daily_sales": 99},
    )

    assert mismatch.status_code == 400
    assert valid.status_code == 200
    assert valid.json()["id"] == ids[3]
    with SessionLocal() as db:
        assert db.query(models.StockingRequest).count() == 1
