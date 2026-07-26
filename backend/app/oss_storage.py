from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_CREDENTIALS_FILE = Path.home() / ".codex" / "secrets" / "Hengzhe-New-Product-Workflow" / "oss.credentials.json"


@dataclass(frozen=True)
class OssConfig:
    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    public_base_url: str


def upload_product_image(data: bytes, ext: str, source_type: str, source_row: int, digest: str) -> str | None:
    config = _config()
    if config is None:
        return None
    object_key = f"product-images/{_safe_segment(source_type)}/row-{source_row}-{_safe_segment(digest)}.{_safe_ext(ext)}"
    _bucket(config).put_object(object_key, data, headers={"Content-Type": _content_type(ext)})
    return f"{config.public_base_url.rstrip('/')}/{object_key}"


def upload_claim_evidence_image(data: bytes, ext: str, opportunity_id: str, digest: str) -> str | None:
    config = _config()
    if config is None:
        return None
    object_key = f"claim-evidence/{_safe_segment(opportunity_id)}/{_safe_segment(digest)}.{_safe_ext(ext)}"
    _bucket(config).put_object(object_key, data, headers={"Content-Type": _content_type(ext)})
    return f"{config.public_base_url.rstrip('/')}/{object_key}"


def read_oss_object_by_public_url(
    url: str,
    allowed_prefixes: tuple[str, ...] = ("product-images/", "claim-evidence/"),
    process: str | None = None,
) -> tuple[bytes, str]:
    config = _config()
    if config is None:
        raise RuntimeError("OSS is not configured")
    parsed = urlparse(url)
    base = urlparse(config.public_base_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc:
        raise ValueError("unsupported OSS URL")
    object_key = unquote(parsed.path.lstrip("/"))
    if not object_key or not any(object_key.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError("unsupported OSS object")
    result = _bucket(config).get_object(object_key, process=process)
    content_type = result.headers.get("Content-Type") or _content_type(Path(object_key).suffix)
    return result.read(), content_type


def _config() -> OssConfig | None:
    if os.getenv("OSS_UPLOAD_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    secret = _read_secret_file(Path(os.getenv("OSS_CREDENTIALS_FILE", DEFAULT_CREDENTIALS_FILE)))
    endpoint = os.getenv("OSS_ENDPOINT") or secret.get("endpoint", "")
    bucket = os.getenv("OSS_BUCKET") or secret.get("bucket", "")
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID") or secret.get("access_key_id", "")
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET") or secret.get("access_key_secret", "")
    if not endpoint or not bucket or not access_key_id or not access_key_secret:
        return None
    public_base_url = os.getenv("OSS_PUBLIC_BASE_URL") or f"https://{bucket}.{endpoint}"
    return OssConfig(endpoint, bucket, access_key_id, access_key_secret, public_base_url)


def _bucket(config: OssConfig):
    import oss2

    return oss2.Bucket(oss2.Auth(config.access_key_id, config.access_key_secret), f"https://{config.endpoint}", config.bucket)


def _read_secret_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or "unknown"


def _safe_ext(value: str) -> str:
    ext = value.lower().strip(".")
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else "png"


def _content_type(ext: str) -> str:
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(_safe_ext(ext), "application/octet-stream")
