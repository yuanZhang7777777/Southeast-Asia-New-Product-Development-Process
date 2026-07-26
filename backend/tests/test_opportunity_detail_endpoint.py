import os
import sys
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


def test_detail_endpoint_missing_id_returns_404() -> None:
    add_opportunity()

    assert client.get("/opportunities/does-not-exist").status_code == 404
