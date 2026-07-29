"""选品1 历史期认领事实回填（从档案快照读认领区，绝不建任务/流程/通知）。

- 数据源：source_type=history_selection1 档案行或当前选品1行中的 `historical_selection1`
  快照（键=列字母，值={"header","group","value"}，全列保真）。0414~0721 各期认领区
  使用已核对的固定列位，只有未列位化来源才降级用表头匹配，避免同名表头错读。
- 判定：主销售员空/错误值 → no_claim_info 跳过（历史没认领人就是没认领过，不造数）；
  正数认领单销→claim；明确拒绝/不认领理由→reject；认领单销中的非数字文字作为拒绝理由保留；
  0 和空值均不创建历史认领行。
- 落库：SalesClaimForecast(source_column=claim_source="history_selection1")，
  不建 FlowTask/FlowInstance、不发通知、不动 opportunity.current_status、不动既有认领行。
- 安全自检（2026-07-27 逐点核实）：现行流程消费认领行处均过滤 source_column='platform'，
  本回填行（source_column='history_selection1'，downstream_status=NULL）天然不进任何现行流程：
  * notification_jobs.py:224 刊登/二次调研提醒过滤 source_column='platform'；
    notification_jobs.py:349-351 淘汰提醒按 product_positioning+secondary_research_submitted_at
    过滤，本回填行两字段均为 NULL，不命中；
  * plm_processing.py:135 到货精确匹配过滤 source_column='platform'（且要求
    downstream_status='待到货'并 join 备货导出链路）；
  * services.py:812/992/1145/2672/2913/3304/3366/3646/3812/4131 与
    routers/opportunities.py:345 等消费点同样过滤 source_column='platform'；
  * selection2_importer.replace_source_claims 只删 source_column∈CLAIM_SOURCE_COLUMNS
    （AL:AN 等列段值），不会误删本回填行；
  * historical_plm_arrival_backfill.py:86 历史到货匹配同样要求 source_column='platform'。
- 幂等：opportunity 已有 source_column='history_selection1' 认领行 → skipped_existing。
- 附件：`--evidence-workbook` 只读取已确认的销售反馈/备注列锚定图片；`--upload-evidence`
  才上传既有 OSS 路径，上传失败单独报出且不影响认领事实。
- --revert 只删本模块建的行；被 arrival_record/review_record/stocking_request/
  export_row/plm_arrival_item/listing_sku_binding 引用的行跳过并报数。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.field_mapping import normalize_header, text_value
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_central_import import ERROR_VALUES, sheet_image_anchors
from app.historical_selection1_import import SOURCE_TYPE
from app.oss_storage import upload_claim_evidence_image
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE
from app.selection2_importer import normalize_claim_result
from app.services import audit

CLAIM_SOURCE_COLUMN = "history_selection1"
AUDIT_ACTION = "history.selection1_claims_backfilled"
NORMALIZE_AUDIT_ACTION = "history.selection1_claims_normalized"
EVIDENCE_AUDIT_ACTION = "history.selection1_claim_evidence_backfilled"
REVERT_AUDIT_ACTION = "history.selection1_claims_reverted"
EVIDENCE_BUNDLE_MANIFEST = "evidence_manifest.json"
# 旧表每期的认领区位置不同，必须按已核对的期数列位读取；不能再按最靠前的同名表头猜测。
PERIOD_CLAIM_LAYOUTS = {
    "开发0414期": {"salesperson": "IT", "claim_flag": "IU", "daily_sales": "IV", "feedback_summary": "IW", "note": "IX"},
    "开发0421期": {"salesperson": "DA", "claim_flag": "DB", "daily_sales": "DC", "feedback_summary": "DD", "note": "DE"},
    "开发0428期": {"reject_reason": "BU", "salesperson": "BV", "claim_flag": "BW", "daily_sales": "BX", "feedback_summary": "BY", "note": "BZ"},
    "开发0512期": {"reject_reason": "BU", "salesperson": "BV", "claim_flag": "BW", "daily_sales": "BX", "feedback_summary": "BY", "note": "BZ"},
    "开发0519期": {"reject_reason": "BU", "salesperson": "BV", "claim_flag": "BW", "daily_sales": "BX", "feedback_summary": "BY", "note": "BZ"},
    "开发0526期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0602期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0609期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0616期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0623期": {"reject_reason": "CC", "salesperson": "CD", "claim_flag": "CE", "daily_sales": "CF", "feedback_summary": "CG", "note": "CH"},
    "开发0630期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0707期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0714期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
    "开发0721期": {"reject_reason": "BW", "salesperson": "BX", "claim_flag": "BY", "daily_sales": "BZ", "feedback_summary": "CA", "note": "CB"},
}
# 表头包含匹配只作为未列位化历史行的保底；当前导入范围均应命中上方布局。
FIELD_KEYWORDS = {
    "salesperson": ("主销售员",),
    "claim_flag": ("是否认领",),
    "daily_sales": ("认领单销",),
    "reject_reason": ("不认领理由", "不认领原因"),
    "feedback_summary": ("销售反馈总结", "销售反馈", "反馈总结"),
    "note": ("备注",),
}
# revert 前逐表核对引用，被引用的认领行跳过不删（含 listing_sku_binding 软引用）。
CLAIM_REFERENCE_COLUMNS = (
    models.ArrivalRecord.claim_record_id,
    models.ReviewRecord.claim_record_id,
    models.StockingRequest.claim_record_id,
    models.ExportRow.claim_record_id,
    models.PlmArrivalItem.matched_claim_record_id,
    models.ListingSkuBinding.claim_record_id,
)


def claim_fields_from_snapshot(snapshot: dict | None, business_period: str | None = None) -> dict[str, Any]:
    """按已核对的期数列位读取认领区；无布局才降级为表头匹配。"""
    cells = (snapshot or {}).get("fields_by_cell") or {}
    layout = PERIOD_CLAIM_LAYOUTS.get(business_period or "")
    if layout:
        fields: dict[str, Any] = {"source_columns": layout}
        mismatches: dict[str, str] = {}
        for field, column in layout.items():
            cell = cells.get(column)
            if cell is None:
                fields[field] = None
                continue
            header = normalize_header(cell.get("header"))
            expected = FIELD_KEYWORDS.get(field, ())
            if expected and header and not any(keyword in header for keyword in expected):
                mismatches[field] = f"{column}:{header}"
            fields[field] = cell.get("value")
        if mismatches:
            fields["layout_mismatch"] = mismatches
        return fields

    fields: dict[str, Any] = {}
    for column in sorted(cells, key=column_index_from_string):
        cell = cells[column] or {}
        header = normalize_header(cell.get("header"))
        if not header:
            continue
        for field, keywords in FIELD_KEYWORDS.items():
            if field not in fields and any(keyword in header for keyword in keywords):
                fields[field] = cell.get("value")
    return fields


def _clean_text(value: Any) -> str | None:
    text = text_value(value)
    return None if text in ERROR_VALUES else text


def _strict_number_value(value: Any) -> float | None:
    value = _clean_text(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return None
    return float(text)


def decide_claim(fields: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Return historical claim facts; only a positive numeric daily-sales value is a claim."""
    salesperson = _clean_text(fields.get("salesperson"))
    if not salesperson:
        return "no_claim_info", None

    raw_sales = _clean_text(fields.get("daily_sales"))
    daily_sales = _strict_number_value(fields.get("daily_sales"))
    reject_reason = _clean_text(fields.get("reject_reason"))
    feedback_summary = _clean_text(fields.get("feedback_summary"))
    result = normalize_claim_result(fields.get("claim_flag"))

    if not reject_reason and raw_sales is not None and daily_sales is None:
        reject_reason = raw_sales
    if result == "reject" or reject_reason:
        return "reject", {
            "salesperson_name": salesperson,
            "claim_result": "reject",
            "claim_daily_sales": None,
            "reject_reason": reject_reason,
            "feedback_summary": feedback_summary,
        }
    if daily_sales is None:
        return "unclaimed", None
    if daily_sales == 0:
        return "zero_daily_sales", None
    if daily_sales < 0:
        return "invalid_value", None
    return "claim", {
        "salesperson_name": salesperson,
        "claim_result": "claim",
        "claim_daily_sales": daily_sales,
        "reject_reason": None,
        "feedback_summary": feedback_summary,
    }


