from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import AuthContext, require_roles
from app.config import get_settings
from app.db import get_db
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender
from app.workflow_status import REVIEW_RETURNED_FOR_SUPPLEMENT

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(require_roles("manager"))])


@router.post("/bulk", response_model=schemas.MessageResponse)
def submit_bulk_review(
    payload: schemas.BulkReviewCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> schemas.MessageResponse:
    try:
        records = services.submit_bulk_reviews(
            db,
            payload,
            actor_name=auth.user.name if auth else None,
            actor_user_id=auth.user.id if auth else None,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    if payload.action == "reject":
        settings = get_settings()
        sender = DingTalkCardSender(DingTalkCardConfig.from_settings(settings))
        for record in records:
            claim = db.get(models.SalesClaimForecast, record.claim_record_id) if record.claim_record_id else None
            services.notify_operator_new_product_todo_card(
                db,
                claim.salesperson_name if claim else None,
                f"returned-{record.id}",
                settings,
                sender,
            )
    db.commit()
    return schemas.MessageResponse(message="bulk review submitted", id=str(len(records)))


@router.post("", response_model=schemas.MessageResponse)
def submit_review(
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> schemas.MessageResponse:
    try:
        record = services.submit_review(
            db,
            payload,
            actor_name=auth.user.name if auth else None,
            actor_user_id=auth.user.id if auth else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    if record.review_status == REVIEW_RETURNED_FOR_SUPPLEMENT:
        claim = db.get(models.SalesClaimForecast, record.claim_record_id) if record.claim_record_id else None
        settings = get_settings()
        services.notify_operator_new_product_todo_card(
            db,
            claim.salesperson_name if claim else None,
            f"returned-{record.id}",
            settings,
            DingTalkCardSender(DingTalkCardConfig.from_settings(settings)),
        )
    db.commit()
    return schemas.MessageResponse(message="review submitted", id=record.id)
