from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


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
