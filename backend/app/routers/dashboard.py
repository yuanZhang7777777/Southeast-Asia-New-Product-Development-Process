from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas, services
from app.auth import AuthContext, require_roles
from app.db import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def dashboard_counts_owner(auth: AuthContext | None, requested_owner: str | None) -> str | None:
    if auth is None or auth.role_keys.intersection({"manager", "super_admin"}):
        return requested_owner
    return auth.operator_name


@router.get("/counts", response_model=schemas.DashboardCountsRead)
def dashboard_counts(
    salesperson_name: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    owner = dashboard_counts_owner(auth, salesperson_name)
    return {
        "waiting_listing": services.count_waiting_listing_groups(db, owner),
        "waiting_secondary_research": services.count_waiting_secondary_research_claims(db, owner),
        "pending_review_periods": services.count_pending_review_observation_periods(db, owner),
        "pending_claim_reviews": services.count_pending_claim_reviews(db),
        "pending_not_claim_reviews": services.count_pending_not_claim_reviews(db),
    }
