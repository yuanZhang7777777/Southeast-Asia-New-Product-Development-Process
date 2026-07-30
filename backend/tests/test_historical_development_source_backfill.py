import json
import shutil
import sys
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_development_source_backfill import (  # noqa: E402
    build_backfill_rows,
    build_source_index,
    iter_development_source_records,
    match_source,
    write_outputs,
)


OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".test_outputs" / "historical_development_source_backfill"


def write_source_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "7.1"
    sheet.append(
        [
            "站点",
            "开发部门",
            "开发员",
            "一级类目",
            "关键词",
            "主SKU名称",
            "主SKU",
            "子SKU名称",
            "子SKU",
            "产品类型",
            "开品理由",
            "开发询价",
            None,
            None,
            None,
            None,
            "Shopee菲律宾市场调研",
            None,
            None,
            "Shopee菲律宾成本",
            None,
            None,
        ]
    )
    sheet.append(
        [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "产品规格",
            "供应商链接",
            "供应商名称",
            "商品成本-含税（元）",
            "包装重量(kg)",
            "最低价链接",
            "售价1",
            "月销1",
            "参考单销",
            "稳定期定价（PHP）",
            "一次毛利率",
        ]
    )
    sheet.append(
        [
            "PH",
            "开发部",
            "张三",
            "家居用品",
            "测试关键词",
            "主SKU名",
            "MSKU",
            "子SKU名",
            "SSKU",
            "利润款",
            "开品理由",
            "规格A",
            "https://supplier.example/item",
            "供应商A",
            12.5,
            0.4,
            "https://comp.example/item",
            99,
            300,
            4.5,
            149,
            0.22,
        ]
    )
    workbook.save(path)


def test_reads_development_source_and_writes_backfill_json() -> None:
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_path = OUTPUT_DIR / "source.xlsx"
    write_source_workbook(source_path)

    records = iter_development_source_records(source_path)
    assert len(records) == 1
    assert records[0]["development_inquiry"]["product_spec"] == "规格A"
    assert records[0]["development_inquiry"]["tax_included_cost_rmb"] == 12.5
    assert records[0]["pricing_snapshot"]["reference_daily_sales"] == 4.5
    assert records[0]["pricing_snapshot"]["stable_price"] == 149
    assert records[0]["competitors"][0]["url"] == "https://comp.example/item"

    classification = {
        "records": [
            {
                "country": "PH",
                "main_sku": "MSKU",
                "child_sku": "SSKU",
                "historical_salesperson": "张三",
                "source_reference": {"source_file": "market.xlsx", "source_sheet": "PH精品", "source_row": 3},
            }
        ]
    }
    rows = build_backfill_rows(classification, build_source_index([source_path]))
    summary = write_outputs(rows, OUTPUT_DIR, "20260726")

    rows_json = OUTPUT_DIR / "historical-development-source-backfill-rows-20260726.json"
    payload = json.loads(rows_json.read_text(encoding="utf-8"))
    assert summary["unique_matches"] == 1
    assert payload[0]["match_status"] == "unique"
    assert payload[0]["source"]["development_inquiry"]["supplier_name"] == "供应商A"


def test_dedupes_identical_sources_but_keeps_real_multiple_candidates() -> None:
    key = ("PH", "MSKU", "SSKU")
    base = {
        "country": "PH",
        "main_sku": "MSKU",
        "sub_sku": "SSKU",
        "developer_name": "张三",
        "development_inquiry": {"product_spec": "规格A"},
        "pricing_snapshot": {"stable_price": 149},
        "competitors": [],
        "source_reference": {"source_file": "a.xlsx", "source_sheet": "7.1", "source_row": 3},
    }
    record = {"country": "PH", "main_sku": "MSKU", "child_sku": "SSKU"}

    duplicate = {**base, "source_reference": {"source_file": "a.xlsx", "source_sheet": "7.8", "source_row": 4}}
    assert match_source({key: [base, duplicate]}, record).status == "unique"

    changed = {**base, "development_inquiry": {"product_spec": "规格B"}}
    assert match_source({key: [base, changed]}, record).status == "multiple"
