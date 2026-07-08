from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import require_roles
from app.db import get_db

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("manager"))])


@router.get("/role-mappings", response_model=list[schemas.RoleMappingRead])
def role_mappings(db: Session = Depends(get_db)) -> list[models.RoleMapping]:
    return list(db.scalars(select(models.RoleMapping).order_by(models.RoleMapping.name)))


@router.post("/role-mappings", response_model=schemas.RoleMappingRead)
def create_role_mapping(payload: schemas.RoleMappingCreate, db: Session = Depends(get_db)) -> models.RoleMapping:
    item = models.RoleMapping(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/operator-profiles", response_model=list[schemas.OperatorAssignmentProfileRead])
def operator_profiles(db: Session = Depends(get_db)) -> list[models.OperatorAssignmentProfile]:
    return list(db.scalars(select(models.OperatorAssignmentProfile).order_by(models.OperatorAssignmentProfile.operator_name)))


@router.post("/operator-profiles", response_model=schemas.OperatorAssignmentProfileRead)
def upsert_operator_profile(
    payload: schemas.OperatorAssignmentProfileCreate, db: Session = Depends(get_db)
) -> models.OperatorAssignmentProfile:
    item = db.scalar(
        select(models.OperatorAssignmentProfile).where(
            models.OperatorAssignmentProfile.operator_name == payload.operator_name
        )
    )
    if item is None:
        item = models.OperatorAssignmentProfile(operator_name=payload.operator_name)
        db.add(item)
    _apply_operator_profile(item, payload.model_dump())
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


def _apply_operator_profile(item: models.OperatorAssignmentProfile, values: dict[str, object]) -> None:
    for field in ("operator_name", "key_site", "key_category1", "key_category2", "enabled"):
        if field in values:
            setattr(item, field, values[field])
