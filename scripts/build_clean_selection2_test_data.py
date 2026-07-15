from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


OUTPUT = Path("outputs/test_sources/选品2-财根机会池-干净测试数据.xlsx")


HEADERS = {
    2: "SPU",
    3: "SKU",
    5: "产品名称",
    6: "产品规格属性（材质、大小、颜色）",
    7: "图片",
    8: "进价",
    22: "进货链接",
    38: "开发表格认领情况--主销售员",
    39: "是否认领",
    40: "认领单销",
    41: "销售员1",
    42: "认领单销/不认领原因",
    43: "销售员2",
    44: "认领单销/不认领原因",
    45: "销售员3",
    46: "认领单销/不认领原因",
    47: "销售员4",
    48: "认领单销/不认领原因",
}

ROWS = [
    {
        2: "CGPOOL001",
        3: "CGPOOL001-A",
        5: "厨房抽屉分隔收纳盒",
        6: "透明大号",
        7: "https://img.alicdn.com/imgextra/i1/test-clean-selection2-001.jpg",
        8: 8.6,
        22: "https://detail.1688.com/offer/clean-selection2-001.html",
    },
    {
        2: "CGPOOL002",
        3: "CGPOOL002-B",
        5: "车载后备箱折叠收纳箱",
        6: "黑色 55L",
        7: "https://img.alicdn.com/imgextra/i1/test-clean-selection2-002.jpg",
        8: 23.5,
        22: "https://detail.1688.com/offer/clean-selection2-002.html",
    },
    {
        2: "CGPOOL003",
        3: "CGPOOL003-C",
        5: "浴室免打孔毛巾架",
        6: "银色双杆",
        7: "https://img.alicdn.com/imgextra/i1/test-clean-selection2-003.jpg",
        8: 12.8,
        22: "https://detail.1688.com/offer/clean-selection2-003.html",
    },
]


def build(path: Path = OUTPUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "5.26期"
    header_row = [None] * 48
    for index, title in HEADERS.items():
        header_row[index - 1] = title
    worksheet.append(header_row)
    for item in ROWS:
        row = [None] * 48
        for index, value in item.items():
            row[index - 1] = value
        worksheet.append(row)
    workbook.save(path)
    return path


if __name__ == "__main__":
    output = build()
    assert output.exists()
    print(output)
