import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_central_import import apply_central_rows, business_period_from_sheet  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_business_period_from_sheet() -> None:
    assert business_period_from_sheet("6.30") == "开发0630期"
    assert business_period_from_sheet("4.28") == "开发0428期"
    assert business_period_from_sheet("说明文档") is None


def central_row(sub_sku: str, image_url: str | None = None) -> dict:
    return {
        "source_type": "history_central_ph",
        "source_file": "东南亚海外仓新品表-PH.xlsx",
        "source_sheet": "6.30",
        "source_row": 3,
        "batch": "开发0630期",
        "country": "PH",
        "site": "PH",
        "main_sku": sub_sku[:-1],
        "sub_sku": sub_sku,
        "image_url": image_url,
        "developer_department": "开发一部",
        "developer_name": "开发员A",
        "category_level1": "家居厨卫",
        "keyword": "hook",
        "main_sku_name": "挂钩",
        "sub_sku_name": "挂钩-灰",
        "product_type": "新品",
        "reason": "测试",
        "snapshot": {
            "archive_type": "historical_central",
            "business_period": "开发0630期",
            "fields_by_cell": {"A": {"header": "站点", "value": "PH"}},
            "source_reference": {"source_file": "x", "source_sheet": "6.30", "source_row": 3},
        },
    }


def test_apply_creates_updates_and_backfills_images() -> None:
    with SessionLocal() as db:
        db.add(
            models.NewProductOpportunity(
                source_type="historical_market_monitor_archive",
                main_sku="HXG15G",
                sub_sku="HXG15GD",
                batch="开发0630期",
                current_status="historical_archive",
            )
        )
        db.commit()

    rows = [central_row("HXG15GD", image_url="https://oss.example/img1.png")]
    with SessionLocal() as db:
        counts = apply_central_rows(db, rows, source_label="PH")
        db.commit()
    assert counts == {"created": 1, "updated": 0, "image_backfilled": 1}

    with SessionLocal() as db:
        central = db.query(models.NewProductOpportunity).filter_by(source_type="history_central_ph").one()
        monitor = db.query(models.NewProductOpportunity).filter_by(source_type="historical_market_monitor_archive").one()
        snapshots = db.query(models.SourceRecordSnapshot).count()
        assert central.batch == "开发0630期"
        assert central.current_status == "historical_archive"
        assert central.image_url == "https://oss.example/img1.png"
        assert monitor.image_url == "https://oss.example/img1.png"
        assert snapshots == 1
        assert db.query(models.FlowTask).count() == 0

    with SessionLocal() as db:
        counts2 = apply_central_rows(db, rows, source_label="PH")
        db.commit()
    assert counts2["created"] == 0
    assert counts2["updated"] == 1
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(source_type="history_central_ph").count() == 1
