"""FineBI 周数据自动拉取：登录 -> 创建导出 -> 下载 -> 校验表头 -> 入库。

协议来自生产自动化实测：
1. GET /webroot/decision/login 取登录页，解析页面里需要回传的字段（hidden input / Dec.system origin），
   再向同一 URL POST JSON（username/password + validity/keepAlive 等常见字段）。
   成功判定 = HTTP 200 且会话新增 FineBI 认证 Cookie；失败时把登录页关键片段写进异常便于运维排查。
2. POST /webroot/decision/v5/design/report/data/export?reportId=..&entryType=6&operationId=..，
   body = 配置文件（FINEBI_PAYLOAD_FILE）里的 JSON。创建成功也可能 Content-Length: 0，
   真正成败以下载结果为准。
3. GET /webroot/decision/v5/design/report/data/export/download/<operationId>?link=&sessionID=..&form=true，
   成功判定 = 返回 Excel/ZIP 文件头（PK..）而非 HTML，且 openpyxl 能打开、表头与既有 finebi_live 一致。
operationId / sessionID 每次运行用 uuid 重新生成，绝不写死。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date
from http.cookiejar import CookieJar
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.historical_finebi_import import (
    KEY_COLUMNS,
    METRIC_COLUMNS,
    apply_plan,
    build_plan,
    period_window,
    read_finebi_periods,
)
from app.historical_monitoring_sources import text_value

LOGIN_PATH = "/webroot/decision/login"
EXPORT_PATH = "/webroot/decision/v5/design/report/data/export"
DOWNLOAD_PATH = "/webroot/decision/v5/design/report/data/export/download"
DEFAULT_TARGET_DIR = Path("outputs/historical_data/finebi_live")
WEEK_LABEL_PATTERN = re.compile(r"\d{4}-\d{4}")
REQUIRED_HEADER_COLUMNS = (*KEY_COLUMNS, *METRIC_COLUMNS)
REQUIRED_SETTINGS = (
    ("FINEBI_BASE_URL", "finebi_base_url"),
    ("FINEBI_USERNAME", "finebi_username"),
    ("FINEBI_PASSWORD", "finebi_password"),
    ("FINEBI_REPORT_ID", "finebi_report_id"),
    ("FINEBI_PAYLOAD_FILE", "finebi_payload_file"),
)
XLSX_MAGIC = b"PK\x03\x04"


class FineBIPullError(RuntimeError):
    """FineBI 协议层失败（登录 / 导出 / 下载 / 文件校验）。"""


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def snippet(self, limit: int = 300) -> str:
        text = re.sub(r"\s+", " ", self.body.decode("utf-8", errors="replace")).strip()
        return text[:limit] or "空"


class UrllibSession:
    """带 Cookie 会话的最小 HTTP 客户端；测试中整体替换为假会话，绝不发起真实请求。"""

    def __init__(self) -> None:
        self.jar = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self.jar))

    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> HttpResponse:
        request = Request(url, data=data, headers=headers or {}, method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return HttpResponse(
                    int(response.status),
                    {key.lower(): value for key, value in response.headers.items()},
                    response.read(),
                )
        except HTTPError as exc:
            return HttpResponse(
                int(exc.code),
                {key.lower(): value for key, value in (exc.headers or {}).items()},
                exc.read() or b"",
            )
        except (URLError, TimeoutError) as exc:
            raise FineBIPullError(f"FineBI 请求失败：{url} 不可达（{type(exc).__name__}）") from exc

    def cookie_names(self) -> set[str]:
        return {cookie.name for cookie in self.jar}


def validate_week_label(week_label: str, year: int) -> str:
    label = (week_label or "").strip()
    if not WEEK_LABEL_PATTERN.fullmatch(label):
        raise ValueError("week_label 格式应为 MMDD-MMDD，例如 0723-0729")
    try:
        period_window(label, year)
    except ValueError as exc:
        raise ValueError(f"week_label 不是合法日期区间：{label}") from exc
    return label


def pull_week(
    week_label: str,
    *,
    settings: Settings | None = None,
    target_dir: Path | str | None = None,
    session: UrllibSession | None = None,
    year: int | None = None,
) -> Path:
    settings = settings or get_settings()
    label = validate_week_label(week_label, year or date.today().year)
    _require_configuration(settings)
    payload_bytes = _load_payload(settings.finebi_payload_file)
    session = session or UrllibSession()
    base = settings.finebi_base_url.strip().rstrip("/")
    operation_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    _login(session, base, settings)
    _create_export(session, base, settings.finebi_report_id.strip(), operation_id, payload_bytes)
    content = _download_export(session, base, operation_id, session_id)
    _validate_headers(content, label)

    directory = Path(target_dir) if target_dir else DEFAULT_TARGET_DIR
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{label}.xlsx"
    if target.exists():
        os.replace(target, target.with_name(f"{target.name}.bak"))
    partial = target.with_name(f"{target.name}.part")
    partial.write_bytes(content)
    os.replace(partial, target)
    return target


def pull_and_import(
    db: Session,
    week_label: str,
    imported_by: str | None = None,
    *,
    settings: Settings | None = None,
    target_dir: Path | str | None = None,
    session: UrllibSession | None = None,
    year: int | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    year = year or date.today().year
    directory = Path(target_dir) if target_dir else DEFAULT_TARGET_DIR
    path = pull_week(week_label, settings=settings, target_dir=directory, session=session, year=year)
    label = path.stem
    finebi, periods, skipped = read_finebi_periods(directory, year, include_period=label)
    plan = build_plan(db, {}, finebi, year)
    counts = apply_plan(db, plan, source_label=path.name, imported_by=imported_by)
    return {
        "week_label": label,
        "file": str(path),
        "periods": periods,
        "excluded_periods": skipped,
        "summary": plan["summary"],
        "apply_counts": counts,
    }


def _require_configuration(settings: Settings) -> None:
    missing = [name for name, attribute in REQUIRED_SETTINGS if not str(getattr(settings, attribute)).strip()]
    if missing:
        raise ValueError(f"FineBI 拉取配置不完整，缺少：{', '.join(missing)}")


def _load_payload(payload_file: str) -> bytes:
    path = Path(payload_file)
    if not path.is_file():
        raise ValueError(f"FINEBI_PAYLOAD_FILE 不存在：{path}")
    content = path.read_bytes()
    try:
        json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"FINEBI_PAYLOAD_FILE 不是合法 JSON：{path}") from exc
    return content


def _login(session: UrllibSession, base: str, settings: Settings) -> None:
    login_url = f"{base}{LOGIN_PATH}"
    page = session.request("GET", login_url)
    if page.status != 200:
        raise FineBIPullError(f"FineBI 登录页获取失败：HTTP {page.status}，响应片段：{page.snippet()}")
    page_html = page.body.decode("utf-8", errors="replace")
    fields = _login_page_fields(page_html)
    fields.pop("username", None)
    fields.pop("password", None)
    payload: dict[str, object] = {
        "validity": -1,
        "keepAlive": False,
        "sso": False,
        "encrypted": False,
        **fields,
        "username": settings.finebi_username,
        "password": settings.finebi_password,
    }
    before = session.cookie_names()
    response = session.request(
        "POST",
        login_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    new_cookies = sorted(session.cookie_names() - before)
    if response.status != 200 or not new_cookies:
        raise FineBIPullError(
            f"FineBI 登录失败：HTTP {response.status}，新增认证 Cookie：{new_cookies or '无'}，"
            f"登录响应片段：{response.snippet()}；登录页片段：{_page_snippet(page_html)}"
        )


def _login_page_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input\b[^>]*>", html, flags=re.IGNORECASE):
        if not re.search(r"type\s*=\s*[\"']hidden[\"']", tag, flags=re.IGNORECASE):
            continue
        name = _tag_attribute(tag, "name")
        if name:
            fields[name] = _tag_attribute(tag, "value")
    origin = re.search(r"[\"']origin[\"']\s*:\s*[\"']([^\"']+)[\"']", html)
    if origin:
        fields.setdefault("origin", origin.group(1))
    return fields


def _tag_attribute(tag: str, name: str) -> str:
    match = re.search(rf"{name}\s*=\s*[\"']([^\"']*)[\"']", tag, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _page_snippet(html: str, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", html).strip()[:limit] or "空"


def _create_export(
    session: UrllibSession, base: str, report_id: str, operation_id: str, payload_bytes: bytes
) -> None:
    params = urlencode({"reportId": report_id, "entryType": 6, "operationId": operation_id})
    response = session.request(
        "POST",
        f"{base}{EXPORT_PATH}?{params}",
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
    )
    if response.status != 200:
        raise FineBIPullError(f"FineBI 创建导出失败：HTTP {response.status}，响应片段：{response.snippet()}")
    # 生产实测：创建成功也可能返回 Content-Length: 0，因此空 body 不算失败，成败以下载结果为准。


def _download_export(session: UrllibSession, base: str, operation_id: str, session_id: str) -> bytes:
    params = urlencode({"link": "", "sessionID": session_id, "form": "true"})
    response = session.request("GET", f"{base}{DOWNLOAD_PATH}/{operation_id}?{params}")
    content_type = response.headers.get("content-type", "")
    if (
        response.status != 200
        or "text/html" in content_type.lower()
        or not response.body.startswith(XLSX_MAGIC)
    ):
        raise FineBIPullError(
            f"FineBI 下载失败：HTTP {response.status}，Content-Type：{content_type or '未知'}，"
            f"返回的不是 Excel/ZIP 文件；响应片段：{response.snippet()}"
        )
    return response.body


def _validate_headers(content: bytes, week_label: str) -> None:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise FineBIPullError(f"FineBI 下载的 {week_label} 文件无法被 openpyxl 打开：{exc}") from exc
    try:
        seen: list[str] = []
        for worksheet in workbook.worksheets:
            first_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
            headers = {text_value(value) for value in first_row if text_value(value)}
            if all(column in headers for column in REQUIRED_HEADER_COLUMNS):
                return
            seen.extend(sorted(headers))
        raise FineBIPullError(
            f"FineBI 下载的 {week_label} 表头与既有 finebi_live 文件不一致，不入库："
            f"需要 {list(REQUIRED_HEADER_COLUMNS)}，实际 {seen or '无表头'}"
        )
    finally:
        workbook.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="FineBI 周数据自动拉取（默认仅下载，不入库）")
    parser.add_argument("--week-label", required=True, help="周标签，形如 0723-0729")
    parser.add_argument("--import-db", action="store_true", help="下载后解析并写入数据库")
    parser.add_argument("--imported-by", default="finebi_auto_pull")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.finebi_auto_pull_enabled:
        raise SystemExit("FINEBI_AUTO_PULL_ENABLED=false，请先在部署环境开启")
    if args.import_db:
        from app.db import SessionLocal

        with SessionLocal() as db:
            report = pull_and_import(db, args.week_label, imported_by=args.imported_by, settings=settings)
            db.commit()
    else:
        report = {"week_label": args.week_label, "file": str(pull_week(args.week_label, settings=settings))}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
