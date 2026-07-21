from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app import models, services
from app.plm_arrivals import parse_plm_arrival_preview
from app.site_codes import normalize_site_code
from app.workflow_status import CLAIM_RESULT_CLAIM, CLAIM_WAITING_ARRIVAL

BEIJING_TZ = timezone(timedelta(hours=8))


def process_plm_arrival_workbook(
    db: Session,
    workbook_path: str | Path,
    date_text: str,
    source_file: str | None = None,
    bloc_name: str = "\u96c6\u56e2\u516b\u90e8",
    workflow_automation_enabled: bool = False,
) -> dict[str, Any]:
    path = Path(workbook_path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = db.scalar(select(models.PlmArrivalBatch).where(models.PlmArrivalBatch.source_hash == source_hash))
    if existing:
        return _summary(db, existing, "duplicate")

    preview = parse_plm_arrival_preview(path, date_text, bloc_name=bloc_name)
    batch = models.PlmArrivalBatch(
        arrival_date=date_text,
        source_file=source_file or path.name,
        source_hash=source_hash,
        bloc_name=bloc_name,
        status="processed",
        processed_at=datetime.now(timezone.utc),
        row_count=preview["row_count"],
    )
    db.add(batch)
    db.flush()

    arrival_records = 0
    planned_responsibilities: list[dict[str, Any]] = []
    for row in preview["items"]:
        item = _arrival_item(batch.id, row)
        db.add(item)
        if item.arrival_type != "new_arrival":
            item.match_status = "not_new_arrival"
            continue
        matches = _exact_claim_matches(db, row)
        if not matches:
            item.match_status = "unmatched"
            continue
        item.matched_claim_record_id = matches[0][0].id
        item.match_status = "matched"
        item.raw_payload = {**(item.raw_payload or {}), "_matched_claim_record_ids": [claim.id for claim, _ in matches]}
        planned_responsibilities.extend(_responsibility_rows(matches, item.product_name))
        if not workflow_automation_enabled:
            item.match_status = "matched_dry_run"
            continue
        db.flush()
        for claim, opportunity in matches:
            if _arrival_record_exists(db, batch.id, claim.id):
                continue
            services.open_secondary_research(db, claim.id, item.latest_storage_time)
            db.add(
                models.ArrivalRecord(
                    opportunity_id=opportunity.id,
                    claim_record_id=claim.id,
                    plm_arrival_batch_id=batch.id,
                    plm_arrival_item_id=item.id,
                    salesperson_name=claim.salesperson_name,
                    country=row.get("country") or opportunity.country,
                    warehouse=row.get("warehouse"),
                    arrived_quantity=_int_or_none(row.get("available_quantity")),
                    arrived_at=item.latest_storage_time,
                    note="PLM arrival exact match",
                )
            )
            arrival_records += 1

    db.commit()
    return _summary(db, batch, "processed", arrival_records, planned_responsibilities)


def _arrival_item(batch_id: str, row: dict[str, Any]) -> models.PlmArrivalItem:
    return models.PlmArrivalItem(
        batch_id=batch_id,
        source_sheet=row.get("source_sheet"),
        source_row=row.get("source_row"),
        arrival_type=row["arrival_type"],
        product_name=row.get("product_name"),
        salesperson_name=(row.get("salesperson_name") or "").strip() or None,
        country=row.get("country"),
        warehouse=row.get("warehouse"),
        main_sku=row.get("main_sku"),
        sub_sku=row.get("sub_sku"),
        latest_storage_time=_datetime_value(row.get("latest_storage_time")),
        first_listing_time=_datetime_value(row.get("first_listing_time")),
        available_quantity=row.get("available_quantity"),
        real_stock_quantity=row.get("real_stock_quantity"),
        daily_sales=row.get("daily_sales"),
        raw_payload=row,
    )


def _exact_claim_matches(
    db: Session,
    row: dict[str, Any],
) -> list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]]:
    sub_sku = _sku_key(row.get("sub_sku"))
    site = normalize_site_code(row.get("country")) or ""
    salesperson = (row.get("salesperson_name") or "").strip()
    if not sub_sku or not site or not salesperson:
        return []
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .join(models.ExportRow, models.ExportRow.claim_record_id == models.SalesClaimForecast.id)
        .join(models.ExportBatch, models.ExportBatch.id == models.ExportRow.export_batch_id)
        .join(
            models.StockingRequest,
            and_(
                models.StockingRequest.id == models.ExportRow.stocking_request_id,
                models.StockingRequest.claim_record_id == models.SalesClaimForecast.id,
                models.StockingRequest.opportunity_id == models.NewProductOpportunity.id,
            ),
        )
        .where(
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
            models.SalesClaimForecast.source_column == "platform",
            models.SalesClaimForecast.downstream_status == CLAIM_WAITING_ARRIVAL,
            models.ExportRow.opportunity_id == models.NewProductOpportunity.id,
            models.ExportBatch.scope == "stocking_available",
            models.StockingRequest.status == "exported",
        )
        .order_by(models.SalesClaimForecast.created_at)
    ).all()
    seen: set[str] = set()
    matches: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]] = []
    for claim, opportunity in rows:
        if claim.id in seen:
            continue
        seen.add(claim.id)
        if (claim.salesperson_name or "").strip() != salesperson:
            continue
        if _sku_key(opportunity.sub_sku) != sub_sku:
            continue
        if (normalize_site_code(opportunity.site or opportunity.country) or "") != site:
            continue
        matches.append((claim, opportunity))
    return matches