def _caigen_claim_facts(snapshot: dict | None) -> list[tuple[str, dict[str, Any] | None, str]]:
    """开发0727期-财根按每个“销售员* / 预估单销*”槽位恢复多人认领。"""
    cells = (snapshot or {}).get("fields_by_cell") or {}
    columns = sorted(cells, key=column_index_from_string)
    facts: list[tuple[str, dict[str, Any] | None, str]] = []
    for index, column in enumerate(columns):
        cell = cells[column] or {}
        header = normalize_header(cell.get("header"))
        salesperson = _clean_text(cell.get("value"))
        if "销售员" not in header or not salesperson or "侵权" in salesperson:
            continue
        sales_column = None
        for next_column in columns[index + 1:]:
            next_header = normalize_header((cells[next_column] or {}).get("header"))
            if "销售员" in next_header:
                break
            if "预估单销" in next_header or "认领单销" in next_header:
                sales_column = next_column
                break
        fields = {
            "salesperson": salesperson,
            "daily_sales": (cells.get(sales_column) or {}).get("value") if sales_column else None,
            "source_columns": {"salesperson": column, **({"daily_sales": sales_column} if sales_column else {})},
        }
        outcome, payload = decide_claim(fields)
        facts.append((outcome, payload, column))
    return facts


def claim_facts_from_snapshot(
    snapshot: dict | None,
    business_period: str | None,
) -> list[tuple[str, dict[str, Any] | None, str]]:
    if business_period == "开发0727期-财根":
        return _caigen_claim_facts(snapshot)
    fields = claim_fields_from_snapshot(snapshot, business_period)
    if fields.get("layout_mismatch"):
        return [("layout_mismatch", None, "layout")]
    outcome, payload = decide_claim(fields)
    source_column = str((fields.get("source_columns") or {}).get("salesperson") or "fallback")
    return [(outcome, payload, source_column)]


