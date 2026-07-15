import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from io import BytesIO
import base64

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.utils import column_index_from_string  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.excel_images import PUBLIC_UPLOAD_PREFIX, UPLOADED_SOURCES_ROOT  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_traceability_export_contains_central_fields_and_internal_review_fields() -> None:
    prepare_approved_claim()

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert workbook.sheetnames == ["TH"]
    sheet = workbook["TH"]
    headers = [cell.value for cell in sheet[1]]
    row = dict(zip(headers, [cell.value for cell in sheet[2]]))

    assert headers[: len(services.CENTRAL_TRACEABILITY_HEADERS)] == services.CENTRAL_TRACEABILITY_HEADERS
    assert len(services.CENTRAL_TRACEABILITY_HEADERS) == 80
    assert services.CENTRAL_TRACEABILITY_HEADERS[-1] == "开发是否接受核价结果"
    assert row["站点"] == "泰国"
    assert row["主SKU"] == "MAIN-TRACE"
    assert row["子SKU"] == "SUB-TRACE"
    assert row["开发询价 / 产品规格"] == "规格A"
    assert row["产品外包装"] == "彩盒"
    assert row["商品成本-含税（元）"] == 12.5
    assert row["包装后体积"] == 0.08
    assert row["Shopee菲律宾成本 / 稳定期总成本（PHP）（含头程+平台费+基础设施）"] == 88.8
    assert row["稳定期利润率"] == 0.22
    assert row["平台佣金率"] == 0.191
    assert row["开发是否接受核价结果"] == "接受"
    assert row["销售员"] == "销售A"
    assert row["认领单销"] == 2
    assert row["主管复核状态"] == "approved"
    assert row["导出范围"] == "traceability"


def test_traceability_export_embeds_product_image_instead_of_address_text() -> None:
    prepare_approved_claim()

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["TH"]
    assert sheet["F2"].value is None
    assert len(sheet._images) == 1
    marker = sheet._images[0].anchor._from
    assert (marker.row, marker.col) == (1, 5)


