import os
import sys
from pathlib import Path

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


def test_review_approved_claim_marks_ready_and_completes_review_task() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=2)

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "approved",
            "review_comment": "通过",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        pending_review_tasks = pending_tasks(db, opportunity_id, "manager_review")
    assert opportunity.current_status == "ready_for_stocking"
    assert pending_review_tasks == []


def test_opportunity_summary_includes_latest_claim_daily_sales() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=2)

    listed = next(item for item in client.get("/opportunities").json() if item["id"] == opportunity_id)

    assert listed["latest_claim_daily_sales"] == 2


def test_operator_can_update_same_claim_before_review_without_duplicate_review_task() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=2)
    with SessionLocal() as db:
        original = db.query(models.SalesClaimForecast).filter_by(opportunity_id=opportunity_id).one()
        original_id = original.id
        first_submitted_at = original.first_submitted_at
        original_updated_at = original.last_updated_at

        updated = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity_id,
                salesperson_name="销售A",
                claim_result="claim",
                claim_daily_sales=5,
            ),
            assignee_name="销售A",
        )
        db.commit()
        pending_review_tasks = pending_tasks(db, opportunity_id, "manager_review")
        updated_values = {
            "id": updated.id,
            "first_submitted_at": updated.first_submitted_at,
            "last_updated_at": updated.last_updated_at,
            "claim_daily_sales": updated.claim_daily_sales,
        }

    assert updated_values["id"] == original_id
    assert updated_values["first_submitted_at"] == first_submitted_at
    assert updated_values["last_updated_at"] >= original_updated_at
    assert updated_values["claim_daily_sales"] == 5
    assert len(pending_review_tasks) == 1


def test_other_operator_cannot_update_submitted_claim() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=2)

    with SessionLocal() as db, pytest.raises(PermissionError, match="does not belong"):
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity_id,
                salesperson_name="销售B",
                claim_result="claim",
                claim_daily_sales=5,
            ),
            assignee_name="销售B",
        )


def test_operator_cannot_update_claim_after_manager_review() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=2)
    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "approved",
        },
    )
    assert response.status_code == 200

    with SessionLocal() as db, pytest.raises(PermissionError, match="does not belong"):
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity_id,
                salesperson_name="销售A",
                claim_result="claim",
                claim_daily_sales=5,
            ),
            assignee_name="销售A",
        )


def test_review_confirmed_not_claim_is_terminal_and_not_exportable() -> None:
    opportunity_id = prepare_submission("reject", reject_reason="市场容量不足")

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "confirmed_not_claim",
            "review_comment": "确认不认领",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
    assert opportunity.current_status == "已确认不认领"
    assert client.get("/stocking/available-list").json() == []


def test_review_returned_for_supplement_creates_sales_claim_task_without_editing_claim() -> None:
    note = '{"evidence_images":[{"name":"market.png","type":"image/png","size":12345}]}'
    opportunity_id = prepare_submission(
        "reject",
        reject_reason="首次理由",
        feedback_summary="竞品价格低，暂不认领",
        note=note,
    )

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "returned_for_supplement",
            "review_comment": "补充市场截图",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        claim = db.query(models.SalesClaimForecast).one()
        returned_tasks = pending_tasks(db, opportunity_id, "sales_claim")
    assert opportunity.current_status == "returned_for_supplement"
    assert claim.reject_reason == "首次理由"
    assert [(task.assignee_name, task.status) for task in returned_tasks] == [("销售A", "pending")]

    listed = next(item for item in client.get("/opportunities").json() if item["id"] == opportunity_id)
    assert listed["latest_claim_result"] == "reject"
    assert listed["latest_claim_salesperson"] == "销售A"
    assert listed["latest_reject_reason"] == "首次理由"
    assert listed["latest_feedback_summary"] == "竞品价格低，暂不认领"
    assert listed["latest_claim_note"] == note
    assert listed["latest_review_status"] == "returned_for_supplement"
    assert listed["latest_review_comment"] == "补充市场截图"


def test_review_returned_for_supplement_requires_reason() -> None:
    opportunity_id = prepare_submission("reject", reject_reason="首次理由")

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "returned_for_supplement",
            "review_comment": " ",
        },
    )

    assert response.status_code == 400
    assert "review_comment" in response.json()["detail"]


def test_review_claim_submission_can_be_returned_for_supplement() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=1)

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "returned_for_supplement",
            "review_comment": "认领单销依据不足",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        returned_tasks = pending_tasks(db, opportunity_id, "sales_claim")
    assert opportunity.current_status == "returned_for_supplement"
    assert [(task.assignee_name, task.status) for task in returned_tasks] == [("销售A", "pending")]


