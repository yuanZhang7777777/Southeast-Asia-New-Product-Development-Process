from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app import models
from app.config import Settings
from app.db import SessionLocal
CLAIM_HISTORICAL_SECONDARY_SUBMITTED = "historical_secondary_submitted"
CLAIM_RESULT_CLAIM = "claim"
CLAIM_WAITING_SECONDARY_RESEARCH = "waiting_secondary_research"
OPPORTUNITY_CLAIM_SUBMITTED = "claim_submitted"

BEIJING_TZ = timezone(timedelta(hours=8))


def ingest_package(package_dir: Path, apply: bool = False) -> dict[str, int]:
    settings = Settings()
    if apply and settings.app_env not in {"development", "local", "test"}:
        raise RuntimeError(f"refusing PLM local ingest outside dev/local/test env: {settings.app_env}")

    plan = json.loads((package_dir / "plm_20260727_20260803_match_plan.json").read_text(encoding="utf-8"))
    raw = json.loads((package_dir / "plm_arrivals_20260727_20260803.json").read_text(encoding="utf-8"))
    raw_by_key = {
        (
            str(item.get("arrival_date") or ""),
            str(item.get("main_sku") or "").strip(),
            str(item.get("sub_sku") or "").strip(),
            str(item.get("salesperson_name") or "").strip(),
            int(item.get("source_row") or 0),
        ): item
        for item in raw["items"]
    }

    summary = {
        "rows": 0,
        "batches_created": 0,
        "items_created": 0,
        "arrival_records_created": 0,
        "existing_claims_updated": 0,
        "plm_discovery_opportunities_created": 0,
        "duplicate_empty_claims_deleted": 0,
        "skipped_review_required": 0,
    }
    with SessionLocal() as db:
        for row in plan["rows"]:
            summary["rows"] += 1
            status = row["系统命中结果"]
            raw_item = raw_by_key.get((
                row["到货日期"],
                row["主SKU"],
                row["子SKU"],
                row["PLM销售员"],
                int(row["PLM源行"] or 0),
            ))
            if raw_item is None:
                raise RuntimeError(f"missing raw PLM row for {row['到货日期']} {row['主SKU']} {row['子SKU']}")
            if status in {"可覆盖-已二调", "可覆盖-待二调"}:
                batch, batch_created = ensure_batch(db, package_dir, raw_item)
                item, item_created = ensure_item(db, batch, raw_item, row["认领ID"], "matched")
                claim = db.get(models.SalesClaimForecast, row["认领ID"])
                if claim is None:
                    raise RuntimeError(f"claim not found: {row['认领ID']}")
                opportunity = db.get(models.NewProductOpportunity, claim.opportunity_id)
                if opportunity is None:
                    raise RuntimeError(f"opportunity not found for claim: {claim.id}")
                if not arrival_exists(db, batch.id, claim.id):
                    db.add(arrival_record(opportunity, claim, batch, item, raw_item))
                    summary["arrival_records_created"] += 1
                before_status = claim.downstream_status
                if status == "可覆盖-已二调":
                    claim.downstream_status = CLAIM_HISTORICAL_SECONDARY_SUBMITTED
                else:
                    claim.downstream_status = CLAIM_WAITING_SECONDARY_RESEARCH
                claim.arrival_detected_at = claim.arrival_detected_at or item.latest_storage_time
                if claim.downstream_status != before_status:
                    summary["existing_claims_updated"] += 1
                summary["duplicate_empty_claims_deleted"] += delete_empty_duplicate_claims(db, claim)
                summary["batches_created"] += int(batch_created)
                summary["items_created"] += int(item_created)
                continue
            if status == "系统未找到":
                batch, batch_created = ensure_batch(db, package_dir, raw_item)
                opportunity = models.NewProductOpportunity(
                    source_type="plm_arrival_discovery",
                    source_file=source_basename(raw_item.get("source_file")),
                    source_sheet=raw_item.get("source_sheet"),
                    source_row=raw_item.get("source_row"),
                    batch=plm_discovery_period(raw_item),
                    country=row["PLM国家"],
                    site=row["PLM国家"],
                    main_sku_name=raw_item.get("product_name"),
                    main_sku=row["主SKU"],
                    sub_sku_name=raw_item.get("product_name"),
                    sub_sku=row["子SKU"],
                    current_status=OPPORTUNITY_CLAIM_SUBMITTED,
                    snapshot={"plm_arrival_discovery": raw_item},
                )
                db.add(opportunity)
                db.flush()
                claim = models.SalesClaimForecast(
                    opportunity_id=opportunity.id,
                    salesperson_name=row["PLM销售员"],
                    claim_result=CLAIM_RESULT_CLAIM,
                    source_column="plm_arrival_discovery",
                    claim_source="plm_arrival_discovery",
                    downstream_status=CLAIM_WAITING_SECONDARY_RESEARCH,
                    arrival_detected_at=parse_dt(raw_item.get("latest_storage_time")),
                )
                db.add(claim)
                db.flush()
                item, item_created = ensure_item(db, batch, raw_item, claim.id, "matched")
                db.add(arrival_record(opportunity, claim, batch, item, raw_item))
                db.add(models.SourceRecordSnapshot(
                    opportunity_id=opportunity.id,
                    source_file=opportunity.source_file,
                    source_sheet=opportunity.source_sheet,
                    source_row=opportunity.source_row,
                    payload=opportunity.snapshot,
                ))
                summary["batches_created"] += int(batch_created)
                summary["items_created"] += int(item_created)
                summary["arrival_records_created"] += 1
                summary["plm_discovery_opportunities_created"] += 1
                continue
            summary["skipped_review_required"] += 1
        if apply:
            db.commit()
        else:
            db.rollback()
    return summary


