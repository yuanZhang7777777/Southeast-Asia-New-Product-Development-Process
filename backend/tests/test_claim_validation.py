import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


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
