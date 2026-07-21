from io import BytesIO
from urllib.error import URLError

import pytest
from openpyxl import Workbook

from app.config import Settings
from app import erp_product_list


HEADERS = [
    "sku",
    "主SKU",
    "产品体积长(cm)",
    "产品体积宽(cm)",
    "产品体积高(cm)",
    "产品包装后体积长(cm)",
    "产品包装后体积宽(cm)",
    "产品包装后体积高(cm)",
]


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(HEADERS)
    for row in rows:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_calculate_unit_volume_prefers_complete_packaging_dimensions() -> None:
    row = {
        "产品体积长(cm)": 1,
        "产品体积宽(cm)": 1,
        "产品体积高(cm)": 1,
        "产品包装后体积长(cm)": "10.1",
        "产品包装后体积宽(cm)": " 9.4 ",
        "产品包装后体积高(cm)": "1.4",
    }

    assert erp_product_list.calculate_unit_volume(row) == 0.000132916


def test_calculate_unit_volume_falls_back_to_complete_product_dimensions() -> None:
    row = {
        "产品体积长(cm)": "6.7",
        "产品体积宽(cm)": "5.3",
        "产品体积高(cm)": "2.5",
        "产品包装后体积长(cm)": "10",
        "产品包装后体积宽(cm)": "",
        "产品包装后体积高(cm)": "2",
    }

    assert erp_product_list.calculate_unit_volume(row) == 0.000088775


def test_calculate_unit_volume_returns_none_when_both_dimension_groups_are_incomplete() -> None:
    row = {
        "产品体积长(cm)": 6.7,
        "产品体积宽(cm)": 5.3,
        "产品体积高(cm)": 0,
        "产品包装后体积长(cm)": 10.1,
        "产品包装后体积宽(cm)": "bad",
        "产品包装后体积高(cm)": 1.4,
    }

    assert erp_product_list.calculate_unit_volume(row) is None


def test_parse_product_list_workbook_returns_requested_skus_with_manual_fallbacks() -> None:
    content = _workbook_bytes(
        [
            ["GSHWAC225ND", "MAIN-1", 1, 1, 1, "10.1", "9.4", "1.4"],
            ["SH-OD-492-BL", "MAIN-2", "6.7", "5.3", "2.5", 10, None, 2],
            ["NOT-REQUESTED", "MAIN-3", 9, 9, 9, 9, 9, 9],
        ]
    )

    assert erp_product_list.parse_product_list_workbook(
        content, ["GSHWAC225ND", "SH-OD-492-BL", "MISSING"]
    ) == {
        "GSHWAC225ND": 0.000132916,
        "SH-OD-492-BL": 0.000088775,
        "MISSING": None,
    }


def test_fetch_product_volumes_uses_open_login_and_new_successful_product_list_export(monkeypatch) -> None:
    calls: list[tuple[str, dict, dict]] = []
    list_calls = 0

    def fake_post_json(url: str, body: dict, headers: dict | None = None) -> dict:
        nonlocal list_calls
        calls.append((url, body, headers or {}))
        if url == "http://erp.example/open/system/innerOpen/login":
            return {"success": True, "data": {"accessToken": "temporary-token"}}
        if url == "http://erp.example/product-list":
            return {"success": True, "data": "任务创建成功"}
        assert url == "http://erp.example/download-list"
        list_calls += 1
        if list_calls == 1:
            return {"success": True, "data": {"list": [{"id": "old", "source": "productList", "status": "success"}]}}
        return {
            "success": True,
            "data": {
                "list": [
                    {"id": "old", "source": "productList", "status": "success", "downloadUrl": "old.xlsx"},
                    {"id": "failed", "source": "productList", "status": "failed", "downloadUrl": "failed.xlsx"},
                    {"id": "wrong", "source": "inventory", "status": "success", "downloadUrl": "wrong.xlsx"},
                    {
                        "id": "ready",
                        "source": "productList",
                        "status": "success",
                        "downloadUrl": "http://files.example/products.xlsx",
                    },
                ]
            },
        }

    downloaded: list[str] = []

    def fake_download_bytes(url: str) -> bytes:
        downloaded.append(url)
        return _workbook_bytes([["GSHWAC225ND", "MAIN-1", 1, 1, 1, 10.1, 9.4, 1.4]])

    monkeypatch.setattr(erp_product_list, "_post_json", fake_post_json)
    monkeypatch.setattr(erp_product_list, "_download_bytes", fake_download_bytes)

    result = erp_product_list.fetch_product_volumes(
        ["GSHWAC225ND", "MISSING"],
        Settings(
            erp_login_url="http://erp.example/open/system/innerOpen/login",
            erp_product_list_url="http://erp.example/product-list",
            erp_download_list_url="http://erp.example/download-list",
            erp_username="erp-user",
            erp_password="erp-password",
        ),
    )

    login_call, initial_list_call, create_call, poll_call = calls
    assert login_call == (
        "http://erp.example/open/system/innerOpen/login",
        {"username": "erp-user", "password": "erp-password"},
        {},
    )
    assert initial_list_call[1] == {"pageNum": 1, "pageSize": 20}
    assert initial_list_call[2] == {"Authorization": "temporary-token"}
    assert create_call[1] == {
        "skuList": ["GSHWAC225ND", "MISSING"],
        "isfile": "0",
        "portionFieldSet": (
            "sku,mainsku,pretendlength,pretendwidth,pretendlheight,"
            "actualLength,actualWidth,actualHeight"
        ),
    }
    assert create_call[2] == {"Authorization": "temporary-token"}
    assert poll_call[1] == {"pageNum": 1, "pageSize": 20}
    assert poll_call[2] == {"Authorization": "temporary-token"}
    assert downloaded == ["http://files.example/products.xlsx"]
    assert result == {"GSHWAC225ND": 0.000132916, "MISSING": None}


def test_fetch_product_volumes_returns_manual_fallback_without_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        erp_product_list,
        "_post_json",
        lambda *_args, **_kwargs: pytest.fail("network must not be called without ERP configuration"),
    )

    assert erp_product_list.fetch_product_volumes(["SKU-1"], Settings()) == {"SKU-1": None}


def test_http_errors_do_not_expose_credentials_tokens_or_sensitive_urls(monkeypatch) -> None:
    secret_url = "http://erp.example/path?password=erp-password&token=temporary-token"

    def fake_urlopen(*_args, **_kwargs):
        raise URLError("erp-user erp-password temporary-token")

    monkeypatch.setattr(erp_product_list, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        erp_product_list._post_json(
            secret_url,
            {"username": "erp-user", "password": "erp-password"},
            {"Authorization": "temporary-token"},
        )

    error = str(exc_info.value)
    assert "erp-user" not in error
    assert "erp-password" not in error
    assert "temporary-token" not in error
    assert secret_url not in error
    assert exc_info.value.__cause__ is None
