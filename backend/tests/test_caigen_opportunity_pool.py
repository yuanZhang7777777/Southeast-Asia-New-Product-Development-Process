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


def test_joining_claim_pool_creates_one_persistent_task_per_operator_and_child_sku() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)
        first = services.join_selection2_claim_pool(
            db,
            [opportunity.id],
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )
        second = services.join_selection2_claim_pool(
            db,
            [opportunity.id],
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )
        db.commit()

        tasks = db.query(models.FlowTask).all()
        db.refresh(opportunity)

    assert [task.id for task in first] == [task.id for task in second]
    assert len(tasks) == 1
    assert tasks[0].status == "pending"
    assert tasks[0].node_code == "self_claim"
    assert tasks[0].assignee_name == "赵钰婷"
    assert opportunity.current_status == "pending_assignment"


def test_join_claim_pool_endpoint_returns_persistent_tasks() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)
        opportunity_id = opportunity.id
        db.commit()

    response = client.post(
        "/claims/pool/join",
        json={"opportunity_ids": [opportunity_id], "assignee_name": "赵钰婷"},
    )

    assert response.status_code == 200
    assert response.json()[0]["opportunity_id"] == opportunity_id
    assert response.json()[0]["node_code"] == "self_claim"


def test_caigen_opportunity_pool_allows_multiple_self_claims_for_one_child_sku() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)
        zhao_task = services.join_selection2_claim_pool(
            db,
            [opportunity.id],
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )[0]
        li_task = services.join_selection2_claim_pool(
            db,
            [opportunity.id],
            assignee_name="李干",
            assignee_user_id="operator-li",
        )[0]
        zhao_task_id = zhao_task.id
        li_task_id = li_task.id
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="赵钰婷",
                claim_result="claim",
                claim_daily_sales=1.5,
                claim_source="caigen_self_claim",
            ),
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="李干",
                claim_result="claim",
                claim_daily_sales=1,
                claim_source="caigen_self_claim",
            ),
            assignee_name="李干",
            assignee_user_id="operator-li",
        )
        db.commit()

        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.salesperson_name).all()
        task_statuses = {
            task.id: task.status
            for task in db.query(models.FlowTask).filter(models.FlowTask.id.in_([zhao_task_id, li_task_id]))
        }

    assert [(claim.salesperson_name, claim.claim_daily_sales, claim.claim_source, claim.task_id) for claim in claims] == [
        ("李干", 1, "caigen_self_claim", li_task_id),
        ("赵钰婷", 1.5, "caigen_self_claim", zhao_task_id),
    ]
    assert task_statuses == {zhao_task_id: "completed", li_task_id: "completed"}


def test_joined_task_can_be_submitted_after_manager_closes_pool() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)
        task = services.join_selection2_claim_pool(
            db,
            [opportunity.id],
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )[0]
        opportunity.claim_pool_open = False

        claim = services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="赵钰婷",
                claim_result="reject",
                reject_reason="利润不足",
                claim_source="caigen_self_claim",
            ),
            assignee_name="赵钰婷",
            assignee_user_id="operator-zhao",
        )

    assert claim.task_id == task.id
    assert task.status == "completed"


def test_caigen_self_claim_requires_joined_task() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)

        with pytest.raises(PermissionError, match="task"):
            services.submit_claim(
                db,
                schemas.ClaimCreate(
                    opportunity_id=opportunity.id,
                    salesperson_name="Operator A",
                    claim_result="claim",
                    claim_daily_sales=1,
                    claim_source="caigen_self_claim",
                ),
                assignee_name="Operator A",
                assignee_user_id="operator-a",
            )


def test_caigen_self_claim_rejects_non_caigen_opportunity() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="W27",
            source_row=1,
            batch="W27",
            main_sku="MAIN-A",
            sub_sku="SUB-A",
        )
        db.add(opportunity)
        db.commit()

        with pytest.raises(PermissionError, match="caigen"):
            services.submit_claim(
                db,
                schemas.ClaimCreate(
                    opportunity_id=opportunity.id,
                    salesperson_name="Operator A",
                    claim_result="claim",
                    claim_daily_sales=1,
                    claim_source="caigen_self_claim",
                ),
            )


def add_caigen_opportunity(db) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        source_type="selection2_caigen_claim_feedback",
        source_file="选品2.xlsx",
        source_sheet="5.26期",
        source_row=1,
        batch="BATCH-CAIGEN",
        country="PH",
        site="PH",
        category_level1="汽摩配",
        main_sku="HXG15GD",
        sub_sku="HXG15GD",
        claim_pool_open=True,
    )
    db.add(opportunity)
    db.flush()
    return opportunity
