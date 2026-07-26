from __future__ import annotations

import os

from sqlalchemy import func, select
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


def list_users(db: Session) -> list[schemas.AdminUserRead]:
    users = list(db.scalars(select(models.User).order_by(models.User.created_at.asc())))
    password_user_ids = set(db.scalars(select(models.UserPassword.user_id)))
    return [
        schemas.AdminUserRead(
            id=user.id,
            dingtalk_user_id=user.dingtalk_user_id,
            name=user.name,
            enabled=user.enabled,
            has_password=user.id in password_user_ids,
        )
        for user in users
    ]


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
    for field in ("name", "role", "dingtalk_user_id", "group_name", "site", "manager_user_id", "enabled"):
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
