from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings

HISTORICAL_ARCHIVE_SOURCE_TYPE = "historical_market_monitor_archive"
HISTORICAL_ARCHIVE_STATUS = "historical_archive"
HISTORICAL_ARCHIVE_BATCH = "历史归档"
BUSINESS_PERIOD_PATTERN = re.compile(r"开发新品(\d{3,4})期")


def business_period_from_bucket(bucket: object) -> str | None:
    match = BUSINESS_PERIOD_PATTERN.search(str(bucket or ""))
    return f"开发{match.group(1)}期" if match else None
PENDING_SECONDARY_STATUSES = {"已到货待补二次调研", "已刊登但二次调研缺失"}
def _apply_allowed_envs() -> set[str]:
    # 生产补数需逐次显式解锁：运行时设 APPLY_ALLOWED_ENVS_EXTRA=production（用户 2026-07-27 授权迁生产）。
    extra = {part.strip().lower() for part in os.getenv("APPLY_ALLOWED_ENVS_EXTRA", "").split(",") if part.strip()}
    return {"local", "test", "testing", "dev", "development", "uat"} | extra


class _ApplyAllowedEnvs:
    def __contains__(self, env: object) -> bool:
        return env in _apply_allowed_envs()

    def __iter__(self):
        return iter(sorted(_apply_allowed_envs()))


APPLY_ALLOWED_ENVS = _ApplyAllowedEnvs()
REVIEW_HEADERS = [
    "归类状态",
    "建议动作",
    "冲突原因",
    "主SKU",
    "子SKU",
    "国家",
    "历史销售员",
    "PLM销售员",
    "负责人",
    "到货时间",
    "是否有二次调研",
    "是否有刊登证据",
    "刊登证据状态",
    "指标口径",
    "代表主SKU",
    "Item汇总",
    "已确认店铺",
    "已确认Item",
    "候选Item数",
    "候选店铺Item",
    "共享Item归属",
    "FineBI可补",
    "二次结论",
    "产品定位",
    "目标单销",
    "卖点总结",
    "来源文件",
    "来源Sheet",
    "来源行",
    "未导入原因",
]


@dataclass(frozen=True)
class ReviewOutput:
    summary: dict[str, Any]
    summary_json: Path
    hard_conflict_workbook: Path
    pending_secondary_workbook: Path
    multi_item_workbook: Path
    missing_finebi_workbook: Path
    plm_arrival_workbook: Path
    finebi_metrics_workbook: Path
    shared_item_workbook: Path
    skipped_workbook: Path


@dataclass(frozen=True)
class ArchiveImportResult:
    import_batch_id: str | None
    created_count: int
    updated_count: int
    skipped_count: int


def build_archive_rows(report: dict[str, Any], sample_per_status: int | None = None) -> list[dict[str, Any]]:
    records = list(report.get("records") or [])
    if sample_per_status is not None:
        records = _sample_by_status(records, sample_per_status)
    return [_archive_row(record) for record in records]


