from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, selection1_importer, services
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


@router.post("/import/selection1", response_model=schemas.Selection1ImportResponse)
def import_selection1(
    payload: schemas.Selection1ImportRequest, db: Session = Depends(get_db)
) -> schemas.Selection1ImportResponse:
    try:
        result = selection1_importer.import_selection1_workbook(db, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result
