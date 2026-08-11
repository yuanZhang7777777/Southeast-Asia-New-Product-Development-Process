from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings
from app.db import SessionLocal
from app.workflow_status import CLAIM_HISTORICAL_SECONDARY_SUBMITTED, CLAIM_WAITING_SECONDARY_RESEARCH

DEFAULT_CUTOFF = date(2026, 7, 27)
NOTE = "历史 PLM 到货反推二调已完成"
REOPEN_NOTE = "历史二调误锁退回待处理：无刊登证据且二调字段未完整"


def cleanup_historical_secondary_statuses(
    db: Session,
    apply: bool = False,
    cutoff: date = DEFAULT_CUTOFF,
) -> dict[str, int]:
    summary = {
        "submitted_waiting_to_history": 0,
        "historic_arrived_waiting_to_history": 0,
        "unchanged_waiting_current": 0,
        "unchanged_no_evidence": 0,
    }
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH)
    ).all()

    for claim, opportunity in rows:
        if claim.secondary_research_submitted_at:
            summary["submitted_waiting_to_history"] += 1
            if apply:
                mark_historical(claim, reason="submitted_waiting")
            continue

        arrived_at = historical_arrival_at(db, claim)
        historical = is_before_cutoff(opportunity.batch, arrived_at, cutoff)
        if not historical:
            if arrived_at:
                summary["unchanged_waiting_current"] += 1
            else:
                summary["unchanged_no_evidence"] += 1
            continue

        if arrived_at:
            summary["historic_arrived_waiting_to_history"] += 1
            if apply:
                claim.secondary_research_submitted_at = arrived_at
                mark_historical(claim, reason="historic_arrival_inferred")
            continue

        summary["unchanged_no_evidence"] += 1

    return summary


def historical_arrival_at(db: Session, claim: models.SalesClaimForecast) -> datetime | None:
    if claim.arrival_detected_at:
        return claim.arrival_detected_at
    return db.scalar(
        select(func.min(models.ArrivalRecord.arrived_at)).where(
            models.ArrivalRecord.claim_record_id == claim.id,
            models.ArrivalRecord.arrived_at.is_not(None),
        )
    )


def reopen_mislocked_historical_secondary_statuses(db: Session, apply: bool = False) -> dict[str, int]:
    summary = {
        "checked": 0,
        "reopened": 0,
        "kept_with_listing": 0,
        "kept_with_fields": 0,
    }
    listing_evidence = secondary_listing_evidence(db)
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(
            models.SalesClaimForecast.downstream_status == CLAIM_HISTORICAL_SECONDARY_SUBMITTED,
            models.SalesClaimForecast.secondary_research_submitted_at.is_not(None),
        )
    ).all()
    for claim, opportunity in rows:
        summary["checked"] += 1
        if has_complete_secondary_values(claim):
            summary["kept_with_fields"] += 1
            continue
        if has_listing_evidence(claim, opportunity, listing_evidence):
            summary["kept_with_listing"] += 1
            continue
        summary["reopened"] += 1
        if apply:
            before = {
                "downstream_status": claim.downstream_status,
                "secondary_research_submitted_at": claim.secondary_research_submitted_at.isoformat()
                if claim.secondary_research_submitted_at else None,
            }
            claim.downstream_status = CLAIM_WAITING_SECONDARY_RESEARCH
            claim.secondary_research_at = None
            claim.secondary_research_submitted_at = None
            if REOPEN_NOTE not in (claim.note or ""):
                claim.note = f"{claim.note}\n{REOPEN_NOTE}".strip() if claim.note else REOPEN_NOTE
            claim.last_updated_at = datetime.now(timezone.utc)
            claim.__dict__.setdefault("_history_cleanup_audit", {"before": before, "reason": "mislocked_blank_no_listing"})
    return summary


def has_complete_secondary_values(claim: models.SalesClaimForecast) -> bool:
    return (
        bool(text(claim.secondary_conclusion))
        and claim.product_positioning in {"引流款", "利润款", "淘汰款", "稳定款", "清仓款"}
        and bool(claim.secondary_target_daily_sales)
        and claim.secondary_target_daily_sales > 0
        and bool(text(claim.secondary_selling_points))
    )


