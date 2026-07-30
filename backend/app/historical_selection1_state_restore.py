"""Activate only explicit-window historical selection-1 new arrivals."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_selection1_claim_backfill import claim_fields_from_snapshot, decide_claim
from app.historical_selection1_import import SOURCE_TYPE
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE
from app.services import audit, open_secondary_research
from app.site_codes import normalize_site_code
from app.workflow_status import CLAIM_WAITING_ARRIVAL, OPPORTUNITY_CLAIM_SUBMITTED

MIGRATION_SOURCE = "historical_selection1_state_restore"
ACTIVE_SOURCE_COLUMN = "platform"
CLAIM_EVIDENCE_SOURCE_COLUMNS = ("history_selection1", "selection1_tail")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(country: Any, sub_sku: Any) -> tuple[str, str]:
    return (normalize_site_code(country) or "", _text(sub_sku).upper())


def _plm_index(history: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in history.get("new_arrival_matches") or []:
        key = _key(row.get("country"), row.get("sub_sku"))
        if key[0] and key[1]:
            result[key] = row
    for row in history.get("matches") or []:
        key = _key(row.get("country"), row.get("sub_sku"))
        if key[0] and key[1]:
            result.setdefault(key, row)
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


def _arrival_date(row: dict[str, Any]) -> date | None:
    arrived_at = _arrived_at(row)
    return arrived_at.date() if arrived_at else None


def restore_selection1_states(
    db: Session,
    plm_history: dict[str, Any],
    *,
    apply: bool = False,
    actor: str | None = None,
    arrival_from: date | None = None,
    arrival_to: date | None = None,
) -> dict[str, int]:
    """Open secondary research only for claimed, explicit-window PLM new arrivals."""
    if (arrival_from is None) != (arrival_to is None):
        raise ValueError("arrival_from and arrival_to must be provided together")
    if arrival_from and arrival_to and arrival_from > arrival_to:
        raise ValueError("arrival_from must not be after arrival_to")

    counts = {
        "total": 0,
        "activation_window_required": 0,
        "not_new_arrival": 0,
        "outside_arrival_window": 0,
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
    claim_evidence = {}
    for claim in db.scalars(
        select(models.SalesClaimForecast).where(
            models.SalesClaimForecast.source_column.in_(CLAIM_EVIDENCE_SOURCE_COLUMNS),
            models.SalesClaimForecast.claim_result == "claim",
        )
    ):
        claim_evidence.setdefault(claim.opportunity_id, claim)
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type.in_([SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE]))
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        counts["total"] += 1
        if arrival_from is None:
            counts["activation_window_required"] += 1
            continue
        if opportunity.id in existing:
            counts["skipped_existing"] += 1
            continue
        evidence = claim_evidence.get(opportunity.id)
        if evidence is not None:
            payload = {
                "salesperson_name": evidence.salesperson_name,
                "claim_daily_sales": evidence.claim_daily_sales,
            }
        else:
            snapshot = opportunity.snapshot or {}
            source_snapshot = snapshot.get("historical_selection1") if isinstance(snapshot, dict) else None
            outcome, payload = decide_claim(claim_fields_from_snapshot(source_snapshot or snapshot))
            if outcome != "claim" or payload is None:
                continue
        plm_row = plm_rows.get(_key(opportunity.site or opportunity.country, opportunity.sub_sku))
        if not plm_row or plm_row.get("arrival_type") != "new_arrival":
            counts["not_new_arrival"] += 1
            continue
        plm_date = _arrival_date(plm_row)
        if plm_date is None or plm_date < arrival_from or plm_date > arrival_to:
            counts["outside_arrival_window"] += 1
            continue

        owner = _text(plm_row.get("salesperson_name")) or _text(payload["salesperson_name"])
        counts["waiting_secondary_research"] += 1
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
            opportunity.current_status = OPPORTUNITY_CLAIM_SUBMITTED
        if claim.id not in arrivals_by_claim:
            db.add(
                models.ArrivalRecord(
                    opportunity_id=opportunity.id,
                    claim_record_id=claim.id,
                    salesperson_name=owner,
                    country=plm_row.get("country") or opportunity.country,
                    warehouse=plm_row.get("warehouse"),
                    arrived_at=_arrived_at(plm_row),
                    note="历史PLM新品到货窗口回填",
                )
            )
        open_secondary_research(db, claim.id, _arrived_at(plm_row))
    if apply:
        audit(db, "history.selection1_state_restored", "new_product_opportunity", None, counts, actor)
        db.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="选品1历史新品到货窗口激活（仅显式窗口内新品）")
    parser.add_argument("--plm-history", required=True)
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--arrival-from", type=date.fromisoformat)
    parser.add_argument("--arrival-to", type=date.fromisoformat)
    parser.add_argument("--actor", default=MIGRATION_SOURCE)
    args = parser.parse_args()

    from app.config import get_settings
    from app.db import SessionLocal

    if args.apply_dev and get_settings().app_env not in APPLY_ALLOWED_ENVS:
        raise SystemExit("apply blocked outside development")
    history = json.loads(Path(args.plm_history).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        report = restore_selection1_states(
            db,
            history,
            apply=args.apply_dev,
            actor=args.actor,
            arrival_from=args.arrival_from,
            arrival_to=args.arrival_to,
        )
        if args.apply_dev:
            db.commit()
    print(json.dumps({"mode": "apply" if args.apply_dev else "dry-run", **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
