from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, or_, select
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
        .outerjoin(models.SalesClaimForecast, models.SalesClaimForecast.task_id == models.FlowTask.id)
        .where(
            models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
            or_(
                models.FlowTask.status == "pending",
                and_(
                    models.FlowTask.status == "completed",
                    models.FlowTask.task_type == "sales_claim",
                    models.NewProductOpportunity.current_status.in_({"claim_submitted", "claim_rejected"}),
                    models.SalesClaimForecast.id.is_not(None),
                    models.FlowTask.completed_at.is_not(None),
                    ~exists(
                        select(models.ReviewRecord.id).where(
                            models.ReviewRecord.opportunity_id == models.NewProductOpportunity.id,
                            models.ReviewRecord.created_at >= models.FlowTask.completed_at,
                        )
                    ),
                ),
            ),
        )
    )
    if auth and auth.role_keys.isdisjoint({"manager", "super_admin"}):
        assignee_name = auth.operator_name
    if assignee_name:
        query = query.where(models.FlowTask.assignee_name == assignee_name)
    return list(db.scalars(query.distinct().order_by(models.FlowTask.created_at.desc()).limit(200)))
