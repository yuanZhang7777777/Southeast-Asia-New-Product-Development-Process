from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app import models, services
from app.historical_arrival_activation import activate_historical_arrival, listing_status_for_sku
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

    planned_responsibilities: list[dict[str, Any]] = []
    for row in preview["items"]:
        item = _arrival_item(batch.id, row)
        db.add(item)
        if item.arrival_type != "new_arrival":
            item.match_status = "not_new_arrival"
            continue
        candidates = _exact_claim_matches(db, row)
        matches, listing_status = _unlisted_claim_matches(db, candidates)
        if matches:
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
            continue
        if candidates:
            item.match_status = listing_status or "already_listed"
            item.raw_payload = {
                **(item.raw_payload or {}),
                "_skipped_listing_claim_record_ids": [claim.id for claim, _ in candidates],
            }
            continue

        db.flush()
        historical = activate_historical_arrival(db, item, apply=workflow_automation_enabled)
        item.raw_payload = {**(item.raw_payload or {}), "_historical_activation": historical}
        if historical.get("status") == "already_activated":
            item.match_status = "historical_deduped"
            continue
        runtime_claim_ids = historical.get("runtime_claim_ids") or ([historical["runtime_claim_id"]] if historical.get("runtime_claim_id") else [])
        if runtime_claim_ids:
            item.matched_claim_record_id = runtime_claim_ids[0]
            matches = db.execute(
                select(models.SalesClaimForecast, models.NewProductOpportunity)
                .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
                .where(models.SalesClaimForecast.id.in_(runtime_claim_ids))
            ).all()
            planned_responsibilities.extend(_responsibility_rows(matches, item.product_name))
            item.match_status = "matched_historical" if workflow_automation_enabled else "matched_historical_dry_run"
            continue
        if historical.get("status") == "historical_candidate":
            item.match_status = "matched_historical_dry_run"
            planned_responsibilities.extend(_historical_responsibility_rows(db, historical, item.product_name))
            continue
        item.match_status = historical.get("status") if historical.get("status") in {
            "already_listed",
            "listing_binding_unresolved",
            "owner_unmapped",
            "owner_ambiguous",
            "main_sku_ambiguous",
            "missing_site_or_sub_sku",
            "historical_secondary_research",
        } else "unmatched"

    db.commit()
    return _summary(db, batch, "processed", planned_responsibilities=planned_responsibilities)


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
        select(models.SalesClaimForecast, models.NewProductOpportunity, models.ExportRow)
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
    for claim, opportunity, export_row in rows:
        if claim.id in seen:
            continue
        if (claim.salesperson_name or "").strip() != salesperson:
            continue
        if _sku_key(opportunity.sub_sku) != sub_sku:
            continue
        if (normalize_site_code(export_row.country) or "") != site:
            continue
        seen.add(claim.id)
        matches.append((claim, opportunity))
    return matches


def _unlisted_claim_matches(
    db: Session,
    candidates: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]],
) -> tuple[list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]], str | None]:
    matches: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]] = []
    blocked: list[str] = []
    for claim, opportunity in candidates:
        status = listing_status_for_sku(
            db,
            country=opportunity.site or opportunity.country,
            main_sku=opportunity.main_sku,
            sub_sku=opportunity.sub_sku,
        )
        if status is None:
            matches.append((claim, opportunity))
        else:
            blocked.append(status)
    if matches:
        return matches, None
    if "already_listed" in blocked:
        return [], "already_listed"
    return [], blocked[0] if blocked else None


def _active_listing_keys(db: Session) -> set[tuple[str, str]]:
    rows = list(
        db.execute(
            select(
                models.ListingRecord.main_sku,
                models.ListingRecord.country,
                models.ListingRecord.site,
                models.ListingRecord.item,
                models.ListingSkuBinding.main_sku,
            )
            .outerjoin(models.ListingSkuBinding, models.ListingSkuBinding.listing_record_id == models.ListingRecord.id)
            .where(models.ListingRecord.status == "active")
        )
    )
    return {
        (_sku_key(binding_main_sku or main_sku), normalize_site_code(site or country) or "")
        for main_sku, country, site, item, binding_main_sku in rows
        if _sku_key(binding_main_sku or main_sku) and _sku_key(item)
    }


def _opportunity_listing_key(opportunity: models.NewProductOpportunity) -> tuple[str, str]:
    return (
        _sku_key(opportunity.main_sku),
        normalize_site_code(opportunity.site or opportunity.country) or "",
    )


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
        "already_listed_count": sum(1 for item in items if item.match_status == "already_listed"),
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


def _historical_responsibility_rows(
    db: Session,
    decision: dict[str, Any],
    product_name: str | None,
) -> list[dict[str, Any]]:
    rows = decision.get("activations") or [{
        "opportunity_id": decision.get("opportunity_id"),
        "owner_name": decision.get("owner_name"),
    }]
    result = []
    for row in rows:
        if row.get("status") != "historical_candidate":
            continue
        opportunity_id = row.get("opportunity_id")
        if not isinstance(opportunity_id, str):
            continue
        opportunity = db.get(models.NewProductOpportunity, opportunity_id)
        if opportunity is None:
            continue
        result.append({
            "claim_record_id": None,
            "opportunity_id": opportunity.id,
            "business_period": opportunity.batch,
            "salesperson_name": row.get("owner_name"),
            "site": opportunity.site,
            "country": opportunity.country,
            "main_sku": opportunity.main_sku,
            "sub_sku": opportunity.sub_sku,
            "product_name": product_name or opportunity.main_sku_name or opportunity.sub_sku_name,
        })
    return result


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