def write_archive_review_outputs(rows: list[dict[str, Any]], output_dir: str | Path, run_date: str) -> ReviewOutput:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    status_counts = Counter(row["snapshot"].get("classification_status") for row in rows)
    conflict_rows = [row for row in rows if row["snapshot"].get("conflict_reason")]
    hard_conflict_rows = [row for row in rows if _listing_status(row) == "hard_conflict" or row["snapshot"].get("conflict_reason")]
    shared_item_rows = [row for row in rows if _listing_status(row) == "shared_item_binding"]
    skipped_rows = [row for row in rows if _skip_reason(row)]
    pending_secondary_rows = [
        row for row in rows if row["snapshot"].get("classification_status") in PENDING_SECONDARY_STATUSES
    ]
    multi_item_rows = [row for row in rows if _listing_status(row) == "multi_item_candidates"]
    missing_finebi_rows = [row for row in rows if _listing_status(row) == "missing_finebi_evidence"]
    plm_arrival_rows = [row for row in rows if row["snapshot"].get("arrival_time")]
    finebi_metrics_rows = [row for row in rows if (row["snapshot"].get("listing") or {}).get("finebi_fillable")]
    summary = {
        "total_rows": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "conflict_rows": len(conflict_rows),
        "hard_conflict_rows": len(hard_conflict_rows),
        "shared_item_binding_rows": len(shared_item_rows),
        "skipped_rows": len(skipped_rows),
        "multi_item_candidate_rows": len(multi_item_rows),
        "missing_finebi_evidence_rows": len(missing_finebi_rows),
        "plm_arrival_rows": len(plm_arrival_rows),
        "finebi_fillable_rows": len(finebi_metrics_rows),
        "pending_secondary_rows": len(pending_secondary_rows),
        "source_type": HISTORICAL_ARCHIVE_SOURCE_TYPE,
        "current_status": HISTORICAL_ARCHIVE_STATUS,
    }
    summary_json = output_path / f"historical-archive-import-summary-{run_date}.json"
    hard_conflict_workbook = output_path / f"历史档案硬冲突清单-{run_date}.xlsx"
    pending_secondary_workbook = output_path / f"历史二次调研待补清单-{run_date}.xlsx"
    multi_item_workbook = output_path / f"历史多Item候选清单-{run_date}.xlsx"
    missing_finebi_workbook = output_path / f"历史刊登来源待补证据清单-{run_date}.xlsx"
    plm_arrival_workbook = output_path / f"历史PLM到货命中清单-{run_date}.xlsx"
    finebi_metrics_workbook = output_path / f"历史FineBI可补周指标清单-{run_date}.xlsx"
    shared_item_workbook = output_path / f"历史FineBI共享Item绑定清单-{run_date}.xlsx"
    skipped_workbook = output_path / f"历史未导入清单-{run_date}.xlsx"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_review_workbook(hard_conflict_rows, hard_conflict_workbook)
    _write_review_workbook(pending_secondary_rows, pending_secondary_workbook)
    _write_review_workbook(multi_item_rows, multi_item_workbook)
    _write_review_workbook(missing_finebi_rows, missing_finebi_workbook)
    _write_review_workbook(plm_arrival_rows, plm_arrival_workbook)
    _write_review_workbook(finebi_metrics_rows, finebi_metrics_workbook)
    _write_review_workbook(shared_item_rows, shared_item_workbook)
    _write_review_workbook(skipped_rows, skipped_workbook)
    return ReviewOutput(
        summary,
        summary_json,
        hard_conflict_workbook,
        pending_secondary_workbook,
        multi_item_workbook,
        missing_finebi_workbook,
        plm_arrival_workbook,
        finebi_metrics_workbook,
        shared_item_workbook,
        skipped_workbook,
    )


def apply_archive_to_db(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source_file: str,
    imported_by: str | None = None,
) -> ArchiveImportResult:
    batch = models.ImportBatch(
        source_type=HISTORICAL_ARCHIVE_SOURCE_TYPE,
        source_file=source_file,
        source_sheet="classification",
        business_period=HISTORICAL_ARCHIVE_BATCH,
        imported_by=imported_by,
        status="running",
    )
    db.add(batch)
    db.flush()

    created = updated = skipped = 0
    for row in rows:
        if not row.get("main_sku") or not row.get("sub_sku"):
            skipped += 1
            continue
        existing = _find_existing_archive(db, row)
        if existing:
            if _update_existing(existing, row):
                updated += 1
            _ensure_source_snapshot(db, existing, None)
            continue
        opportunity = models.NewProductOpportunity(**_opportunity_data(row, import_batch_id=batch.id))
        db.add(opportunity)
        db.flush()
        _ensure_source_snapshot(db, opportunity, batch.id)
        created += 1

    batch.created_count = created
    batch.updated_count = updated
    batch.skipped_count = skipped
    batch.status = "completed"
    return ArchiveImportResult(batch.id, created, updated, skipped)


