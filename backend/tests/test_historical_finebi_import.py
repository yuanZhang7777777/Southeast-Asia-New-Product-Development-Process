import os
import sys
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app import historical_finebi_import as hfi  # noqa: E402
from app import models, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def build_workbench(path: Path, rows: list[list]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "精品流程"
    for _ in range(3):
        worksheet.append([None] * 38)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def workbench_row(
    main_sku: str,
    shop: str,
    item: str,
    *,
    salesperson: str = "运营A",
    country: str = "PH",
    week1_metrics: list | None = None,
    week1_review: list | None = None,
    summary: str | None = None,
) -> list:
    row = [None] * 38
    row[0] = "2026-06-01"
    row[1] = main_sku
    row[2] = country
    row[3] = salesperson
    row[4] = shop
    row[5] = item
    row[6] = "标题优化"
    if week1_metrics:
        row[12:16] = week1_metrics
    if week1_review:
        row[16:19] = week1_review
    if summary:
        row[37] = summary
    return row


def build_finebi(path: Path, rows: list[list]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "ItemID财务数据八部"
    worksheet.append(
        ["ITEMID", "主SKU", "店铺", "审核时间", "订单特性", "总收入", "商品数量", "订单量", "一次毛利",
         "SKU一次毛利率", "SKU合单率", "商品成本", "预估重量"]
    )
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def finebi_row(item: str, main_sku: str, shop: str, revenue: float, orders: int, gross: float) -> list:
    return [item, main_sku, shop, "2026-04-03", "普通", revenue, 1, orders, gross, 0.2, 0.5, 10, 0.3]


def run_import(tmp_path: Path, workbench_rows: list[list], finebi_files: dict[str, list[list]], apply: bool = True):
    workbench_path = tmp_path / "刊登监控.xlsx"
    build_workbench(workbench_path, workbench_rows)
    finebi_dir = tmp_path / "finebi_live"
    finebi_dir.mkdir(exist_ok=True)
    for period, rows in finebi_files.items():
        build_finebi(finebi_dir / f"05_ItemID财务数据八部_{period}.xlsx", rows)
    workbench, warnings = hfi.read_workbench(workbench_path)
    finebi, periods, skipped = hfi.read_finebi_periods(finebi_dir, 2026)
    with SessionLocal() as db:
        plan = hfi.build_plan(db, workbench, finebi, 2026)
        counts = None
        if apply:
            counts = hfi.apply_plan(db, plan, source_label="test")
            db.commit()
    return plan, counts, {"warnings": warnings, "periods": periods, "skipped": skipped}


def test_shared_item_aggregation_review_and_idempotency(tmp_path: Path) -> None:
    workbench_rows = [
        workbench_row("MAINA", "Shopee-101PH", "10000000001",
                      week1_review=["2026-06-08", "利润款", "调价"], summary="总体表现稳定"),
        workbench_row("MAINB", "Shopee-101PH", "10000000001"),
    ]
    finebi_files = {
        "0402-0408": [
            finebi_row("10000000001", "MAINA", "Shopee-101PH", 100.0, 3, 20.0),
            finebi_row("10000000001", "MAINB", "Shopee-101PH", 50.0, 2, 10.0),
        ],
        "0409-0415": [finebi_row("10000000001", "MAINA", "Shopee-101PH", 80.0, 4, 16.0)],
        "0723-0729": [finebi_row("10000000001", "MAINA", "Shopee-101PH", 999.0, 99, 999.0)],
    }
    plan, counts, meta = run_import(tmp_path, workbench_rows, finebi_files)

    assert meta["skipped"] == ["0723-0729"]
    assert plan["summary"]["scoped_items"] == 1
    assert plan["summary"]["shared_items"] == 1
    assert counts["listings_created"] == 1
    assert counts["bindings_created"] == 2

    with SessionLocal() as db:
        listing = db.query(models.ListingRecord).one()
        bindings = db.query(models.ListingSkuBinding).order_by(models.ListingSkuBinding.main_sku).all()
        weeks = (
            db.query(models.ItemObservationPeriod)
            .order_by(models.ItemObservationPeriod.week_number)
            .all()
        )
        assert listing.source_type == "history_finebi"
        assert listing.is_shared_item is True
        assert listing.representative_rule == "lexical_first"
        assert listing.main_sku == "MAINA"
        assert listing.first_period_start == date(2026, 4, 2)
        assert [binding.main_sku for binding in bindings] == ["MAINA", "MAINB"]
        assert {binding.binding_source for binding in bindings} == {"history_finebi"}
        assert [week.week_number for week in weeks] == [1, 2, 4]
        week1, week2, week4 = weeks
        assert (week1.order_count, week1.total_revenue, week1.gross_profit_amount) == (5, 150.0, 30.0)
        assert week1.period_start == date(2026, 4, 2)
        assert week1.record_source == "history_finebi"
        assert week1.metrics_origin == "finebi_live"
        assert week1.product_positioning == "利润款"
        assert week2.order_count == 4
        assert week4.period_start is None
        assert week4.four_week_summary == "总体表现稳定"
        assert db.query(models.NotificationLog).count() == 0
        assert db.query(models.SalesClaimForecast).count() == 0

    plan2, counts2, _ = run_import(tmp_path, workbench_rows, finebi_files)
    assert counts2["listings_created"] == 0
    assert counts2["listings_reused"] == 1
    assert counts2["bindings_created"] == 0
    assert counts2["weeks_created"] == 0
    assert counts2["weeks_updated"] == 0
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 1
        assert db.query(models.ListingSkuBinding).count() == 2
        assert db.query(models.ItemObservationPeriod).count() == 3

    with SessionLocal() as db:
        workbench_view = services.list_listing_workbench(db)
        summary_view = services.listing_summary(db, "MAINA")
    assert workbench_view["listing_records"] == []
    assert workbench_view["period_rows"] == []
    assert len(summary_view["listing_records"]) == 1
    assert summary_view["listing_records"][0]["is_shared_item"] is True
    assert {row["record_source"] for row in summary_view["period_rows"]} == {"history_finebi"}
    assert len(summary_view["period_rows"]) == 3


def test_finebi_metrics_start_at_first_complete_period_and_cap_at_four_weeks(tmp_path: Path) -> None:
    workbench_rows = [workbench_row("MAINF", "Shopee-105PH", "10000000006")]
    finebi_files = {
        "0402-0408": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 0.0, 0, 0.0)],
        "0409-0415": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 10.0, 1, 2.0)],
        "0416-0422": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 20.0, 2, 4.0)],
        "0423-0429": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 30.0, 3, 6.0)],
        "0430-0506": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 40.0, 4, 8.0)],
        "0723-0729": [finebi_row("10000000006", "MAINF", "Shopee-105PH", 999.0, 99, 999.0)],
    }
    plan, counts, meta = run_import(tmp_path, workbench_rows, finebi_files)

    assert meta["skipped"] == ["0723-0729"]
    assert len(plan["items"][0]["finebi_weeks"]) == 4
    assert [week["period"] for week in plan["items"][0]["finebi_weeks"]] == [
        "0402-0408",
        "0409-0415",
        "0416-0422",
        "0423-0429",
    ]
    assert counts["weeks_created"] == 4
    with SessionLocal() as db:
        weeks = db.query(models.ItemObservationPeriod).order_by(models.ItemObservationPeriod.week_number).all()
        assert [week.period_start for week in weeks] == [
            date(2026, 4, 2),
            date(2026, 4, 9),
            date(2026, 4, 16),
            date(2026, 4, 23),
        ]
        assert weeks[0].order_count == 0
