from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import require_roles
from app.config import Settings, get_settings
from app.db import get_db
from app.dingtalk_user_sync import sync_configured_dingtalk_user_ids

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("manager"))])


@router.get("/role-mappings", response_model=list[schemas.RoleMappingRead])
def role_mappings(db: Session = Depends(get_db)) -> list[models.RoleMapping]:
    return list(db.scalars(select(models.RoleMapping).order_by(models.RoleMapping.name)))


@router.post("/role-mappings", response_model=schemas.RoleMappingRead)
def create_role_mapping(
    payload: schemas.RoleMappingCreate,
    db: Session = Depends(get_db),
    _auth: object = Depends(require_roles("super_admin")),
) -> models.RoleMapping:
    item = models.RoleMapping(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/operator-profiles", response_model=list[schemas.OperatorAssignmentProfileRead])
def operator_profiles(db: Session = Depends(get_db)) -> list[models.OperatorAssignmentProfile]:
    return list(
        db.scalars(
            select(models.OperatorAssignmentProfile).order_by(
                models.OperatorAssignmentProfile.display_order,
                models.OperatorAssignmentProfile.created_at,
                models.OperatorAssignmentProfile.operator_name,
            )
        )
    )


@router.post("/operator-profiles", response_model=schemas.OperatorAssignmentProfileRead)
def upsert_operator_profile(
    payload: schemas.OperatorAssignmentProfileCreate, db: Session = Depends(get_db)
) -> models.OperatorAssignmentProfile:
    values = payload.model_dump()
    item = db.scalar(
        select(models.OperatorAssignmentProfile).where(
            models.OperatorAssignmentProfile.operator_name == payload.operator_name
        )
    )
    if item is None:
        item = models.OperatorAssignmentProfile(
            operator_name=payload.operator_name,
            display_order=values.pop("display_order") or _next_profile_order(db),
        )
        db.add(item)
    elif values.get("display_order") is None:
        values.pop("display_order")
    _apply_operator_profile(item, values)
    _upsert_operator_role_mapping(db, item.operator_name)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/operator-profiles/{profile_id}", response_model=schemas.OperatorAssignmentProfileRead)
def update_operator_profile(
    profile_id: str, payload: schemas.OperatorAssignmentProfileUpdate, db: Session = Depends(get_db)
) -> models.OperatorAssignmentProfile:
    item = db.get(models.OperatorAssignmentProfile, profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="operator profile not found")
    _apply_operator_profile(item, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(item)
    return item


@router.delete("/operator-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operator_profile(profile_id: str, db: Session = Depends(get_db)) -> Response:
    item = db.get(models.OperatorAssignmentProfile, profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="operator profile not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/dingtalk-user-ids/sync")
def sync_dingtalk_user_ids(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    report = sync_configured_dingtalk_user_ids(db, settings, write=True)
    db.commit()
    return {key: len(value) if isinstance(value, list) else value for key, value in report.items()}


def _apply_operator_profile(item: models.OperatorAssignmentProfile, values: dict[str, object]) -> None:
    for field in ("operator_name", "key_site", "key_category1", "key_category2", "assignment_priority", "display_order", "enabled"):
        if field in values:
            setattr(item, field, values[field])


def _next_profile_order(db: Session) -> int:
    return int(db.scalar(select(func.max(models.OperatorAssignmentProfile.display_order))) or 0) + 1


def _upsert_operator_role_mapping(db: Session, operator_name: str) -> None:
    mapping = db.scalar(
        select(models.RoleMapping).where(
            models.RoleMapping.name == operator_name,
            models.RoleMapping.role.in_(("operator", "sales")),
        )
    )
    if mapping is None:
        db.add(models.RoleMapping(name=operator_name, role="operator", enabled=True))
        return
    mapping.role = "operator"
    mapping.enabled = True
