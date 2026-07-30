import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas  # noqa: E402
from app.auth import AuthContext  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.claims import submit_claim as submit_claim_route  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_claim_task(db, assignee: str) -> str:
    opportunity = models.NewProductOpportunity(
        source_type="selection2_caigen_claim_feedback",
        main_sku="HXG15G",
        sub_sku="HXG15GD",
    )
    db.add(opportunity)
    db.flush()
    flow = models.FlowInstance(opportunity_id=opportunity.id, current_node="sales_claim", current_status="assigned", owner_role="sales")
    db.add(flow)
    db.flush()
    db.add(models.FlowTask(flow_instance_id=flow.id, node_code="sales_claim", task_type="sales_claim", assignee_name=assignee, assignee_role="sales"))
    db.flush()
    return opportunity.id


def auth_context(db, name: str, role: str) -> AuthContext:
    user = models.User(name=name)
    db.add(user)
    db.flush()
    return AuthContext(user=user, roles=[schemas.AuthRoleRead(role=role, name=name)])


def test_super_admin_can_submit_claim_for_any_operator() -> None:
    with SessionLocal() as db:
        opportunity_id = seed_claim_task(db, "冯卓宏")
        auth = auth_context(db, "刘学城", "super_admin")
        payload = schemas.ClaimCreate(
            opportunity_id=opportunity_id,
            salesperson_name="冯卓宏",
            claim_result="claim",
            claim_daily_sales=1.5,
        )
        response = submit_claim_route(payload, db=db, auth=auth)
        assert response.id
        claim = db.query(models.SalesClaimForecast).one()
        assert claim.salesperson_name == "冯卓宏"


def test_operator_cannot_submit_claim_for_someone_else() -> None:
    with SessionLocal() as db:
        opportunity_id = seed_claim_task(db, "冯卓宏")
        auth = auth_context(db, "李桂敏", "operator")
        payload = schemas.ClaimCreate(
            opportunity_id=opportunity_id,
            salesperson_name="冯卓宏",
            claim_result="claim",
            claim_daily_sales=1.5,
        )
        with pytest.raises(HTTPException) as exc:
            submit_claim_route(payload, db=db, auth=auth)
        assert exc.value.status_code == 403


def test_claim_requires_daily_sales_when_claiming() -> None:
    response = client.post(
        "/claims",
        json={
            "opportunity_id": "missing",
            "salesperson_name": "销售A",
            "claim_result": "claim",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "claim_daily_sales must be greater than 0 when claim_result is claim"


def test_claim_requires_positive_daily_sales_when_claiming() -> None:
    response = client.post(
        "/claims",
        json={
            "opportunity_id": "missing",
            "salesperson_name": "销售A",
            "claim_result": "claim",
            "claim_daily_sales": 0,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "claim_daily_sales must be greater than 0 when claim_result is claim"


def test_reject_requires_nonblank_reason() -> None:
    response = client.post(
        "/claims",
        json={
            "opportunity_id": "missing",
            "salesperson_name": "销售A",
            "claim_result": "reject",
            "reject_reason": "   ",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "reject_reason is required when claim_result is reject"
