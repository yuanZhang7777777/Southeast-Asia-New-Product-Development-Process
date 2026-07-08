from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import (
    AuthContext,
    default_password_for_name,
    default_role,
    get_current_auth,
    hash_password,
    issue_token,
    role_mappings_for_user,
    roles_from_mappings,
    verify_password,
)
from app.config import Settings, get_settings, is_local_app_env
from app.db import get_db
from app.dingtalk_auth import exchange_dingtalk_auth_code

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.AuthLoginResponse)
def account_login(
    payload: schemas.AccountLoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> schemas.AuthLoginResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid account")
    mappings = list(
        db.scalars(
            select(models.RoleMapping)
            .where(models.RoleMapping.enabled.is_(True), models.RoleMapping.name == name)
            .order_by(models.RoleMapping.created_at.asc())
        )
    )
    roles = roles_from_mappings(mappings)
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not configured")

    user_key = f"account:{name}"
    user = db.scalar(select(models.User).where(models.User.dingtalk_user_id == user_key))
    if user is None:
        user = models.User(dingtalk_user_id=user_key, name=name)
        db.add(user)
        db.flush()
    if not user.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is disabled")

    password = db.scalar(select(models.UserPassword).where(models.UserPassword.user_id == user.id))
    if password is None:
        if payload.password != default_password_for_name(name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid account or password")
        db.add(models.UserPassword(user_id=user.id, password_hash=hash_password(payload.password)))
    elif not verify_password(payload.password, password.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid account or password")

    for mapping in mappings:
        if mapping.user_id is None:
            mapping.user_id = user.id
    db.commit()
    db.refresh(user)
    return auth_response(settings, user, roles)


@router.post("/dingtalk/login", response_model=schemas.AuthLoginResponse)
def dingtalk_login(
    payload: schemas.DingTalkLoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> schemas.AuthLoginResponse:
    dingtalk_user_id = resolve_dingtalk_user_id(payload, settings)
    user = db.scalar(select(models.User).where(models.User.dingtalk_user_id == dingtalk_user_id))
    if user is None:
        mapping = first_login_mapping(db, payload, dingtalk_user_id, settings)
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not configured")
        user = models.User(dingtalk_user_id=dingtalk_user_id, name=mapping.name or payload.name)
        db.add(user)
        db.flush()
        mapping.user_id = user.id
        if payload.dingtalk_user_id and not mapping.dingtalk_user_id:
            mapping.dingtalk_user_id = payload.dingtalk_user_id
    if not user.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is disabled")

    mappings = role_mappings_for_user(db, user, settings)
    roles = roles_from_mappings(mappings)
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no enabled role")
    db.commit()
    db.refresh(user)
    return auth_response(settings, user, roles)


@router.get("/me", response_model=schemas.AuthLoginResponse)
def me(auth: AuthContext = Depends(get_current_auth), settings: Settings = Depends(get_settings)) -> schemas.AuthLoginResponse:
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization")
    return auth_response(settings, auth.user, auth.roles)


@router.post("/password")
def change_password(
    payload: schemas.ChangePasswordRequest,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization")
    password = db.scalar(select(models.UserPassword).where(models.UserPassword.user_id == auth.user.id))
    if password is None:
        if payload.old_password != default_password_for_name(auth.user.name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid password")
        password = models.UserPassword(user_id=auth.user.id, password_hash="")
        db.add(password)
    elif not verify_password(payload.old_password, password.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid password")
    password.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


def resolve_dingtalk_user_id(payload: schemas.DingTalkLoginRequest, settings: Settings) -> str:
    if payload.dingtalk_user_id and is_local_app_env(settings.app_env):
        return payload.dingtalk_user_id
    if payload.auth_code:
        return exchange_dingtalk_auth_code(payload.auth_code, settings)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="DingTalk auth_code exchange is not configured")


def first_login_mapping(
    db: Session,
    payload: schemas.DingTalkLoginRequest,
    dingtalk_user_id: str,
    settings: Settings,
) -> models.RoleMapping | None:
    query = select(models.RoleMapping).where(models.RoleMapping.enabled.is_(True))
    query = query.where(models.RoleMapping.dingtalk_user_id == dingtalk_user_id)
    return db.scalar(query.order_by(models.RoleMapping.created_at.asc()))


def auth_response(settings: Settings, user: models.User, roles: list[schemas.AuthRoleRead]) -> schemas.AuthLoginResponse:
    role = default_role(roles)
    operator_name = next((item.name for item in roles if item.role == "operator"), None)
    return schemas.AuthLoginResponse(
        access_token=issue_token(settings, user, roles),
        user=user,
        roles=roles,
        default_role=role,
        operator_name=operator_name,
    )
