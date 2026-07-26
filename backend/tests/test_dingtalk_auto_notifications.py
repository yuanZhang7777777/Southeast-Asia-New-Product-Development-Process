import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender  # noqa: E402
from app.main import app  # noqa: E402
from app.workflow_status import (  # noqa: E402
    CLAIM_RESULT_REJECT,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_CLAIM_SUBMITTED,
    OPPORTUNITY_DISABLED,
    OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
    REVIEW_RETURNED_FOR_SUPPLEMENT,
    TASK_PENDING,
)

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeSender:
    def __init__(self) -> None:
        self.cards = []

    def send_new_product_todo(self, card):
        self.cards.append(card)
        return {"ok": True}


def test_operator_auto_card_counts_pending_claim_main_sku_groups() -> None:
    sender = FakeSender()
    settings = Settings(dingtalk_card_autosend_enabled=True, dingtalk_card_test_receiver_name="", platform_base_url="https://np.example")
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-user-a", enabled=True))
        for main_sku, sub_sku in [("MAIN-1", "S1"), ("MAIN-1", "S2"), ("MAIN-2", "S3")]:
            opportunity = models.NewProductOpportunity(source_type="test", main_sku=main_sku, sub_sku=sub_sku)
            db.add(opportunity)
            db.flush()
            flow = models.FlowInstance(opportunity_id=opportunity.id, current_node="sales_claim", current_status="assigned")
            db.add(flow)
            db.flush()
            db.add(
                models.FlowTask(
                    flow_instance_id=flow.id,
                    node_code="sales_claim",
                    task_type="sales_claim",
                    assignee_name="销售A",
                    status=TASK_PENDING,
                )
            )
        for main_sku, sub_sku in [("RETURN-1", "R1"), ("RETURN-1", "R2"), ("RETURN-2", "R3")]:
            opportunity = models.NewProductOpportunity(
                source_type="test",
                main_sku=main_sku,
                sub_sku=sub_sku,
                current_status=OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
            )
            db.add(opportunity)
            db.flush()
            flow = models.FlowInstance(
                opportunity_id=opportunity.id,
                current_node="sales_claim",
                current_status=OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
            )
            db.add(flow)
            db.flush()
            db.add(
                models.FlowTask(
                    flow_instance_id=flow.id,
                    node_code="sales_claim",
                    task_type="sales_claim",
                    assignee_name="销售A",
                    status=TASK_PENDING,
                )
            )
        disabled = models.NewProductOpportunity(
            source_type="test",
            main_sku="DISABLED-1",
            sub_sku="D1",
            current_status=OPPORTUNITY_DISABLED,
        )
        db.add(disabled)
        db.flush()
        disabled_flow = models.FlowInstance(opportunity_id=disabled.id, current_node="sales_claim", current_status=OPPORTUNITY_DISABLED)
        db.add(disabled_flow)
        db.flush()
        db.add(
            models.FlowTask(
                flow_instance_id=disabled_flow.id,
                node_code="sales_claim",
                task_type="sales_claim",
                assignee_name="销售A",
                status=TASK_PENDING,
            )
        )
        db.flush()

        log = services.notify_operator_new_product_todo_card(db, "销售A", "assignment-test", settings, sender)

        assert log.send_status == "sent"
        assert sender.cards[0].receiver_dingtalk_user_id == "dt-user-a"
        assert sender.cards[0].receiver_role == "operator"
        assert sender.cards[0].left_count == 2
        assert sender.cards[0].right_count == 2
        assert sender.cards[0].action_url == "https://np.example/?from=ding&role=operator"


def test_supervisor_card_fans_out_to_real_supervisor_allowlist_even_with_test_receiver() -> None:
    sender = FakeSender()
    settings = Settings(dingtalk_card_autosend_enabled=True, dingtalk_card_test_receiver_name="刘学城", platform_base_url="https://np.example")
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="刘学城", role="super_admin", dingtalk_user_id="dt-liu", enabled=True),
                models.RoleMapping(name="徐成芬", role="manager", dingtalk_user_id="dt-xcf", enabled=True),
                models.RoleMapping(name="徐仔云", role="manager", dingtalk_user_id="dt-xzy", enabled=True),
                models.RoleMapping(name="罗艳娇", role="manager", dingtalk_user_id="dt-lyj", enabled=True),
                models.RoleMapping(name="闫歌", role="manager", dingtalk_user_id="dt-yg", enabled=True),
                models.RoleMapping(name="其他主管", role="manager", dingtalk_user_id="dt-other", enabled=True),
            ]
        )
        db.add(
            models.NewProductOpportunity(
                source_type="test",
                main_sku="MAIN-R",
                sub_sku="S1",
                current_status=OPPORTUNITY_CLAIM_REJECTED,
            )
        )
        db.add(models.NewProductOpportunity(source_type="test", main_sku="MAIN-C", sub_sku="S2", current_status=OPPORTUNITY_CLAIM_SUBMITTED))
        db.flush()

        log = services.notify_supervisor_new_product_todo_card(db, "not-claim-test", settings, sender)

        assert log.send_status == "sent"
        assert {card.receiver_dingtalk_user_id for card in sender.cards} == {"dt-liu", "dt-xcf", "dt-xzy", "dt-lyj", "dt-yg"}
        assert len(sender.cards) == 5
        assert all(card.receiver_role == "supervisor" for card in sender.cards)
        assert all(card.left_count == 1 for card in sender.cards)
    assert all(card.right_count == 1 for card in sender.cards)
    assert all(card.action_url == "https://np.example/?from=ding&role=supervisor" for card in sender.cards)


