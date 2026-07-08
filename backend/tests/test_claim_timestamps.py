import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_assigned_claim_update_preserves_first_submit_time_and_tracks_last_update() -> None:
    with SessionLocal() as db:
        opportunity = add_opportunity(db)
        task = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="销售A"),
        )[0]
        db.flush()
        task_id = task.id
        first = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售A",
                claim_result="reject",
                reject_reason="市场容量不足",
                note="第一次提交",
            ),
        )
        db.commit()
        first_id = first.id
        first_submitted_at = first.first_submitted_at
        first_updated_at = first.last_updated_at

        second = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="销售A",
                claim_result="reject",
                reject_reason="竞品价格太低",
                note="补充说明",
            ),
        )
        db.commit()

        claims_count = db.query(models.SalesClaimForecast).count()
        second_id = second.id
        second_task_id = second.task_id
        second_first_submitted_at = second.first_submitted_at
        second_last_updated_at = second.last_updated_at
        second_reject_reason = second.reject_reason
        second_note = second.note

    assert claims_count == 1
    assert second_id == first_id
    assert second_task_id == task_id
    assert second_first_submitted_at == first_submitted_at
    assert second_last_updated_at >= first_updated_at
    assert second_reject_reason == "竞品价格太低"
    assert second_note == "补充说明"


def add_opportunity(db) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        source_type="selection1_developer_claim_feedback",
        source_file="选品1.xlsx",
        source_sheet="开发0623期",
        source_row=1,
        batch="BATCH-1",
        country="PH",
        site="PH",
        category_level1="家居厨卫",
        main_sku="MAIN-CLAIM",
        sub_sku="SUB-CLAIM",
    )
    db.add(opportunity)
    db.flush()
    return opportunity
