from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.field_mapping import normalize_header, text_value
from app.historical_archive_import import APPLY_ALLOWED_ENVS

SOURCE_TYPES = {"PH": "history_central_ph", "TH": "history_central_th", "VN": "history_central_vn"}
ARCHIVE_STATUS = "historical_archive"
SHEET_PERIOD_PATTERN = re.compile(r"^(\d{1,2})\.(\d{1,2})$")
ERROR_VALUES = {"#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#REF!", "#VALUE!"}
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def business_period_from_sheet(sheet_name: str) -> str | None:
    match = SHEET_PERIOD_PATTERN.match(sheet_name.strip())
    if not match:
        return None
    return f"开发{int(match.group(1)):02d}{int(match.group(2)):02d}期"


def sheet_image_bytes(archive: zipfile.ZipFile, sheet_name: str) -> dict[int, tuple[bytes, str]]:
    """按行号取 sheet 内嵌图片（zip 直读，避免整簿载入内存）。"""
    workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    workbook_rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {rel.get("Id"): rel.get("Target") for rel in workbook_rels.iter(f"{REL_NS}Relationship")}
    sheet_path = None
    for sheet in workbook_xml.iter(f"{MAIN_NS}sheet"):
        if sheet.get("name") == sheet_name:
            target = rel_targets.get(sheet.get(f"{R_NS}id"), "")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            break
    if not sheet_path:
        return {}
    rels_path = f"xl/worksheets/_rels/{Path(sheet_path).name}.rels"
    if rels_path not in archive.namelist():
        return {}
    sheet_rels = ElementTree.fromstring(archive.read(rels_path))
    drawing_path = None
    for rel in sheet_rels.iter(f"{REL_NS}Relationship"):
        if rel.get("Type", "").endswith("/drawing"):
            drawing_path = str(Path("xl/worksheets") / rel.get("Target")).replace("\\", "/")
            drawing_path = re.sub(r"xl/worksheets/\.\./", "xl/", drawing_path)
            break
    if not drawing_path or drawing_path not in archive.namelist():
        return {}
    drawing_rels_path = f"xl/drawings/_rels/{Path(drawing_path).name}.rels"
    media_by_rid: dict[str, str] = {}
    if drawing_rels_path in archive.namelist():
        drawing_rels = ElementTree.fromstring(archive.read(drawing_rels_path))
        for rel in drawing_rels.iter(f"{REL_NS}Relationship"):
            target = str(Path("xl/drawings") / rel.get("Target")).replace("\\", "/")
            media_by_rid[rel.get("Id")] = re.sub(r"xl/drawings/\.\./", "xl/", target)
    images: dict[int, tuple[bytes, str]] = {}
    drawing = ElementTree.fromstring(archive.read(drawing_path))
    for anchor in [*drawing.iter(f"{XDR}twoCellAnchor"), *drawing.iter(f"{XDR}oneCellAnchor")]:
        anchor_from = anchor.find(f"{XDR}from")
        blip = anchor.find(f".//{A_NS}blip")
        if anchor_from is None or blip is None:
            continue
        row_element = anchor_from.find(f"{XDR}row")
        media_path = media_by_rid.get(blip.get(f"{R_NS}embed", ""))
        if row_element is None or not media_path or media_path not in archive.namelist():
            continue
        row = int(row_element.text or 0) + 1
        if row not in images:
            images[row] = (archive.read(media_path), Path(media_path).suffix.lstrip(".") or "png")
    return images


