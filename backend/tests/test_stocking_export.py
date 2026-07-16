import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from io import BytesIO
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


STOCKING_HEADERS = [
    "操作状态",
    "时间",
    "备货类型",
    "选品数据源",
    "销售员",
    "主SKU",
    "子sku",
    "成本价",
    "单个体积",
    "备货单销",
    "备货数量",
    "备货国家",
    "备货仓库",
    "货值",
    "体积",
    "补货原因",
]


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_stocking_export_matches_official_workbook_structure() -> None:
    prepare_approved_claims([("销售A", 2.5)])

    response = client.get("/stocking/available-list/export")

    assert response.status_code == 200
    assert "filename*=UTF-8''%E6%B5%B7%E5%A4%96%E4%BB%93%E5%A4%87%E8%B4%A7%E7%94%B3%E8%AF%B7%E8%A1%A8.xlsx" in response.headers[
        "content-disposition"
    ]
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["PH"]
    headers = [cell.value for cell in sheet[1]]
    row = dict(zip(headers, [cell.value for cell in sheet[2]]))

    assert headers == STOCKING_HEADERS
    assert row["销售员"] == "销售A"
    assert row["操作状态"] is None
    assert row["主SKU"] == "MAIN-EXPORT"
    assert row["子sku"] == "SUB-EXPORT"
    assert row["备货单销"] == 2.5
    assert row["备货数量"] == 75
    assert row["补货原因"] is None


def test_stocking_export_splits_sheets_by_country_and_uses_beijing_time() -> None:
    prepare_approved_claims([("销售PH", 1)], country="PH", site="PH", main_sku="MAIN-PH", sub_sku="SUB-PH", source_row=1)
    prepare_approved_claims([("销售TH", 1)], country="TH", site="泰国", main_sku="MAIN-TH", sub_sku="SUB-TH", source_row=2)

    response = client.get("/stocking/available-list/export")

    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert workbook.sheetnames == ["PH", "TH"]
    assert workbook["PH"]["F2"].value == "MAIN-PH"
    assert workbook["TH"]["F2"].value == "MAIN-TH"
    assert services.excel_value(datetime(2026, 7, 6, 2, 9, 38, tzinfo=timezone.utc)) == datetime(2026, 7, 6, 10, 9, 38)
    assert datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=7) <= workbook["PH"]["B2"].value


def test_multiple_approved_claims_for_one_child_sku_export_as_multiple_rows() -> None:
    prepare_approved_claims([("赵钰婷", 1.5), ("李干", 1)])

    response = client.get("/stocking/available-list")

    assert response.status_code == 200
    rows = sorted(response.json(), key=lambda item: item["salesperson_name"])
    assert [(row["salesperson_name"], row["sub_sku"], row["claim_daily_sales"], row["quantity"]) for row in rows] == [
        ("李干", "SUB-EXPORT", 1, 30),
        ("赵钰婷", "SUB-EXPORT", 1.5, 45),
    ]


def test_stocking_export_repeats_current_rows_without_regressing_later_status() -> None:
    opportunity_id = prepare_approved_claims([("销售A", 2.5)])

    first = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert first.status_code == 200

    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id).one()
        claim.downstream_status = "waiting_secondary_research"
        db.commit()

    second = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert second.status_code == 200
    workbook = load_workbook(BytesIO(second.content), data_only=True)
    assert workbook["PH"].max_row == 2

    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id).one()
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        rows = db.query(models.ExportRow).filter_by(claim_record_id=claim.id).all()
        transition_audits = db.query(models.AuditLog).filter_by(
            action="opportunity.waiting_arrival",
            entity_id=opportunity_id,
        ).all()
        assert claim.downstream_status == "waiting_secondary_research"
        assert opportunity.current_status == "waiting_arrival"
        assert len(rows) == 2
        assert len(transition_audits) == 1


