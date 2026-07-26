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
    pre_sheet = workbook.create_sheet("开发0407期")
    pre_sheet.append(["站点", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称", "主SKU",
                      "子SKU名称", "子SKU", "产品类型", "开品理由"])
    pre_sheet.append([None] * 12)
    pre_sheet.append(["菲律宾", "部", "员", "类", "kw", None, "名", "OLD407", "名B", "OLD407A", "引流", "r"])
    # 旧世代双层结构（仿真实 0820 期）：R1 字段+分组表头（含重复子SKU列、无站点列），
    # R2 分组子字段，R3 公式行（无子SKU，应跳过），R4 起数据。
    old_sheet = workbook.create_sheet("开发0820期--表格容易错行")
    old_sheet.append(["序列", "需求日期", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称",
                      "主SKU", "是否进入核价流程", "子SKU名称", "子SKU", "子SKU",
                      "竞品单价\n（链接1）\n(比索）", "竞品月销\n（链接1）", "参考定价   （比索）", "开发询价", None])
    old_sheet.append([None] * 16 + ["国内参考链接", "供应商名称"])
    old_sheet.append(["公式行", "2025-08-13", None, None, None, None, None, None,
                      None, None, None, None, None, 66, None, 75, None, None])
    old_sheet.append([None, "2025-08-13", "产品开发四部", "金彩", "宠物用品", "pet bed", None, "宠物窝",
                      "OLD820", "是", "蓝色招财猫S码", "OLD820A", None,
                      130, 392, 130, "https://detail.1688.com/offer/1", "唐山盈好"])
    note_sheet = workbook.create_sheet("说明文档")
    note_sheet.append(["这是说明文字"])
    workbook.save(path)


def build_old_generation_workbook(path: Path) -> None:
    workbook = Workbook()
    # 单层表头 + 空行 + 数据（含旧世代别名：关键词组 / 主SKU名称（33））
    sheet = workbook.active
    sheet.title = "开发0903期"
    sheet.append(["序列", "需求日期", "开发部门", "开发员", "一级类目", "关键词组", "产品图片",
                  "主SKU名称（33）", "主SKU", "子SKU名称", "子SKU", "参考定价   （比索）", "备注"])
    sheet.append([None] * 13)
    sheet.append([1, "2025-09-01", "产品开发五部", "开发员E", "收纳", "storage box", None,
                  "收纳箱", "OLD903", "收纳箱-绿", "OLD903A", 88, "旧世代备注"])
    # 单层表头 + 数据紧跟（仿真实 0827 期，无空行、无第二层表头）
    direct = workbook.create_sheet("开发0827期")
    direct.append(["需求日期", "一级类目", "产品图片", "主SKU名称", "主SKU", "子SKU名称", "子SKU",
                   "合计单销", "是否认领", "销售反馈"])
    direct.append(["2025-08-25", "玩具", None, "分数学习器", "OLD827", "全套磁性分数学习器", "OLD827A1",
                   0.5, "是", "反馈1"])
    direct.append(["2025-08-25", "玩具", None, None, None, "新款磁性分数盘", "OLD827A2", 0.5, None, None])
    # 前 3 行找不到主SKU/子SKU表头 → 整表跳过并报告
    broken = workbook.create_sheet("开发0908期")
    broken.append(["随便", "什么"])
    broken.append(["数据", "行"])
    broken.append(["还是", "数据"])
    workbook.save(path)


def parse_fixture(tmp_path: Path) -> dict:
    source = tmp_path / "选品1：海外仓开发部门开发新品认领-反馈-测试.xlsx"
    build_selection1_workbook(source)
    return parse_selection1_workbook(source)


