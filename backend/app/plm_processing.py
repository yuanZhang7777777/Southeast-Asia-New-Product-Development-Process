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
from app.workflow_status import CLAIM_RESULT_CLAIM

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
    source_hash = hashlib.sha256(path.read_bytes() + f"\n{date_text}\n{bloc_name}".encode()).hexdigest()
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
        if historical.get("status") == "no_historical_claim" and workflow_automation_enabled:
            discovered = _activate_plm_discovery(db, batch, item)
            item.raw_payload = {**(item.raw_payload or {}), "_plm_discovery": discovered}
            runtime_claim_id = discovered.get("runtime_claim_id")
            if runtime_claim_id:
                item.matched_claim_record_id = runtime_claim_id
                item.match_status = "matched_discovered"
                matches = db.execute(
                    select(models.SalesClaimForecast, models.NewProductOpportunity)
                    .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
                    .where(models.SalesClaimForecast.id == runtime_claim_id)
                ).all()
                planned_responsibilities.extend(_responsibility_rows(matches, item.product_name))
                continue
            if discovered.get("status"):
                item.match_status = discovered["status"]
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
    main_sku = _sku_key(row.get("main_sku"))
    site = normalize_site_code(row.get("country")) or ""
    salesperson = (row.get("salesperson_name") or "").strip()
    if not sub_sku or not site or not salesperson:
        return []
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
            models.SalesClaimForecast.source_column.in_(
                ("platform", "history_selection1", "plm_arrival_discovery", "manual_secondary")
            ),
            models.SalesClaimForecast.secondary_research_submitted_at.is_(None),
        )
        .order_by(models.SalesClaimForecast.created_at)
    ).all()
    export_sites = _stocking_export_sites(db, [claim.id for claim, _ in rows])
    seen: set[str] = set()
    matches: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]] = []
    for claim, opportunity in rows:
        if claim.id in seen:
            continue
        if (claim.salesperson_name or "").strip() != salesperson:
            continue
        if main_sku and _sku_key(opportunity.main_sku) != main_sku:
            continue
        if _sku_key(opportunity.sub_sku) != sub_sku:
            continue
        claim_export_sites = export_sites.get(claim.id)
        claim_sites = claim_export_sites or {normalize_site_code(opportunity.site or opportunity.country) or ""}
        if site not in claim_sites:
            continue
        if opportunity.current_status == "disabled" or services.is_read_only_historical_opportunity(opportunity):
            continue
        if opportunity.current_status == "historical_archive":
            continue
        seen.add(claim.id)
        matches.append((claim, opportunity))
    return matches


def _stocking_export_sites(db: Session, claim_ids: list[str]) -> dict[str, set[str]]:
    if not claim_ids:
        return {}
    rows = db.execute(
        select(models.ExportRow.claim_record_id, models.ExportRow.country)
        .join(models.ExportBatch, models.ExportBatch.id == models.ExportRow.export_batch_id)
        .join(
            models.StockingRequest,
            and_(
                models.StockingRequest.id == models.ExportRow.stocking_request_id,
                models.StockingRequest.claim_record_id == models.ExportRow.claim_record_id,
            ),
        )
        .where(
            models.ExportRow.claim_record_id.in_(claim_ids),
            models.ExportBatch.scope == "stocking_available",
            models.StockingRequest.status == "exported",
        )
    )
    result: dict[str, set[str]] = {}
    for claim_id, country in rows:
        site = normalize_site_code(country)
        if site:
            result.setdefault(claim_id, set()).add(site)
    return result


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
            select(models.ArrivalRecord.id).where(models.ArrivalRecord.claim_record_id == claim_id)
        )
        is not None
    )


def _activate_plm_discovery(
    db: Session,
    batch: models.PlmArrivalBatch,
    item: models.PlmArrivalItem,
) -> dict[str, Any]:
    site = normalize_site_code(item.country)
    main_sku = (item.main_sku or "").strip()
    sub_sku = (item.sub_sku or "").strip()
    salesperson_name = (item.salesperson_name or "").strip()
    if not site or not main_sku or not sub_sku:
        return {"status": "assignment_missing_required_fields"}
    country = _country_label(item.country)
    assignment = {
        "status": "pending_assignment",
        "batch_id": batch.id,
        "item_id": item.id,
        "arrival_date": batch.arrival_date,
        "source_file": batch.source_file,
        "source_sheet": item.source_sheet,
        "source_row": item.source_row,
        "salesperson_name": salesperson_name or None,
        "country": country,
        "site": site,
        "main_sku": main_sku,
        "sub_sku": sub_sku,
        "product_name": item.product_name,
        "warehouse": item.warehouse,
        "latest_storage_time": item.latest_storage_time.isoformat() if item.latest_storage_time else None,
        "first_listing_time": item.first_listing_time.isoformat() if item.first_listing_time else None,
        "reason": "PLM新品到货未能精确命中当前系统负责人，等待主管/超管指派",
    }
    item.raw_payload = {
        **(item.raw_payload or {}),
        "_plm_assignment": assignment,
    }
    return assignment


