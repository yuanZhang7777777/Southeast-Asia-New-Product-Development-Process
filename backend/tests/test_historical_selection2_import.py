import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection2.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402

from app.historical_selection2_import import (  # noqa: E402
    SOURCE_TYPE,
    inspect_selection2_workbook,
    parse_historical_selection2_row,
    parse_selection2_workbook,
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".test_outputs" / "historical_selection2_import"


def _row(values_by_column: dict[int, object]) -> tuple[object | None, ...]:
    row = [None] * 48
    for column, value in values_by_column.items():
        row[column - 1] = value
    return tuple(row)


def test_parse_row_creates_claims_only_for_numeric_daily_sales() -> None:
    parsed = parse_historical_selection2_row(
        _row(
            {
                2: "SPU-1",
                3: "SKU-1",
                5: "商品A",
                6: "红色",
                38: "冯卓宏",
                39: "是",
                40: 2,
                41: "李桂敏",
                42: "市场销量不足",
                43: "赵钰婷",
                44: "1.5",
            }
        ),
        source_file="selection2.xlsx",
        source_sheet="7.27期",
        source_row=2,
    )

    assert parsed is not None
    assert parsed["source_type"] == SOURCE_TYPE
    assert parsed["current_status"] == "historical_archive"
    assert parsed["main_sku"] == "SPU-1"
    assert parsed["sub_sku"] == "SKU-1"
    assert parsed["task_policy"] == "none"
    assert [(claim["salesperson_name"], claim["claim_daily_sales"], claim["source_column"]) for claim in parsed["claims"]] == [
        ("冯卓宏", 2.0, "AL:AN"),
        ("赵钰婷", 1.5, "AQ:AR"),
    ]
    assert parsed["rejected_sources"] == [
        {"salesperson_name": "李桂敏", "raw_value": "市场销量不足", "source_column": "AO:AP"}
    ]


def test_parse_row_with_infringement_marker_keeps_archive_only() -> None:
    parsed = parse_historical_selection2_row(
        _row(
            {
                2: "SPU-2",
                3: "SKU-2",
                5: "商品B",
                38: "冯卓宏",
                40: 2,
                45: "侵权商品",
            }
        ),
        source_file="selection2.xlsx",
        source_sheet="7.27期",
        source_row=3,
    )

    assert parsed is not None
    assert parsed["claims"] == []
    assert parsed["operator_match_policy"] == "skip"
    assert parsed["archive_only_reason"] == "infringing_product"
    assert parsed["snapshot"]["fields_by_cell"]["AS"]["value"] == "侵权商品"


def test_parse_empty_claim_area_is_historical_unclaimed_not_pending_task() -> None:
    parsed = parse_historical_selection2_row(
        _row({2: "SPU-3", 3: "SKU-3", 5: "商品C"}),
        source_file="selection2.xlsx",
        source_sheet="7.27期",
        source_row=4,
    )

    assert parsed is not None
    assert parsed["claims"] == []
    assert parsed["operator_match_policy"] == "none"
    assert parsed["task_policy"] == "none"
    assert parsed["archive_only_reason"] == "historical_unclaimed"


def test_parse_workbook_reports_latest_period_and_rows() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "selection2-history.xlsx"
    workbook = Workbook()
    old = workbook.active
    old.title = "5.26期"
    _append_headers(old)
    old.append(_row({2: "OLD", 3: "OLD-A", 5: "旧商品"}))
    latest = workbook.create_sheet("7.27期")
    _append_headers(latest)
    latest.append(_row({2: "NEW", 3: "NEW-A", 5: "新商品", 41: "销售A", 42: 1}))
    note = workbook.create_sheet("说明")
    note.append(["说明"])
    workbook.save(path)

    report = parse_selection2_workbook(path)

    assert report["latest_sheet"] == "7.27期"
    assert report["latest_period"] == "0727"
    assert report["row_count"] == 2
    assert report["sheets"] == [
        {"sheet": "5.26期", "period": "0526", "rows": 1, "skipped": 0},
        {"sheet": "7.27期", "period": "0727", "rows": 1, "skipped": 0},
    ]
    assert report["skipped_sheets"] == [{"sheet": "说明", "reason": "非期数sheet"}]


def test_inspect_workbook_reports_unreadable_zip_without_writing() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    broken = OUTPUT_DIR / "broken.xlsx"
    broken.write_bytes(b"PK\x03\x04not-a-complete-xlsx")

    report = inspect_selection2_workbook(broken)

    assert report["readable"] is False
    assert report["sheets"] == []
    assert "could not open workbook" in report["error"]


def _append_headers(sheet) -> None:
    headers = [None] * 48
    for column_index, title in {
        2: "SPU",
        3: "SKU",
        5: "产品名称",
        6: "产品规格属性（材质、大小、颜色）",
        38: "开发表格认领情况--主销售员",
        39: "是否认领",
        40: "认领单销",
        41: "销售员1",
        42: "认领单销/不认领原因",
        43: "销售员2",
        44: "认领单销/不认领原因",
        45: "销售员3",
        46: "认领单销/不认领原因",
    }.items():
        headers[column_index - 1] = title
    sheet.append(headers)
