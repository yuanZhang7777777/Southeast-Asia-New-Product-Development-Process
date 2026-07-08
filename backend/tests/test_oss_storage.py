import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import excel_images, oss_storage  # noqa: E402


def test_upload_product_image_returns_public_url(monkeypatch) -> None:
    calls = {}

    class FakeBucket:
        def put_object(self, key: str, data: bytes, headers: dict[str, str]):
            calls["key"] = key
            calls["data"] = data
            calls["headers"] = headers

    monkeypatch.setattr(oss_storage, "_bucket", lambda config: FakeBucket())
    monkeypatch.setenv("OSS_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("OSS_ENDPOINT", "oss-cn-shanghai.aliyuncs.com")
    monkeypatch.setenv("OSS_BUCKET", "hz-sea-np-flow-prod")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "test-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.delenv("OSS_PUBLIC_BASE_URL", raising=False)

    url = oss_storage.upload_product_image(b"image-bytes", "png", "selection1", 3, "abcdef")

    assert url == "https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/product-images/selection1/row-3-abcdef.png"
    assert calls == {
        "key": "product-images/selection1/row-3-abcdef.png",
        "data": b"image-bytes",
        "headers": {"Content-Type": "image/png"},
    }


def test_upload_product_image_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OSS_UPLOAD_ENABLED", "false")

    assert oss_storage.upload_product_image(b"image-bytes", "png", "selection1", 3, "abcdef") is None


def test_save_product_image_falls_back_to_local_when_oss_upload_fails(monkeypatch, tmp_path: Path) -> None:
    class FakeImage:
        format = "png"

        def _data(self) -> bytes:
            return b"image-bytes"

    def boom(*_args, **_kwargs):
        raise RuntimeError("oss denied")

    monkeypatch.setattr(excel_images, "UPLOADED_SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(excel_images, "upload_product_image", boom)

    url = excel_images.save_product_image(FakeImage(), "selection1", 3)

    assert url.startswith("/uploaded-sources/product-images/")
    assert (tmp_path / url.removeprefix("/uploaded-sources/")).exists()
