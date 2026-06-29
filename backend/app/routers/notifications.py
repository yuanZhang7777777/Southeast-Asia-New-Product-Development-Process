from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/test", response_model=schemas.NotificationRead)
def test_notification(payload: schemas.NotificationTestRequest, db: Session = Depends(get_db)) -> models.NotificationLog:
    item = services.create_notification_log(db, payload)
    db.commit()
    db.refresh(item)
    return item


@router.get("/logs", response_model=list[schemas.NotificationRead])
def notification_logs(db: Session = Depends(get_db)) -> list[models.NotificationLog]:
    return list(db.scalars(select(models.NotificationLog).order_by(models.NotificationLog.created_at.desc()).limit(200)))
