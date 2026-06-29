from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/four-week", response_model=list[schemas.FourWeekSummaryRead])
def list_four_week_summaries(db: Session = Depends(get_db)) -> list[models.FourWeekSummary]:
    return list(db.scalars(select(models.FourWeekSummary).order_by(models.FourWeekSummary.created_at.desc()).limit(200)))


@router.post("/four-week", response_model=schemas.FourWeekSummaryRead)
def create_four_week_summary(payload: schemas.FourWeekSummaryCreate, db: Session = Depends(get_db)) -> models.FourWeekSummary:
    item = models.FourWeekSummary(**payload.model_dump())
    db.add(item)
    services.audit(db, "summary.four_week_created", "four_week_summary", item.id, payload.model_dump(), payload.summary_user)
    db.commit()
    db.refresh(item)
    return item
