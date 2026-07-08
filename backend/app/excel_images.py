from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from openpyxl.utils import column_index_from_string

from app.oss_storage import upload_product_image


UPLOADED_SOURCES_ROOT = Path(__file__).resolve().parents[1] / ".uploaded_sources"
PUBLIC_UPLOAD_PREFIX = "/uploaded-sources"


def images_by_row(worksheet: Any, column: str) -> dict[int, Any]:
    target_col = column_index_from_string(column)
    found: dict[int, Any] = {}
    for image in getattr(worksheet, "_images", []):
        marker = getattr(getattr(image, "anchor", None), "_from", None)
        if marker is None:
            continue
        row = marker.row + 1
        col = marker.col + 1
        if col == target_col and row not in found:
            found[row] = image
    return found


def save_product_image(image: Any | None, source_type: str, source_row: int) -> str | None:
    if image is None:
        return None
    data = image._data()
    if not data:
        return None
    digest = hashlib.sha1(data).hexdigest()[:16]
    ext = _safe_ext(getattr(image, "format", None))
    try:
        oss_url = upload_product_image(data, ext, source_type, source_row, digest)
    except Exception:
        # ponytail: keep imports usable when OSS credentials/policy are wrong; strict upload can be added when ops needs fail-fast.
        oss_url = None
    if oss_url:
        return oss_url
    source = _safe_segment(source_type)
    directory = UPLOADED_SOURCES_ROOT / "product-images" / source
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"row-{source_row}-{digest}.{ext}"
    target = directory / filename
    if not target.exists():
        target.write_bytes(data)
    return f"{PUBLIC_UPLOAD_PREFIX}/product-images/{source}/{filename}"


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or "unknown"


def _safe_ext(value: str | None) -> str:
    ext = (value or "png").lower().strip(".")
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else "png"
