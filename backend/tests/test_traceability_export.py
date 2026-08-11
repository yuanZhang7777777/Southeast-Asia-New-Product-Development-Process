import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from io import BytesIO
import base64

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.excel_images import PUBLIC_UPLOAD_PREFIX, UPLOADED_SOURCES_ROOT  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
TRACEABILITY_HEADERS = ["站点", "主SKU", "子SKU", "销售员", "认领结果", "认领单销", "不认领理由", "主管复核状态（中文）", "主管复核意见"]


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_export_periods_list_every_imported_period_with_current_counts() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.ImportBatch(source_type="selection1", source_sheet="S29", business_period="2026年第29期", imported_at=datetime(2026, 7, 1, tzinfo=timezone.utc)),
                models.ImportBatch(source_type="selection1", source_sheet="S30", business_period="2026年第30期", imported_at=datetime(2026, 7, 8, tzinfo=timezone.utc)),
                models.ImportBatch(source_type="selection1", source_sheet="S31", business_period="2026年第31期", imported_at=datetime(2026, 7, 15, tzinfo=timezone.utc)),
                models.ImportBatch(source_type="history_cleanup", source_sheet="历史归档", business_period="历史归档", imported_at=datetime(2026, 7, 16, tzinfo=timezone.utc)),
            ]
        )
        db.commit()

    prepare_approved_claim(business_period="2026年第29期", source_row=1, main_sku="MAIN-29", sub_sku="SUB-29")
    prepare_reject_claim(source_sheet="S29", business_period="2026年第29期", source_row=2, main_sku="REJECT-29", review_status="confirmed_not_claim")
    prepare_approved_claim(business_period="2026年第30期", source_row=3, main_sku="MAIN-30", sub_sku="SUB-30")
    prepare_approved_claim(business_period="历史归档", source_row=4, main_sku="MAIN-HIDDEN", sub_sku="SUB-HIDDEN")

    response = client.get("/stocking/export-periods")

    assert response.status_code == 200
    assert [
        (row["business_period"], row["stocking_count"], row["traceability_count"])
        for row in response.json()
    ] == [
        ("2026年第31期", 0, 0),
        ("2026年第30期", 1, 1),
        ("2026年第29期", 1, 2),
    ]


def test_traceability_export_contains_only_claim_review_columns_for_claim_and_reject() -> None:
    prepare_approved_claim_without_stocking()
    prepare_reject_claim(source_sheet="开发0623期", business_period="BATCH-TRACE", source_row=2, main_sku="MAIN-REJECT", review_status="confirmed_not_claim")

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert workbook.sheetnames == ["认领复核明细"]
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]

    assert headers == TRACEABILITY_HEADERS
    assert [(row["主SKU"], row["认领结果"], row["主管复核状态（中文）"]) for row in rows] == [
        ("MAIN-TRACE", "认领", "认领通过"),
        ("MAIN-REJECT", "不认领", "确认不认领"),
    ]
    assert rows[0]["站点"] == "泰国"
    assert rows[0]["销售员"] == "销售A"
    assert rows[0]["认领单销"] == 2
    assert rows[1]["不认领理由"] == "市场容量不足"


def test_central_traceability_export_is_kept_as_separate_export_type() -> None:
    prepare_approved_claim_without_stocking()
    prepare_reject_claim(source_sheet="开发0623期", business_period="BATCH-TRACE", source_row=2, main_sku="MAIN-REJECT", review_status="confirmed_not_claim")

    response = client.get("/stocking/traceability/central-export?business_period=BATCH-TRACE")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["中央字段导出"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    assert headers[: len(services.CENTRAL_TRACEABILITY_HEADERS)] == services.CENTRAL_TRACEABILITY_HEADERS
    assert "图片附件" not in headers
    assert [row["认领结果"] for row in rows] == ["认领", "不认领"]
    assert len(sheet._images) == 0


def test_traceability_export_does_not_embed_product_images() -> None:
    prepare_approved_claim()

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["认领复核明细"]
    assert len(sheet._images) == 0


def test_traceability_export_does_not_include_central_source_fields() -> None:
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
        submit_latest_stocking_request(db, opportunity.id)
        db.commit()

    response = client.get("/stocking/traceability/export")

    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    row = next(row for row in rows if row["子SKU"] == "SUB-S2")
    assert headers == TRACEABILITY_HEADERS
    assert row["主SKU"] == "MAIN-S2"


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
        claim = services.submit_claim(
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
                claim_record_id=claim.id,
                reviewer_name="练玉君",
                review_status="confirmed_not_claim",
                review_comment="同意不认领",
            ),
        )
        db.commit()

    response = client.get("/stocking/traceability/export")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    assert workbook.sheetnames == ["认领复核明细"]
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    row = dict(zip(headers, [cell.value for cell in sheet[2]]))

    assert row["主SKU"] == "MAIN-REJECT"
    assert row["子SKU"] == "SUB-REJECT"
    assert row["销售员"] == "销售C"
    assert row["认领结果"] == "不认领"
    assert row["不认领理由"] == "市场调研销量不足"
    assert row["主管复核状态（中文）"] == "确认不认领"
    assert row["主管复核意见"] == "同意不认领"
    assert "图片附件" not in headers


