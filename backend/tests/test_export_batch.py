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

    response = export_available()

    assert response.status_code == 200
    with SessionLocal() as db:
        batch = db.query(models.ExportBatch).one()
        rows = db.query(models.ExportRow).all()
        opportunity_status = db.get(models.NewProductOpportunity, opportunity_id).current_status

    assert batch.file_name == "海外仓备货申请表.xlsx"
    assert batch.scope == "stocking_available"
    assert batch.row_count == 1
    assert batch.exported_by == "主管A"
    assert [(row.opportunity_id, row.claim_record_id, row.stocking_quantity) for row in rows] == [
        (opportunity_id, claim_id, 60)
    ]
    assert opportunity_status == "ready_for_stocking"


def test_record_export_batch_does_not_advance_unsubmitted_stocking_draft() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="manual",
            main_sku="MAIN-DRAFT",
            sub_sku="SUB-DRAFT",
            current_status="ready_for_stocking",
        )
        db.add(opportunity)
        db.flush()
        claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="Sales A",
            claim_result="claim",
            claim_daily_sales=1,
            source_column="platform",
            downstream_status="waiting_stocking_request",
        )
        db.add(claim)
        db.flush()
        request = models.StockingRequest(
            opportunity_id=opportunity.id,
            claim_record_id=claim.id,
            request_type="initial",
            salesperson_name=claim.salesperson_name,
            main_sku=opportunity.main_sku,
            sub_sku=opportunity.sub_sku,
            daily_sales=1,
            quantity=30,
            status="draft",
        )
        db.add(request)
        db.flush()
        item = schemas.AvailableStockingItem(
            opportunity_id=opportunity.id,
            request_id=request.id,
            claim_record_id=claim.id,
            status="draft",
            time=models.now_utc(),
            selection_source="manual",
            salesperson_name=claim.salesperson_name,
            main_sku=opportunity.main_sku,
            sub_sku=opportunity.sub_sku,
            site="PH",
            claim_daily_sales=1,
            quantity=30,
        )

        services.record_export_batch(db, [item], "draft.xlsx", "stocking_available")
        db.flush()

        assert claim.downstream_status == "waiting_stocking_request"
        assert opportunity.current_status == "ready_for_stocking"


def test_available_export_filters_by_source_sheet_without_repeating_transitioned_rows() -> None:
    first_id, first_claim_id = prepare_approved_claim(source_sheet="开发0623期", source_row=1, sub_sku="SUB-W27")
    second_id, second_claim_id = prepare_approved_claim(source_sheet="开发0630期", source_row=2, sub_sku="SUB-W28")

    response = export_available("source_sheet=开发0623期")

    assert response.status_code == 200
    list_response = client.get("/stocking/available-list?source_sheet=开发0623期")
    assert list_response.status_code == 200
    assert list_response.json() == []

    with SessionLocal() as db:
        exported = db.query(models.ExportRow).all()
    assert [(row.opportunity_id, row.claim_record_id) for row in exported] == [(first_id, first_claim_id)]

    other_period = client.get("/stocking/available-list?source_sheet=开发0630期")
    assert other_period.status_code == 200
    assert [(item["opportunity_id"], item["claim_record_id"]) for item in other_period.json()] == [(second_id, second_claim_id)]


def test_available_export_filters_by_import_batch_id() -> None:
    first_id, first_claim_id = prepare_approved_claim(import_batch_id="batch-0623", source_row=1, sub_sku="SUB-BATCH-1")
    prepare_approved_claim(import_batch_id="batch-0630", source_row=2, sub_sku="SUB-BATCH-2")

    response = export_available("import_batch_id=batch-0623")

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
        request = db.query(models.StockingRequest).filter_by(claim_record_id=claim.id).one()
        request.status = "submitted"
        claim.downstream_status = "waiting_export"
        db.commit()
        return opportunity.id, claim.id


def export_available(query: str = ""):
    with SessionLocal() as db:
        if db.query(models.RoleMapping).filter_by(dingtalk_user_id="dt-manager").first() is None:
            db.add(models.RoleMapping(name="主管A", role="manager", dingtalk_user_id="dt-manager", enabled=True))
            db.commit()
    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-manager", "name": "主管A"})
    suffix = f"?{query}" if query else ""
    request_ids = [row["request_id"] for row in client.get(f"/stocking/available-list{suffix}").json()]
    return client.post(
        "/stocking/available-list/export",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"request_ids": request_ids},
    )


def test_traceability_batch_records_rows_without_advancing_request_claim_or_opportunity() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="sales_self_selection", main_sku="MAIN-TRACE", sub_sku="SUB-TRACE",
            country="PH", site="PH", current_status="ready_for_stocking",
        )
        db.add(opportunity)
        db.flush()
        claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id, salesperson_name="销售A", claim_result="claim",
            claim_daily_sales=1, source_column="platform", downstream_status="waiting_export",
        )
        db.add(claim)
        db.flush()
        request = models.StockingRequest(
            opportunity_id=opportunity.id, claim_record_id=claim.id, request_type="initial",
            salesperson_name="销售A", main_sku=opportunity.main_sku, sub_sku=opportunity.sub_sku,
            daily_sales=1, quantity=30, status="submitted",
        )
        db.add(request)
        db.flush()
        item = schemas.AvailableStockingItem(
            opportunity_id=opportunity.id, request_id=request.id, claim_record_id=claim.id,
            application_date=None, selection_source="销售自选", salesperson_name="销售A",
            main_sku=opportunity.main_sku, sub_sku=opportunity.sub_sku, site="PH",
            claim_daily_sales=1, quantity=30, stocking_country="PH", status="submitted",
        )

        services.record_export_batch(db, [item], "trace.xlsx", "traceability")
        db.flush()

        row = db.query(models.ExportRow).one()
        assert row.stocking_request_id == request.id
        assert request.status == "submitted"
        assert claim.downstream_status == "waiting_export"
        assert opportunity.current_status == "ready_for_stocking"
