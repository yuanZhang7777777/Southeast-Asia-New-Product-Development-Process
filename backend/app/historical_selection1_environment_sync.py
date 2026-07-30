"""Synchronize the cleaned Selection1 historical foundation into an environment.

This is deliberately narrow: Selection1 archive rows + historical claim facts +
visibility cleanup. It does not create flow tasks, secondary research, listings,
observations, PLM records, or DingTalk notifications.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, services
from app.config import get_settings
from app.db import SessionLocal
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_central_import import ARCHIVE_STATUS
from app.historical_opportunity_dedupe import canonical_business_period
from app.historical_selection1_claim_backfill import (
    CANONICAL_CLAIM_PERIODS,
    CLAIM_SOURCE_COLUMN,
    backfill_selection1_claims,
    normalize_selection1_claims,
)
from app.historical_selection1_import import (
    SOURCE_TYPE as HISTORY_SELECTION1_SOURCE_TYPE,
    _opportunity_identity,
    _row_identity,
    apply_selection1_rows,
    normalize_selection1_history_rows,
    plan_selection1_rows,
)
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE
from app.workflow_status import OPPORTUNITY_DISABLED

DEFAULT_CLEANUP_SOURCE_TYPES = (
    HISTORY_SELECTION1_SOURCE_TYPE,
    CURRENT_SELECTION1_SOURCE_TYPE,
    "historical_market_monitor_archive",
)


def _load_rows(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain rows[]")
    return payload


def _source_label(payload: dict[str, Any], fallback: Path) -> str:
    return str(payload.get("source_file") or fallback.name)


def _clean_scope(rows: list[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str, str, str, str]]]:
    normalized = normalize_selection1_history_rows(rows)["rows"]
    periods = {str(row.get("batch") or "") for row in normalized if row.get("batch")}
    keys = {_row_identity(row) for row in normalized if row.get("main_sku") and row.get("sub_sku")}
    return periods, keys


def plan_visibility_cleanup(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source_types: tuple[str, ...] = DEFAULT_CLEANUP_SOURCE_TYPES,
) -> dict[str, Any]:
    allowed_periods, clean_keys = _clean_scope(rows)
    candidates: list[models.NewProductOpportunity] = []
    restore_candidates: list[models.NewProductOpportunity] = []
    by_reason: Counter[str] = Counter()
    by_period: Counter[str] = Counter()
    kept = already_disabled = 0

    opportunities = db.scalars(
        select(models.NewProductOpportunity).where(models.NewProductOpportunity.source_type.in_(source_types))
    )
    for opportunity in opportunities:
        period = canonical_business_period(opportunity.batch, source_type=opportunity.source_type)
        clean_match = period in allowed_periods and _opportunity_identity(opportunity) in clean_keys
        if clean_match:
            kept += 1
            if opportunity.current_status == OPPORTUNITY_DISABLED:
                restore_candidates.append(opportunity)
            continue
        if opportunity.current_status == OPPORTUNITY_DISABLED:
            already_disabled += 1
            continue
        candidates.append(opportunity)
        reason = "period_not_in_scope" if period not in allowed_periods else "identity_not_in_clean_source"
        by_reason[reason] += 1
        by_period[period or "-"] += 1

    return {
        "kept": kept,
        "to_restore": len(restore_candidates),
        "to_disable": len(candidates),
        "already_disabled": already_disabled,
        "disable_by_reason": dict(sorted(by_reason.items())),
        "disable_by_period": dict(sorted(by_period.items())),
        "disable_samples": [_sample_opportunity(item) for item in candidates[:50]],
        "_disable_candidates": candidates,
        "_restore_candidates": restore_candidates,
    }


def _sample_opportunity(opportunity: models.NewProductOpportunity) -> dict[str, Any]:
    return {
        "id": opportunity.id,
        "source_type": opportunity.source_type,
        "batch": opportunity.batch,
        "country": opportunity.country,
        "site": opportunity.site,
        "main_sku": opportunity.main_sku,
        "sub_sku": opportunity.sub_sku,
        "current_status": opportunity.current_status,
        "source_file": opportunity.source_file,
        "source_sheet": opportunity.source_sheet,
        "source_row": opportunity.source_row,
    }


def apply_visibility_cleanup(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    actor: str | None,
    source_types: tuple[str, ...] = DEFAULT_CLEANUP_SOURCE_TYPES,
) -> dict[str, Any]:
    report = plan_visibility_cleanup(db, rows, source_types=source_types)
    disable_candidates = report.pop("_disable_candidates")
    restore_candidates = report.pop("_restore_candidates")
    disabled = services.set_opportunities_disabled(
        db,
        disable_candidates,
        True,
        "selection1 clean environment sync",
        actor,
        scope="selection1_environment_sync",
    )
    restored = services.set_opportunities_disabled(
        db,
        restore_candidates,
        False,
        "selection1 clean environment sync",
        actor,
        scope="selection1_environment_sync",
    )
    for opportunity in restore_candidates:
        if opportunity.source_type == HISTORY_SELECTION1_SOURCE_TYPE and opportunity.current_status == "pending_assignment":
            opportunity.current_status = ARCHIVE_STATUS
    report["disabled"] = disabled
    report["restored"] = restored
    return report


def readback_selection1_summary(db: Session) -> dict[str, Any]:
    opportunities = list(
        db.scalars(
            select(models.NewProductOpportunity).where(
                models.NewProductOpportunity.source_type.in_(
                    (HISTORY_SELECTION1_SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE)
                ),
                models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
            )
        )
    )
    claims = list(
        db.scalars(select(models.SalesClaimForecast).where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN))
    )
    by_period: dict[str, Counter[str]] = defaultdict(Counter)
    for opportunity in opportunities:
        by_period[opportunity.batch or "-"]["opportunities"] += 1
    opportunity_period = {opportunity.id: opportunity.batch or "-" for opportunity in opportunities}
    for claim in claims:
        period = opportunity_period.get(claim.opportunity_id)
        if period:
            by_period[period][claim.claim_result or "-"] += 1
    return {
        "visible_selection1_opportunities": len(opportunities),
        "history_selection1_claims": len(claims),
        "by_period": {period: dict(counts) for period, counts in sorted(by_period.items())},
    }


def sync_selection1_environment(
    db: Session,
    payload: dict[str, Any],
    *,
    rows_path: Path,
    apply: bool,
    batch_tag: str,
    actor: str | None,
    cleanup_source_types: tuple[str, ...] = DEFAULT_CLEANUP_SOURCE_TYPES,
) -> dict[str, Any]:
    rows = payload["rows"]
    source_label = _source_label(payload, rows_path)
    source_sha256 = payload.get("source_sha256")
    report: dict[str, Any] = {
        "source_file": source_label,
        "source_sha256": source_sha256,
        "batch_tag": batch_tag,
        "apply": apply,
        "plan": plan_selection1_rows(db, rows),
        "cleanup_plan": plan_visibility_cleanup(db, rows, source_types=cleanup_source_types),
    }
    report["cleanup_plan"].pop("_disable_candidates", None)
    report["cleanup_plan"].pop("_restore_candidates", None)
    if not apply:
        return report

    app_env = get_settings().app_env
    if app_env not in APPLY_ALLOWED_ENVS:
        raise RuntimeError(f"APP_ENV={app_env!r} is not allowed for historical writes")
    report["import"] = apply_selection1_rows(
        db,
        rows,
        source_label=source_label,
        batch_tag=batch_tag,
        imported_by=actor,
        source_sha256=source_sha256,
    )
    report["claims"] = backfill_selection1_claims(
        db,
        apply=True,
        actor=actor,
        periods=CANONICAL_CLAIM_PERIODS,
    )
    report["claim_normalization"] = normalize_selection1_claims(
        db,
        apply=True,
        actor=actor,
        periods=CANONICAL_CLAIM_PERIODS,
    )
    report["cleanup"] = apply_visibility_cleanup(db, rows, actor=actor, source_types=cleanup_source_types)
    report["readback"] = readback_selection1_summary(db)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Selection1 historical clean sync: import + claims + visibility cleanup.")
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--batch-tag", default="selection1-clean-env-sync-20260729")
    parser.add_argument("--actor", default="codex")
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--cleanup-source-type", action="append", default=None)
    args = parser.parse_args()

    payload = _load_rows(args.rows)
    source_types = tuple(args.cleanup_source_type or DEFAULT_CLEANUP_SOURCE_TYPES)
    db = SessionLocal()
    try:
        report = sync_selection1_environment(
            db,
            payload,
            rows_path=args.rows,
            apply=args.apply_dev,
            batch_tag=args.batch_tag,
            actor=args.actor,
            cleanup_source_types=source_types,
        )
        if args.apply_dev:
            db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