def test_traceability_export_filters_by_period_and_excludes_unconfirmed_not_claim() -> None:
    prepare_approved_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=1, main_sku="MAIN-W27", sub_sku="SUB-W27")
    prepare_approved_claim(source_sheet="选品1原始数据", business_period="2026年第30期", source_row=2, main_sku="MAIN-W28", sub_sku="SUB-W28")
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=3, main_sku="MAIN-REJECT-PENDING", review_status=None)
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第29期", source_row=4, main_sku="MAIN-REJECT-CONFIRMED", review_status="confirmed_not_claim")
    prepare_reject_claim(source_sheet="选品1原始数据", business_period="2026年第30期", source_row=5, main_sku="MAIN-REJECT-OTHER", review_status="confirmed_not_claim")

    response = client.get("/stocking/traceability/export?business_period=2026年第29期")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    assert [row["主SKU"] for row in rows] == ["MAIN-W27", "MAIN-REJECT-CONFIRMED"]


def test_traceability_export_excludes_disabled_not_claim_opportunities() -> None:
    opportunity_id = prepare_reject_claim(
        source_sheet="W-DISABLED",
        source_row=1,
        main_sku="MAIN-DISABLED",
        review_status="confirmed_not_claim",
    )
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        assert opportunity is not None
        opportunity.current_status = "disabled"
        db.commit()

    with SessionLocal() as db:
        rows = services.list_not_claim_traceability_rows(db, source_sheet="W-DISABLED")

    assert rows == []


def test_traceability_export_requires_confirmation_for_each_not_claim_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="W-CLAIM-SCOPE",
            source_row=1,
            batch="W-CLAIM-SCOPE",
            country="PH",
            site="PH",
            main_sku="MAIN-CLAIM-SCOPE",
            sub_sku="SUB-CLAIM-SCOPE",
        )
        db.add(opportunity)
        db.flush()
        confirmed = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售已确认",
                claim_result="reject",
                reject_reason="市场容量不足",
            ),
        )
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售未确认",
                claim_result="reject",
                reject_reason="市场容量不足",
            ),
        )
        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                claim_record_id=confirmed.id,
                reviewer_name="练玉君",
                review_status="confirmed_not_claim",
            ),
        )
        db.commit()

    response = client.get("/stocking/traceability/export?source_sheet=W-CLAIM-SCOPE")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    assert {row["销售员"] for row in rows} == {"销售已确认"}


def test_bulk_confirmed_not_claim_rows_are_claim_scoped_and_exported() -> None:
    opportunity_ids = [
        prepare_reject_claim("W-BULK-NOT-CLAIM", 1, "MAIN-BULK-A", None),
        prepare_reject_claim("W-BULK-NOT-CLAIM", 2, "MAIN-BULK-B", None),
    ]

    response = client.post(
        "/reviews/bulk",
        json={"opportunity_ids": opportunity_ids, "reviewer_name": "练玉君", "action": "approve"},
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        rows = services.list_not_claim_traceability_rows(db, source_sheet="W-BULK-NOT-CLAIM")
        review_claim_ids = [review.claim_record_id for review in db.query(models.ReviewRecord)]
    assert {opportunity.main_sku for opportunity, _, _ in rows} == {"MAIN-BULK-A", "MAIN-BULK-B"}
    assert None not in review_claim_ids


def test_historical_null_not_claim_confirmation_exports_only_latest_existing_submission() -> None:
    _, older_claim_id, latest_claim_id = prepare_historical_null_reject_review(
        "W-LEGACY-NOT-CLAIM",
        "confirmed_not_claim",
    )

    response = client.get("/stocking/traceability/export?source_sheet=W-LEGACY-NOT-CLAIM")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), data_only=True)
    sheet = workbook["认领复核明细"]
    headers = [cell.value for cell in sheet[1]]
    rows = [dict(zip(headers, [cell.value for cell in row])) for row in sheet.iter_rows(min_row=2)]
    assert [row["销售员"] for row in rows] == ["销售最新提交"]
    with SessionLocal() as db:
        exported_claim_ids = {row.claim_record_id for row in db.query(models.ExportRow)}
    assert older_claim_id not in exported_claim_ids
    assert exported_claim_ids == {latest_claim_id}


