from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.config import Settings

DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID = "a428e864-5416-4ea6-ad29-36e19e0615e2.schema"
DINGTALK_ARRIVAL_CARD_TEMPLATE_ID = "a4053068-a70c-4ec8-a5b7-293d38a67a84.schema"
DINGTALK_ACCESS_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
DINGTALK_CREATE_AND_DELIVER_URL = "https://api.dingtalk.com/v1.0/card/instances/createAndDeliver"

HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class DingTalkCardConfig:
    client_id: str
    client_secret: str
    robot_code: str = ""
    search_icon: str = ""
    card_template_id: str = DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID
    arrival_card_template_id: str = DINGTALK_ARRIVAL_CARD_TEMPLATE_ID
    access_token_url: str = DINGTALK_ACCESS_TOKEN_URL
    create_and_deliver_url: str = DINGTALK_CREATE_AND_DELIVER_URL
    test_recipient_user_id: str = ""

    @classmethod
    def from_settings(cls, settings: Settings) -> "DingTalkCardConfig":
        return cls(
            client_id=settings.dingtalk_client_id,
            client_secret=settings.dingtalk_client_secret,
            robot_code=settings.dingtalk_robot_code or settings.dingtalk_client_id,
            arrival_card_template_id=(
                settings.dingtalk_arrival_card_template_id.strip() or DINGTALK_ARRIVAL_CARD_TEMPLATE_ID
            ),
            test_recipient_user_id=settings.dingtalk_test_recipient_user_id.strip(),
        )


@dataclass(frozen=True)
class NewProductTodoCard:
    receiver_dingtalk_user_id: str
    receiver_role: str
    left_count: int
    right_count: int
    action_url: str
    out_track_id: str
    subject_name: str = ""
    card_title: str = ""
    summary_text: str = ""
    left_label: str = ""
    right_label: str = ""
    tip_text: str = ""


@dataclass(frozen=True)
class ArrivalCardItem:
    main_sku: str
    child_sku_count: int
    product_name: str = ""


@dataclass(frozen=True)
class ArrivalCard:
    receiver_dingtalk_user_id: str
    arrival_date: str
    salesperson_name: str
    new_items: list[ArrivalCardItem]
    old_items: list[ArrivalCardItem]
    action_url: str
    out_track_id: str
    card_title: str = "到货通知"
    summary_text: str = ""
    left_label: str = "主SKU数"
    left_count: int | None = None
    action_text: str = "进入系统查看"
    sku_markdown: str | None = None


def build_new_product_todo_params(
    role: str,
    left_count: int,
    right_count: int,
    action_url: str,
    subject_name: str = "",
    card_title: str = "",
    summary_text: str = "",
    left_label: str = "",
    right_label: str = "",
    tip_text: str = "",
) -> dict[str, str]:
    total = left_count + right_count
    if role == "operator":
        default_title = f"{subject_name}的新品待办" if subject_name else "新品待办"
        params = {
            "card_title": default_title,
            "summary_text": f"你有 {total} 项新品事项待处理",
            "left_label": "待认领",
            "left_count": str(left_count),
            "right_label": "待补充",
            "right_count": str(right_count),
            "tip_text": "请处理待认领新品和退回补充事项",
            "action_text": "立即处理",
            "action_url": action_url,
        }
    elif role == "supervisor":
        params = {
            "card_title": "主管新品待办",
            "summary_text": f"你有 {total} 项主管事项待处理",
            "left_label": "认领待复核",
            "left_count": str(left_count),
            "right_label": "不认领待复核",
            "right_count": str(right_count),
            "tip_text": "请按小时汇总复核运营提交的认领和不认领",
            "action_text": "进入主管处理",
            "action_url": action_url,
        }
    else:
        raise ValueError("receiver_role must be operator or supervisor")
    overrides = {
        "card_title": card_title,
        "summary_text": summary_text,
        "left_label": left_label,
        "right_label": right_label,
        "tip_text": tip_text,
    }
    params.update({key: value for key, value in overrides.items() if value})
    return params


