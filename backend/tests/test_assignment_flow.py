import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_confirm_assignment_expands_one_selected_row_to_main_sku_group() -> None:
    with SessionLocal() as db:
        selected = add_opportunity(db, "MAIN-001", "SUB-001", "BATCH-1")
        same_group = add_opportunity(db, "MAIN-001", "SUB-002", "BATCH-1")
        other_batch = add_opportunity(db, "MAIN-001", "SUB-003", "BATCH-2")
        db.commit()

        tasks = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[selected.id], assignee_name="销售A"),
        )
        db.commit()

        selected_id = selected.id
        same_group_id = same_group.id
        assigned_opportunity_ids = {
            task.flow_instance.opportunity_id
            for task in db.query(models.FlowTask).order_by(models.FlowTask.created_at).all()
        }
        refreshed_other_batch = db.get(models.NewProductOpportunity, other_batch.id)

    assert len(tasks) == 2
    assert assigned_opportunity_ids == {selected_id, same_group_id}
    assert refreshed_other_batch.current_status == "pending_assignment"


def test_confirm_assignment_ignores_locked_siblings_when_group_is_partially_assigned() -> None:
    with SessionLocal() as db:
        selected = add_opportunity(db, "MAIN-MIXED", "SUB-001", "BATCH-1")
        same_group_pending = add_opportunity(db, "MAIN-MIXED", "SUB-002", "BATCH-1")
        same_group_locked = add_opportunity(db, "MAIN-MIXED", "SUB-003", "BATCH-1")
        same_group_locked.current_status = "assigned"
        db.commit()

        tasks = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[selected.id], assignee_name="销售A"),
        )
        db.commit()

        selected_id = selected.id
        same_group_pending_id = same_group_pending.id
        same_group_locked_id = same_group_locked.id
        assigned_opportunity_ids = {
            task.flow_instance.opportunity_id
            for task in db.query(models.FlowTask).order_by(models.FlowTask.created_at).all()
        }
        refreshed_locked = db.get(models.NewProductOpportunity, same_group_locked_id)

    assert len(tasks) == 2
    assert assigned_opportunity_ids == {selected_id, same_group_pending_id}
    assert refreshed_locked.current_status == "assigned"


def test_confirm_assignment_rejects_non_pending_opportunities() -> None:
    with SessionLocal() as db:
        opportunity = add_opportunity(db, "MAIN-LOCKED", "SUB-001", "BATCH-1")
        opportunity.current_status = "ready_for_stocking"
        db.commit()

        with pytest.raises(ValueError, match="pending_assignment"):
            services.confirm_assignment(
                db,
                schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="Operator A"),
            )


def test_reassign_rejects_completed_tasks() -> None:
    with SessionLocal() as db:
        opportunity = add_opportunity(db, "MAIN-REASSIGN", "SUB-001", "BATCH-1")
        tasks = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="Operator A"),
        )
        task = tasks[0]
        task.status = "completed"
        db.commit()

        with pytest.raises(ValueError, match="pending"):
            services.reassign_task(
                db,
                schemas.ReassignRequest(task_id=task.id, assignee_name="Operator B", reason="wrong owner"),
            )


def test_my_tasks_includes_opportunity_id_for_frontend_filtering() -> None:
    with SessionLocal() as db:
        opportunity = add_opportunity(db, "MAIN-002", "SUB-001", "BATCH-1")
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="销售A"),
        )
        db.commit()
        opportunity_id = opportunity.id

    response = client.get("/tasks/my?assignee_name=销售A")

    assert response.status_code == 200
    assert response.json()[0]["opportunity_id"] == opportunity_id


def test_my_tasks_keeps_completed_claim_task_visible_until_manager_review() -> None:
    with SessionLocal() as db:
        opportunity = add_opportunity(db, "MAIN-EDITABLE", "SUB-001", "BATCH-1")
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="销售A"),
        )
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
        db.commit()
        opportunity_id = opportunity.id

    response = client.get("/tasks/my?assignee_name=销售A")

    assert response.status_code == 200
    assert [(item["opportunity_id"], item["status"]) for item in response.json()] == [(opportunity_id, "completed")]


def test_preview_assignments_counts_existing_pending_main_sku_groups() -> None:
    with SessionLocal() as db:
        existing_a = add_opportunity(db, "MAIN-A", "SUB-001", "BATCH-1")
        existing_b = add_opportunity(db, "MAIN-B", "SUB-002", "BATCH-1")
        incoming = add_opportunity(db, "MAIN-C", "SUB-003", "BATCH-1")
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[existing_a.id], assignee_name="Operator A"),
        )
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[existing_b.id], assignee_name="Operator A"),
        )
        profiles = [
            SimpleNamespace(operator_name="Operator A", key_site="PH", key_category1="瀹跺眳鍘ㄥ崼", key_category2="", enabled=True),
            SimpleNamespace(operator_name="Operator B", key_site="PH", key_category1="瀹跺眳鍘ㄥ崼", key_category2="", enabled=True),
        ]

        preview = services.preview_assignments([incoming], ["Operator A", "Operator B"], profiles, db=db)

    assert preview[0].suggested_assignee == "Operator B"


def add_opportunity(db, main_sku: str, sub_sku: str, batch: str) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        source_type="selection1_developer_claim_feedback",
        source_file="选品1.xlsx",
        source_sheet="开发0623期",
        source_row=int(sub_sku.rsplit("-", 1)[1]),
        batch=batch,
        country="PH",
        site="PH",
        category_level1="家居厨卫",
        main_sku=main_sku,
        sub_sku=sub_sku,
    )
    db.add(opportunity)
    db.flush()
    return opportunity
