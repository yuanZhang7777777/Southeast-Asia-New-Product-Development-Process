import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_archive_import import business_period_from_bucket  # noqa: E402
from app.historical_business_period_backfill import backfill_business_periods  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_business_period_from_bucket() -> None:
    assert business_period_from_bucket("开发新品0602期") == "开发0602期"
    assert business_period_from_bucket("开发新品0414期 备注") == "开发0414期"
    assert business_period_from_bucket("老品货盘") is None
    assert business_period_from_bucket(None) is None


def archive_opportunity(sub_sku: str, bucket: str | None, batch: str = "历史归档") -> models.NewProductOpportunity:
    return models.NewProductOpportunity(
        source_type="historical_market_monitor_archive",
        main_sku=sub_sku,
        sub_sku=sub_sku,
        batch=batch,
        current_status="historical_archive",
        snapshot={"raw_classification_record": {"product_bucket": bucket}},
    )


def test_backfill_updates_only_matching_rows() -> None:
    with SessionLocal() as db:
        db.add(archive_opportunity("SKU-A", "开发新品0602期"))
        db.add(archive_opportunity("SKU-B", "老品货盘"))
        db.add(archive_opportunity("SKU-C", "开发新品0428期", batch="开发0428期"))
        db.commit()

    with SessionLocal() as db:
        dry = backfill_business_periods(db, apply=False)
        db.commit()
    assert dry == {
        "mode": "dry-run",
        "updated": 1,
        "updated_by_period": {"开发0602期": 1},
        "unchanged": 1,
        "unmatched": 1,
    }
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(sub_sku="SKU-A").one().batch == "历史归档"

    with SessionLocal() as db:
        applied = backfill_business_periods(db, apply=True)
        db.commit()
    assert applied["updated"] == 1
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(sub_sku="SKU-A").one().batch == "开发0602期"
        assert db.query(models.NewProductOpportunity).filter_by(sub_sku="SKU-B").one().batch == "历史归档"
