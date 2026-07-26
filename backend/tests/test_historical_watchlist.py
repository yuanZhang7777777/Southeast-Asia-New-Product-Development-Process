from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
from re import sub
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_watchlist import build_historical_watchlist


def test_resets_malformed_sheet_dimension_before_reading_rows(tmp_path: Path) -> None:
    source = tmp_path / "history-TH.xlsx"
    build_workbook(source, [("MAIN-1", "SUB-1", {"TH": ("张三", 1)})])
    rewrite_dimension(source, "A1:A2")

    records = build_historical_watchlist([source])

    assert [(record["country"], record["child_sku"]) for record in records] == [("TH", "SUB-1")]


def test_excludes_rejections_and_fragile_goods_notes(tmp_path: Path) -> None:
    source = tmp_path / "history-TH.xlsx"
    build_workbook(
        source,
        [
            ("MAIN-1", "SUB-REJECT", {"TH": ("不认领", 1)}),
            ("MAIN-2", "SUB-FRAGILE", {"TH": ("易碎品", 1)}),
            ("MAIN-3", "SUB-NOTE", {"TH": ("市场需求量过小", 1)}),
            ("MAIN-3", "SUB-OK", {"TH": ("李四", None)}),
        ],
    )

    records = build_historical_watchlist([source])

    assert [(record["child_sku"], record["historical_claimants"]) for record in records] == [("SUB-OK", ["李四"])]


def test_merges_duplicate_country_child_keys_and_preserves_ambiguous_main_skus(tmp_path: Path) -> None:
    source = tmp_path / "history-VN.xlsx"
    build_workbook(
        source,
        [
            (" main-a ", " sku-1 ", {"VN": ("张三", 1)}),
            ("MAIN-B", "SKU-1", {"VN": ("李四", 2)}),
        ],
    )

    records = build_historical_watchlist([source])

    assert records[0]["country"] == "VN"
    assert records[0]["child_sku"] == "SKU-1"
    assert records[0]["main_skus"] == ["MAIN-A", "MAIN-B"]
    assert records[0]["historical_claimants"] == ["张三", "李四"]
    assert len(records[0]["source_references"]) == 2


def test_discovers_country_column_and_keeps_source_traceability(tmp_path: Path) -> None:
    source = tmp_path / "history-PH.xlsx"
    build_workbook(source, [(" main-p ", " sub-p ", {"PH": ("王小明", 3)})], sheet_name="6.30")

    record = build_historical_watchlist([source])[0]

    assert record["country"] == "PH"
    assert record["child_sku"] == "SUB-P"
    assert record["main_skus"] == ["MAIN-P"]
    assert record["historical_claimants"] == ["王小明"]
    assert record["source_references"] == [
        {
            "source_file": source.name,
            "source_sha256": sha256(source.read_bytes()).hexdigest(),
            "source_sheet": "6.30",
            "source_row": 3,
            "source_column": 3,
        }
    ]


def test_preserves_two_plausible_names_from_one_claimant_cell(tmp_path: Path) -> None:
    source = tmp_path / "history-PH.xlsx"
    build_workbook(source, [("MAIN", "SUB", {"PH": ("施情芳 殷国琳", 1)})])

    assert build_historical_watchlist([source])[0]["historical_claimants"] == ["施情芳", "殷国琳"]


def test_uses_only_the_matching_country_column_for_each_source_workbook(tmp_path: Path) -> None:
    source = tmp_path / "history-TH.xlsx"
    build_workbook(source, [("MAIN", "SUB-TH", {"TH": ("张三", 1), "VN": ("李四", 1)})])

    records = build_historical_watchlist([source])

    assert [(record["country"], record["historical_claimants"]) for record in records] == [("TH", ["张三"])]



def test_uses_claim_column_country_when_source_file_has_no_country(tmp_path: Path) -> None:
    source = tmp_path / "财根团队新品开发表.xlsx"
    build_workbook(source, [("MAIN", "SUB-PH", {"PH": ("王小明", 3), "TH": ("李四", 2)})])

    records = build_historical_watchlist([source])

    assert [(record["country"], record["child_sku"], record["historical_claimants"]) for record in records] == [
        ("PH", "SUB-PH", ["王小明"]),
        ("TH", "SUB-PH", ["李四"]),
    ]

def build_workbook(path: Path, rows: list[tuple[str, str, dict[str, tuple[object, object]]]], sheet_name: str = "history") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    countries = list(dict.fromkeys(country for _, _, claims in rows for country in claims))
    worksheet.append(["主SKU", "子SKU"] + [item for country in countries for item in (country, None)])
    worksheet.append(["主SKU", "子SKU"] + [item for _ in countries for item in ("认领人", "预估单销")])
    for main_sku, child_sku, claims in rows:
        worksheet.append([main_sku, child_sku] + [item for country in countries for item in claims.get(country, (None, None))])
    workbook.save(path)


def rewrite_dimension(path: Path, dimension: str) -> None:
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["xl/worksheets/sheet1.xml"] = sub(
        rb'<dimension ref="[^"]+"/>', f'<dimension ref="{dimension}"/>'.encode(), files["xl/worksheets/sheet1.xml"]
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
