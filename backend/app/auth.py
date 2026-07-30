from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Iterable

from fastapi import Depends, HTTPException, Request, status
from pypinyin import Style, lazy_pinyin
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import Settings, get_settings
from app.db import get_db


@dataclass(frozen=True)
class AuthContext:
    user: models.User
    roles: list[schemas.AuthRoleRead]

    @property
    def role_keys(self) -> set[str]:
        return {role.role for role in self.roles}

    @property
    def operator_name(self) -> str | None:
        for role in self.roles:
            if role.role == "operator":
                return role.name
        if "super_admin" in self.role_keys:
            return self.user.name
        return None


def auth_required(settings: Settings) -> bool:
    return settings.auth_required or settings.app_env.strip().lower() not in {"local", "test", "testing"}


def normalize_role(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if text in {"super_admin", "superadmin", "admin", "超级管理员", "系统管理员"}:
        return "super_admin"
    if text in {"manager", "supervisor", "主管"}:
        return "manager"
    if text in {"operator", "sales", "运营", "销售", "组员", "组长"}:
        return "operator"
    return None


def roles_from_mappings(mappings: Iterable[models.RoleMapping]) -> list[schemas.AuthRoleRead]:
    roles: list[schemas.AuthRoleRead] = []
    seen: set[tuple[str, str]] = set()
    for mapping in mappings:
        role = normalize_role(mapping.role)
        if not role:
            continue
        key = (role, mapping.name)
        if key in seen:
            continue
        seen.add(key)
        roles.append(schemas.AuthRoleRead(role=role, name=mapping.name))
    return roles


def role_mappings_for_user(db: Session, user: models.User, settings: Settings) -> list[models.RoleMapping]:
    filters = [models.RoleMapping.user_id == user.id]
    if user.dingtalk_user_id:
        filters.append(models.RoleMapping.dingtalk_user_id == user.dingtalk_user_id)
    if settings.app_env.strip().lower() in {"local", "test", "testing"} or (user.dingtalk_user_id or "").startswith("account:"):
        filters.append(models.RoleMapping.name == user.name)
    return list(
        db.scalars(
            select(models.RoleMapping)
            .where(models.RoleMapping.enabled.is_(True), or_(*filters))
            .order_by(models.RoleMapping.created_at.asc())
        )
    )


def default_role(roles: list[schemas.AuthRoleRead]) -> str:
    if any(role.role == "super_admin" for role in roles):
        return "manager"
    if any(role.role == "manager" for role in roles):
        return "manager"
    return roles[0].role


def issue_token(settings: Settings, user: models.User, roles: list[schemas.AuthRoleRead]) -> str:
    now = int(time.time())
    payload = {
        "sub": user.id,
        "name": user.name,
        "roles": [role.model_dump() for role in roles],
        "iat": now,
        "exp": now + settings.auth_token_ttl_seconds,
    }
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    sig = _sign(settings, body)
    return f"{body}.{sig}"


def read_token(settings: Settings, token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    if not hmac.compare_digest(_sign(settings, body), sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    try:
        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    return payload


def get_current_auth(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext | None:
    header = request.headers.get("Authorization", "")
    if not header:
        if auth_required(settings):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization")
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization")
    payload = read_token(settings, token)
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user disabled or missing")
    roles = roles_from_mappings(role_mappings_for_user(db, user, settings))
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no enabled role")
    return AuthContext(user=user, roles=roles)


def require_roles(*allowed: str):
    allowed_set = set(allowed)

    def dependency(auth: AuthContext | None = Depends(get_current_auth), settings: Settings = Depends(get_settings)) -> AuthContext | None:
        if auth is None and not auth_required(settings):
            return None
        if auth is None or ("super_admin" not in auth.role_keys and auth.role_keys.isdisjoint(allowed_set)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return auth

    return dependency


def default_password_for_name(name: str) -> str:
    parts: list[str] = []
    for char in name.strip():
        if char.isascii() and char.isalnum():
            parts.append(char.lower())
            continue
        pinyin = lazy_pinyin(char, style=Style.FIRST_LETTER, errors="ignore")
        if pinyin:
            parts.append(pinyin[0].lower())
    initials = "".join(parts)
    return f"{initials}123456"


def hash_password(password: str) -> str:
    iterations = 260_000
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return hmac.compare_digest(digest, expected)


def _sign(settings: Settings, body: str) -> str:
    digest = hmac.new(settings.auth_secret_key.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return _b64(digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
