from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/my", response_model=list[schemas.TaskRead])
def my_tasks(assignee_name: str | None = None, db: Session = Depends(get_db)) -> list[models.FlowTask]:
    query = select(models.FlowTask).where(models.FlowTask.status == "pending")
    if assignee_name:
        query = query.where(models.FlowTask.assignee_name == assignee_name)
    return list(db.scalars(query.order_by(models.FlowTask.created_at.desc()).limit(200)))
