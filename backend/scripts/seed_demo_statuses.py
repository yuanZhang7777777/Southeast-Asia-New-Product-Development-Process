from __future__ import annotations

from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app import models, schemas, services
from app.db import SessionLocal
from app.workflow_status import (
    CLAIM_RESULT_CLAIM,
    CLAIM_RESULT_REJECT,
    OPPORTUNITY_ASSIGNED,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_CLAIM_SUBMITTED,
    OPPORTUNITY_CONFIRMED_NOT_CLAIM,
    OPPORTUNITY_PENDING_ASSIGNMENT,
    OPPORTUNITY_READY_FOR_STOCKING,
    OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
    REVIEW_APPROVED,
    REVIEW_CONFIRMED_NOT_CLAIM,
    REVIEW_RETURNED_FOR_SUPPLEMENT,
    TASK_PENDING,
)


DEMO_SOURCE_TYPE = "local_demo_status_coverage"
DEMO_SOURCE_FILE = "本地演示数据脚本"


def main() -> None:
    with SessionLocal() as db:
        clear_demo(db)
        seed_profiles(db)
        seed_opportunities(db)
        db.commit()
    print("seeded local demo status coverage")


def clear_demo(db) -> None:
    opportunity_ids = list(
        db.scalars(
            select(models.NewProductOpportunity.id).where(
                (models.NewProductOpportunity.source_type == DEMO_SOURCE_TYPE)
                | (models.NewProductOpportunity.source_file == DEMO_SOURCE_FILE)
            )
        )
    )
    if not opportunity_ids:
        return

    flow_ids = list(
        db.scalars(select(models.FlowInstance.id).where(models.FlowInstance.opportunity_id.in_(opportunity_ids)))
    )
    if flow_ids:
        db.execute(delete(models.FlowTask).where(models.FlowTask.flow_instance_id.in_(flow_ids)))
    db.execute(delete(models.FlowInstance).where(models.FlowInstance.opportunity_id.in_(opportunity_ids)))
    db.execute(delete(models.ReviewRecord).where(models.ReviewRecord.opportunity_id.in_(opportunity_ids)))
    db.execute(delete(models.StockingRequest).where(models.StockingRequest.opportunity_id.in_(opportunity_ids)))
    db.execute(delete(models.SalesClaimForecast).where(models.SalesClaimForecast.opportunity_id.in_(opportunity_ids)))
    db.execute(delete(models.SourceRecordSnapshot).where(models.SourceRecordSnapshot.opportunity_id.in_(opportunity_ids)))
    db.execute(delete(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(opportunity_ids)))


def seed_profiles(db) -> None:
    rows = [
        ("庞莹莹", "PH", "家居厨卫", "商办工业"),
        ("陈丽妹", "PH", "家居厨卫", "商办工业"),
        ("冯卓宏", "PH", "汽摩配", "家居厨卫"),
        ("赵钰婷", "TH", "汽摩配", "户外运动"),
        ("李干", "VN", "商办工业", "家居厨卫"),
    ]
    for operator_name, key_site, key_category1, key_category2 in rows:
        profile = db.scalar(
            select(models.OperatorAssignmentProfile).where(
                models.OperatorAssignmentProfile.operator_name == operator_name
            )
        )
        if profile is None:
            profile = models.OperatorAssignmentProfile(operator_name=operator_name)
            db.add(profile)
        profile.key_site = key_site
        profile.key_category1 = key_category1
        profile.key_category2 = key_category2
        profile.enabled = True