def test_traceability_export_does_not_treat_selection2_column_letters_as_central_fields() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_file="选品2.xlsx",
            source_sheet="5.26期",
            source_row=1,
            main_sku="MAIN-S2",
            sub_sku="SUB-S2",
            snapshot={"cells": {"R": "-125.6"}},
        )
        db.add(opportunity)
        db.flush()
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售B",
                claim_result="claim",
                claim_daily_sales=1,
                claim_source="caigen_self_claim",
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
        db.commit()

    response = client.get("/stocking/traceability/export")

    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["未填国家"]
    rows = [dict(zip([cell.value for cell in sheet[1]], [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    row = next(row for row in rows if row["子SKU"] == "SUB-S2")
    assert row["商品成本-含税（元）"] is None


def test_traceability_export_preserves_selection1_duplicate_headers_by_column(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1_duplicate_headers.xlsx"
    source_workbook = Workbook()
    source_sheet = source_workbook.active
    source_sheet.title = "开发0623期"
    source_sheet.append([None] * column_index_from_string("CH"))
    header_row = [None] * column_index_from_string("CH")
    for column, value in {
        "A": "站点",
        "H": "主SKU",
        "J": "子SKU",
        "AG": "售价(PHP）",
        "AH": "月销",
        "AJ": "售价(PHP）",
        "AK": "月销",
    }.items():
        header_row[column_index_from_string(column) - 1] = value
    source_sheet.append(header_row)
    data_row = [None] * column_index_from_string("CH")
    for column, value in {
        "A": "菲律宾",
        "H": "MAIN-DUP",
        "J": "SUB-DUP",
        "AG": 77,
        "AH": 777,
        "AJ": 88,
        "AK": 888,
    }.items():
        data_row[column_index_from_string(column) - 1] = value
    source_sheet.append(data_row)
    source_workbook.save(workbook_path)

    import_response = client.post(
        "/opportunities/import/selection1",
        json={"source_file": str(workbook_path), "source_sheet": "开发0623期"},
    )
    assert import_response.status_code == 200

    with SessionLocal() as db:
        opportunity = db.query(models.NewProductOpportunity).filter_by(sub_sku="SUB-DUP").one()
        assert opportunity.snapshot["fields_by_column"]["AG"] == 77
        assert opportunity.snapshot["fields_by_column"]["AJ"] == 88
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售C",
                claim_result="claim",
                claim_daily_sales=1,
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
        db.commit()

    response = client.get("/stocking/traceability/export")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = next(sheet for sheet in workbook.worksheets if sheet["J2"].value == "SUB-DUP")

    assert sheet.cell(row=2, column=column_index_from_string("AG")).value == 77
    assert sheet.cell(row=2, column=column_index_from_string("AH")).value == 777
    assert sheet.cell(row=2, column=column_index_from_string("AJ")).value == 88
    assert sheet.cell(row=2, column=column_index_from_string("AK")).value == 888


def test_traceability_export_adds_not_claim_sheet_with_feedback_and_images() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="开发0623期",
            source_row=12,
            country="PH",
            site="菲律宾",
            category_level1="家居厨卫",
            main_sku_name="测试商品",
            main_sku="MAIN-REJECT",
            sub_sku_name="蓝色",
            sub_sku="SUB-REJECT",
        )
        db.add(opportunity)
        db.flush()
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售C",
                claim_result="reject",
                reject_reason="市场调研销量不足",
                feedback_summary="竞品价格压得太低",
                note=json.dumps(
                    {
                        "evidence_images": [
                            {"name": "reject-proof.png", "type": "image/png", "size": 1024},
                        ]
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                reviewer_name="练玉君",
                review_status="confirmed_not_claim",
                review_comment="同意不认领",
            ),
        )
        db.commit()

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert "不认领结果" in workbook.sheetnames
    sheet = workbook["不认领结果"]
    headers = [cell.value for cell in sheet[1]]
    row = dict(zip(headers, [cell.value for cell in sheet[2]]))

    assert row["主SKU"] == "MAIN-REJECT"
    assert row["子SKU"] == "SUB-REJECT"
    assert row["销售员"] == "销售C"
    assert row["认领结果"] == "reject"
    assert row["不认领理由"] == "市场调研销量不足"
    assert row["销售反馈总结"] == "竞品价格压得太低"
    assert row["主管复核状态"] == "confirmed_not_claim"
    assert row["主管复核意见"] == "同意不认领"
    assert row["导出范围"] == "traceability_not_claim"
    assert "reject-proof.png" in row["图片附件"]


def test_traceability_export_filters_by_period_and_excludes_unconfirmed_not_claim() -> None:
    prepare_approved_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=1, main_sku="MAIN-W27", sub_sku="SUB-W27")
    prepare_approved_claim(source_sheet="选品1原始数据", business_period="2026年第30期", source_row=2, main_sku="MAIN-W28", sub_sku="SUB-W28")
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=3, main_sku="MAIN-REJECT-PENDING", review_status=None)
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=4, main_sku="MAIN-REJECT-CONFIRMED", review_status="confirmed_not_claim")
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第30期", source_row=5, main_sku="MAIN-REJECT-OTHER", review_status="confirmed_not_claim")

    response = client.get("/stocking/traceability/export?business_period=2026年第29期")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert "TH" in workbook.sheetnames
    approved_sheet = workbook["TH"]
    approved_values = [row[7].value for row in approved_sheet.iter_rows(min_row=2)]
    assert approved_values == ["MAIN-W27"]

    assert "不认领结果" in workbook.sheetnames
    reject_sheet = workbook["不认领结果"]
    reject_values = [row[7].value for row in reject_sheet.iter_rows(min_row=2)]
    assert reject_values == ["MAIN-REJECT-CONFIRMED"]


def test_traceability_export_records_not_claim_rows_once() -> None:
    prepare_reject_claim(source_sheet="W27", source_row=1, main_sku="MAIN-NOT-CLAIM-ONCE", review_status="confirmed_not_claim")

    first = client.get("/stocking/traceability/export?source_sheet=W27")
    second = client.get("/stocking/traceability/export?source_sheet=W27")

    assert first.status_code == 200
    assert second.status_code == 200
    with SessionLocal() as db:
        exported = db.query(models.ExportRow).all()

    assert len(exported) == 1
    assert exported[0].main_sku == "MAIN-NOT-CLAIM-ONCE"


def prepare_approved_claim(
    source_sheet: str = "开发0623期",
    business_period: str = "BATCH-TRACE",
    source_row: int = 1,
    main_sku: str = "MAIN-TRACE",
    sub_sku: str = "SUB-TRACE",
) -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet=source_sheet,
            source_row=source_row,
            batch=business_period,
            country="TH",
            site="泰国",
            developer_department="产品开发六部",
            developer_name="开发A",
            category_level1="汽摩配",
            keyword="key lock cover",
            image_url=write_uploaded_product_image(),
            main_sku_name="摩托车保护盖",
            main_sku=main_sku,
            sub_sku_name="红色",
            sub_sku=sub_sku,
            product_type="利润款",
            reason="新品开发",
            snapshot={
                "fields_by_header": {
                    "产品规格": "规格A",
                    "产品外包装": "彩盒",
                    "商品成本-含税（元）": 12.5,
                    "包装后体积": 0.08,
                    "稳定期总成本（THB）（含头程+平台费+基础设施）": 88.8,
                    "一次毛利率": 0.22,
                    "平台佣金率（含技术服务费）": 0.191,
                    "开发是否接受核价结果": "接受",
                }
            },
        )
        db.add(opportunity)
        db.flush()
        services.submit_claim(
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
        db.commit()
        return opportunity.id


def prepare_reject_claim(
    source_sheet: str,
    source_row: int,
    main_sku: str,
    review_status: str | None,
    business_period: str | None = None,
) -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet=source_sheet,
            source_row=source_row,
            batch=business_period or source_sheet,
            country="PH",
            site="PH",
            main_sku=main_sku,
            sub_sku=f"{main_sku}-SUB",
        )
        db.add(opportunity)
        db.flush()
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售A",
                claim_result="reject",
                reject_reason="市场容量不足",
            ),
        )
        if review_status:
            services.submit_review(
                db,
                schemas.ReviewCreate(
                    opportunity_id=opportunity.id,
                    reviewer_name="练玉君",
                    review_status=review_status,
                    review_comment="确认不认领",
                ),
            )
        db.commit()
        return opportunity.id


def write_uploaded_product_image() -> str:
    relative_path = Path("product-images/test/row-1-traceability.png")
    target = UPLOADED_SOURCES_ROOT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(TINY_PNG)
    return f"{PUBLIC_UPLOAD_PREFIX}/{relative_path.as_posix()}"
