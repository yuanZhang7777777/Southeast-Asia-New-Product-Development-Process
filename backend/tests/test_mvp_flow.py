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


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mvp_flow_and_notification_dedupe() -> None:
    import_response = client.post(
        "/opportunities/import",
        json={
            "items": [
                {
                    "source_type": "ph_site_sheet",
                    "source_file": "东南亚海外仓新品表-PH.xlsx",
                    "source_sheet": "新品",
                    "source_row": 2,
                    "country": "PH",
                    "site": "PH",
                    "main_sku": "MAIN-001",
                    "sub_sku": "SUB-001",
                    "keyword": "storage rack",
                    "snapshot": {"A": "MAIN-001", "B": "SUB-001"},
                },
                {
                    "source_type": "ph_site_sheet",
                    "source_file": "东南亚海外仓新品表-PH.xlsx",
                    "source_sheet": "新品",
                    "source_row": 3,
                    "country": "PH",
                    "site": "PH",
                    "main_sku": "MAIN-001",
                    "sub_sku": "SUB-002",
                    "keyword": "storage rack",
                    "snapshot": {"A": "MAIN-001", "B": "SUB-002"},
                },
            ]
        },
    )
    assert import_response.status_code == 200
    opportunity_ids = [item["id"] for item in import_response.json()]

    preview_response = client.post(
        "/assignments/preview",
        json={"opportunity_ids": opportunity_ids, "candidates": ["销售A", "销售B"]},
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["items"] == [
        {"main_sku": "MAIN-001", "sub_sku_count": 2, "suggested_assignee": "销售A"}
    ]

    confirm_response = client.post(
        "/assignments/confirm",
        json={"opportunity_ids": opportunity_ids, "assignee_name": "销售A"},
    )
    assert confirm_response.status_code == 200
    assert len(confirm_response.json()) == 2

    claim_response = client.post(
        "/claims",
        json={
            "opportunity_id": opportunity_ids[0],
            "salesperson_name": "销售A",
            "claim_result": "claim",
            "claim_daily_sales": 2,
            "feedback_summary": "可认领",
        },
    )
    assert claim_response.status_code == 200

    review_response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_ids[0],
            "reviewer_name": "主管A",
            "review_status": "approved",
            "review_comment": "通过",
        },
    )
    assert review_response.status_code == 200

    stocking_response = client.get("/stocking/requests")
    assert stocking_response.status_code == 200
    stocking_items = stocking_response.json()
    assert stocking_items[0]["daily_sales"] == 2
    assert stocking_items[0]["quantity"] == 60

    first_notice = client.post(
        "/notifications/test",
        json={"receiver_name": "销售A", "title": "测试提醒", "dedupe_key": "notice:claim:1"},
    )
    second_notice = client.post(
        "/notifications/test",
        json={"receiver_name": "销售A", "title": "测试提醒", "dedupe_key": "notice:claim:1"},
    )
    assert first_notice.status_code == 200
    assert second_notice.status_code == 200
    assert first_notice.json()["id"] == second_notice.json()["id"]
    assert len(client.get("/notifications/logs").json()) == 1
