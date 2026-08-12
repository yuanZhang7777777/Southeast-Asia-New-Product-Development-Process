from __future__ import annotations

from typing import Any


SITE_ALIASES = {
    "菲律宾": "PH",
    "菲": "PH",
    "PH": "PH",
    "泰国": "TH",
    "泰": "TH",
    "TH": "TH",
    "越南": "VN",
    "越": "VN",
    "VN": "VN",
    "马来西亚": "MY",
    "马来": "MY",
    "MY": "MY",
    "新加坡": "SG",
    "SG": "SG",
    "印度尼西亚": "ID",
    "印尼": "ID",
    "ID": "ID",
}

SITE_LABELS = {
    "PH": "菲律宾",
    "TH": "泰国",
    "VN": "越南",
    "MY": "马来西亚",
    "SG": "新加坡",
    "ID": "印度尼西亚",
}


def normalize_site_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    compact = "".join(text.split())
    upper = compact.upper()
    return SITE_ALIASES.get(compact) or SITE_ALIASES.get(upper) or upper


def site_display_label(value: Any) -> str | None:
    code = normalize_site_code(value)
    if not code:
        return None
    return SITE_LABELS.get(code, code)


def site_match_values(value: Any) -> set[str]:
    code = normalize_site_code(value)
    if not code:
        return set()
    values = {code}
    label = SITE_LABELS.get(code)
    if label:
        values.add(label)
    values.update(alias for alias, alias_code in SITE_ALIASES.items() if alias_code == code)
    return values
