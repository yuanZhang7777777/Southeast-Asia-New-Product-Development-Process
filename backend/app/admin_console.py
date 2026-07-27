from __future__ import annotations

import os

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import default_password_for_name, hash_password
from app.config import Settings
from app.services import audit

FEATURE_SWITCH_SETTINGS = (
    ("AUTH_REQUIRED", "auth_required"),
    ("DINGTALK_CARD_AUTOSEND_ENABLED", "dingtalk_card_autosend_enabled"),
    ("DINGTALK_USER_SYNC_ENABLED", "dingtalk_user_sync_enabled"),
    ("FINEBI_AUTO_PULL_ENABLED", "finebi_auto_pull_enabled"),
    ("PLM_SYNC_ENABLED", "plm_sync_enabled"),
    ("WORKFLOW_AUTOMATION_ENABLED", "workflow_automation_enabled"),
)


ROLE_OPTIONS = {"operator", "sales", "manager", "super_admin"}


def list_users(db: Session) -> list[schemas.AdminUserRead]:
    password_user_ids = set(db.scalars(select(models.UserPassword.user_id)))
    return [
        _user_read(user, password_user_ids)
        for user in db.scalars(select(models.User).order_by(models.User.created_at.asc()))
    ]


def user_read(db: Session, user: models.User) -> schemas.AdminUserRead:
    return _user_read(user, {user.id} if db.scalar(select(models.UserPassword.id).where(models.UserPassword.user_id == user.id)) else set())


