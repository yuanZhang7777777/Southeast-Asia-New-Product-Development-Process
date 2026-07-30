from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.services import audit, normalize_site_code
from app.workflow_status import CLAIM_LISTING_OBSERVATION

ELIGIBLE_STATUSES = ("waiting_secondary_research", "waiting_listing")
AUDIT_ACTION = "history.claim_listing_activated"


def activate_listed_claims(db: Session, batch_tag: str, apply: bool = False, actor: str | None = None) -> dict[str, object]:
    bindings = db.execute(
        select(
            models.ListingSkuBinding.main_sku,
            models.ListingRecord.country,
            models.ListingRecord.site,
        ).join(models.ListingRecord, models.ListingRecord.id == models.ListingSkuBinding.listing_record_id)
        .where(models.ListingRecord.status == "active")
    ).all()
    listed_keys = {
        (main_sku, normalize_site_code(site or country))
        for main_sku, country, site in bindings
        if main_sku
    }
    listed_any_country = {main_sku for main_sku, _ in listed_keys}

    counts: Counter[str] = Counter()
    activated: list[dict[str, str]] = []
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(models.SalesClaimForecast.downstream_status.in_(ELIGIBLE_STATUSES))
    ).all()
    for claim, opportunity in rows:
        key = (opportunity.main_sku, normalize_site_code(opportunity.site or opportunity.country))
        if key in listed_keys:
            counts[f"activated_from_{claim.downstream_status}"] += 1
            activated.append({"claim_id": claim.id, "from": claim.downstream_status, "main_sku": opportunity.main_sku})
            if apply:
                previous = claim.downstream_status
                claim.downstream_status = CLAIM_LISTING_OBSERVATION
                audit(
                    db,
                    AUDIT_ACTION,
                    "sales_claim_forecast",
                    claim.id,
                    {"from": previous, "to": CLAIM_LISTING_OBSERVATION, "batch_tag": batch_tag,
                     "main_sku": opportunity.main_sku},
                    actor,
                )
        elif opportunity.main_sku in listed_any_country:
            counts["skipped_country_mismatch"] += 1
        else:
            counts["not_listed"] += 1
    return {
        "mode": "apply" if apply else "dry-run",
        "batch_tag": batch_tag,
        "eligible": len(rows),
        "activated": len(activated),
        **dict(sorted(counts.items())),
        "sample": activated[:10],
    }


def revert_activation(db: Session, batch_tag: str, actor: str | None = None) -> dict[str, int]:
    reverted = 0
    entries = db.scalars(
        select(models.AuditLog).where(models.AuditLog.action == AUDIT_ACTION)
    ).all()
    for entry in entries:
        detail = entry.detail or {}
        if detail.get("batch_tag") != batch_tag or not entry.entity_id:
            continue
        claim = db.get(models.SalesClaimForecast, entry.entity_id)
        if claim is not None and claim.downstream_status == CLAIM_LISTING_OBSERVATION:
            claim.downstream_status = detail.get("from", "waiting_listing")
            reverted += 1
    audit(db, "history.claim_listing_activation_reverted", "sales_claim_forecast", None,
          {"batch_tag": batch_tag, "reverted": reverted}, actor)
    return {"reverted": reverted}


def main() -> None:
    parser = argparse.ArgumentParser(description="把已有 active 刊登绑定的认领补到刊登观察中（可整批撤销）")
    parser.add_argument("--batch-tag", default="activation-20260726")
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--revert", action="store_true", help="按 batch-tag 整批撤销")
    parser.add_argument("--actor", default="history_listing_activation")
    args = parser.parse_args()

    from app.config import get_settings
    from app.db import SessionLocal

    if args.apply_dev or args.revert:
        settings = get_settings()
        if settings.app_env not in APPLY_ALLOWED_ENVS:
            raise SystemExit(f"blocked: app_env={settings.app_env}")
    with SessionLocal() as db:
        if args.revert:
            report: dict[str, object] = revert_activation(db, args.batch_tag, actor=args.actor)
            db.commit()
        else:
            report = activate_listed_claims(db, args.batch_tag, apply=args.apply_dev, actor=args.actor)
            if args.apply_dev:
                db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