def test_legacy_null_review_only_applies_to_claims_existing_when_reviewed() -> None:
    reviewed_at = datetime(2026, 7, 1, 8, tzinfo=timezone.utc)
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_file="选品2.xlsx",
            source_sheet="5.26期",
            source_row=1,
            batch="BATCH-EXPORT",
            country="PH",
            site="PH",
            main_sku="MAIN-LEGACY-REVIEW",
            sub_sku="SUB-LEGACY-REVIEW",
            current_status="ready_for_stocking",
        )
        db.add(opportunity)
        db.flush()
        existing_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售已复核",
            claim_result="claim",
            claim_daily_sales=1,
            source_column="platform",
            created_at=reviewed_at - timedelta(minutes=1),
        )
        later_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售后认领",
            claim_result="claim",
            claim_daily_sales=2,
            source_column="platform",
            created_at=reviewed_at + timedelta(minutes=1),
        )
        db.add_all(
            [
                existing_claim,
                later_claim,
                models.ReviewRecord(
                    opportunity_id=opportunity.id,
                    reviewer_name="历史主管",
                    review_status="approved",
                    created_at=reviewed_at,
                ),
            ]
        )
        db.flush()
        existing_claim_id = existing_claim.id
        db.commit()

    response = client.get("/stocking/available-list?business_period=BATCH-EXPORT")

    assert response.status_code == 200
    assert [(row["claim_record_id"], row["salesperson_name"]) for row in response.json()] == [
        (existing_claim_id, "销售已复核")
    ]


def test_repeat_export_includes_newly_approved_rows_in_the_same_period() -> None:
    prepare_approved_claims([("销售A", 1)], main_sku="MAIN-FIRST", sub_sku="SUB-FIRST", source_row=1)
    first = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")
    assert first.status_code == 200

    prepare_approved_claims([("销售B", 2)], main_sku="MAIN-LATER", sub_sku="SUB-LATER", source_row=2)
    second = client.get("/stocking/available-list/export?business_period=BATCH-EXPORT")

    workbook = load_workbook(BytesIO(second.content), data_only=True)
    assert {workbook["PH"][f"F{row}"].value for row in range(2, workbook["PH"].max_row + 1)} == {
        "MAIN-FIRST",
        "MAIN-LATER",
    }


def test_repeatable_exports_still_exclude_disabled_opportunities() -> None:
    opportunity_id = prepare_approved_claims([("销售A", 1)])
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        assert opportunity is not None
        opportunity.current_status = "disabled"
        db.commit()

    response = client.get("/stocking/available-list?business_period=BATCH-EXPORT")

    assert response.status_code == 200
    assert response.json() == []


def prepare_approved_claims(
    claims: list[tuple[str, float]],
    country: str = "PH",
    site: str = "PH",
    main_sku: str = "MAIN-EXPORT",
    sub_sku: str = "SUB-EXPORT",
    source_row: int = 1,
) -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_file="选品2.xlsx",
            source_sheet="5.26期",
            source_row=source_row,
            batch="BATCH-EXPORT",
            country=country,
            site=site,
            developer_department="产品开发六部",
            developer_name="开发A",
            category_level1="汽摩配",
            keyword="motor cover",
            image_url="https://example.com/image.jpg",
            main_sku_name="摩托车配件",
            main_sku=main_sku,
            sub_sku_name="黑色",
            sub_sku=sub_sku,
            product_type="利润款",
            reason="新品开发",
        )
        db.add(opportunity)
        db.flush()
        for salesperson_name, daily_sales in claims:
            services.submit_claim(
                db,
                schemas.ClaimCreate(
                    opportunity_id=opportunity.id,
                    salesperson_name=salesperson_name,
                    claim_result="claim",
                    claim_daily_sales=daily_sales,
                    claim_source="caigen_self_claim",
                ),
            )
        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                reviewer_name="练玉君",
                review_status="approved",
                review_comment="通过",
            ),
        )
        db.commit()
        return opportunity.id