def create_user(
    db: Session,
    payload: schemas.AdminUserCreateRequest,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.User:
    name = _required_name(payload.name)
    dingtalk_user_id = _optional_text(payload.dingtalk_user_id)
    role = _valid_role(payload.role)
    if db.scalar(select(models.User.id).where(models.User.name == name)):
        raise ValueError("账号姓名已存在")
    if dingtalk_user_id and db.scalar(select(models.User.id).where(models.User.dingtalk_user_id == dingtalk_user_id)):
        raise ValueError("钉钉 userId 已被其他账号使用")
    user = models.User(name=name, dingtalk_user_id=dingtalk_user_id, enabled=True)
    db.add(user)
    db.flush()
    password = payload.password or default_password_for_name(name)
    db.add(models.UserPassword(user_id=user.id, password_hash=hash_password(password)))
    db.add(models.RoleMapping(user_id=user.id, name=name, role=role, dingtalk_user_id=dingtalk_user_id, enabled=True))

    audit(db, "user.created", "user", user.id, {"role": role}, actor_name, actor_user_id)
    return user


def update_user(
    db: Session,
    user: models.User,
    payload: schemas.AdminUserUpdateRequest,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.User:
    values = payload.model_dump(exclude_unset=True)
    old_name = user.name
    new_name = _required_name(values.pop("name", user.name))
    new_dingtalk_user_id = _optional_text(values.pop("dingtalk_user_id", user.dingtalk_user_id))
    role = values.pop("role", None)
    if new_name != old_name and db.scalar(select(models.User.id).where(models.User.name == new_name, models.User.id != user.id)):
        raise ValueError("账号姓名已存在")
    if new_dingtalk_user_id and db.scalar(
        select(models.User.id).where(models.User.dingtalk_user_id == new_dingtalk_user_id, models.User.id != user.id)
    ):
        raise ValueError("钉钉 userId 已被其他账号使用")
    user.name = new_name
    user.dingtalk_user_id = new_dingtalk_user_id
    if "enabled" in values:
        user.enabled = bool(values["enabled"])
    mappings = list(
        db.scalars(
            select(models.RoleMapping).where(
                or_(models.RoleMapping.user_id == user.id, models.RoleMapping.name == old_name)
            )
        )
    )
    for mapping in mappings:
        mapping.user_id = user.id
        mapping.name = new_name
        mapping.dingtalk_user_id = new_dingtalk_user_id
    if role is not None:
        role = _valid_role(role)
        if mappings:
            mappings[0].role = role
        else:
            mapping = models.RoleMapping(user_id=user.id, name=new_name, role=role, dingtalk_user_id=new_dingtalk_user_id, enabled=True)
            db.add(mapping)
            mappings = [mapping]
    profile = db.scalar(select(models.OperatorAssignmentProfile).where(models.OperatorAssignmentProfile.operator_name == old_name))
    current_role = role or (mappings[0].role if mappings else None)
    if profile is not None:
        profile.operator_name = new_name
        if current_role != "operator" or not user.enabled:
            profile.enabled = False

    audit(db, "user.updated", "user", user.id, {"role": current_role, "enabled": user.enabled}, actor_name, actor_user_id)
    return user


def delete_user(
    db: Session,
    user: models.User,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> None:
    mappings = list(
        db.scalars(
            select(models.RoleMapping).where(
                or_(models.RoleMapping.user_id == user.id, models.RoleMapping.name == user.name)
            )
        )
    )
    for mapping in db.scalars(select(models.RoleMapping).where(models.RoleMapping.manager_user_id == user.id)):
        mapping.manager_user_id = None
    for mapping in mappings:
        db.delete(mapping)
    password = db.scalar(select(models.UserPassword).where(models.UserPassword.user_id == user.id))
    if password is not None:
        db.delete(password)
    profile = db.scalar(select(models.OperatorAssignmentProfile).where(models.OperatorAssignmentProfile.operator_name == user.name))
    if profile is not None:
        db.delete(profile)
    audit(db, "user.deleted", "user", user.id, {}, actor_name, actor_user_id)
    db.delete(user)


def _user_read(user: models.User, password_user_ids: set[str]) -> schemas.AdminUserRead:
    return schemas.AdminUserRead(
        id=user.id,
        dingtalk_user_id=user.dingtalk_user_id,
        name=user.name,
        enabled=user.enabled,
        has_password=user.id in password_user_ids,
    )


def _required_name(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    return name


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _valid_role(value: object) -> str:
    role = str(value or "").strip()
    if role not in ROLE_OPTIONS:
        raise ValueError("角色无效")
    return role



def reset_user_password(
    db: Session,
    user: models.User,
    new_password: str | None,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> schemas.AdminPasswordResetResponse:
    generated = new_password is None
    password_value = new_password or default_password_for_name(user.name)
    record = db.scalar(select(models.UserPassword).where(models.UserPassword.user_id == user.id))
    if record is None:
        record = models.UserPassword(user_id=user.id, password_hash="")
        db.add(record)
    record.password_hash = hash_password(password_value)
    audit(db, "user.password_reset", "user", user.id, {"generated": generated}, actor_name, actor_user_id)
    return schemas.AdminPasswordResetResponse(password=password_value, generated=generated)


def set_user_enabled(
    db: Session,
    user: models.User,
    enabled: bool,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.User:
    user.enabled = enabled
    audit(db, "user.enabled" if enabled else "user.disabled", "user", user.id, {}, actor_name, actor_user_id)
    return user


def update_role_mapping(
    db: Session,
    mapping: models.RoleMapping,
    values: dict[str, object],
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.RoleMapping:
    changed: dict[str, dict[str, object]] = {}
    for field in ("name", "role", "dingtalk_user_id", "group_name", "site", "manager_user_id", "enabled", "notification_enabled"):
        if field in values and getattr(mapping, field) != values[field]:
            changed[field] = {"from": getattr(mapping, field), "to": values[field]}
            setattr(mapping, field, values[field])
    if changed:
        audit(db, "role_mapping.updated", "role_mapping", mapping.id, changed, actor_name, actor_user_id)
    return mapping


def list_import_batches_page(
    db: Session,
    page: int,
    page_size: int,
    source_type: str | None = None,
    business_period: str | None = None,
    batch_status: str | None = None,
) -> schemas.ImportBatchPage:
    query = select(models.ImportBatch)
    if source_type:
        query = query.where(models.ImportBatch.source_type == source_type)
    if business_period:
        query = query.where(models.ImportBatch.business_period == business_period)
    if batch_status:
        query = query.where(models.ImportBatch.status == batch_status)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    items = list(
        db.scalars(
            query.order_by(models.ImportBatch.imported_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return schemas.ImportBatchPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.ImportBatchSummary.model_validate(item) for item in items],
    )


def feature_switches(settings: Settings) -> list[schemas.FeatureSwitchRead]:
    switches = [
        schemas.FeatureSwitchRead(name=name, enabled=bool(getattr(settings, attribute)))
        for name, attribute in FEATURE_SWITCH_SETTINGS
    ]
    switches.append(schemas.FeatureSwitchRead(name="OSS_UPLOAD_ENABLED", enabled=_oss_upload_enabled()))
    return sorted(switches, key=lambda item: item.name)


def _oss_upload_enabled() -> bool:
    return os.getenv("OSS_UPLOAD_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