def _archive_row(record: dict[str, Any]) -> dict[str, Any]:
    source_reference = dict(record.get("source_reference") or {})
    secondary = {
        "secondary_research_at": record.get("secondary_research_at"),
        "secondary_competitor_url": record.get("secondary_competitor_url"),
        "secondary_conclusion": record.get("secondary_conclusion"),
        "positioning": record.get("positioning"),
        "target_daily_sales": record.get("target_daily_sales"),
        "selling_points": record.get("selling_points"),
    }
    snapshot = {
        "archive_type": "historical_market_monitor",
        "classification_status": record.get("classification_status"),
        "suggested_action": record.get("suggested_action"),
        "conflict_reason": record.get("conflict_reason") or "",
        "historical_salesperson": record.get("historical_salesperson"),
        "plm_salesperson": record.get("plm_salesperson"),
        "owner_for_action": record.get("owner_for_action"),
        "arrival_time": record.get("arrival_time"),
        "has_secondary_research": bool(record.get("has_secondary_research")),
        "secondary_research_complete": bool(record.get("secondary_research_complete")),
        "has_listing_item": bool(record.get("has_listing_item")),
        "listing": {
            "source": record.get("listing_source"),
            "evidence_status": record.get("listing_evidence_status") or "none",
            "evidence_status_label": _listing_status_label(record.get("listing_evidence_status")),
            "metric_dimension": record.get("metric_dimension") or ("item_summary" if record.get("has_listing_item") else None),
            "metric_owner_main_sku": record.get("metric_owner_main_sku") or (record.get("main_sku") if record.get("has_listing_item") else None),
            "metrics_are_item_summary": bool(record.get("metrics_are_item_summary") if record.get("metrics_are_item_summary") is not None else record.get("has_listing_item")),
            "shop": record.get("shop"),
            "item": record.get("item"),
            "finebi_fillable": bool(record.get("finebi_fillable")),
            "multi_item_candidates": record.get("multi_item_candidates") or [],
            "shared_item_owners": record.get("shared_item_owners") or [],
        },
        "secondary": secondary,
        "market_source": {
            "product_bucket": record.get("product_bucket"),
            "category_level2": record.get("category_level2"),
            "sales_note": record.get("sales_note"),
            "reference_daily_sales": record.get("reference_daily_sales"),
            "reference_price": record.get("reference_price"),
            "claimed_daily_sales": record.get("claimed_daily_sales"),
            "competitors": record.get("competitors") or [],
            "arrival_note": record.get("arrival_note"),
        },
        "source_reference": source_reference,
        "raw_classification_record": record,
    }
    return {
        "source_type": HISTORICAL_ARCHIVE_SOURCE_TYPE,
        "source_file": source_reference.get("source_file"),
        "source_sheet": source_reference.get("source_sheet"),
        "source_row": source_reference.get("source_row"),
        "batch": business_period_from_bucket(record.get("product_bucket")) or HISTORICAL_ARCHIVE_BATCH,
        "country": record.get("country"),
        "site": record.get("country"),
        "developer_department": None,
        "developer_name": record.get("historical_salesperson"),
        "category_level1": record.get("category_level1"),
        "keyword": record.get("keyword"),
        "image_url": record.get("image_url"),
        "main_sku_name": record.get("product_name"),
        "main_sku": record.get("main_sku"),
        "sub_sku_name": record.get("product_name"),
        "sub_sku": record.get("child_sku") or record.get("sub_sku"),
        "product_type": record.get("product_type"),
        "reason": record.get("sales_note"),
        "current_status": HISTORICAL_ARCHIVE_STATUS,
        "snapshot": snapshot,
    }


