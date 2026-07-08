import os
import sys
from base64 import b64decode
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.drawing.image import Image  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / ".uploaded_sources"
PNG_BYTES = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_selection1_import_creates_batch_and_links_snapshots(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1.xlsx"
    build_selection1_fixture(workbook_path)

    response = client.post("/opportunities/import/selection1", json={"source_file": str(workbook_path), "source_sheet": "W27"})

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 1
    assert body["import_batch_id"]

    with SessionLocal() as db:
        batch = db.get(models.ImportBatch, body["import_batch_id"])
        opportunity = db.query(models.NewProductOpportunity).one()
        snapshot = db.query(models.SourceRecordSnapshot).one()

    assert batch is not None
    assert batch.created_count == 1
    assert opportunity.import_batch_id == batch.id
    assert opportunity.current_status == "pending_assignment"
    assert snapshot.import_batch_id == batch.id
    assert db.query(models.FlowTask).count() == 0


def test_selection1_upload_import_uses_browser_file(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1_upload.xlsx"
    build_selection1_fixture(workbook_path)

    with workbook_path.open("rb") as handle:
        response = client.post(
            "/opportunities/import/selection1/upload",
            data={"source_sheet": "W27"},
            files={"file": ("selection1.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 1
    assert "selection1" in body["source_file"]


def test_excel_sheet_upload_returns_first_sheet(tmp_path: Path) -> None:
    workbook_path = tmp_path / "multi_sheet.xlsx"
    workbook = Workbook()
    workbook.active.title = "latest"
    workbook.create_sheet("history")
    workbook.save(workbook_path)

    with workbook_path.open("rb") as handle:
        response = client.post(
            "/opportunities/excel-sheets/upload",
            files={"file": ("multi_sheet.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

    assert response.status_code == 200
    assert response.json() == {"sheets": ["latest", "history"], "default_sheet": "latest"}


def test_selection1_import_extracts_embedded_product_image(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1_image.xlsx"
    image_path = tmp_path / "product.png"
    image_path.write_bytes(PNG_BYTES)
    build_selection1_fixture(workbook_path, image_path=image_path)

    response = client.post("/opportunities/import/selection1", json={"source_file": str(workbook_path), "source_sheet": "W27"})

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.query(models.NewProductOpportunity).one()

    assert opportunity.image_url
    assert opportunity.image_url.startswith("/uploaded-sources/product-images/")
    assert (UPLOAD_ROOT / opportunity.image_url.removeprefix("/uploaded-sources/")).exists()
    assert client.get(opportunity.image_url).status_code == 200


def test_selection1_import_skips_repeated_header_rows(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1_headers.xlsx"
    build_selection1_fixture(workbook_path, include_repeated_header=True)

    response = client.post("/opportunities/import/selection1", json={"source_file": str(workbook_path), "source_sheet": "W27"})

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(main_sku="MAINSKU").count() == 0


def test_selection1_reimport_keeps_previous_source_snapshots(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection1_reimport.xlsx"
    build_selection1_fixture(workbook_path)
    payload = {"source_file": str(workbook_path), "source_sheet": "W27"}

    first = client.post("/opportunities/import/selection1", json=payload)
    second = client.post("/opportunities/import/selection1", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    with SessionLocal() as db:
        snapshots = db.query(models.SourceRecordSnapshot).order_by(models.SourceRecordSnapshot.created_at).all()

    assert len(snapshots) == 2
    assert snapshots[0].import_batch_id == first.json()["import_batch_id"]
    assert snapshots[1].import_batch_id == second.json()["import_batch_id"]


def build_selection1_fixture(path: Path, image_path: Path | None = None, include_repeated_header: bool = False) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "W27"
    worksheet.append([None] * 86)
    headers = [None] * 86
    for column_index, title in {
        1: "site",
        8: "main_sku",
        10: "sub_sku",
        82: "salesperson",
        83: "claim_result",
        84: "claim_daily_sales",
    }.items():
        headers[column_index - 1] = title
    worksheet.append(headers)
    row = [None] * 86
    for column_index, value in {
        1: "TH",
        8: "MAIN-001",
        10: "SUB-001",
        82: "Operator A",
        83: "yes",
        84: 1,
    }.items():
        row[column_index - 1] = value
    worksheet.append(row)
    if include_repeated_header:
        repeated = [None] * 86
        repeated[7] = "MainSKU"
        repeated[9] = "SubSKU"
        worksheet.append(repeated)
    if image_path:
        worksheet.add_image(Image(str(image_path)), "F3")
    workbook.save(path)
