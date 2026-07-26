from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.historical_archive_import import (
    APPLY_ALLOWED_ENVS,
    HISTORICAL_ARCHIVE_SOURCE_TYPE,
    business_period_from_bucket,
)


def backfill_business_periods(db: Session, apply: bool = False) -> dict[str, object]:
    updated: Counter[str] = Counter()
    unmatched = 0
    unchanged = 0
    for opportunity in db.scalars(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == HISTORICAL_ARCHIVE_SOURCE_TYPE
        )
    ):
        bucket = ((opportunity.snapshot or {}).get("raw_classification_record") or {}).get("product_bucket")
        period = business_period_from_bucket(bucket)
        if period is None:
            unmatched += 1
            continue
        if opportunity.batch == period:
            unchanged += 1
            continue
        updated[period] += 1
        if apply:
            opportunity.batch = period
    return {
        "mode": "apply" if apply else "dry-run",
        "updated": sum(updated.values()),
        "updated_by_period": dict(sorted(updated.items())),
        "unchanged": unchanged,
        "unmatched": unmatched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="历史档案期数回填（货品列 开发新品NNNN期 → 开发NNNN期）")
    parser.add_argument("--apply-dev", action="store_true", help="真正写库（默认 dry-run）")
    args = parser.parse_args()

    from app.config import get_settings
    from app.db import SessionLocal

    if args.apply_dev:
        settings = get_settings()
        if settings.app_env not in APPLY_ALLOWED_ENVS:
            raise SystemExit(f"apply blocked: app_env={settings.app_env} 不在允许环境 {sorted(APPLY_ALLOWED_ENVS)}")
    with SessionLocal() as db:
        report = backfill_business_periods(db, apply=args.apply_dev)
        if args.apply_dev:
            db.commit()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
