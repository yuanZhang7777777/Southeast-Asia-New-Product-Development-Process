from pathlib import Path
import sys

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_data_audit import audit_source_workbooks, validate_required_headers


def test_audit_source_workbooks_reports_missing_duplicates_and_formula_errors() -> None:
    workbook_path = Path(".codex_tmp/test_historical_data_audit/history.xlsx")
    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "4.14"
    worksheet.append(["站点", "开发部门", "开发员", "一级类目", "关键词", "产品图片", "主SKU名称", "主SKU", "子SKU名称", "子SKU", "产品类型", "开品理由", "新字段"])
    worksheet.append(["", "", "", "", "", "", "", "", "", "", "引流or绑定or利润", "", ""])
    worksheet.append(["PH", "开发部", "张三", "家居厨卫", "kw", None, "主名", "MAIN1", "子名", "SUB1", "利润", "理由", "漂移值"])
    worksheet.append(["PH", "开发部", "张三", "家居厨卫", "kw", None, "主名", "MAIN1", "子名", "SUB1", "利润", "#DIV/0!", None])
    worksheet.append(["PH", "开发部", "张三", "家居厨卫", None, None, "主名", "MAIN2", "子名", "SUB2", "利润", "理由", None])
    workbook.save(workbook_path)

    report = audit_source_workbooks([workbook_path])

    sheet = report["files"][0]["sheets"][0]
    assert sheet["data_row_count"] == 3
    assert sheet["missing_required_counts"]["关键词"] == 1
    assert sheet["formula_error_count"] == 1
    assert sheet["unexpected_headers"] == [{"column": "M", "header": "新字段"}]
    assert report["duplicate_keys"][0]["key"] == "PH|SUB1"


def test_required_header_validation_accepts_selection1_aliases_and_rejects_missing() -> None:
    headers = ["国家", "部门", "开发员", "一级类目", "关键词", "主SKU名称", "主SKU", "子SKU名称", "子SKU", "产品类型", "开品理由"]

    result = validate_required_headers(headers)

    assert result["missing"] == []
    assert result["matched"]["站点/国家"] == "国家"

    missing = validate_required_headers(["国家", "部门"])
    assert "主SKU" in missing["missing"]
