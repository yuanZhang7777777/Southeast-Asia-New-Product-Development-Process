import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import claims  # noqa: E402
from app.routers.auth import resolve_dingtalk_user_id  # noqa: E402

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
    os.environ.pop("DINGTALK_CLIENT_ID", None)
    os.environ.pop("DINGTALK_CLIENT_SECRET", None)
    get_settings.cache_clear()


def test_login_requires_enabled_role_mapping() -> None:
    response = client.post(
        "/auth/login",
        json={"name": "未配置用户", "password": "wzpyh123456"},
    )

    assert response.status_code == 403


def test_only_super_admin_can_create_role_mapping() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="Manager A", role="manager", dingtalk_user_id="dt-manager", enabled=True),
                models.RoleMapping(name="Admin A", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
            ]
        )
        db.commit()

    manager_login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-manager"})
    admin_login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-admin"})
    payload = {"name": "New Admin", "role": "super_admin"}

    manager_response = client.post(
        "/admin/role-mappings",
        headers={"Authorization": f"Bearer {manager_login.json()['access_token']}"},
        json=payload,
    )
    admin_response = client.post(
        "/admin/role-mappings",
        headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        json=payload,
    )

    assert manager_response.status_code == 403
    assert admin_response.status_code == 200


def test_account_login_returns_token_and_current_user_roles() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        db.commit()

    login = client.post(
        "/auth/login",
        json={"name": "销售A", "password": "xsa123456"},
    )

    assert login.status_code == 200
    body = login.json()
    assert body["default_role"] == "operator"
    assert body["operator_name"] == "销售A"
    token = body["access_token"]
    current = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert current.status_code == 200
    assert current.json()["roles"] == [{"role": "operator", "name": "销售A"}]


