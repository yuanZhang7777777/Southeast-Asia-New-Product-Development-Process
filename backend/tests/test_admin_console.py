import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def setup_function() -> None:
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["AUTH_SECRET_KEY"] = "test-auth-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    os.environ["AUTH_REQUIRED"] = "false"
    os.environ.pop("AUTH_SECRET_KEY", None)
    get_settings.cache_clear()


def test_non_super_admin_is_rejected_on_admin_console_endpoints() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="Manager A", role="manager", dingtalk_user_id="dt-manager", enabled=True),
                models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-operator", enabled=True),
            ]
        )
        mapping = models.RoleMapping(name="Operator B", role="operator", enabled=True)
        db.add(mapping)
        db.commit()
        mapping_id = mapping.id

    manager = auth_headers("dt-manager")
    operator = auth_headers("dt-operator")

    assert client.get("/admin/users", headers=manager).status_code == 403
    assert client.post("/admin/users/any-id/reset-password", headers=manager, json={}).status_code == 403
    assert client.patch("/admin/users/any-id", headers=manager, json={"enabled": False}).status_code == 403
    assert client.patch(f"/admin/role-mappings/{mapping_id}", headers=manager, json={"enabled": False}).status_code == 403
    assert client.post("/admin/import-batches/any-id/disable", headers=manager, json={"disabled": True}).status_code == 403
    assert client.get("/admin/feature-switches", headers=manager).status_code == 403
    assert client.get("/admin/import-batches", headers=manager).status_code == 200
    assert client.get("/admin/import-batches", headers=operator).status_code == 403


def test_super_admin_can_reset_password_to_custom_and_generated_default() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
                models.RoleMapping(name="销售A", role="operator", enabled=True),
            ]
        )
        db.commit()
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 200
    admin = auth_headers("dt-admin")
    user = find_user(admin, "销售A")
    assert user["has_password"] is True

    custom = client.post(f"/admin/users/{user['id']}/reset-password", headers=admin, json={"new_password": "custom-pass-9"})

    assert custom.status_code == 200
    assert custom.json()["generated"] is False
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 403
    assert client.post("/auth/login", json={"name": "销售A", "password": "custom-pass-9"}).status_code == 200

    generated = client.post(f"/admin/users/{user['id']}/reset-password", headers=admin, json={})

    assert generated.status_code == 200
    assert generated.json() == {"status": "ok", "password": "xsa123456", "generated": True}
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 200
    with SessionLocal() as db:
        audits = db.query(models.AuditLog).filter_by(action="user.password_reset").all()
    assert [entry.detail for entry in audits] == [{"generated": False}, {"generated": True}]
    assert all("custom-pass-9" not in json.dumps(entry.detail) for entry in audits)


def test_super_admin_can_disable_and_enable_user_but_not_self() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
                models.RoleMapping(name="销售A", role="operator", enabled=True),
            ]
        )
        db.commit()
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 200
    admin = auth_headers("dt-admin")
    user = find_user(admin, "销售A")

    disabled = client.patch(f"/admin/users/{user['id']}", headers=admin, json={"enabled": False})

    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 403

    enabled = client.patch(f"/admin/users/{user['id']}", headers=admin, json={"enabled": True})

    assert enabled.status_code == 200
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 200

    self_id = client.get("/auth/me", headers=admin).json()["user"]["id"]
    assert client.patch(f"/admin/users/{self_id}", headers=admin, json={"enabled": False}).status_code == 400


def test_super_admin_can_adjust_and_disable_role_mapping() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True))
        mapping = models.RoleMapping(name="销售A", role="operator", enabled=True)
        db.add(mapping)
        db.commit()
        mapping_id = mapping.id
    admin = auth_headers("dt-admin")

    promoted = client.patch(f"/admin/role-mappings/{mapping_id}", headers=admin, json={"role": "manager"})

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "manager"
    login = client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"})
    assert login.status_code == 200
    assert login.json()["default_role"] == "manager"

    revoked = client.patch(f"/admin/role-mappings/{mapping_id}", headers=admin, json={"enabled": False})

    assert revoked.status_code == 200
    assert client.post("/auth/login", json={"name": "销售A", "password": "xsa123456"}).status_code == 403
    with SessionLocal() as db:
        audits = db.query(models.AuditLog).filter_by(action="role_mapping.updated").all()
    assert len(audits) == 2


