from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

DEFAULT_COMPANY_CATEGORY_SHEET = "公司类目"
_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def import_company_categories(
    db: Session,
    source_file: str | Path,
    source_sheet: str = DEFAULT_COMPANY_CATEGORY_SHEET,
) -> dict[str, int]:
    path = Path(source_file)
    rows = _xlsx_rows(path, source_sheet)
    header = _find_header(rows)
    level1_index = header[0] if header else 0
    level2_index = header[1] if header else 1
    start_row = header[2] + 1 if header else 0

    created_count = 0
    updated_count = 0
    skipped_count = 0
    seen: set[tuple[str, str]] = set()
    for row_number, values in rows[start_row:]:
        level1 = _text(values[level1_index] if level1_index < len(values) else None)
        level2 = _text(values[level2_index] if level2_index < len(values) else None) or ""
        if not level1:
            skipped_count += 1
            continue
        key = (level1, level2)
        if key in seen:
            skipped_count += 1
            continue
        seen.add(key)
        item = db.scalar(
            select(models.CompanyCategory).where(
                models.CompanyCategory.level1 == level1,
                models.CompanyCategory.level2 == level2,
            )
        )
        if item is None:
            item = models.CompanyCategory(level1=level1, level2=level2)
            db.add(item)
            created_count += 1
        else:
            updated_count += 1
        item.enabled = True
        item.source_file = str(path)
        item.source_sheet = source_sheet
        item.source_row = row_number
    return {"created_count": created_count, "updated_count": updated_count, "skipped_count": skipped_count}


def _find_header(rows: list[tuple[int, list[str | None]]]) -> tuple[int, int, int] | None:
    for row_index, (_row_number, values) in enumerate(rows[:20]):
        normalized = [_text(value) or "" for value in values]
        level1_indexes = [idx for idx, value in enumerate(normalized) if "一级" in value and "类目" in value]
        level2_indexes = [idx for idx, value in enumerate(normalized) if "二级" in value and "类目" in value]
        if level1_indexes and level2_indexes:
            return level1_indexes[0], level2_indexes[0], row_index
    return None


def _xlsx_rows(path: Path, sheet_name: str) -> list[tuple[int, list[str | None]]]:
    with ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_path = _sheet_path(archive, sheet_name)
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[tuple[int, list[str | None]]] = []
        for row in root.findall(".//main:sheetData/main:row", _NS):
            row_number = int(row.attrib.get("r", len(rows) + 1))
            values: dict[int, str | None] = {}
            for cell in row.findall("main:c", _NS):
                column_index = _column_index(cell.attrib.get("r", "A"))
                values[column_index] = _cell_value(cell, shared_strings)
            if values:
                width = max(values) + 1
                rows.append((row_number, [values.get(index) for index in range(width)]))
        return rows


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.findall(".//main:t", _NS)) for item in root.findall("main:si", _NS)]


def _sheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_by_id = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("pkg_rel:Relationship", _NS)}
    for sheet in workbook.findall("main:sheets/main:sheet", _NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        target = rel_by_id[sheet.attrib[f"{{{_NS['rel']}}}id"]]
        target = target.lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError(f"sheet not found: {sheet_name}")


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _text("".join(text.text or "" for text in cell.findall(".//main:t", _NS)))
    value = cell.find("main:v", _NS)
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        index = int(value.text)
        return shared_strings[index] if index < len(shared_strings) else None
    return _text(value.text)


def _column_index(ref: str) -> int:
    letters = "".join(char for char in ref if char.isalpha()).upper() or "A"
    index = 0
    for char in letters:
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
