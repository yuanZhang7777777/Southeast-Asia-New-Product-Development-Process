import sys
import uuid
from pathlib import Path

from openpyxl import Workbook

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.historical_plm_excel_backfill import build_plm_excel_history  # noqa: E402


GROUP_EIGHT = "集团八部"


def test_plm_excel_history_keeps_latest_owner_and_marks_multi_salesperson() -> None:
    tmp_path = Path("outputs/test_tmp") / f"plm_excel_{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    first = tmp_path / "plm-2026-07-12.xlsx"
    second = tmp_path / "plm-2026-07-13.xlsx"
    write_plm(first, "2026-07-12", "销售A")
    write_plm(second, "2026-07-13", "销售B")

    result = build_plm_excel_history(
        [("2026-07-12", first), ("2026-07-13", second)],
        bloc_name=GROUP_EIGHT,
        failed_dates=["2026-07-14"],
    )

    assert result["summary"]["downloaded_workbook_count"] == 2
    assert result["summary"]["item_count"] == 2
    assert result["summary"]["unique_key_count"] == 1
    assert result["summary"]["multi_salesperson_key_count"] == 1
    assert result["summary"]["failed_date_count"] == 1
    assert result["matches"][0]["salesperson_name"] == "销售B"
    assert result["matches"][0]["arrival_date"] == "2026-07-13"
    assert result["hard_conflicts"][0]["salespeople"] == ["销售A", "销售B"]


def write_plm(path: Path, date_text: str, salesperson: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["商品名称", "子SKU", "主SKU", "销售员", "集团", "海外仓", "国家", "最后一次入库时间", "首次上架时间"])
    sheet.append(["商品", " SUB-1 ", "MAIN-1", salesperson, GROUP_EIGHT, "菲律宾仓", "菲律宾", f"{date_text} 10:00:00", f"{date_text} 00:00:00"])
    workbook.save(path)
