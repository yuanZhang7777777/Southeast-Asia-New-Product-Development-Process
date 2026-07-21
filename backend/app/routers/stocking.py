from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import erp_product_list, models, schemas, services
from app.auth import AuthContext, require_roles
from app.config import Settings, get_settings
from app.db import get_db

router = APIRouter(prefix="/stocking", tags=["stocking"])


@router.get("/requests", response_model=list[schemas.StockingRequestRead])
def list_stocking_requests(
    db: Session = Depends(get_db),
    _auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[models.StockingRequest]:
    return list(db.scalars(select(models.StockingRequest).order_by(models.StockingRequest.created_at.desc()).limit(200)))


@router.get("/export-periods", response_model=list[schemas.ExportPeriodSummary])
def list_export_periods(
    db: Session = Depends(get_db),
    _auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[schemas.ExportPeriodSummary]:
    return services.list_export_period_summaries(db)


@router.get("/available-list", response_model=list[schemas.AvailableStockingItem])
def list_available_stocking_items(
    source_sheet: str | None = Query(None),
    business_period: str | None = Query(None),
    import_batch_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[schemas.AvailableStockingItem]:
    return services.list_available_stocking_items(db, source_sheet=source_sheet, business_period=business_period, import_batch_id=import_batch_id)


@router.post("/available-list/export")
def export_available_stocking_items(
    payload: schemas.StockingExportSelection,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> Response:
    if auth is None:
        raise HTTPException(status_code=401, detail="manager authentication required")
    file_name = "海外仓备货申请表.xlsx"
    try:
        items = services.lock_selected_stocking_items(db, payload.request_ids)
    except (LookupError, PermissionError, ValueError, RuntimeError) as exc:
        db.rollback()
        _raise_service_error(exc)
    try:
        content = services.build_available_stocking_workbook(items)
    except Exception:
        db.rollback()
        raise
    try:
        services.record_export_batch(
            db,
            items,
            file_name=file_name,
            scope="stocking_available",
            exported_by=auth.user.name,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    filename = quote(file_name)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/traceability/export")
def export_traceability_items(
    source_sheet: str | None = Query(None),
    business_period: str | None = Query(None),
    import_batch_id: str | None = Query(None),
    db: Session = Depends(get_db),
    _auth: AuthContext | None = Depends(require_roles("manager")),
) -> Response:
    items = services.list_available_stocking_items(
        db,
        source_sheet=source_sheet,
        business_period=business_period,
        import_batch_id=import_batch_id,
    )
    not_claim_rows = services.list_not_claim_traceability_rows(db, source_sheet=source_sheet, business_period=business_period, import_batch_id=import_batch_id)
    file_name = period_file_name("新品中央字段导出", business_period or source_sheet, import_batch_id)
    batch = services.record_export_batch(
        db,
        items,
        file_name=file_name,
        scope="traceability",
        extra_row_count=len(not_claim_rows),
        extra_rows=[(opportunity, claim) for opportunity, claim, _ in not_claim_rows],
    )
    content = services.build_traceability_workbook(
        db,
        items,
        export_batch=batch,
        not_claim_rows=not_claim_rows,
    )
    db.commit()
    filename = quote(file_name)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def period_file_name(prefix: str, source_sheet: str | None, import_batch_id: str | None) -> str:
    period = source_sheet or import_batch_id
    return f"{prefix}-{period}.xlsx" if period else f"{prefix}.xlsx"


@router.post("/requests", response_model=schemas.MessageResponse)
def create_stocking_request(
    payload: schemas.StockingRequestCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> schemas.MessageResponse:
    claim = db.get(models.SalesClaimForecast, payload.claim_record_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim record not found")
    if claim.opportunity_id != payload.opportunity_id:
        raise HTTPException(status_code=400, detail="claim record does not belong to opportunity")
    item = services.create_stocking_draft_for_claim(db, claim.id, auth.user.name if auth else payload.salesperson_name)
    db.commit()
    return schemas.MessageResponse(message="stocking draft created", id=item.id)


@router.post("/self-selections", response_model=list[schemas.OperatorStockingItemRead])
def create_sales_self_selection(
    payload: schemas.SalesSelfSelectionCreate,
    auth: AuthContext | None = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> list[schemas.OperatorStockingItemRead]:
    operator_name, actor_user_id = _operator_identity(auth)
    try:
        items = services.create_sales_self_selection(db, payload, operator_name, actor_user_id)
        db.commit()
        return items
    except (LookupError, PermissionError, ValueError, RuntimeError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.get("/my-requests", response_model=list[schemas.OperatorStockingItemRead])
def list_my_stocking_requests(
    auth: AuthContext | None = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> list[schemas.OperatorStockingItemRead]:
    operator_name, _ = _operator_identity(auth)
    return services.list_operator_stocking_items(db, operator_name)


@router.put("/requests/{request_id}", response_model=schemas.StockingRequestRead)
def update_my_stocking_request(
    request_id: str,
    payload: schemas.StockingRequestUpdate,
    auth: AuthContext | None = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> models.StockingRequest:
    operator_name, actor_user_id = _operator_identity(auth)
    try:
        request = services.update_stocking_request(db, request_id, operator_name, payload, actor_user_id)
        db.commit()
        db.refresh(request)
        return request
    except (LookupError, PermissionError, ValueError, RuntimeError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post("/requests/{request_id}/submit", response_model=schemas.StockingRequestRead)
def submit_my_stocking_request(
    request_id: str,
    auth: AuthContext | None = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> models.StockingRequest:
    operator_name, actor_user_id = _operator_identity(auth)
    try:
        request = services.submit_stocking_request(db, request_id, operator_name, actor_user_id)
        db.commit()
        db.refresh(request)
        return request
    except (LookupError, PermissionError, ValueError, RuntimeError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post("/decisions/{claim_record_id}", response_model=schemas.OperatorStockingItemRead)
def update_my_stocking_decision(
    claim_record_id: str,
    payload: schemas.StockingDecisionUpdate,
    auth: AuthContext | None = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> schemas.OperatorStockingItemRead:
    operator_name, actor_user_id = _operator_identity(auth)
    try:
        item = services.update_stocking_decision(db, claim_record_id, operator_name, payload, actor_user_id)
        db.commit()
        return item
    except (LookupError, PermissionError, ValueError, RuntimeError) as exc:
        db.rollback()
        _raise_service_error(exc)


@router.post("/volume-preview", response_model=list[schemas.VolumePreviewRead])
def preview_stocking_volume(
    payload: schemas.VolumePreviewRequest,
    _auth: AuthContext | None = Depends(require_roles("operator")),
    settings: Settings = Depends(get_settings),
) -> list[schemas.VolumePreviewRead]:
    skus = list(dict.fromkeys(sku.strip() for sku in payload.skus if sku.strip()))
    if not skus:
        raise HTTPException(status_code=400, detail="at least one sub_sku is required")
    volumes = erp_product_list.fetch_product_volumes(skus, settings)
    return [
        schemas.VolumePreviewRead(
            sub_sku=sku,
            unit_volume=volumes.get(sku),
            status="resolved" if volumes.get(sku) is not None else "manual_required",
        )
        for sku in skus
    ]


def _operator_identity(auth: AuthContext | None) -> tuple[str, str]:
    if auth is None or not auth.operator_name:
        raise HTTPException(status_code=401, detail="operator authentication required")
    return auth.operator_name, auth.user.id


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        status_code = 404
    elif isinstance(exc, PermissionError):
        status_code = 403
    elif isinstance(exc, RuntimeError):
        status_code = 409
    else:
        status_code = 400
    raise HTTPException(status_code=status_code, detail=str(exc))