def _historical_snapshot(opportunity: models.NewProductOpportunity) -> tuple[dict[str, Any] | None, str | None]:
    snapshot = dict(opportunity.snapshot or {})
    if opportunity.source_type == SOURCE_TYPE:
        return snapshot, snapshot.get("business_period") or opportunity.batch
    nested = snapshot.get("historical_selection1")
    if isinstance(nested, dict):
        return nested, nested.get("business_period") or opportunity.batch
    return None, None


def _claim_exists(
    existing: list[models.SalesClaimForecast],
    payload: dict[str, Any],
) -> bool:
    for claim in existing:
        if _claim_matches(claim, payload):
            return True
    return False


def _claim_matches(claim: models.SalesClaimForecast, payload: dict[str, Any]) -> bool:
    return (
        (claim.salesperson_name or "") == (payload.get("salesperson_name") or "")
        and claim.claim_result == payload.get("claim_result")
        and claim.claim_daily_sales == payload.get("claim_daily_sales")
        and (claim.reject_reason or "") == (payload.get("reject_reason") or "")
    )


def _claim_note(
    opportunity: models.NewProductOpportunity,
    snapshot: dict[str, Any],
    source_column: str,
) -> str:
    reference = snapshot.get("source_reference") or {}
    return json.dumps(
        {
            "history_source": {
                "source_file": reference.get("source_file") or opportunity.source_file,
                "source_sheet": reference.get("source_sheet") or opportunity.source_sheet,
                "source_row": reference.get("source_row") or opportunity.source_row,
                "business_period": snapshot.get("business_period") or opportunity.batch,
                "claim_column": source_column,
            },
            "source_note": _clean_text(claim_fields_from_snapshot(snapshot, snapshot.get("business_period") or opportunity.batch).get("note")),
            "evidence_images": [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _owner_mapping_status(db: Session, name: str) -> str:
    rows = db.execute(
        select(models.RoleMapping, models.User)
        .outerjoin(models.User, models.User.id == models.RoleMapping.user_id)
        .where(
            models.RoleMapping.name == name,
            models.RoleMapping.role == "operator",
            models.RoleMapping.enabled.is_(True),
        )
    ).all()
    mappings = [
        mapping
        for mapping, user in rows
        if (mapping.user_id or mapping.dingtalk_user_id)
        and (mapping.user_id is None or (user is not None and user.enabled))
    ]
    if not mappings:
        return "unmapped"
    if len({mapping.dingtalk_user_id for mapping in mappings}) > 1:
        return "ambiguous"
    return "mapped"


def _owner_mapping_report(db: Session, owner_names: set[str]) -> dict[str, Any]:
    rows = [{"salesperson_name": name, "status": _owner_mapping_status(db, name)} for name in sorted(owner_names)]
    return {
        "mapped": sum(row["status"] == "mapped" for row in rows),
        "unmapped": sum(row["status"] == "unmapped" for row in rows),
        "ambiguous": sum(row["status"] == "ambiguous" for row in rows),
        "rows": rows,
    }


def _claim_note_payload(claim: models.SalesClaimForecast, opportunity: models.NewProductOpportunity) -> dict[str, Any]:
    try:
        payload = json.loads(claim.note or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    history_source = payload.get("history_source")
    if not isinstance(history_source, dict):
        history_source = {}
    payload["history_source"] = {
        "source_file": history_source.get("source_file") or opportunity.source_file,
        "source_sheet": history_source.get("source_sheet") or opportunity.source_sheet,
        "source_row": history_source.get("source_row") or opportunity.source_row,
        "business_period": history_source.get("business_period") or opportunity.batch,
        "claim_column": history_source.get("claim_column"),
    }
    if not isinstance(payload.get("evidence_images"), list):
        payload["evidence_images"] = []
    return payload


def _claim_evidence_columns(period: str | None) -> set[str]:
    layout = PERIOD_CLAIM_LAYOUTS.get(period or "") or {}
    return {column for field, column in layout.items() if field in {"feedback_summary", "note"}}


def write_selection1_claim_evidence_bundle(
    bundle_path: Path,
    evidence_by_source: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, int]:
    """Persist selected source images so a development server need not receive the full workbook."""
    entries: list[dict[str, Any]] = []
    members: dict[str, bytes] = {}
    for (sheet, row), images in sorted(evidence_by_source.items()):
        for image in images:
            data = image.get("data")
            column = str(image.get("column") or "").upper()
            ext = str(image.get("ext") or "png").lower().lstrip(".")
            if not isinstance(data, bytes) or not data or not re.fullmatch(r"[A-Z]{1,3}", column):
                continue
            if not re.fullmatch(r"[a-z0-9]{1,8}", ext):
                ext = "png"
            member = f"images/{hashlib.sha1(data).hexdigest()}.{ext}"
            members.setdefault(member, data)
            entries.append(
                {
                    "source_sheet": sheet,
                    "source_row": row,
                    "source_column": column,
                    "ext": ext,
                    "member": member,
                }
            )
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(EVIDENCE_BUNDLE_MANIFEST, json.dumps({"version": 1, "images": entries}, ensure_ascii=False))
        for member, data in members.items():
            archive.writestr(member, data)
    return {"images": len(entries), "source_rows": len(evidence_by_source)}


def read_selection1_claim_evidence_bundle(bundle_path: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """Load a bundle written above; reject any record without an exact source coordinate."""
    loaded: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    with zipfile.ZipFile(bundle_path) as archive:
        payload = json.loads(archive.read(EVIDENCE_BUNDLE_MANIFEST).decode("utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("images"), list):
            raise ValueError("unsupported evidence bundle")
        for item in payload["images"]:
            if not isinstance(item, dict):
                raise ValueError("invalid evidence bundle item")
            sheet = _clean_text(item.get("source_sheet"))
            row = item.get("source_row")
            column = str(item.get("source_column") or "").upper()
            ext = str(item.get("ext") or "").lower().lstrip(".")
            member = str(item.get("member") or "")
            if (
                not sheet
                or not isinstance(row, int)
                or row < 1
                or not re.fullmatch(r"[A-Z]{1,3}", column)
                or not re.fullmatch(r"[a-z0-9]{1,8}", ext)
                or not re.fullmatch(r"images/[0-9a-f]{40}\.[a-z0-9]{1,8}", member)
            ):
                raise ValueError("invalid evidence bundle trace")
            loaded[(sheet, row)].append({"column": column, "data": archive.read(member), "ext": ext})
    return dict(loaded)


def _historical_claim_rows(db: Session) -> list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]]:
    return list(
        db.execute(
            select(models.SalesClaimForecast, models.NewProductOpportunity)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
            .where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN)
            .order_by(models.NewProductOpportunity.source_sheet, models.NewProductOpportunity.source_row)
        ).all()
    )


def selection1_claim_evidence_manifest(
    db: Session,
    workbook_path: Path,
) -> tuple[dict[tuple[str, int], list[dict[str, Any]]], dict[str, Any]]:
    """Read only feedback/note images for existing historical claim source rows."""
    requested: dict[tuple[str, int], set[str]] = defaultdict(set)
    unconfigured_sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, int, str | None]] = set()

    def add_source(sheet: str | None, row: Any, period: str | None) -> None:
        if not sheet or not isinstance(row, int):
            return
        source_key = (sheet, row, period)
        if source_key in seen_sources:
            return
        seen_sources.add(source_key)
        columns = _claim_evidence_columns(period)
        if not columns:
            unconfigured_sources.append({"source_sheet": sheet, "source_row": row, "business_period": period})
            return
        requested[(sheet, row)].update(columns)

    for claim, opportunity in _historical_claim_rows(db):
        payload = _claim_note_payload(claim, opportunity)
        source = payload["history_source"]
        add_source(
            _clean_text(source.get("source_sheet")),
            source.get("source_row"),
            _clean_text(source.get("business_period")),
        )

    # Dry-runs run before historical claim rows exist, so derive the same source keys from archive snapshots.
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type.in_((SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE)))
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        snapshot, period = _historical_snapshot(opportunity)
        if snapshot is None or not period:
            continue
        if not any(payload is not None for _, payload, _ in claim_facts_from_snapshot(snapshot, period)):
            continue
        reference = snapshot.get("source_reference") or {}
        add_source(
            _clean_text(reference.get("source_sheet") or opportunity.source_sheet),
            reference.get("source_row") or opportunity.source_row,
            _clean_text(reference.get("business_period") or period),
        )

    manifest: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    with zipfile.ZipFile(workbook_path) as archive:
        rows_by_sheet: dict[str, dict[int, set[str]]] = defaultdict(dict)
        for (sheet, row), columns in requested.items():
            rows_by_sheet[sheet][row] = columns
        for sheet, rows in rows_by_sheet.items():
            for row, anchors in sheet_image_anchors(archive, sheet).items():
                allowed_columns = rows.get(row)
                if not allowed_columns:
                    continue
                for index, data, ext in anchors:
                    column = get_column_letter(index)
                    if column in allowed_columns:
                        manifest[(sheet, row)].append({"column": column, "data": data, "ext": ext})
    return dict(manifest), {
        "target_rows": len(requested),
        "candidate_images": sum(len(images) for images in manifest.values()),
        "unconfigured_sources": unconfigured_sources,
    }


def backfill_selection1_claim_evidence(
    db: Session,
    evidence_by_source: dict[tuple[str, int], list[dict[str, Any]]],
    *,
    apply: bool = False,
    actor: str | None = None,
) -> dict[str, Any]:
    """Attach existing OSS evidence to historical claims without creating workflow records."""
    report: dict[str, Any] = {
        "claims": 0,
        "candidate_images": 0,
        "attached": 0,
        "would_attach": 0,
        "already_attached": 0,
        "skipped_non_evidence_column": 0,
        "skipped_missing_trace": 0,
        "failed_uploads": [],
    }
    for claim, opportunity in _historical_claim_rows(db):
        report["claims"] += 1
        payload = _claim_note_payload(claim, opportunity)
        source = payload["history_source"]
        sheet = _clean_text(source.get("source_sheet"))
        row = source.get("source_row")
        period = _clean_text(source.get("business_period"))
        if not sheet or not isinstance(row, int):
            report["skipped_missing_trace"] += 1
            continue
        allowed_columns = _claim_evidence_columns(period)
        for source_image in evidence_by_source.get((sheet, row), []):
            report["candidate_images"] += 1
            column = str(source_image.get("column") or "").upper()
            if column not in allowed_columns:
                report["skipped_non_evidence_column"] += 1
                continue
            data = source_image.get("data")
            ext = str(source_image.get("ext") or "png").lower().lstrip(".")
            if not isinstance(data, bytes) or not data:
                report["failed_uploads"].append({"source_sheet": sheet, "source_row": row, "source_column": column, "reason": "empty_image"})
                continue
            name = f"{sheet}!{column}{row}.{ext}"
            if any(isinstance(image, dict) and image.get("name") == name for image in payload["evidence_images"]):
                report["already_attached"] += 1
                continue
            if not apply:
                report["would_attach"] += 1
                continue
            digest = hashlib.sha1(data).hexdigest()[:16]
            try:
                url = upload_claim_evidence_image(data, ext, opportunity.id, digest)
            except Exception as exc:
                report["failed_uploads"].append({"source_sheet": sheet, "source_row": row, "source_column": column, "reason": type(exc).__name__})
                continue
            if not url:
                report["failed_uploads"].append({"source_sheet": sheet, "source_row": row, "source_column": column, "reason": "oss_unavailable"})
                continue
            payload["evidence_images"].append(
                {
                    "name": name,
                    "type": f"image/{'jpeg' if ext in {'jpg', 'jpeg'} else ext}",
                    "url": url,
                    "source_sheet": sheet,
                    "source_row": row,
                    "source_column": column,
                }
            )
            claim.note = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            report["attached"] += 1
    if apply and report["attached"]:
        audit(db, EVIDENCE_AUDIT_ACTION, "sales_claim_forecast", None, report, actor)
        db.flush()
    return report


def backfill_selection1_claims(db: Session, *, apply: bool = False, actor: str | None = None) -> dict[str, Any]:
    counts = {
        "total": 0,
        "claim": 0,
        "reject": 0,
        "zero_daily_sales": 0,
        "unclaimed": 0,
        "invalid_value": 0,
        "no_claim_info": 0,
        "layout_mismatch": 0,
        "skipped_existing": 0,
    }
    by_period: dict[str, dict[str, int]] = {}
    owner_names: set[str] = set()
    existing_by_opportunity: dict[str, list[models.SalesClaimForecast]] = defaultdict(list)
    for claim in db.scalars(
        select(models.SalesClaimForecast).where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN)
    ):
        existing_by_opportunity[claim.opportunity_id].append(claim)
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type.in_((SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE)))
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        snapshot, period = _historical_snapshot(opportunity)
        if snapshot is None or not period:
            continue
        counts["total"] += 1
        stats = by_period.setdefault(
            period,
            {
                "rows": 0,
                "claim": 0,
                "reject": 0,
                "zero_daily_sales": 0,
                "unclaimed": 0,
                "invalid_value": 0,
                "no_claim_info": 0,
                "layout_mismatch": 0,
                "skipped_existing": 0,
            },
        )
        stats["rows"] += 1
        for outcome, payload, source_column in claim_facts_from_snapshot(snapshot, period):
            if payload and payload.get("salesperson_name"):
                owner_names.add(str(payload["salesperson_name"]))
            if payload is not None and _claim_exists(existing_by_opportunity[opportunity.id], payload):
                counts["skipped_existing"] += 1
                stats["skipped_existing"] += 1
                continue
            counts[outcome] += 1
            stats[outcome] += 1
            if apply and payload is not None:
                claim = models.SalesClaimForecast(
                    opportunity_id=opportunity.id,
                    source_column=CLAIM_SOURCE_COLUMN,
                    claim_source=CLAIM_SOURCE_COLUMN,
                    note=_claim_note(opportunity, snapshot, source_column),
                    **payload,
                )
                db.add(claim)
                existing_by_opportunity[opportunity.id].append(claim)
    created_key = "created" if apply else "would_create"
    report = {
        created_key: counts["claim"] + counts["reject"],
        **counts,
        "by_period": by_period,
        "owner_mappings": _owner_mapping_report(db, owner_names),
    }
    if apply:
        audit(db, AUDIT_ACTION, "sales_claim_forecast", None, report, actor)
        db.flush()
    return report