def _system_opportunity_exists_for_item(db: Session, item: models.PlmArrivalItem) -> bool:
    site = normalize_site_code(item.country)
    main_sku = _sku_key(item.main_sku)
    sub_sku = _sku_key(item.sub_sku)
    if not site or not main_sku or not sub_sku:
        return False
    rows = db.scalars(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.current_status != "disabled",
            models.NewProductOpportunity.source_type != "plm_arrival_discovery",
        )
    )
    return any(
        _sku_key(row.main_sku) == main_sku
        and _sku_key(row.sub_sku) == sub_sku
        and (normalize_site_code(row.site or row.country) or "") == site
        and row.current_status != "historical_archive"
        and not services.is_read_only_historical_opportunity(row)
        and services.is_visible_business_period(row.batch)
        for row in rows
    )


def activate_existing_system_sku_discoveries(
    db: Session,
    *,
    arrival_date: str | None = None,
    batch_id: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Re-check PLM rows previously blocked by stale system records.

    This is intentionally narrow: it only revisits PLM new-arrival rows whose
    match_status is exactly ``existing_system_sku``. Dry-run is the default so
    production can inspect the affected rows before mutating data.
    """
    query = (
        select(models.PlmArrivalItem, models.PlmArrivalBatch)
        .join(models.PlmArrivalBatch, models.PlmArrivalBatch.id == models.PlmArrivalItem.batch_id)
        .where(
            models.PlmArrivalItem.arrival_type == "new_arrival",
            models.PlmArrivalItem.match_status == "existing_system_sku",
        )
        .order_by(models.PlmArrivalBatch.arrival_date, models.PlmArrivalItem.source_row)
    )
    if arrival_date:
        query = query.where(models.PlmArrivalBatch.arrival_date == arrival_date)
    if batch_id:
        query = query.where(models.PlmArrivalBatch.id == batch_id)

    rows = db.execute(query).all()
    report: dict[str, Any] = {
        "scanned": len(rows),
        "would_activate": 0,
        "activated": 0,
        "queued_for_assignment": 0,
        "skipped": 0,
        "items": [],
    }
    for item, batch in rows:
        if _system_opportunity_exists_for_item(db, item):
            status = "still_existing_system_sku"
            report["skipped"] += 1
            runtime_claim_id = None
        elif not apply:
            status = "would_activate"
            report["would_activate"] += 1
            runtime_claim_id = None
        else:
            discovered = _activate_plm_discovery(db, batch, item)
            item.raw_payload = {**(item.raw_payload or {}), "_plm_discovery_recheck": discovered}
            runtime_claim_id = discovered.get("runtime_claim_id")
            if runtime_claim_id:
                item.matched_claim_record_id = runtime_claim_id
                item.match_status = "matched_discovered"
                status = discovered.get("status") or "activated"
                report["activated"] += 1
            elif discovered.get("status") == "pending_assignment":
                status = "pending_assignment"
                item.match_status = status
                report["queued_for_assignment"] += 1
            else:
                status = discovered.get("status") or "not_activated"
                item.match_status = status
                report["skipped"] += 1
        report["items"].append(
            {
                "batch_id": batch.id,
                "arrival_date": batch.arrival_date,
                "source_file": batch.source_file,
                "source_row": item.source_row,
                "country": item.country,
                "salesperson_name": item.salesperson_name,
                "main_sku": item.main_sku,
                "sub_sku": item.sub_sku,
                "status": status,
                "runtime_claim_id": runtime_claim_id,
            }
        )
    if apply:
        db.commit()
    return report


def _country_label(value: str | None) -> str | None:
    code = normalize_site_code(value)
    return {
        "PH": "菲律宾",
        "TH": "泰国",
        "VN": "越南",
        "MY": "马来西亚",
    }.get(code or "", (value or "").strip() or None)


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
