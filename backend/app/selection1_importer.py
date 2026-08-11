from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.excel_images import images_by_row, save_product_image
from app.field_mapping import json_safe_value, normalize_header
from app.site_codes import normalize_site_code
from app.workbook_sheets import resolve_sheet_name


SOURCE_TYPE = "selection1_developer_claim_feedback"
SOURCE_LABEL = "选品1-开发部门认领反馈"
DEFAULT_SHEET = "开发0623期"

MAIN_COLUMNS = {
    "A": "site",
    "B": "developer_department",
    "C": "developer_name",
    "D": "category_level1",
    "E": "category_level2",
    "F": "keyword",
    "G": "image_url",
    "H": "main_sku_name",
    "I": "main_sku",
    "J": "sub_sku_name",
    "K": "sub_sku",
    "L": "product_type",
    "M": "reason",
}

MAIN_FIELD_ALIASES = {
    "site": ["站点", "国家"],
    "developer_department": ["开发部门", "部门"],
    "developer_name": ["开发员"],
    "category_level1": ["一级类目"],
    "category_level2": ["二级类目"],
    "keyword": ["关键词"],
    "image_url": ["产品图片"],
    "main_sku_name": ["主SKU名称"],
    "main_sku": ["主SKU"],
    "sub_sku_name": ["子SKU名称"],
    "sub_sku": ["子SKU", "子sku"],
    "product_type": ["产品类型", "引流or绑定or利润", "产品类型 / 引流or绑定or利润"],
    "reason": ["开品理由"],
}

MARKET_GROUPS = [
    ("最低价", "Z", "AA", "AB"),
    ("most_orders", "AC", "AD", "AE"),
    ("月销次高", "AF", "AG", "AH"),
    ("月销第三高", "AI", "AJ", "AK"),
    ("新晋", "AL", "AM", "AN"),
]

MARKET_GROUP_ALIASES = {
    "最低价": {
        "url": ["最低价链接", "平台综合推荐(前三页）最低价竞品链接1"],
        "price": ["售价1", "售价1(PHP）", "竞品单价 / （链接1） / (比索）"],
        "sales": ["月销1", "竞品子sku月销 / （链接1）"],
    },
    "most_orders": {
        "url": ["月销最高链接链接1", "月销最高链接", "most / orders链接", "most orders链接", "平台综合推荐（前三页）销量最多竞品链接2"],
        "price": ["售价2", "售价2(PHP）", "竞品单价 / （链接2） / (比索）"],
        "sales": ["月销2", "竞品子sku月销 / （链接2）"],
    },
    "月销次高": {
        "url": ["月销次高链接链接2", "月销次高链接"],
        "price": ["售价(PHP）"],
        "sales": ["月销"],
    },
    "月销第三高": {
        "url": ["月销第三高链接链接3", "月销第三高链接"],
        "price": ["售价(PHP）"],
        "sales": ["月销"],
    },
    "新晋": {
        "url": ["新晋链接", "平台综合推荐（前三页近3个月上架的）新晋竞品链接3"],
        "price": ["售价3", "售价3(PHP）", "竞品单价（链接3）（比索）"],
        "sales": ["月销3", "竞品子sku月销（链接3）"],
    },
}

PRICING_SNAPSHOT_COLUMNS = {
    "AO": "参考单销",
    "AP": "稳定期定价",
    "AQ": "一次毛利额THB",
    "AR": "一次毛利额RMB",
    "AS": "稳定期利润率",
    "AT": "预估单销",
    "AU": "推广期定价",
    "AV": "推广期利润率",
    "AW": "稳定期总成本",
    "AX": "推广期总成本",
}

