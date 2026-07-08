from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.excel_images import images_by_row, save_product_image
from app.field_mapping import normalize_header
from app.site_codes import normalize_site_code


SOURCE_TYPE = "selection1_developer_claim_feedback"
SOURCE_LABEL = "选品1-开发部门认领反馈"
DEFAULT_SHEET = "开发0623期"

MAIN_COLUMNS = {
    "A": "site",
    "B": "developer_department",
    "C": "developer_name",
    "D": "category_level1",
    "E": "keyword",
    "F": "image_url",
    "G": "main_sku_name",
    "H": "main_sku",
    "I": "sub_sku_name",
    "J": "sub_sku",
    "K": "product_type",
    "L": "reason",
}

MARKET_GROUPS = [
    ("最低价", "Z", "AA", "AB"),
    ("most_orders", "AC", "AD", "AE"),
    ("月销次高", "AF", "AG", "AH"),
    ("月销第三高", "AI", "AJ", "AK"),
    ("新晋", "AL", "AM", "AN"),
]

PRICING_SNAPSHOT_COLUMNS = {
    "AO": "参考单销",
    "AP": "参考定价",
    "AQ": "一次毛利额THB",
    "AR": "一次毛利额RMB",
    "AS": "一次毛利率",
    "AT": "预估单销",
    "AU": "推广期定价",
    "AV": "推广期利润率",
}

CLAIM_COLUMNS = {
    "CC": "reject_reason",
    "CD": "salesperson_name",
    "CE": "claim_result",
    "CF": "claim_daily_sales",
    "CG": "feedback_summary",
    "CH": "note",
}

SNAPSHOT_COLUMNS = tuple(
    list(MAIN_COLUMNS)
    + [column for group in MARKET_GROUPS for column in group[1:]]
    + list(PRICING_SNAPSHOT_COLUMNS)
    + list(CLAIM_COLUMNS)
)
MAX_SOURCE_COLUMN = column_index_from_string("CH")

def import_selection1_workbook(db: Session, payload: schemas.Selection1ImportRequest) -> schemas.Selection1ImportResponse:
    source_path = resolve_source_file(payload.source_file)
    import_batch = models.ImportBatch(
        source_type=SOURCE_TYPE,
        source_file=source_path.name,
        source_sheet=payload.source_sheet,
        status="running",
    )
    db.add(import_batch)
    db.flush()

    workbook = load_workbook(source_path, read_only=False, data_only=True)
    if payload.source_sheet not in workbook.sheetnames:
        available = ", ".join(workbook.sheetnames)
        raise ValueError(f"sheet not found: {payload.source_sheet}; available sheets: {available}")

    worksheet = workbook[payload.source_sheet]
    try:
        worksheet.reset_dimensions()
    except AttributeError:
        pass
    source_max_column = max(worksheet.max_column or 0, MAX_SOURCE_COLUMN)
    product_images = images_by_row(worksheet, "F")
    headers_by_column = source_headers_by_column(worksheet, source_max_column)

    created_count = 0
    updated_count = 0
    skipped_count = 0
    market_research_count = 0
    prefill_claim_count = 0
    task_count = 0
    processed_count = 0

    for source_row, row in enumerate(worksheet.iter_rows(min_row=3, max_col=source_max_column, values_only=True), start=3):
        if payload.max_rows is not None and processed_count >= payload.max_rows:
            break
        parsed = parse_selection1_row(row, headers_by_column)
        if parsed is None:
            skipped_count += 1
            continue
        attach_product_image(parsed, product_images.get(source_row), source_row)
        processed_count += 1

        opportunity, created = upsert_opportunity(db, parsed, source_path.name, payload.source_sheet, source_row, import_batch.id)
        created_count += int(created)
        updated_count += int(not created)

        market_research_count += replace_market_research(db, opportunity.id, parsed)
        if replace_source_claim_prefill(db, opportunity.id, parsed):
            prefill_claim_count += 1
        if ensure_import_claim_task(db, opportunity, parsed):
            task_count += 1

    services.audit(
        db,
        "selection1.imported",
        "new_product_opportunity",
        None,
        {
            "source_file": source_path.name,
            "source_sheet": payload.source_sheet,
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
        source_sheet=payload.source_sheet,
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
    raw_values = {get_column_letter(index): clean_cell(value) for index, value in enumerate(row, start=1)}
    values = {column: clean_cell(cell_value(row, column)) for column in SNAPSHOT_COLUMNS}
    main_sku = text_value(values["H"])
    sub_sku = text_value(values["J"])
    if not main_sku or not sub_sku:
        return None
    if is_summary_row(values) or is_repeated_header_row(values):
        return None

    site = text_value(values["A"])
    pricing_snapshot = {label: values[column] for column, label in PRICING_SNAPSHOT_COLUMNS.items() if values[column] not in (None, "")}
    feedback_parts = [text_value(values["CG"]), text_value(values["CH"])]
    claim_prefill = {
        "reject_reason": text_value(values["CC"]),
        "salesperson_name": text_value(values["CD"]),
        "claim_result": normalize_claim_result(values["CE"]),
        "claim_daily_sales": number_value(values["CF"]),
        "feedback_summary": "\n".join(part for part in feedback_parts if part),
    }
    parsed = {
        "main": {field: values[column] for column, field in MAIN_COLUMNS.items()},
        "country": derive_country(site),
        "market_items": parse_market_items(values),
        "reference_daily_sales": number_value(values["AO"]),
        "reference_price": number_value(values["AP"]),
        "pricing_snapshot": pricing_snapshot,
        "claim_prefill": claim_prefill,
        "snapshot": {
            "source_type": SOURCE_TYPE,
            "allowed_columns": list(raw_values),
            "cells": values,
            "fields_by_column": fields_by_column(raw_values),
            "fields_by_header": fields_by_header(headers_by_column or {}, raw_values),
            "pricing_snapshot": pricing_snapshot,
            "claim_prefill": claim_prefill,
        },
    }
    return parsed


def upsert_opportunity(
    db: Session, parsed: dict[str, Any], source_file: str, source_sheet: str, source_row: int, import_batch_id: str | None = None
) -> tuple[models.NewProductOpportunity, bool]:
    existing = db.scalar(
        select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == SOURCE_TYPE,
            models.NewProductOpportunity.source_file == source_file,
            models.NewProductOpportunity.source_sheet == source_sheet,
            models.NewProductOpportunity.source_row == source_row,
        )
    )
    opportunity_data = {
        **parsed["main"],
        "source_type": SOURCE_TYPE,
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
        "import_batch_id": import_batch_id,
        "batch": source_sheet,
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
            column_range="A:L,Z:AN,AO:AV,CC:CH",
            payload=opportunity.snapshot,
        )
    )


