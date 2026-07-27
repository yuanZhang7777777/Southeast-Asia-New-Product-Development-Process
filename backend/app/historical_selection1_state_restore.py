"""Restore actionable selection-1 history from archived rows and PLM facts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_selection1_claim_backfill import claim_fields_from_snapshot, decide_claim
from app.historical_selection1_import import SOURCE_TYPE
from app.services import audit, open_secondary_research
from app.site_codes import normalize_site_code
from app.workflow_status import (
    CLAIM_WAITING_ARRIVAL,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_CLAIM_SUBMITTED,
    OPPORTUNITY_WAITING_ARRIVAL,
)

MIGRATION_SOURCE = "historical_selection1_state_restore"
ACTIVE_SOURCE_COLUMN = "platform"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(country: Any, sub_sku: Any) -> tuple[str, str]:
    return (normalize_site_code(country) or "", _text(sub_sku).upper())


def _plm_index(history: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in history.get("matches") or []:
        key = _key(row.get("country"), row.get("sub_sku"))
        if key[0] and key[1]:
            result[key] = row
    return result


def _arrived_at(row: dict[str, Any]) -> datetime | None:
    value = _text(row.get("latest_storage_time") or row.get("arrival_date"))
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def restore_selection1_states(
    db: Session,
    plm_history: dict[str, Any],
    *,
    apply: bool = False,
    actor: str | None = None,
) -> dict[str, int]:
    counts = {
        "total": 0,
        "claim": 0,
        "reject": 0,
        "unclaimed": 0,
        "waiting_arrival": 0,
        "waiting_secondary_research": 0,
        "skipped_existing": 0,
    }
    existing = set(
        db.scalars(
            select(models.SalesClaimForecast.opportunity_id).where(
                models.SalesClaimForecast.source_column == ACTIVE_SOURCE_COLUMN
            )
        )
    )
    arrivals_by_claim = set(db.scalars(select(models.ArrivalRecord.claim_record_id)).all())
    plm_rows = _plm_index(plm_history)
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type == SOURCE_TYPE)
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        counts["total"] += 1
        if opportunity.id in existing:
            counts["skipped_existing"] += 1
            continue
        outcome, payload = decide_claim(claim_fields_from_snapshot(opportunity.snapshot))
        if outcome in {"no_claim_info", "ambiguous"}:
            counts["unclaimed"] += 1
            continue
        counts[outcome] += 1
        if outcome == "reject":
            if apply:
                db.add(
                    models.SalesClaimForecast(
                        opportunity_id=opportunity.id,
                        source_column=ACTIVE_SOURCE_COLUMN,
                        claim_source=MIGRATION_SOURCE,
                        **payload,
                    )
                )
                if opportunity.current_status == "historical_archive":
                    opportunity.current_status = OPPORTUNITY_CLAIM_REJECTED
            continue

        plm_row = plm_rows.get(_key(opportunity.site or opportunity.country, opportunity.sub_sku))
        owner = _text((plm_row or {}).get("salesperson_name")) or _text(payload["salesperson_name"])
        if plm_row:
            counts["waiting_secondary_research"] += 1
        else:
            counts["waiting_arrival"] += 1
        if not apply:
            continue

        claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name=owner,
            claim_result="claim",
            claim_daily_sales=payload["claim_daily_sales"],
            source_column=ACTIVE_SOURCE_COLUMN,
            claim_source=MIGRATION_SOURCE,
            downstream_status=CLAIM_WAITING_ARRIVAL,
            note=f"历史认领人：{payload['salesperson_name']}" if owner != payload["salesperson_name"] else None,
        )
        db.add(claim)
        db.flush()
        if opportunity.current_status == "historical_archive":
            opportunity.current_status = OPPORTUNITY_CLAIM_SUBMITTED if plm_row else OPPORTUNITY_WAITING_ARRIVAL
        if plm_row:
            if claim.id not in arrivals_by_claim:
                db.add(
                    models.ArrivalRecord(
                        opportunity_id=opportunity.id,
                        claim_record_id=claim.id,
                        salesperson_name=owner,
                        country=plm_row.get("country") or opportunity.country,
                        warehouse=plm_row.get("warehouse"),
                        arrived_at=_arrived_at(plm_row),
                        note="历史PLM Excel 精确到货回填",
                    )
                )
            open_secondary_research(db, claim.id, _arrived_at(plm_row))
    if apply:
        audit(db, "history.selection1_state_restored", "new_product_opportunity", None, counts, actor)
        db.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="选品1历史认领与PLM到货状态恢复")
    parser.add_argument("--plm-history", required=True)
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--actor", default=MIGRATION_SOURCE)
    args = parser.parse_args()

    from app.config import get_settings
    from app.db import SessionLocal

    if args.apply_dev and get_settings().app_env not in APPLY_ALLOWED_ENVS:
        raise SystemExit("apply blocked outside development")
    history = json.loads(Path(args.plm_history).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        report = restore_selection1_states(db, history, apply=args.apply_dev, actor=args.actor)
        if args.apply_dev:
            db.commit()
    print(json.dumps({"mode": "apply" if args.apply_dev else "dry-run", **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