def secondary_listing_evidence(db: Session) -> dict[str, set]:
    evidence = {"claim_ids": set(), "opportunity_ids": set(), "owner_site_main": set(), "owner_site_main_sub": set()}
    listings = db.scalars(select(models.ListingRecord).where(models.ListingRecord.status == "active")).all()
    listing_by_id = {item.id: item for item in listings}
    for listing in listings:
        for claim_id in listing.source_claim_ids or []:
            evidence["claim_ids"].add(claim_id)
        add_listing_key(evidence, listing.salesperson_name, listing.site or listing.country, listing.main_sku, None)
    bindings = db.scalars(select(models.ListingSkuBinding)).all()
    for binding in bindings:
        listing = listing_by_id.get(binding.listing_record_id)
        if binding.claim_record_id:
            evidence["claim_ids"].add(binding.claim_record_id)
        if binding.opportunity_id:
            evidence["opportunity_ids"].add(binding.opportunity_id)
        add_listing_key(
            evidence,
            binding.salesperson_name or (listing.salesperson_name if listing else None),
            (listing.site or listing.country) if listing else None,
            binding.main_sku,
            binding.sub_sku,
        )
    return evidence


def add_listing_key(evidence: dict[str, set], owner: str | None, site: str | None, main_sku: str | None, sub_sku: str | None) -> None:
    owner_text = text(owner)
    site_text = site_code(site)
    main_text = sku(main_sku)
    sub_text = sku(sub_sku)
    if owner_text and site_text and main_text:
        evidence["owner_site_main"].add((owner_text, site_text, main_text))
    if owner_text and site_text and main_text and sub_text:
        evidence["owner_site_main_sub"].add((owner_text, site_text, main_text, sub_text))


def has_listing_evidence(
    claim: models.SalesClaimForecast,
    opportunity: models.NewProductOpportunity,
    evidence: dict[str, set],
) -> bool:
    owner = text(claim.salesperson_name)
    site = site_code(opportunity.site or opportunity.country)
    main = sku(opportunity.main_sku)
    sub = sku(opportunity.sub_sku)
    return (
        claim.id in evidence["claim_ids"]
        or opportunity.id in evidence["opportunity_ids"]
        or (owner, site, main, sub) in evidence["owner_site_main_sub"]
        or (owner, site, main) in evidence["owner_site_main"]
    )


def text(value: object) -> str:
    return str(value or "").strip()


def sku(value: object) -> str:
    return text(value).upper()


def site_code(value: object) -> str:
    raw = text(value)
    mapping = {"菲律宾": "PH", "泰国": "TH", "越南": "VN", "马来西亚": "MY"}
    return mapping.get(raw, raw).upper()


def is_before_cutoff(batch: str | None, arrived_at: datetime | None, cutoff: date) -> bool:
    batch_date = date_from_text(batch or "")
    if batch_date:
        return batch_date < cutoff
    if arrived_at:
        return arrived_at.date() < cutoff
    return False


def date_from_text(text: str) -> date | None:
    match = re.search(r"(20\d{2})[-/]?(\d{2})(\d{2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = re.search(r"(\d{2})(\d{2})", text)
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return date(2026, month, day)


def mark_historical(claim: models.SalesClaimForecast, reason: str) -> None:
    before = {
        "downstream_status": claim.downstream_status,
        "secondary_research_submitted_at": claim.secondary_research_submitted_at.isoformat()
        if claim.secondary_research_submitted_at else None,
    }
    claim.downstream_status = CLAIM_HISTORICAL_SECONDARY_SUBMITTED
    if NOTE not in (claim.note or ""):
        claim.note = f"{claim.note}\n{NOTE}".strip() if claim.note else NOTE
    claim.last_updated_at = datetime.now(timezone.utc)
    claim.__dict__.setdefault("_history_cleanup_audit", {"before": before, "reason": reason})


def add_audits(db: Session) -> None:
    for item in db.dirty:
        if not isinstance(item, models.SalesClaimForecast):
            continue
        audit = item.__dict__.pop("_history_cleanup_audit", None)
        if not audit:
            continue
        db.add(models.AuditLog(
            action="history.secondary_status_cleaned",
            entity_type="sales_claim_forecast",
            entity_id=item.id,
            detail={
                **audit,
                "after": {
                    "downstream_status": item.downstream_status,
                    "secondary_research_submitted_at": item.secondary_research_submitted_at.isoformat()
                    if item.secondary_research_submitted_at else None,
                },
            },
            actor_name="historical_secondary_status_cleanup",
        ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF.isoformat())
    args = parser.parse_args()

    settings = Settings()
    if args.apply_dev and settings.app_env not in {"development", "local", "test"}:
        raise RuntimeError(f"refusing historical secondary cleanup outside dev/local/test env: {settings.app_env}")

    cutoff = date.fromisoformat(args.cutoff)
    with SessionLocal() as db:
        summary = cleanup_historical_secondary_statuses(db, apply=args.apply_dev, cutoff=cutoff)
        summary["reopen_mislocked"] = reopen_mislocked_historical_secondary_statuses(db, apply=args.apply_dev)
        if args.apply_dev:
            add_audits(db)
            db.commit()
        else:
            db.rollback()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
