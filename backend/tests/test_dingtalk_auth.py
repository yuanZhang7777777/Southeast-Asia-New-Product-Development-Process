import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.dingtalk_auth import exchange_dingtalk_auth_code  # noqa: E402


def test_exchange_auth_code_fetches_dingtalk_user_id() -> None:
    post_calls = []
    get_calls = []

    def fake_post(url, headers, body):
        post_calls.append((url, headers, body))
        return {"accessToken": "user-token"}

    def fake_get(url, headers):
        get_calls.append((url, headers))
        return {"userId": "dt-a"}

    settings = Settings(dingtalk_client_id="client-id", dingtalk_client_secret="client-secret")

    user_id = exchange_dingtalk_auth_code("auth-code-a", settings, http_post=fake_post, http_get=fake_get)

    assert user_id == "dt-a"
    assert post_calls[0][2] == {
        "clientId": "client-id",
        "clientSecret": "client-secret",
        "code": "auth-code-a",
        "grantType": "authorization_code",
    }
    assert get_calls[0][1]["x-acs-dingtalk-access-token"] == "user-token"


def test_exchange_auth_code_requires_client_credentials() -> None:
    with pytest.raises(HTTPException) as exc:
        exchange_dingtalk_auth_code("auth-code-a", Settings(dingtalk_client_id="", dingtalk_client_secret=""))

    assert exc.value.status_code == 501
