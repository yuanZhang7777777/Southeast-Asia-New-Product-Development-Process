from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import AuthContext, require_roles
from app.db import get_db
from app.workflow_status import OPPORTUNITY_DISABLED

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/my", response_model=list[schemas.TaskRead])
def my_tasks(
    assignee_name: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> list[models.FlowTask]:
    query = (
        select(models.FlowTask)
        .join(models.FlowInstance, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .join(models.NewProductOpportunity, models.FlowInstance.opportunity_id == models.NewProductOpportunity.id)
        .where(models.FlowTask.status == "pending", models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED)
    )
    if auth and auth.role_keys.isdisjoint({"manager", "super_admin"}):
        assignee_name = auth.operator_name
    if assignee_name:
        query = query.where(models.FlowTask.assignee_name == assignee_name)
    return list(db.scalars(query.order_by(models.FlowTask.created_at.desc()).limit(200)))