PRICING_ALIASES = {
    "AO": ["参考单销"],
    "AP": ["稳定期定价", "稳定期定价 （PHP）", "稳定期定价 / （PHP）", "参考定价", "稳定期参考定价 / （VND）"],
    "AQ": ["一次毛利额 / （THB）", "一次毛利额 / （PHP）", "一次毛利额 / （VND）"],
    "AR": ["一次毛利额 / （人民币）"],
    "AS": ["稳定期利润率", "一次毛利率"],
    "AT": ["预估单销"],
    "AU": ["推广期定价"],
    "AV": ["推广期利润率"],
    "AW": ["稳定期总成本（PHP）（含头程+平台费+基础设施）", "稳定期总成本（THB）（含头程+平台费+基础设施）", "稳定期总成本（VND）（含头程+平台费+基础设施）"],
    "AX": ["推广期总成本（PHP）（含头程+平台费+基础设施）", "推广期总成本（THB）（含头程+平台费+基础设施）", "推广期总成本（VND）（含头程+平台费+基础设施）"],
}

TRACEABILITY_COLUMNS = ("CC", "CD", "CE", "CF", "CG", "CH")

SNAPSHOT_COLUMNS = tuple(get_column_letter(index) for index in range(1, column_index_from_string("BX") + 1)) + TRACEABILITY_COLUMNS
MAX_SOURCE_COLUMN = column_index_from_string("CH")

def import_selection1_workbook(db: Session, payload: schemas.Selection1ImportRequest) -> schemas.Selection1ImportResponse:
    source_path = resolve_source_file(payload.source_file)
    business_period = (payload.business_period or "").strip() or payload.source_sheet.strip()
    import_batch = models.ImportBatch(
        source_type=SOURCE_TYPE,
        source_file=source_path.name,
        source_sheet=payload.source_sheet,
        business_period=business_period,
        status="running",
    )
    db.add(import_batch)
    db.flush()

    workbook = load_workbook(source_path, read_only=False, data_only=True)
    source_sheet = resolve_sheet_name(workbook, payload.source_sheet)
    import_batch.source_sheet = source_sheet

    worksheet = workbook[source_sheet]
    try:
        worksheet.reset_dimensions()
    except AttributeError:
        pass
    source_max_column = max(worksheet.max_column or 0, MAX_SOURCE_COLUMN)
    header_rows, data_start_row = selection1_header_layout(worksheet, source_max_column)
    headers_by_column = source_headers_by_column(worksheet, source_max_column, header_rows=header_rows)
    product_images = images_by_row(worksheet, source_column_for_alias(headers_by_column, ["产品图片"], "G"))

    created_count = 0
    updated_count = 0
    skipped_count = 0
    market_research_count = 0
    prefill_claim_count = 0
    task_count = 0
    processed_count = 0

    for source_row, row in enumerate(
        worksheet.iter_rows(min_row=data_start_row, max_col=source_max_column, values_only=True),
        start=data_start_row,
    ):
        if payload.max_rows is not None and processed_count >= payload.max_rows:
            break
        parsed = parse_selection1_row(row, headers_by_column)
        if parsed is None:
            skipped_count += 1
            continue
        attach_product_image(parsed, product_images.get(source_row), source_row)
        processed_count += 1

        opportunity, created = upsert_opportunity(db, parsed, source_path.name, source_sheet, source_row, business_period, import_batch.id)
        created_count += int(created)
        updated_count += int(not created)

        market_research_count += replace_market_research(db, opportunity.id, parsed)
        if ensure_import_claim_task(db, opportunity, parsed):
            task_count += 1

    services.audit(
        db,
        "selection1.imported",
        "new_product_opportunity",
        None,
        {
            "source_file": source_path.name,
            "source_sheet": source_sheet,
            "business_period": business_period,
            "imported_count": created_count + updated_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
        },
    )
    import_batch.created_count = created_count
    import_batch.updated_count = updated_count
    import_batch.skipped_count = skipped_count
    import_batch.status = "completed"

    return schemas.Selection1ImportResponse(
        import_batch_id=import_batch.id,
        source_file=source_path.name,
        source_sheet=source_sheet,
        business_period=business_period,
        imported_count=created_count + updated_count,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        market_research_count=market_research_count,
        prefill_claim_count=prefill_claim_count,
        task_count=task_count,
    )


