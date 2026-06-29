from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/stocking", tags=["stocking"])


@router.get("/requests", response_model=list[schemas.StockingRequestRead])
def list_stocking_requests(db: Session = Depends(get_db)) -> list[models.StockingRequest]:
    return list(db.scalars(select(models.StockingRequest).order_by(models.StockingRequest.created_at.desc()).limit(200)))


@router.get("/available-list", response_model=list[schemas.AvailableStockingItem])
def list_available_stocking_items(db: Session = Depends(get_db)) -> list[schemas.AvailableStockingItem]:
    return services.list_available_stocking_items(db)


@router.get("/available-list/export")
def export_available_stocking_items(db: Session = Depends(get_db)) -> Response:
    items = services.list_available_stocking_items(db)
    content = services.build_available_stocking_workbook(items)
    filename = quote("可备货清单.xlsx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


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
