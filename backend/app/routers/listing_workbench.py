from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas, services
from app.auth import AuthContext, require_roles
from app.db import get_db


router = APIRouter(prefix="/listing-workbench", tags=["listing-workbench"])


def manager_access(auth: AuthContext | None) -> bool:
    return auth is None or not auth.role_keys.isdisjoint({"manager", "super_admin"})


@router.get("", response_model=schemas.ListingWorkbenchRead)
def get_listing_workbench(
    view: str = "all",
    query: str | None = None,
    period_start: date | None = None,
    country: str | None = None,
    shop: str | None = None,
    salesperson_name: str | None = None,
    status: str | None = None,
    week_number: int | None = None,
    product_positioning: str | None = None,
    tracking_status: str | None = None,
    business_period: str | None = None,
    only_my_tasks: bool = Query(default=False),
    include_history: bool = Query(default=False),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    is_manager = manager_access(auth)
    owner = salesperson_name if is_manager else (auth.operator_name if auth else salesperson_name)
    if is_manager and only_my_tasks and auth:
        owner = auth.operator_name or auth.user.name
    try:
        return services.list_listing_workbench(
            db,
            owner=owner,
            view=view,
            query=query,
            period_start=period_start,
            country=country,
            shop=shop,
            status=status,
            week_number=week_number,
            product_positioning=product_positioning,
            tracking_status=tracking_status,
            business_period=business_period,
            include_history=include_history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/summary", response_model=schemas.ListingWorkbenchRead)
def get_listing_summary(
    main_sku: str,
    country: str | None = None,
    salesperson_name: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    owner = salesperson_name if manager_access(auth) else (auth.operator_name if auth else salesperson_name)
    return services.listing_summary(db, main_sku=main_sku, owner=owner, country=country)


@router.post("/listings/batch", response_model=list[schemas.ListingRecordRead])
def create_listings_batch(
    payload: schemas.ListingBatchRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> list[dict]:
    actor_name = auth.user.name if auth else "local"
    actor_user_id = auth.user.id if auth else None
    try:
        records = services.create_listing_batch(
            db,
            payload.task_key,
            payload.rows,
            actor_name,
            actor_user_id,
            manager_access(auth),
            auth.operator_name if auth else None,
            reuse_listing_ids=payload.reuse_listing_ids,
            manual_context=payload.manual_context,
        )
    except services.RowValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"row_errors": exc.row_errors}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    source_context = services.listing_source_context(db, records)
    result = [services.listing_record_read(item, source_context[item.id]) for item in records]
    db.commit()
    return result


@router.patch("/listings/{listing_id}", response_model=schemas.ListingRecordRead)
def update_listing(
    listing_id: str,
    payload: schemas.ListingRecordUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    try:
        listing = services.update_listing_record(
            db,
            listing_id,
            payload,
            auth.user.name if auth else "local",
            auth.user.id if auth else None,
            manager_access(auth),
            auth.operator_name if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="item already exists") from exc
    source_context = services.listing_source_context(db, [listing])
    return services.listing_record_read(listing, source_context[listing.id])


@router.post("/listings/{listing_id}/periods", response_model=schemas.ObservationPeriodRead)
def create_listing_period(
    listing_id: str,
    payload: schemas.ObservationPeriodCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    try:
        period_start = date.fromisoformat(payload.period_start)
        period = services.add_observation_period(
            db,
            listing_id,
            period_start,
            auth.user.name if auth else "local",
            auth.user.id if auth else None,
            manager_access(auth),
            auth.operator_name if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    listing = period.listing_record
    source_context = services.listing_source_context(db, [listing])
    defaults = services.observation_positioning_defaults(db, [listing.id], source_context)
    result = services.observation_period_read(period, listing, defaults.get(period.id))
    db.commit()
    return result


@router.post("/periods/review-batch", response_model=list[schemas.ObservationPeriodRead])
def review_periods_batch(
    payload: schemas.ObservationPeriodReviewBatchRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> list[dict]:
    try:
        periods = services.review_observation_periods(
            db,
            payload.rows,
            auth.user.name if auth else "local",
            auth.user.id if auth else None,
            manager_access(auth),
            auth.operator_name if auth else None,
        )
    except services.RowValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"row_errors": exc.row_errors}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    listings = list({listing.id: listing for _, listing in periods}.values())
    source_context = services.listing_source_context(db, listings)
    defaults = services.observation_positioning_defaults(db, [listing.id for listing in listings], source_context)
    result = [services.observation_period_read(period, listing, defaults.get(period.id)) for period, listing in periods]
    db.commit()
    return result
