from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import schemas, services
from app.auth import AuthContext, require_roles
from app.db import get_db

router = APIRouter(prefix="/product-board", tags=["product-board"])


@router.get("", response_model=list[schemas.ProductBoardGroupRead])
def list_product_board(
    owner: str | None = None,
    business_period: str | None = None,
    visible_status: str | None = None,
    arrival_date_from: date | None = Query(default=None),
    arrival_date_to: date | None = Query(default=None),
    site: str | None = None,
    query: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> list[dict]:
    if auth and "operator" in auth.role_keys and auth.role_keys.isdisjoint({"manager", "super_admin"}):
        owner = auth.operator_name
    return services.list_product_board_groups(
        db,
        owner=owner,
        business_period=business_period,
        visible_status=visible_status,
        arrival_date_from=arrival_date_from,
        arrival_date_to=arrival_date_to,
        site=site,
        query=query,
    )