def attach_product_image(parsed: dict[str, Any], image: Any | None, source_row: int) -> None:
    if parsed["main"].get("image_url"):
        return
    image_url = save_product_image(image, SOURCE_TYPE, source_row)
    if image_url:
        parsed["main"]["image_url"] = image_url
        parsed["snapshot"]["extracted_image_url"] = image_url


def resolve_source_file(source_file: str | None) -> Path:
    if source_file:
        path = Path(source_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path

    search_roots = [Path.cwd(), Path.cwd().parent]
    for root in search_roots:
        matches = sorted(root.glob("选品1：海外仓开发部门开发新品认领-反馈*.xlsx"))
        if matches:
            return matches[0]
    raise FileNotFoundError("selection1 source workbook not found")


def parse_selection1_row(row: tuple[Any, ...], headers_by_column: dict[str, list[str]] | None = None) -> dict[str, Any] | None:
    raw_values = {get_column_letter(index): json_safe_value(clean_cell(value)) for index, value in enumerate(row, start=1)}
    values = {column: json_safe_value(clean_cell(cell_value(row, column))) for column in SNAPSHOT_COLUMNS}
    headers = headers_by_column or {}
    main = parse_main_fields(raw_values, values, headers)
    main_sku = text_value(main["main_sku"])
    sub_sku = text_value(main["sub_sku"])
    if not main_sku or not sub_sku:
        return None
    if is_summary_row(values, main) or is_repeated_header_row(values, main):
        return None

    site = text_value(main["site"])
    pricing_snapshot = {
        label: source_value(raw_values, headers_by_column or {}, PRICING_ALIASES.get(column, [label]), column)
        for column, label in PRICING_SNAPSHOT_COLUMNS.items()
        if source_value(raw_values, headers_by_column or {}, PRICING_ALIASES.get(column, [label]), column) not in (None, "")
    }
    parsed = {
        "main": main,
        "country": derive_country(site),
        "market_items": parse_market_items(values, raw_values, headers),
        "reference_daily_sales": number_value(source_value(raw_values, headers, PRICING_ALIASES["AO"], "AO")),
        "reference_price": number_value(source_value(raw_values, headers, PRICING_ALIASES["AP"], "AP")),
        "pricing_snapshot": pricing_snapshot,
        "snapshot": {
            "source_type": SOURCE_TYPE,
            "allowed_columns": list(raw_values),
            "cells": values,
            "headers_by_column": headers_by_column or {},
            "fields_by_column": fields_by_column(raw_values),
            "fields_by_header": fields_by_header(headers_by_column or {}, raw_values),
            "pricing_snapshot": pricing_snapshot,
        },
    }
    return parsed



def parse_main_fields(raw_values: dict[str, Any], values: dict[str, Any], headers_by_column: dict[str, list[str]]) -> dict[str, Any]:
    main = {
        field: source_value(raw_values, headers_by_column, MAIN_FIELD_ALIASES[field], column, values)
        for column, field in MAIN_COLUMNS.items()
    }
    main["category_level2"] = source_value(raw_values, headers_by_column, MAIN_FIELD_ALIASES["category_level2"], "", values)
    return main

def upsert_opportunity(
    db: Session,
    parsed: dict[str, Any],
    source_file: str,
    source_sheet: str,
    source_row: int,
    business_period: str,
    import_batch_id: str | None = None,
) -> tuple[models.NewProductOpportunity, bool]:
    normalized_site = normalize_site_code(parsed["main"].get("site") or parsed["country"]) or ""
    candidates = db.scalars(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == SOURCE_TYPE,
            models.NewProductOpportunity.batch == business_period,
            models.NewProductOpportunity.main_sku == parsed["main"]["main_sku"],
            models.NewProductOpportunity.sub_sku == parsed["main"]["sub_sku"],
        )
    )
    existing = next((item for item in candidates if (normalize_site_code(item.site or item.country) or "") == normalized_site), None)
    opportunity_data = {
        **parsed["main"],
        "source_type": SOURCE_TYPE,
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "import_batch_id": import_batch_id,
        "batch": business_period,
        "country": parsed["country"],
        "snapshot": parsed["snapshot"],
    }
    if existing:
        for field, value in opportunity_data.items():
            if field != "current_status":
                setattr(existing, field, value)
        add_source_snapshot(db, existing, import_batch_id)
        return existing, False

    opportunity = models.NewProductOpportunity(**opportunity_data)
    db.add(opportunity)
    db.flush()
    add_source_snapshot(db, opportunity, import_batch_id)
    services.audit(
        db,
        "opportunity.created",
        "new_product_opportunity",
        opportunity.id,
        {"main_sku": opportunity.main_sku, "sub_sku": opportunity.sub_sku, "source_type": SOURCE_TYPE},
    )
    return opportunity, True


