import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_stocking_export_persists_export_batch_and_rows() -> None:
    opportunity_id, claim_id = prepare_approved_claim()

    response = client.get("/stocking/available-list/export")

    assert response.status_code == 200
    with SessionLocal() as db:
        batch = db.query(models.ExportBatch).one()
        rows = db.query(models.ExportRow).all()
        opportunity_status = db.get(models.NewProductOpportunity, opportunity_id).current_status

    assert batch.file_name == "海外仓备货申请表.xlsx"
    assert batch.scope == "stocking_available"
    assert batch.row_count == 1
    assert batch.exported_by == "system"
    assert [(row.opportunity_id, row.claim_record_id, row.stocking_quantity) for row in rows] == [
        (opportunity_id, claim_id, 60)
    ]
    assert opportunity_status == "waiting_arrival"


def test_available_export_filters_by_source_sheet_without_repeating_transitioned_rows() -> None:
    first_id, first_claim_id = prepare_approved_claim(source_sheet="开发0623期", source_row=1, sub_sku="SUB-W27")
    second_id, second_claim_id = prepare_approved_claim(source_sheet="开发0630期", source_row=2, sub_sku="SUB-W28")

    response = client.get("/stocking/available-list/export?source_sheet=开发0623期")

    assert response.status_code == 200
    list_response = client.get("/stocking/available-list?source_sheet=开发0623期")
    assert list_response.status_code == 200
    assert list_response.json() == []

    repeat_response = client.get("/stocking/available-list/export?source_sheet=开发0623期")
    assert repeat_response.status_code == 200
    with SessionLocal() as db:
        exported = db.query(models.ExportRow).all()
    assert [(row.opportunity_id, row.claim_record_id) for row in exported] == [(first_id, first_claim_id)]

    other_period = client.get("/stocking/available-list?source_sheet=开发0630期")
    assert other_period.status_code == 200
    assert [(item["opportunity_id"], item["claim_record_id"]) for item in other_period.json()] == [(second_id, second_claim_id)]


def test_available_export_filters_by_import_batch_id() -> None:
    first_id, first_claim_id = prepare_approved_claim(import_batch_id="batch-0623", source_row=1, sub_sku="SUB-BATCH-1")
    prepare_approved_claim(import_batch_id="batch-0630", source_row=2, sub_sku="SUB-BATCH-2")

    response = client.get("/stocking/available-list/export?import_batch_id=batch-0623")

    assert response.status_code == 200
    with SessionLocal() as db:
        exported = db.query(models.ExportRow).all()
    assert [(row.opportunity_id, row.claim_record_id) for row in exported] == [(first_id, first_claim_id)]


def prepare_approved_claim(
    source_sheet: str = "开发0623期",
    import_batch_id: str | None = None,
    source_row: int = 1,
    sub_sku: str = "SUB-BATCH",
) -> tuple[str, str]:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            import_batch_id=import_batch_id,
            source_file="选品1.xlsx",
            source_sheet=source_sheet,
            source_row=source_row,
            batch="BATCH-BATCH",
            country="PH",
            site="PH",
            main_sku="MAIN-BATCH",
            sub_sku=sub_sku,
        )
        db.add(opportunity)
        db.flush()
        claim = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售A",
                claim_result="claim",
                claim_daily_sales=2,
            ),
        )
        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                reviewer_name="练玉君",
                review_status="approved",
            ),
        )
        claim.downstream_status = "waiting_export"
        db.commit()
        return opportunity.id, claim.id