def ensure_batch(db, package_dir: Path, item: dict[str, Any]) -> tuple[models.PlmArrivalBatch, bool]:
    source = package_dir / "excel_cache" / source_basename(item.get("source_file"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    batch = db.scalar(select(models.PlmArrivalBatch).where(models.PlmArrivalBatch.source_hash == digest))
    if batch:
        return batch, False
    batch = models.PlmArrivalBatch(
        arrival_date=str(item.get("arrival_date") or ""),
        source_file=source.name,
        source_hash=digest,
        bloc_name="集团八部",
        status="processed",
        processed_at=datetime.now(timezone.utc),
        row_count=0,
    )
    db.add(batch)
    db.flush()
    return batch, True


def ensure_item(
    db,
    batch: models.PlmArrivalBatch,
    item: dict[str, Any],
    claim_id: str | None,
    match_status: str,
) -> tuple[models.PlmArrivalItem, bool]:
    existing = db.scalar(
        select(models.PlmArrivalItem).where(
            models.PlmArrivalItem.batch_id == batch.id,
            models.PlmArrivalItem.source_row == item.get("source_row"),
            models.PlmArrivalItem.sub_sku == item.get("sub_sku"),
        )
    )
    if existing:
        existing.matched_claim_record_id = existing.matched_claim_record_id or claim_id
        existing.match_status = match_status
        return existing, False
    created = models.PlmArrivalItem(
        batch_id=batch.id,
        source_sheet=item.get("source_sheet"),
        source_row=item.get("source_row"),
        arrival_type=item.get("arrival_type") or "new_arrival",
        product_name=item.get("product_name"),
        salesperson_name=item.get("salesperson_name"),
        country=item.get("country"),
        warehouse=item.get("warehouse"),
        main_sku=item.get("main_sku"),
        sub_sku=item.get("sub_sku"),
        latest_storage_time=parse_dt(item.get("latest_storage_time")),
        first_listing_time=parse_dt(item.get("first_listing_time")),
        available_quantity=item.get("available_quantity"),
        real_stock_quantity=item.get("real_stock_quantity"),
        daily_sales=item.get("daily_sales"),
        match_status=match_status,
        matched_claim_record_id=claim_id,
        raw_payload=item,
    )
    db.add(created)
    db.flush()
    return created, True


def arrival_record(
    opportunity: models.NewProductOpportunity,
    claim: models.SalesClaimForecast,
    batch: models.PlmArrivalBatch,
    item: models.PlmArrivalItem,
    raw_item: dict[str, Any],
) -> models.ArrivalRecord:
    return models.ArrivalRecord(
        opportunity_id=opportunity.id,
        claim_record_id=claim.id,
        plm_arrival_batch_id=batch.id,
        plm_arrival_item_id=item.id,
        salesperson_name=claim.salesperson_name,
        country=raw_item.get("country") or opportunity.country,
        warehouse=raw_item.get("warehouse"),
        arrived_quantity=int(raw_item["available_quantity"]) if raw_item.get("available_quantity") is not None else None,
        arrived_at=item.latest_storage_time,
        note="PLM local package ingest 20260727-20260803",
    )


def arrival_exists(db, batch_id: str, claim_id: str) -> bool:
    return db.scalar(
        select(models.ArrivalRecord.id).where(
            models.ArrivalRecord.plm_arrival_batch_id == batch_id,
            models.ArrivalRecord.claim_record_id == claim_id,
        )
    ) is not None


def delete_empty_duplicate_claims(db, claim: models.SalesClaimForecast) -> int:
    rows = db.scalars(
        select(models.SalesClaimForecast).where(
            models.SalesClaimForecast.opportunity_id == claim.opportunity_id,
            models.SalesClaimForecast.salesperson_name == claim.salesperson_name,
            models.SalesClaimForecast.id != claim.id,
            models.SalesClaimForecast.downstream_status.is_(None),
            models.SalesClaimForecast.secondary_research_submitted_at.is_(None),
            models.SalesClaimForecast.source_column == "selection1_tail",
        )
    ).all()
    for row in rows:
        db.delete(row)
    return len(rows)


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("/", "-")
    if not text:
        return None
    return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING_TZ).astimezone(timezone.utc)


def plm_discovery_period(item: dict[str, Any]) -> str:
    return "PLM新增到货"


def source_basename(value: Any) -> str:
    return str(value or "").replace("\\", "/").rsplit("/", 1)[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest_package(args.package_dir, apply=args.apply), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