def add_source_snapshot(db: Session, opportunity: models.NewProductOpportunity, import_batch_id: str | None = None) -> None:
    db.add(
        models.SourceRecordSnapshot(
            import_batch_id=import_batch_id,
            opportunity_id=opportunity.id,
            source_file=opportunity.source_file,
            source_sheet=opportunity.source_sheet,
            source_row=opportunity.source_row,
            column_range="A:BX,CC:CH",
            payload=opportunity.snapshot,
        )
    )


def selection1_header_layout(worksheet: Any, max_col: int) -> tuple[tuple[int, ...], int]:
    first_row_headers = source_headers_by_column(worksheet, max_col, header_rows=(1,))
    second_row_headers = source_headers_by_column(worksheet, max_col, header_rows=(2,))
    if has_required_sku_headers(second_row_headers):
        return (1, 2), 3
    if has_required_sku_headers(first_row_headers):
        return (1,), 2
    return (1, 2), 3


def has_required_sku_headers(headers_by_column: dict[str, list[str]]) -> bool:
    return all(
        source_column_for_alias(headers_by_column, MAIN_FIELD_ALIASES[field], "")
        for field in ("main_sku", "sub_sku")
    )


def source_headers_by_column(
    worksheet: Any,
    max_col: int,
    header_rows: tuple[int, ...] = (1, 2),
) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for index in range(1, max_col + 1):
        column = get_column_letter(index)
        values = [text_value(worksheet.cell(row=row, column=index).value) for row in header_rows]
        candidates = [value for value in values if value]
        if len(values) == 2 and values[0] and values[1]:
            candidates.append(f"{values[0]} / {values[1]}")
        if candidates:
            headers[column] = candidates
    return headers


