import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_caigen_period.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app.historical_selection1_import import parse_selection1_workbook  # noqa: E402


def test_parse_treats_caigen_summary_as_independent_business_period(tmp_path: Path) -> None:
    source = tmp_path / "选品1：7.27新海外仓开发部门开发新品认领-反馈.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "开发-财根团队汇总"
    sheet.append(["站点", "开发部门", "开发员", "一级类目", "关键词", "主SKU名称", "主SKU", "子SKU名称", "子SKU", "产品类型", "开品理由"])
    sheet.append(["菲律宾", "财根团队", "开发员A", "家居", "hook", "挂钩", "CG-1", "挂钩黑", "CG-1A", "利润", "测试"])
    workbook.save(source)

    report = parse_selection1_workbook(source)

    assert report["sheets"] == [{"sheet": "开发-财根团队汇总", "period": "开发0727期-财根", "rows": 1, "skipped": 0}]
