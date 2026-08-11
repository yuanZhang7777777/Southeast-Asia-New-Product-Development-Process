from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import and_, delete, exists, func, select, update

from app import models
from app.db import SessionLocal


RENAME_PERIODS = {
    "PLM新品到货20260727-0802": "PLM到货新增SKU20260727-0802",
    "PLM新品到货20260803": "PLM到货新增SKU20260803",
    "PLM到货20260727-0802": "PLM到货新增SKU20260727-0802",
    "PLM到货20260727-0803": "PLM到货新增SKU20260803",
}


def duplicate_tail_ids(db) -> list[str]:
    claim = models.SalesClaimForecast
    tail = claim.__table__.alias("tail")
    hist = claim.__table__.alias("hist")

    candidate_ids = [
        row[0]
        for row in db.execute(
            select(tail.c.id)
            .select_from(
                tail.join(
                    hist,
                    and_(
                        hist.c.opportunity_id == tail.c.opportunity_id,
                        hist.c.salesperson_name == tail.c.salesperson_name,
                        hist.c.claim_result == tail.c.claim_result,
                        hist.c.claim_daily_sales.is_not_distinct_from(tail.c.claim_daily_sales),
                    ),
                )
            )
            .where(
                tail.c.claim_source == "selection1_claim_feedback",
                tail.c.source_column == "selection1_tail",
                hist.c.claim_source == "history_selection1",
                hist.c.source_column == "history_selection1",
                tail.c.secondary_research_submitted_at.is_(None),
                tail.c.secondary_competitor_url.is_(None),
                tail.c.secondary_conclusion.is_(None),
                tail.c.product_positioning.is_(None),
                tail.c.secondary_target_daily_sales.is_(None),
                tail.c.secondary_selling_points.is_(None),
            )
        )
    ]
    if not candidate_ids:
        return []
    referenced = set()
    checks = [
        (models.ReviewRecord, models.ReviewRecord.claim_record_id),
        (models.StockingRequest, models.StockingRequest.claim_record_id),
        (models.ExportRow, models.ExportRow.claim_record_id),
        (models.ArrivalRecord, models.ArrivalRecord.claim_record_id),
        (models.ListingSkuBinding, models.ListingSkuBinding.claim_record_id),
    ]
    for model, column in checks:
        referenced.update(db.scalars(select(column).select_from(model).where(column.in_(candidate_ids))).all())
    return [item_id for item_id in candidate_ids if item_id not in referenced]


def run(apply: bool) -> dict:
    with SessionLocal() as db:
        tail_ids = duplicate_tail_ids(db)
        sample = []
        if tail_ids:
            sample = [
                dict(row._mapping)
                for row in db.execute(
                    select(
                        models.NewProductOpportunity.batch,
                        models.NewProductOpportunity.main_sku,
                        models.NewProductOpportunity.sub_sku,
                        models.SalesClaimForecast.salesperson_name,
                        models.SalesClaimForecast.claim_result,
                        models.SalesClaimForecast.claim_daily_sales,
                        models.SalesClaimForecast.id,
                    )
                    .join(models.SalesClaimForecast, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
                    .where(models.SalesClaimForecast.id.in_(tail_ids))
                    .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.main_sku, models.NewProductOpportunity.sub_sku)
                    .limit(10)
                )
            ]
        result = {
            "apply": apply,
            "delete_duplicate_selection1_tail": len(tail_ids),
            "delete_sample": sample,
            "renamed": {},
        }
        if apply and tail_ids:
            db.execute(delete(models.SalesClaimForecast).where(models.SalesClaimForecast.id.in_(tail_ids)))
            db.add(
                models.AuditLog(
                    actor_name="Codex",
                    action="selection1_tail_duplicate_claim_cleanup",
                    entity_type="maintenance",
                    detail={
                        "deleted_count": len(tail_ids),
                        "reason": "history_selection1 already carries the same owner/result/daily-sales fact with source metadata",
                        "ran_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
        for old, new in RENAME_PERIODS.items():
            opp_count = db.scalar(select(func.count()).select_from(models.NewProductOpportunity).where(models.NewProductOpportunity.batch == old)) or 0
            import_count = db.scalar(select(func.count()).select_from(models.ImportBatch).where(models.ImportBatch.business_period == old)) or 0
            listing_count = db.scalar(select(func.count()).select_from(models.ListingRecord).where(models.ListingRecord.business_period == old)) or 0
            if apply:
                if opp_count:
                    db.execute(update(models.NewProductOpportunity).where(models.NewProductOpportunity.batch == old).values(batch=new))
                if import_count:
                    db.execute(update(models.ImportBatch).where(models.ImportBatch.business_period == old).values(business_period=new))
                if listing_count:
                    db.execute(update(models.ListingRecord).where(models.ListingRecord.business_period == old).values(business_period=new))
            result["renamed"][old] = {
                "to": new,
                "opportunities": int(opp_count),
                "import_batches": int(import_count),
                "listings": int(listing_count),
            }
        if apply:
            db.commit()
        else:
            db.rollback()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.apply), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
