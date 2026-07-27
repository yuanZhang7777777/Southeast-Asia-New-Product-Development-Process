"""选品2历史档案只读解析器。

只解析来源事实，不写库、不匹配运营、不创建任务。认领栏中只有“销售员 + 数值单销”
形成历史已认领证据；拒绝理由、非数值、空值都只保留在来源快照。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from app.field_mapping import json_safe_value, text_value

SOURCE_TYPE = "history_selection2"
ARCHIVE_STATUS = "historical_archive"
MAX_SOURCE_COLUMN = column_index_from_string("AV")
PERIOD_PATTERN = re.compile(r"(?P<month>\d{1,2})\.(?P<day>\d{1,2})期|(?P<compact>\d{3,4})期")
INFRINGEMENT_TEXT = "侵权商品"
CLAIM_GROUPS = (
    ("AL", "AN", "AL:AN"),
    ("AO", "AP", "AO:AP"),
    ("AQ", "AR", "AQ:AR"),
    ("AS", "AT", "AS:AT"),
    ("AU", "AV", "AU:AV"),
)
CLAIM_SCAN_COLUMNS = tuple(
    get_column_letter(index)
    for index in range(column_index_from_string("AL"), column_index_from_string("AV") + 1)
)


def period_from_sheet(sheet_name: str) -> str | None:
    match = PERIOD_PATTERN.search(sheet_name)
    if not match:
        return None
    if compact := match.group("compact"):
        return compact.zfill(4)
    return f"{int(match.group('month')):02d}{int(match.group('day')):02d}"


def parse_selection2_workbook(path: Path, max_rows_per_sheet: int | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    sheet_reports: list[dict[str, Any]] = []
    skipped_sheets: list[dict[str, str]] = []
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        periods: list[tuple[int, str, str]] = []
        for sheet_name in workbook.sheetnames:
            period = period_from_sheet(sheet_name)
            if period is None:
                skipped_sheets.append({"sheet": sheet_name, "reason": "非期数sheet"})
                continue
            periods.append((int(period), sheet_name, period))
            worksheet = workbook[sheet_name]
            try:
                worksheet.reset_dimensions()
            except AttributeError:
                pass
            sheet_rows = skipped = 0
            for source_row, row in enumerate(worksheet.iter_rows(min_row=2, max_col=MAX_SOURCE_COLUMN, values_only=True), start=2):
                if max_rows_per_sheet is not None and sheet_rows >= max_rows_per_sheet:
                    break
                parsed = parse_historical_selection2_row(
                    row,
                    source_file=path.name,
                    source_sheet=sheet_name,
                    source_row=source_row,
                    business_period=f"财根开发新品{period}期",
                )
                if parsed is None:
                    skipped += 1
                    continue
                rows.append(parsed)
                sheet_rows += 1
            sheet_reports.append({"sheet": sheet_name, "period": period, "rows": sheet_rows, "skipped": skipped})
    finally:
        workbook.close()
    latest = max(periods, default=None)
    return {
        "source_type": SOURCE_TYPE,
        "source_file": path.name,
        "readable": True,
        "latest_sheet": latest[1] if latest else None,
        "latest_period": latest[2] if latest else None,
        "sheets": sheet_reports,
        "skipped_sheets": skipped_sheets,
        "row_count": len(rows),
        "rows": rows,
    }


def inspect_selection2_workbook(path: Path) -> dict[str, Any]:
    try:
        report = parse_selection2_workbook(path, max_rows_per_sheet=0)
    except Exception as exc:
        return {
            "source_type": SOURCE_TYPE,
            "source_file": path.name,
            "readable": False,
            "latest_sheet": None,
            "latest_period": None,
            "sheets": [],
            "skipped_sheets": [],
            "row_count": 0,
            "error": f"could not open workbook: {exc}",
        }
    return {key: value for key, value in report.items() if key != "rows"}


def parse_historical_selection2_row(
    row: tuple[Any, ...],
    *,
    source_file: str,
    source_sheet: str,
    source_row: int,
    business_period: str | None = None,
) -> dict[str, Any] | None:
    values = {
        get_column_letter(index): json_safe_value(cell_value(row, get_column_letter(index)))
        for index in range(1, MAX_SOURCE_COLUMN + 1)
    }
    sub_sku = text_value(values.get("C"))
    if not sub_sku or _is_repeated_header(sub_sku):
        return None
    main_sku = text_value(values.get("B")) or sub_sku
    snapshot = {
        "archive_type": "historical_selection2",
        "business_period": business_period or source_sheet,
        "fields_by_cell": fields_by_cell(values),
        "source_reference": {"source_file": source_file, "source_sheet": source_sheet, "source_row": source_row},
    }
    archive_only_reason = None
    operator_match_policy = "none"
    claims: list[dict[str, Any]] = []
    rejected_sources: list[dict[str, Any]] = []
    if has_infringement_marker(values):
        archive_only_reason = "infringing_product"
        operator_match_policy = "skip"
    else:
        claims, rejected_sources = parse_claim_sources(values)
        archive_only_reason = None if claims or rejected_sources else "historical_unclaimed"
    snapshot["claims"] = claims
    snapshot["rejected_sources"] = rejected_sources
    snapshot["archive_only_reason"] = archive_only_reason
    return {
        "source_type": SOURCE_TYPE,
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "batch": business_period or source_sheet,
        "current_status": ARCHIVE_STATUS,
        "main_sku": main_sku,
        "sub_sku": sub_sku,
        "main_sku_name": text_value(values.get("E")),
        "sub_sku_name": text_value(values.get("F")),
        "image_url": text_value(values.get("G")),
        "snapshot": snapshot,
        "claims": claims,
        "rejected_sources": rejected_sources,
        "archive_only_reason": archive_only_reason,
        "operator_match_policy": operator_match_policy,
        "task_policy": "none",
    }


def parse_claim_sources(values: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claims: list[dict[str, Any]] = []
    rejected_sources: list[dict[str, Any]] = []
    for name_column, value_column, source_column in CLAIM_GROUPS:
        salesperson = text_value(values.get(name_column))
        raw_value = values.get(value_column)
        daily_sales = strict_positive_number(raw_value)
        if salesperson and daily_sales is not None:
            claims.append(
                {
                    "salesperson_name": salesperson,
                    "claim_result": "claim",
                    "claim_daily_sales": daily_sales,
                    "source_column": source_column,
                }
            )
            continue
        if salesperson and raw_value not in (None, ""):
            rejected_sources.append(
                {"salesperson_name": salesperson, "raw_value": raw_value, "source_column": source_column}
            )
    return claims, rejected_sources


def strict_positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if number > 0 else None
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    number = float(text)
    return number if number > 0 else None


def has_infringement_marker(values: dict[str, Any]) -> bool:
    return any(text_value(values.get(column)) == INFRINGEMENT_TEXT for column in CLAIM_SCAN_COLUMNS)


def fields_by_cell(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {column: {"value": value} for column, value in values.items() if value not in (None, "")}


def cell_value(row: tuple[Any, ...], column: str) -> Any:
    index = column_index_from_string(column) - 1
    return row[index] if index < len(row) else None


def _is_repeated_header(value: str) -> bool:
    return "".join(value.split()).upper() in {"SKU", "子SKU", "SUBSKU"}


def main() -> None:
    parser = argparse.ArgumentParser(description="选品2历史来源只读解析/检查，不写库。")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    report = inspect_selection2_workbook(args.workbook) if args.inspect_only else parse_selection2_workbook(args.workbook)
    if not args.inspect_only and "rows" in report:
        report = {key: value for key, value in report.items() if key != "rows"}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
