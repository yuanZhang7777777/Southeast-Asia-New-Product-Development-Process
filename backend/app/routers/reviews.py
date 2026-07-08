from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas, services
from app.auth import AuthContext, require_roles
from app.config import get_settings
from app.db import get_db
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender
from app.workflow_status import REVIEW_RETURNED_FOR_SUPPLEMENT

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(require_roles("manager"))])


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
        claim = services.latest_platform_submission(db, record.opportunity_id)
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
