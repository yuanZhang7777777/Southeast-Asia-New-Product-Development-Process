from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("/preview", response_model=schemas.AssignmentPreviewResponse)
def preview(payload: schemas.AssignmentPreviewRequest, db: Session = Depends(get_db)) -> schemas.AssignmentPreviewResponse:
    opportunities = list(
        db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(payload.opportunity_ids)))
    )
    return schemas.AssignmentPreviewResponse(items=services.preview_assignments(opportunities, payload.candidates))


@router.post("/confirm", response_model=list[schemas.TaskRead])
def confirm(payload: schemas.AssignmentConfirmRequest, db: Session = Depends(get_db)) -> list[models.FlowTask]:
    tasks = services.confirm_assignment(db, payload)
    db.commit()
    return tasks


@router.post("/reassign", response_model=schemas.TaskRead)
def reassign(payload: schemas.ReassignRequest, db: Session = Depends(get_db)) -> models.FlowTask:
    try:
        task = services.reassign_task(db, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return task
