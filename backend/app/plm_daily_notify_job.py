from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select

from app import models, services
from app.config import get_settings
from app.db import SessionLocal
from app.dingtalk_card_sender import ArrivalCardItem, DingTalkCardConfig, DingTalkCardSender
from app.notification_jobs import _ArrivalGroup, _send_arrival_card
from app.plm_download import BEIJING
from app.scheduler import JOB_PLM_SYNC, record_job_run, run_plm_sync


CURRENT_SECONDARY_SOURCE_COLUMNS = ("platform", "history_selection1", "plm_arrival_discovery", "manual_secondary")


def main() -> None:
    args = _args()
    dates = _dates(args)
    settings = get_settings()
    sender = DingTalkCardSender(DingTalkCardConfig.from_settings(settings))
    report: dict[str, Any] = {"dates": dates, "processed": [], "notifications": []}

    for date_text in dates:
        processed = run_plm_sync(settings, date_text)
        record_job_run(JOB_PLM_SYNC, date_text, processed)
        report["processed"].append({"date": date_text, "report": processed})

        with SessionLocal() as db:
            groups = arrival_record_groups(db, date_text)
            if args.send:
                rows = send_arrival_record_cards(db, settings, sender, date_text, groups)
                db.commit()
            else:
                rows = [_preview_group(group) for group in groups]
            report["notifications"].append({"date": date_text, "groups": rows})

    print(json.dumps(report, ensure_ascii=False, default=str), flush=True)


def arrival_record_groups(db, arrival_date: str) -> list[_ArrivalGroup]:
    arrival_day_start = datetime.strptime(arrival_date, "%Y-%m-%d").replace(tzinfo=BEIJING)
    arrival_utc_start = arrival_day_start.astimezone(timezone.utc)
    arrival_utc_end = (arrival_day_start + timedelta(days=1)).astimezone(timezone.utc)
    rows = db.execute(
        select(models.ArrivalRecord, models.PlmArrivalItem, models.SalesClaimForecast, models.NewProductOpportunity)
        .outerjoin(models.PlmArrivalBatch, models.ArrivalRecord.plm_arrival_batch_id == models.PlmArrivalBatch.id)
        .outerjoin(models.PlmArrivalItem, models.ArrivalRecord.plm_arrival_item_id == models.PlmArrivalItem.id)
        .join(models.SalesClaimForecast, models.ArrivalRecord.claim_record_id == models.SalesClaimForecast.id)
        .join(models.NewProductOpportunity, models.ArrivalRecord.opportunity_id == models.NewProductOpportunity.id)
        .where(
            or_(
                models.PlmArrivalBatch.arrival_date == arrival_date,
                and_(
                    models.ArrivalRecord.plm_arrival_batch_id.is_(None),
                    models.ArrivalRecord.arrived_at >= arrival_utc_start,
                    models.ArrivalRecord.arrived_at < arrival_utc_end,
                ),
            ),
            or_(models.PlmArrivalItem.id.is_(None), models.PlmArrivalItem.arrival_type == "new_arrival"),
            models.SalesClaimForecast.claim_result == "claim",
            models.SalesClaimForecast.source_column.in_(CURRENT_SECONDARY_SOURCE_COLUMNS),
            models.SalesClaimForecast.downstream_status == "waiting_secondary_research",
            models.SalesClaimForecast.secondary_research_submitted_at.is_(None),
        )
        .order_by(
            models.ArrivalRecord.salesperson_name,
            models.PlmArrivalItem.main_sku,
            models.NewProductOpportunity.main_sku,
            models.PlmArrivalItem.sub_sku,
            models.NewProductOpportunity.sub_sku,
        )
    ).all()
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record, item, claim, opportunity in rows:
        item_salesperson = item.salesperson_name if item else ""
        salesperson = (record.salesperson_name or claim.salesperson_name or item_salesperson or "").strip()
        main_sku = ((item.main_sku if item else None) or opportunity.main_sku or "").strip()
        if not salesperson or not main_sku:
            continue
        product_name = ((item.product_name if item else None) or opportunity.main_sku_name or opportunity.sub_sku_name or "").strip()
        value = grouped[salesperson].setdefault(
            main_sku,
            {"product_name": product_name, "sub_skus": set()},
        )
        sub_sku = ((item.sub_sku if item else None) or opportunity.sub_sku or "").strip()
        if sub_sku:
            value["sub_skus"].add(sub_sku)
    return [
        _ArrivalGroup(
            arrival_date=arrival_date,
            salesperson_name=name,
            new_items=[
                ArrivalCardItem(
                    main_sku=main_sku,
                    child_sku_count=len(value["sub_skus"]),
                    product_name=str(value["product_name"] or ""),
                )
                for main_sku, value in sorted(items.items())
            ],
            old_items=[],
        )
        for name, items in sorted(grouped.items())
    ]


def send_arrival_record_cards(db, settings, sender, arrival_date: str, groups: list[_ArrivalGroup]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for group in groups:
        dedupe_key = f"dingtalk_card:arrival:{arrival_date}:{group.salesperson_name}"
        mapping = services.dingtalk_mapping_for_name(db, group.salesperson_name, ("operator",))
        if mapping is None or not mapping.dingtalk_user_id:
            log = services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_no_receiver")
        elif not mapping.notification_enabled:
            log = services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_notification_disabled")
        else:
            log = _send_arrival_card(
                db,
                dedupe_key,
                mapping.dingtalk_user_id,
                group,
                settings,
                sender,
                action_text="去处理",
                action_url=services.dingtalk_action_url(settings, "operator", view="research"),
            )
        results.append(
            {
                "salesperson": group.salesperson_name,
                "new_main_sku_count": len(group.new_items),
                "send_status": log.send_status,
                "dedupe_key": log.dedupe_key,
            }
        )
    return results


def _preview_group(group: _ArrivalGroup) -> dict[str, Any]:
    return {
        "salesperson": group.salesperson_name,
        "new_main_sku_count": len(group.new_items),
        "items": [item.main_sku for item in group.new_items],
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--date")
    parser.add_argument("--send", action="store_true")
    return parser.parse_args()


def _dates(args: argparse.Namespace) -> list[str]:
    if args.date == "yesterday" or not any([args.date, args.start, args.end]):
        yesterday = datetime.now(BEIJING).date() - timedelta(days=1)
        return [yesterday.isoformat()]
    if args.date:
        return [args.date]
    start = datetime.fromisoformat(args.start).date()
    end = datetime.fromisoformat(args.end).date()
    days = (end - start).days
    if days < 0:
        raise ValueError("--end must be >= --start")
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days + 1)]


if __name__ == "__main__":
    main()