def test_admin_import_batches_are_paginated_and_filterable() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True))
        first = add_batch(db, "selection1_developer_claim_feedback", "2026W25", datetime(2026, 7, 1, tzinfo=timezone.utc))
        second = add_batch(db, "selection2_market_research", "2026W26", datetime(2026, 7, 2, tzinfo=timezone.utc))
        third = add_batch(db, "selection1_developer_claim_feedback", "2026W27", datetime(2026, 7, 3, tzinfo=timezone.utc))
        db.commit()
        first_id, second_id, third_id = first.id, second.id, third.id
    admin = auth_headers("dt-admin")

    page_one = client.get("/admin/import-batches?page=1&page_size=2", headers=admin).json()
    page_two = client.get("/admin/import-batches?page=2&page_size=2", headers=admin).json()
    filtered = client.get("/admin/import-batches?source_type=selection2_market_research", headers=admin).json()

    assert page_one["total"] == 3
    assert [item["id"] for item in page_one["items"]] == [third_id, second_id]
    assert [item["id"] for item in page_two["items"]] == [first_id]
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == second_id
    assert filtered["items"][0]["created_count"] == 2


def test_super_admin_can_disable_and_restore_import_batch_from_console() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True))
        batch = add_batch(db, "selection1_developer_claim_feedback", "2026W27", datetime(2026, 7, 3, tzinfo=timezone.utc))
        add_opportunity(db, batch.id, "MAIN-A", "SUB-A", "assigned")
        add_opportunity(db, batch.id, "MAIN-B", "SUB-B", "ready_for_stocking")
        db.commit()
        batch_id = batch.id
    admin = auth_headers("dt-admin")

    disabled = client.post(f"/admin/import-batches/{batch_id}/disable", headers=admin, json={"disabled": True, "reason": "bad period"})
    listed = client.get("/admin/import-batches", headers=admin).json()

    assert disabled.status_code == 200
    assert disabled.json() == {"message": "disabled", "id": "2"}
    assert listed["items"][0]["status"] == "disabled"
    with SessionLocal() as db:
        statuses = {item.sub_sku: item.current_status for item in db.query(models.NewProductOpportunity).all()}
    assert statuses == {"SUB-A": "disabled", "SUB-B": "disabled"}

    restored = client.post(f"/admin/import-batches/{batch_id}/disable", headers=admin, json={"disabled": False, "reason": "restore"})
    listed = client.get("/admin/import-batches", headers=admin).json()

    assert restored.status_code == 200
    assert listed["items"][0]["status"] == "completed"
    with SessionLocal() as db:
        statuses = {item.sub_sku: item.current_status for item in db.query(models.NewProductOpportunity).all()}
    assert statuses == {"SUB-A": "assigned", "SUB-B": "ready_for_stocking"}


def test_feature_switches_expose_only_switch_names_and_booleans() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True))
        db.commit()
    admin = auth_headers("dt-admin")

    response = client.get("/admin/feature-switches", headers=admin)

    assert response.status_code == 200
    switches = response.json()
    assert {item["name"] for item in switches} == {
        "AUTH_REQUIRED",
        "DINGTALK_CARD_AUTOSEND_ENABLED",
        "DINGTALK_USER_SYNC_ENABLED",
        "OSS_UPLOAD_ENABLED",
        "PLM_SYNC_ENABLED",
        "WORKFLOW_AUTOMATION_ENABLED",
    }
    assert all(set(item) == {"name", "enabled"} for item in switches)
    assert all(isinstance(item["enabled"], bool) for item in switches)
    assert next(item["enabled"] for item in switches if item["name"] == "AUTH_REQUIRED") is True
    assert next(item["enabled"] for item in switches if item["name"] == "OSS_UPLOAD_ENABLED") is False


def auth_headers(dingtalk_user_id: str) -> dict[str, str]:
    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": dingtalk_user_id})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def find_user(headers: dict[str, str], name: str) -> dict:
    users = client.get("/admin/users", headers=headers).json()
    return next(item for item in users if item["name"] == name)


def add_batch(db, source_type: str, business_period: str, imported_at: datetime) -> models.ImportBatch:
    batch = models.ImportBatch(
        source_type=source_type,
        source_file="source.xlsx",
        source_sheet=business_period,
        business_period=business_period,
        imported_at=imported_at,
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
