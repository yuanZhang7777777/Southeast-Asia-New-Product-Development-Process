"""Consolidate duplicate historical selection opportunities without losing source evidence."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import SessionLocal
from app.site_codes import normalize_site_code
from app.workflow_status import OPPORTUNITY_REPLACED_BY_NORMALIZED_SELECTION1


HISTORICAL_SOURCE_TYPES = {
    "historical_market_monitor_archive",
    "history_selection1",
    "history_selection2",
    "selection1_developer_claim_feedback",
    "selection2_caigen_claim_feedback",
}
SELECTION1_SOURCE_TYPES = {"history_selection1", "selection1_developer_claim_feedback"}
SELECTION2_SOURCE_TYPES = {"history_selection2", "selection2_caigen_claim_feedback"}
SOURCE_PRIORITY = {
    "selection1_developer_claim_feedback": 0,
    "selection2_caigen_claim_feedback": 1,
    "history_selection1": 2,
    "history_selection2": 2,
    "historical_market_monitor_archive": 3,
}
COPY_IF_EMPTY = (
    "source_file", "source_sheet", "source_row", "country", "site", "developer_department",
    "developer_name", "category_level1", "keyword", "image_url", "main_sku_name", "sub_sku_name",
    "product_type", "reason",
)


SELECTION2_CAIGEN_SOURCE_TYPE = "selection2_caigen_claim_feedback"


def canonical_business_period(value: str | None, *, source_type: str | None = None) -> str:
    text = (value or "").strip()
    if source_type in {SELECTION2_CAIGEN_SOURCE_TYPE, "history_selection2"}:
        if re.fullmatch(r"\u9009\u54c12-\u8d22\u6839\d{4}\u671f", text):
            return text
        prefix = r"(?:\u9009\u54c12-\u8d22\u6839|\u8d22\u6839\u5f00\u53d1\u65b0\u54c1)?"
        compact = re.fullmatch(rf"{prefix}(\d{{4}})\u671f", text)
        if compact:
            return f"\u9009\u54c12-\u8d22\u6839{compact.group(1)}\u671f"
        dotted = re.fullmatch(rf"{prefix}(\d{{1,2}})[.\uFF0E/](\d{{1,2}})\u671f?", text)
        if dotted:
            return f"\u9009\u54c12-\u8d22\u6839{int(dotted.group(1)):02d}{int(dotted.group(2)):02d}\u671f"
    if source_type in SELECTION1_SOURCE_TYPES:
        if re.fullmatch(r"\u5f00\u53d1\d{4}\u671f-\u8d22\u6839", text):
            return text
        caigen = re.fullmatch(r"\u5f00\u53d1-\u8d22\u6839\u56e2\u961f\u6c47\u603b-(?:20\d{2})?(\d{4})", text)
        if caigen:
            return f"\u5f00\u53d1{caigen.group(1)}\u671f-\u8d22\u6839"
    match = re.fullmatch(r"\u5f00\u53d1(?:\u65b0\u54c1)?(\d{4})\u671f", text)
    return f"\u5f00\u53d1{match.group(1)}\u671f" if match else text


def source_namespace(source_type: str | None) -> str:
    if source_type in SELECTION1_SOURCE_TYPES:
        return "selection1"
    if source_type in SELECTION2_SOURCE_TYPES:
        return "selection2"
    return (source_type or "").strip()


def opportunity_key(item: models.NewProductOpportunity) -> tuple[str, str, str, str, str]:
    location = normalize_site_code(item.country or item.site) or ""
    if not location:
        source_sheet = (item.source_sheet or "").strip().casefold()
        location = f"sheet:{source_sheet}" if source_sheet else f"record:{item.id}"
    return (
        source_namespace(item.source_type),
        location,
        (item.main_sku or "").strip().upper(),
        (item.sub_sku or "").strip().upper(),
        canonical_business_period(item.batch, source_type=item.source_type),
    )


def duplicate_groups(db: Session) -> list[list[models.NewProductOpportunity]]:
    grouped: dict[tuple[str, str, str, str, str], list[models.NewProductOpportunity]] = defaultdict(list)
    for item in db.scalars(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type.in_(HISTORICAL_SOURCE_TYPES),
            models.NewProductOpportunity.current_status != OPPORTUNITY_REPLACED_BY_NORMALIZED_SELECTION1,
        )
    ):
        key = opportunity_key(item)
        if all(key):
            grouped[key].append(item)
    return [items for items in grouped.values() if len(items) > 1]


def duplicate_plan_rows(db: Session, groups: list[list[models.NewProductOpportunity]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_index, items in enumerate(groups, start=1):
        canonical = min(items, key=_opportunity_rank)
        for item in sorted(items, key=_opportunity_rank):
            if item.id == canonical.id:
                action = "keep_canonical"
            else:
                action = "hide_after_migration" if (_has_downstream_references(db, item.id) or item.image_url) else "delete_after_backup"
            rows.append({
                "group": group_index,
                "action": action,
                "opportunity_id": item.id,
                "canonical_id": canonical.id,
                "source_type": item.source_type,
                "source_file": item.source_file,
                "source_sheet": item.source_sheet,
                "source_row": item.source_row,
                "business_period": item.batch,
                "canonical_period": canonical_business_period(item.batch, source_type=item.source_type),
                "country": item.country,
                "site": item.site,
                "main_sku": item.main_sku,
                "sub_sku": item.sub_sku,
                "status": item.current_status,
                "has_image": bool(item.image_url),
                "has_downstream_refs": _has_downstream_references(db, item.id),
            })
    return rows


def write_reconcile_workbook(output_dir: Path, report: dict[str, int], rows: list[dict[str, Any]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    summary = workbook.active
    summary.title = "摘要"
    summary.append(["指标", "数量"])
    for key, value in report.items():
        summary.append([key, value])
    detail = workbook.create_sheet("归并计划")
    headers = [
        "group", "action", "opportunity_id", "canonical_id", "source_type", "source_file", "source_sheet",
        "source_row", "business_period", "canonical_period", "country", "site", "main_sku", "sub_sku",
        "status", "has_image", "has_downstream_refs",
    ]
    detail.append(headers)
    for row in rows:
        detail.append([row.get(header) for header in headers])
    path = output_dir / "历史选品1规范化归并计划.xlsx"
    workbook.save(path)
    return path


def _period_alias_items(db: Session) -> list[models.NewProductOpportunity]:
    return [
        item
        for item in db.scalars(
            select(models.NewProductOpportunity).where(models.NewProductOpportunity.source_type.in_(SELECTION1_SOURCE_TYPES))
        )
        if item.batch != canonical_business_period(item.batch, source_type=item.source_type)
    ]


def _normalize_historical_periods(db: Session) -> int:
    items = _period_alias_items(db)
    for item in items:
        item.batch = canonical_business_period(item.batch, source_type=item.source_type)
    return len(items)



def _opportunity_rank(item: models.NewProductOpportunity) -> tuple[int, int, str]:
    return (
        SOURCE_PRIORITY.get(item.source_type, 99),
        1 if item.current_status == "historical_archive" else 0,
        item.id,
    )


def _claim_rank(item: models.SalesClaimForecast) -> tuple[int, int, str]:
    return (
        0 if item.claim_source in {"selection1_claim_feedback", "selection2_claim_feedback"} else 1,
        0 if item.claim_result != "claim" else 1,
        item.id,
    )


def _copy_missing(target: models.NewProductOpportunity, source: models.NewProductOpportunity) -> None:
    for field in COPY_IF_EMPTY:
        if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
            setattr(target, field, getattr(source, field))


def _move_opportunity_references(
    db: Session,
    source_id: str,
    target_id: str,
) -> None:
    for model in (
        models.SourceRecordSnapshot,
        models.MarketResearchItem,
        models.SalesClaimForecast,
        models.FlowInstance,
        models.ReviewRecord,
        models.SupplyChainQuote,
        models.StockingRequest,
        models.ExportRow,
        models.ArrivalRecord,
    ):
        for row in db.scalars(select(model).where(model.opportunity_id == source_id)):
            row.opportunity_id = target_id
    for binding in db.scalars(select(models.ListingSkuBinding).where(models.ListingSkuBinding.opportunity_id == source_id)):
        binding.opportunity_id = target_id
    for audit_row in db.scalars(
        select(models.AuditLog).where(
            models.AuditLog.entity_type == "new_product_opportunity",
            models.AuditLog.entity_id == source_id,
        )
    ):
        audit_row.entity_id = target_id


def _has_downstream_references(db: Session, opportunity_id: str) -> bool:
    for model in (
        models.MarketResearchItem,
        models.SalesClaimForecast,
        models.FlowInstance,
        models.ReviewRecord,
        models.SupplyChainQuote,
        models.StockingRequest,
        models.ExportRow,
        models.ArrivalRecord,
    ):
        if db.scalar(select(model.id).where(model.opportunity_id == opportunity_id).limit(1)):
            return True
    if db.scalar(select(models.ListingSkuBinding.id).where(models.ListingSkuBinding.opportunity_id == opportunity_id).limit(1)):
        return True
    return False


def _mark_replaced(source: models.NewProductOpportunity, target: models.NewProductOpportunity) -> None:
    snapshot = dict(source.snapshot or {})
    snapshot.update({
        "replaced_by_opportunity_id": target.id,
        "replacement_status": OPPORTUNITY_REPLACED_BY_NORMALIZED_SELECTION1,
        "replacement_reason": "normalized_selection1_rebuild",
    })
    source.snapshot = snapshot
    source.current_status = OPPORTUNITY_REPLACED_BY_NORMALIZED_SELECTION1


def _copy_claim_progress(target: models.SalesClaimForecast, source: models.SalesClaimForecast) -> None:
    if target.claim_result != "claim" or source.claim_result != "claim":
        return
    if source.downstream_status == "waiting_secondary_research":
        target.downstream_status = source.downstream_status
    for field in (
        "arrival_detected_at", "secondary_research_at", "secondary_competitor_url", "secondary_conclusion",
        "product_positioning", "secondary_target_daily_sales", "secondary_selling_points",
        "secondary_research_submitted_at",
    ):
        if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
            setattr(target, field, getattr(source, field))


def _move_claim_references(
    db: Session,
    source: models.SalesClaimForecast,
    target: models.SalesClaimForecast,
) -> None:
    for row in db.scalars(select(models.ReviewRecord).where(models.ReviewRecord.claim_record_id == source.id)):
        row.claim_record_id = target.id
    target_stocking = db.scalar(select(models.StockingRequest).where(models.StockingRequest.claim_record_id == target.id))
    for row in db.scalars(select(models.StockingRequest).where(models.StockingRequest.claim_record_id == source.id)):
        if target_stocking is None:
            row.claim_record_id = target.id
            target_stocking = row
        else:
            row.claim_record_id = None
    for row in db.scalars(select(models.ExportRow).where(models.ExportRow.claim_record_id == source.id)):
        row.claim_record_id = target.id
    for row in db.scalars(select(models.ListingSkuBinding).where(models.ListingSkuBinding.claim_record_id == source.id)):
        row.claim_record_id = target.id
    for audit_row in db.scalars(
        select(models.AuditLog).where(
            models.AuditLog.entity_type == "sales_claim_forecast",
            models.AuditLog.entity_id == source.id,
        )
    ):
        audit_row.entity_id = target.id


def _merge_claims(
    db: Session,
    opportunity_id: str,
) -> tuple[dict[str, str], list[models.SalesClaimForecast]]:
    by_owner: dict[str, list[models.SalesClaimForecast]] = defaultdict(list)
    for claim in db.scalars(select(models.SalesClaimForecast).where(models.SalesClaimForecast.opportunity_id == opportunity_id)):
        owner_key = (claim.salesperson_name or "").strip() or f"__unowned__:{claim.id}"
        by_owner[owner_key].append(claim)
    replacements: dict[str, str] = {}
    redundant_claims: list[models.SalesClaimForecast] = []
    for claims in by_owner.values():
        if len(claims) < 2:
            continue
        keeper = min(claims, key=_claim_rank)
        for source in claims:
            if source.id == keeper.id:
                continue
            _copy_claim_progress(keeper, source)
            _move_claim_references(db, source, keeper)
            replacements[source.id] = keeper.id
            redundant_claims.append(source)
    return replacements, redundant_claims


def _dedupe_arrivals(
    db: Session,
    opportunity_id: str,
    replacements: dict[str, str],
) -> int:
    grouped: dict[tuple[str | None, str | None], list[models.ArrivalRecord]] = defaultdict(list)
    for row in db.scalars(select(models.ArrivalRecord).where(models.ArrivalRecord.opportunity_id == opportunity_id)):
        row.claim_record_id = replacements.get(row.claim_record_id or "", row.claim_record_id)
        grouped[(row.plm_arrival_batch_id, row.claim_record_id)].append(row)
    removed = 0
    for rows in grouped.values():
        for row in rows[1:]:
            db.delete(row)
            removed += 1
    return removed


def reconcile_historical_opportunities(db: Session, *, apply: bool = False) -> dict[str, int]:
    period_aliases_normalized = _normalize_historical_periods(db) if apply else len(_period_alias_items(db))
    groups = duplicate_groups(db)
    report = {
        "duplicate_groups": len(groups),
        "merged_opportunities": sum(len(items) - 1 for items in groups),
        "claims_removed": 0,
        "arrivals_removed": 0,
        "period_aliases_normalized": period_aliases_normalized,
        "hidden_replaced_opportunities": 0,
        "deleted_opportunities": 0,
        "images_reused": 0,
    }
    if not apply:
        return report
    for items in groups:
        canonical = min(items, key=_opportunity_rank)
        duplicate_actions: list[tuple[models.NewProductOpportunity, bool]] = []
        for duplicate in items:
            if duplicate.id == canonical.id:
                continue
            keep_hidden = _has_downstream_references(db, duplicate.id) or bool(duplicate.image_url)
            if not canonical.image_url and duplicate.image_url:
                report["images_reused"] += 1
            _copy_missing(canonical, duplicate)
            _move_opportunity_references(db, duplicate.id, canonical.id)
            duplicate_actions.append((duplicate, keep_hidden))
        db.flush()
        replacements, redundant_claims = _merge_claims(db, canonical.id)
        report["claims_removed"] += len(redundant_claims)
        report["arrivals_removed"] += _dedupe_arrivals(db, canonical.id, replacements)
        for claim in redundant_claims:
            db.delete(claim)
        db.flush()
        for duplicate, keep_hidden in duplicate_actions:
            if keep_hidden:
                _mark_replaced(duplicate, canonical)
                report["hidden_replaced_opportunities"] += 1
            else:
                db.delete(duplicate)
                report["deleted_opportunities"] += 1
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.apply_dev and get_settings().app_env.lower() in {"prod", "production"}:
        raise SystemExit("refusing to clean production data")
    workbook_path = None
    with SessionLocal() as db:
        groups = duplicate_groups(db)
        plan_rows = duplicate_plan_rows(db, groups) if args.output_dir else []
        report = reconcile_historical_opportunities(db, apply=args.apply_dev)
        if args.output_dir:
            workbook_path = write_reconcile_workbook(args.output_dir, report, plan_rows)
        if args.apply_dev:
            db.commit()
        else:
            db.rollback()
    if workbook_path:
        report["workbook"] = str(workbook_path)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