def test_card_test_receiver_redirects_operator_card_to_named_user() -> None:
    sender = FakeSender()
    settings = Settings(
        dingtalk_card_autosend_enabled=True,
        platform_base_url="https://np.example",
        dingtalk_card_test_receiver_name="刘学城",
    )
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-user-a", enabled=True))
        db.add(models.RoleMapping(name="刘学城", role="super_admin", dingtalk_user_id="dt-liu", enabled=True))
        db.flush()

        log = services.notify_operator_new_product_todo_card(db, "销售A", "test-receiver", settings, sender)

        assert log.receiver_name == "刘学城"
        assert sender.cards[0].receiver_dingtalk_user_id == "dt-liu"
        assert sender.cards[0].receiver_role == "operator"
        assert sender.cards[0].subject_name == "销售A"


def test_test_recipient_mode_audit_records_original_and_actual_receiver() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-test-mode"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", test_recipient_user_id="dt-test-owner"),
        http_post=fake_post,
    )
    with SessionLocal() as db:
        payload = schemas.DingTalkNewProductTodoCardRequest(
            receiver_dingtalk_user_id="dt-user-a",
            receiver_name="销售A",
            receiver_role="operator",
            subject_name="销售A",
            left_count=1,
            right_count=0,
            action_url="https://np.example/?from=ding&role=operator",
            out_track_id="test-mode-operator-1",
        )

        log = services.send_dingtalk_new_product_todo_card(db, payload, sender)

        assert log.send_status == "sent"
        assert log.receiver_name == "销售A"
        deliver_call = calls[1]
        assert deliver_call[2]["userId"] == "dt-test-owner"
        db.flush()
        sent_audit = db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_sent").one()
        redirect = sent_audit.detail["test_mode_redirect"]
        assert redirect["original_receiver"] == "销售A"
        assert redirect["original_receiver_dingtalk_user_id"] != redirect["actual_receiver_dingtalk_user_id"]


def test_sent_audit_has_no_redirect_detail_without_test_recipient() -> None:
    def fake_post(url: str, headers: dict, body: dict) -> dict:
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-normal"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret"),
        http_post=fake_post,
    )
    with SessionLocal() as db:
        payload = schemas.DingTalkNewProductTodoCardRequest(
            receiver_dingtalk_user_id="dt-user-a",
            receiver_name="销售A",
            receiver_role="operator",
            subject_name="销售A",
            left_count=1,
            right_count=0,
            action_url="https://np.example/?from=ding&role=operator",
            out_track_id="normal-operator-1",
        )

        log = services.send_dingtalk_new_product_todo_card(db, payload, sender)

        assert log.send_status == "sent"
        db.flush()
        sent_audit = db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_sent").one()
        assert "test_mode_redirect" not in sent_audit.detail


def test_claim_submission_does_not_trigger_supervisor_card_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(services, "notify_supervisor_new_product_todo_card", lambda *args, **kwargs: calls.append(args))
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN-N", sub_sku="S1")
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    response = client.post(
        "/claims",
        json={
            "opportunity_id": opportunity_id,
            "salesperson_name": "销售A",
            "claim_result": CLAIM_RESULT_REJECT,
            "reject_reason": "不适合",
        },
    )

    assert response.status_code == 200
    assert calls == []


def test_return_for_supplement_still_triggers_operator_card(monkeypatch: pytest.MonkeyPatch) -> None:
    operator_calls: list[object] = []
    supervisor_calls: list[object] = []
    monkeypatch.setattr(services, "notify_operator_new_product_todo_card", lambda *args, **kwargs: operator_calls.append(args))
    monkeypatch.setattr(services, "notify_supervisor_new_product_todo_card", lambda *args, **kwargs: supervisor_calls.append(args))
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN-R", sub_sku="S1")
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    first_response = client.post(
        "/claims",
        json={
            "opportunity_id": opportunity_id,
            "salesperson_name": "销售A",
            "claim_result": CLAIM_RESULT_REJECT,
            "reject_reason": "资料不足",
        },
    )
    assert first_response.status_code == 200
    review_response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "reviewer_name": "主管A",
            "review_status": REVIEW_RETURNED_FOR_SUPPLEMENT,
            "review_comment": "补充说明",
        },
    )
    assert review_response.status_code == 200

    second_response = client.post(
        "/claims",
        json={
            "opportunity_id": opportunity_id,
            "salesperson_name": "销售A",
            "claim_result": CLAIM_RESULT_REJECT,
            "reject_reason": "已补充资料",
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]
    assert supervisor_calls == []
    assert len(operator_calls) == 1
    assert operator_calls[0][1] == "销售A"
    assert str(operator_calls[0][2]).startswith("returned-")
