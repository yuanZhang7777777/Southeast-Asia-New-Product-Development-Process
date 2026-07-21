import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from scripts import seed_demo_statuses  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_demo_seed_creates_exportable_ready_for_stocking_rows() -> None:
    seed_demo_statuses.main()

    with SessionLocal() as db:
        requests = (
            db.query(models.StockingRequest)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.StockingRequest.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku.in_(["DEMO-READY", "DEMO-MIXED"]))
            .all()
        )
        for request in requests:
            request.status = "submitted"
            db.get(models.SalesClaimForecast, request.claim_record_id).downstream_status = "waiting_export"
        db.flush()
        rows = services.list_available_stocking_items(db)

    assert {(row.main_sku, row.sub_sku, row.salesperson_name, row.quantity) for row in rows} >= {
        ("DEMO-READY", "DEMO-READY-A", "李干", 45),
        ("DEMO-MIXED", "DEMO-MIXED-A", "陈丽妹", 30),
    }


def test_demo_seed_creates_assignment_preview_data() -> None:
    seed_demo_statuses.main()

    with SessionLocal() as db:
        pending_main_skus = {
            row.main_sku
            for row in db.query(models.NewProductOpportunity)
            .filter(
                models.NewProductOpportunity.source_type == seed_demo_statuses.DEMO_SOURCE_TYPE,
                models.NewProductOpportunity.current_status == "pending_assignment",
            )
            .all()
        }

    assert pending_main_skus >= {
        "DEMO-PENDING",
        "DEMO-PENDING-PH-HOME",
        "DEMO-PENDING-PH-AUTO",
        "DEMO-PENDING-VN-OFFICE",
        "DEMO-PENDING-FALLBACK",
    }


def test_demo_seed_reproducibly_covers_stocking_request_branches() -> None:
    seed_demo_statuses.main()
    seed_demo_statuses.main()

    with SessionLocal() as db:
        claims = (
            db.query(models.SalesClaimForecast)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku == "DEMO-SELF-STOCKING")
            .all()
        )
        statuses = {
            db.get(models.NewProductOpportunity, claim.opportunity_id).sub_sku: claim.downstream_status
            for claim in claims
        }
        requests = {
            request.sub_sku: request
            for request in db.query(models.StockingRequest)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.StockingRequest.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku == "DEMO-SELF-STOCKING")
            .all()
        }
        export_rows = services.list_available_stocking_items(db)

    assert statuses == {
        "DEMO-SELF-DRAFT": "waiting_stocking_request",
        "DEMO-SELF-SUBMITTED": "waiting_export",
        "DEMO-SELF-LIST": "waiting_listing",
        "DEMO-SELF-PAUSED": "stocking_paused",
    }
    assert set(requests) == {"DEMO-SELF-DRAFT", "DEMO-SELF-SUBMITTED"}
    assert requests["DEMO-SELF-DRAFT"].status == "draft"
    assert requests["DEMO-SELF-SUBMITTED"].status == "submitted"
    assert {
        (row.main_sku, row.sub_sku, row.quantity, row.amount, row.volume)
        for row in export_rows
    } >= {("DEMO-SELF-STOCKING", "DEMO-SELF-SUBMITTED", 61, 762.5, 0.122)}