def parse_central_workbook(
    path: Path,
    country_code: str,
    upload_images: bool = False,
    max_rows_per_sheet: int | None = None,
) -> dict[str, Any]:
    source_type = SOURCE_TYPES[country_code]
    rows: list[dict[str, Any]] = []
    sheet_reports: list[dict[str, Any]] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_names = [name for name in workbook.sheetnames if business_period_from_sheet(name)]
        for sheet_name in sheet_names:
            worksheet = workbook[sheet_name]
            try:
                worksheet.reset_dimensions()
            except AttributeError:
                pass
            period = business_period_from_sheet(sheet_name)
            iterator = worksheet.iter_rows(values_only=True)
            header_top = next(iterator, ()) or ()
            header_bottom = next(iterator, ()) or ()
            headers: dict[int, str] = {}
            for index in range(max(len(header_top), len(header_bottom))):
                top = text_value(header_top[index]) if index < len(header_top) else None
                bottom = text_value(header_bottom[index]) if index < len(header_bottom) else None
                label = bottom or top
                if label:
                    headers[index] = label
            column_of = {normalize_header(label): index for index, label in headers.items()}

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
            field_cols = {
                "developer_department": col("开发部门"),
                "developer_name": col("开发员"),
                "category_level1": col("一级类目"),
                "keyword": col("开发关键词", "关键词"),
                "main_sku_name": col("主SKU名称"),
                "sub_sku_name": col("子SKU名称"),
                "product_type": col("产品类型"),
                "reason": col("开品理由"),
            }
            sheet_rows = 0
            skipped = 0
            for source_row, row in enumerate(iterator, start=3):
                if max_rows_per_sheet is not None and sheet_rows >= max_rows_per_sheet:
                    break
                sub_sku = text_value(row[sub_col]) if sub_col is not None and sub_col < len(row) else None
                if not sub_sku or sub_sku in ERROR_VALUES:
                    skipped += 1
                    continue
                cell = lambda index: row[index] if index is not None and index < len(row) else None  # noqa: E731
                fields_by_cell = {
                    get_column_letter(index + 1): {"header": headers.get(index), "value": _json_safe(value)}
                    for index, value in enumerate(row)
                    if value is not None and text_value(value)
                }
                main_sku = text_value(cell(main_col)) or sub_sku
                site_raw = text_value(cell(site_col))
                rows.append(
                    {
                        "source_type": source_type,
                        "source_file": path.name,
                        "source_sheet": sheet_name,
                        "source_row": source_row,
                        "batch": period,
                        "country": country_code,
                        "site": site_raw or country_code,
                        "main_sku": main_sku,
                        "sub_sku": sub_sku,
                        "image_row": source_row if image_col is not None else None,
                        **{
                            field: text_value(cell(index))
                            for field, index in field_cols.items()
                        },
                        "snapshot": {
                            "archive_type": "historical_central",
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
                        url = upload_product_image(data, ext, f"{row['source_type']}-{sheet_name}", row["source_row"], digest)
                    except Exception:
                        image_stats["upload_errors"] += 1
                        continue
                    if url:
                        row["image_url"] = url
                        row["snapshot"]["image_origin"] = "central_embedded"
                        image_stats["uploaded"] += 1
        image_stats["rows_with_image"] = sum(1 for row in rows if row.get("image_url"))

    return {
        "source_type": source_type,
        "source_file": path.name,
        "sheets": sheet_reports,
        "row_count": len(rows),
        "image_stats": image_stats,
        "rows": rows,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def apply_central_rows(db: Session, rows: list[dict[str, Any]], source_label: str, imported_by: str | None = None) -> dict[str, int]:
    batch = models.ImportBatch(
        source_type=rows[0]["source_type"] if rows else "history_central",
        source_file=source_label,
        source_sheet="all",
        business_period="历史全期",
        imported_by=imported_by,
        status="running",
    )
    db.add(batch)
    db.flush()
    counts = {"created": 0, "updated": 0, "image_backfilled": 0}
    for row in rows:
        existing = db.scalars(
            select(models.NewProductOpportunity).where(
                models.NewProductOpportunity.source_type == row["source_type"],
                models.NewProductOpportunity.batch == row["batch"],
                models.NewProductOpportunity.site == row["site"],
                models.NewProductOpportunity.main_sku == row["main_sku"],
                models.NewProductOpportunity.sub_sku == row["sub_sku"],
            )
        ).first()
        data = {
            "source_type": row["source_type"],
            "source_file": row["source_file"],
            "source_sheet": row["source_sheet"],
            "source_row": row["source_row"],
            "batch": row["batch"],
            "country": row["country"],
            "site": row["site"],
            "developer_department": row.get("developer_department"),
            "developer_name": row.get("developer_name"),
            "category_level1": row.get("category_level1"),
            "keyword": row.get("keyword"),
            "image_url": row.get("image_url"),
            "main_sku_name": row.get("main_sku_name"),
            "main_sku": row["main_sku"],
            "sub_sku_name": row.get("sub_sku_name"),
            "sub_sku": row["sub_sku"],
            "product_type": row.get("product_type"),
            "reason": row.get("reason"),
            "snapshot": row["snapshot"],
        }
        if existing:
            for field, value in data.items():
                if field == "image_url" and not value:
                    continue
                setattr(existing, field, value)
            counts["updated"] += 1
            opportunity = existing
        else:
            opportunity = models.NewProductOpportunity(**data, current_status=ARCHIVE_STATUS, import_batch_id=batch.id)
            db.add(opportunity)
            db.flush()
            counts["created"] += 1
        db.add(
            models.SourceRecordSnapshot(
                import_batch_id=batch.id,
                opportunity_id=opportunity.id,
                source_file=row["source_file"],
                source_sheet=row["source_sheet"],
                source_row=row["source_row"],
                column_range="fields_by_cell",
                payload=row["snapshot"],
            )
        )
        if row.get("image_url"):
            for other in db.scalars(
                select(models.NewProductOpportunity).where(
                    models.NewProductOpportunity.sub_sku == row["sub_sku"],
                    models.NewProductOpportunity.source_type != row["source_type"],
                    (models.NewProductOpportunity.image_url.is_(None)) | (models.NewProductOpportunity.image_url == ""),
                )
            ):
                other.image_url = row["image_url"]
                counts["image_backfilled"] += 1
    batch.created_count = counts["created"]
    batch.updated_count = counts["updated"]
    batch.status = "completed"
    db.flush()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="三国中央表历史档案导入（本地解析/传图，rows 文件可搬到服务器 apply）")
    parser.add_argument("--workbook", help="东南亚海外仓新品表-XX.xlsx 路径（parse 模式必填）")
    parser.add_argument("--country", choices=["PH", "TH", "VN"], help="国家（parse 模式必填）")
    parser.add_argument("--upload-images", action="store_true", help="抽取内嵌图片并上传 OSS（需 OSS_UPLOAD_ENABLED=1）")
    parser.add_argument("--rows-out", help="解析结果 JSONL 输出路径")
    parser.add_argument("--apply-rows", help="对 rows 文件执行入库（在目标环境跑）")
    parser.add_argument("--apply-dev", action="store_true", help="与 --apply-rows 连用，真正写库")
    parser.add_argument("--imported-by", default="history_central_import")
    parser.add_argument("--max-rows-per-sheet", type=int, default=None, help="调试用每 sheet 行数上限")
    args = parser.parse_args()

    if args.apply_rows:
        from app.config import get_settings
        from app.db import SessionLocal

        payload = json.loads(Path(args.apply_rows).read_text(encoding="utf-8"))
        rows = payload["rows"]
        if not args.apply_dev:
            print(json.dumps({"mode": "dry-run", "rows": len(rows)}, ensure_ascii=False))
            return
        settings = get_settings()
        if settings.app_env not in APPLY_ALLOWED_ENVS:
            raise SystemExit(f"apply blocked: app_env={settings.app_env}")
        with SessionLocal() as db:
            counts = apply_central_rows(db, rows, source_label=payload.get("source_file", "central"), imported_by=args.imported_by)
            db.commit()
        print(json.dumps({"mode": "apply", **counts}, ensure_ascii=False))
        return

    if not args.workbook or not args.country:
        raise SystemExit("parse 模式需要 --workbook 与 --country")
    report = parse_central_workbook(
        Path(args.workbook), args.country, upload_images=args.upload_images, max_rows_per_sheet=args.max_rows_per_sheet
    )
    summary = {key: value for key, value in report.items() if key != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if args.rows_out:
        Path(args.rows_out).write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"rows written to {args.rows_out}")


if __name__ == "__main__":
    main()