def seed_opportunities(db) -> None:
    add_group(db, "DEMO-PENDING", ["A", "B"], OPPORTUNITY_PENDING_ASSIGNMENT, "TH", "家居厨卫", 10)
    add_group(db, "DEMO-PENDING-PH-HOME", ["A", "B", "C"], OPPORTUNITY_PENDING_ASSIGNMENT, "PH", "家居厨卫", 12)
    add_group(db, "DEMO-PENDING-PH-AUTO", ["A"], OPPORTUNITY_PENDING_ASSIGNMENT, "PH", "汽摩配", 15)
    add_group(db, "DEMO-PENDING-VN-OFFICE", ["A", "B"], OPPORTUNITY_PENDING_ASSIGNMENT, "VN", "商办工业", 16)
    add_group(db, "DEMO-PENDING-FALLBACK", ["A"], OPPORTUNITY_PENDING_ASSIGNMENT, "SG", "玩具", 18)

    assigned = add_group(db, "DEMO-ASSIGNED", ["A", "B"], OPPORTUNITY_ASSIGNED, "PH", "汽摩配", 30)
    for item in assigned:
        add_task(db, item, "陈丽妹")

    add_group(db, "DEMO-POOL", ["A"], "open_claim_pool", "PH", "商办工业", 40)

    submitted = add_group(db, "DEMO-REVIEW", ["A"], OPPORTUNITY_CLAIM_SUBMITTED, "VN", "家居厨卫", 50)[0]
    submit_claim(db, submitted, "庞莹莹", CLAIM_RESULT_CLAIM, daily_sales=1.2)

    rejected = add_group(db, "DEMO-REJECT", ["A"], OPPORTUNITY_CLAIM_REJECTED, "TH", "户外运动", 60)[0]
    submit_claim(
        db,
        rejected,
        "赵钰婷",
        CLAIM_RESULT_REJECT,
        reject_reason="市场调研销量不足，已附截图占位",
        note='{"evidence_images":[{"name":"demo-research.png","type":"image/png","size":12345}]}',
    )

    returned = add_group(db, "DEMO-RETURN", ["A"], OPPORTUNITY_RETURNED_FOR_SUPPLEMENT, "PH", "家居厨卫", 70)[0]
    submit_claim(db, returned, "冯卓宏", CLAIM_RESULT_REJECT, reject_reason="需要补充竞品截图")
    submit_review(db, returned, REVIEW_RETURNED_FOR_SUPPLEMENT, "请补充竞品截图")

    ready = add_group(db, "DEMO-READY", ["A"], OPPORTUNITY_READY_FOR_STOCKING, "VN", "商办工业", 80)[0]
    submit_claim(db, ready, "李干", CLAIM_RESULT_CLAIM, daily_sales=1.5)
    submit_review(db, ready, REVIEW_APPROVED, "通过")

    confirmed = add_group(db, "DEMO-NOT-CLAIM", ["A"], OPPORTUNITY_CONFIRMED_NOT_CLAIM, "TH", "汽摩配", 90)[0]
    submit_claim(db, confirmed, "赵钰婷", CLAIM_RESULT_REJECT, reject_reason="同款竞争激烈，确认不认领")
    submit_review(db, confirmed, REVIEW_CONFIRMED_NOT_CLAIM, "确认不认领")

    mixed_ready = add_opportunity(db, "DEMO-MIXED", "DEMO-MIXED-A", OPPORTUNITY_READY_FOR_STOCKING, "PH", "家居厨卫", 100)
    submit_claim(db, mixed_ready, "陈丽妹", CLAIM_RESULT_CLAIM, daily_sales=1)
    submit_review(db, mixed_ready, REVIEW_APPROVED, "通过")
    mixed_reject = add_opportunity(db, "DEMO-MIXED", "DEMO-MIXED-B", OPPORTUNITY_CONFIRMED_NOT_CLAIM, "PH", "家居厨卫", 101)
    submit_claim(db, mixed_reject, "陈丽妹", CLAIM_RESULT_REJECT, reject_reason="规格不适合海外仓备货")
    submit_review(db, mixed_reject, REVIEW_CONFIRMED_NOT_CLAIM, "确认不认领")

    seed_stocking_request_branches(db)


