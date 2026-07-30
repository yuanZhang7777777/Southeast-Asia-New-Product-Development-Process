import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_suffix('.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_selection1_claim_backfill import build_selection1_canonical_package  # noqa: E402


def _row(*, source_row: int, sub_sku: str, reason: str) -> dict:
    return {
        "source_file": "selection1.xlsx",
        "source_sheet": "开发0414期",
        "source_row": source_row,
        "source_type": "history_selection1",
        "batch": "开发0414期",
        "country": "PH",
        "site": "PH",
        "main_sku": "MAIN1",
        "sub_sku": sub_sku,
        "main_sku_name": "主商品",
        "sub_sku_name": "子商品",
        "reason": reason,
        "snapshot": {
            "fields_by_cell": {
                "IT": {"header": "主销售员", "value": "运营A"},
                "IU": {"header": "是否认领", "value": "是"},
                "IV": {"header": "认领单销", "value": 0.5},
                "IW": {"header": "销售反馈总结", "value": "来源反馈"},
                "IX": {"header": "备注", "value": None},
            }
        },
    }


def _claim_group_row(*, source_row: int, sub_sku: str, salesperson: str | None, flag: str, sales: object) -> dict:
    cells = {
        "BW": {"header": "不认领理由", "value": "市场需求量过小"},
        "BY": {"header": "是否认领", "value": flag},
        "BZ": {"header": "认领单销", "value": sales},
    }
    if salesperson is not None:
        cells["BX"] = {"header": "主销售员", "value": salesperson}
    return {
        "source_file": "selection1.xlsx",
        "source_sheet": "开发0526期",
        "source_row": source_row,
        "source_type": "history_selection1",
        "batch": "开发0526期",
        "country": "TH",
        "site": "泰国",
        "main_sku": "LJJ926",
        "sub_sku": sub_sku,
        "main_sku_name": "厨房秤电子秤",
        "sub_sku_name": sub_sku,
        "snapshot": {"fields_by_cell": cells},
    }


def test_canonical_package_excludes_conflicting_rows_and_their_claim_facts() -> None:
    good = _row(source_row=2, sub_sku="GOOD1", reason="理由A")
    conflict_a = _row(source_row=3, sub_sku="DUP1", reason="理由A")
    conflict_b = _row(source_row=4, sub_sku="DUP1", reason="理由B")

    package = build_selection1_canonical_package([good, conflict_a, conflict_b])

    assert [row["sub_sku"] for row in package["archive_rows"]] == ["GOOD1"]
    assert package["counts"] == {
        "raw_rows": 3,
        "archive_rows": 1,
        "claim_facts": 1,
        "claims": 1,
        "rejections": 0,
        "unresolved_groups": 1,
        "unresolved_rows": 2,
        "unresolved_claim_facts": 2,
    }
    assert package["claim_facts"][0]["sub_sku"] == "GOOD1"
    assert package["unresolved"][0]["source_rows"] == [3, 4]


def test_canonical_package_inherits_unique_group_salesperson_for_merged_claim_area() -> None:
    explicit = _claim_group_row(source_row=253, sub_sku="LJJ926A4", salesperson="庞莹莹", flag="是", sales=0.5)
    merged_blank = _claim_group_row(
        source_row=254,
        sub_sku="LJJ926A5",
        salesperson=None,
        flag="否",
        sales="已认领普通款，测试市场情况",
    )

    package = build_selection1_canonical_package([explicit, merged_blank])
    by_sub_sku = {item["sub_sku"]: item for item in package["claim_facts"]}

    assert by_sub_sku["LJJ926A5"]["salesperson_name"] == "庞莹莹"
    assert by_sub_sku["LJJ926A5"]["outcome"] == "reject"
    assert by_sub_sku["LJJ926A5"]["reject_reason"] == "市场需求量过小"
    assert by_sub_sku["LJJ926A5"]["claim_column"] == "inherited_main_sku_group"
