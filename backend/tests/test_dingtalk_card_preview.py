import os
import sys
from pathlib import Path

os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.dingtalk_card_sender import build_new_product_todo_params  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_dingtalk_card_preview_returns_same_params_as_real_card_builder() -> None:
    payload = {
        "receiver_role": "operator",
        "left_count": 3,
        "right_count": 1,
        "action_url": "http://127.0.0.1:5173/?from=ding&role=operator",
    }

    response = client.post("/notifications/dingtalk/new-product-todo-card/preview", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] is False
    assert body["params"] == build_new_product_todo_params(
        role=payload["receiver_role"],
        left_count=payload["left_count"],
        right_count=payload["right_count"],
        action_url=payload["action_url"],
    )


def test_dingtalk_card_preview_marks_zero_count_card_as_not_sent() -> None:
    response = client.post(
        "/notifications/dingtalk/new-product-todo-card/preview",
        json={
            "receiver_role": "supervisor",
            "left_count": 0,
            "right_count": 0,
            "action_url": "http://127.0.0.1:5173/?from=ding&role=supervisor",
        },
    )

    assert response.status_code == 200
    assert response.json()["skipped"] is True