def _sample_by_status(records: list[dict[str, Any]], sample_per_status: int) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    selected = []
    for record in records:
        status = record.get("classification_status") or ""
        if counts[status] >= sample_per_status:
            continue
        selected.append(record)
        counts[status] += 1
    return selected


def _listing_status(row: dict[str, Any]) -> str | None:
    return ((row.get("snapshot") or {}).get("listing") or {}).get("evidence_status")


def _listing_status_label(status: str | None) -> str:
    return {
        "none": "无刊登证据",
        "confirmed_item": "已确认Item",
        "multi_item_candidates": "多Item候选",
        "missing_finebi_evidence": "旧表有Item待补FineBI证据",
        "hard_conflict": "同店铺Item多主SKU待核对",
        "shared_item_binding": "共享Item汇总",
    }.get(status or "none", status or "无刊登证据")


def _skip_reason(row: dict[str, Any]) -> str:
    if not row.get("main_sku"):
        return "缺主SKU"
    if not row.get("sub_sku"):
        return "缺子SKU"
    return ""


def _format_item_candidates(candidates: list[dict[str, Any]]) -> str:
    parts = [
        f"{item.get('shop') or '-'} / {item.get('item_id') or '-'} / {item.get('first_period') or '-'}~{item.get('last_period') or '-'}"
        for item in candidates[:10]
    ]
    suffix = f"；...共{len(candidates)}项" if len(candidates) > 10 else ""
    return "；".join(parts) + suffix


def _format_shared_item_owners(owners: list[dict[str, Any]]) -> str:
    parts = [
        f"{item.get('country') or '-'} / {item.get('main_sku') or '-'} / {item.get('shop') or '-'} / {item.get('item_id') or '-'} / {item.get('first_period') or '-'}~{item.get('last_period') or '-'} / 行数{item.get('row_count') or 0}"
        for item in owners[:10]
    ]
    suffix = f"；...共{len(owners)}项" if len(owners) > 10 else ""
    return "；".join(parts) + suffix


def _write_review_workbook(rows: list[dict[str, Any]], path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "清单"
    worksheet.append(REVIEW_HEADERS)
    for row in rows:
        worksheet.append(_review_values(row))
    workbook.save(path)


def _review_values(row: dict[str, Any]) -> list[Any]:
    snapshot = row["snapshot"]
    secondary = snapshot.get("secondary") or {}
    source = snapshot.get("source_reference") or {}
    listing = snapshot.get("listing") or {}
    return [
        snapshot.get("classification_status"),
        snapshot.get("suggested_action"),
        snapshot.get("conflict_reason"),
        row.get("main_sku"),
        row.get("sub_sku"),
        row.get("country"),
        snapshot.get("historical_salesperson"),
        snapshot.get("plm_salesperson"),
        snapshot.get("owner_for_action"),
        snapshot.get("arrival_time"),
        "是" if snapshot.get("has_secondary_research") else "否",
        "是" if snapshot.get("has_listing_item") else "否",
        _listing_status_label(listing.get("evidence_status")),
        listing.get("metric_dimension"),
        listing.get("metric_owner_main_sku"),
        "是" if listing.get("metrics_are_item_summary") else "否",
        listing.get("shop"),
        listing.get("item"),
        len(listing.get("multi_item_candidates") or []),
        _format_item_candidates(listing.get("multi_item_candidates") or []),
        _format_shared_item_owners(listing.get("shared_item_owners") or []),
        "是" if listing.get("finebi_fillable") else "否",
        secondary.get("secondary_conclusion"),
        secondary.get("positioning"),
        secondary.get("target_daily_sales"),
        secondary.get("selling_points"),
        source.get("source_file"),
        source.get("source_sheet"),
        source.get("source_row"),
        _skip_reason(row),
    ]


def _find_existing_archive(db: Session, row: dict[str, Any]) -> models.NewProductOpportunity | None:
    return db.scalar(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == HISTORICAL_ARCHIVE_SOURCE_TYPE,
            models.NewProductOpportunity.source_file == row.get("source_file"),
            models.NewProductOpportunity.source_sheet == row.get("source_sheet"),
            models.NewProductOpportunity.source_row == row.get("source_row"),
            models.NewProductOpportunity.main_sku == row.get("main_sku"),
            models.NewProductOpportunity.sub_sku == row.get("sub_sku"),
        )
    )


