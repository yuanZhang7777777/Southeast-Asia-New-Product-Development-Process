from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import AuthContext, require_roles
from app.config import get_settings
from app.db import get_db
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender

router = APIRouter(prefix="/assignments", tags=["assignments"], dependencies=[Depends(require_roles("manager"))])


@router.post("/preview", response_model=schemas.AssignmentPreviewResponse)
def preview(payload: schemas.AssignmentPreviewRequest, db: Session = Depends(get_db)) -> schemas.AssignmentPreviewResponse:
    opportunities = list(
        db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(payload.opportunity_ids)))
    )
    profile_query = select(models.OperatorAssignmentProfile).where(models.OperatorAssignmentProfile.enabled.is_(True))
    if payload.candidates:
        profile_query = profile_query.where(models.OperatorAssignmentProfile.operator_name.in_(payload.candidates))
    profiles = list(db.scalars(profile_query))
    return schemas.AssignmentPreviewResponse(items=services.preview_assignments(opportunities, payload.candidates, profiles, db=db))


@router.get("/board", response_model=schemas.AssignmentBoardResponse)
def board(
    batch: str | None = None,
    assignee_name: str | None = None,
    db: Session = Depends(get_db),
) -> schemas.AssignmentBoardResponse:
    return services.list_assignment_board(db, batch=batch, assignee_name=assignee_name)


@router.post("/confirm", response_model=list[schemas.TaskRead])
def confirm(
    payload: schemas.AssignmentConfirmRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[models.FlowTask]:
    try:
        tasks = services.confirm_assignment(
            db,
            payload,
            actor_name=auth.user.name if auth else None,
            actor_user_id=auth.user.id if auth else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    if tasks:
        services.notify_operator_new_product_todo_card(
            db,
            payload.assignee_name,
            f"assignment-{tasks[0].id}",
            get_settings(),
            DingTalkCardSender(DingTalkCardConfig.from_settings(get_settings())),
        )
    db.commit()
    return tasks


@router.post("/reassign", response_model=schemas.TaskRead)
def reassign(
    payload: schemas.ReassignRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> models.FlowTask:
    try:
        task = services.reassign_task(
            db,
            payload,
            actor_name=auth.user.name if auth else None,
            actor_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    services.notify_operator_new_product_todo_card(
        db,
        payload.assignee_name,
        f"reassign-{task.id}",
        get_settings(),
        DingTalkCardSender(DingTalkCardConfig.from_settings(get_settings())),
    )
    db.commit()
    return task
