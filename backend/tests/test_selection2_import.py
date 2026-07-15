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


def test_selection2_import_is_idempotent_and_keeps_multi_sales_feedback(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection2.xlsx"
    build_selection2_fixture(workbook_path)
    payload = {"source_file": str(workbook_path), "source_sheet": "5.26期"}

    first = client.post("/opportunities/import/selection2", json=payload)
    second = client.post("/opportunities/import/selection2", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created_count"] == 1
    assert second.json()["created_count"] == 0
    assert second.json()["updated_count"] == 1

    with SessionLocal() as db:
        opportunity = db.query(models.NewProductOpportunity).one()
        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.source_column).all()
        snapshots = db.query(models.SourceRecordSnapshot).order_by(models.SourceRecordSnapshot.created_at).all()

    assert opportunity.source_type == "selection2_caigen_claim_feedback"
    assert opportunity.main_sku == "HXG15GD"
    assert opportunity.sub_sku == "HXG15GD"
    assert opportunity.site is None
    assert opportunity.snapshot["headers_by_column"]["H"] == ["进价"]
    assert [snapshot.import_batch_id for snapshot in snapshots] == [
        first.json()["import_batch_id"],
        second.json()["import_batch_id"],
    ]
    assert [(claim.salesperson_name, claim.claim_result, claim.claim_daily_sales, claim.reject_reason) for claim in claims] == [
        ("冯卓宏", "reject", None, None),
        ("李桂敏", "reject", None, "市场销量不足"),
        ("赵钰婷", "claim", 1.5, None),
    ]


def test_selection2_upload_import_uses_browser_file(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection2_upload.xlsx"
    build_selection2_fixture(workbook_path)

    with workbook_path.open("rb") as handle:
        response = client.post(
            "/opportunities/import/selection2/upload",
            data={"source_sheet": "5.26期"},
            files={
                "file": (
                    "选品2：海外仓财根团队开发新品认领-反馈.xlsx",
                    handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    assert "选品2" in body["source_file"]


def test_selection2_upload_import_tolerates_sheet_spacing(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection2_upload.xlsx"
    build_selection2_fixture(workbook_path)

    with workbook_path.open("rb") as handle:
        response = client.post(
            "/opportunities/import/selection2/upload",
            data={"source_sheet": "5.26 期"},
            files={
                "file": (
                    "选品2：海外仓财根团队开发新品认领-反馈.xlsx",
                    handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 200
    assert response.json()["source_sheet"] == "5.26期"


def test_selection2_import_extracts_embedded_product_image(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection2_image.xlsx"
    image_path = tmp_path / "product.png"
    image_path.write_bytes(PNG_BYTES)
    build_selection2_fixture(workbook_path, image_path=image_path)

    response = client.post(
        "/opportunities/import/selection2",
        json={"source_file": str(workbook_path), "source_sheet": "5.26期"},
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunity = db.query(models.NewProductOpportunity).one()

    assert opportunity.image_url
    assert opportunity.image_url.startswith("/uploaded-sources/product-images/")
    assert (UPLOAD_ROOT / opportunity.image_url.removeprefix("/uploaded-sources/")).exists()
    assert client.get(opportunity.image_url).status_code == 200


def test_selection2_clean_import_has_no_prefill_claims(tmp_path: Path) -> None:
    workbook_path = tmp_path / "selection2_clean.xlsx"
    build_selection2_clean_fixture(workbook_path)

    response = client.post(
        "/opportunities/import/selection2",
        json={"source_file": str(workbook_path), "source_sheet": "5.26期"},
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 2
    assert response.json()["prefill_claim_count"] == 0
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 2
        assert db.query(models.SalesClaimForecast).count() == 0
        assert db.query(models.FlowTask).count() == 2


def build_selection2_fixture(path: Path, image_path: Path | None = None) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "5.26期"
    headers = [None] * 48
    for column_index, title in {
        2: "SPU",
        3: "SKU",
        5: "产品名称",
        6: "产品规格属性（材质、大小、颜色）",
        7: "图片",
        8: "进价",
        22: "进货链接",
        38: "开发表格认领情况--主销售员",
        39: "是否认领",
        40: "认领单销",
        41: "销售员1",
        42: "认领单销/不认领原因",
        43: "销售员2",
        44: "认领单销/不认领原因",
    }.items():
        headers[column_index - 1] = title
    worksheet.append(headers)
    row = [None] * 48
    for column_index, value in {
        3: "HXG15GD",
        5: "本田CLICK125/CLICK150",
        6: "黑色金线",
        8: 12.2,
        22: "https://detail.1688.com/offer/1.html",
        38: "冯卓宏",
        39: "否",
        40: 0,
        41: "李桂敏",
        42: "市场销量不足",
        43: "赵钰婷",
        44: 1.5,
    }.items():
        row[column_index - 1] = value
    if image_path is None:
        row[6] = "https://example.com/image.jpg"
    worksheet.append(row)
    if image_path:
        worksheet.add_image(Image(str(image_path)), "G2")
    workbook.save(path)


def build_selection2_clean_fixture(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "5.26期"
    headers = [None] * 48
    for column_index, title in {
        2: "SPU",
        3: "SKU",
        5: "产品名称",
        6: "产品规格属性（材质、大小、颜色）",
        7: "图片",
        8: "进价",
        22: "进货链接",
        38: "开发表格认领情况--主销售员",
        39: "是否认领",
        40: "认领单销",
        41: "销售员1",
        42: "认领单销/不认领原因",
    }.items():
        headers[column_index - 1] = title
    worksheet.append(headers)
    for index in range(2):
        row = [None] * 48
        for column_index, value in {
            2: f"CG-CLEAN-{index + 1}",
            3: f"CG-CLEAN-{index + 1}-A",
            5: f"财根干净测试商品{index + 1}",
            6: "无历史认领",
            7: f"https://example.com/clean-{index + 1}.jpg",
            8: 10 + index,
            22: f"https://detail.1688.com/offer/clean-{index + 1}.html",
        }.items():
            row[column_index - 1] = value
        worksheet.append(row)
    workbook.save(path)
