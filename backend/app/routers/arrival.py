from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/arrival", tags=["arrival"])


@router.get("/records", response_model=list[schemas.ArrivalRecordRead])
def list_arrival_records(db: Session = Depends(get_db)) -> list[models.ArrivalRecord]:
    return list(db.scalars(select(models.ArrivalRecord).order_by(models.ArrivalRecord.created_at.desc()).limit(200)))


@router.post("/records", response_model=schemas.ArrivalRecordRead)
def create_arrival_record(payload: schemas.ArrivalRecordCreate, db: Session = Depends(get_db)) -> models.ArrivalRecord:
    item = models.ArrivalRecord(**payload.model_dump())
    db.add(item)
    services.audit(db, "arrival.recorded", "arrival_record", item.id, payload.model_dump())
    db.commit()
    db.refresh(item)
    return item
