import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_assignment_board.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def confirm_at(db, opportunity, assignee_name: str, assigned_at: datetime) -> list[models.FlowTask]:
    tasks = services.confirm_assignment(
        db,
        schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name=assignee_name),
    )
    db.flush()
    for task in tasks:
        task.created_at = assigned_at
    return tasks


def test_board_groups_assignments_by_batch_with_assignee_and_status() -> None:
    base_time = datetime(2026, 7, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        newer = add_opportunity(db, "MAIN-N", "SUB-N1", "0714期")
        older = add_opportunity(db, "MAIN-O", "SUB-O1", "0707期")
        unassigned = add_opportunity(db, "MAIN-P", "SUB-P1", "0714期")
        confirm_at(db, older, "运营B", base_time - timedelta(days=7))
        confirm_at(db, newer, "运营A", base_time)
        db.commit()
        newer_id = newer.id
        unassigned_id = unassigned.id

    response = client.get("/assignments/board")

    assert response.status_code == 200
    body = response.json()
    assert body["batches"] == ["0714期", "0707期"]
    assert body["assignees"] == ["运营A", "运营B"]
    assert [group["batch"] for group in body["groups"]] == ["0714期", "0707期"]
    newer_rows = body["groups"][0]["rows"]
    assert [row["opportunity_id"] for row in newer_rows] == [newer_id]
    assert newer_rows[0]["assignee_name"] == "运营A"
    assert newer_rows[0]["task_status"] == "pending"
    assert newer_rows[0]["opportunity_status"] == "assigned"
    assert newer_rows[0]["main_sku"] == "MAIN-N"
    assert newer_rows[0]["sub_sku"] == "SUB-N1"
    all_ids = [row["opportunity_id"] for group in body["groups"] for row in group["rows"]]
    assert unassigned_id not in all_ids


def test_board_filters_by_batch_and_assignee_but_keeps_filter_options() -> None:
    base_time = datetime(2026, 7, 20, tzinfo=timezone.utc)
    with SessionLocal() as db:
        first = add_opportunity(db, "MAIN-1", "SUB-101", "0707期")
        second = add_opportunity(db, "MAIN-2", "SUB-201", "0714期")
        confirm_at(db, first, "运营B", base_time - timedelta(days=7))
        confirm_at(db, second, "运营A", base_time)
        db.commit()

    response = client.get("/assignments/board", params={"batch": "0707期", "assignee_name": "运营B"})

    assert response.status_code == 200
    body = response.json()
    assert body["batches"] == ["0714期", "0707期"]
    assert body["assignees"] == ["运营A", "运营B"]
    assert len(body["groups"]) == 1
    assert body["groups"][0]["batch"] == "0707期"
    assert [row["assignee_name"] for row in body["groups"][0]["rows"]] == ["运营B"]

    empty = client.get("/assignments/board", params={"batch": "0707期", "assignee_name": "运营A"})

    assert empty.status_code == 200
    assert empty.json()["groups"] == []


def test_board_reflects_reassignment_and_hides_disabled_opportunities() -> None:
    with SessionLocal() as db:
        target = add_opportunity(db, "MAIN-R", "SUB-R1", "0714期")
        disabled = add_opportunity(db, "MAIN-D", "SUB-D1", "0714期")
        tasks = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[target.id], assignee_name="运营A"),
        )
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[disabled.id], assignee_name="运营B"),
        )
        db.flush()
        disabled.current_status = "disabled"
        db.commit()
        task_id = tasks[0].id

    reassign = client.post(
        "/assignments/reassign",
        json={"task_id": task_id, "assignee_name": "运营C", "reason": "主管改派"},
    )

    assert reassign.status_code == 200

    response = client.get("/assignments/board")

    assert response.status_code == 200
    body = response.json()
    rows = [row for group in body["groups"] for row in group["rows"]]
    assert [(row["main_sku"], row["assignee_name"]) for row in rows] == [("MAIN-R", "运营C")]


def add_opportunity(db, main_sku: str, sub_sku: str, batch: str) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        source_type="selection1_developer_claim_feedback",
        source_file="选品1.xlsx",
        source_sheet=batch,
        source_row=1,
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
