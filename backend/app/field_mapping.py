from typing import Any


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).replace("\xa0", " ").split())


def empty_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def mapped_text(values: dict[str, Any], column: str | None = None) -> str | None:
    value = empty_value(values.get(column) if column else None)
    return str(value) if value is not None else None


def number_value(value: Any) -> float | None:
    value = empty_value(value)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).replace(",", "")
    number_text = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    if number_text in {"", ".", "-", "-."}:
        return None
    try:
        return float(number_text)
    except ValueError:
        return None


def text_value(value: Any) -> str | None:
    value = empty_value(value)
    return str(value) if value is not None else None