def seed_stocking_request_branches(db) -> None:
    items = services.create_sales_self_selection(
        db,
        schemas.SalesSelfSelectionCreate(
            main_sku="DEMO-SELF-STOCKING",
            main_sku_name="销售自选备货演示",
            country="PH",
            children=[
                schemas.SalesSelfSelectionChildCreate(
                    sub_sku="DEMO-SELF-DRAFT", inventory_available=False, needs_stocking=True
                ),
                schemas.SalesSelfSelectionChildCreate(
                    sub_sku="DEMO-SELF-SUBMITTED", inventory_available=False, needs_stocking=True
                ),
                schemas.SalesSelfSelectionChildCreate(
                    sub_sku="DEMO-SELF-LIST", inventory_available=True, needs_stocking=False
                ),
                schemas.SalesSelfSelectionChildCreate(
                    sub_sku="DEMO-SELF-PAUSED", inventory_available=False, needs_stocking=False
                ),
            ],
        ),
        "庞莹莹",
    )
    for item in items:
        opportunity = db.get(models.NewProductOpportunity, item.opportunity_id)
        opportunity.source_file = DEMO_SOURCE_FILE
        snapshot = db.scalar(
            select(models.SourceRecordSnapshot).where(
                models.SourceRecordSnapshot.opportunity_id == item.opportunity_id
            )
        )
        snapshot.source_file = DEMO_SOURCE_FILE

    submitted = next(item for item in items if item.sub_sku == "DEMO-SELF-SUBMITTED")
    services.update_stocking_request(
        db,
        submitted.request_id,
        "庞莹莹",
        schemas.StockingRequestUpdate(
            application_date=date(2026, 7, 21),
            request_type="initial",
            cost_price=12.5,
            unit_volume=0.002,
            daily_sales=2.01,
            country="PH",
        ),
    )
    services.submit_stocking_request(db, submitted.request_id, "庞莹莹")


def add_group(
    db,
    main_sku: str,
    suffixes: list[str],
    status: str,
    site: str,
    category: str,
    row_start: int,
) -> list[models.NewProductOpportunity]:
    return [
        add_opportunity(db, main_sku, f"{main_sku}-{suffix}", status, site, category, row_index)
        for row_index, suffix in enumerate(suffixes, start=row_start)
    ]


def add_opportunity(
    db,
    main_sku: str,
    sub_sku: str,
    status: str,
    site: str,
    category: str,
    source_row: int,
) -> models.NewProductOpportunity:
    item = models.NewProductOpportunity(
        source_type=DEMO_SOURCE_TYPE,
        source_file=DEMO_SOURCE_FILE,
        source_sheet="状态覆盖",
        source_row=source_row,
        country=site,
        site=site,
        category_level1=category,
        keyword=f"{category} Demo 商品",
        main_sku=main_sku,
        main_sku_name=f"{main_sku} 主商品",
        sub_sku=sub_sku,
        sub_sku_name=f"{sub_sku} 子款",
        current_status=status,
        snapshot={"demo": True, "status": status},
    )
    db.add(item)
    db.flush()
    db.add(
        models.SourceRecordSnapshot(
            opportunity_id=item.id,
            source_file=item.source_file,
            source_sheet=item.source_sheet,
            source_row=item.source_row,
            column_range="demo",
            payload=item.snapshot,
        )
    )
    return item


def add_task(db, item: models.NewProductOpportunity, assignee_name: str) -> None:
    flow = models.FlowInstance(
        opportunity_id=item.id,
        current_node="sales_claim",
        current_status=OPPORTUNITY_ASSIGNED,
        owner_role="sales",
    )
    db.add(flow)
    db.flush()
    db.add(
        models.FlowTask(
            flow_instance_id=flow.id,
            node_code="sales_claim",
            task_type="sales_claim",
            assignee_name=assignee_name,
            assignee_role="sales",
            status=TASK_PENDING,
        )
    )


def submit_claim(
    db,
    item: models.NewProductOpportunity,
    salesperson_name: str,
    claim_result: str,
    daily_sales: float | None = None,
    reject_reason: str | None = None,
    note: str | None = None,
) -> None:
    services.submit_claim(
        db,
        schemas.ClaimCreate(
            opportunity_id=item.id,
            salesperson_name=salesperson_name,
            claim_result=claim_result,
            claim_daily_sales=daily_sales,
            reject_reason=reject_reason,
            feedback_summary="本地演示数据",
            claim_source="assigned_task",
            note=note,
        )
    )


def submit_review(
    db,
    item: models.NewProductOpportunity,
    review_status: str,
    review_comment: str,
) -> None:
    services.submit_review(
        db,
        schemas.ReviewCreate(
            opportunity_id=item.id,
            reviewer_name="练玉君",
            review_status=review_status,
            review_comment=review_comment,
        ),
    )


if __name__ == "__main__":
    main()
