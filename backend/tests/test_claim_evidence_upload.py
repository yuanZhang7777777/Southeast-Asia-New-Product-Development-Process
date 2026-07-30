import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from starlette.datastructures import Headers, UploadFile  # noqa: E402

from app import models, schemas  # noqa: E402
from app.auth import AuthContext  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import claims  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_claim_evidence_upload_falls_back_to_local_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OSS_UPLOAD_ENABLED", "false")
    monkeypatch.setattr(claims, "UPLOADED_SOURCES_ROOT", tmp_path)

    response = client.post(
        "/claims/evidence-images",
        data={"opportunity_id": "OPP-1"},
        files={"file": ("proof.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"].startswith("/uploaded-sources/claim-evidence/OPP-1/")
    assert payload["name"] == "proof.png"
    assert payload["type"] == "image/png"
    assert payload["size"] == len(b"image-bytes")
    assert (tmp_path / payload["url"].removeprefix("/uploaded-sources/")).exists()


def test_manager_correction_can_upload_secondary_research_image(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OSS_UPLOAD_ENABLED", "false")
    monkeypatch.setattr(claims, "UPLOADED_SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(
        claims.services,
        "can_upload_claim_evidence",
        lambda *_: (_ for _ in ()).throw(AssertionError("manager upload must not use operator ownership check")),
    )
    manager = AuthContext(
        user=models.User(id="manager-1", name="主管A", enabled=True),
        roles=[schemas.AuthRoleRead(role="manager", name="主管A")],
    )
    upload = UploadFile(
        file=BytesIO(b"image-bytes"),
        filename="correction.png",
        headers=Headers({"content-type": "image/png"}),
    )
    with SessionLocal() as db:
        result = asyncio.run(claims.upload_evidence_image("OPP-1", upload, manager, db))

    assert result["name"] == "correction.png"
    assert str(result["url"]).startswith("/uploaded-sources/claim-evidence/OPP-1/")

def test_claim_evidence_proxy_reads_private_oss_image(monkeypatch) -> None:
    monkeypatch.setattr(claims, "read_oss_object_by_public_url", lambda url: (b"image-bytes", "image/png"))

    response = client.get(
        "/claims/evidence-images/proxy",
        params={"url": "https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/claim-evidence/a/proof.png"},
    )

    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["content-type"] == "image/png"
