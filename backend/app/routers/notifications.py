from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import require_roles
from app.config import get_settings
from app.db import get_db
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender, build_new_product_todo_params

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_roles("manager"))])


@router.post("/test", response_model=schemas.NotificationRead)
def test_notification(payload: schemas.NotificationTestRequest, db: Session = Depends(get_db)) -> models.NotificationLog:
    item = services.create_notification_log(db, payload)
    db.commit()
    db.refresh(item)
    return item


@router.post("/dingtalk/new-product-todo-card", response_model=schemas.NotificationRead)
def send_dingtalk_new_product_todo_card(
    payload: schemas.DingTalkNewProductTodoCardRequest,
    db: Session = Depends(get_db),
) -> models.NotificationLog:
    sender = DingTalkCardSender(DingTalkCardConfig.from_settings(get_settings()))
    item = services.send_dingtalk_new_product_todo_card(db, payload, sender)
    db.commit()
    db.refresh(item)
    return item


@router.post("/dingtalk/new-product-todo-card/preview", response_model=schemas.DingTalkCardPreviewRead)
def preview_dingtalk_new_product_todo_card(payload: schemas.DingTalkCardPreviewRequest) -> schemas.DingTalkCardPreviewRead:
    return schemas.DingTalkCardPreviewRead(
        **payload.model_dump(),
        skipped=payload.left_count + payload.right_count == 0,
        params=build_new_product_todo_params(
            role=payload.receiver_role,
            left_count=payload.left_count,
            right_count=payload.right_count,
            action_url=payload.action_url,
            subject_name=payload.subject_name or "",
        ),
    )


@router.get("/logs", response_model=list[schemas.NotificationRead])
def notification_logs(db: Session = Depends(get_db)) -> list[models.NotificationLog]:
    return list(db.scalars(select(models.NotificationLog).order_by(models.NotificationLog.created_at.desc()).limit(200)))
