import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_personnel_config_imports_assignment_profiles(tmp_path: Path) -> None:
    workbook_path = tmp_path / "集团八部销售员信息表.xlsx"
    build_personnel_fixture(workbook_path)

    from app.personnel_importer import import_personnel_config

    with SessionLocal() as db:
        result = import_personnel_config(db, workbook_path)
        db.commit()
        profiles = db.query(models.OperatorAssignmentProfile).order_by(models.OperatorAssignmentProfile.operator_name).all()
        role_mappings = db.query(models.RoleMapping).order_by(models.RoleMapping.name).all()

    assert result == {"created_count": 2, "updated_count": 0, "skipped_count": 0}
    assert [
        (
            profile.operator_name,
            profile.role,
            profile.operator_level,
            profile.business_type,
            profile.key_site,
            profile.key_category1,
            profile.key_category2,
            profile.enabled,
        )
        for profile in profiles
    ] == [
        ("冯卓宏", "组员", "P1", "精品（海外仓）", "PH", "汽摩配", "家居厨卫", True),
        ("陈丽妹", "组员", "P1", "精品（海外仓）", "PH", "家居厨卫", "商办工业", True),
    ]
    assert [(item.name, item.role, item.enabled) for item in role_mappings] == [
        ("冯卓宏", "operator", True),
        ("陈丽妹", "operator", True),
    ]


def test_operator_profile_admin_crud_exposes_only_assignment_fields() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    create_response = client.post(
        "/admin/operator-profiles",
        json={
            "operator_name": "陈丽妹",
            "key_site": "PH",
            "key_category1": "家居厨卫",
            "key_category2": "商办工业",
            "enabled": True,
            "role": "组员",
            "operator_level": "P1",
            "business_type": "精品（海外仓）",
        },
    )

    assert create_response.status_code == 200
    body = create_response.json()
    assert set(body) == {"id", "operator_name", "key_site", "key_category1", "key_category2", "enabled"}
    assert body["operator_name"] == "陈丽妹"

    update_response = client.patch(
        f"/admin/operator-profiles/{body['id']}",
        json={"key_site": "TH", "key_category1": "汽摩配", "enabled": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["key_site"] == "TH"
    assert update_response.json()["enabled"] is False

    list_response = client.get("/admin/operator-profiles")
    assert list_response.status_code == 200
    assert list_response.json()[0]["key_category1"] == "汽摩配"

    delete_response = client.delete(f"/admin/operator-profiles/{body['id']}")
    assert delete_response.status_code == 204
    assert client.get("/admin/operator-profiles").json() == []


def build_personnel_fixture(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet.append(["销售员", "入职日期", "岗位", "运营分层", "业务类型", "重点站点", "重点品类1", "重点品类2"])
    worksheet.append(["陈丽妹", "2024-03-06", "组员", "P1", "精品（海外仓）", "PH", "家居厨卫", "商办工业"])
    worksheet.append(["冯卓宏", "2025-03-10", "组员", "P1", "精品（海外仓）", "PH", "汽摩配", "家居厨卫"])
    workbook.save(path)