def test_historical_null_return_targets_only_latest_existing_submission() -> None:
    opportunity_id, older_claim_id, latest_claim_id = prepare_historical_null_reject_review(
        "W-LEGACY-RETURN",
        "returned_for_supplement",
    )

    with SessionLocal() as db:
        older_review = services.latest_review_for_claim(
            db,
            opportunity_id,
            db.get(models.SalesClaimForecast, older_claim_id),
        )
        latest_review = services.latest_review_for_claim(
            db,
            opportunity_id,
            db.get(models.SalesClaimForecast, latest_claim_id),
        )

    assert older_review is None
    assert latest_review is not None
    assert latest_review.review_status == "returned_for_supplement"


def test_traceability_export_records_each_repeat_download() -> None:
    prepare_reject_claim(source_sheet="W27", source_row=1, main_sku="MAIN-NOT-CLAIM-ONCE", review_status="confirmed_not_claim")

    first = client.get("/stocking/traceability/export?source_sheet=W27")
    second = client.get("/stocking/traceability/export?source_sheet=W27")

    assert first.status_code == 200
    assert second.status_code == 200
    with SessionLocal() as db:
        exported = db.query(models.ExportRow).all()

    assert len(exported) == 2
    assert {row.main_sku for row in exported} == {"MAIN-NOT-CLAIM-ONCE"}
    assert len({row.export_batch_id for row in exported}) == 2


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
        submit_latest_stocking_request(db, opportunity.id)
        db.commit()
        return opportunity.id


def prepare_approved_claim_without_stocking() -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="开发0623期",
            source_row=1,
            batch="BATCH-TRACE",
            country="TH",
            site="泰国",
            main_sku="MAIN-TRACE",
            sub_sku="SUB-TRACE",
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
                note=json.dumps(
                    {"evidence_images": [{"name": "claim-proof.png", "type": "image/png", "size": 2048}]},
                    ensure_ascii=False,
                ),
            ),
        )
        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                claim_record_id=claim.id,
                reviewer_name="练玉君",
                review_status="approved",
            ),
        )
        db.commit()
        return opportunity.id


def submit_latest_stocking_request(db, opportunity_id: str) -> None:
    claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id, claim_result="claim").one()
    request = db.query(models.StockingRequest).filter_by(claim_record_id=claim.id).one()
    request.status = "submitted"
    claim.downstream_status = "waiting_export"

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
        claim = services.submit_claim(
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
                    claim_record_id=claim.id,
                    reviewer_name="练玉君",
                    review_status=review_status,
                    review_comment="确认不认领",
                ),
            )
        db.commit()
        return opportunity.id


def prepare_historical_null_reject_review(source_sheet: str, review_status: str) -> tuple[str, str, str]:
    reviewed_at = datetime(2026, 7, 1, 8, tzinfo=timezone.utc)
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet=source_sheet,
            source_row=1,
            batch=source_sheet,
            country="PH",
            site="PH",
            main_sku=f"MAIN-{source_sheet}",
            sub_sku=f"SUB-{source_sheet}",
            current_status="已确认不认领" if review_status == "confirmed_not_claim" else "returned_for_supplement",
        )
        db.add(opportunity)
        db.flush()
        older_submitted_at = reviewed_at - timedelta(minutes=2)
        latest_submitted_at = reviewed_at - timedelta(minutes=1)
        older_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售较早提交",
            claim_result="reject",
            reject_reason="较早不认领",
            source_column="platform",
            created_at=older_submitted_at,
            first_submitted_at=older_submitted_at,
            last_updated_at=older_submitted_at,
        )
        latest_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售最新提交",
            claim_result="reject",
            reject_reason="最新不认领",
            source_column="platform",
            created_at=latest_submitted_at,
            first_submitted_at=latest_submitted_at,
            last_updated_at=latest_submitted_at,
        )
        db.add_all(
            [
                older_claim,
                latest_claim,
                models.ReviewRecord(
                    opportunity_id=opportunity.id,
                    reviewer_name="历史主管",
                    review_status=review_status,
                    created_at=reviewed_at,
                ),
            ]
        )
        db.flush()
        result = (opportunity.id, older_claim.id, latest_claim.id)
        db.commit()
        return result


def write_uploaded_product_image() -> str:
    relative_path = Path("product-images/test/row-1-traceability.png")
    target = UPLOADED_SOURCES_ROOT / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(TINY_PNG)
    return f"{PUBLIC_UPLOAD_PREFIX}/{relative_path.as_posix()}"