def test_bulk_review_approves_same_type_claim_submissions() -> None:
    opportunity_ids = [prepare_submission("claim", claim_daily_sales=1), prepare_submission("claim", claim_daily_sales=2)]
    with SessionLocal() as db:
        db.add(
            models.SalesClaimForecast(
                opportunity_id=opportunity_ids[0],
                salesperson_name="销售B",
                claim_result="claim",
                claim_daily_sales=3,
                source_column="platform",
            )
        )
        db.commit()

    response = client.post(
        "/reviews/bulk",
        json={"opportunity_ids": opportunity_ids, "reviewer_name": "练玉君", "action": "approve"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "2"
    with SessionLocal() as db:
        statuses = [db.get(models.NewProductOpportunity, opportunity_id).current_status for opportunity_id in opportunity_ids]
        claim_ids = {claim.id for claim in db.query(models.SalesClaimForecast).filter(models.SalesClaimForecast.opportunity_id.in_(opportunity_ids))}
        review_claim_ids = {review.claim_record_id for review in db.query(models.ReviewRecord)}
    assert statuses == ["ready_for_stocking", "ready_for_stocking"]
    assert review_claim_ids == claim_ids


def test_bulk_review_confirms_same_type_not_claim_submissions() -> None:
    opportunity_ids = [
        prepare_submission("reject", reject_reason="市场小"),
        prepare_submission("reject", reject_reason="价格低"),
    ]

    response = client.post(
        "/reviews/bulk",
        json={"opportunity_ids": opportunity_ids, "reviewer_name": "练玉君", "action": "approve"},
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        statuses = [db.get(models.NewProductOpportunity, opportunity_id).current_status for opportunity_id in opportunity_ids]
        review_claim_ids = [review.claim_record_id for review in db.query(models.ReviewRecord)]
    assert statuses == ["已确认不认领", "已确认不认领"]
    assert None not in review_claim_ids


def test_bulk_review_rejects_mixed_submission_types_without_partial_updates() -> None:
    claim_id = prepare_submission("claim", claim_daily_sales=1)
    not_claim_id = prepare_submission("reject", reject_reason="市场小")

    response = client.post(
        "/reviews/bulk",
        json={
            "opportunity_ids": [claim_id, not_claim_id],
            "reviewer_name": "练玉君",
            "action": "reject",
            "review_comment": "统一退回补充",
        },
    )

    assert response.status_code == 400
    assert "same submission type" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.get(models.NewProductOpportunity, claim_id).current_status == "claim_submitted"
        assert db.get(models.NewProductOpportunity, not_claim_id).current_status == "claim_rejected"
        assert db.query(models.ReviewRecord).count() == 0


def test_bulk_review_rejects_same_type_with_shared_reason() -> None:
    opportunity_ids = [prepare_submission("claim", claim_daily_sales=1), prepare_submission("claim", claim_daily_sales=2)]

    response = client.post(
        "/reviews/bulk",
        json={
            "opportunity_ids": opportunity_ids,
            "reviewer_name": "练玉君",
            "action": "reject",
            "review_comment": "补充单销依据",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        statuses = [db.get(models.NewProductOpportunity, opportunity_id).current_status for opportunity_id in opportunity_ids]
        comments = [record.review_comment for record in db.query(models.ReviewRecord).order_by(models.ReviewRecord.created_at)]
    assert statuses == ["returned_for_supplement", "returned_for_supplement"]
    assert comments == ["补充单销依据", "补充单销依据"]


def test_review_cannot_confirm_claim_as_not_claim() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=1)

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "Manager A",
            "review_status": "confirmed_not_claim",
            "review_comment": "wrong path",
        },
    )

    assert response.status_code == 400
    assert "not-claim" in response.json()["detail"]


def test_review_cannot_approve_not_claim_submission() -> None:
    opportunity_id = prepare_submission("reject", reject_reason="market too small")

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "Manager A",
            "review_status": "approved",
            "review_comment": "wrong path",
        },
    )

    assert response.status_code == 400
    assert "claim" in response.json()["detail"]


def test_review_rejects_invalid_status() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=1)

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "edit_claim",
        },
    )

    assert response.status_code == 422
    assert "review_status" in str(response.json()["detail"])


def test_review_payload_cannot_include_operator_fields() -> None:
    opportunity_id = prepare_submission("claim", claim_daily_sales=1)

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "练玉君",
            "review_status": "approved",
            "claim_daily_sales": 99,
        },
    )

    assert response.status_code == 422


def prepare_submission(
    claim_result: str,
    claim_daily_sales: float | None = None,
    reject_reason: str | None = None,
    feedback_summary: str | None = None,
    note: str | None = None,
) -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="开发0623期",
            source_row=1,
            batch="BATCH-REVIEW",
            country="PH",
            site="PH",
            category_level1="家居厨卫",
            main_sku="MAIN-REVIEW",
            sub_sku="SUB-REVIEW",
        )
        db.add(opportunity)
        db.flush()
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
                claim_result=claim_result,
                claim_daily_sales=claim_daily_sales,
                reject_reason=reject_reason,
                feedback_summary=feedback_summary,
                note=note,
            ),
        )
        db.commit()
        return opportunity.id


def pending_tasks(db, opportunity_id: str, task_type: str) -> list[models.FlowTask]:
    return (
        db.query(models.FlowTask)
        .join(models.FlowInstance)
        .filter(
            models.FlowInstance.opportunity_id == opportunity_id,
            models.FlowTask.task_type == task_type,
            models.FlowTask.status == "pending",
        )
        .order_by(models.FlowTask.created_at)
        .all()
    )
