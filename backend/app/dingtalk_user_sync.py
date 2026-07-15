from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings
from app.dingtalk_card_sender import urllib_json_post

ORG_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
DEPT_LIST_URL = "https://oapi.dingtalk.com/topapi/v2/department/listsub"
USER_LIST_URL = "https://oapi.dingtalk.com/topapi/v2/user/list"


def sync_configured_dingtalk_user_ids(db: Session, settings: Settings, write: bool = True) -> dict[str, Any]:
    token = fetch_access_token(settings.dingtalk_client_id, settings.dingtalk_client_secret)
    return sync_role_mapping_user_ids(db, list_dingtalk_users(token), write=write)


def sync_role_mapping_user_ids(
    db: Session, users: list[dict[str, Any]], write: bool = True, only_names: set[str] | None = None
) -> dict[str, Any]:
    mappings = list(
        db.scalars(
            select(models.RoleMapping)
            .where(models.RoleMapping.enabled.is_(True))
            .order_by(models.RoleMapping.name.asc(), models.RoleMapping.role.asc())
        )
    )
    if only_names:
        mappings = [item for item in mappings if item.name in only_names]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for user in users:
        by_name.setdefault(str(user.get("name") or "").strip(), []).append(user)

    matched = []
    missing = []
    ambiguous = []
    for mapping in mappings:
        candidates = by_name.get(mapping.name.strip(), [])
        if len(candidates) == 1:
            user_id = str(candidates[0].get("userid") or candidates[0].get("userId") or "")
            matched.append({"name": mapping.name, "role": mapping.role, "dingtalk_user_id": user_id})
            if write and user_id:
                mapping.dingtalk_user_id = user_id
            continue
        if candidates:
            ambiguous.append({"name": mapping.name, "role": mapping.role, "count": len(candidates)})
        else:
            missing.append({"name": mapping.name, "role": mapping.role})
    return {
        "total_dingtalk_users": len(users),
        "matched": matched,
        "missing": missing,
        "ambiguous": ambiguous,
    }


def fetch_access_token(client_id: str, client_secret: str) -> str:
    if not client_id or not client_secret:
        raise RuntimeError("DingTalk client credentials are not configured")
    response = urllib_json_post(
        ORG_TOKEN_URL,
        {"Content-Type": "application/json"},
        {"appKey": client_id, "appSecret": client_secret},
    )
    token = response.get("accessToken")
    if not token:
        raise RuntimeError("DingTalk access token response did not include accessToken")
    return str(token)


def list_dingtalk_users(access_token: str) -> list[dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    queue = [1]
    seen_depts: set[int] = set()
    while queue:
        dept_id = queue.pop(0)
        if dept_id in seen_depts:
            continue
        seen_depts.add(dept_id)
        for child in post_topapi(access_token, DEPT_LIST_URL, {"dept_id": dept_id}).get("result") or []:
            child_id = child.get("dept_id") or child.get("deptId")
            if child_id:
                queue.append(int(child_id))
        cursor = 0
        while True:
            result = post_topapi(
                access_token,
                USER_LIST_URL,
                {"dept_id": dept_id, "cursor": cursor, "size": 100, "language": "zh_CN"},
            ).get("result") or {}
            for user in result.get("list") or []:
                user_id = user.get("userid") or user.get("userId")
                if user_id:
                    users[str(user_id)] = user
            if not result.get("has_more"):
                break
            cursor = int(result.get("next_cursor") or 0)
    return list(users.values())


def post_topapi(access_token: str, url: str, body: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(3):
        request = Request(
            f"{url}?{urlencode({'access_token': access_token})}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        if payload.get("errcode") == 88 and attempt < 2:
            time.sleep(1)
            continue
        if payload.get("errcode") not in (None, 0):
            raise RuntimeError(f"DingTalk API error {payload.get('errcode')}: {payload.get('errmsg')}")
        return payload
    raise RuntimeError("DingTalk API request failed after retries")
