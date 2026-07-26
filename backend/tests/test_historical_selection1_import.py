import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_selection1_import import (  # noqa: E402
    SOURCE_TYPE,
    apply_selection1_rows,
    parse_selection1_workbook,
    plan_selection1_rows,
    revert_selection1_import,
)
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def build_selection1_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "开发0623期"
    sheet.append(
        ["站点", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称", "主SKU",
         "子SKU名称", "子SKU", "产品类型", "开品理由", "月销次高", None, None, "月销第三高", None, None]
    )
    sheet.append(
        [None] * 12 + ["月销次高链接", "售价(PHP）", "月销", "月销第三高链接", "售价(PHP）", "月销"]
    )
    # 核价列落在 BY（旧 cells 快照 A:BX+CC:CH 的缺口区），验证全列保真。
    sheet.cell(row=1, column=77, value="供应链核价")
    sheet.cell(row=2, column=77, value="采购核价人")
    sheet.append(
        ["菲律宾", "开发一部", "开发员A", "家居厨卫", "hook", None, "挂钩", "HXG15G",
         "挂钩-灰", "HXG15GD", "引流", "理由A", "https://a.example/1", 11.5, 300, "https://b.example/3", 9.9, 120]
    )
    sheet.cell(row=3, column=77, value="核价员A")
    sheet.append(["合计", None, None, None, None, None, None, None, None, "合计", None, None])
    sheet.append(["站点", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称", "主SKU",
                  "子SKU名称", "子SKU", "产品类型", "开品理由"])
    sheet.append(
        ["泰国", "开发二部", "开发员B", "收纳", "box", None, "收纳盒", "TAB10K",
         "收纳盒-蓝", "TAB10KB", "利润", "理由B"]
    )
    for old_sheet_name, sub_sku in (("开发0407期", "OLD407A"), ("开发0820期--表格容易错行", "OLD820A")):
        old_sheet = workbook.create_sheet(old_sheet_name)
        old_sheet.append(["站点", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称", "主SKU",
                          "子SKU名称", "子SKU", "产品类型", "开品理由"])
        old_sheet.append([None] * 12)
        old_sheet.append(["菲律宾", "部", "员", "类", "kw", None, "名", sub_sku[:-1], "名B", sub_sku, "引流", "r"])
    note_sheet = workbook.create_sheet("说明文档")
    note_sheet.append(["这是说明文字"])
    workbook.save(path)


def parse_fixture(tmp_path: Path) -> dict:
    source = tmp_path / "选品1：海外仓开发部门开发新品认领-反馈-测试.xlsx"
    build_selection1_workbook(source)
    return parse_selection1_workbook(source)