def fields_by_header(headers_by_column: dict[str, list[str]], values: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for column, headers in headers_by_column.items():
        value = values.get(column)
        if value is None:
            continue
        for header in headers:
            key = normalize_header(header)
            if key and key not in fields:
                fields[key] = value
    return fields


def fields_by_column(values: dict[str, Any]) -> dict[str, Any]:
    return {column: value for column, value in values.items() if value not in (None, "")}


def replace_market_research(db: Session, opportunity_id: str, parsed: dict[str, Any]) -> int:
    db.execute(delete(models.MarketResearchItem).where(models.MarketResearchItem.opportunity_id == opportunity_id))
    count = 0
    for item in parsed["market_items"]:
        db.add(
            models.MarketResearchItem(
                opportunity_id=opportunity_id,
                research_type=item["research_type"],
                competitor_url=item["competitor_url"],
                competitor_price=item["competitor_price"],
                competitor_monthly_sales=item["competitor_monthly_sales"],
                reference_daily_sales=parsed["reference_daily_sales"],
                reference_price=parsed["reference_price"],
            )
        )
        count += 1
    return count


def ensure_import_claim_task(db: Session, opportunity: models.NewProductOpportunity, parsed: dict[str, Any]) -> bool:
    # Supervisor assignment is the only first-version entry to operator tasks.
    return False


def parse_market_items(values: dict[str, Any], raw_values: dict[str, Any], headers_by_column: dict[str, list[str]]) -> list[dict[str, Any]]:
    items = []
    for research_type, url_column, price_column, sales_column in MARKET_GROUPS:
        aliases = MARKET_GROUP_ALIASES[research_type]
        competitor_url = text_value(source_value(raw_values, headers_by_column, aliases["url"], url_column, values))
        competitor_price = number_value(source_value(raw_values, headers_by_column, aliases["price"], price_column, values))
        if not competitor_url and competitor_price is None:
            continue
        items.append(
            {
                "research_type": research_type,
                "competitor_url": competitor_url,
                "competitor_price": competitor_price,
                "competitor_monthly_sales": number_value(source_value(raw_values, headers_by_column, aliases["sales"], sales_column, values)),
            }
        )
    return items


def source_column_for_alias(headers_by_column: dict[str, list[str]], aliases: list[str], fallback_column: str) -> str:
    alias_keys = {normalize_header(alias) for alias in aliases}
    for column, headers in headers_by_column.items():
        if any(normalize_header(header) in alias_keys for header in headers):
            return column
    return fallback_column


def source_value(
    raw_values: dict[str, Any],
    headers_by_column: dict[str, list[str]],
    aliases: list[str],
    fallback_column: str,
    fallback_values: dict[str, Any] | None = None,
) -> Any:
    alias_keys = {normalize_header(alias) for alias in aliases}
    for column, headers in headers_by_column.items():
        value = raw_values.get(column)
        if value in (None, ""):
            continue
        if any(normalize_header(header) in alias_keys for header in headers):
            return value
    return (fallback_values or raw_values).get(fallback_column)


def is_summary_row(values: dict[str, Any], main: dict[str, Any] | None = None) -> bool:
    summary_labels = {"小计", "合计", "总计", "汇总"}
    identity_values = [values.get(column) for column in ("A", "G", "H", "I", "J")]
    if main:
        identity_values += [main.get(field) for field in ("site", "main_sku_name", "main_sku", "sub_sku_name", "sub_sku")]
    return any((text_value(value) or "").strip(" ：:") in summary_labels for value in identity_values)


def is_repeated_header_row(values: dict[str, Any], main: dict[str, Any] | None = None) -> bool:
    main_sku = "".join((text_value((main or {}).get("main_sku") or values.get("H")) or "").split()).upper()
    sub_sku = "".join((text_value((main or {}).get("sub_sku") or values.get("J")) or "").split()).upper()
    site = text_value((main or {}).get("site") or values.get("A"))
    category = text_value((main or {}).get("category_level1") or values.get("D"))
    return main_sku in {"主SKU", "MAINSKU"} or sub_sku in {"子SKU", "SUBSKU"} or (
        site in {"站点", "国家"} and category == "一级类目"
    )


def derive_country(site: str | None) -> str | None:
    return normalize_site_code(site)


def clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def cell_value(row: tuple[Any, ...], column: str) -> Any:
    index = column_index_from_string(column) - 1
    if index >= len(row):
        return None
    return row[index]


def text_value(value: Any) -> str | None:
    cleaned = clean_cell(value)
    if cleaned is None:
        return None
    return str(cleaned).strip()


def number_value(value: Any) -> float | None:
    cleaned = clean_cell(value)
    if cleaned is None:
        return None
    if isinstance(cleaned, int | float):
        return float(cleaned)
    text = str(cleaned).strip().replace(",", "")
    if not text or text in {"-", "/"}:
        return None
    number_text = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    if number_text in {"", ".", "-", "-."}:
        return None
    try:
        return float(number_text)
    except ValueError:
        return None
