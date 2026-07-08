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


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_manager_can_edit_current_sku_fields_without_rewriting_source_snapshot() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="W27",
            source_row=1,
            batch="W27",
            main_sku="MAIN-OLD",
            sub_sku="SUB-OLD",
            main_sku_name="Old main",
            sub_sku_name="Old sub",
            snapshot={"fields_by_header": {"主SKU": "MAIN-OLD", "子SKU": "SUB-OLD"}},
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SourceRecordSnapshot(
                opportunity_id=opportunity.id,
                source_file=opportunity.source_file,
                source_sheet=opportunity.source_sheet,
                source_row=opportunity.source_row,
                column_range="source",
                payload=opportunity.snapshot,
            )
        )
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(
        f"/opportunities/{opportunity_id}",
        json={
            "main_sku": "MAIN-NEW",
            "sub_sku": "SUB-NEW",
            "main_sku_name": "New main",
            "sub_sku_name": "New sub",
            "edit_reason": "source correction",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["main_sku"] == "MAIN-NEW"
    assert body["sub_sku"] == "SUB-NEW"

    with SessionLocal() as db:
        snapshot = db.query(models.SourceRecordSnapshot).one()
        audit = db.query(models.AuditLog).filter_by(action="opportunity.updated").one()

    assert snapshot.payload["fields_by_header"] == {"主SKU": "MAIN-OLD", "子SKU": "SUB-OLD"}
    assert audit.detail["before"]["main_sku"] == "MAIN-OLD"
    assert audit.detail["after"]["main_sku"] == "MAIN-NEW"
    assert audit.detail["reason"] == "source correction"


def test_sku_edit_requires_reason() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN", sub_sku="SUB")
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(f"/opportunities/{opportunity_id}", json={"main_sku": "MAIN-NEW", "edit_reason": " "})

    assert response.status_code == 400
    assert "reason" in response.json()["detail"]
