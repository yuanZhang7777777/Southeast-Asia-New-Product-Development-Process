"""选品1 历史期档案模式导入器（本次迁移有效期，绝不建认领/任务/通知）。

- 范围：开发0414期至开发0721期，以及开发-财根团队汇总；其它期跳过并在
  `skipped_sheets` 中列出。
- 表头动态探测：前 3 行内找同时含『主SKU』『子SKU』表头的行定为表头行；其下一行若
  主/子SKU 列已有值则视为单层表头（数据紧跟，如开发0827期），否则该行按第二层表头
  处理（子字段行或空行均可，覆盖新世代双层与旧世代『表头+空行+数据』变体）。
- 档案行：NewProductOpportunity(source_type=history_selection1, current_status 与
  historical_central_import 档案行一致)；快照 `fields_by_cell` 按列字母全列保真，
  规避 cells 快照缺 BY:CB、同名表头/同别名串值只存第一列的问题。
  旧世代无『站点』列：site/country 置空，历史缺失不造数。
- 判重键：来源命名空间 + 业务期 + 国家/站点（缺失时 sheet 隔离）+ 主SKU + 子SKU；跨来源不合并。
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
from app.historical_opportunity_dedupe import canonical_business_period
from app.historical_watchlist import sha256_file
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE
from app.services import audit
from app.site_codes import SITE_ALIASES, normalize_site_code

SOURCE_TYPE = "history_selection1"
AUDIT_ACTION = "history.selection1_imported"
REVERT_AUDIT_ACTION = "history.selection1_import_reverted"
SHEET_PERIOD_PATTERN = re.compile(r"开发(\d{4})期")
SPECIAL_SHEET_PERIODS = {"开发-财根团队汇总": "开发0727期-财根"}
NEW_GENERATION_MIN = 414  # 用户拍板（2026-07-26）：0414/0421 与新世代同表头结构，一并纳入
LEGACY_PERIODS = {"0815", "0820", "0827", "0903", "0908", "0910", "0917", "0924"}  # 当前工作簿已确认的去年旧期；未来新期不按 MMDD 阈值误排除。
MIGRATION_PERIODS = {"0414", "0421", "0428", "0512", "0519", "0526", "0602", "0609", "0616", "0623", "0630", "0707", "0714", "0721"}
HEADER_PROBE_ROWS = 3  # 表头行动态探测范围：前 3 行
SUMMARY_LABELS = {"小计", "合计", "总计", "汇总"}
VALID_PRODUCT_TYPES = {"引流", "绑定", "利润", "稳定", "淘汰", "清仓", "引流款", "利润款", "稳定款", "淘汰款", "清仓款"}
FIELD_ALIASES = {
    "developer_department": ("开发部门", "部门"),
    "developer_name": ("开发员",),
    "category_level1": ("一级类目",),
    # 关键词组：旧世代别名（防个别期表头变体）
    "keyword": ("关键词", "开发关键词", "关键词组"),
    # 主SKU名称（33）：开发0903期实测表头
    "main_sku_name": ("主SKU名称", "主SKU名称（33）"),
    "sub_sku_name": ("子SKU名称",),
    "product_type": ("产品类型", "引流or绑定or利润", "产品类型/引流or绑定or利润"),
    "reason": ("开品理由",),
}


def period_from_sheet(sheet_name: str) -> str | None:
    match = SHEET_PERIOD_PATTERN.search(sheet_name)
    return match.group(1) if match else None


def sheet_skip_reason(sheet_name: str) -> str | None:
    period = period_from_sheet(sheet_name)
    if sheet_name in SPECIAL_SHEET_PERIODS:
        return None
    if period is None:
        return "非期数sheet"
    if int(period) < NEW_GENERATION_MIN:
        return "早于0414期"
    if period in LEGACY_PERIODS:
        return "排除旧期"
    if period not in MIGRATION_PERIODS:
        return "排除非本次历史期"
    return None


def sheet_generation(sheet_name: str) -> str | None:
    return "current" if sheet_skip_reason(sheet_name) is None else None


def _known_site_value(value: Any) -> str | None:
    text = text_value(value)
    if not text:
        return None
    compact = "".join(text.split())
    if compact in SITE_ALIASES or compact.upper() in SITE_ALIASES:
        return text
    return None


def _leading_site_value(row: tuple[Any, ...], before_column: int) -> str | None:
    for index in range(max(before_column, 0)):
        site = _known_site_value(row[index] if index < len(row) else None)
        if site:
            return site
    return None


def _checkbox_site_columns(sheet_name: str, header_bottom: tuple[Any, ...]) -> dict[int, str]:
    if sheet_name != "开发0414期":
        return {}
    columns: dict[int, str] = {}
    for index, value in enumerate(header_bottom):
        site = _known_site_value(value)
        code = normalize_site_code(site)
        if code in {"PH", "TH", "VN", "MY", "SG", "ID"}:
            columns[index] = code
    return columns


def _checked_checkbox_sites(row: tuple[Any, ...], checkbox_columns: dict[int, str]) -> set[str]:
    checked: set[str] = set()
    for index, site in checkbox_columns.items():
        value = (text_value(row[index] if index < len(row) else None) or "").strip().upper()
        if value in {"✔", "√", "是", "YES", "Y", "1"}:
            checked.add(site)
    return checked


def _append_quality_issue(snapshot: dict[str, Any], issue: str) -> None:
    issues = snapshot.setdefault("data_quality_issues", [])
    if issue not in issues:
        issues.append(issue)


def _resolve_0414_checkbox_sites(sheet_rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sheet_rows:
        if row.pop("_checkbox_pending", False):
            grouped[row["main_sku"]].append(row)
        else:
            row.pop("_checkbox_sites", None)
    for group_rows in grouped.values():
        group_sites: set[str] = set()
        direct_sites: dict[int, set[str]] = {}
        for index, row in enumerate(group_rows):
            sites = set(row.pop("_checkbox_sites", set()))
            direct_sites[index] = sites
            group_sites.update(sites)
        for index, row in enumerate(group_rows):
            sites = direct_sites[index]
            snapshot = row["snapshot"]
            if len(sites) == 1:
                site = next(iter(sites))
                row["country"] = site
                row["site"] = site
                snapshot["site_raw"] = site
                snapshot["site_resolution"] = "checkbox_mark"
            elif len(sites) > 1:
                snapshot["site_resolution"] = "checkbox_multiple_selected"
                _append_quality_issue(snapshot, "multiple_checkbox_sites")
            elif len(group_sites) == 1:
                site = next(iter(group_sites))
                row["country"] = site
                row["site"] = site
                snapshot["site_raw"] = site
                snapshot["site_resolution"] = "checkbox_inherited"
            elif not group_sites:
                snapshot["site_resolution"] = "checkbox_group_unchecked"
                _append_quality_issue(snapshot, "missing_checkbox_site")
            else:
                snapshot["site_resolution"] = "checkbox_group_ambiguous"
                _append_quality_issue(snapshot, "ambiguous_checkbox_sites")


def _sku_header_columns(row: tuple[Any, ...]) -> tuple[int | None, int | None]:
    """行内首个『主SKU』/『子SKU』表头列（大小写不敏感；0820期存在重复子SKU表头，取首列）。"""
    main_index = sub_index = None
    for index, value in enumerate(row):
        key = normalize_header(value).upper()
        if key == "主SKU" and main_index is None:
            main_index = index
        elif key == "子SKU" and sub_index is None:
            sub_index = index
    return main_index, sub_index


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
    selected_sheets: set[str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    sheet_reports: list[dict[str, Any]] = []
    skipped_sheets: list[dict[str, Any]] = []
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet_name in workbook.sheetnames:
            if selected_sheets is not None and sheet_name not in selected_sheets:
                skipped_sheets.append({"sheet": sheet_name, "reason": "不在本次导入范围"})
                continue
            reason = sheet_skip_reason(sheet_name)
            if reason:
                skipped_sheets.append({"sheet": sheet_name, "reason": reason})
                continue
            period = SPECIAL_SHEET_PERIODS.get(sheet_name) or f"开发{period_from_sheet(sheet_name)}期"
            worksheet = workbook[sheet_name]
            try:
                worksheet.reset_dimensions()
            except AttributeError:
                pass
            iterator = worksheet.iter_rows(values_only=True)
            buffered: list[tuple[Any, ...]] = []

            def row_at(position: int) -> tuple[Any, ...] | None:
                while len(buffered) <= position:
                    try:
                        buffered.append(next(iterator))
                    except StopIteration:
                        return None
                return buffered[position]

            header_pos = main_header_col = sub_header_col = None
            for position in range(HEADER_PROBE_ROWS):
                candidate = row_at(position)
                if candidate is None:
                    break
                main_index, sub_index = _sku_header_columns(candidate)
                if main_index is not None and sub_index is not None:
                    header_pos, main_header_col, sub_header_col = position, main_index, sub_index
                    break
            if header_pos is None:
                skipped_sheets.append({"sheet": sheet_name, "reason": "前3行未探测到主SKU/子SKU表头"})
                continue
            header_top = row_at(header_pos) or ()
            # 单层/双层探测：表头行下一行的主/子SKU列已有值 → 单层表头、数据紧跟（旧世代0827期）；
            # 否则该行按第二层表头处理（新世代子字段行，或旧世代空行/双层子字段行）。
            probe = row_at(header_pos + 1)

            def probe_value(index: int | None) -> str | None:
                if probe is None or index is None or index >= len(probe):
                    return None
                return text_value(probe[index])

            single_layer = bool(probe_value(main_header_col) or probe_value(sub_header_col))
            header_bottom = () if single_layer or probe is None else probe
            data_pos = header_pos + (1 if single_layer else 2)
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

            site_col = col("站点", "国家")  # 旧世代无站点列 → None，site/country 置空
            # 主/子SKU 直接用表头探测列：与探测判定一致，且大小写不敏感（col() 区分大小写）。
            main_col = main_header_col
            sub_col = sub_header_col
            image_col = col("产品图片")
            field_cols = {field: col(*aliases) for field, aliases in FIELD_ALIASES.items()}
            checkbox_site_columns = _checkbox_site_columns(sheet_name, header_bottom)

            def cell(row: tuple[Any, ...], index: int | None) -> Any:
                return row[index] if index is not None and index < len(row) else None

            def data_rows():
                position = data_pos
                while position < len(buffered):
                    yield position + 1, buffered[position]
                    position += 1
                for values in iterator:
                    yield position + 1, values
                    position += 1

            sheet_rows = 0
            skipped = 0
            parsed_sheet_rows: list[dict[str, Any]] = []
            carried_main_sku: str | None = None
            carried_main_sku_name: str | None = None
            for source_row, row in data_rows():
                if max_rows_per_sheet is not None and sheet_rows >= max_rows_per_sheet:
                    break
                sub_sku = text_value(cell(row, sub_col))
                if not sub_sku or sub_sku in ERROR_VALUES:
                    skipped += 1
                    continue
                site_raw = text_value(cell(row, site_col))
                site_resolution = "header_site_column" if site_raw else None
                if not site_raw and site_col is None:
                    site_raw = _leading_site_value(row, main_col)
                    if site_raw:
                        site_resolution = "leading_site_column"
                checkbox_sites = _checked_checkbox_sites(row, checkbox_site_columns)
                checkbox_pending = bool(checkbox_site_columns) and not site_raw
                if checkbox_pending:
                    site_resolution = "checkbox_pending"
                source_main_sku = text_value(cell(row, main_col))
                fields = {field: text_value(cell(row, index)) for field, index in field_cols.items()}
                if fields["product_type"] not in VALID_PRODUCT_TYPES:
                    fields["product_type"] = None
                if _is_summary_row(site_raw, source_main_sku, sub_sku, fields["main_sku_name"], fields["sub_sku_name"]):
                    carried_main_sku = None
                    carried_main_sku_name = None
                    skipped += 1
                    continue
                if _is_repeated_header_row(sub_sku, source_main_sku):
                    carried_main_sku = None
                    carried_main_sku_name = None
                    skipped += 1
                    continue

                inherited_fields: dict[str, str] = {}
                backfilled_fields: dict[str, dict[str, str]] = {}
                if source_main_sku:
                    main_sku = source_main_sku
                    carried_main_sku = source_main_sku
                    carried_main_sku_name = fields["main_sku_name"]
                elif carried_main_sku:
                    main_sku = carried_main_sku
                    inherited_fields["main_sku"] = main_sku
                    if carried_main_sku_name:
                        fields["main_sku_name"] = carried_main_sku_name
                        inherited_fields["main_sku_name"] = carried_main_sku_name
                else:
                    main_sku = sub_sku
                    backfilled_fields["main_sku"] = {"source": "sub_sku", "value": sub_sku}
                if not fields["sub_sku_name"] and fields["main_sku_name"]:
                    fields["sub_sku_name"] = fields["main_sku_name"]
                    backfilled_fields["sub_sku_name"] = {
                        "source": "main_sku_name", "value": fields["main_sku_name"],
                    }
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
                parsed_sheet_rows.append(
                    {
                        "source_type": SOURCE_TYPE,
                        "source_file": path.name,
                        "source_sheet": sheet_name,
                        "source_row": source_row,
                        "batch": period,
                        "country": country,
                        "site": site_raw or country,
                        "main_sku": main_sku,
                        "sub_sku": sub_sku,
                        "image_row": source_row if image_col is not None else None,
                        **fields,
                        "snapshot": {
                            "archive_type": "historical_selection1",
                            "business_period": period,
                            "site_raw": site_raw,
                            **({"site_resolution": site_resolution} if site_resolution else {}),
                            **({"inherited_fields": inherited_fields} if inherited_fields else {}),
                            **({"backfilled_fields": backfilled_fields} if backfilled_fields else {}),
                            "fields_by_cell": fields_by_cell,
                            "source_reference": {
                                "source_file": path.name,
                                "source_sheet": sheet_name,
                                "source_row": source_row,
                            },
                        },
                    }
                )
                if checkbox_site_columns:
                    parsed_sheet_rows[-1]["_checkbox_sites"] = checkbox_sites
                    parsed_sheet_rows[-1]["_checkbox_pending"] = checkbox_pending
                sheet_rows += 1
            if checkbox_site_columns:
                _resolve_0414_checkbox_sites(parsed_sheet_rows)
            rows.extend(parsed_sheet_rows)
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


BACKFILL_EMPTY_FIELDS = (
    "country", "site", "developer_department", "developer_name", "category_level1", "keyword",
    "image_url", "main_sku_name", "sub_sku_name", "product_type", "reason",
)


def _selection1_identity(
    *,
    source_sheet: str | None,
    batch: str | None,
    country: str | None,
    site: str | None,
    main_sku: str | None,
    sub_sku: str | None,
    source_type: str | None,
) -> tuple[str, str, str, str, str]:
    sheet = (source_sheet or "").strip().casefold()
    location = normalize_site_code(country or site) or f"sheet:{sheet}"
    return (
        sheet,
        canonical_business_period(batch, source_type=source_type),
        location,
        (main_sku or "").strip().upper(),
        (sub_sku or "").strip().upper(),
    )


def _row_identity(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return _selection1_identity(
        source_sheet=row.get("source_sheet"),
        batch=row.get("batch"),
        country=row.get("country"),
        site=row.get("site"),
        main_sku=row.get("main_sku"),
        sub_sku=row.get("sub_sku"),
        source_type=row.get("source_type", SOURCE_TYPE),
    )


SELECTION1_NORMALIZE_FIELDS = tuple(field for field in BACKFILL_EMPTY_FIELDS if field not in {"country", "site"})


def _selection1_merge_identity(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return ((row.get("source_file") or "").strip(), *_row_identity(row))


def _selection1_display_identity(row: dict[str, Any]) -> list[str]:
    location = normalize_site_code(row.get("country") or row.get("site")) or f"sheet:{(row.get('source_sheet') or '').strip().casefold()}"
    return [
        canonical_business_period(row.get("batch"), source_type=row.get("source_type", SOURCE_TYPE)),
        location.casefold(),
        (row.get("main_sku") or "").strip().upper(),
        (row.get("sub_sku") or "").strip().upper(),
    ]


def _distinct_selection1_field_values(rows: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = text_value(row.get(field))
        if not value:
            continue
        comparison = normalize_header(value)
        if comparison not in seen:
            seen.add(comparison)
            values.append(value)
    return values


def normalize_selection1_history_rows(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    """Merge same-source duplicate identities; keep real business conflicts for review."""
    groups: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row is not None:
            groups.setdefault(_selection1_merge_identity(row), []).append(row)

    unified_rows: list[dict[str, Any]] = []
    merged_groups: list[dict[str, Any]] = []
    business_repair_rows: list[dict[str, Any]] = []
    for group in groups.values():
        group = sorted(group, key=lambda item: int(item.get("source_row") or 0))
        source_rows = [item.get("source_row") for item in group]
        conflicts = {
            field: values
            for field in SELECTION1_NORMALIZE_FIELDS
            if len(values := _distinct_selection1_field_values(group, field)) > 1
        }
        if conflicts:
            first = group[0]
            business_repair_rows.append(
                {
                    "source_file": first.get("source_file"),
                    "source_sheet": first.get("source_sheet"),
                    "business_period": first.get("batch"),
                    "country": first.get("country"),
                    "site": first.get("site"),
                    "main_sku": first.get("main_sku"),
                    "sub_sku": first.get("sub_sku"),
                    "source_rows": source_rows,
                    "conflicting_fields": conflicts,
                }
            )
            continue

        merged = dict(group[0])
        for field in SELECTION1_NORMALIZE_FIELDS:
            values = _distinct_selection1_field_values(group, field)
            if values:
                merged[field] = values[0]
        merged["source_rows"] = source_rows
        merged_snapshot = dict(merged.get("snapshot") or {})
        if len(group) > 1:
            merged_snapshot["merged_source_rows"] = source_rows
            merged_snapshot["merged_source_snapshots"] = [item.get("snapshot") or {} for item in group]
            merged_groups.append({"identity": _selection1_display_identity(merged), "source_rows": source_rows})
        merged["snapshot"] = merged_snapshot
        unified_rows.append(merged)

    return {
        "rows": unified_rows,
        "merged_groups": merged_groups,
        "business_repair_rows": business_repair_rows,
    }

def _opportunity_identity(opportunity: models.NewProductOpportunity) -> tuple[str, str, str, str, str]:
    return _selection1_identity(
        source_sheet=opportunity.source_sheet,
        batch=opportunity.batch,
        country=opportunity.country,
        site=opportunity.site,
        main_sku=opportunity.main_sku,
        sub_sku=opportunity.sub_sku,
        source_type=opportunity.source_type,
    )

def _existing_opportunity_index(
    db: Session, rows: list[dict[str, Any]]
) -> dict[tuple[str, str, str, str, str], tuple[str, models.NewProductOpportunity]]:
    sheets = {row["source_sheet"] for row in rows}
    if not sheets:
        return {}
    index: dict[tuple[str, str, str, str, str], tuple[str, models.NewProductOpportunity]] = {}
    opportunities = db.scalars(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type.in_([SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE]),
            models.NewProductOpportunity.source_sheet.in_(sheets),
        )
    )
    for opportunity in opportunities:
        key = _opportunity_identity(opportunity)
        kind = "archive" if opportunity.source_type == SOURCE_TYPE else "current_flow"
        if key not in index or index[key][0] != "archive":
            index[key] = (kind, opportunity)
    return index


def _existing_key_index(db: Session, rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], str]:
    return {key: kind for key, (kind, _) in _existing_opportunity_index(db, rows).items()}


def _backfill_existing_opportunity(
    db: Session,
    opportunity: models.NewProductOpportunity,
    row: dict[str, Any],
    import_batch_id: str,
) -> bool:
    changed = False
    for field in BACKFILL_EMPTY_FIELDS:
        if getattr(opportunity, field) in (None, "") and row.get(field) not in (None, ""):
            setattr(opportunity, field, row[field])
            changed = True

    snapshot = dict(opportunity.snapshot or {})
    if opportunity.source_type == CURRENT_SELECTION1_SOURCE_TYPE:
        updated_snapshot = {**snapshot, "historical_selection1": row["snapshot"]}
    else:
        updated_snapshot = {**snapshot, **row["snapshot"]}
    if updated_snapshot != snapshot:
        opportunity.snapshot = updated_snapshot
        changed = True

    source_snapshot = db.scalar(
        select(models.SourceRecordSnapshot).where(
            models.SourceRecordSnapshot.opportunity_id == opportunity.id,
            models.SourceRecordSnapshot.source_file == row.get("source_file"),
            models.SourceRecordSnapshot.source_sheet == row["source_sheet"],
            models.SourceRecordSnapshot.source_row == row.get("source_row"),
        )
    )
    if source_snapshot is None:
        db.add(
            models.SourceRecordSnapshot(
                import_batch_id=import_batch_id,
                opportunity_id=opportunity.id,
                source_file=row.get("source_file"),
                source_sheet=row["source_sheet"],
                source_row=row.get("source_row"),
                column_range="fields_by_cell",
                payload=row["snapshot"],
            )
        )
        changed = True
    return changed

def plan_selection1_rows(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalization = normalize_selection1_history_rows(rows)
    rows = normalization["rows"]
    existing = _existing_key_index(db, rows)
    counts = {
        "would_create": 0,
        "skipped_missing_identity": 0,
        "skipped_existing_archive": 0,
        "skipped_existing_current_flow": 0,
        "skipped_duplicate_in_file": 0,
        "skipped_conflicting_duplicate_in_file": len(normalization["business_repair_rows"]),
        "merged_duplicate_groups": len(normalization["merged_groups"]),
    }
    by_period: dict[str, dict[str, int]] = {}
    planned: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        stats = by_period.setdefault(row["batch"], {"rows": 0, "would_create": 0, "skipped": 0})
        stats["rows"] += 1
        if not row.get("main_sku") or not row.get("sub_sku"):
            counts["skipped_missing_identity"] += 1
            stats["skipped"] += 1
            continue
        key = _row_identity(row)
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
    return {**counts, "by_period": by_period, "business_repair_rows": normalization["business_repair_rows"]}


def _reverted_batch_tags(db: Session) -> set[str]:
    return {
        (entry.detail or {}).get("batch_tag")
        for entry in db.scalars(select(models.AuditLog).where(models.AuditLog.action == REVERT_AUDIT_ACTION))
    }


def batch_already_imported(db: Session, source_sha256: str, batch_tag: str) -> bool:
    # 键=文件指纹+批次标签：同文件换新标签允许扩范围补导（行级判重兜底防重复建行）。
    reverted = _reverted_batch_tags(db)
    for entry in db.scalars(select(models.AuditLog).where(models.AuditLog.action == AUDIT_ACTION)):
        detail = entry.detail or {}
        if (
            detail.get("source_sha256") == source_sha256
            and detail.get("batch_tag") == batch_tag
            and detail.get("batch_tag") not in reverted
        ):
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
    normalization = normalize_selection1_history_rows(rows)
    rows = normalization["rows"]
    counts = {
        "created": 0,
        "backfilled_existing_archive": 0,
        "backfilled_existing_current_flow": 0,
        "skipped_missing_identity": 0,
        "skipped_existing_archive": 0,
        "skipped_existing_current_flow": 0,
        "skipped_duplicate_in_file": 0,
        "skipped_conflicting_duplicate_in_file": len(normalization["business_repair_rows"]),
        "merged_duplicate_groups": len(normalization["merged_groups"]),
    }
    if source_sha256 and batch_already_imported(db, source_sha256, batch_tag):
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

    existing_rows = _existing_opportunity_index(db, rows)
    created_keys: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        if not row.get("main_sku") or not row.get("sub_sku"):
            counts["skipped_missing_identity"] += 1
            continue
        key = _row_identity(row)
        existing = existing_rows.get(key)
        kind = existing[0] if existing else None
        if kind:
            counts[f"skipped_existing_{kind}"] += 1
            if _backfill_existing_opportunity(db, existing[1], row, batch.id):
                counts[f"backfilled_existing_{kind}"] += 1
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
    return {"batch_already_imported": False, "import_batch_id": batch.id, **counts, "business_repair_rows": normalization["business_repair_rows"]}


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
        description="选品1 历史期档案导入（0414+，排除已确认去年旧期；本地解析/传图，rows 文件搬到服务器 apply；默认 dry-run）"
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
    parser.add_argument("--sheet", action="append", dest="selected_sheets", help="仅解析指定 sheet；可重复传入")
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
        Path(args.workbook), upload_images=args.upload_images, max_rows_per_sheet=args.max_rows_per_sheet,
        selected_sheets=set(args.selected_sheets) if args.selected_sheets else None
    )
    summary = {key: value for key, value in report.items() if key != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if args.rows_out:
        Path(args.rows_out).write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"rows written to {args.rows_out}")


if __name__ == "__main__":
    main()
