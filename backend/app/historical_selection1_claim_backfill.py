"""选品1 历史期认领事实回填（从档案快照读认领区，绝不建任务/流程/通知）。

- 数据源：source_type=history_selection1 档案行的 snapshot["fields_by_cell"]
  （键=列字母，值={"header","group","value"}，全列保真）。认领区各期列位不同
  （0428~0519 在 BT~BX、0526~0616 在 BW~BZ、0623 在 CC~CF、0414/0421 与旧世代另有列位），
  故按表头包含匹配识别，不依赖列位，也不需重新解析源文件。
- 判定：主销售员空/错误值 → no_claim_info 跳过（历史没认领人就是没认领过，不造数）；
  是否认领 是/认领→claim、否/不认领→reject；其它/空 → 认领单销>0 则 claim，
  否则有不认领理由则 reject，都没有 → ambiguous 跳过。
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
- --revert 只删本模块建的行；被 arrival_record/review_record/stocking_request/
  export_row/plm_arrival_item/listing_sku_binding 引用的行跳过并报数。
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from openpyxl.utils import column_index_from_string
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.field_mapping import normalize_header, number_value, text_value
from app.historical_archive_import import APPLY_ALLOWED_ENVS
from app.historical_central_import import ERROR_VALUES
from app.historical_selection1_import import SOURCE_TYPE
from app.selection2_importer import normalize_claim_result
from app.services import audit

CLAIM_SOURCE_COLUMN = "history_selection1"
AUDIT_ACTION = "history.selection1_claims_backfilled"
REVERT_AUDIT_ACTION = "history.selection1_claims_reverted"
# 表头包含匹配（normalize_header 后），同字段命中多列时取列序最靠前的一列。
FIELD_KEYWORDS = {
    "salesperson": ("主销售员",),
    "claim_flag": ("是否认领",),
    "daily_sales": ("认领单销",),
    "reject_reason": ("不认领理由", "不认领原因"),
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


def claim_fields_from_snapshot(snapshot: dict | None) -> dict[str, Any]:
    """按表头包含匹配从全列快照提取认领区原始值（fields_by_cell 只存非空单元格）。"""
    cells = (snapshot or {}).get("fields_by_cell") or {}
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


def decide_claim(fields: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """返回 (outcome, payload)：outcome ∈ claim/reject/no_claim_info/ambiguous。"""
    salesperson = _clean_text(fields.get("salesperson"))
    if not salesperson:
        return "no_claim_info", None
    result = normalize_claim_result(fields.get("claim_flag"))
    daily_sales = number_value(fields.get("daily_sales"))
    reject_reason = _clean_text(fields.get("reject_reason"))
    if result is None:
        if daily_sales is not None and daily_sales > 0:
            result = "claim"
        elif reject_reason:
            result = "reject"
        else:
            return "ambiguous", None
    payload = {
        "salesperson_name": salesperson,
        "claim_result": result,
        "claim_daily_sales": daily_sales if result == "claim" else None,
        "reject_reason": reject_reason if result == "reject" else None,
    }
    return result, payload


def backfill_selection1_claims(db: Session, *, apply: bool = False, actor: str | None = None) -> dict[str, Any]:
    counts = {"total": 0, "claim": 0, "reject": 0, "ambiguous": 0, "no_claim_info": 0, "skipped_existing": 0}
    by_period: dict[str, dict[str, int]] = {}
    already_backfilled = set(
        db.scalars(
            select(models.SalesClaimForecast.opportunity_id).where(
                models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN
            )
        )
    )
    opportunities = db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.source_type == SOURCE_TYPE)
        .order_by(models.NewProductOpportunity.batch, models.NewProductOpportunity.source_row)
    )
    for opportunity in opportunities:
        counts["total"] += 1
        stats = by_period.setdefault(
            opportunity.batch or "未知期",
            {"rows": 0, "claim": 0, "reject": 0, "ambiguous": 0, "no_claim_info": 0, "skipped_existing": 0},
        )
        stats["rows"] += 1
        if opportunity.id in already_backfilled:
            counts["skipped_existing"] += 1
            stats["skipped_existing"] += 1
            continue
        outcome, payload = decide_claim(claim_fields_from_snapshot(opportunity.snapshot))
        counts[outcome] += 1
        stats[outcome] += 1
        if apply and payload is not None:
            db.add(
                models.SalesClaimForecast(
                    opportunity_id=opportunity.id,
                    source_column=CLAIM_SOURCE_COLUMN,
                    claim_source=CLAIM_SOURCE_COLUMN,
                    **payload,
                )
            )
    created_key = "created" if apply else "would_create"
    report = {created_key: counts["claim"] + counts["reject"], **counts, "by_period": by_period}
    if apply:
        audit(db, AUDIT_ACTION, "sales_claim_forecast", None, report, actor)
        db.flush()
    return report


def revert_selection1_claims(db: Session, actor: str | None = None) -> dict[str, int]:
    claims = list(
        db.scalars(
            select(models.SalesClaimForecast).where(models.SalesClaimForecast.source_column == CLAIM_SOURCE_COLUMN)
        )
    )
    claim_ids = [claim.id for claim in claims]
    referenced: set[str] = set()
    if claim_ids:
        for column in CLAIM_REFERENCE_COLUMNS:
            referenced.update(db.scalars(select(column).where(column.in_(claim_ids))))
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
        description="选品1 历史认领事实回填（从档案快照按表头识别认领区；默认 dry-run，不建任务不发通知不动状态）"
    )
    parser.add_argument("--apply-dev", action="store_true", help="真正写库（受 APPLY_ALLOWED_ENVS 门控）")
    parser.add_argument("--revert", action="store_true", help="删除本模块建的认领行（被子表引用的跳过并报数）")
    parser.add_argument("--actor", default="history_selection1_claim_backfill")
    args = parser.parse_args()

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
        if args.apply_dev:
            db.commit()
        print(json.dumps({"mode": "apply" if args.apply_dev else "dry-run", **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