def test_account_login_can_change_password() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="赵钰婷", role="operator", enabled=True))
        db.commit()

    login = client.post("/auth/login", json={"name": "赵钰婷", "password": "zyt123456"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    changed = client.post(
        "/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "zyt123456", "new_password": "newpass123"},
    )

    assert changed.status_code == 200
    assert client.post("/auth/login", json={"name": "赵钰婷", "password": "zyt123456"}).status_code == 403
    assert client.post("/auth/login", json={"name": "赵钰婷", "password": "newpass123"}).status_code == 200


def test_super_admin_role_can_call_manager_api_without_hardcoded_account() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="刘学城", role="super_admin", enabled=True))
        db.commit()

    login = client.post(
        "/auth/login",
        json={"name": "刘学城", "password": "lxc123456"},
    )

    assert login.status_code == 200
    body = login.json()
    assert body["default_role"] == "manager"
    assert body["roles"] == [{"role": "super_admin", "name": "刘学城"}]
    response = client.get("/admin/role-mappings", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 200


def test_first_version_supervisor_can_call_manager_api() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="练玉君", role="manager", enabled=True))
        db.commit()

    login = client.post("/auth/login", json={"name": "练玉君", "password": "lyj123456"})

    assert login.status_code == 200
    body = login.json()
    assert body["default_role"] == "manager"
    assert body["roles"] == [{"role": "manager", "name": "练玉君"}]
    response = client.get("/admin/role-mappings", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 200


def test_operator_token_cannot_call_manager_admin_api() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        db.commit()

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a", "name": "销售A"})
    token = login.json()["access_token"]
    response = client.get("/admin/role-mappings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_evidence_proxy_accepts_query_token_for_image_tags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(claims, "UPLOADED_SOURCES_ROOT", tmp_path)
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", enabled=True))
        db.commit()
    login = client.post("/auth/login", json={"name": "Operator A", "password": "operatora123456"})
    token = login.json()["access_token"]
    image_dir = tmp_path / "claim-evidence" / "OPP-1"
    image_dir.mkdir(parents=True)
    (image_dir / "proof.png").write_bytes(b"image-bytes")

    response = client.get(
        "/claims/evidence-images/proxy",
        params={"url": "/uploaded-sources/claim-evidence/OPP-1/proof.png", "token": token},
    )

    assert response.status_code == 200
    assert response.content == b"image-bytes"


def test_dingtalk_auth_code_login_maps_exchanged_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["DINGTALK_CLIENT_ID"] = "client-id"
    os.environ["DINGTALK_CLIENT_SECRET"] = "client-secret"
    get_settings.cache_clear()

    def fake_exchange(auth_code, settings):
        assert auth_code == "auth-code-a"
        assert settings.dingtalk_client_id == "client-id"
        return "dt-a"

    monkeypatch.setattr("app.routers.auth.exchange_dingtalk_auth_code", fake_exchange, raising=False)
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        db.commit()

    login = client.post("/auth/dingtalk/login", json={"auth_code": "auth-code-a"})

    assert login.status_code == 200
    body = login.json()
    assert body["default_role"] == "operator"
    assert body["operator_name"] == "Operator A"
    assert body["roles"] == [{"role": "operator", "name": "Operator A"}]


def test_dingtalk_auth_code_login_rejects_unmapped_user(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ["DINGTALK_CLIENT_ID"] = "client-id"
    os.environ["DINGTALK_CLIENT_SECRET"] = "client-secret"
    get_settings.cache_clear()

    monkeypatch.setattr("app.routers.auth.exchange_dingtalk_auth_code", lambda auth_code, settings: "dt-missing", raising=False)

    login = client.post("/auth/dingtalk/login", json={"auth_code": "auth-code-missing"})

    assert login.status_code == 403


def test_dingtalk_auth_code_login_requires_configured_exchange() -> None:
    os.environ["DINGTALK_CLIENT_ID"] = ""
    os.environ["DINGTALK_CLIENT_SECRET"] = ""
    get_settings.cache_clear()

    login = client.post("/auth/dingtalk/login", json={"auth_code": "auth-code-a"})

    assert login.status_code == 501


def test_production_dingtalk_login_does_not_trust_client_user_id() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://workflow:password@postgres:5432/workflow",
        auth_secret_key="production-secret",
    )

    with pytest.raises(HTTPException) as exc:
        resolve_dingtalk_user_id(schemas.DingTalkLoginRequest(dingtalk_user_id="dt-a"), settings)

    assert exc.value.status_code == 501


def test_operator_token_cannot_submit_claim_for_another_operator() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN-A", sub_sku="S1")
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a", "name": "销售A"})
    token = login.json()["access_token"]
    response = client.post(
        "/claims",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "opportunity_id": opportunity_id,
            "salesperson_name": "销售B",
            "claim_result": "claim",
            "claim_daily_sales": 1,
        },
    )

    assert response.status_code == 403


def test_protected_followup_routes_require_authentication() -> None:
    assert client.get("/arrival/records").status_code == 401
    assert client.post("/arrival/records", json={"opportunity_id": "missing"}).status_code == 401
    assert client.get("/summary/four-week").status_code == 401
    assert client.post("/summary/four-week", json={"opportunity_id": "missing"}).status_code == 401


def test_operator_token_cannot_submit_claim_with_another_operators_task_id() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        own = models.NewProductOpportunity(source_type="test", main_sku="OWN", sub_sku="S1")
        other = models.NewProductOpportunity(source_type="test", main_sku="OTHER", sub_sku="S1")
        db.add_all([own, other])
        db.flush()
        tasks = services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[other.id], assignee_name="Operator B"),
        )
        db.flush()
        task = tasks[0]
        db.commit()
        other_id = other.id
        other_task_id = task.id

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a", "name": "Operator A"})
    token = login.json()["access_token"]

    response = client.post(
        "/claims",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "opportunity_id": other_id,
            "task_id": other_task_id,
            "salesperson_name": "Operator A",
            "claim_result": "claim",
            "claim_daily_sales": 1,
        },
    )

    assert response.status_code == 403