def normalize_selection1_claims(db: Session, *, apply: bool = False, actor: str | None = None) -> dict[str, int]:
    """Correct stale historical facts only when none of them are already referenced by a flow."""
    existing_by_opportunity: dict[str, list[models.SalesClaimForecast]] = defaultdict(list)
    for claim in db.scalars(
        select(models.SalesClaimForecast).where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN)
    ):
        existing_by_opportunity[claim.opportunity_id].append(claim)

    operations: list[tuple[str, models.SalesClaimForecast, dict[str, Any] | None, str | None, models.NewProductOpportunity, dict[str, Any]]] = []
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type.in_((SOURCE_TYPE, CURRENT_SELECTION1_SOURCE_TYPE)))
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        snapshot, period = _historical_snapshot(opportunity)
        if snapshot is None or not period:
            continue
        expected = [
            (payload, source_column)
            for _, payload, source_column in claim_facts_from_snapshot(snapshot, period)
            if payload is not None
        ]
        remaining = list(existing_by_opportunity.get(opportunity.id, []))
        missing: list[tuple[dict[str, Any], str]] = []
        for payload, source_column in expected:
            match_index = next((index for index, claim in enumerate(remaining) if _claim_matches(claim, payload)), None)
            if match_index is None:
                missing.append((payload, source_column))
            else:
                remaining.pop(match_index)
        for claim, (payload, source_column) in zip(remaining, missing):
            operations.append(("update", claim, payload, source_column, opportunity, snapshot))
        for claim in remaining[len(missing):]:
            operations.append(("delete", claim, None, None, opportunity, snapshot))

    referenced_ids = _referenced_claim_ids(db, [claim for _, claim, _, _, _, _ in operations])
    if referenced_ids:
        return {"updated": 0, "deleted_extra": 0, "skipped_referenced": len(referenced_ids)}

    report = {"updated": 0, "deleted_extra": 0, "skipped_referenced": 0}
    if not apply:
        for operation, *_ in operations:
            report["updated" if operation == "update" else "deleted_extra"] += 1
        return report

    for operation, claim, payload, source_column, opportunity, snapshot in operations:
        if operation == "delete":
            db.delete(claim)
            report["deleted_extra"] += 1
            continue
        previous_note = _claim_note_payload(claim, opportunity)
        claim.salesperson_name = payload.get("salesperson_name") if payload else None
        claim.claim_result = payload.get("claim_result") if payload else None
        claim.claim_daily_sales = payload.get("claim_daily_sales") if payload else None
        claim.reject_reason = payload.get("reject_reason") if payload else None
        claim.feedback_summary = payload.get("feedback_summary") if payload else None
        claim.claim_source = CLAIM_SOURCE_COLUMN
        note = json.loads(_claim_note(opportunity, snapshot, source_column or "fallback"))
        note["evidence_images"] = previous_note.get("evidence_images") or []
        claim.note = json.dumps(note, ensure_ascii=False, separators=(",", ":"))
        report["updated"] += 1
    if report["updated"] or report["deleted_extra"]:
        audit(db, NORMALIZE_AUDIT_ACTION, "sales_claim_forecast", None, report, actor)
        db.flush()
    return report