def test_workbench_only_item_uses_fallback_metrics(tmp_path: Path) -> None:
    workbench_rows = [
        workbench_row("MAINC", "Shopee-102TH", "10000000002", country="TH",
                      week1_metrics=[6, 300.0, 60.0, 0.2], week1_review=["2026-06-08", "引流款", "加广告"]),
    ]
    plan, counts, _ = run_import(tmp_path, workbench_rows, {})

    assert plan["summary"]["workbench_fallback_week_rows"] == 1
    with SessionLocal() as db:
        listing = db.query(models.ListingRecord).one()
        week = db.query(models.ItemObservationPeriod).one()
        assert listing.country == "TH"
        assert listing.first_period_start is None
        assert week.week_number == 1
        assert week.period_start is None
        assert week.metrics_origin == "workbench_fallback"
        assert (week.order_count, week.total_revenue, week.gross_profit_amount) == (6, 300.0, 60.0)
        assert week.product_positioning == "引流款"


def test_finebi_only_item_scoped_by_known_main_sku(tmp_path: Path) -> None:
    with SessionLocal() as db:
        db.add(
            models.NewProductOpportunity(
                source_type="selection1_developer_claim_feedback",
                main_sku="MAIND",
                sub_sku="MAIND-1",
                country="VN",
            )
        )
        db.commit()
        opportunity_id = db.query(models.NewProductOpportunity).one().id

    finebi_files = {
        "0402-0408": [
            finebi_row("10000000003", "MAIND", "Shopee-103VN", 10.0, 1, 2.0),
            finebi_row("10000000004", "UNKNOWN-SKU", "Shopee-103VN", 10.0, 1, 2.0),
        ],
    }
    plan, counts, _ = run_import(tmp_path, [], finebi_files)

    assert plan["summary"]["scoped_items"] == 1
    assert plan["summary"]["finebi_items_out_of_scope"] == 1
    with SessionLocal() as db:
        listing = db.query(models.ListingRecord).one()
        binding = db.query(models.ListingSkuBinding).one()
        assert listing.item == "10000000003"
        assert listing.salesperson_name == ""
        assert binding.opportunity_id == opportunity_id


def test_history_import_attaches_to_existing_platform_listing(tmp_path: Path) -> None:
    with SessionLocal() as db:
        listing = models.ListingRecord(
            id=models.new_id(),
            source_group_key="seed-task",
            source_claim_ids=[],
            source_type="selection1",
            main_sku="MAINE",
            salesperson_name="运营B",
            shop="Shopee-104PH",
            item="10000000005",
            listing_strategy="平台策略",
            first_period_start=date(2026, 7, 16),
            first_period_end=date(2026, 7, 22),
            representative_rule="single_binding",
        )
        db.add(listing)
        db.add(
            models.ItemObservationPeriod(
                id=models.new_id(),
                listing_record_id=listing.id,
                week_number=1,
                period_start=date(2026, 7, 16),
                period_end=date(2026, 7, 22),
            )
        )
        db.commit()
        platform_listing_id = listing.id

    finebi_files = {"0402-0408": [finebi_row("10000000005", "MAINE", "Shopee-104PH", 10.0, 1, 2.0)]}
    plan, counts, _ = run_import(tmp_path, [], finebi_files)

    assert plan["summary"]["scoped_items"] == 1
    assert counts["listings_created"] == 0
    assert counts["listings_reused"] == 1
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 1
        history_weeks = (
            db.query(models.ItemObservationPeriod)
            .filter_by(listing_record_id=platform_listing_id, record_source="history_finebi")
            .all()
        )
        platform_weeks = (
            db.query(models.ItemObservationPeriod)
            .filter_by(listing_record_id=platform_listing_id, record_source="platform")
            .all()
        )
        assert len(history_weeks) == 1
        assert len(platform_weeks) == 1
        assert platform_weeks[0].period_start == date(2026, 7, 16)