def _update_existing(opportunity: models.NewProductOpportunity, row: dict[str, Any]) -> bool:
    changed = False
    for field, value in _opportunity_data(row, import_batch_id=None).items():
        if field == "import_batch_id":
            continue
        if field == "snapshot":
            value = _snapshot_with_preserved_enrichments(opportunity.snapshot, value)
        if getattr(opportunity, field) != value:
            setattr(opportunity, field, value)
            changed = True
    return changed


def _snapshot_with_preserved_enrichments(existing: Any, incoming: Any) -> Any:
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming
    if "development_source" not in existing or "development_source" in incoming:
        return incoming
    return {**incoming, "development_source": existing["development_source"]}


def _opportunity_data(row: dict[str, Any], import_batch_id: str | None) -> dict[str, Any]:
    data = {key: row.get(key) for key in (
        "source_type",
        "source_file",
        "source_sheet",
        "source_row",
        "batch",
        "country",
        "site",
        "developer_department",
        "developer_name",
        "category_level1",
        "keyword",
        "image_url",
        "main_sku_name",
        "main_sku",
        "sub_sku_name",
        "sub_sku",
        "product_type",
        "reason",
        "current_status",
        "snapshot",
    )}
    data["import_batch_id"] = import_batch_id
    return data


def _ensure_source_snapshot(db: Session, opportunity: models.NewProductOpportunity, import_batch_id: str | None) -> None:
    existing = db.scalar(
        select(models.SourceRecordSnapshot).where(
            models.SourceRecordSnapshot.opportunity_id == opportunity.id,
            models.SourceRecordSnapshot.source_file == opportunity.source_file,
            models.SourceRecordSnapshot.source_sheet == opportunity.source_sheet,
            models.SourceRecordSnapshot.source_row == opportunity.source_row,
        )
    )
    if existing:
        if existing.payload != opportunity.snapshot:
            existing.payload = opportunity.snapshot
        return
    db.add(
        models.SourceRecordSnapshot(
            import_batch_id=import_batch_id,
            opportunity_id=opportunity.id,
            source_file=opportunity.source_file,
            source_sheet=opportunity.source_sheet,
            source_row=opportunity.source_row,
            column_range="classification-json",
            payload=opportunity.snapshot,
        )
    )


def _ensure_apply_allowed() -> None:
    env = get_settings().app_env.strip().lower()
    if env not in APPLY_ALLOWED_ENVS:
        raise RuntimeError(f"refusing historical archive import outside dev/local env: {env}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run or apply historical archive import for classified records.")
    parser.add_argument("--classification", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/historical_data/historical_archive_import_20260725"))
    parser.add_argument("--run-date", default="20260725")
    parser.add_argument("--sample-per-status", type=int)
    parser.add_argument("--apply-dev", action="store_true")
    parser.add_argument("--imported-by", default="codex")
    args = parser.parse_args()

    report = json.loads(args.classification.read_text(encoding="utf-8"))
    rows = build_archive_rows(report, sample_per_status=args.sample_per_status)
    output = write_archive_review_outputs(rows, args.output_dir, args.run_date)
    result: ArchiveImportResult | None = None
    if args.apply_dev:
        _ensure_apply_allowed()
        from app.db import SessionLocal

        with SessionLocal() as db:
            result = apply_archive_to_db(db, rows, source_file=args.classification.name, imported_by=args.imported_by)
            db.commit()
    print(json.dumps({"review": output.summary, "apply": result.__dict__ if result else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