def _arrival_record_exists(db: Session, batch_id: str, claim_id: str) -> bool:
    return (
        db.scalar(
            select(models.ArrivalRecord.id).where(
                models.ArrivalRecord.plm_arrival_batch_id == batch_id,
                models.ArrivalRecord.claim_record_id == claim_id,
            )
        )
        is not None
    )


def _summary(
    db: Session,
    batch: models.PlmArrivalBatch,
    status: str,
    arrival_record_count: int | None = None,
    planned_responsibilities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = list(db.scalars(select(models.PlmArrivalItem).where(models.PlmArrivalItem.batch_id == batch.id)))
    if arrival_record_count is None:
        arrival_record_count = len(
            list(db.scalars(select(models.ArrivalRecord.id).where(models.ArrivalRecord.plm_arrival_batch_id == batch.id)))
        )
    responsibilities = planned_responsibilities if planned_responsibilities is not None else _matched_responsibilities_from_items(db, items)
    return {
        "batch_id": batch.id,
        "status": status,
        "row_count": len(items),
        "new_arrival_count": sum(1 for item in items if item.arrival_type == "new_arrival"),
        "restock_count": sum(1 for item in items if item.arrival_type == "restock"),
        "unknown_count": sum(1 for item in items if item.arrival_type == "unknown"),
        "matched_count": len(responsibilities),
        "unmatched_count": sum(1 for item in items if item.match_status == "unmatched"),
        "arrival_record_count": arrival_record_count,
        "planned_responsibilities": responsibilities,
    }


def _matched_responsibilities_from_items(db: Session, items: list[models.PlmArrivalItem]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        raw = item.raw_payload or {}
        claim_ids = raw.get("_matched_claim_record_ids")
        if not isinstance(claim_ids, list):
            claim_ids = [item.matched_claim_record_id] if item.matched_claim_record_id else []
        if not claim_ids:
            continue
        matches = db.execute(
            select(models.SalesClaimForecast, models.NewProductOpportunity)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
            .where(models.SalesClaimForecast.id.in_(claim_ids))
            .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.main_sku, models.NewProductOpportunity.sub_sku)
        ).all()
        rows.extend(_responsibility_rows(matches, item.product_name))
    return rows


def _responsibility_rows(
    matches: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]],
    product_name: str | None,
) -> list[dict[str, Any]]:
    return [
        {
            "claim_record_id": claim.id,
            "opportunity_id": opportunity.id,
            "business_period": opportunity.batch,
            "salesperson_name": claim.salesperson_name,
            "site": opportunity.site,
            "country": opportunity.country,
            "main_sku": opportunity.main_sku,
            "sub_sku": opportunity.sub_sku,
            "product_name": product_name or opportunity.main_sku_name or opportunity.sub_sku_name,
        }
        for claim, opportunity in matches
    ]


def _sku_key(value: Any) -> str:
    return "".join(str(value or "").split()).upper()


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        source = value
        if source.tzinfo is None:
            source = source.replace(tzinfo=BEIJING_TZ)
        return source.astimezone(timezone.utc)
    text = str(value or "").strip().replace("/", "-")
    if not text:
        return None
    for fmt, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:length], fmt).replace(tzinfo=BEIJING_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