def source_headers_by_column(worksheet: Any, max_col: int) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for index in range(1, max_col + 1):
        column = get_column_letter(index)
        top = text_value(worksheet.cell(row=1, column=index).value)
        sub = text_value(worksheet.cell(row=2, column=index).value)
        candidates = [value for value in (top, sub, f"{top} / {sub}" if top and sub else None) if value]
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


def replace_source_claim_prefill(db: Session, opportunity_id: str, parsed: dict[str, Any]) -> bool:
    claim = parsed["claim_prefill"]
    db.execute(
        delete(models.SalesClaimForecast).where(
            models.SalesClaimForecast.opportunity_id == opportunity_id,
            models.SalesClaimForecast.source_column == "CC:CH",
        )
    )
    if not any(claim.values()):
        return False
    db.add(
        models.SalesClaimForecast(
            opportunity_id=opportunity_id,
            platform="Shopee",
            salesperson_name=claim["salesperson_name"],
            claim_result=claim["claim_result"],
            claim_daily_sales=claim["claim_daily_sales"],
            reject_reason=claim["reject_reason"],
            feedback_summary=claim["feedback_summary"],
            source_column="CC:CH",
        )
    )
    return True


def ensure_import_claim_task(db: Session, opportunity: models.NewProductOpportunity, parsed: dict[str, Any]) -> bool:
    # Selection1 source claim columns are retained as reference/prefill only.
    # Supervisor assignment is the only first-version entry to operator tasks.
    return False


def parse_market_items(values: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for research_type, url_column, price_column, sales_column in MARKET_GROUPS:
        competitor_url = text_value(values[url_column])
        competitor_price = number_value(values[price_column])
        if not competitor_url and competitor_price is None:
            continue
        items.append(
            {
                "research_type": research_type,
                "competitor_url": competitor_url,
                "competitor_price": competitor_price,
                "competitor_monthly_sales": number_value(values[sales_column]),
            }
        )
    return items


def is_summary_row(values: dict[str, Any]) -> bool:
    joined = " ".join(str(value) for value in values.values() if value is not None)
    return "小计" in joined or "合计" in joined


def is_repeated_header_row(values: dict[str, Any]) -> bool:
    main_sku = "".join((text_value(values.get("H")) or "").split()).upper()
    sub_sku = "".join((text_value(values.get("J")) or "").split()).upper()
    site = text_value(values.get("A"))
    category = text_value(values.get("D"))
    return main_sku in {"主SKU", "MAINSKU"} or sub_sku in {"子SKU", "SUBSKU"} or (
        site in {"站点", "国家"} and category == "一级类目"
    )


def derive_country(site: str | None) -> str | None:
    return normalize_site_code(site)


def normalize_claim_result(value: Any) -> str | None:
    text = text_value(value)
    if text in {"是", "认领", "claim", "CLAIM", "yes", "YES"}:
        return "claim"
    if text in {"否", "不认领", "reject", "REJECT", "no", "NO"}:
        return "reject"
    return None


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
