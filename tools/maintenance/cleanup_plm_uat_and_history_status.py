from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, exists, func, select, update

from app import models
from app.db import SessionLocal
from app.workflow_status import OPPORTUNITY_CONFIRMED_NOT_CLAIM


DELETE_PERIODS = ("UAT0804全链路期", "PLM到货20260804")
RENAME_PERIODS = {
    "PLM到货20260727-0802": "PLM新品到货20260727-0802",
    "PLM到货20260727-0803": "PLM新品到货20260803",
}


def _ids(rows) -> list[str]:
    return [row for row in rows if row]


def _delete(db, model, where, apply: bool) -> int:
    count = db.scalar(select(func.count()).select_from(model).where(where)) or 0
    if apply and count:
        db.execute(delete(model).where(where))
    return int(count)


def _collect_delete_targets(db) -> dict[str, list[str]]:
    opp_ids = _ids(db.scalars(select(models.NewProductOpportunity.id).where(models.NewProductOpportunity.batch.in_(DELETE_PERIODS))).all())
    claim_ids = _ids(db.scalars(select(models.SalesClaimForecast.id).where(models.SalesClaimForecast.opportunity_id.in_(opp_ids))).all()) if opp_ids else []
    flow_ids = _ids(db.scalars(select(models.FlowInstance.id).where(models.FlowInstance.opportunity_id.in_(opp_ids))).all()) if opp_ids else []
    task_ids = _ids(db.scalars(select(models.FlowTask.id).where(models.FlowTask.flow_instance_id.in_(flow_ids))).all()) if flow_ids else []
    stocking_ids = _ids(
        db.scalars(
            select(models.StockingRequest.id).where(
                (models.StockingRequest.opportunity_id.in_(opp_ids))
                | (models.StockingRequest.claim_record_id.in_(claim_ids))
            )
        ).all()
    ) if opp_ids or claim_ids else []
    listing_ids = set()
    if DELETE_PERIODS:
        listing_ids.update(db.scalars(select(models.ListingRecord.id).where(models.ListingRecord.business_period.in_(DELETE_PERIODS))).all())
    if opp_ids or claim_ids:
        listing_ids.update(
            db.scalars(
                select(models.ListingSkuBinding.listing_record_id).where(
                    (models.ListingSkuBinding.opportunity_id.in_(opp_ids))
                    | (models.ListingSkuBinding.claim_record_id.in_(claim_ids))
                )
            ).all()
        )
    arrival_rows = []
    if opp_ids or claim_ids:
        arrival_rows = db.execute(
            select(
                models.ArrivalRecord.id,
                models.ArrivalRecord.plm_arrival_batch_id,
                models.ArrivalRecord.plm_arrival_item_id,
            ).where(
                (models.ArrivalRecord.opportunity_id.in_(opp_ids))
                | (models.ArrivalRecord.claim_record_id.in_(claim_ids))
            )
        ).all()
    plm_item_ids = {row.plm_arrival_item_id for row in arrival_rows if row.plm_arrival_item_id}
    plm_item_ids.update(
        db.scalars(select(models.PlmArrivalItem.id).where(models.PlmArrivalItem.matched_claim_record_id.in_(claim_ids))).all()
        if claim_ids
        else []
    )
    plm_batch_ids = {row.plm_arrival_batch_id for row in arrival_rows if row.plm_arrival_batch_id}
    if plm_item_ids:
        plm_batch_ids.update(
            db.scalars(select(models.PlmArrivalItem.batch_id).where(models.PlmArrivalItem.id.in_(plm_item_ids))).all()
        )
    import_batch_ids = set(
        db.scalars(select(models.NewProductOpportunity.import_batch_id).where(models.NewProductOpportunity.id.in_(opp_ids))).all()
        if opp_ids
        else []
    )
    import_batch_ids.update(
        db.scalars(select(models.ImportBatch.id).where(models.ImportBatch.business_period.in_(DELETE_PERIODS))).all()
    )
    audit_entity_ids = set(opp_ids) | set(claim_ids) | set(flow_ids) | set(task_ids) | set(stocking_ids) | set(listing_ids)
    return {
        "opportunity": opp_ids,
        "claim": claim_ids,
        "flow": flow_ids,
        "task": task_ids,
        "stocking": stocking_ids,
        "listing": _ids(list(listing_ids)),
        "plm_item": _ids(list(plm_item_ids)),
        "plm_batch": _ids(list(plm_batch_ids)),
        "import_batch": _ids(list(import_batch_ids)),
        "audit_entity": _ids(list(audit_entity_ids)),
    }


