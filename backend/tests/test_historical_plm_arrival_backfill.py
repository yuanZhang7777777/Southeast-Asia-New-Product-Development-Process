import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_plm_backfill.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_plm_arrival_backfill import apply_snapshot, snapshot_date_from_name  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def build_snapshot(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "汇总表格"
    worksheet.append(
        ["商品名称", "子SKU", "主SKU", "销售员", "集团", "海外仓", "国家",
         "最后一次入库时间", "首次上架时间", "海外仓可发", "真仓库存", "单销"]
    )
    worksheet.append(
        ["挂钩", "HXG15GD", "HXG15G", "销售A", "集团八部", "菲律宾仓", "菲律宾",
         "2026-06-20 10:00:00", "2026-06-20 10:00:00", 30, 40, 1.5]
    )
    worksheet.append(
        ["别部商品", "OTHER-1", "OTHER", "销售B", "集团一部", "泰国仓", "泰国",
         "2026-06-21 10:00:00", "2026-06-01 10:00:00", 5, 5, 0.2]
    )
    worksheet.append(
        ["无认领商品", "NOCLAIM-1", "NOCLAIM", "销售C", "集团八部", "泰国仓", "泰国",
         "2026-06-22 10:00:00", "2026-06-22 10:00:00", 8, 8, 0.4]
    )
    workbook.save(path)


def seeded_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            main_sku="HXG15G",
            sub_sku="HXG15GD",
            country="PH",
            site="PH",
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="销售A",
                claim_result="claim",
                source_column="platform",
                downstream_status="waiting_secondary_research",
            )
        )
        db.commit()


def test_snapshot_date_from_name() -> None:
    assert snapshot_date_from_name("真仓库存明细数据-普通商品-汇总数据-1782963834978.xlsx") is not None
    assert snapshot_date_from_name("真仓库存明细数据.xlsx") is None


def test_backfill_creates_archive_and_arrival_without_side_effects(tmp_path: Path) -> None:
    seeded_claim()
    snapshot = tmp_path / "真仓库存明细数据-汇总-1782963834978.xlsx"
    build_snapshot(snapshot)

    with SessionLocal() as db:
        dry = apply_snapshot(db, snapshot, "2026-07-01", apply=False)
        db.commit()
    assert dry["rows"] == 2
    assert dry["matched_rows"] == 1
    assert dry["arrival_created"] == 1
    with SessionLocal() as db:
        assert db.query(models.PlmArrivalBatch).count() == 0

    with SessionLocal() as db:
        applied = apply_snapshot(db, snapshot, "2026-07-01", apply=True, actor="test")
        db.commit()
    assert applied["arrival_created"] == 1
    with SessionLocal() as db:
        batch = db.query(models.PlmArrivalBatch).one()
        items = db.query(models.PlmArrivalItem).all()
        arrival = db.query(models.ArrivalRecord).one()
        claim = db.query(models.SalesClaimForecast).one()
        assert batch.status == "history_archive"
        assert len(items) == 2
        assert {item.match_status for item in items} == {"history_archive"}
        assert arrival.note == "历史PLM快照回填"
        assert arrival.arrived_at is not None
        assert claim.downstream_status == "waiting_secondary_research"
        assert db.query(models.NotificationLog).count() == 0

    with SessionLocal() as db:
        rerun = apply_snapshot(db, snapshot, "2026-07-01", apply=True, actor="test")
        db.commit()
    assert rerun["batch_already_imported"] is True
    assert rerun["arrival_created"] == 0
    assert rerun["claims_already_have_arrival"] == 1
    with SessionLocal() as db:
        assert db.query(models.PlmArrivalBatch).count() == 1
        assert db.query(models.ArrivalRecord).count() == 1
