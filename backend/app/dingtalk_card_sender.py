from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.config import Settings

DINGTALK_NEW_PRODUCT_TODO_TEMPLATE_ID = "e335a9d6-72f9-495f-aafa-58cc7023d99a.schema"
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
    access_token_url: str = DINGTALK_ACCESS_TOKEN_URL
    create_and_deliver_url: str = DINGTALK_CREATE_AND_DELIVER_URL

    @classmethod
    def from_settings(cls, settings: Settings) -> "DingTalkCardConfig":
        return cls(
            client_id=settings.dingtalk_client_id,
            client_secret=settings.dingtalk_client_secret,
            robot_code=settings.dingtalk_robot_code or settings.dingtalk_client_id,
            card_template_id=settings.dingtalk_new_product_todo_card_template_id,
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


def build_new_product_todo_params(
    role: str,
    left_count: int,
    right_count: int,
    action_url: str,
    subject_name: str = "",
) -> dict[str, str]:
    total = left_count + right_count
    card_title = f"{subject_name}的新品待办" if subject_name else "新品待办"
    if role == "operator":
        return {
            "card_title": card_title,
            "summary_text": f"你有 {total} 项新品事项待处理",
            "left_label": "待认领",
            "left_count": str(left_count),
            "right_label": "待补充",
            "right_count": str(right_count),
            "tip_text": "请处理待认领新品和退回补充事项",
            "action_text": "立即处理",
            "action_url": action_url,
        }
    if role == "supervisor":
        return {
            "card_title": card_title,
            "summary_text": f"你有 {total} 项主管事项待处理",
            "left_label": "认领待复核",
            "left_count": str(left_count),
            "right_label": "不认领待复核",
            "right_count": str(right_count),
            "tip_text": "请按小时汇总复核运营提交的认领和不认领",
            "action_text": "进入主管处理",
            "action_url": action_url,
        }
    raise ValueError("receiver_role must be operator or supervisor")


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
        )
        robot_code = self.config.robot_code or self.config.client_id
        last_message = card_params["summary_text"]
        search_desc = f'{card_params["card_title"]} {last_message}'[:200]
        return {
            "userId": card.receiver_dingtalk_user_id,
            "cardTemplateId": self.config.card_template_id,
            "outTrackId": card.out_track_id,
            "callbackType": "STREAM",
            "cardData": {"cardParamMap": stringify_card_param_map(card_params)},
            "openSpaceId": f"dtv1.card//im_robot.{card.receiver_dingtalk_user_id}",
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
