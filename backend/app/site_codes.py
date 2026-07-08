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


def normalize_site_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    compact = "".join(text.split())
    upper = compact.upper()
    return SITE_ALIASES.get(compact) or SITE_ALIASES.get(upper) or upper
