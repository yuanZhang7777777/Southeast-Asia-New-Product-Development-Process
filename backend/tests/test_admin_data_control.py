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


def test_super_admin_can_disable_and_restore_one_opportunity_without_losing_previous_status() -> None:
    with SessionLocal() as db:
        batch = add_batch(db)
        opportunity = add_opportunity(db, batch.id, "MAIN-ONE", "SUB-ONE", "assigned")
        db.commit()
        opportunity_id = opportunity.id

    disabled = client.post(
        f"/opportunities/{opportunity_id}/disable",
        json={"disabled": True, "reason": "wrong upload"},
    )
    hidden = client.get("/opportunities").json()
    visible_to_admin = client.get("/opportunities?include_disabled=true").json()

    assert disabled.status_code == 200
    assert hidden == []
    assert visible_to_admin[0]["current_status"] == "disabled"

    restored = client.post(
        f"/opportunities/{opportunity_id}/disable",
        json={"disabled": False, "reason": "restore"},
    )
    listed = client.get("/opportunities").json()

    assert restored.status_code == 200
    assert listed[0]["current_status"] == "assigned"


def test_super_admin_can_disable_and_restore_import_batch() -> None:
    with SessionLocal() as db:
        batch = add_batch(db)
        add_opportunity(db, batch.id, "MAIN-A", "SUB-A", "pending_assignment")
        add_opportunity(db, batch.id, "MAIN-B", "SUB-B", "ready_for_stocking")
        db.commit()
        batch_id = batch.id

    disabled = client.post(
        f"/opportunities/import-batches/{batch_id}/disable",
        json={"disabled": True, "reason": "bad period"},
    )
    batches_after_disable = client.get("/opportunities/import-batches").json()
    hidden = client.get("/opportunities").json()

    assert disabled.status_code == 200
    assert batches_after_disable[0]["status"] == "disabled"
    assert hidden == []

    restored = client.post(
        f"/opportunities/import-batches/{batch_id}/disable",
        json={"disabled": False, "reason": "restore period"},
    )
    batches_after_restore = client.get("/opportunities/import-batches").json()
    listed = client.get("/opportunities").json()

    assert restored.status_code == 200
    assert batches_after_restore[0]["status"] == "completed"
    assert {item["current_status"] for item in listed} == {"pending_assignment", "ready_for_stocking"}


def test_super_admin_group_disable_keeps_same_main_sku_other_site_active() -> None:
    with SessionLocal() as db:
        batch = add_batch(db)
        ph = add_opportunity(db, batch.id, "MAIN-SITE", "SUB-PH", "pending_assignment")
        ph.site = None
        ph.country = "PH"
        th = add_opportunity(db, batch.id, "MAIN-SITE", "SUB-TH", "pending_assignment")
        th.site = None
        th.country = "TH"
        db.commit()
        ph_id = ph.id

    response = client.post(
        f"/opportunities/{ph_id}/disable-group",
        json={"disabled": True, "reason": "bad PH only"},
    )
    visible_to_admin = client.get("/opportunities?include_disabled=true").json()

    assert response.status_code == 200
    assert {item["sub_sku"]: item["current_status"] for item in visible_to_admin} == {
        "SUB-PH": "disabled",
        "SUB-TH": "pending_assignment",
    }


def add_batch(db) -> models.ImportBatch:
    batch = models.ImportBatch(
        source_type="selection1_developer_claim_feedback",
        source_file="source.xlsx",
        source_sheet="2026W27",
        created_count=2,
        updated_count=0,
        skipped_count=0,
        status="completed",
    )
    db.add(batch)
    db.flush()
    return batch


def add_opportunity(db, batch_id: str, main_sku: str, sub_sku: str, status: str) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        import_batch_id=batch_id,
        source_type="selection1_developer_claim_feedback",
        source_file="source.xlsx",
        source_sheet="2026W27",
        source_row=sum(ord(char) for char in sub_sku),
        batch="2026W27",
        site="PH",
        country="PH",
        category_level1="Home",
        main_sku=main_sku,
        sub_sku=sub_sku,
        current_status=status,
    )
    db.add(opportunity)
    db.flush()
    return opportunity
