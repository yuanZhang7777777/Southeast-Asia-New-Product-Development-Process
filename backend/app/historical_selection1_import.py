"""选品1 历史期档案模式导入器（仅新世代期数，绝不建认领/任务/通知）。

- 范围：sheet 名含 `开发MMDD期` 且 0428 <= MMDD < 0815 的新世代期；旧世代（0421 及更早、0815-0924）
  与非期数 sheet 一律跳过并在报告 `skipped_sheets` 中列出。
- 档案行：NewProductOpportunity(source_type=history_selection1, current_status 与
  historical_central_import 档案行一致)；快照 `fields_by_cell` 按列字母全列保真，
  规避 cells 快照缺 BY:CB、同名表头/同别名串值只存第一列的问题。
- 判重键：source_type + source_sheet + sub_sku（与选品2 修复后语义一致）；
  现行选品1 机会行（selection1_developer_claim_feedback）同 sheet 同子SKU 也计跳过、绝不更新。
- 批次级 sha256 判重防整文件重导；审计带 batch_tag，支持 --revert 整批撤销。
- 两段式：本机 `--workbook [--upload-images] --rows-out rows.json` 解析，
  服务器容器内 `--apply-rows rows.json --apply-dev` 入库（受 APPLY_ALLOWED_ENVS 门控）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.field_mapping import normalize_header, text_value
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_central_import import ARCHIVE_STATUS, ERROR_VALUES, _json_safe, sheet_image_bytes
from app.historical_watchlist import sha256_file
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE
from app.services import audit
from app.site_codes import normalize_site_code

SOURCE_TYPE = "history_selection1"
AUDIT_ACTION = "history.selection1_imported"
REVERT_AUDIT_ACTION = "history.selection1_import_reverted"
SHEET_PERIOD_PATTERN = re.compile(r"开发(\d{4})期")
NEW_GENERATION_MIN = 414  # 用户拍板（2026-07-26）：0414/0421 与新世代同表头结构，一并纳入
OLD_GENERATION_MIN = 815  # 开发0815期~0924期为旧世代杂糅结构
SUMMARY_LABELS = {"小计", "合计", "总计", "汇总"}
FIELD_ALIASES = {
    "developer_department": ("开发部门", "部门"),
    "developer_name": ("开发员",),
    "category_level1": ("一级类目",),
    "keyword": ("关键词", "开发关键词"),
    "main_sku_name": ("主SKU名称",),
    "sub_sku_name": ("子SKU名称",),
    "product_type": ("产品类型", "引流or绑定or利润", "产品类型/引流or绑定or利润"),
    "reason": ("开品理由",),
}


def period_from_sheet(sheet_name: str) -> str | None:
    match = SHEET_PERIOD_PATTERN.search(sheet_name)
    return match.group(1) if match else None


def sheet_skip_reason(sheet_name: str) -> str | None:
    period = period_from_sheet(sheet_name)
    if period is None:
        return "非期数sheet"
    if int(period) < NEW_GENERATION_MIN:
        return "早于0414期"
    if int(period) >= OLD_GENERATION_MIN:
        return "旧世代（0815-0924）"
    return None


def _is_summary_row(*values: str | None) -> bool:
    return any((value or "").strip(" ：:") in SUMMARY_LABELS for value in values)


def _is_repeated_header_row(sub_sku: str, main_sku: str | None) -> bool:
    compact_sub = "".join(sub_sku.split()).upper()
    compact_main = "".join((main_sku or "").split()).upper()
    return compact_sub in {"子SKU", "SUBSKU"} or compact_main in {"主SKU", "MAINSKU"}


def parse_selection1_workbook(
    path: Path,
    upload_images: bool = False,
    max_rows_per_sheet: int | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    sheet_reports: list[dict[str, Any]] = []
    skipped_sheets: list[dict[str, Any]] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet_name in workbook.sheetnames:
            reason = sheet_skip_reason(sheet_name)
            if reason:
                skipped_sheets.append({"sheet": sheet_name, "reason": reason})
                continue
            period = f"开发{period_from_sheet(sheet_name)}期"
            worksheet = workbook[sheet_name]
            try:
                worksheet.reset_dimensions()
            except AttributeError:
                pass
            iterator = worksheet.iter_rows(values_only=True)
            header_top = next(iterator, ()) or ()
            header_bottom = next(iterator, ()) or ()
            headers: dict[int, str] = {}
            groups: dict[int, str] = {}
            column_of: dict[str, int] = {}
            current_group: str | None = None
            for index in range(max(len(header_top), len(header_bottom))):
                top = text_value(header_top[index]) if index < len(header_top) else None
                bottom = text_value(header_bottom[index]) if index < len(header_bottom) else None
                if top:
                    current_group = top
                if current_group:
                    groups[index] = current_group
                label = bottom or top
                if not label:
                    continue
                headers[index] = label
                # 同名表头首列优先（setdefault），识别字段全在左侧 A~L 区，不受右侧重复表头影响。
                for candidate in (top, bottom, f"{current_group}/{label}" if current_group else None):
                    if candidate:
                        column_of.setdefault(normalize_header(candidate), index)

            def col(*names: str) -> int | None:
                for name in names:
                    index = column_of.get(normalize_header(name))
                    if index is not None:
                        return index
                return None

            site_col = col("站点", "国家")
            main_col = col("主SKU")
            sub_col = col("子SKU")
            image_col = col("产品图片")
            field_cols = {field: col(*aliases) for field, aliases in FIELD_ALIASES.items()}

            def cell(row: tuple[Any, ...], index: int | None) -> Any:
                return row[index] if index is not None and index < len(row) else None

            sheet_rows = 0
            skipped = 0
            for source_row, row in enumerate(iterator, start=3):
                if max_rows_per_sheet is not None and sheet_rows >= max_rows_per_sheet:
                    break
                sub_sku = text_value(cell(row, sub_col))
                if not sub_sku or sub_sku in ERROR_VALUES:
                    skipped += 1
                    continue
                site_raw = text_value(cell(row, site_col))
                main_sku = text_value(cell(row, main_col))
                fields = {field: text_value(cell(row, index)) for field, index in field_cols.items()}
                if _is_summary_row(site_raw, main_sku, sub_sku, fields["main_sku_name"], fields["sub_sku_name"]):
                    skipped += 1
                    continue
                if _is_repeated_header_row(sub_sku, main_sku):
                    skipped += 1
                    continue
                # 全列保真快照：键=列字母，同名表头/同别名的多列各自完整保留，无 BY:CB 缺口。
                fields_by_cell = {
                    get_column_letter(index + 1): {
                        "header": headers.get(index),
                        "group": groups.get(index),
                        "value": _json_safe(value),
                    }
                    for index, value in enumerate(row)
                    if value is not None and text_value(value)
                }
                country = normalize_site_code(site_raw)
                rows.append(
                    {
                        "source_type": SOURCE_TYPE,
                        "source_file": path.name,
                        "source_sheet": sheet_name,
                        "source_row": source_row,
                        "batch": period,
                        "country": country,
                        "site": site_raw or country,
                        "main_sku": main_sku or sub_sku,
                        "sub_sku": sub_sku,
                        "image_row": source_row if image_col is not None else None,
                        **fields,
                        "snapshot": {
                            "archive_type": "historical_selection1",
                            "business_period": period,
                            "site_raw": site_raw,
                            "fields_by_cell": fields_by_cell,
                            "source_reference": {
                                "source_file": path.name,
                                "source_sheet": sheet_name,
                                "source_row": source_row,
                            },
                        },
                    }
                )
                sheet_rows += 1
            sheet_reports.append({"sheet": sheet_name, "period": period, "rows": sheet_rows, "skipped": skipped})
    finally:
        workbook.close()

    image_stats = {"uploaded": 0, "rows_with_image": 0, "upload_errors": 0}
    if upload_images:
        from app.oss_storage import upload_product_image

        rows_by_sheet: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            rows_by_sheet[row["source_sheet"]].append(row)
        with zipfile.ZipFile(path) as archive:
            for sheet_name, sheet_rows_list in rows_by_sheet.items():
                images = sheet_image_bytes(archive, sheet_name)
                for row in sheet_rows_list:
                    image = images.get(row["source_row"])
                    if image is None:
                        continue
                    data, ext = image
                    digest = hashlib.sha1(data).hexdigest()[:16]
                    try:
                        url = upload_product_image(data, ext, f"{SOURCE_TYPE}-{sheet_name}", row["source_row"], digest)
                    except Exception:
                        image_stats["upload_errors"] += 1
                        continue
                    if url:
                        row["image_url"] = url
                        row["snapshot"]["image_origin"] = "selection1_embedded"
                        image_stats["uploaded"] += 1
        image_stats["rows_with_image"] = sum(1 for row in rows if row.get("image_url"))

    return {
        "source_type": SOURCE_TYPE,
        "source_file": path.name,
        "source_sha256": sha256_file(path),
        "sheets": sheet_reports,
        "skipped_sheets": skipped_sheets,
        "row_count": len(rows),
        "image_stats": image_stats,
        "rows": rows,
    }


def _existing_key_index(db: Session, rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """(source_sheet, sub_sku) -> 'archive' | 'current_flow'，档案键优先。"""
    sheets = {row["source_sheet"] for row in rows}
    if not sheets:
        return {}
    index: dict[tuple[str, str], str] = {}
    for source_type, source_sheet, sub_sku in db.execute(
        select(
            models.NewProductOpportunity.source_type,
            models.NewProductOpportunity.source_sheet,
            models.NewProductOpportunity.sub_sku,
        ).where(
            models.NewProductOpportunity.source_type.in_([SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE]),
            models.NewProductOpportunity.source_sheet.in_(sheets),
        )
    ):
        kind = "archive" if source_type == SOURCE_TYPE else "current_flow"
        if index.get((source_sheet, sub_sku)) != "archive":
            index[(source_sheet, sub_sku)] = kind
    return index


def plan_selection1_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    existing = _existing_key_index(db, rows)
    counts = {
        "would_create": 0,
        "skipped_existing_archive": 0,
        "skipped_existing_current_flow": 0,
        "skipped_duplicate_in_file": 0,
    }
    by_period: dict[str, dict[str, int]] = {}
    planned: set[tuple[str, str]] = set()
    for row in rows:
        stats = by_period.setdefault(row["batch"], {"rows": 0, "would_create": 0, "skipped": 0})
        stats["rows"] += 1
        key = (row["source_sheet"], row["sub_sku"])
        kind = existing.get(key)
        if kind:
            counts[f"skipped_existing_{kind}"] += 1
            stats["skipped"] += 1
            continue
        if key in planned:
            counts["skipped_duplicate_in_file"] += 1
            stats["skipped"] += 1
            continue
        planned.add(key)
        counts["would_create"] += 1
        stats["would_create"] += 1
    return {**counts, "by_period": by_period}


def _reverted_batch_tags(db: Session) -> set[str]:
    return {
        (entry.detail or {}).get("batch_tag")
        for entry in db.scalars(select(models.AuditLog).where(models.AuditLog.action == REVERT_AUDIT_ACTION))
    }


def batch_already_imported(db: Session, source_sha256: str) -> bool:
    reverted = _reverted_batch_tags(db)
    for entry in db.scalars(select(models.AuditLog).where(models.AuditLog.action == AUDIT_ACTION)):
        detail = entry.detail or {}
        if detail.get("source_sha256") == source_sha256 and detail.get("batch_tag") not in reverted:
            return True
    return False


def apply_selection1_rows(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    source_label: str,
    batch_tag: str,
    imported_by: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    counts = {
        "created": 0,
        "skipped_existing_archive": 0,
        "skipped_existing_current_flow": 0,
        "skipped_duplicate_in_file": 0,
    }
    if source_sha256 and batch_already_imported(db, source_sha256):
        return {"batch_already_imported": True, "import_batch_id": None, **counts}

    batch = models.ImportBatch(
        source_type=SOURCE_TYPE,
        source_file=source_label,
        source_sheet="all",
        business_period="历史全期",
        imported_by=imported_by,
        status="running",
    )
    db.add(batch)
    db.flush()

    existing = _existing_key_index(db, rows)
    created_keys: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["source_sheet"], row["sub_sku"])
        kind = existing.get(key)
        if kind:
            # 已存在（含现行流程行）只计数跳过，绝不更新既有行。
            counts[f"skipped_existing_{kind}"] += 1
            continue
        if key in created_keys:
            counts["skipped_duplicate_in_file"] += 1
            continue
        opportunity = models.NewProductOpportunity(
            source_type=SOURCE_TYPE,
            source_file=row.get("source_file"),
            source_sheet=row["source_sheet"],
            source_row=row.get("source_row"),
            batch=row.get("batch"),
            country=row.get("country"),
            site=row.get("site"),
            developer_department=row.get("developer_department"),
            developer_name=row.get("developer_name"),
            category_level1=row.get("category_level1"),
            keyword=row.get("keyword"),
            image_url=row.get("image_url"),
            main_sku_name=row.get("main_sku_name"),
            main_sku=row["main_sku"],
            sub_sku_name=row.get("sub_sku_name"),
            sub_sku=row["sub_sku"],
            product_type=row.get("product_type"),
            reason=row.get("reason"),
            current_status=ARCHIVE_STATUS,
            snapshot=row["snapshot"],
            import_batch_id=batch.id,
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SourceRecordSnapshot(
                import_batch_id=batch.id,
                opportunity_id=opportunity.id,
                source_file=row.get("source_file"),
                source_sheet=row["source_sheet"],
                source_row=row.get("source_row"),
                column_range="fields_by_cell",
                payload=row["snapshot"],
            )
        )
        created_keys.add(key)
        counts["created"] += 1

    batch.created_count = counts["created"]
    batch.skipped_count = sum(value for key, value in counts.items() if key.startswith("skipped"))
    batch.status = "completed"
    audit(
        db,
        AUDIT_ACTION,
        "new_product_opportunity",
        None,
        {"batch_tag": batch_tag, "import_batch_id": batch.id, "source_sha256": source_sha256,
         "source_file": source_label, **counts},
        imported_by,
    )
    db.flush()
    return {"batch_already_imported": False, "import_batch_id": batch.id, **counts}


def revert_selection1_import(db: Session, batch_tag: str, actor: str | None = None) -> dict[str, int]:
    batch_ids = []
    for entry in db.scalars(select(models.AuditLog).where(models.AuditLog.action == AUDIT_ACTION)):
        detail = entry.detail or {}
        if detail.get("batch_tag") == batch_tag and detail.get("import_batch_id"):
            batch_ids.append(detail["import_batch_id"])
    opportunity_ids = list(
        db.scalars(
            select(models.NewProductOpportunity.id).where(
                models.NewProductOpportunity.source_type == SOURCE_TYPE,
                models.NewProductOpportunity.import_batch_id.in_(batch_ids),
            )
        )
    ) if batch_ids else []
    deleted_snapshots = 0
    if opportunity_ids:
        deleted_snapshots = db.execute(
            delete(models.SourceRecordSnapshot).where(models.SourceRecordSnapshot.opportunity_id.in_(opportunity_ids))
        ).rowcount
        db.execute(
            delete(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(opportunity_ids))
        )
    for batch_id in batch_ids:
        batch = db.get(models.ImportBatch, batch_id)
        if batch is not None:
            batch.status = "reverted"
    audit(
        db,
        REVERT_AUDIT_ACTION,
        "new_product_opportunity",
        None,
        {"batch_tag": batch_tag, "reverted_opportunities": len(opportunity_ids),
         "reverted_snapshots": deleted_snapshots, "import_batch_ids": batch_ids},
        actor,
    )
    db.flush()
    return {"reverted_opportunities": len(opportunity_ids), "reverted_snapshots": deleted_snapshots}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="选品1 历史期档案导入（仅新世代 0428+；本地解析/传图，rows 文件搬到服务器 apply；默认 dry-run）"
    )
    parser.add_argument("--workbook", help="选品1：海外仓开发部门开发新品认领-反馈*.xlsx 路径（parse 模式必填）")
    parser.add_argument("--upload-images", action="store_true", help="zip 直读内嵌图片并上传 OSS（需 OSS_UPLOAD_ENABLED=1）")
    parser.add_argument("--rows-out", help="解析结果 JSON 输出路径")
    parser.add_argument("--apply-rows", help="对 rows 文件执行入库（在目标环境跑；缺 --apply-dev 时只做 dry-run 统计）")
    parser.add_argument("--apply-dev", action="store_true", help="与 --apply-rows 连用，真正写库（受 APPLY_ALLOWED_ENVS 门控）")
    parser.add_argument("--revert", action="store_true", help="按 --batch-tag 整批撤销本导入器建的档案行")
    parser.add_argument("--batch-tag", default=f"selection1-history-{date.today():%Y%m%d}")
    parser.add_argument("--imported-by", default="history_selection1_import")
    parser.add_argument("--max-rows-per-sheet", type=int, default=None, help="调试用每 sheet 行数上限")
    args = parser.parse_args()

    if args.revert:
        from app.config import get_settings
        from app.db import SessionLocal

        settings = get_settings()
        if settings.app_env not in APPLY_ALLOWED_ENVS:
            raise SystemExit(f"revert blocked: app_env={settings.app_env}")
        with SessionLocal() as db:
            report = revert_selection1_import(db, args.batch_tag, actor=args.imported_by)
            db.commit()
        print(json.dumps({"mode": "revert", "batch_tag": args.batch_tag, **report}, ensure_ascii=False))
        return

    if args.apply_rows:
        from app.config import get_settings
        from app.db import SessionLocal

        payload = json.loads(Path(args.apply_rows).read_text(encoding="utf-8"))
        rows = payload["rows"]
        with SessionLocal() as db:
            if not args.apply_dev:
                plan = plan_selection1_rows(db, rows)
                print(json.dumps({"mode": "dry-run", "rows": len(rows), **plan}, ensure_ascii=False, indent=2))
                return
            settings = get_settings()
            if settings.app_env not in APPLY_ALLOWED_ENVS:
                raise SystemExit(f"apply blocked: app_env={settings.app_env}")
            counts = apply_selection1_rows(
                db,
                rows,
                source_label=payload.get("source_file", "selection1"),
                batch_tag=args.batch_tag,
                imported_by=args.imported_by,
                source_sha256=payload.get("source_sha256"),
            )
            db.commit()
        print(json.dumps({"mode": "apply", "batch_tag": args.batch_tag, **counts}, ensure_ascii=False, indent=2))
        return

    if not args.workbook:
        raise SystemExit("parse 模式需要 --workbook")
    report = parse_selection1_workbook(
        Path(args.workbook), upload_images=args.upload_images, max_rows_per_sheet=args.max_rows_per_sheet
    )
    summary = {key: value for key, value in report.items() if key != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if args.rows_out:
        Path(args.rows_out).write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"rows written to {args.rows_out}")


if __name__ == "__main__":
    main()
