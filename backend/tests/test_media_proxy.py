import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import media  # noqa: E402


client = TestClient(app)

PRODUCT_IMAGE_URL = "https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/product-images/history_selection1/row-3-abc123.png"


def test_media_proxy_returns_image_bytes_with_public_cache(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_read(url: str, allowed_prefixes=("product-images/", "claim-evidence/"), process=None) -> tuple[bytes, str]:
        captured["url"] = url
        captured["allowed_prefixes"] = allowed_prefixes
        return b"image-bytes", "image/png"

    monkeypatch.setattr(media, "read_oss_object_by_public_url", fake_read)

    response = client.get("/media/oss-image", params={"src": PRODUCT_IMAGE_URL})

    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=604800"
    assert captured["url"] == PRODUCT_IMAGE_URL
    # 只放行商品图前缀，认领证据图不走本代理。
    assert captured["allowed_prefixes"] == ("product-images/",)


def test_media_proxy_rejects_illegal_src_with_400(monkeypatch) -> None:
    def fake_read(url: str, allowed_prefixes=None, process=None) -> tuple[bytes, str]:
        raise ValueError("unsupported OSS URL")

    monkeypatch.setattr(media, "read_oss_object_by_public_url", fake_read)

    response = client.get("/media/oss-image", params={"src": "https://evil.example.com/product-images/x.png"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported OSS URL"


def test_media_proxy_returns_503_when_oss_not_configured(monkeypatch) -> None:
    def fake_read(url: str, allowed_prefixes=None, process=None) -> tuple[bytes, str]:
        raise RuntimeError("OSS is not configured")

    monkeypatch.setattr(media, "read_oss_object_by_public_url", fake_read)

    response = client.get("/media/oss-image", params={"src": PRODUCT_IMAGE_URL})

    assert response.status_code == 503
    assert response.json()["detail"] == "OSS is not configured"


def test_media_proxy_maps_upstream_failure_to_502(monkeypatch) -> None:
    def fake_read(url: str, allowed_prefixes=None, process=None) -> tuple[bytes, str]:
        raise OSError("network down")

    monkeypatch.setattr(media, "read_oss_object_by_public_url", fake_read)

    response = client.get("/media/oss-image", params={"src": PRODUCT_IMAGE_URL})

    assert response.status_code == 502
    assert response.json()["detail"] == "failed to read OSS image"
