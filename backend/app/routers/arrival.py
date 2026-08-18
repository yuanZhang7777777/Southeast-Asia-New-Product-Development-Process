from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import require_roles
from app.config import Settings, get_settings
from app.db import get_db
from app.plm_arrivals import parse_plm_arrival_preview
from app.plm_processing import process_plm_arrival_workbook

router = APIRouter(prefix="/arrival", tags=["arrival"], dependencies=[Depends(require_roles("manager"))])


@router.get("/records", response_model=list[schemas.ArrivalRecordRead])
def list_arrival_records(db: Session = Depends(get_db)) -> list[models.ArrivalRecord]:
    return list(db.scalars(select(models.ArrivalRecord).order_by(models.ArrivalRecord.created_at.desc()).limit(200)))


@router.post("/records", response_model=schemas.ArrivalRecordRead)
def create_arrival_record(payload: schemas.ArrivalRecordCreate, db: Session = Depends(get_db)) -> models.ArrivalRecord:
    target = db.get(models.NewProductOpportunity, payload.opportunity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    if services.is_read_only_historical_opportunity(target):
        raise HTTPException(status_code=403, detail="historical source products are read-only")
    data = payload.model_dump()
    if payload.claim_record_id:
        try:
            claim, opportunity = services.secondary_research_claim(db, payload.claim_record_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if opportunity.id != payload.opportunity_id:
            raise HTTPException(status_code=400, detail="claim record does not belong to opportunity")
        data["salesperson_name"] = claim.salesperson_name
        data["country"] = opportunity.country
        try:
            services.open_secondary_research(db, claim.id, payload.arrived_at)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = models.ArrivalRecord(**data)
    db.add(item)
    services.audit(db, "arrival.recorded", "arrival_record", item.id, payload.model_dump(mode="json"))
    db.commit()
    db.refresh(item)
    return item


@router.get("/plm-preview", response_model=schemas.PlmArrivalPreviewRead)
def plm_arrival_preview(
    date_text: str = Query(alias="date"),
    settings: Settings = Depends(get_settings),
) -> dict:
    path = Path(settings.plm_cache_dir) / f"plm-{date_text}.xlsx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="PLM cache file not found")
    return parse_plm_arrival_preview(path, date_text)


@router.post("/plm-process", response_model=schemas.PlmArrivalProcessRead)
def process_plm_arrivals(
    payload: schemas.PlmArrivalProcessRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    source_file = payload.source_file or f"plm-{payload.date}.xlsx"
    path = Path(settings.plm_cache_dir) / source_file
    if not path.exists():
        raise HTTPException(status_code=404, detail="PLM cache file not found")
    return process_plm_arrival_workbook(
        db,
        path,
        payload.date,
        source_file=source_file,
        workflow_automation_enabled=settings.workflow_automation_enabled,
    )