def _referenced_claim_ids(db: Session, claims: list[models.SalesClaimForecast]) -> set[str]:
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return set()
    referenced: set[str] = set()
    for column in CLAIM_REFERENCE_COLUMNS:
        referenced.update(value for value in db.scalars(select(column).where(column.in_(claim_ids))) if value)
    return referenced


def revert_selection1_claims(db: Session, actor: str | None = None) -> dict[str, int]:
    claims = list(
        db.scalars(
            select(models.SalesClaimForecast).where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN)
        )
    )
    referenced = _referenced_claim_ids(db, claims)
    deleted = skipped = 0
    for claim in claims:
        if claim.id in referenced:
            skipped += 1
            continue
        db.delete(claim)
        deleted += 1
    report = {"reverted_claims": deleted, "skipped_referenced": skipped}
    audit(db, REVERT_AUDIT_ACTION, "sales_claim_forecast", None, report, actor)
    db.flush()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="选品1 历史认领事实回填（按各期已核对列位；默认 dry-run，不建任务不发通知不动状态）"
    )
    parser.add_argument("--apply-dev", action="store_true", help="真正写库（受 APPLY_ALLOWED_ENVS 门控）")
    parser.add_argument("--revert", action="store_true", help="删除本模块建的认领行（被子表引用的跳过并报数）")
    evidence_source = parser.add_mutually_exclusive_group()
    evidence_source.add_argument("--evidence-workbook", type=Path, help="源选品1 XLSX；只扫描已回填认领的反馈/备注图片")
    evidence_source.add_argument("--evidence-bundle", type=Path, help="由源 XLSX 提取的认领证据包，用于开发机上传")
    parser.add_argument("--write-evidence-bundle", type=Path, help="将 --evidence-workbook 的命中图片写为小型证据包")
    parser.add_argument("--upload-evidence", action="store_true", help="上传证据图片到既有 OSS（必须同时 --apply-dev）")
    parser.add_argument("--actor", default="history_selection1_claim_backfill")
    args = parser.parse_args()

    if args.upload_evidence and not args.apply_dev:
        parser.error("--upload-evidence requires --apply-dev")
    if args.write_evidence_bundle and not args.evidence_workbook:
        parser.error("--write-evidence-bundle requires --evidence-workbook")
    if args.upload_evidence and not (args.evidence_workbook or args.evidence_bundle):
        parser.error("--upload-evidence requires --evidence-workbook or --evidence-bundle")

    from app.config import get_settings
    from app.db import SessionLocal

    if args.apply_dev or args.revert:
        settings = get_settings()
        if settings.app_env not in APPLY_ALLOWED_ENVS:
            raise SystemExit(f"apply blocked: app_env={settings.app_env}")
    with SessionLocal() as db:
        if args.revert:
            report = revert_selection1_claims(db, actor=args.actor)
            db.commit()
            print(json.dumps({"mode": "revert", **report}, ensure_ascii=False, indent=2))
            return
        report = backfill_selection1_claims(db, apply=args.apply_dev, actor=args.actor)
        if args.evidence_workbook:
            manifest, scan_report = selection1_claim_evidence_manifest(db, args.evidence_workbook)
            report["evidence"] = {
                "scan": scan_report,
                **backfill_selection1_claim_evidence(
                    db,
                    manifest,
                    apply=args.upload_evidence,
                    actor=args.actor,
                ),
            }
            if args.write_evidence_bundle:
                report["evidence"]["bundle"] = write_selection1_claim_evidence_bundle(args.write_evidence_bundle, manifest)
        elif args.evidence_bundle:
            manifest = read_selection1_claim_evidence_bundle(args.evidence_bundle)
            report["evidence"] = {
                "scan": {"target_rows": len(manifest), "candidate_images": sum(len(images) for images in manifest.values())},
                **backfill_selection1_claim_evidence(
                    db,
                    manifest,
                    apply=args.upload_evidence,
                    actor=args.actor,
                ),
            }
        if args.apply_dev:
            db.commit()
        print(json.dumps({"mode": "apply" if args.apply_dev else "dry-run", **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