def test_operator_token_only_lists_own_opportunities_and_tasks() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        db.add(models.RoleMapping(name="Manager A", role="manager", dingtalk_user_id="dt-m", enabled=True))
        own = models.NewProductOpportunity(source_type="test", main_sku="OWN", sub_sku="S1")
        other = models.NewProductOpportunity(source_type="test", main_sku="OTHER", sub_sku="S1")
        unassigned = models.NewProductOpportunity(source_type="test", main_sku="UNASSIGNED", sub_sku="S1")
        db.add_all([own, other, unassigned])
        db.flush()
        own_flow = models.FlowInstance(opportunity_id=own.id)
        other_flow = models.FlowInstance(opportunity_id=other.id)
        db.add_all([own_flow, other_flow])
        db.flush()
        db.add_all(
            [
                models.FlowTask(flow_instance_id=own_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator A"),
                models.FlowTask(flow_instance_id=other_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator B"),
            ]
        )
        db.commit()

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a"})
    token = login.json()["access_token"]

    opportunities = client.get("/opportunities", headers={"Authorization": f"Bearer {token}"}).json()
    tasks = client.get("/tasks/my?assignee_name=Operator B", headers={"Authorization": f"Bearer {token}"}).json()

    assert [item["main_sku"] for item in opportunities] == ["OWN"]
    assert [item["assignee_name"] for item in tasks] == ["Operator A"]

    manager_login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-m"})
    manager_token = manager_login.json()["access_token"]
    manager_opportunities = client.get("/opportunities", headers={"Authorization": f"Bearer {manager_token}"}).json()

    assert {item["main_sku"] for item in manager_opportunities} == {"OWN", "OTHER", "UNASSIGNED"}


def test_tasks_endpoint_hides_disabled_opportunity_tasks() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        active = models.NewProductOpportunity(source_type="test", main_sku="ACTIVE", sub_sku="S1", current_status="assigned")
        disabled = models.NewProductOpportunity(source_type="test", main_sku="DISABLED", sub_sku="S1", current_status="disabled")
        db.add_all([active, disabled])
        db.flush()
        active_flow = models.FlowInstance(opportunity_id=active.id)
        disabled_flow = models.FlowInstance(opportunity_id=disabled.id)
        db.add_all([active_flow, disabled_flow])
        db.flush()
        db.add_all(
            [
                models.FlowTask(flow_instance_id=active_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator A"),
                models.FlowTask(flow_instance_id=disabled_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator A"),
            ]
        )
        active_id = active.id
        db.commit()

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a"})
    token = login.json()["access_token"]

    tasks = client.get("/tasks/my", headers={"Authorization": f"Bearer {token}"}).json()

    assert [item["opportunity_id"] for item in tasks] == [active_id]


def test_super_admin_operator_can_filter_tasks_for_selected_operator() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="Admin", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
                models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-admin", enabled=True),
            ]
        )
        own = models.NewProductOpportunity(source_type="test", main_sku="OWN", sub_sku="S1")
        other = models.NewProductOpportunity(source_type="test", main_sku="OTHER", sub_sku="S1")
        db.add_all([own, other])
        db.flush()
        own_flow = models.FlowInstance(opportunity_id=own.id)
        other_flow = models.FlowInstance(opportunity_id=other.id)
        db.add_all([own_flow, other_flow])
        db.flush()
        db.add_all(
            [
                models.FlowTask(flow_instance_id=own_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator A"),
                models.FlowTask(flow_instance_id=other_flow.id, task_type="sales_claim", node_code="sales_claim", assignee_name="Operator B"),
            ]
        )
        db.commit()

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-admin"})
    token = login.json()["access_token"]

    tasks = client.get("/tasks/my?assignee_name=Operator B", headers={"Authorization": f"Bearer {token}"}).json()

    assert [item["assignee_name"] for item in tasks] == ["Operator B"]


def test_review_uses_authenticated_manager_as_actor() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Manager A", role="manager", dingtalk_user_id="dt-m", enabled=True))
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN-AUTH", sub_sku="SUB-AUTH")
        db.add(opportunity)
        db.flush()
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="Operator A",
                claim_result="claim",
                claim_daily_sales=1,
            ),
        )
        db.commit()
        opportunity_id = opportunity.id

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-m"})
    token = login.json()["access_token"]
    response = client.post(
        "/reviews",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "Spoofed Manager",
            "review_status": "approved",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        review = db.query(models.ReviewRecord).one()
        audit = db.query(models.AuditLog).filter_by(action="review.submitted").one()

    assert review.reviewer_name == "Manager A"
    assert audit.actor_name == "Manager A"


def test_operator_evidence_upload_requires_owned_opportunity() -> None:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="Operator A", role="operator", dingtalk_user_id="dt-a", enabled=True))
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN-EVIDENCE", sub_sku="SUB-EVIDENCE")
        db.add(opportunity)
        db.flush()
        services.confirm_assignment(
            db,
            schemas.AssignmentConfirmRequest(opportunity_ids=[opportunity.id], assignee_name="Operator B"),
        )
        db.commit()
        opportunity_id = opportunity.id

    login = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": "dt-a"})
    token = login.json()["access_token"]
    response = client.post(
        "/claims/evidence-images",
        headers={"Authorization": f"Bearer {token}"},
        data={"opportunity_id": opportunity_id},
        files={"file": ("proof.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 403
