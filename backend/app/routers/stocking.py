from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import require_roles
from app.db import get_db

router = APIRouter(prefix="/stocking", tags=["stocking"], dependencies=[Depends(require_roles("manager"))])


@router.get("/requests", response_model=list[schemas.StockingRequestRead])
def list_stocking_requests(db: Session = Depends(get_db)) -> list[models.StockingRequest]:
    return list(db.scalars(select(models.StockingRequest).order_by(models.StockingRequest.created_at.desc()).limit(200)))


@router.get("/available-list", response_model=list[schemas.AvailableStockingItem])
def list_available_stocking_items(
    source_sheet: str | None = Query(None),
    business_period: str | None = Query(None),
    import_batch_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[schemas.AvailableStockingItem]:
    return services.list_available_stocking_items(db, source_sheet=source_sheet, business_period=business_period, import_batch_id=import_batch_id)


@router.get("/available-list/export")
def export_available_stocking_items(
    source_sheet: str | None = Query(None),
    business_period: str | None = Query(None),
    import_batch_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    items = services.list_available_stocking_items(db, source_sheet=source_sheet, business_period=business_period, import_batch_id=import_batch_id)
    file_name = period_file_name("海外仓备货申请表", business_period or source_sheet, import_batch_id)
    batch = services.record_export_batch(db, items, file_name=file_name, scope="stocking_available")
    content = services.build_available_stocking_workbook(items, exported_at=batch.exported_at)
    db.commit()
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
) -> Response:
    items = services.list_available_stocking_items(
        db,
        source_sheet=source_sheet,
        business_period=business_period,
        import_batch_id=import_batch_id,
        exclude_exported_scope="traceability",
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
def create_stocking_request(payload: schemas.StockingRequestCreate, db: Session = Depends(get_db)) -> schemas.MessageResponse:
    quantity = int(round(payload.daily_sales * 30))
    item = models.StockingRequest(
        opportunity_id=payload.opportunity_id,
        salesperson_name=payload.salesperson_name,
        daily_sales=payload.daily_sales,
        quantity=quantity,
        country=payload.country,
        warehouse=payload.warehouse,
        reason=payload.reason,
        status="draft",
    )
    db.add(item)
    services.audit(db, "stocking.request_created", "stocking_request", item.id, payload.model_dump(), payload.salesperson_name)
    db.commit()
    return schemas.MessageResponse(message="stocking draft created", id=item.id)
