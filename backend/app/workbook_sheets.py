from __future__ import annotations

from typing import Any


def resolve_sheet_name(workbook: Any, requested: str) -> str:
    if requested in workbook.sheetnames:
        return requested
    normalized = _sheet_key(requested)
    for sheet_name in workbook.sheetnames:
        if _sheet_key(sheet_name) == normalized:
            return sheet_name
    available = ", ".join(workbook.sheetnames)
    raise ValueError(f"sheet not found: {requested}; available sheets: {available}")


def _sheet_key(value: str) -> str:
    return "".join(str(value).split()).casefold()
