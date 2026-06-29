from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=list[schemas.OpportunityRead])
def list_opportunities(db: Session = Depends(get_db)) -> list[models.NewProductOpportunity]:
    return list(db.scalars(select(models.NewProductOpportunity).order_by(models.NewProductOpportunity.created_at.desc()).limit(200)))


@router.post("/import", response_model=list[schemas.OpportunityRead])
def import_opportunities(payload: schemas.OpportunityImportRequest, db: Session = Depends(get_db)) -> list[models.NewProductOpportunity]:
    items = [services.create_opportunity(db, item) for item in payload.items]
    db.commit()
    return items