def test_parse_scopes_new_generation_and_keeps_full_snapshot(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    assert report["sheets"] == [{"sheet": "开发0623期", "period": "开发0623期", "rows": 2, "skipped": 2}]
    skipped = {entry["sheet"]: entry["reason"] for entry in report["skipped_sheets"]}
    assert skipped == {
        "开发0407期": "早于0414期",
        "开发0820期--表格容易错行": "旧世代（0815-0924）",
        "说明文档": "非期数sheet",
    }
    assert report["row_count"] == 2
    first = report["rows"][0]
    assert first["sub_sku"] == "HXG15GD"
    assert first["main_sku"] == "HXG15G"
    assert first["batch"] == "开发0623期"
    assert first["country"] == "PH"
    assert first["site"] == "菲律宾"
    assert first["developer_name"] == "开发员A"
    assert first["product_type"] == "引流"
    cells = first["snapshot"]["fields_by_cell"]
    # 『月销次高/月销第三高』同名表头两列各自完整保留，不串值。
    assert cells["N"]["value"] == 11.5 and cells["N"]["group"] == "月销次高"
    assert cells["Q"]["value"] == 9.9 and cells["Q"]["group"] == "月销第三高"
    assert cells["O"]["value"] == 300
    assert cells["R"]["value"] == 120
    # 核价列（BY）在快照内，无 BY:CB 缺口。
    assert cells["BY"] == {"header": "采购核价人", "group": "供应链核价", "value": "核价员A"}


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        plan = plan_selection1_rows(db, report["rows"])
    assert plan["would_create"] == 2
    assert plan["by_period"]["开发0623期"] == {"rows": 2, "would_create": 2, "skipped": 0}
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 0
        assert db.query(models.ImportBatch).count() == 0
        assert db.query(models.SourceRecordSnapshot).count() == 0
        assert db.query(models.AuditLog).count() == 0


def test_apply_creates_archive_rows_without_tasks_or_notifications(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        counts = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t-apply",
            imported_by="test", source_sha256=report["source_sha256"],
        )
        db.commit()
    assert counts["created"] == 2
    assert counts["batch_already_imported"] is False
    with SessionLocal() as db:
        opportunities = db.query(models.NewProductOpportunity).all()
        assert {item.source_type for item in opportunities} == {SOURCE_TYPE}
        assert {item.current_status for item in opportunities} == {"historical_archive"}
        assert {item.sub_sku for item in opportunities} == {"HXG15GD", "TAB10KB"}
        assert db.query(models.SourceRecordSnapshot).count() == 2
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.FlowInstance).count() == 0
        assert db.query(models.SalesClaimForecast).count() == 0
        assert db.query(models.NotificationLog).count() == 0
        batch = db.query(models.ImportBatch).one()
        assert batch.status == "completed"
        assert batch.created_count == 2


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t1",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    with SessionLocal() as db:
        second = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t2",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    assert second["batch_already_imported"] is True
    assert second["created"] == 0
    with SessionLocal() as db:
        third = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t3",
            source_sha256=None,
        )
        db.commit()
    assert third["created"] == 0
    assert third["skipped_existing_archive"] == 2
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 2
        assert db.query(models.SourceRecordSnapshot).count() == 2


def test_existing_current_flow_row_is_skipped_and_untouched(tmp_path: Path) -> None:
    with SessionLocal() as db:
        db.add(
            models.NewProductOpportunity(
                source_type=CURRENT_SELECTION1_SOURCE_TYPE,
                source_sheet="开发0623期",
                batch="开发0623期",
                main_sku="HXG15G",
                sub_sku="HXG15GD",
                site="PH",
                country="PH",
                current_status="pending_assignment",
                snapshot={"marker": "keep-me"},
            )
        )
        db.commit()
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        counts = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t-current",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    assert counts["created"] == 1
    assert counts["skipped_existing_current_flow"] == 1
    with SessionLocal() as db:
        current = db.query(models.NewProductOpportunity).filter_by(
            source_type=CURRENT_SELECTION1_SOURCE_TYPE
        ).one()
        assert current.current_status == "pending_assignment"
        assert current.snapshot == {"marker": "keep-me"}
        assert (
            db.query(models.NewProductOpportunity)
            .filter_by(source_type=SOURCE_TYPE, sub_sku="HXG15GD")
            .count()
            == 0
        )
        created = db.query(models.NewProductOpportunity).filter_by(source_type=SOURCE_TYPE).one()
        assert created.sub_sku == "TAB10KB"


def test_revert_removes_batch_and_allows_reimport(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t-revert",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    with SessionLocal() as db:
        reverted = revert_selection1_import(db, "t-revert", actor="test")
        db.commit()
    assert reverted == {"reverted_opportunities": 2, "reverted_snapshots": 2}
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 0
        assert db.query(models.SourceRecordSnapshot).count() == 0
        assert db.query(models.ImportBatch).one().status == "reverted"
    with SessionLocal() as db:
        again = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t-after-revert",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    assert again["batch_already_imported"] is False
    assert again["created"] == 2
    with SessionLocal() as db:
        assert db.query(models.NotificationLog).count() == 0