def test_parse_scopes_both_generations_and_keeps_full_snapshot(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    assert report["sheets"] == [
        {"sheet": "开发0623期", "period": "开发0623期", "rows": 2, "skipped": 2},
        {"sheet": "开发0820期--表格容易错行", "period": "开发0820期", "rows": 1, "skipped": 1,
         "generation": "old"},
    ]
    skipped = {entry["sheet"]: entry["reason"] for entry in report["skipped_sheets"]}
    assert skipped == {
        "开发0407期": "早于0414期",
        "说明文档": "非期数sheet",
    }
    assert report["row_count"] == 3
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
    # 新世代快照形状保持既有（不带世代标记，0414-0623 已入库）。
    assert "generation" not in first["snapshot"]


def test_parse_old_generation_two_layer_sheet(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    old = [row for row in report["rows"] if row["batch"] == "开发0820期"]
    assert len(old) == 1
    row = old[0]
    # 公式行（无子SKU）跳过后，数据从第 4 行起。
    assert row["source_row"] == 4
    assert row["main_sku"] == "OLD820"
    assert row["sub_sku"] == "OLD820A"
    # 旧世代无站点列：site/country 置空，不造数。
    assert row["site"] is None
    assert row["country"] is None
    assert row["developer_department"] == "产品开发四部"
    assert row["developer_name"] == "金彩"
    assert row["keyword"] == "pet bed"
    assert row["main_sku_name"] == "宠物窝"
    assert row["sub_sku_name"] == "蓝色招财猫S码"
    assert row["product_type"] is None and row["reason"] is None
    assert row["snapshot"]["generation"] == "old"
    assert row["snapshot"]["site_raw"] is None
    cells = row["snapshot"]["fields_by_cell"]
    # 重复『子SKU』表头取首列（L），数据不串列。
    assert cells["L"]["value"] == "OLD820A" and "M" not in cells
    # 带换行的竞品表头与参考定价（比索）全列保真。
    assert cells["N"] == {"header": "竞品单价\n（链接1）\n(比索）", "group": "竞品单价\n（链接1）\n(比索）",
                          "value": 130}
    assert cells["O"]["value"] == 392
    assert cells["P"]["header"] == "参考定价   （比索）" and cells["P"]["value"] == 130
    # 双层分组（开发询价）与新世代同一套解析逻辑。
    assert cells["Q"] == {"header": "国内参考链接", "group": "开发询价", "value": "https://detail.1688.com/offer/1"}
    assert cells["R"] == {"header": "供应商名称", "group": "开发询价", "value": "唐山盈好"}


def test_parse_old_generation_single_layer_variants(tmp_path: Path) -> None:
    source = tmp_path / "选品1：旧世代单层变体.xlsx"
    build_old_generation_workbook(source)
    report = parse_selection1_workbook(source)
    assert report["sheets"] == [
        {"sheet": "开发0903期", "period": "开发0903期", "rows": 1, "skipped": 0, "generation": "old"},
        {"sheet": "开发0827期", "period": "开发0827期", "rows": 2, "skipped": 0, "generation": "old"},
    ]
    assert report["skipped_sheets"] == [{"sheet": "开发0908期", "reason": "前3行未探测到主SKU/子SKU表头"}]
    by_sub = {row["sub_sku"]: row for row in report["rows"]}
    # 单层表头 + 空行：数据从第 3 行起；旧世代别名（关键词组 / 主SKU名称（33））生效。
    blank_variant = by_sub["OLD903A"]
    assert blank_variant["source_row"] == 3
    assert blank_variant["main_sku"] == "OLD903"
    assert blank_variant["keyword"] == "storage box"
    assert blank_variant["main_sku_name"] == "收纳箱"
    assert blank_variant["site"] is None and blank_variant["country"] is None
    assert blank_variant["snapshot"]["generation"] == "old"
    # 单层表头 + 数据紧跟（0827 变体）：第 2 行即数据，不被当成第二层表头吞掉。
    first_direct = by_sub["OLD827A1"]
    assert first_direct["source_row"] == 2
    assert first_direct["main_sku"] == "OLD827"
    second_direct = by_sub["OLD827A2"]
    assert second_direct["source_row"] == 3
    # 主SKU 空缺沿用现行回退规则（=子SKU），与新世代行为一致。
    assert second_direct["main_sku"] == "OLD827A2"
    assert second_direct["snapshot"]["generation"] == "old"


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        plan = plan_selection1_rows(db, report["rows"])
    assert plan["would_create"] == 3
    assert plan["by_period"]["开发0623期"] == {"rows": 2, "would_create": 2, "skipped": 0}
    assert plan["by_period"]["开发0820期"] == {"rows": 1, "would_create": 1, "skipped": 0}
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
    assert counts["created"] == 3
    assert counts["batch_already_imported"] is False
    with SessionLocal() as db:
        opportunities = db.query(models.NewProductOpportunity).all()
        assert {item.source_type for item in opportunities} == {SOURCE_TYPE}
        assert {item.current_status for item in opportunities} == {"historical_archive"}
        assert {item.sub_sku for item in opportunities} == {"HXG15GD", "TAB10KB", "OLD820A"}
        old_row = next(item for item in opportunities if item.sub_sku == "OLD820A")
        assert old_row.snapshot["generation"] == "old"
        assert old_row.site is None and old_row.country is None
        assert db.query(models.SourceRecordSnapshot).count() == 3
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.FlowInstance).count() == 0
        assert db.query(models.SalesClaimForecast).count() == 0
        assert db.query(models.NotificationLog).count() == 0
        batch = db.query(models.ImportBatch).one()
        assert batch.status == "completed"
        assert batch.created_count == 3


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    report = parse_fixture(tmp_path)
    with SessionLocal() as db:
        apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t1",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    with SessionLocal() as db:
        same_tag = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t1",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    assert same_tag["batch_already_imported"] is True
    assert same_tag["created"] == 0
    with SessionLocal() as db:
        second = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t2",
            source_sha256=report["source_sha256"],
        )
        db.commit()
    # 同文件换新批次标签允许通过批次闸（扩范围补导场景），行级判重兜底不重复建行。
    assert second["batch_already_imported"] is False
    assert second["created"] == 0
    assert second["skipped_existing_archive"] == 3
    with SessionLocal() as db:
        third = apply_selection1_rows(
            db, report["rows"], source_label=report["source_file"], batch_tag="t3",
            source_sha256=None,
        )
        db.commit()
    assert third["created"] == 0
    assert third["skipped_existing_archive"] == 3
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 3
        assert db.query(models.SourceRecordSnapshot).count() == 3


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
    assert counts["created"] == 2
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
        created = db.query(models.NewProductOpportunity).filter_by(source_type=SOURCE_TYPE).all()
        assert {item.sub_sku for item in created} == {"TAB10KB", "OLD820A"}


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
    assert reverted == {"reverted_opportunities": 3, "reverted_snapshots": 3}
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
    assert again["created"] == 3
    with SessionLocal() as db:
        assert db.query(models.NotificationLog).count() == 0