def build_arrival_card_params(
    arrival_date: str,
    salesperson_name: str,
    new_items: list[ArrivalCardItem],
    old_items: list[ArrivalCardItem],
    action_url: str,
    card_title: str = "到货通知",
    summary_text: str = "",
    left_label: str = "主SKU数",
    left_count: int | None = None,
    action_text: str = "进入系统查看",
    sku_markdown: str | None = None,
) -> dict[str, str]:
    total = len(new_items) + len(old_items)
    return {
        "card_title": card_title,
        "summary_text": summary_text or f"{arrival_date} 到货 {total} 个主 SKU",
        "left_label": left_label,
        "left_count": str(total if left_count is None else left_count),
        "sku_markdown": sku_markdown or arrival_card_sku_markdown(new_items, old_items),
        "action_text": action_text,
        "action_url": action_url,
    }


def arrival_card_sku_markdown(new_items: list[ArrivalCardItem], old_items: list[ArrivalCardItem]) -> str:
    sections = []
    if new_items:
        sections.append(_arrival_card_section("新品", new_items))
    if old_items:
        sections.append(_arrival_card_section("老品", old_items))
    return "\n\n".join(sections)


def _arrival_card_section(title: str, items: list[ArrivalCardItem]) -> str:
    lines = [f"**{title}**"]
    for index, item in enumerate(items, start=1):
        name = f"｜{item.product_name}" if item.product_name else ""
        lines.append(f"{index}. {item.main_sku}｜{item.child_sku_count} 个子 SKU{name}")
    return "\n".join(lines)


def masked_dingtalk_user_id(value: str | None) -> str:
    if not value or len(value) < 8:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


