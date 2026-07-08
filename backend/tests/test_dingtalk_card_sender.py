import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dingtalk_card_sender import (
    DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID,
    DingTalkCardConfig,
    DingTalkCardSender,
    NewProductTodoCard,
    build_new_product_todo_params,
    masked_dingtalk_user_id,
)


def test_operator_card_uses_confirmed_template_and_labels() -> None:
    params = build_new_product_todo_params(
        role="operator",
        left_count=12,
        right_count=5,
        action_url="https://example.com/mobile/tasks?from=ding&role=operator",
        subject_name="销售A",
    )

    assert params == {
        "card_title": "销售A的新品待办",
        "summary_text": "你有 17 项新品事项待处理",
        "left_label": "待认领",
        "left_count": "12",
        "right_label": "待补充",
        "right_count": "5",
        "tip_text": "请处理待认领新品和退回补充事项",
        "action_text": "立即处理",
        "action_url": "https://example.com/mobile/tasks?from=ding&role=operator",
    }


def test_supervisor_card_uses_confirmed_template_and_labels() -> None:
    params = build_new_product_todo_params(
        role="supervisor",
        left_count=5,
        right_count=2,
        action_url="https://example.com/mobile/tasks?from=ding&role=supervisor",
        subject_name="练玉君",
    )

    assert params["card_title"] == "练玉君的新品待办"
    assert params["summary_text"] == "你有 7 项主管事项待处理"
    assert params["left_label"] == "认领待复核"
    assert params["right_label"] == "不认领待复核"
    assert params["action_text"] == "进入主管处理"


def test_sender_skips_zero_count_card_without_http_calls() -> None:
    calls: list[tuple[str, dict, dict]] = []
    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret"),
        http_post=lambda url, headers, body: calls.append((url, headers, body)) or {},
    )

    result = sender.send_new_product_todo(
        NewProductTodoCard(
            receiver_dingtalk_user_id="user-private-id",
            receiver_role="operator",
            left_count=0,
            right_count=0,
            action_url="https://example.com/mobile/tasks?from=ding",
            out_track_id="new-product-todo-operator-20260704",
        )
    )

    assert result == {"skipped": True, "reason": "empty_counts"}
    assert calls == []


def test_sender_builds_create_and_deliver_payload() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"deliverResults": [{"success": True}], "cardInstanceId": "card-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", robot_code="robot-code"),
        http_post=fake_post,
    )

    result = sender.send_new_product_todo(
        NewProductTodoCard(
            receiver_dingtalk_user_id="receiver-user-id",
            receiver_role="operator",
            left_count=1,
            right_count=2,
            action_url="https://example.com/mobile/tasks?from=ding&role=operator",
            out_track_id="new-product-todo-operator-20260704",
            subject_name="销售A",
        )
    )

    assert result["cardInstanceId"] == "card-1"
    token_call, deliver_call = calls
    assert token_call[2] == {"appKey": "cid", "appSecret": "secret"}
    assert deliver_call[1]["x-acs-dingtalk-access-token"] == "token-value"
    assert deliver_call[2]["cardTemplateId"] == DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID
    assert deliver_call[2]["callbackType"] == "STREAM"
    assert deliver_call[2]["openSpaceId"] == "dtv1.card//im_robot.receiver-user-id"
    assert deliver_call[2]["imRobotOpenDeliverModel"] == {"spaceType": "IM_ROBOT", "robotCode": "robot-code"}
    assert deliver_call[2]["imRobotOpenSpaceModel"]["lastMessageI18n"]["ZH_CN"]
    assert deliver_call[2]["imRobotOpenSpaceModel"]["searchSupport"]["searchDesc"]
    assert deliver_call[2]["cardData"]["cardParamMap"]["card_title"] == "销售A的新品待办"
    assert deliver_call[2]["cardData"]["cardParamMap"]["left_label"] == "待认领"
    assert "sys_full_json_obj" not in deliver_call[2]["cardData"]["cardParamMap"]
    assert deliver_call[2]["userIdType"] == 1
    assert json.dumps(deliver_call[2], ensure_ascii=False).find("secret") == -1


def test_masked_dingtalk_user_id_never_returns_full_value() -> None:
    assert masked_dingtalk_user_id("abcdef123456") == "abc***456"
    assert masked_dingtalk_user_id("short") == "***"


def test_unknown_card_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="receiver_role"):
        build_new_product_todo_params(
            role="manager",
            left_count=1,
            right_count=0,
            action_url="https://example.com/mobile/tasks?from=ding",
        )
