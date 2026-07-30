import os
import sys
import json
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)

SNAPSHOT = {
    "cells": {"A": "PH", "M": "规格A"},
    "fields_by_column": {"A": "PH", "M": "规格A"},
    "headers_by_column": {"A": ["站点"], "M": ["产品规格"]},
    "fields_by_header": {"站点": "PH", "产品规格": "规格A"},
}


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def add_opportunity() -> str:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            snapshot=SNAPSHOT,
        )
        db.add(opportunity)
        db.commit()
        return opportunity.id


def test_list_response_is_lightweight_without_snapshot() -> None:
    add_opportunity()

    rows = client.get("/opportunities").json()

    assert len(rows) == 1
    assert "snapshot" not in rows[0]
    assert rows[0]["main_sku"] == "MAIN-1"
    assert rows[0]["current_status"] == "pending_assignment"


def test_detail_endpoint_returns_full_snapshot() -> None:
    opportunity_id = add_opportunity()

    response = client.get(f"/opportunities/{opportunity_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == opportunity_id
    assert body["snapshot"] == SNAPSHOT
    assert body["main_sku"] == "MAIN-1"
    assert body["latest_claim_result"] is None


def test_detail_endpoint_returns_historical_claim_facts_without_replacing_platform_summary() -> None:
    opportunity_id = add_opportunity()
    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        assert opportunity is not None
        opportunity.batch = "开发0623期"
        opportunity.source_row = 184
        history_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="历史运营甲",
            claim_result="claim",
            claim_daily_sales=0.5,
            feedback_summary="历史调研结论",
            source_column="history_selection1",
            note=json.dumps(
                {
                    "history_source": {"business_period": "开发0526期", "source_row": 71, "claim_column": "BX"},
                    "evidence_images": [{"name": "history-proof.png", "url": "/uploaded-sources/claim-evidence/OPP/history-proof.png", "type": "image/png", "size": 123}],
                },
                ensure_ascii=False,
            ),
        )
        history_reject = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="历史运营乙",
            claim_result="reject",
            reject_reason="来源拒绝理由",
            feedback_summary="历史销售反馈",
            source_column="history_selection2",
        )
        platform_claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="当前运营",
            claim_result="claim",
            claim_daily_sales=3,
            source_column="platform",
        )
        db.add_all([history_claim, history_reject, platform_claim])
        db.commit()
        history_claim_id = history_claim.id
        platform_claim_id = platform_claim.id

    response = client.get(f"/opportunities/{opportunity_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_claim_record_id"] == platform_claim_id
    assert body["latest_claim_salesperson"] == "当前运营"
    facts = {item["salesperson_name"]: item for item in body["historical_claims"]}
    assert set(facts) == {"历史运营甲", "历史运营乙"}
    assert facts["历史运营甲"] == {
        "id": history_claim_id,
        "salesperson_name": "历史运营甲",
        "claim_result": "claim",
        "claim_daily_sales": 0.5,
        "reject_reason": None,
        "feedback_summary": "历史调研结论",
        "source_column": "history_selection1",
        "source_period": "开发0526期",
        "source_row": 71,
        "evidence_images": [{"name": "history-proof.png", "url": "/uploaded-sources/claim-evidence/OPP/history-proof.png", "type": "image/png", "size": 123}],
        "manager_review_status": None,
        "manager_review_comment": None,
    }
    assert facts["历史运营乙"]["claim_result"] == "reject"
    assert facts["历史运营乙"]["reject_reason"] == "来源拒绝理由"
    assert facts["历史运营乙"]["source_period"] == "开发0623期"


def test_detail_endpoint_missing_id_returns_404() -> None:
    add_opportunity()

    assert client.get("/opportunities/does-not-exist").status_code == 404