class DingTalkCardSender:
    def __init__(self, config: DingTalkCardConfig, http_post: HttpPost | None = None) -> None:
        self.config = config
        self.http_post = http_post or urllib_json_post

    def send_new_product_todo(self, card: NewProductTodoCard) -> dict[str, Any]:
        if card.left_count == 0 and card.right_count == 0:
            return {"skipped": True, "reason": "empty_counts"}
        if not self.config.client_id or not self.config.client_secret:
            raise ValueError("DingTalk client credentials are not configured")
        access_token = self.fetch_access_token()
        payload = self.build_create_and_deliver_payload(card)
        result = self.deliver(access_token, payload)
        return self._with_test_redirect(result, card.receiver_dingtalk_user_id, card.subject_name)

    def send_arrival_card(self, card: ArrivalCard) -> dict[str, Any]:
        if not card.new_items and not card.old_items and not card.sku_markdown:
            return {"skipped": True, "reason": "empty_items"}
        if not self.config.client_id or not self.config.client_secret:
            raise ValueError("DingTalk client credentials are not configured")
        access_token = self.fetch_access_token()
        payload = self.build_arrival_create_and_deliver_payload(card)
        result = self.deliver(access_token, payload)
        return self._with_test_redirect(result, card.receiver_dingtalk_user_id, card.salesperson_name)

    def deliver(self, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.http_post(
            self.config.create_and_deliver_url,
            {
                "x-acs-dingtalk-access-token": access_token,
                "Content-Type": "application/json",
            },
            payload,
        )

    def fetch_access_token(self) -> str:
        response = self.http_post(
            self.config.access_token_url,
            {"Content-Type": "application/json"},
            {"appKey": self.config.client_id, "appSecret": self.config.client_secret},
        )
        token = response.get("accessToken")
        if not token:
            raise ValueError("DingTalk access token response did not include accessToken")
        return str(token)

    def build_create_and_deliver_payload(self, card: NewProductTodoCard) -> dict[str, Any]:
        card_params = build_new_product_todo_params(
            role=card.receiver_role,
            left_count=card.left_count,
            right_count=card.right_count,
            action_url=card.action_url,
            subject_name=card.subject_name,
            card_title=card.card_title,
            summary_text=card.summary_text,
            left_label=card.left_label,
            right_label=card.right_label,
            tip_text=card.tip_text,
        )
        robot_code = self.config.robot_code or self.config.client_id
        last_message = card_params["summary_text"]
        search_desc = f'{card_params["card_title"]} {last_message}'[:200]
        return self._build_create_and_deliver_payload(
            receiver_dingtalk_user_id=card.receiver_dingtalk_user_id,
            card_template_id=self.config.card_template_id,
            out_track_id=card.out_track_id,
            card_params=card_params,
            last_message=last_message,
            search_desc=search_desc,
            robot_code=robot_code,
            original_receiver_label=card.subject_name,
        )

    def build_arrival_create_and_deliver_payload(self, card: ArrivalCard) -> dict[str, Any]:
        card_params = build_arrival_card_params(
            arrival_date=card.arrival_date,
            salesperson_name=card.salesperson_name,
            new_items=card.new_items,
            old_items=card.old_items,
            action_url=card.action_url,
            card_title=card.card_title,
            summary_text=card.summary_text,
            left_label=card.left_label,
            left_count=card.left_count,
            action_text=card.action_text,
            sku_markdown=card.sku_markdown,
        )
        last_message = card_params["summary_text"]
        return self._build_create_and_deliver_payload(
            receiver_dingtalk_user_id=card.receiver_dingtalk_user_id,
            card_template_id=self.config.arrival_card_template_id,
            out_track_id=card.out_track_id,
            card_params=card_params,
            last_message=last_message,
            search_desc=f'{card_params["card_title"]} {last_message}'[:200],
            robot_code=self.config.robot_code or self.config.client_id,
            original_receiver_label=card.salesperson_name,
        )

    def _test_redirect_meta(
        self,
        receiver_dingtalk_user_id: str,
        original_receiver_label: str = "",
    ) -> dict[str, str] | None:
        test_recipient = self.config.test_recipient_user_id.strip()
        if not test_recipient or test_recipient == receiver_dingtalk_user_id:
            return None
        return {
            "original_receiver": original_receiver_label or masked_dingtalk_user_id(receiver_dingtalk_user_id),
            "original_receiver_dingtalk_user_id": masked_dingtalk_user_id(receiver_dingtalk_user_id),
            "actual_receiver_dingtalk_user_id": masked_dingtalk_user_id(test_recipient),
        }

    def _with_test_redirect(
        self,
        result: dict[str, Any],
        receiver_dingtalk_user_id: str,
        original_receiver_label: str = "",
    ) -> dict[str, Any]:
        redirect = self._test_redirect_meta(receiver_dingtalk_user_id, original_receiver_label)
        if redirect is None:
            return result
        return {**result, "test_mode_redirect": redirect}

    def _build_create_and_deliver_payload(
        self,
        receiver_dingtalk_user_id: str,
        card_template_id: str,
        out_track_id: str,
        card_params: dict[str, Any],
        last_message: str,
        search_desc: str,
        robot_code: str,
        original_receiver_label: str = "",
    ) -> dict[str, Any]:
        redirect = self._test_redirect_meta(receiver_dingtalk_user_id, original_receiver_label)
        if redirect is not None:
            marker = f"（测试模式｜原收件人：{redirect['original_receiver']}）"
            card_params = {**card_params, "summary_text": f"{card_params.get('summary_text', '')}{marker}"}
            last_message = f"{last_message}{marker}"
            search_desc = f"{search_desc}{marker}"[:200]
            receiver_dingtalk_user_id = self.config.test_recipient_user_id.strip()
        return {
            "userId": receiver_dingtalk_user_id,
            "cardTemplateId": card_template_id,
            "outTrackId": out_track_id,
            "callbackType": "STREAM",
            "cardData": {"cardParamMap": stringify_card_param_map(card_params)},
            "openSpaceId": f"dtv1.card//im_robot.{receiver_dingtalk_user_id}",
            "imRobotOpenSpaceModel": {
                "supportForward": True,
                "lastMessageI18n": {"ZH_CN": last_message},
                "searchSupport": {"searchIcon": self.config.search_icon, "searchDesc": search_desc},
            },
            "imRobotOpenDeliverModel": {"spaceType": "IM_ROBOT", "robotCode": robot_code},
            "userIdType": 1,
        }


def stringify_card_param_map(values: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str):
            result[key] = value
            continue
        try:
            result[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            result[key] = ""
    return result


def urllib_json_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DingTalk HTTP {exc.code}: {raw}") from exc
    return json.loads(raw) if raw else {}
