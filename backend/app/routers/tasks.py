from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app import models, schemas, services
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
                    models.SalesClaimForecast.id.is_not(None),
                    models.FlowTask.completed_at.is_not(None),
                    ~exists(
                        select(models.ReviewRecord.id).where(
                            models.ReviewRecord.opportunity_id == models.NewProductOpportunity.id,
                            or_(
                                models.ReviewRecord.claim_record_id == models.SalesClaimForecast.id,
                                and_(
                                    models.ReviewRecord.claim_record_id.is_(None),
                                    models.ReviewRecord.created_at >= models.FlowTask.completed_at,
                                ),
                            ),
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
    tasks = list(db.scalars(query.distinct().order_by(models.FlowTask.created_at.desc()).limit(200)))
    for task in tasks:
        claim = db.scalar(
            select(models.SalesClaimForecast)
            .where(models.SalesClaimForecast.task_id == task.id)
            .order_by(models.SalesClaimForecast.last_updated_at.desc())
        )
        if claim is None and task.node_code == "returned_claim" and task.opportunity_id:
            claim = db.scalar(
                select(models.SalesClaimForecast)
                .where(
                    models.SalesClaimForecast.opportunity_id == task.opportunity_id,
                    models.SalesClaimForecast.salesperson_name == task.assignee_name,
                    models.SalesClaimForecast.source_column == "platform",
                )
                .order_by(models.SalesClaimForecast.last_updated_at.desc())
            )
        review = services.latest_review_for_claim(db, task.opportunity_id, claim) if task.opportunity_id and claim else None
        task.claim_record_id = claim.id if claim else None
        task.claim_result = claim.claim_result if claim else None
        task.claim_daily_sales = claim.claim_daily_sales if claim else None
        task.reject_reason = claim.reject_reason if claim else None
        task.feedback_summary = claim.feedback_summary if claim else None
        task.claim_note = claim.note if claim else None
        task.review_status = review.review_status if review else None
        task.review_comment = review.review_comment if review else None
    return tasks