def _history_reject_candidates(db) -> list[str]:
    opp = models.NewProductOpportunity
    claim = models.SalesClaimForecast
    flow = models.FlowInstance
    task = models.FlowTask
    has_history_reject = exists(
        select(claim.id).where(
            claim.opportunity_id == opp.id,
            claim.claim_source == "history_selection1",
            claim.claim_result == "reject",
        )
    )
    has_any_claim = exists(select(claim.id).where(claim.opportunity_id == opp.id, claim.claim_result == "claim"))
    has_flow_task = exists(select(task.id).join(flow, flow.id == task.flow_instance_id).where(flow.opportunity_id == opp.id))
    return _ids(
        db.scalars(
            select(opp.id).where(
                has_history_reject,
                ~has_any_claim,
                ~has_flow_task,
                opp.current_status.in_(("pending_assignment", "claim_rejected")),
            )
        ).all()
    )


def run(apply: bool) -> dict:
    with SessionLocal() as db:
        targets = _collect_delete_targets(db)
        status_fix_ids = _history_reject_candidates(db)
        status_before = Counter(
            db.scalars(select(models.NewProductOpportunity.current_status).where(models.NewProductOpportunity.id.in_(status_fix_ids))).all()
        )
        result = {
            "apply": apply,
            "delete_periods": DELETE_PERIODS,
            "rename_periods": RENAME_PERIODS,
            "delete_targets": {key: len(value) for key, value in targets.items()},
            "deleted": {},
            "renamed": {},
            "history_reject_status_fix": {
                "count": len(status_fix_ids),
                "before": dict(status_before),
                "after": OPPORTUNITY_CONFIRMED_NOT_CLAIM,
            },
        }
        if targets["task"]:
            result["deleted"]["notification_log"] = _delete(db, models.NotificationLog, models.NotificationLog.task_id.in_(targets["task"]), apply)
        if targets["opportunity"]:
            result["deleted"]["notification_log_by_opportunity"] = _delete(
                db, models.NotificationLog, models.NotificationLog.opportunity_id.in_(targets["opportunity"]), apply
            )
        if targets["audit_entity"]:
            result["deleted"]["audit_log"] = _delete(db, models.AuditLog, models.AuditLog.entity_id.in_(targets["audit_entity"]), apply)
        if targets["listing"]:
            result["deleted"]["item_observation_period"] = _delete(
                db, models.ItemObservationPeriod, models.ItemObservationPeriod.listing_record_id.in_(targets["listing"]), apply
            )
            result["deleted"]["listing_sku_binding"] = _delete(
                db, models.ListingSkuBinding, models.ListingSkuBinding.listing_record_id.in_(targets["listing"]), apply
            )
            result["deleted"]["listing_record"] = _delete(db, models.ListingRecord, models.ListingRecord.id.in_(targets["listing"]), apply)
        if targets["opportunity"] or targets["claim"] or targets["stocking"]:
            result["deleted"]["export_row"] = _delete(
                db,
                models.ExportRow,
                (models.ExportRow.opportunity_id.in_(targets["opportunity"]))
                | (models.ExportRow.claim_record_id.in_(targets["claim"]))
                | (models.ExportRow.stocking_request_id.in_(targets["stocking"])),
                apply,
            )
        if targets["stocking"]:
            result["deleted"]["stocking_request"] = _delete(db, models.StockingRequest, models.StockingRequest.id.in_(targets["stocking"]), apply)
        if targets["opportunity"] or targets["claim"] or targets["plm_item"] or targets["plm_batch"]:
            result["deleted"]["arrival_record"] = _delete(
                db,
                models.ArrivalRecord,
                (models.ArrivalRecord.opportunity_id.in_(targets["opportunity"]))
                | (models.ArrivalRecord.claim_record_id.in_(targets["claim"]))
                | (models.ArrivalRecord.plm_arrival_item_id.in_(targets["plm_item"]))
                | (models.ArrivalRecord.plm_arrival_batch_id.in_(targets["plm_batch"])),
                apply,
            )
        if targets["plm_item"]:
            result["deleted"]["plm_arrival_item"] = _delete(db, models.PlmArrivalItem, models.PlmArrivalItem.id.in_(targets["plm_item"]), apply)
        if targets["claim"] or targets["opportunity"]:
            result["deleted"]["review_record"] = _delete(
                db,
                models.ReviewRecord,
                (models.ReviewRecord.opportunity_id.in_(targets["opportunity"]))
                | (models.ReviewRecord.claim_record_id.in_(targets["claim"])),
                apply,
            )
        if targets["opportunity"]:
            result["deleted"]["supply_chain_quote"] = _delete(
                db, models.SupplyChainQuote, models.SupplyChainQuote.opportunity_id.in_(targets["opportunity"]), apply
            )
            result["deleted"]["market_research_item"] = _delete(
                db, models.MarketResearchItem, models.MarketResearchItem.opportunity_id.in_(targets["opportunity"]), apply
            )
            result["deleted"]["source_record_snapshot"] = _delete(
                db, models.SourceRecordSnapshot, models.SourceRecordSnapshot.opportunity_id.in_(targets["opportunity"]), apply
            )
            result["deleted"]["sales_claim_forecast"] = _delete(
                db, models.SalesClaimForecast, models.SalesClaimForecast.opportunity_id.in_(targets["opportunity"]), apply
            )
        if targets["task"]:
            result["deleted"]["flow_task"] = _delete(db, models.FlowTask, models.FlowTask.id.in_(targets["task"]), apply)
        if targets["flow"]:
            result["deleted"]["flow_instance"] = _delete(db, models.FlowInstance, models.FlowInstance.id.in_(targets["flow"]), apply)
        if targets["opportunity"]:
            result["deleted"]["new_product_opportunity"] = _delete(
                db, models.NewProductOpportunity, models.NewProductOpportunity.id.in_(targets["opportunity"]), apply
            )
        if targets["import_batch"]:
            removable_import_batches = [
                item_id
                for item_id in targets["import_batch"]
                if not db.scalar(select(models.NewProductOpportunity.id).where(models.NewProductOpportunity.import_batch_id == item_id).limit(1))
                and not db.scalar(select(models.SourceRecordSnapshot.id).where(models.SourceRecordSnapshot.import_batch_id == item_id).limit(1))
            ]
            result["deleted"]["import_batch"] = _delete(
                db, models.ImportBatch, models.ImportBatch.id.in_(removable_import_batches), apply
            ) if removable_import_batches else 0
        if targets["plm_batch"]:
            removable_plm_batches = [
                item_id
                for item_id in targets["plm_batch"]
                if not db.scalar(select(models.PlmArrivalItem.id).where(models.PlmArrivalItem.batch_id == item_id).limit(1))
                and not db.scalar(select(models.ArrivalRecord.id).where(models.ArrivalRecord.plm_arrival_batch_id == item_id).limit(1))
            ]
            result["deleted"]["plm_arrival_batch"] = _delete(
                db, models.PlmArrivalBatch, models.PlmArrivalBatch.id.in_(removable_plm_batches), apply
            ) if removable_plm_batches else 0
        if status_fix_ids and apply:
            db.execute(
                update(models.NewProductOpportunity)
                .where(models.NewProductOpportunity.id.in_(status_fix_ids))
                .values(current_status=OPPORTUNITY_CONFIRMED_NOT_CLAIM)
            )
            db.add(
                models.AuditLog(
                    actor_name="Codex",
                    action="history_selection1_reject_status_cleanup",
                    entity_type="maintenance",
                    entity_id=None,
                    detail={
                        "count": len(status_fix_ids),
                        "before": dict(status_before),
                        "after": OPPORTUNITY_CONFIRMED_NOT_CLAIM,
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
            result["renamed"][old] = {"to": new, "opportunities": int(opp_count), "import_batches": int(import_count), "listings": int(listing_count)}
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
