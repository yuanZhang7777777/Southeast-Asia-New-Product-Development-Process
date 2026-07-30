from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.selection1_importer import parse_selection1_row, source_headers_by_column


def test_selection1_parser_handles_caigen_extended_opening_period_column() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append([
        "开品周期",
        "站点",
        "开发部门",
        "开发员",
        "一级类目",
        "关键词",
        "产品图片",
        "主SKU名称",
        "主SKU",
        "子SKU名称",
        "子SKU",
        "产品类型",
        "开品理由",
    ])
    worksheet.append(["", "", "", "", "", "", "", "", "", "", "", "引流or绑定or利润", ""])
    row = (
        "6.24-6.30",
        "菲律宾",
        "产品开发一部",
        "刘学广",
        "汽配与摩配",
        "Foot mat",
        None,
        "摩托车脚垫",
        "HXG44",
        "黑色",
        "HXG44BK",
        "利润",
        "供应商已核价",
    )

    parsed = parse_selection1_row(row, source_headers_by_column(worksheet, 13))

    assert parsed is not None
    assert parsed["main"]["site"] == "菲律宾"
    assert parsed["main"]["developer_department"] == "产品开发一部"
    assert parsed["main"]["main_sku_name"] == "摩托车脚垫"
    assert parsed["main"]["main_sku"] == "HXG44"
    assert parsed["main"]["sub_sku_name"] == "黑色"
    assert parsed["main"]["sub_sku"] == "HXG44BK"
    assert parsed["main"]["product_type"] == "利润"
    assert parsed["main"]["reason"] == "供应商已核价"
