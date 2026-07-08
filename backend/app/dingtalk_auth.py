from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from app.config import Settings
from app.dingtalk_card_sender import urllib_json_post

DINGTALK_USER_ACCESS_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"
DINGTALK_USER_INFO_URL = "https://api.dingtalk.com/v1.0/contact/users/me"

HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]
HttpGet = Callable[[str, dict[str, str]], dict[str, Any]]


def exchange_dingtalk_auth_code(
    auth_code: str,
    settings: Settings,
    http_post: HttpPost | None = None,
    http_get: HttpGet | None = None,
) -> str:
    code = auth_code.strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing DingTalk auth code")
    if not settings.dingtalk_client_id or not settings.dingtalk_client_secret:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="DingTalk auth_code exchange is not configured")

    post = http_post or urllib_json_post
    get = http_get or urllib_json_get
    try:
        token_body = post(
            DINGTALK_USER_ACCESS_TOKEN_URL,
            {"Content-Type": "application/json"},
            {
                "clientId": settings.dingtalk_client_id,
                "clientSecret": settings.dingtalk_client_secret,
                "code": code,
                "grantType": "authorization_code",
            },
        )
        user_id = extract_dingtalk_user_id(token_body)
        if user_id:
            return user_id
        access_token = token_body.get("accessToken") or token_body.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="DingTalk auth response did not include accessToken")
        user_body = get(DINGTALK_USER_INFO_URL, {"x-acs-dingtalk-access-token": str(access_token)})
        user_id = extract_dingtalk_user_id(user_body)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="DingTalk user response did not include userId")
        return user_id
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="DingTalk auth exchange failed") from exc


def extract_dingtalk_user_id(data: dict[str, Any]) -> str | None:
    for key in ("userId", "userid", "user_id", "unionId", "unionid", "union_id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = data.get("result")
    if isinstance(result, dict):
        return extract_dingtalk_user_id(result)
    return None


def urllib_json_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"DingTalk HTTP {exc.code}") from exc
    return json.loads(raw) if raw else {}
