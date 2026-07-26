import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.dingtalk_card_sender import (
    DINGTALK_ARRIVAL_CARD_TEMPLATE_ID,
    DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID,
    ArrivalCard,
    ArrivalCardItem,
    DingTalkCardConfig,
    DingTalkCardSender,
    NewProductTodoCard,
    build_arrival_card_params,
    build_new_product_todo_params,
    masked_dingtalk_user_id,
)

CARD_TEMPLATE_ID_PATTERN = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.schema")


def test_repository_only_mentions_confirmed_card_templates() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed = {DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID, DINGTALK_ARRIVAL_CARD_TEMPLATE_ID}
    paths = [
        root / ".env.example",
        root / "backend",
        root / "deploy",
        root / "docker-compose.yml",
        root / "docs",
        root / "frontend",
    ]

    found: set[str] = set()
    for path in paths:
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if any(part in {".pytest_cache", "__pycache__", "node_modules", "dist"} for part in candidate.parts):
                continue
            if candidate.is_file() and candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".xlsx", ".docx", ".pyc"}:
                found.update(CARD_TEMPLATE_ID_PATTERN.findall(candidate.read_text(encoding="utf-8", errors="ignore")))

    assert found <= allowed


def test_from_settings_uses_confirmed_card_templates() -> None:
    config = DingTalkCardConfig.from_settings(Settings())

    assert config.card_template_id == DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID
    assert config.arrival_card_template_id == DINGTALK_ARRIVAL_CARD_TEMPLATE_ID


def test_from_settings_allows_current_arrival_template_override() -> None:
    config = DingTalkCardConfig.from_settings(
        Settings(dingtalk_arrival_card_template_id="current-arrival-template")
    )

    assert config.arrival_card_template_id == "current-arrival-template"


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

    assert params["card_title"] == "主管新品待办"
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


def test_arrival_card_params_group_new_and_old_sections() -> None:
    params = build_arrival_card_params(
        arrival_date="2026-07-12",
        salesperson_name="销售A",
        new_items=[ArrivalCardItem(main_sku="MAIN-1", child_sku_count=2, product_name="新品一")],
        old_items=[ArrivalCardItem(main_sku="MAIN-2", child_sku_count=1, product_name="老品二")],
        action_url="https://example.com/?from=ding&role=operator",
    )

    assert set(params) == {"card_title", "summary_text", "left_label", "left_count", "sku_markdown", "action_text", "action_url"}
    assert params["card_title"] == "到货通知"
    assert params["summary_text"] == "2026-07-12 到货 2 个主 SKU"
    assert params["left_label"] == "主SKU数"
    assert params["left_count"] == "2"
    assert "**新品**" in params["sku_markdown"]
    assert "MAIN-1｜2 个子 SKU｜新品一" in params["sku_markdown"]
    assert "**老品**" in params["sku_markdown"]
    assert "MAIN-2｜1 个子 SKU｜老品二" in params["sku_markdown"]


def test_sender_builds_arrival_card_with_confirmed_template() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "arrival-card-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", robot_code="robot-code"),
        http_post=fake_post,
    )

    result = sender.send_arrival_card(
        ArrivalCard(
            receiver_dingtalk_user_id="receiver-user-id",
            arrival_date="2026-07-12",
            salesperson_name="销售A",
            new_items=[ArrivalCardItem(main_sku="MAIN-1", child_sku_count=2, product_name="新品一")],
            old_items=[],
            action_url="https://example.com/?from=ding&role=operator",
            out_track_id="arrival-2026-07-12-sales-a",
        )
    )

    assert result["cardInstanceId"] == "arrival-card-1"
    deliver_call = calls[1]
    assert deliver_call[2]["cardTemplateId"] == DINGTALK_ARRIVAL_CARD_TEMPLATE_ID
    assert deliver_call[2]["cardData"]["cardParamMap"]["card_title"] == "到货通知"
    assert deliver_call[2]["cardData"]["cardParamMap"]["left_label"] == "主SKU数"
    assert "new_items" not in deliver_call[2]["cardData"]["cardParamMap"]


def test_from_settings_reads_test_recipient_user_id() -> None:
    config = DingTalkCardConfig.from_settings(Settings(dingtalk_test_recipient_user_id=" test-owner-user-id "))

    assert config.test_recipient_user_id == "test-owner-user-id"


def test_test_recipient_mode_redirects_todo_card_and_marks_summary() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(
            client_id="cid",
            client_secret="secret",
            robot_code="robot-code",
            test_recipient_user_id="test-owner-user-id",
        ),
        http_post=fake_post,
    )

    result = sender.send_new_product_todo(
        NewProductTodoCard(
            receiver_dingtalk_user_id="receiver-user-id",
            receiver_role="operator",
            left_count=1,
            right_count=2,
            action_url="https://example.com/mobile/tasks?from=ding&role=operator",
            out_track_id="new-product-todo-operator-20260726",
            subject_name="销售A",
        )
    )

    deliver_call = calls[1]
    assert deliver_call[2]["userId"] == "test-owner-user-id"
    assert deliver_call[2]["openSpaceId"] == "dtv1.card//im_robot.test-owner-user-id"
    marker = "（测试模式｜原收件人：销售A）"
    assert deliver_call[2]["cardData"]["cardParamMap"]["summary_text"].endswith(marker)
    assert deliver_call[2]["imRobotOpenSpaceModel"]["lastMessageI18n"]["ZH_CN"].endswith(marker)
    assert result["test_mode_redirect"] == {
        "original_receiver": "销售A",
        "original_receiver_dingtalk_user_id": masked_dingtalk_user_id("receiver-user-id"),
        "actual_receiver_dingtalk_user_id": masked_dingtalk_user_id("test-owner-user-id"),
    }


def test_test_recipient_mode_redirects_arrival_card() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "arrival-card-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", test_recipient_user_id="test-owner-user-id"),
        http_post=fake_post,
    )

    result = sender.send_arrival_card(
        ArrivalCard(
            receiver_dingtalk_user_id="receiver-user-id",
            arrival_date="2026-07-25",
            salesperson_name="销售A",
            new_items=[ArrivalCardItem(main_sku="MAIN-1", child_sku_count=2, product_name="新品一")],
            old_items=[],
            action_url="https://example.com/?from=ding&role=operator",
            out_track_id="arrival-2026-07-25-sales-a",
        )
    )

    deliver_call = calls[1]
    assert deliver_call[2]["userId"] == "test-owner-user-id"
    assert deliver_call[2]["openSpaceId"] == "dtv1.card//im_robot.test-owner-user-id"
    assert "（测试模式｜原收件人：销售A）" in deliver_call[2]["cardData"]["cardParamMap"]["summary_text"]
    assert result["test_mode_redirect"]["original_receiver"] == "销售A"


def test_empty_test_recipient_keeps_original_receiver_and_summary() -> None:
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", test_recipient_user_id="  "),
        http_post=fake_post,
    )

    result = sender.send_new_product_todo(
        NewProductTodoCard(
            receiver_dingtalk_user_id="receiver-user-id",
            receiver_role="operator",
            left_count=1,
            right_count=0,
            action_url="https://example.com/mobile/tasks?from=ding&role=operator",
            out_track_id="new-product-todo-operator-20260726",
            subject_name="销售A",
        )
    )

    deliver_call = calls[1]
    assert deliver_call[2]["userId"] == "receiver-user-id"
    assert deliver_call[2]["openSpaceId"] == "dtv1.card//im_robot.receiver-user-id"
    assert "测试模式" not in deliver_call[2]["cardData"]["cardParamMap"]["summary_text"]
    assert "test_mode_redirect" not in result


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
