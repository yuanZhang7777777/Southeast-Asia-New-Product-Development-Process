from __future__ import annotations

import json
import math
from copy import deepcopy
from collections import defaultdict
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import assignment_rules, models, schemas
from app.config import Settings
from app.dingtalk_card_sender import DingTalkCardSender, NewProductTodoCard, masked_dingtalk_user_id
from app.excel_images import PUBLIC_UPLOAD_PREFIX, UPLOADED_SOURCES_ROOT
from app.field_mapping import normalize_header, number_value
from app.oss_storage import read_oss_object_by_public_url
from app.site_codes import normalize_site_code
from app.workflow_status import (
    CLAIM_LISTING_OBSERVATION,
    CLAIM_RESULT_CLAIM,
    CLAIM_RESULT_REJECT,
    CLAIM_DISABLED,
    CLAIM_WAITING_ARRIVAL,
    CLAIM_WAITING_EXPORT,
    CLAIM_WAITING_LISTING,
    CLAIM_WAITING_SECONDARY_RESEARCH,
    CLAIM_WAITING_STOCKING_REQUEST,
    CLAIM_STOCKING_PAUSED,
    OPPORTUNITY_ASSIGNED,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_CLAIM_SUBMITTED,
    OPPORTUNITY_CONFIRMED_NOT_CLAIM,
    OPPORTUNITY_DISABLED,
    OPPORTUNITY_OPEN_CLAIM_POOL,
    OPPORTUNITY_PENDING_ASSIGNMENT,
    OPPORTUNITY_READY_FOR_STOCKING,
    OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
    REVIEW_APPROVED,
    REVIEW_CONFIRMED_NOT_CLAIM,
    REVIEW_PENDING,
    REVIEW_RETURNED_FOR_SUPPLEMENT,
    TASK_COMPLETED,
    TASK_PENDING,
)

EXCEL_TIMEZONE = timezone(timedelta(hours=8))
SUPERVISOR_NAME = "练玉君"

REVIEW_TO_OPPORTUNITY_STATUS = {
    REVIEW_APPROVED: OPPORTUNITY_READY_FOR_STOCKING,
    REVIEW_CONFIRMED_NOT_CLAIM: OPPORTUNITY_CONFIRMED_NOT_CLAIM,
    REVIEW_RETURNED_FOR_SUPPLEMENT: OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
}


def current_business_period_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() - 3) % 7)


def next_complete_business_period_start(day: date) -> date:
    return current_business_period_start(day) + timedelta(days=7)


def validate_selectable_period_start(period_start: date, today: date) -> None:
    if period_start.weekday() != 3:
        raise ValueError("period_start must be a Thursday")
    current = current_business_period_start(today)
    if period_start not in {current, current + timedelta(days=7)}:
        raise ValueError("period_start must be the current or next business period")


def initial_observation_period_dates(first_period_start: date) -> list[tuple[date, date]]:
    return [
        (first_period_start + timedelta(days=7 * index), first_period_start + timedelta(days=7 * index + 6))
        for index in range(4)
    ]

# Canonical v1 central schema, frozen from 东南亚海外仓新品表-PH.xlsx / 6.23 through 开发是否接受核价结果.
CENTRAL_TRACEABILITY_COLUMNS = [
    ("A", "站点"),
    ("B", "开发部门"),
    ("C", "开发员"),
    ("D", "一级类目"),
    ("E", "关键词"),
    ("F", "产品图片"),
    ("G", "主SKU名称"),
    ("H", "主SKU"),
    ("I", "子SKU名称"),
    ("J", "子SKU"),
    ("K", "产品类型 / 引流or绑定or利润"),
    ("L", "开品理由"),
    ("M", "开发询价 / 产品规格"),
    ("N", "产品外包装"),
    ("O", "末道包材"),
    ("P", "供应商链接"),
    ("Q", "供应商名称"),
    ("R", "商品成本-含税（元）"),
    ("S", "预估单销*30的加购运费"),
    ("T", "单子sku的加购运费分摊"),
    ("U", "包装重量(kg)"),
    ("V", "产品包装后体积长(cm)"),
    ("W", "产品包装后体积宽(cm)"),
    ("X", "产品包装后体积高(cm)"),
    ("Y", "包装后体积"),
    ("Z", "Shopee菲律宾市场调研 / 最低价链接"),
    ("AA", "售价1(PHP）"),
    ("AB", "月销1"),
    ("AC", "月销最高链接链接1"),
    ("AD", "售价2(PHP）"),
    ("AE", "月销2"),
    ("AF", "月销次高链接链接2"),
    ("AG", "售价(PHP）"),
    ("AH", "月销"),
    ("AI", "月销第三高链接链接3"),
    ("AJ", "售价(PHP）"),
    ("AK", "月销"),
    ("AL", "新晋链接"),
    ("AM", "售价3(PHP）"),
    ("AN", "月销3"),
    ("AO", "参考单销"),
    ("AP", "稳定期定价 （PHP）"),
    ("AQ", "一次毛利额\n（PHP）"),
    ("AR", "一次毛利额\n（人民币）"),
    ("AS", "稳定期利润率"),
    ("AT", "预估单销"),
    ("AU", "推广期定价"),
    ("AV", "推广期利润率"),
    ("AW", "Shopee菲律宾成本 / 稳定期总成本（PHP）（含头程+平台费+基础设施）"),
    ("AX", "推广期总成本（PHP）（含头程+平台费+基础设施）"),
    ("AY", "头程费用（元）"),
    ("AZ", "菲律宾汇率"),
    ("BA", "港口"),
    ("BB", "头程标准"),
    ("BC", "包材费"),
    ("BD", "尾程运费收入（PHP）"),
    ("BE", "国内仓库人力成本"),
    ("BF", "国外仓库人力成本"),
    ("BG", "退款"),
    ("BH", "其他公司资金成本"),
    ("BI", "仓储费"),
    ("BJ", "库损"),
    ("BK", "营销费"),
    ("BL", "平台佣金率"),
    ("BM", "交易手续费率"),
    ("BN", "基础设施费（PHP）"),
    ("BO", "汇总 / 总预估单销"),
    ("BP", "预估备货金额"),
    ("BQ", "预估备货量"),
    ("BR", "备货天数"),
    ("BS", "预估备货体积"),
    ("BT", "海空判断 / 1pc空运头程费"),
    ("BU", "空海运差额"),
    ("BV", "预估毛利额-空海运差额"),
    ("BW", "PH物流方式"),
    ("BX", "空运备货量"),
    ("BY", "供应链核/报价 / 采购  核价人"),
    ("BZ", "核价意见"),
    ("CA", "采购建议报价"),
    ("CB", "开发是否接受核价结果"),
]

CENTRAL_TRACEABILITY_HEADERS = [header for _, header in CENTRAL_TRACEABILITY_COLUMNS]
PRODUCT_IMAGE_COLUMN_INDEX = CENTRAL_TRACEABILITY_HEADERS.index("产品图片")
PRODUCT_IMAGE_COLUMN_LETTER = get_column_letter(PRODUCT_IMAGE_COLUMN_INDEX + 1)
PRODUCT_IMAGE_MAX_WIDTH = 96
PRODUCT_IMAGE_MAX_HEIGHT = 72
CENTRAL_COLUMN_BY_HEADER = {header: column for column, header in CENTRAL_TRACEABILITY_COLUMNS}

TRACEABILITY_PLATFORM_HEADERS = [
    "来源表",
    "来源Sheet",
    "来源行号",
    "导入批次",
    "销售员",
    "认领结果",
    "认领单销",
    "不认领理由",
    "销售反馈总结",
    "主管复核状态",
    "主管复核意见",
    "认领首次创建时间",
    "认领最后更新时间",
    "导出批次ID",
    "导出人",
    "导出时间",
    "导出文件名",
    "导出范围",
]

CENTRAL_FIELD_ALIASES = {
    "站点": ["站点", "国家"],
    "国家": ["站点", "国家"],
    "开发部门": ["部门", "开发部门"],
    "产品类型 / 引流or绑定or利润": ["产品类型", "引流or绑定or利润"],
    "开发询价 / 产品规格": ["开发询价 / 产品规格", "产品规格", "开发询价"],
    "供应商链接": ["供应商链接", "进货链接"],
    "商品成本-含税（元）": ["商品成本-含税（元）", "进价", "成本价"],
    "Shopee菲律宾市场调研 / 最低价链接": ["最低价链接"],
    "售价1(PHP）": ["售价1", "售价1(PHP）"],
    "月销最高链接链接1": ["月销最高链接链接1", "most orders链接"],
    "售价2(PHP）": ["售价2", "售价2(PHP）"],
    "月销次高链接链接2": ["月销次高链接链接2"],
    "售价(PHP）": ["售价(PHP）"],
    "售价3(PHP）": ["售价3", "售价3(PHP）"],
    "稳定期定价 （PHP）": ["稳定期定价 （PHP）", "参考定价 （THB）", "参考定价（THB）", "稳定期参考定价 （VND）"],
    "一次毛利额\n（PHP）": ["一次毛利额\n（PHP）", "一次毛利额\n（THB）", "一次毛利额（VND）"],
    "稳定期利润率": ["稳定期利润率", "一次毛利率"],
    "Shopee菲律宾成本 / 稳定期总成本（PHP）（含头程+平台费+基础设施）": ["稳定期总成本（PHP）（含头程+平台费+基础设施）", "稳定期总成本（THB）（含头程+平台费+基础设施）", "稳定期总成本（VND）（含头程+平台费+基础设施）"],
    "推广期总成本（PHP）（含头程+平台费+基础设施）": ["推广期总成本（PHP）（含头程+平台费+基础设施）", "推广期总成本（THB）（含头程+平台费+基础设施）", "推广期总成本（VND）（含头程+平台费+基础设施）"],
    "菲律宾汇率": ["菲律宾汇率", "泰国汇率", "越南汇率"],
    "尾程运费收入（PHP）": ["尾程运费收入（PHP）", "尾程运费收入（THB）", "尾程运费收入（VND）"],
    "国外仓库人力成本": ["国外仓库人力成本", "国外订单操作费"],
    "平台佣金率": ["平台佣金率", "平台佣金率（含技术服务费）"],
    "基础设施费（PHP）": ["基础设施费（PHP）", "基础设施费（VND）", "基础设施"],
    "汇总 / 总预估单销": ["总预估单销", "销售备货单销"],
    "海空判断 / 1pc空运头程费": ["1pc空运头程费"],
    "供应链核/报价 / 采购  核价人": ["采购 核价人", "采购  核价人", "采购 / 核价人"],
}


def audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str | None,
    detail: dict,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> None:
    db.add(
        models.AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            actor_name=actor_name,
            actor_user_id=actor_user_id,
        )
    )


def create_opportunity(db: Session, payload: schemas.OpportunityCreate) -> models.NewProductOpportunity:
    item = models.NewProductOpportunity(**payload.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        query = select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == payload.source_type,
            models.NewProductOpportunity.source_file == payload.source_file,
            models.NewProductOpportunity.source_sheet == payload.source_sheet,
            models.NewProductOpportunity.source_row == payload.source_row,
        )
        existing = db.scalar(query)
        if existing is None:
            raise
        return existing
    db.add(
        models.SourceRecordSnapshot(
            opportunity_id=item.id,
            source_file=item.source_file,
            source_sheet=item.source_sheet,
            source_row=item.source_row,
            column_range="source_row",
            payload=payload.snapshot or payload.model_dump(),
        )
    )
    audit(db, "opportunity.created", "new_product_opportunity", item.id, {"main_sku": item.main_sku, "sub_sku": item.sub_sku})
    return item


OPPORTUNITY_UPDATE_FIELDS = (
    "main_sku",
    "sub_sku",
    "main_sku_name",
    "sub_sku_name",
    "site",
    "country",
    "category_level1",
    "developer_department",
    "developer_name",
    "keyword",
    "product_type",
    "reason",
    "image_url",
    "current_status",
)

EDITABLE_OPPORTUNITY_STATUSES = {
    OPPORTUNITY_PENDING_ASSIGNMENT,
    OPPORTUNITY_OPEN_CLAIM_POOL,
    OPPORTUNITY_ASSIGNED,
    OPPORTUNITY_CLAIM_SUBMITTED,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
    OPPORTUNITY_READY_FOR_STOCKING,
    OPPORTUNITY_CONFIRMED_NOT_CLAIM,
}

OPPORTUNITY_FIELD_COLUMNS = {
    "site": "A",
    "developer_department": "B",
    "developer_name": "C",
    "category_level1": "D",
    "keyword": "E",
    "image_url": "F",
    "main_sku_name": "G",
    "main_sku": "H",
    "sub_sku_name": "I",
    "sub_sku": "J",
    "product_type": "K",
    "reason": "L",
}
OPPORTUNITY_COLUMN_FIELDS = {column: field for field, column in OPPORTUNITY_FIELD_COLUMNS.items()}


def update_opportunity(
    db: Session,
    opportunity_id: str,
    payload: schemas.OpportunityUpdateRequest,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.NewProductOpportunity:
    reason = _clean_text(payload.edit_reason)
    if not reason:
        raise ValueError("edit reason is required")
    opportunity = db.get(models.NewProductOpportunity, opportunity_id)
    if opportunity is None:
        raise LookupError("opportunity not found")

    before: dict[str, object] = {}
    after: dict[str, object] = {}
    values = payload.model_dump(exclude_unset=True)
    for field in OPPORTUNITY_UPDATE_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if isinstance(value, str):
            value = value.strip()
        if field in {"main_sku", "sub_sku"} and not value:
            raise ValueError(f"{field} is required")
        old_value = getattr(opportunity, field)
        if old_value == value:
            continue
        if field == "current_status":
            _validate_edited_opportunity_status(db, opportunity, value)
        before[field] = old_value
        after[field] = value
        setattr(opportunity, field, value)

    source_updates = values.get("source_cells") or {}
    changed_source_before, changed_source_after = _update_opportunity_source_cells(opportunity, source_updates)
    if changed_source_before:
        before["source_cells"] = changed_source_before
        after["source_cells"] = changed_source_after

    synced_fields = {OPPORTUNITY_FIELD_COLUMNS[field]: after[field] for field in OPPORTUNITY_FIELD_COLUMNS if field in after}
    if synced_fields:
        _update_opportunity_source_cells(opportunity, synced_fields, validate_columns=False)

    if before:
        audit(
            db,
            "opportunity.updated",
            "new_product_opportunity",
            opportunity.id,
            {"before": before, "after": after, "reason": reason},
            actor_name,
            actor_user_id,
        )
    return opportunity


def _validate_edited_opportunity_status(db: Session, opportunity: models.NewProductOpportunity, status: str) -> None:
    if status not in EDITABLE_OPPORTUNITY_STATUSES:
        raise ValueError("invalid editable status")
    if status in {OPPORTUNITY_PENDING_ASSIGNMENT, OPPORTUNITY_OPEN_CLAIM_POOL}:
        return
    claim = latest_platform_submission(db, opportunity.id)
    if status == OPPORTUNITY_CLAIM_SUBMITTED and (not claim or claim.claim_result != CLAIM_RESULT_CLAIM):
        raise ValueError("claim submission status requires a claim submission")
    if status == OPPORTUNITY_CLAIM_REJECTED and (not claim or claim.claim_result != CLAIM_RESULT_REJECT):
        raise ValueError("not-claim status requires a not-claim submission")
    if status == OPPORTUNITY_ASSIGNED:
        task = db.scalar(
            select(models.FlowTask.id)
            .join(models.FlowInstance)
            .where(
                models.FlowInstance.opportunity_id == opportunity.id,
                models.FlowTask.task_type == "sales_claim",
                models.FlowTask.status == TASK_PENDING,
            )
        )
        if not task:
            raise ValueError("assigned status requires a pending sales claim task")
    if status in {OPPORTUNITY_RETURNED_FOR_SUPPLEMENT, OPPORTUNITY_READY_FOR_STOCKING, OPPORTUNITY_CONFIRMED_NOT_CLAIM}:
        review = latest_review(db, opportunity.id)
        required_review = {
            OPPORTUNITY_RETURNED_FOR_SUPPLEMENT: REVIEW_RETURNED_FOR_SUPPLEMENT,
            OPPORTUNITY_READY_FOR_STOCKING: REVIEW_APPROVED,
            OPPORTUNITY_CONFIRMED_NOT_CLAIM: REVIEW_CONFIRMED_NOT_CLAIM,
        }[status]
        if not review or review.review_status != required_review:
            raise ValueError(f"{status} status requires a matching review record")


def _update_opportunity_source_cells(
    opportunity: models.NewProductOpportunity,
    updates: dict[str, object],
    validate_columns: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    if not updates:
        return {}, {}
    snapshot = deepcopy(opportunity.snapshot or {})
    cells = dict(snapshot.get("cells") or {})
    fields_by_column = dict(snapshot.get("fields_by_column") or {})
    headers_by_column = dict(snapshot.get("headers_by_column") or {})
    fields_by_header = dict(snapshot.get("fields_by_header") or {})
    pricing_snapshot = dict(snapshot.get("pricing_snapshot") or {})
    allowed = set(snapshot.get("allowed_columns") or cells or fields_by_column or headers_by_column)
    normalized_updates = {str(column).strip().upper(): value for column, value in updates.items()}
    invalid = sorted(column for column in normalized_updates if validate_columns and column not in allowed)
    if invalid:
        raise ValueError(f"source columns are not editable: {', '.join(invalid)}")
    header_owners: dict[str, str] = {}
    for source_column, source_headers in headers_by_column.items():
        if isinstance(source_headers, str):
            source_headers = [source_headers]
        for source_header in source_headers:
            header_owners.setdefault(normalize_header(source_header), source_column)

    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for column, submitted_value in normalized_updates.items():
        if isinstance(submitted_value, (dict, list, tuple, set)):
            raise ValueError(f"source column {column} must be a scalar value")
        old_value = fields_by_column.get(column, cells.get(column))
        value = _coerce_edited_source_value(submitted_value, old_value)
        if old_value == value:
            continue
        before[column] = old_value
        after[column] = value
        cells[column] = value
        fields_by_column[column] = value
        headers = headers_by_column.get(column) or []
        if isinstance(headers, str):
            headers = [headers]
        for header in headers:
            normalized_header = normalize_header(header)
            if header_owners.get(normalized_header) == column:
                fields_by_header[normalized_header] = value
            for key in list(pricing_snapshot):
                normalized_key = normalize_header(key)
                if normalized_key in normalized_header or normalized_header in normalized_key:
                    pricing_snapshot[key] = value
        model_field = OPPORTUNITY_COLUMN_FIELDS.get(column)
        if model_field:
            if model_field in {"main_sku", "sub_sku"} and not value:
                raise ValueError(f"{model_field} is required")
            setattr(opportunity, model_field, value)

    if after:
        snapshot["cells"] = cells
        snapshot["fields_by_column"] = fields_by_column
        snapshot["fields_by_header"] = fields_by_header
        if pricing_snapshot:
            snapshot["pricing_snapshot"] = pricing_snapshot
        opportunity.snapshot = snapshot
    return before, after


def _coerce_edited_source_value(value: object, old_value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    if not isinstance(old_value, (int, float)) or isinstance(old_value, bool):
        return text
    percent = text.endswith("%")
    try:
        number = float(text.removesuffix("%").replace(",", ""))
    except ValueError:
        return text
    number = number / 100 if percent else number
    return int(number) if isinstance(old_value, int) and number.is_integer() else number


def set_opportunities_disabled(
    db: Session,
    opportunities: list[models.NewProductOpportunity],
    disabled: bool,
    reason: str | None = None,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
    scope: str = "opportunity",
) -> int:
    changed = 0
    for opportunity in opportunities:
        if disabled and opportunity.current_status != OPPORTUNITY_DISABLED:
            _remember_enabled_status(opportunity, reason, actor_name)
            opportunity.current_status = OPPORTUNITY_DISABLED
            changed += 1
        elif not disabled and opportunity.current_status == OPPORTUNITY_DISABLED:
            opportunity.current_status = _remembered_status(opportunity)
            changed += 1
    if changed:
        audit(
            db,
            "opportunity.disabled" if disabled else "opportunity.restored",
            "new_product_opportunity",
            None,
            {"scope": scope, "count": changed, "reason": reason},
            actor_name,
            actor_user_id,
        )
    return changed


def set_import_batch_disabled(
    db: Session,
    batch: models.ImportBatch,
    disabled: bool,
    reason: str | None = None,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> int:
    opportunities = list(
        db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.import_batch_id == batch.id))
    )
    changed = set_opportunities_disabled(db, opportunities, disabled, reason, actor_name, actor_user_id, scope="import_batch")
    batch.status = "disabled" if disabled else "completed"
    audit(
        db,
        "import_batch.disabled" if disabled else "import_batch.restored",
        "import_batch",
        batch.id,
        {"count": changed, "reason": reason},
        actor_name,
        actor_user_id,
    )
    return changed


def _remember_enabled_status(opportunity: models.NewProductOpportunity, reason: str | None, actor_name: str | None) -> None:
    snapshot = dict(opportunity.snapshot or {})
    snapshot["_admin_disabled"] = {
        "previous_status": opportunity.current_status,
        "reason": reason,
        "actor_name": actor_name,
        "disabled_at": models.now_utc().isoformat(),
    }
    opportunity.snapshot = snapshot


def _remembered_status(opportunity: models.NewProductOpportunity) -> str:
    snapshot = dict(opportunity.snapshot or {})
    meta = snapshot.get("_admin_disabled") if isinstance(snapshot.get("_admin_disabled"), dict) else {}
    previous = meta.get("previous_status") if isinstance(meta, dict) else None
    return previous if previous and previous != OPPORTUNITY_DISABLED else OPPORTUNITY_PENDING_ASSIGNMENT


def preview_assignments(
    opportunities: list[models.NewProductOpportunity],
    candidates: list[str],
    profiles: list[models.OperatorAssignmentProfile] | None = None,
    db: Session | None = None,
) -> list[schemas.AssignmentPreviewItem]:
    candidate_profiles = list(profiles or [])
    existing_names = {profile.operator_name for profile in candidate_profiles}
    for candidate in candidates:
        if candidate not in existing_names:
            candidate_profiles.append(
                SimpleNamespace(
                    operator_name=candidate,
                    key_site=None,
                    key_category1=None,
                    key_category2=None,
                    key_categories=[],
                    enabled=True,
                )
            )
    candidate_names = {getattr(profile, "operator_name", None) for profile in candidate_profiles}
    initial_loads = _pending_assignment_group_loads(db, candidate_names) if db else {}
    initial_last_assigned = _last_assignment_times(db, candidate_names) if db else {}
    return assignment_rules.preview_main_sku_assignment_groups(
        opportunities,
        candidate_profiles,
        initial_loads=initial_loads,
        initial_last_assigned=initial_last_assigned,
    )


def _pending_assignment_group_loads(db: Session, operator_names: set[str | None]) -> dict[str, int]:
    names = {name for name in operator_names if name}
    if not names:
        return {}
    rows = db.execute(
        select(
            models.FlowTask.assignee_name,
            models.NewProductOpportunity.source_type,
            models.NewProductOpportunity.batch,
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.site,
            models.NewProductOpportunity.country,
        )
        .join(models.FlowInstance, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .join(models.NewProductOpportunity, models.FlowInstance.opportunity_id == models.NewProductOpportunity.id)
        .where(
            models.FlowTask.task_type == "sales_claim",
            models.FlowTask.status == TASK_PENDING,
            models.FlowTask.assignee_name.in_(names),
            models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
        )
    ).all()
    groups: dict[str, set[tuple[str | None, str | None, str, str]]] = defaultdict(set)
    for assignee_name, source_type, batch, main_sku, site, country in rows:
        if not assignee_name or not main_sku:
            continue
        groups[assignee_name].add((source_type, batch, main_sku, normalize_site_code(site or country) or ""))
    return {name: len(keys) for name, keys in groups.items()}


def _last_assignment_times(db: Session, operator_names: set[str | None]) -> dict[str, datetime]:
    names = {name for name in operator_names if name}
    if not names:
        return {}
    rows = db.execute(
        select(models.FlowTask.assignee_name, func.max(models.FlowTask.created_at))
        .where(
            models.FlowTask.task_type == "sales_claim",
            models.FlowTask.assignee_name.in_(names),
        )
        .group_by(models.FlowTask.assignee_name)
    ).all()
    return {name: latest for name, latest in rows if name and latest is not None}


def list_assignment_board(
    db: Session,
    batch: str | None = None,
    assignee_name: str | None = None,
) -> schemas.AssignmentBoardResponse:
    rows = db.execute(
        select(models.FlowTask, models.NewProductOpportunity)
        .join(models.FlowInstance, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .join(models.NewProductOpportunity, models.FlowInstance.opportunity_id == models.NewProductOpportunity.id)
        .where(
            models.FlowTask.task_type == "sales_claim",
            # 开放池任务（无受派人）不是"分配结果"，且不能被改派绕过认领状态机。
            models.FlowTask.assignee_name.is_not(None),
            models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
        )
        .order_by(models.FlowTask.created_at.desc())
    ).all()
    latest_rows: list[schemas.AssignmentBoardRow] = []
    seen_opportunity_ids: set[str] = set()
    for task, opportunity in rows:
        if opportunity.id in seen_opportunity_ids:
            continue
        seen_opportunity_ids.add(opportunity.id)
        latest_rows.append(
            schemas.AssignmentBoardRow(
                task_id=task.id,
                opportunity_id=opportunity.id,
                batch=(opportunity.batch or opportunity.source_sheet or "").strip() or None,
                site=opportunity.site or opportunity.country,
                category_level1=opportunity.category_level1,
                main_sku=opportunity.main_sku,
                main_sku_name=opportunity.main_sku_name,
                sub_sku=opportunity.sub_sku,
                sub_sku_name=opportunity.sub_sku_name,
                assignee_name=task.assignee_name,
                task_status=task.status,
                opportunity_status=opportunity.current_status,
                assigned_at=task.created_at,
            )
        )
    batches: list[str] = []
    for row in latest_rows:
        period = row.batch or ""
        if period not in batches:
            batches.append(period)
    assignees = sorted({row.assignee_name for row in latest_rows if row.assignee_name})
    filtered = [
        row
        for row in latest_rows
        if (not batch or (row.batch or "") == batch) and (not assignee_name or row.assignee_name == assignee_name)
    ]
    grouped: dict[str, list[schemas.AssignmentBoardRow]] = defaultdict(list)
    for row in filtered:
        grouped[row.batch or ""].append(row)
    groups = [
        schemas.AssignmentBoardGroup(batch=period, rows=sorted(grouped[period], key=lambda row: (row.main_sku, row.sub_sku)))
        for period in batches
        if period in grouped
    ]
    return schemas.AssignmentBoardResponse(batches=batches, assignees=assignees, groups=groups)


def confirm_assignment(
    db: Session,
    payload: schemas.AssignmentConfirmRequest,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> list[models.FlowTask]:
    selected = list(
        db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(payload.opportunity_ids)))
    )
    locked = [item for item in selected if item.current_status != OPPORTUNITY_PENDING_ASSIGNMENT]
    if locked:
        raise ValueError("assignment only supports pending_assignment opportunities")
    opportunities = _expand_assignment_groups(db, selected)
    tasks: list[models.FlowTask] = []
    for opportunity in opportunities:
        flow = models.FlowInstance(
            opportunity_id=opportunity.id,
            current_node="sales_claim",
            current_status=OPPORTUNITY_ASSIGNED,
            owner_user_id=payload.assignee_user_id,
            owner_role="sales",
            deadline_at=payload.deadline_at,
        )
        db.add(flow)
        db.flush()
        task = models.FlowTask(
            flow_instance_id=flow.id,
            node_code="sales_claim",
            task_type="sales_claim",
            assignee_user_id=payload.assignee_user_id,
            assignee_name=payload.assignee_name,
            assignee_role="sales",
            deadline_at=payload.deadline_at,
        )
        opportunity.current_status = OPPORTUNITY_ASSIGNED
        db.add(task)
        tasks.append(task)
        audit(
            db,
            "assignment.confirmed",
            "flow_task",
            task.id,
            {"opportunity_id": opportunity.id, "assignee_name": payload.assignee_name},
            actor_name or payload.assignee_name,
            actor_user_id,
        )
    return tasks


def _expand_assignment_groups(db: Session, selected: list[models.NewProductOpportunity]) -> list[models.NewProductOpportunity]:
    opportunities_by_id: dict[str, models.NewProductOpportunity] = {}
    for opportunity in selected:
        query = select(models.NewProductOpportunity).where(
            models.NewProductOpportunity.source_type == opportunity.source_type,
            models.NewProductOpportunity.main_sku == opportunity.main_sku,
            models.NewProductOpportunity.current_status == OPPORTUNITY_PENDING_ASSIGNMENT,
        )
        if opportunity.batch is None:
            query = query.where(models.NewProductOpportunity.batch.is_(None))
        else:
            query = query.where(models.NewProductOpportunity.batch == opportunity.batch)
        for group_opportunity in db.scalars(query):
            opportunities_by_id[group_opportunity.id] = group_opportunity
    return list(opportunities_by_id.values())


def submit_claim(
    db: Session,
    payload: schemas.ClaimCreate,
    assignee_name: str | None = None,
    assignee_user_id: str | None = None,
) -> models.SalesClaimForecast:
    if payload.claim_result == CLAIM_RESULT_CLAIM and (
        payload.claim_daily_sales is None or payload.claim_daily_sales <= 0
    ):
        raise ValueError("claim_daily_sales must be greater than 0 when claim_result is claim")
    if payload.claim_result == CLAIM_RESULT_REJECT and not _clean_text(payload.reject_reason):
        raise ValueError("reject_reason is required when claim_result is reject")

    now = datetime.now(timezone.utc)
    claim_source = payload.claim_source or "assigned_task"
    opportunity = db.get(models.NewProductOpportunity, payload.opportunity_id)
    if opportunity is None:
        raise ValueError("opportunity not found")
    if claim_source == "caigen_self_claim" and not is_caigen_self_claim_opportunity(opportunity):
        raise PermissionError("caigen self claim is only allowed for caigen opportunity pool")
    task = (
        _find_claim_task(db, payload.opportunity_id, payload.task_id, assignee_name, assignee_user_id)
        if claim_source != "caigen_self_claim"
        else None
    )
    if claim_source != "caigen_self_claim" and assignee_name and task is None:
        raise PermissionError("claim task does not belong to current operator")
    claim = None
    if claim_source != "caigen_self_claim":
        claim = db.scalar(
            select(models.SalesClaimForecast)
            .where(
                models.SalesClaimForecast.opportunity_id == payload.opportunity_id,
                models.SalesClaimForecast.salesperson_name == payload.salesperson_name,
                models.SalesClaimForecast.claim_source == claim_source,
                models.SalesClaimForecast.source_column == "platform",
            )
            .order_by(models.SalesClaimForecast.created_at.desc())
        )
    if claim is None:
        claim = models.SalesClaimForecast(
            opportunity_id=payload.opportunity_id,
            platform="Shopee",
            salesperson_name=payload.salesperson_name,
            source_column="platform",
            claim_source=claim_source,
            task_id=task.id if task else payload.task_id,
            first_submitted_at=now,
        )
        db.add(claim)
    elif task:
        claim.task_id = task.id

    claim.claim_result = payload.claim_result
    claim.claim_daily_sales = payload.claim_daily_sales
    claim.reject_reason = _clean_text(payload.reject_reason)
    claim.feedback_summary = payload.feedback_summary
    claim.note = payload.note
    claim.last_updated_at = now
    opportunity.current_status = OPPORTUNITY_CLAIM_SUBMITTED if payload.claim_result == CLAIM_RESULT_CLAIM else OPPORTUNITY_CLAIM_REJECTED
    if task:
        task.status = TASK_COMPLETED
        task.completed_at = now
    create_review_task(db, payload.opportunity_id, payload.salesperson_name)
    audit(db, "claim.submitted", "sales_claim_forecast", claim.id, payload.model_dump(), payload.salesperson_name)
    return claim


def is_caigen_self_claim_opportunity(opportunity: models.NewProductOpportunity) -> bool:
    return opportunity.source_type == "selection2_caigen_claim_feedback" and opportunity.current_status in {
        OPPORTUNITY_PENDING_ASSIGNMENT,
        OPPORTUNITY_OPEN_CLAIM_POOL,
        OPPORTUNITY_CLAIM_SUBMITTED,
        OPPORTUNITY_CLAIM_REJECTED,
    }


def can_upload_claim_evidence(
    db: Session,
    opportunity_id: str,
    assignee_name: str | None = None,
    assignee_user_id: str | None = None,
) -> bool:
    opportunity = db.get(models.NewProductOpportunity, opportunity_id)
    if opportunity is None:
        return False
    if is_caigen_self_claim_opportunity(opportunity):
        return True
    if assignee_name:
        downstream_claim = db.scalar(
            select(models.SalesClaimForecast).where(
                models.SalesClaimForecast.opportunity_id == opportunity_id,
                models.SalesClaimForecast.salesperson_name == assignee_name,
                models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH,
            )
        )
        if downstream_claim:
            return True
    return _find_claim_task(db, opportunity_id, assignee_name=assignee_name, assignee_user_id=assignee_user_id) is not None


def _find_claim_task(
    db: Session,
    opportunity_id: str,
    task_id: str | None = None,
    assignee_name: str | None = None,
    assignee_user_id: str | None = None,
) -> models.FlowTask | None:
    filters = [
        models.FlowInstance.opportunity_id == opportunity_id,
        models.FlowTask.task_type == "sales_claim",
    ]
    if task_id:
        filters.append(models.FlowTask.id == task_id)
    if assignee_name or assignee_user_id:
        owner_filters = []
        if assignee_name:
            owner_filters.append(models.FlowTask.assignee_name == assignee_name)
        if assignee_user_id:
            owner_filters.append(models.FlowTask.assignee_user_id == assignee_user_id)
        filters.append(or_(*owner_filters))
    query = (
        select(models.FlowTask)
        .join(models.FlowInstance)
        .where(*filters)
        .order_by(models.FlowTask.created_at.desc())
    )
    pending = db.scalar(query.where(models.FlowTask.status == TASK_PENDING))
    if pending:
        return pending

    opportunity = db.get(models.NewProductOpportunity, opportunity_id)
    if opportunity is None or opportunity.current_status not in {OPPORTUNITY_CLAIM_SUBMITTED, OPPORTUNITY_CLAIM_REJECTED}:
        return None
    completed = db.scalar(query.where(models.FlowTask.status == TASK_COMPLETED))
    claim = latest_platform_submission(db, opportunity_id)
    if completed is None or claim is None or claim.task_id != completed.id:
        return None
    review = latest_review(db, opportunity_id)
    if review and _same_or_later(review.created_at, completed.completed_at):
        return None
    return completed


def _same_or_later(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return False
    return left.replace(tzinfo=None) >= right.replace(tzinfo=None)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def create_review_task(db: Session, opportunity_id: str, actor_name: str | None = None) -> None:
    flow = db.scalar(
        select(models.FlowInstance)
        .where(models.FlowInstance.opportunity_id == opportunity_id)
        .order_by(models.FlowInstance.created_at.desc())
    )
    if not flow:
        flow = models.FlowInstance(opportunity_id=opportunity_id, current_node="review", current_status=REVIEW_PENDING)
        db.add(flow)
        db.flush()
    flow.current_node = "review"
    flow.current_status = REVIEW_PENDING
    existing = db.scalar(
        select(models.FlowTask)
        .join(models.FlowInstance)
        .where(
            models.FlowInstance.opportunity_id == opportunity_id,
            models.FlowTask.task_type == "manager_review",
            models.FlowTask.status == TASK_PENDING,
        )
    )
    if existing:
        return
    task = models.FlowTask(
        flow_instance_id=flow.id,
        node_code="review",
        task_type="manager_review",
        assignee_role="manager",
    )
    db.add(task)
    audit(db, "review_task.created", "flow_task", task.id, {"opportunity_id": opportunity_id}, actor_name)


def submit_review(
    db: Session,
    payload: schemas.ReviewCreate,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.ReviewRecord:
    if payload.review_status not in REVIEW_TO_OPPORTUNITY_STATUS:
        raise ValueError("invalid review_status")
    review_comment = _clean_text(payload.review_comment)
    if payload.review_status == REVIEW_RETURNED_FOR_SUPPLEMENT and not review_comment:
        raise ValueError("review_comment is required when returning for supplement")
    db.flush()
    opportunity = db.get(models.NewProductOpportunity, payload.opportunity_id)
    claim = (
        db.get(models.SalesClaimForecast, payload.claim_record_id)
        if payload.claim_record_id
        else latest_platform_submission(db, payload.opportunity_id)
    )
    reviewed_claims = [claim] if claim else []
    if not payload.claim_record_id and payload.review_status == REVIEW_APPROVED:
        reviewed_claims = list(
            db.scalars(
                select(models.SalesClaimForecast)
                .where(
                    models.SalesClaimForecast.opportunity_id == payload.opportunity_id,
                    models.SalesClaimForecast.source_column == "platform",
                    models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
                )
                .order_by(models.SalesClaimForecast.created_at.asc())
            )
        )
        claim = reviewed_claims[0] if reviewed_claims else None
    if claim and claim.opportunity_id != payload.opportunity_id:
        raise ValueError("claim record does not belong to opportunity")
    if payload.review_status == REVIEW_APPROVED and (
        not opportunity
        or opportunity.current_status != OPPORTUNITY_CLAIM_SUBMITTED
        or not claim
        or claim.claim_result != CLAIM_RESULT_CLAIM
    ):
        raise ValueError("only claim submissions can be approved")
    if payload.review_status == REVIEW_CONFIRMED_NOT_CLAIM and (
        not opportunity
        or opportunity.current_status != OPPORTUNITY_CLAIM_REJECTED
        or not claim
        or claim.claim_result != CLAIM_RESULT_REJECT
    ):
        raise ValueError("only not-claim submissions can be confirmed")
    if payload.review_status == REVIEW_RETURNED_FOR_SUPPLEMENT and (
        not opportunity
        or opportunity.current_status not in {OPPORTUNITY_CLAIM_SUBMITTED, OPPORTUNITY_CLAIM_REJECTED}
        or not claim
        or claim.claim_result not in {CLAIM_RESULT_CLAIM, CLAIM_RESULT_REJECT}
    ):
        raise ValueError("only claim or not-claim submissions can be returned for supplement")
    reviewer_name = actor_name or payload.reviewer_name
    records = [
        models.ReviewRecord(
            opportunity_id=payload.opportunity_id,
            claim_record_id=reviewed_claim.id,
            reviewer_user_id=actor_user_id,
            reviewer_name=reviewer_name,
            review_status=payload.review_status,
            review_comment=review_comment,
        )
        for reviewed_claim in reviewed_claims
    ]
    db.add_all(records)
    if opportunity:
        opportunity.current_status = REVIEW_TO_OPPORTUNITY_STATUS[payload.review_status]
    task = db.scalar(
        select(models.FlowTask)
        .join(models.FlowInstance)
        .where(
            models.FlowInstance.opportunity_id == payload.opportunity_id,
            models.FlowTask.task_type == "manager_review",
            models.FlowTask.status == TASK_PENDING,
        )
        .order_by(models.FlowTask.created_at.desc())
    )
    if task:
        task.status = TASK_COMPLETED
        task.completed_at = datetime.now(timezone.utc)
    if payload.review_status == REVIEW_RETURNED_FOR_SUPPLEMENT:
        create_returned_claim_task(db, payload.opportunity_id, reviewer_name)
    if payload.review_status == REVIEW_APPROVED:
        for reviewed_claim in reviewed_claims:
            create_stocking_draft_for_claim(db, reviewed_claim.id, reviewer_name)
            reviewed_claim.downstream_status = CLAIM_WAITING_STOCKING_REQUEST
        audit(db, "opportunity.ready_for_stocking", "new_product_opportunity", payload.opportunity_id, {}, reviewer_name, actor_user_id)
    for record in records:
        audit(
            db,
            "review.submitted",
            "review_record",
            record.id,
            {**payload.model_dump(), "claim_record_id": record.claim_record_id},
            reviewer_name,
            actor_user_id,
        )
    return records[0]


def submit_bulk_reviews(
    db: Session,
    payload: schemas.BulkReviewCreate,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> list[models.ReviewRecord]:
    opportunities = list(db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.id.in_(payload.opportunity_ids))))
    by_id = {item.id: item for item in opportunities}
    missing = [opportunity_id for opportunity_id in payload.opportunity_ids if opportunity_id not in by_id]
    if missing:
        raise ValueError(f"opportunities not found: {', '.join(missing)}")
    statuses = {item.current_status for item in opportunities}
    if len(statuses) != 1:
        raise ValueError("bulk review requires the same submission type")
    current_status = statuses.pop()
    if current_status not in {OPPORTUNITY_CLAIM_SUBMITTED, OPPORTUNITY_CLAIM_REJECTED}:
        raise ValueError("only pending claim or not-claim submissions can be bulk reviewed")
    if payload.action == "reject":
        review_status = REVIEW_RETURNED_FOR_SUPPLEMENT
    else:
        review_status = REVIEW_APPROVED if current_status == OPPORTUNITY_CLAIM_SUBMITTED else REVIEW_CONFIRMED_NOT_CLAIM

    return [
        submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity_id,
                reviewer_name=payload.reviewer_name,
                review_status=review_status,
                review_comment=payload.review_comment,
            ),
            actor_name,
            actor_user_id,
        )
        for opportunity_id in payload.opportunity_ids
    ]


def create_returned_claim_task(db: Session, opportunity_id: str, actor_name: str | None = None) -> None:
    flow = db.scalar(
        select(models.FlowInstance)
        .where(models.FlowInstance.opportunity_id == opportunity_id)
        .order_by(models.FlowInstance.created_at.desc())
    )
    if flow is None:
        flow = models.FlowInstance(opportunity_id=opportunity_id)
        db.add(flow)
        db.flush()
    claim = latest_platform_submission(db, opportunity_id)
    original_task = db.get(models.FlowTask, claim.task_id) if claim and claim.task_id else None
    flow.current_node = "sales_claim"
    flow.current_status = OPPORTUNITY_RETURNED_FOR_SUPPLEMENT
    flow.owner_user_id = original_task.assignee_user_id if original_task else None
    flow.owner_role = "sales"
    task = models.FlowTask(
        flow_instance_id=flow.id,
        node_code="sales_claim",
        task_type="sales_claim",
        assignee_user_id=original_task.assignee_user_id if original_task else None,
        assignee_name=claim.salesperson_name if claim else None,
        assignee_role="sales",
    )
    db.add(task)
    audit(db, "claim.returned_for_supplement", "flow_task", task.id, {"opportunity_id": opportunity_id}, actor_name)


def latest_platform_submission(
    db: Session,
    opportunity_id: str,
    created_before: datetime | None = None,
) -> models.SalesClaimForecast | None:
    query = (
        select(models.SalesClaimForecast)
        .where(
            models.SalesClaimForecast.opportunity_id == opportunity_id,
            models.SalesClaimForecast.source_column == "platform",
        )
        .order_by(models.SalesClaimForecast.last_updated_at.desc(), models.SalesClaimForecast.created_at.desc())
    )
    if created_before is not None:
        query = query.where(models.SalesClaimForecast.created_at <= created_before)
    return db.scalar(query)


def open_secondary_research(
    db: Session,
    claim_record_id: str,
    arrived_at: datetime | None = None,
) -> models.SalesClaimForecast:
    claim = db.get(models.SalesClaimForecast, claim_record_id)
    if claim is None:
        raise LookupError("claim record not found")
    if claim.claim_result != CLAIM_RESULT_CLAIM:
        raise ValueError("only claimed products can enter secondary research")
    claim.downstream_status = CLAIM_WAITING_SECONDARY_RESEARCH
    claim.arrival_detected_at = arrived_at or datetime.now(timezone.utc)
    audit(
        db,
        "secondary_research.opened",
        "sales_claim_forecast",
        claim.id,
        {"arrival_detected_at": claim.arrival_detected_at.isoformat()},
        claim.salesperson_name,
    )
    return claim


def list_secondary_research_groups(
    db: Session,
    salesperson_name: str | None = None,
    business_period: str | None = None,
    downstream_status: str | None = None,
) -> list[dict]:
    filters = [models.SalesClaimForecast.downstream_status.is_not(None)]
    if salesperson_name:
        filters.append(models.SalesClaimForecast.salesperson_name == salesperson_name)
    if business_period and business_period != "__all__":
        filters.append(models.NewProductOpportunity.batch == business_period)
    if downstream_status:
        filters.append(models.SalesClaimForecast.downstream_status == downstream_status)
    if business_period is None:
        latest_period = db.scalar(
            select(models.NewProductOpportunity.batch)
            .join(
                models.SalesClaimForecast,
                models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id,
            )
            .where(*filters, models.NewProductOpportunity.batch.is_not(None))
            .order_by(models.NewProductOpportunity.batch.desc())
            .limit(1)
        )
        if latest_period:
            filters.append(models.NewProductOpportunity.batch == latest_period)
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(
            models.NewProductOpportunity,
            models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id,
        )
        .where(*filters)
        .order_by(
            models.NewProductOpportunity.batch.desc(),
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
            models.SalesClaimForecast.salesperson_name,
        )
    ).all()
    opportunity_ids = {opportunity.id for _, opportunity in rows}
    peer_rows = []
    if opportunity_ids:
        peer_rows = db.execute(
            select(models.SalesClaimForecast)
            .where(
                models.SalesClaimForecast.opportunity_id.in_(opportunity_ids),
                models.SalesClaimForecast.secondary_research_submitted_at.is_not(None),
            )
            .order_by(models.SalesClaimForecast.secondary_research_submitted_at.desc())
        ).scalars().all()
    peers_by_opportunity: dict[str, list[models.SalesClaimForecast]] = defaultdict(list)
    for peer in peer_rows:
        peers_by_opportunity[peer.opportunity_id].append(peer)

    groups: dict[str, dict] = {}
    for claim, opportunity in rows:
        key = secondary_research_group_key(claim, opportunity)
        group = groups.setdefault(
            key,
            {
                "key": key,
                "source_type": opportunity.source_type,
                "business_period": opportunity.batch,
                "site": opportunity.site,
                "country": opportunity.country,
                "main_sku": opportunity.main_sku,
                "main_sku_name": opportunity.main_sku_name,
                "salesperson_name": claim.salesperson_name or "",
                "items": [],
            },
        )
        peers = [peer for peer in peers_by_opportunity[opportunity.id] if peer.id != claim.id]
        group["items"].append(secondary_research_item(claim, opportunity, peers))
    return list(groups.values())


def update_secondary_research_draft(
    db: Session,
    claim_record_id: str,
    payload: schemas.SecondaryResearchDraftUpdate,
    salesperson_name: str,
) -> dict:
    claim, opportunity = secondary_research_claim(db, claim_record_id)
    if claim.salesperson_name != salesperson_name:
        raise PermissionError("secondary research record does not belong to current operator")
    if claim.downstream_status != CLAIM_WAITING_SECONDARY_RESEARCH:
        raise ValueError("only pending secondary research can be edited")
    writable_fields = payload.model_fields_set - {"secondary_research_at"}
    for field in writable_fields:
        setattr(claim, field, getattr(payload, field))
    claim.last_updated_at = datetime.now(timezone.utc)
    audit(
        db,
        "secondary_research.draft_saved",
        "sales_claim_forecast",
        claim.id,
        {"fields": sorted(writable_fields)},
        salesperson_name,
    )
    return secondary_research_item(claim, opportunity, secondary_research_peers(db, claim))

def correct_secondary_research(
    db: Session,
    claim_record_id: str,
    payload: schemas.SecondaryResearchDraftUpdate,
    actor_name: str,
    actor_user_id: str | None,
    manager_access: bool,
    operator_name: str | None,
) -> dict:
    claim, opportunity = secondary_research_claim(db, claim_record_id, lock=True)
    if claim.secondary_research_submitted_at is None:
        raise ValueError("only submitted secondary research can be corrected")
    if not manager_access and claim.salesperson_name != operator_name:
        raise PermissionError("secondary research record does not belong to current operator")

    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for field in payload.model_fields_set - {"secondary_research_at"}:
        old_value = getattr(claim, field)
        new_value = getattr(payload, field)
        if old_value == new_value:
            continue
        before[field] = old_value.isoformat() if isinstance(old_value, datetime) else deepcopy(old_value)
        after[field] = new_value.isoformat() if isinstance(new_value, datetime) else deepcopy(new_value)
        setattr(claim, field, new_value)

    if not _clean_text(claim.secondary_conclusion):
        raise ValueError("secondary_conclusion is required")
    if claim.product_positioning not in {"引流款", "利润款", "淘汰款", "稳定款", "清仓款"}:
        raise ValueError("product_positioning is required")
    if not claim.secondary_target_daily_sales or claim.secondary_target_daily_sales <= 0:
        raise ValueError("secondary_target_daily_sales is required")
    if not _clean_text(claim.secondary_selling_points):
        raise ValueError("secondary_selling_points is required")
    if not before:
        return secondary_research_item(claim, opportunity, secondary_research_peers(db, claim))

    listing_rows = db.scalars(
        select(models.ListingRecord).where(
            models.ListingRecord.main_sku == opportunity.main_sku,
            models.ListingRecord.salesperson_name == claim.salesperson_name,
        )
    ).all()
    has_listing = any(claim.id in (listing.source_claim_ids or []) for listing in listing_rows)
    if not has_listing and claim.downstream_status in {CLAIM_WAITING_LISTING, CLAIM_DISABLED}:
        old_status = claim.downstream_status
        claim.downstream_status = (
            CLAIM_DISABLED if claim.product_positioning in {"淘汰款", "清仓款"} else CLAIM_WAITING_LISTING
        )
        if old_status != claim.downstream_status:
            before["downstream_status"] = old_status
            after["downstream_status"] = claim.downstream_status

    claim.last_updated_at = datetime.now(timezone.utc)
    audit(
        db,
        "secondary_research.corrected",
        "sales_claim_forecast",
        claim.id,
        {"before": before, "after": after},
        actor_name,
        actor_user_id,
    )
    return secondary_research_item(claim, opportunity, secondary_research_peers(db, claim))

def submit_secondary_research_group(
    db: Session,
    claim_record_ids: list[str],
    salesperson_name: str,
) -> list[dict]:
    selected = [secondary_research_claim(db, claim_id) for claim_id in dict.fromkeys(claim_record_ids)]
    if any(claim.salesperson_name != salesperson_name for claim, _ in selected):
        raise PermissionError("secondary research group does not belong to current operator")
    group_keys = {secondary_research_group_key(claim, opportunity) for claim, opportunity in selected}
    if len(group_keys) != 1:
        raise ValueError("claim records must belong to one main SKU group")
    first_claim, first_opportunity = selected[0]
    all_group_rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(
            models.NewProductOpportunity,
            models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id,
        )
        .where(
            models.SalesClaimForecast.salesperson_name == salesperson_name,
            models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH,
            models.NewProductOpportunity.source_type == first_opportunity.source_type,
            models.NewProductOpportunity.batch == first_opportunity.batch,
            models.NewProductOpportunity.site == first_opportunity.site,
            models.NewProductOpportunity.main_sku == first_opportunity.main_sku,
        )
    ).all()
    if {claim.id for claim, _ in all_group_rows} != {claim.id for claim, _ in selected}:
        raise ValueError("all pending child SKUs in the main SKU group must be submitted together")
    missing = [
        opportunity.sub_sku
        for claim, opportunity in selected
        if not _clean_text(claim.secondary_conclusion)
        or claim.product_positioning not in {"引流款", "利润款", "淘汰款", "稳定款", "清仓款"}
        or not claim.secondary_target_daily_sales
        or claim.secondary_target_daily_sales <= 0
        or not _clean_text(claim.secondary_selling_points)
    ]
    if missing:
        raise ValueError(f"secondary research is incomplete for: {', '.join(missing)}")
    now = datetime.now(timezone.utc)
    result = []
    for claim, opportunity in selected:
        claim.secondary_research_at = now
        claim.secondary_research_submitted_at = now
        claim.downstream_status = (
            CLAIM_DISABLED if claim.product_positioning in {"淘汰款", "清仓款"} else CLAIM_WAITING_LISTING
        )
        audit(
            db,
            "secondary_research.completed",
            "sales_claim_forecast",
            claim.id,
            {"product_positioning": claim.product_positioning, "downstream_status": claim.downstream_status},
            salesperson_name,
        )
        result.append(secondary_research_item(claim, opportunity, secondary_research_peers(db, claim)))
    return result


def list_secondary_research_export_rows(
    db: Session,
    salesperson_name: str | None = None,
    business_period: str | None = None,
    scenario: str = "pending",
    country: str | None = None,
    query: str | None = None,
) -> list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]]:
    if scenario not in {"pending", "submitted", "all"}:
        raise ValueError("invalid secondary research export scenario")
    filters = [models.SalesClaimForecast.downstream_status.is_not(None)]
    if salesperson_name:
        filters.append(models.SalesClaimForecast.salesperson_name == salesperson_name)
    if business_period:
        filters.append(models.NewProductOpportunity.batch == business_period)
    if country:
        filters.append(models.NewProductOpportunity.country == country)
    pending = models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH
    submitted = models.SalesClaimForecast.secondary_research_submitted_at.is_not(None)
    if scenario == "pending":
        filters.extend([pending, models.SalesClaimForecast.secondary_research_submitted_at.is_(None)])
    elif scenario == "submitted":
        filters.append(submitted)
    else:
        filters.append(or_(pending, submitted))
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(*filters)
        .order_by(
            models.NewProductOpportunity.batch.desc(),
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
            models.SalesClaimForecast.salesperson_name,
        )
    ).all()
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    return [
        row for row in rows
        if any((value or "").lower().find(needle) >= 0 for value in (
            row[1].main_sku,
            row[1].main_sku_name,
            row[1].sub_sku,
            row[1].sub_sku_name,
            row[1].keyword,
            row[0].salesperson_name,
        ))
    ]


def build_secondary_research_export_workbook(rows: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]]) -> bytes:
    headers = [
        "业务期", "国家", "站点", "负责人", "主 SKU", "主 SKU 名称", "子 SKU", "子 SKU 名称",
        "复查结论", "商品定位", "锚定链接", "目标单销", "卖点总结", "提交时间", "调研时间", "图片数",
        "类目", "关键词", "开品理由", "来源文件", "来源 Sheet", "来源行",
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "二次调研"
    worksheet.append(headers)
    for claim, opportunity in rows:
        worksheet.append([
            opportunity.batch,
            opportunity.country,
            opportunity.site,
            claim.salesperson_name,
            opportunity.main_sku,
            opportunity.main_sku_name,
            opportunity.sub_sku,
            opportunity.sub_sku_name,
            claim.secondary_conclusion,
            claim.product_positioning,
            claim.secondary_competitor_url,
            claim.secondary_target_daily_sales,
            claim.secondary_selling_points,
            excel_value(claim.secondary_research_submitted_at),
            excel_value(claim.secondary_research_at),
            len(claim.secondary_evidence_images or []),
            opportunity.category_level1,
            opportunity.keyword,
            opportunity.reason,
            opportunity.source_file,
            opportunity.source_sheet,
            opportunity.source_row,
        ])
    style_worksheet(worksheet, max_width=36, fill="D9EAF7")
    for column in ("N", "O"):
        for cell in worksheet[column][1:]:
            cell.number_format = "yyyy-mm-dd hh:mm"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def secondary_research_claim(
    db: Session,
    claim_record_id: str,
    lock: bool = False,
) -> tuple[models.SalesClaimForecast, models.NewProductOpportunity]:
    statement = (
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(
            models.NewProductOpportunity,
            models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id,
        )
        .where(models.SalesClaimForecast.id == claim_record_id)
    )
    if lock:
        statement = statement.with_for_update(of=models.SalesClaimForecast)
    row = db.execute(statement).one_or_none()
    if row is None:
        raise LookupError("secondary research record not found")
    return row[0], row[1]


def secondary_research_group_key(
    claim: models.SalesClaimForecast,
    opportunity: models.NewProductOpportunity,
) -> str:
    return "|".join(
        [
            opportunity.source_type or "",
            opportunity.batch or "",
            opportunity.site or "",
            opportunity.main_sku or "",
            claim.salesperson_name or "",
        ]
    )


def secondary_research_peers(
    db: Session,
    claim: models.SalesClaimForecast,
) -> list[models.SalesClaimForecast]:
    return list(
        db.scalars(
            select(models.SalesClaimForecast)
            .where(
                models.SalesClaimForecast.opportunity_id == claim.opportunity_id,
                models.SalesClaimForecast.id != claim.id,
                models.SalesClaimForecast.secondary_research_submitted_at.is_not(None),
            )
            .order_by(models.SalesClaimForecast.secondary_research_submitted_at.desc())
        )
    )


def secondary_research_item(
    claim: models.SalesClaimForecast,
    opportunity: models.NewProductOpportunity,
    peers: list[models.SalesClaimForecast],
) -> dict:
    return {
        "claim_record_id": claim.id,
        "opportunity_id": opportunity.id,
        "salesperson_name": claim.salesperson_name or "",
        "downstream_status": claim.downstream_status or "",
        "arrival_detected_at": claim.arrival_detected_at,
        "secondary_research_at": claim.secondary_research_at,
        "secondary_competitor_url": claim.secondary_competitor_url,
        "secondary_conclusion": claim.secondary_conclusion,
        "product_positioning": claim.product_positioning,
        "secondary_target_daily_sales": claim.secondary_target_daily_sales,
        "secondary_selling_points": claim.secondary_selling_points,
        "secondary_evidence_images": claim.secondary_evidence_images or [],
        "secondary_research_submitted_at": claim.secondary_research_submitted_at,
        "sub_sku": opportunity.sub_sku,
        "sub_sku_name": opportunity.sub_sku_name,
        "image_url": opportunity.image_url,
        "reason": opportunity.reason,
        "snapshot": opportunity.snapshot or {},
        "peer_records": [
            {
                "claim_record_id": peer.id,
                "salesperson_name": peer.salesperson_name,
                "secondary_research_at": peer.secondary_research_at,
                "secondary_competitor_url": peer.secondary_competitor_url,
                "secondary_conclusion": peer.secondary_conclusion,
                "product_positioning": peer.product_positioning,
                "secondary_target_daily_sales": peer.secondary_target_daily_sales,
                "secondary_selling_points": peer.secondary_selling_points,
                "secondary_research_submitted_at": peer.secondary_research_submitted_at,
            }
            for peer in peers
        ],
    }


class RowValidationError(ValueError):
    def __init__(self, row_errors: list[dict], status_code: int = 400):
        super().__init__("row validation failed")
        self.row_errors = row_errors
        self.status_code = status_code


def listing_task_key(
    source_type: str,
    business_period: str | None,
    site_or_country: str | None,
    main_sku: str,
    salesperson_name: str,
) -> str:
    return "|".join(
        [source_type, business_period or "", normalize_site_code(site_or_country) or "", main_sku, salesperson_name]
    )


def list_pending_listing_tasks(
    db: Session,
    owner: str | None = None,
    today: date | None = None,
) -> list[dict]:
    statement = (
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(models.SalesClaimForecast.downstream_status == CLAIM_WAITING_LISTING)
    )
    if owner:
        statement = statement.where(models.SalesClaimForecast.salesperson_name == owner)
    groups: dict[str, dict] = {}
    waiting_group_keys: set[str] = set()
    default_start = current_business_period_start(today or datetime.now(EXCEL_TIMEZONE).date()) + timedelta(days=7)
    for claim, opportunity in db.execute(statement).all():
        key = listing_task_key(
            opportunity.source_type,
            opportunity.batch,
            opportunity.site or opportunity.country,
            opportunity.main_sku,
            claim.salesperson_name or "",
        )
        group = groups.setdefault(
            key,
            {
                "task_key": key,
                "source_type": opportunity.source_type,
                "business_period": opportunity.batch,
                "country": opportunity.country,
                "site": opportunity.site,
                "main_sku": opportunity.main_sku,
                "main_sku_name": opportunity.main_sku_name,
                "salesperson_name": claim.salesperson_name or "",
                "claim_record_ids": [],
                "default_first_period_start": default_start,
            },
        )
        waiting_group_keys.add(key)
        group["claim_record_ids"].append(claim.id)
    listing_statement = select(models.ListingRecord)
    if owner:
        listing_statement = listing_statement.where(models.ListingRecord.salesperson_name == owner)
    listings = list(db.scalars(listing_statement))
    reusable_by_key: dict[tuple[str, str | None, str], list[models.ListingRecord]] = defaultdict(list)
    for listing in listings:
        if listing.status == "active" and listing.tracking_status == "active":
            reusable_by_key[
                (
                    listing.main_sku,
                    normalize_site_code(listing.site or listing.country),
                    listing.salesperson_name,
                )
            ].append(listing)
        groups.setdefault(
            listing.source_group_key,
            {
                "task_key": listing.source_group_key,
                "source_type": listing.source_type,
                "business_period": listing.business_period,
                "country": listing.country,
                "site": listing.site,
                "main_sku": listing.main_sku,
                "main_sku_name": listing.main_sku_name,
                "salesperson_name": listing.salesperson_name,
                "claim_record_ids": list(listing.source_claim_ids or []),
                "default_first_period_start": default_start,
            },
        )
    for key, group in groups.items():
        group["claim_record_ids"].sort()
        reusable_ids = sorted(
            listing.id
            for listing in reusable_by_key.get(
                (
                    group["main_sku"],
                    normalize_site_code(group["site"] or group["country"]),
                    group["salesperson_name"],
                ),
                [],
            )
            if listing.source_group_key != key
        ) if key in waiting_group_keys else []
        group["reusable_listing_ids"] = reusable_ids
        group["requires_confirmation"] = key in waiting_group_keys
    return sorted(groups.values(), key=lambda item: (item["business_period"] or "", item["main_sku"], item["salesperson_name"]))


def create_listing_batch(
    db: Session,
    task_key: str,
    rows: list[schemas.ListingBatchRow],
    actor_name: str,
    actor_user_id: str | None,
    actor_is_manager: bool,
    operator_name: str | None = None,
    reuse_listing_ids: list[str] | None = None,
    manual_context: schemas.ManualListingContext | None = None,
    today: date | None = None,
) -> list[models.ListingRecord]:
    reuse_listing_ids = list(dict.fromkeys(reuse_listing_ids or []))
    if not rows and not reuse_listing_ids:
        raise RowValidationError([{"row_index": 0, "field": "rows", "message": "rows or reuse_listing_ids is required"}])
    task = next((item for item in list_pending_listing_tasks(db, today=today) if item["task_key"] == task_key), None)
    if task is None:
        existing_task = db.scalar(
            select(models.ListingRecord)
            .where(models.ListingRecord.source_group_key == task_key)
            .order_by(models.ListingRecord.created_at)
        )
        if existing_task is None:
            if manual_context is None:
                raise LookupError("listing task not found")
            main_sku = _clean_text(manual_context.main_sku)
            salesperson_name = _clean_text(manual_context.salesperson_name)
            site_or_country = _clean_text(manual_context.site) or _clean_text(manual_context.country)
            if not main_sku or not salesperson_name or not site_or_country:
                raise RowValidationError([
                    {"row_index": 0, "field": "manual_context", "message": "main_sku, salesperson_name and country/site are required"}
                ])
            task = {
                "task_key": task_key,
                "source_type": "manual_listing",
                "business_period": _clean_text(manual_context.business_period),
                "country": _clean_text(manual_context.country) or site_or_country,
                "site": _clean_text(manual_context.site) or site_or_country,
                "main_sku": main_sku,
                "main_sku_name": _clean_text(manual_context.main_sku_name),
                "salesperson_name": salesperson_name,
                "claim_record_ids": [],
                "requires_confirmation": False,
                "reusable_listing_ids": [],
            }
        else:
            task = {
                "task_key": task_key,
                "source_type": existing_task.source_type,
                "business_period": existing_task.business_period,
                "country": existing_task.country,
                "site": existing_task.site,
                "main_sku": existing_task.main_sku,
                "main_sku_name": existing_task.main_sku_name,
                "salesperson_name": existing_task.salesperson_name,
                "claim_record_ids": existing_task.source_claim_ids,
            }
    if not actor_is_manager and task["salesperson_name"] != (operator_name or actor_name):
        raise PermissionError("listing task does not belong to current operator")

    claim_ids = sorted(set(task["claim_record_ids"]))
    claims = list(
        db.scalars(
            select(models.SalesClaimForecast)
            .where(models.SalesClaimForecast.id.in_(claim_ids))
            .order_by(models.SalesClaimForecast.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(claims) != len(claim_ids):
        raise LookupError("listing task claim record not found")
    if task.get("requires_confirmation") and any(
        claim.downstream_status != CLAIM_WAITING_LISTING for claim in claims
    ):
        raise ValueError("listing task is no longer pending")

    check_day = today or datetime.now(EXCEL_TIMEZONE).date()
    first_period_start = next_complete_business_period_start(check_day)
    row_errors: list[dict] = []
    cleaned: list[dict] = []
    for row_index, row in enumerate(rows):
        values = {
            "shop": (row.shop or "").strip(),
            "item": (row.item or "").strip(),
            "listing_strategy": (row.listing_strategy or "").strip(),
        }
        for field in ("shop", "item", "listing_strategy"):
            if not values[field]:
                row_errors.append({"row_index": row_index, "field": field, "message": f"{field} is required"})
        cleaned.append({**values, "first_period_start": first_period_start})

    item_rows: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row_index, values in enumerate(cleaned):
        if values["item"]:
            item_rows[(values["shop"], values["item"])].append(row_index)
    for indexes in item_rows.values():
        if len(indexes) > 1:
            row_errors.extend(
                {"row_index": row_index, "field": "item", "message": "item is duplicated in this batch"}
                for row_index in indexes
            )
    existing_pairs = {
        (shop, item)
        for shop, item in db.execute(
            select(models.ListingRecord.shop, models.ListingRecord.item).where(
                models.ListingRecord.item.in_({item for _, item in item_rows}),
                models.ListingRecord.status == "active",
            )
        )
    } if item_rows else set()
    row_errors.extend(
        {"row_index": row_index, "field": "item", "message": "item already exists"}
        for pair in existing_pairs
        if pair in item_rows
        for row_index in item_rows[pair]
    )
    reusable = {
        listing.id: listing
        for listing in db.scalars(
            select(models.ListingRecord)
            .where(models.ListingRecord.id.in_(reuse_listing_ids))
            .order_by(models.ListingRecord.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    } if reuse_listing_ids else {}
    allowed_reuse_ids = set(task.get("reusable_listing_ids", []))
    reuse_errors = [
        {
            "row_index": index,
            "field": "reuse_listing_ids",
            "message": "listing is not reusable for this task",
        }
        for index, listing_id in enumerate(reuse_listing_ids)
        if listing_id not in reusable
        or listing_id not in allowed_reuse_ids
        or reusable[listing_id].status != "active"
        or reusable[listing_id].tracking_status != "active"
        or reusable[listing_id].main_sku != task["main_sku"]
        or normalize_site_code(reusable[listing_id].site or reusable[listing_id].country)
        != normalize_site_code(task["site"] or task["country"])
        or reusable[listing_id].salesperson_name != task["salesperson_name"]
    ]
    if row_errors or reuse_errors:
        field_order = {"shop": 0, "item": 1, "listing_strategy": 2, "first_period_start": 3}
        row_errors.sort(key=lambda error: (error["row_index"], field_order.get(error["field"], 99)))
        conflict = any("duplicated" in error["message"] or "already exists" in error["message"] for error in row_errors)
        raise RowValidationError([*row_errors, *reuse_errors], 409 if conflict else 400)

    created: list[models.ListingRecord] = []
    for values in cleaned:
        first_start = values["first_period_start"]
        record = models.ListingRecord(
            id=models.new_id(),
            source_group_key=task_key,
            source_claim_ids=task["claim_record_ids"],
            source_type=task["source_type"],
            business_period=task["business_period"],
            country=task["country"],
            site=task["site"],
            main_sku=task["main_sku"],
            main_sku_name=task["main_sku_name"],
            salesperson_name=task["salesperson_name"],
            shop=values["shop"],
            item=values["item"],
            listing_strategy=values["listing_strategy"],
            first_period_start=first_start,
            first_period_end=first_start + timedelta(days=6),
            representative_rule="single_binding",
            created_by_user_id=actor_user_id,
            created_by_name=actor_name,
        )
        db.add(record)
        db.add(
            models.ListingSkuBinding(
                id=models.new_id(),
                listing_record_id=record.id,
                main_sku=task["main_sku"],
                salesperson_name=task["salesperson_name"],
                binding_source="platform_confirm",
            )
        )
        for week_number, (period_start, period_end) in enumerate(initial_observation_period_dates(first_start), start=1):
            db.add(
                models.ItemObservationPeriod(
                    id=models.new_id(),
                    listing_record_id=record.id,
                    week_number=week_number,
                    period_start=period_start,
                    period_end=period_end,
                )
            )
        audit(
            db,
            "listing.created",
            "listing_record",
            record.id,
            {"item": record.item, "task_key": task_key},
            actor_name,
            actor_user_id,
        )
        created.append(record)
    reused = [reusable[listing_id] for listing_id in reuse_listing_ids]
    for listing in reused:
        existing_claim_ids = list(listing.source_claim_ids or [])
        added_claim_ids = [claim_id for claim_id in task["claim_record_ids"] if claim_id not in existing_claim_ids]
        listing.source_claim_ids = list(dict.fromkeys([
            *existing_claim_ids,
            *task["claim_record_ids"],
        ]))
        if added_claim_ids:
            audit(
                db,
                "listing.reused",
                "listing_record",
                listing.id,
                {"task_key": task_key, "added_claim_record_ids": added_claim_ids},
                actor_name,
                actor_user_id,
            )
    for claim in claims:
        claim.downstream_status = CLAIM_LISTING_OBSERVATION
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise RowValidationError(
            [
                {"row_index": index, "field": "item", "message": "item already exists"}
                for index in range(len(rows))
            ],
            409,
        ) from exc
    return [*reused, *created]


def ensure_listing_product_detail(
    db: Session,
    listing_id: str,
    main_sku: str,
    actor_is_manager: bool,
    operator_name: str | None,
    actor_name: str | None,
    actor_user_id: str | None,
) -> models.NewProductOpportunity:
    listing = db.get(models.ListingRecord, listing_id)
    if listing is None:
        raise LookupError("listing record not found")
    requested_main_sku = _clean_text(main_sku)
    if not requested_main_sku:
        raise ValueError("main_sku is required")
    if not actor_is_manager and listing.salesperson_name != operator_name:
        raise PermissionError("listing record does not belong to current operator")

    binding = db.scalar(
        select(models.ListingSkuBinding).where(
            models.ListingSkuBinding.listing_record_id == listing.id,
            models.ListingSkuBinding.main_sku == requested_main_sku,
        )
    )
    if binding and binding.opportunity_id:
        opportunity = db.get(models.NewProductOpportunity, binding.opportunity_id)
        if opportunity is not None:
            return opportunity

    listing_site = normalize_site_code(listing.site or listing.country)
    candidates = [
        item for item in db.scalars(
            select(models.NewProductOpportunity).where(
                models.NewProductOpportunity.main_sku == requested_main_sku,
                models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
            )
        )
        if not listing_site or normalize_site_code(item.site or item.country) == listing_site
    ]
    period_candidates = [item for item in candidates if listing.business_period and item.batch == listing.business_period]
    opportunity = period_candidates[0] if len(period_candidates) == 1 else (candidates[0] if len(candidates) == 1 else None)
    if opportunity is not None:
        if binding is None:
            binding = models.ListingSkuBinding(
                id=models.new_id(),
                listing_record_id=listing.id,
                main_sku=requested_main_sku,
                salesperson_name=listing.salesperson_name,
                binding_source="history_listing",
            )
            db.add(binding)
        binding.opportunity_id = opportunity.id
        audit(
            db,
            "listing.product_detail_linked",
            "listing_record",
            listing.id,
            {"main_sku": requested_main_sku, "opportunity_id": opportunity.id},
            actor_name,
            actor_user_id,
        )
        return opportunity

    known_sub_sku = _clean_text(binding.sub_sku if binding else None) or _clean_text(listing.representative_sub_sku)
    placeholder_sub_sku = not known_sub_sku
    sub_sku = known_sub_sku or requested_main_sku
    listing_snapshot = {
        "listing_record_id": listing.id,
        "shop": listing.shop,
        "item": listing.item,
        "main_sku": requested_main_sku,
        "source_type": listing.source_type,
        "sub_sku_needs_confirmation": placeholder_sub_sku,
    }
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type="history_listing_only",
        source_file="FineBI历史刊登",
        source_sheet=listing.source_type,
        batch=listing.business_period or "历史刊登",
        country=listing.country,
        site=listing.site,
        developer_name=listing.salesperson_name,
        main_sku_name=listing.main_sku_name,
        main_sku=requested_main_sku,
        sub_sku_name="待补子 SKU" if placeholder_sub_sku else None,
        sub_sku=sub_sku,
        current_status="historical_archive",
        snapshot={"listing_only": listing_snapshot},
    )
    db.add(opportunity)
    db.add(
        models.SourceRecordSnapshot(
            id=models.new_id(),
            opportunity_id=opportunity.id,
            source_file="FineBI历史刊登",
            source_sheet=listing.source_type,
            payload={"listing_only": listing_snapshot},
        )
    )
    if binding is None:
        binding = models.ListingSkuBinding(
            id=models.new_id(),
            listing_record_id=listing.id,
            main_sku=requested_main_sku,
            sub_sku=known_sub_sku or None,
            salesperson_name=listing.salesperson_name,
            binding_source="history_listing",
        )
        db.add(binding)
    binding.opportunity_id = opportunity.id
    audit(
        db,
        "listing.product_detail_created",
        "new_product_opportunity",
        opportunity.id,
        {"listing_record_id": listing.id, "main_sku": requested_main_sku},
        actor_name,
        actor_user_id,
    )
    return opportunity


def listing_source_context(
    db: Session,
    listings: list[models.ListingRecord],
) -> dict[str, dict]:
    claim_to_listing_ids: dict[str, list[str]] = defaultdict(list)
    for listing in listings:
        for claim_id in listing.source_claim_ids or []:
            claim_to_listing_ids[claim_id].append(listing.id)
    periods_by_listing: dict[str, set[str]] = defaultdict(set)
    positions_by_listing: dict[str, set[str]] = defaultdict(set)
    if claim_to_listing_ids:
        rows = db.execute(
            select(
                models.SalesClaimForecast.id,
                models.SalesClaimForecast.product_positioning,
                models.NewProductOpportunity.batch,
            )
            .join(
                models.NewProductOpportunity,
                models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id,
            )
            .where(models.SalesClaimForecast.id.in_(claim_to_listing_ids))
        ).all()
        for claim_id, product_positioning, business_period in rows:
            for listing_id in claim_to_listing_ids[claim_id]:
                if value := _clean_text(business_period):
                    periods_by_listing[listing_id].add(value)
                if value := _clean_text(product_positioning):
                    positions_by_listing[listing_id].add(value)
    bound_skus_by_listing: dict[str, set[str]] = defaultdict(set)
    if listings:
        for listing_id, bound_main_sku in db.execute(
            select(models.ListingSkuBinding.listing_record_id, models.ListingSkuBinding.main_sku).where(
                models.ListingSkuBinding.listing_record_id.in_([listing.id for listing in listings])
            )
        ):
            bound_skus_by_listing[listing_id].add(bound_main_sku)
    return {
        listing.id: {
            "source_business_periods": sorted(periods_by_listing[listing.id]),
            "secondary_positioning": next(iter(positions_by_listing[listing.id]))
            if len(positions_by_listing[listing.id]) == 1
            else None,
            "bound_main_skus": sorted(bound_skus_by_listing[listing.id]),
        }
        for listing in listings
    }


def observation_positioning_defaults(
    db: Session,
    listing_ids: list[str],
    source_context: dict[str, dict],
) -> dict[str, str | None]:
    periods_by_listing: dict[str, list[models.ItemObservationPeriod]] = defaultdict(list)
    if listing_ids:
        for period in db.scalars(
            select(models.ItemObservationPeriod).where(
                models.ItemObservationPeriod.listing_record_id.in_(listing_ids)
            )
        ):
            periods_by_listing[period.listing_record_id].append(period)
    defaults: dict[str, str | None] = {}
    for listing_id, periods in periods_by_listing.items():
        latest_positioning = None
        for period in sorted(periods, key=lambda item: (item.period_start or date.min, item.week_number)):
            defaults[period.id] = latest_positioning or source_context.get(listing_id, {}).get("secondary_positioning")
            latest_positioning = _clean_text(period.product_positioning) or latest_positioning
    return defaults


def listing_record_read(item: models.ListingRecord, source_context: dict | None = None) -> dict:
    source_context = source_context or {}
    return {
        "id": item.id,
        "task_key": item.source_group_key,
        "main_sku": item.main_sku,
        "main_sku_name": item.main_sku_name,
        "country": item.country,
        "site": item.site,
        "salesperson_name": item.salesperson_name,
        "shop": item.shop,
        "item": item.item,
        "listing_strategy": item.listing_strategy,
        "first_period_start": item.first_period_start,
        "business_period": item.business_period,
        "source_business_periods": source_context.get("source_business_periods", []),
        "status": item.status,
        "tracking_status": item.tracking_status,
        "first_round_completed_at": item.initial_observation_completed_at,
        "is_shared_item": item.is_shared_item,
        "representative_rule": item.representative_rule,
        "representative_sub_sku": item.representative_sub_sku,
        "is_history": item.source_type == "history_finebi",
        "bound_main_skus": source_context.get("bound_main_skus", []),
    }


def observation_period_read(
    period: models.ItemObservationPeriod,
    listing: models.ListingRecord,
    default_product_positioning: str | None = None,
) -> dict:
    rate = None
    if period.total_revenue not in {None, 0} and period.gross_profit_amount is not None:
        rate = period.gross_profit_amount / period.total_revenue
    return {
        "id": period.id,
        "listing_record_id": listing.id,
        "main_sku": listing.main_sku,
        "main_sku_name": listing.main_sku_name,
        "country": listing.country,
        "salesperson_name": listing.salesperson_name,
        "shop": listing.shop,
        "item": listing.item,
        "week_number": period.week_number,
        "period_start": period.period_start,
        "period_end": period.period_end,
        "record_source": period.record_source,
        "metrics_origin": period.metrics_origin,
        "business_period": listing.business_period,
        "status": period.status,
        "tracking_status": listing.tracking_status,
        "order_count": period.order_count,
        "total_revenue": period.total_revenue,
        "gross_profit_amount": period.gross_profit_amount,
        "gross_profit_rate": rate,
        "product_positioning": period.product_positioning,
        "default_product_positioning": default_product_positioning,
        "optimization_action": period.optimization_action,
        "four_week_summary": period.four_week_summary,
        "first_round_completed_at": listing.initial_observation_completed_at,
    }


def list_listing_workbench(
    db: Session,
    owner: str | None = None,
    view: str = "all",
    query: str | None = None,
    period_start: date | None = None,
    country: str | None = None,
    shop: str | None = None,
    status: str | None = None,
    week_number: int | None = None,
    product_positioning: str | None = None,
    tracking_status: str | None = None,
    business_period: str | None = None,
    include_history: bool = False,
) -> dict:
    pending = list_pending_listing_tasks(db, owner)
    statement = select(models.ListingRecord)
    if not include_history:
        statement = statement.where(models.ListingRecord.source_type != "history_finebi")
    if owner:
        statement = statement.where(models.ListingRecord.salesperson_name == owner)
    if country:
        statement = statement.where(models.ListingRecord.country == country)
        pending = [task for task in pending if task["country"] == country]
    if shop:
        statement = statement.where(models.ListingRecord.shop.contains(shop.strip()))
    if tracking_status:
        statement = statement.where(models.ListingRecord.tracking_status == tracking_status)
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        statement = statement.where(
            or_(
                models.ListingRecord.main_sku.ilike(like),
                models.ListingRecord.main_sku_name.ilike(like),
                models.ListingRecord.item.ilike(like),
            )
        )
        pending = [
            task
            for task in pending
            if text.lower() in task["main_sku"].lower()
            or text.lower() in (task["main_sku_name"] or "").lower()
        ]
    listings = list(db.scalars(statement.order_by(models.ListingRecord.created_at.desc())))
    available_business_periods = sorted({
        *(item.business_period for item in listings if item.business_period),
        *(task["business_period"] for task in pending if task["business_period"]),
    })
    if business_period:
        listings = [item for item in listings if item.business_period == business_period]
        pending = [task for task in pending if task["business_period"] == business_period]
    listing_ids = [item.id for item in listings]
    period_statement = select(models.ItemObservationPeriod).where(
        models.ItemObservationPeriod.listing_record_id.in_(listing_ids)
    )
    if not include_history:
        period_statement = period_statement.where(models.ItemObservationPeriod.record_source == "platform")
    if period_start:
        period_statement = period_statement.where(models.ItemObservationPeriod.period_start == period_start)
    if status:
        period_statement = period_statement.where(models.ItemObservationPeriod.status == status)
    if week_number:
        period_statement = period_statement.where(models.ItemObservationPeriod.week_number == week_number)
    if product_positioning:
        period_statement = period_statement.where(models.ItemObservationPeriod.product_positioning == product_positioning)
    if view in {"pending_data", "pending_review"}:
        period_statement = period_statement.where(models.ItemObservationPeriod.status == view)
    if view == "first_round_completed":
        completed_ids = {item.id for item in listings if item.initial_observation_completed_at is not None}
        listings = [item for item in listings if item.id in completed_ids]
        period_statement = period_statement.where(models.ItemObservationPeriod.listing_record_id.in_(completed_ids))
    periods = list(
        db.scalars(period_statement.order_by(models.ItemObservationPeriod.period_start, models.ItemObservationPeriod.week_number))
    )
    listing_by_id = {item.id: item for item in listings}
    if view == "pending_listing":
        listings = []
        periods = []
    elif view != "all" and view not in {"pending_data", "pending_review", "first_round_completed"}:
        raise ValueError("invalid workbench view")
    source_context = listing_source_context(db, listings)
    positioning_defaults = observation_positioning_defaults(db, [item.id for item in listings], source_context)
    return {
        "pending_listing_tasks": pending if view in {"all", "pending_listing"} else [],
        "available_business_periods": available_business_periods,
        "listing_records": [listing_record_read(item, source_context[item.id]) for item in listings],
        "period_rows": [
            observation_period_read(
                period,
                listing_by_id[period.listing_record_id],
                positioning_defaults.get(period.id),
            )
            for period in periods
        ],
    }


def listing_summary(db: Session, main_sku: str, owner: str | None = None, country: str | None = None) -> dict:
    # 商品详情只看单个主 SKU：直接按 SKU（含绑定关系）查库，避免整表拉全部刊登与周数据再丢弃。
    bound_listing_ids = set(
        db.scalars(
            select(models.ListingSkuBinding.listing_record_id).where(
                models.ListingSkuBinding.main_sku == main_sku
            )
        )
    )
    statement = select(models.ListingRecord).where(
        or_(
            models.ListingRecord.main_sku == main_sku,
            models.ListingRecord.id.in_(bound_listing_ids),
        )
    )
    if owner:
        statement = statement.where(models.ListingRecord.salesperson_name == owner)
    if country:
        statement = statement.where(models.ListingRecord.country == country)
    listings = list(db.scalars(statement.order_by(models.ListingRecord.created_at.desc())))
    listing_by_id = {item.id: item for item in listings}
    periods = list(
        db.scalars(
            select(models.ItemObservationPeriod)
            .where(models.ItemObservationPeriod.listing_record_id.in_(list(listing_by_id)))
            .order_by(models.ItemObservationPeriod.period_start, models.ItemObservationPeriod.week_number)
        )
    )
    source_context = listing_source_context(db, listings)
    positioning_defaults = observation_positioning_defaults(db, [item.id for item in listings], source_context)
    return {
        "pending_listing_tasks": [],
        "listing_records": [listing_record_read(item, source_context[item.id]) for item in listings],
        "period_rows": [
            observation_period_read(
                period,
                listing_by_id[period.listing_record_id],
                positioning_defaults.get(period.id),
            )
            for period in periods
        ],
    }


def review_observation_periods(
    db: Session,
    rows: list[schemas.ObservationPeriodReviewRow],
    actor_name: str,
    actor_user_id: str | None,
    actor_is_manager: bool,
    operator_name: str | None = None,
) -> list[tuple[models.ItemObservationPeriod, models.ListingRecord]]:
    period_ids = [row.period_id for row in rows]
    if len(period_ids) != len(set(period_ids)):
        raise RowValidationError(
            [
                {"row_index": index, "field": "period_id", "message": "period is duplicated in this batch"}
                for index, period_id in enumerate(period_ids)
                if period_ids.count(period_id) > 1
            ]
        )
    period_links = dict(
        db.execute(
            select(models.ItemObservationPeriod.id, models.ItemObservationPeriod.listing_record_id).where(
                models.ItemObservationPeriod.id.in_(period_ids)
            )
        ).all()
    )
    missing = [period_id for period_id in period_ids if period_id not in period_links]
    if missing:
        raise LookupError(f"observation period not found: {', '.join(missing)}")
    listing_ids = set(period_links.values())
    listings = {
        listing.id: listing
        for listing in db.scalars(
            select(models.ListingRecord).where(
                models.ListingRecord.id.in_(listing_ids)
            ).order_by(models.ListingRecord.id).with_for_update()
        )
    }
    locked_listing_periods = list(
        db.scalars(
            select(models.ItemObservationPeriod)
            .where(
                models.ItemObservationPeriod.listing_record_id.in_(listing_ids),
                models.ItemObservationPeriod.record_source == "platform",
            )
            .order_by(models.ItemObservationPeriod.listing_record_id, models.ItemObservationPeriod.week_number)
            .with_for_update()
        )
    )
    periods = {period.id: period for period in locked_listing_periods if period.id in period_links}
    if not actor_is_manager and any(
        listings[period.listing_record_id].salesperson_name != (operator_name or actor_name)
        for period in periods.values()
    ):
        raise PermissionError("observation period does not belong to current operator")

    allowed_positioning = {"引流款", "利润款", "淘汰款", "稳定款", "清仓款"}
    row_errors: list[dict] = []
    for row_index, row in enumerate(rows):
        period = periods[row.period_id]
        listing = listings[period.listing_record_id]
        if listing.status != "active":
            row_errors.append(
                {"row_index": row_index, "field": "period_id", "message": "listing is not active and tracked"}
            )
        elif period.status not in {"pending_review", "completed"}:
            row_errors.append(
                {"row_index": row_index, "field": "period_id", "message": "period must be pending_review"}
            )
        if row.product_positioning not in allowed_positioning:
            row_errors.append(
                {"row_index": row_index, "field": "product_positioning", "message": "invalid product_positioning"}
            )
        if not (row.optimization_action or "").strip():
            row_errors.append(
                {"row_index": row_index, "field": "optimization_action", "message": "optimization_action is required"}
            )
        if period.week_number == 4 and not (row.four_week_summary or "").strip():
            row_errors.append(
                {
                    "row_index": row_index,
                    "field": "four_week_summary",
                    "message": "four_week_summary is required for week 4",
                }
            )
    if row_errors:
        raise RowValidationError(row_errors)

    now = models.now_utc()
    result: list[tuple[models.ItemObservationPeriod, models.ListingRecord]] = []
    touched_listing_ids: set[str] = set()
    old_values = {period.id: (period.status, period.product_positioning) for period in periods.values()}
    submitted_positioning = {row.period_id: row.product_positioning for row in rows}
    listing_periods: dict[str, list[models.ItemObservationPeriod]] = defaultdict(list)
    for item in locked_listing_periods:
        listing_periods[item.listing_record_id].append(item)
    for row in rows:
        period = periods[row.period_id]
        listing = listings[period.listing_record_id]
        old_status, old_positioning = old_values[period.id]
        previous_positioning = old_positioning
        if old_status == "pending_review":
            previous_positioning = None
            for previous_period in reversed(listing_periods[listing.id]):
                if previous_period.week_number >= period.week_number:
                    continue
                if previous_period.id in submitted_positioning:
                    previous_positioning = submitted_positioning[previous_period.id]
                    break
                if previous_period.status == "completed" and previous_period.product_positioning:
                    previous_positioning = previous_period.product_positioning
                    break
        period.product_positioning = row.product_positioning
        period.optimization_action = row.optimization_action.strip()
        if period.week_number == 4:
            period.four_week_summary = row.four_week_summary.strip()
        period.status = "completed"
        period.reviewed_at = now
        audit(
            db,
            "observation.reviewed",
            "item_observation_period",
            period.id,
            {"week_number": period.week_number, "product_positioning": period.product_positioning},
            actor_name,
            actor_user_id,
        )
        if period.product_positioning == "淘汰款" and previous_positioning != "淘汰款":
            audit(
                db,
                "observation.elimination_entered",
                "item_observation_period",
                period.id,
                {
                    "listing_record_id": listing.id,
                    "week_number": period.week_number,
                    "previous_positioning": previous_positioning,
                    "product_positioning": "淘汰款",
                },
                actor_name,
                actor_user_id,
            )
        touched_listing_ids.add(listing.id)
        result.append((period, listing))
    db.flush()
    for listing_id in touched_listing_ids:
        initial_periods = list(
            db.scalars(
                select(models.ItemObservationPeriod).where(
                    models.ItemObservationPeriod.listing_record_id == listing_id,
                    models.ItemObservationPeriod.week_number <= 4,
                    models.ItemObservationPeriod.record_source == "platform",
                )
            )
        )
        if len(initial_periods) == 4 and all(period.status == "completed" for period in initial_periods):
            listings[listing_id].initial_observation_completed_at = listings[listing_id].initial_observation_completed_at or now
    return result


def update_listing_record(
    db: Session,
    listing_id: str,
    payload: schemas.ListingRecordUpdate,
    actor_name: str,
    actor_user_id: str | None,
    actor_is_manager: bool,
    operator_name: str | None = None,
    today: date | None = None,
) -> models.ListingRecord:
    listing = db.get(models.ListingRecord, listing_id)
    if listing is None:
        raise LookupError("listing record not found")
    if not actor_is_manager and listing.salesperson_name != (operator_name or actor_name):
        raise PermissionError("listing record does not belong to current operator")
    if listing.status == "voided":
        raise ValueError("voided listing cannot be edited")
    if "status" in payload.model_fields_set and not actor_is_manager:
        raise PermissionError("only managers can void a listing")
    check_day = today or datetime.now(EXCEL_TIMEZONE).date()
    periods = list(
        db.scalars(
            select(models.ItemObservationPeriod)
            .where(
                models.ItemObservationPeriod.listing_record_id == listing.id,
                models.ItemObservationPeriod.record_source == "platform",
            )
            .order_by(models.ItemObservationPeriod.week_number)
        )
    )
    has_metrics = any(period.metrics_fetched_at is not None for period in periods)
    changed: list[str] = []
    original_pair = (listing.shop, listing.item)
    for field in ("shop", "item", "listing_strategy"):
        if field not in payload.model_fields_set:
            continue
        value = (getattr(payload, field) or "").strip()
        if not value:
            raise ValueError(f"{field} is required")
        if has_metrics and field in {"shop", "item"} and value != getattr(listing, field):
            raise ValueError(f"{field} cannot be changed after weekly metrics exist")
        setattr(listing, field, value)
        changed.append(field)
    if (listing.shop, listing.item) != original_pair and db.scalar(
        select(models.ListingRecord.id).where(
            models.ListingRecord.shop == listing.shop,
            models.ListingRecord.item == listing.item,
            models.ListingRecord.status == "active",
            models.ListingRecord.id != listing.id,
        )
    ):
        raise ValueError("item already exists")
    if "first_period_start" in payload.model_fields_set:
        if has_metrics:
            raise ValueError("first_period_start cannot be changed after weekly metrics exist")
        try:
            first_start = date.fromisoformat(payload.first_period_start or "")
            validate_selectable_period_start(first_start, check_day)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        _replan_periods(db, periods, first_start)
        listing.first_period_start = first_start
        listing.first_period_end = first_start + timedelta(days=6)
        changed.append("first_period_start")
    if "tracking_status" in payload.model_fields_set and payload.tracking_status != listing.tracking_status:
        if payload.tracking_status == "stopped":
            listing.tracking_status = "stopped"
            listing.stopped_at = models.now_utc()
            action = "listing.stopped"
        elif payload.tracking_status == "active" and listing.tracking_status == "stopped":
            last_fetched_week = max(
                (period.week_number for period in periods if period.status != "pending_data"),
                default=0,
            )
            pending = [
                period
                for period in periods
                if period.status == "pending_data" and period.week_number > last_fetched_week
            ]
            fixed = [period for period in periods if period not in pending]
            next_start = current_business_period_start(check_day) + timedelta(days=7)
            if fixed:
                next_start = max(next_start, max(period.period_start for period in fixed) + timedelta(days=7))
            _replan_periods(db, pending, next_start)
            listing.tracking_status = "active"
            listing.resumed_at = models.now_utc()
            action = "listing.resumed"
        else:
            raise ValueError("tracking_status must be active or stopped")
        audit(db, action, "listing_record", listing.id, {}, actor_name, actor_user_id)
    if "status" in payload.model_fields_set:
        if payload.status != "voided":
            raise ValueError("status must be voided")
        reason = (payload.void_reason or "").strip()
        if not reason:
            raise ValueError("void_reason is required")
        listing.status = "voided"
        listing.tracking_status = "stopped"
        listing.void_reason = reason
        listing.voided_at = models.now_utc()
        audit(db, "listing.voided", "listing_record", listing.id, {"reason": reason}, actor_name, actor_user_id)
    if changed:
        audit(db, "listing.updated", "listing_record", listing.id, {"fields": changed}, actor_name, actor_user_id)
    return listing


def _replan_periods(db: Session, periods: list[models.ItemObservationPeriod], first_start: date) -> None:
    if not periods:
        return
    temporary_start = date(2099, 1, 1)
    for index, period in enumerate(periods):
        period.period_start = temporary_start + timedelta(days=7 * index)
        period.period_end = period.period_start + timedelta(days=6)
    db.flush()
    for index, period in enumerate(sorted(periods, key=lambda item: item.week_number)):
        period.period_start = first_start + timedelta(days=7 * index)
        period.period_end = period.period_start + timedelta(days=6)


def add_observation_period(
    db: Session,
    listing_id: str,
    period_start: date,
    actor_name: str,
    actor_user_id: str | None,
    actor_is_manager: bool,
    operator_name: str | None = None,
    today: date | None = None,
) -> models.ItemObservationPeriod:
    listing = db.get(models.ListingRecord, listing_id)
    if listing is None:
        raise LookupError("listing record not found")
    if not actor_is_manager and listing.salesperson_name != (operator_name or actor_name):
        raise PermissionError("listing record does not belong to current operator")
    if listing.status != "active" or listing.tracking_status != "active":
        raise ValueError("only active tracked listings can add periods")
    if listing.initial_observation_completed_at is None:
        raise ValueError("first round must be completed before adding a period")
    validate_selectable_period_start(period_start, today or datetime.now(EXCEL_TIMEZONE).date())
    periods = list(
        db.scalars(
            select(models.ItemObservationPeriod).where(
                models.ItemObservationPeriod.listing_record_id == listing.id,
                models.ItemObservationPeriod.record_source == "platform",
            )
        )
    )
    if any(period.period_start == period_start for period in periods):
        raise ValueError("period_start already exists")
    period = models.ItemObservationPeriod(
        id=models.new_id(),
        listing_record_id=listing.id,
        week_number=max(period.week_number for period in periods) + 1,
        period_start=period_start,
        period_end=period_start + timedelta(days=6),
    )
    db.add(period)
    audit(
        db,
        "observation.period_added",
        "item_observation_period",
        period.id,
        {"week_number": period.week_number, "period_start": period_start.isoformat()},
        actor_name,
        actor_user_id,
    )
    db.flush()
    return period


def recompute_listing_binding_state(db: Session, listing: models.ListingRecord) -> None:
    bindings = list(
        db.scalars(
            select(models.ListingSkuBinding).where(models.ListingSkuBinding.listing_record_id == listing.id)
        )
    )
    main_skus = sorted({binding.main_sku for binding in bindings})
    sub_skus = sorted({binding.sub_sku for binding in bindings if binding.sub_sku})
    listing.is_shared_item = len(main_skus) > 1 or len(sub_skus) > 1
    if len(bindings) <= 1:
        listing.representative_rule = "single_binding"
    elif any(binding.claim_record_id for binding in bindings):
        listing.representative_rule = "platform_claim"
    else:
        listing.representative_rule = "lexical_first"
    listing.representative_sub_sku = sub_skus[0] if len(sub_skus) == 1 else None


def apply_week_metrics(
    db: Session,
    shop: str,
    item: str,
    period_start: date,
    metrics: dict | None,
    actor_name: str = "weekly_item_import",
) -> models.ItemObservationPeriod | None:
    listing = db.scalars(
        select(models.ListingRecord)
        .where(
            models.ListingRecord.shop == shop.strip(),
            models.ListingRecord.item == item.strip(),
            models.ListingRecord.status == "active",
        )
        .with_for_update()
    ).one_or_none()
    if listing is None:
        return None
    period = db.scalar(
        select(models.ItemObservationPeriod)
        .where(
            models.ItemObservationPeriod.listing_record_id == listing.id,
            models.ItemObservationPeriod.period_start == period_start,
            models.ItemObservationPeriod.record_source == "platform",
        )
        .with_for_update()
    )
    if period is None:
        return None
    if period.metrics_fetched_at is not None:
        return period
    if metrics is None or listing.tracking_status != "active":
        return period
    required = ("order_count", "total_revenue", "gross_profit_amount")
    missing = [field for field in required if field not in metrics or metrics[field] is None]
    if missing:
        raise ValueError(f"weekly metrics missing: {', '.join(missing)}")
    period.order_count = int(metrics["order_count"])
    period.total_revenue = float(metrics["total_revenue"])
    period.gross_profit_amount = float(metrics["gross_profit_amount"])
    period.source_snapshot = metrics.get("source_snapshot") or {key: metrics[key] for key in required}
    period.metrics_fetched_at = models.now_utc()
    if period.status == "pending_data":
        period.status = "pending_review"

    dedupe_key = f"dingtalk_card:observation-period:{period.id}"
    pending_notification = any(
        isinstance(value, models.NotificationLog) and value.dedupe_key == dedupe_key for value in db.new
    )
    if not pending_notification and db.scalar(
        select(models.NotificationLog.id).where(models.NotificationLog.dedupe_key == dedupe_key)
    ) is None:
        db.add(
            models.NotificationLog(
                id=models.new_id(),
                dedupe_key=dedupe_key,
                task_id=period.id,
                receiver_name=listing.salesperson_name,
                channel="work_notice",
                message_title=f"{listing.item} 第{period.week_number}周数据待复盘",
                send_status="pending",
            )
        )
    audit(
        db,
        "observation.metrics_applied",
        "item_observation_period",
        period.id,
        {"item": listing.item, "period_start": period_start.isoformat()},
        actor_name,
    )
    return period


def list_product_board_groups(
    db: Session,
    owner: str | None = None,
    business_period: str | None = None,
    visible_status: str | None = None,
    arrival_date_from: date | None = None,
    arrival_date_to: date | None = None,
    site: str | None = None,
    query: str | None = None,
) -> list[dict]:
    filters = [models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED]
    if business_period:
        filters.append(models.NewProductOpportunity.batch == business_period)
    if site:
        filters.append(or_(models.NewProductOpportunity.site == site, models.NewProductOpportunity.country == site))
    text = (query or "").strip()
    if text:
        like = f"%{text}%"
        matching_task_opportunities = (
            select(models.FlowInstance.opportunity_id)
            .join(models.FlowTask, models.FlowTask.flow_instance_id == models.FlowInstance.id)
            .where(
                models.FlowTask.status == TASK_PENDING,
                models.FlowTask.task_type == "sales_claim",
                models.FlowTask.assignee_name.like(like),
            )
        )
        filters.append(
            or_(
                models.NewProductOpportunity.main_sku.like(like),
                models.NewProductOpportunity.sub_sku.like(like),
                models.NewProductOpportunity.main_sku_name.like(like),
                models.NewProductOpportunity.sub_sku_name.like(like),
                models.NewProductOpportunity.keyword.like(like),
                models.SalesClaimForecast.salesperson_name.like(like),
                models.NewProductOpportunity.id.in_(matching_task_opportunities),
            )
        )
    pending_task_rows = db.execute(
        select(models.FlowInstance.opportunity_id, models.FlowTask)
        .join(models.FlowTask, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .where(models.FlowTask.status == TASK_PENDING, models.FlowTask.task_type == "sales_claim")
    ).all()
    pending_tasks_by_opportunity: dict[str, list[models.FlowTask]] = defaultdict(list)
    for opportunity_id, task in pending_task_rows:
        if opportunity_id:
            pending_tasks_by_opportunity[opportunity_id].append(task)

    def add_responsibility(group: dict, key: str, item: dict) -> None:
        if key in group["_responsibility_keys"]:
            return
        group["_responsibility_keys"].add(key)
        group["responsibilities"].append(item)

    rows = db.execute(
        select(models.NewProductOpportunity, models.SalesClaimForecast)
        .outerjoin(
            models.SalesClaimForecast,
            (models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
            & (models.SalesClaimForecast.source_column == "platform"),
        )
        .where(*filters)
        .order_by(
            models.NewProductOpportunity.batch.asc(),
            models.NewProductOpportunity.main_sku.asc(),
            models.NewProductOpportunity.sub_sku.asc(),
            models.SalesClaimForecast.created_at.asc(),
        )
    )
    reviewed_opportunity_ids = set(db.scalars(select(models.ReviewRecord.opportunity_id).distinct()))
    groups: dict[tuple[str | None, str | None, str], dict] = {}
    for opportunity, claim in rows:
        review = (
            latest_review_for_claim(db, opportunity.id, claim)
            if claim and opportunity.id in reviewed_opportunity_ids
            else None
        )
        status = responsibility_visible_status(opportunity, claim, review)
        pending_tasks = pending_tasks_by_opportunity.get(opportunity.id, [])
        if visible_status and status != visible_status:
            continue
        if owner and (not claim or claim.salesperson_name != owner) and not any(task.assignee_name == owner for task in pending_tasks):
            continue
        if (arrival_date_from or arrival_date_to) and not _date_in_range(claim.arrival_detected_at if claim else None, arrival_date_from, arrival_date_to):
            continue
        key = (opportunity.batch, normalize_site_code(opportunity.site or opportunity.country), opportunity.main_sku)
        group = groups.setdefault(
            key,
            {
                "key": "|".join(str(part or "") for part in key),
                "business_period": opportunity.batch,
                "site": opportunity.site,
                "country": opportunity.country,
                "main_sku": opportunity.main_sku,
                "main_sku_name": opportunity.main_sku_name,
                "image_url": opportunity.image_url,
                "child_skus": [],
                "responsibilities": [],
                "_child_ids": set(),
                "_responsibility_keys": set(),
            },
        )
        if not group.get("image_url") and opportunity.image_url:
            group["image_url"] = opportunity.image_url
        if opportunity.id not in group["_child_ids"]:
            group["_child_ids"].add(opportunity.id)
            group["child_skus"].append(
                {
                    "opportunity_id": opportunity.id,
                    "sub_sku": opportunity.sub_sku,
                    "sub_sku_name": opportunity.sub_sku_name,
                    "visible_status": status,
                }
            )
        if claim and (not owner or claim.salesperson_name == owner):
            add_responsibility(
                group,
                f"claim:{claim.id}",
                {
                    "claim_record_id": claim.id,
                    "task_id": claim.task_id,
                    "opportunity_id": opportunity.id,
                    "salesperson_name": claim.salesperson_name,
                    "sub_sku": opportunity.sub_sku,
                    "claim_daily_sales": claim.claim_daily_sales,
                    "visible_status": status,
                    "arrival_detected_at": claim.arrival_detected_at,
                },
            )
        claim_owner = claim.salesperson_name if claim else None
        for task in pending_tasks:
            if owner and task.assignee_name != owner:
                continue
            if claim_owner and task.assignee_name == claim_owner:
                continue
            add_responsibility(
                group,
                f"task:{task.id}",
                {
                    "claim_record_id": None,
                    "task_id": task.id,
                    "opportunity_id": opportunity.id,
                    "salesperson_name": task.assignee_name,
                    "sub_sku": opportunity.sub_sku,
                    "claim_daily_sales": None,
                    "visible_status": opportunity.current_status,
                    "arrival_detected_at": None,
                },
            )
    result = []
    for group in groups.values():
        owners = {item["salesperson_name"] for item in group["responsibilities"] if item["salesperson_name"]}
        claimed_children = {item["opportunity_id"] for item in group["responsibilities"]}
        tags = []
        if len(owners) > 1:
            tags.append("multi_owner")
        if claimed_children and len(claimed_children) < len(group["_child_ids"]):
            tags.append("partial_claim")
        group["summary_tags"] = tags
        group.pop("_child_ids")
        group.pop("_responsibility_keys")
        result.append(group)
    return result


def responsibility_visible_status(
    opportunity: models.NewProductOpportunity,
    claim: models.SalesClaimForecast | None,
    review: models.ReviewRecord | None = None,
) -> str:
    if claim and claim.downstream_status:
        return claim.downstream_status
    if claim and claim.claim_result == CLAIM_RESULT_CLAIM and review and review.review_status == REVIEW_APPROVED:
        return CLAIM_WAITING_STOCKING_REQUEST
    return opportunity.current_status


def _date_in_range(value: datetime | None, start: date | None, end: date | None) -> bool:
    if value is None:
        return False
    current = value.date()
    return (start is None or current >= start) and (end is None or current <= end)


SALES_SELF_SELECTION = "sales_self_selection"


def create_sales_self_selection(
    db: Session,
    payload: schemas.SalesSelfSelectionCreate,
    operator_name: str,
    actor_user_id: str | None = None,
) -> list[schemas.OperatorStockingItemRead]:
    main_sku = _clean_text(payload.main_sku)
    country = _clean_text(payload.country)
    children = [(_clean_text(child.sub_sku), child) for child in payload.children]
    if not main_sku or not country or any(not sub_sku for sub_sku, _ in children):
        raise ValueError("main_sku, country, and child sub_sku are required")
    normalized = [sub_sku.casefold() for sub_sku, _ in children if sub_sku]
    if len(normalized) != len(set(normalized)):
        raise ValueError("child sub_sku values must be unique")

    period = f"销售自选{datetime.now(EXCEL_TIMEZONE):%Y%m%d}"
    existing = db.scalar(
        select(models.NewProductOpportunity.id)
        .join(
            models.SalesClaimForecast,
            models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id,
        )
        .where(
            models.NewProductOpportunity.source_type == SALES_SELF_SELECTION,
            models.NewProductOpportunity.batch == period,
            models.NewProductOpportunity.main_sku == main_sku,
            models.NewProductOpportunity.sub_sku.in_([sub_sku for sub_sku, _ in children]),
            models.SalesClaimForecast.salesperson_name == operator_name,
        )
    )
    if existing:
        raise ValueError("sales self selection already exists")

    claims: list[models.SalesClaimForecast] = []
    now = datetime.now(timezone.utc)
    for source_row, (sub_sku, child) in enumerate(children, start=1):
        snapshot = {
            "source": "销售自选",
            "operator_name": operator_name,
            "main_sku": main_sku,
            "main_sku_name": _clean_text(payload.main_sku_name),
            "sub_sku": sub_sku,
            "sub_sku_name": _clean_text(child.sub_sku_name),
            "country": country,
            "inventory_available": child.inventory_available,
            "needs_stocking": child.needs_stocking,
        }
        opportunity = models.NewProductOpportunity(
            source_type=SALES_SELF_SELECTION,
            source_file="平台销售自选",
            source_sheet=period,
            source_row=source_row,
            batch=period,
            country=country,
            site=country,
            main_sku=main_sku,
            main_sku_name=_clean_text(payload.main_sku_name),
            sub_sku=sub_sku,
            sub_sku_name=_clean_text(child.sub_sku_name),
            current_status=OPPORTUNITY_READY_FOR_STOCKING,
            snapshot=snapshot,
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SourceRecordSnapshot(
                opportunity_id=opportunity.id,
                source_file=opportunity.source_file,
                source_sheet=period,
                source_row=source_row,
                column_range="sales_self_selection",
                payload=snapshot,
            )
        )
        claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            platform="Shopee",
            salesperson_name=operator_name,
            claim_result=CLAIM_RESULT_CLAIM,
            source_column="platform",
            claim_source=SALES_SELF_SELECTION,
            inventory_available=child.inventory_available,
            needs_stocking=child.needs_stocking,
            stocking_decision_updated_at=now,
            downstream_status=_stocking_decision_status(child.inventory_available, child.needs_stocking),
        )
        db.add(claim)
        db.flush()
        if child.needs_stocking:
            create_stocking_draft_for_claim(db, claim.id, operator_name)
        audit(
            db,
            "sales_self_selection.created",
            "new_product_opportunity",
            opportunity.id,
            snapshot,
            operator_name,
            actor_user_id,
        )
        claims.append(claim)
    db.flush()
    return [_operator_stocking_item(db, claim) for claim in claims]


def list_operator_stocking_items(db: Session, operator_name: str) -> list[schemas.OperatorStockingItemRead]:
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(
            models.NewProductOpportunity,
            models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id,
        )
        .where(
            models.SalesClaimForecast.salesperson_name == operator_name,
            models.SalesClaimForecast.source_column == "platform",
        )
        .order_by(
            models.NewProductOpportunity.main_sku.asc(),
            models.NewProductOpportunity.sub_sku.asc(),
            models.SalesClaimForecast.created_at.asc(),
        )
    )
    result = []
    for claim, opportunity in rows:
        request = db.scalar(
            select(models.StockingRequest).where(models.StockingRequest.claim_record_id == claim.id)
        )
        if request is None and not (
            opportunity.source_type == SALES_SELF_SELECTION
            and claim.downstream_status in {CLAIM_STOCKING_PAUSED, CLAIM_WAITING_LISTING}
        ):
            continue
        result.append(_operator_stocking_item(db, claim, opportunity, request))
    return result


def update_stocking_request(
    db: Session,
    request_id: str,
    operator_name: str,
    payload: schemas.StockingRequestUpdate,
    actor_user_id: str | None = None,
) -> models.StockingRequest:
    request, claim = _owned_stocking_request(db, request_id, operator_name, lock=True)
    if request.status == "exported":
        raise RuntimeError("exported stocking request is read-only")
    before_status = request.status
    dimension_fields = {"length_cm", "width_cm", "height_cm"}
    changed_fields = set(payload.model_fields_set)
    if dimension_fields & changed_fields:
        changed_fields.update({"unit_volume", "unit_volume_source"})
    before = {
        field: value.isoformat() if isinstance((value := getattr(request, field)), (date, datetime)) else value
        for field in changed_fields
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in {"country", "warehouse", "reason"}:
            value = _clean_text(value)
        setattr(request, field, value)
    dimension_values = (
        request.length_cm,
        request.width_cm,
        request.height_cm,
    )
    if dimension_fields & payload.model_fields_set and (
        any(value is not None for value in dimension_values) or "unit_volume" not in payload.model_fields_set
    ):
        if all(value is not None for value in dimension_values):
            request.unit_volume = round(request.length_cm * request.width_cm * request.height_cm / 1_000_000, 12)
            request.unit_volume_source = "manual"
        else:
            request.unit_volume = None
            request.unit_volume_source = None
    elif "unit_volume" in payload.model_fields_set:
        request.unit_volume_source = None if request.unit_volume is None else payload.unit_volume_source or "manual"
    elif "unit_volume_source" in payload.model_fields_set:
        request.unit_volume_source = payload.unit_volume_source if request.unit_volume is not None else None
    _recalculate_stocking_request(request)
    after = {
        field: value.isoformat() if isinstance((value := getattr(request, field)), (date, datetime)) else value
        for field in changed_fields
    }
    semantic_changed_fields = {
        field for field in changed_fields if before[field] != after[field]
    }
    if not semantic_changed_fields:
        db.flush()
        return request
    if before_status == "submitted":
        request.status = "draft"
        claim.downstream_status = CLAIM_WAITING_STOCKING_REQUEST
    audit(
        db,
        "stocking.request_updated",
        "stocking_request",
        request.id,
        {
            "status_before": before_status,
            "status_after": request.status,
            "before": {field: before[field] for field in semantic_changed_fields},
            "after": {field: after[field] for field in semantic_changed_fields},
        },
        operator_name,
        actor_user_id,
    )
    db.flush()
    return request


def submit_stocking_request(
    db: Session,
    request_id: str,
    operator_name: str,
    actor_user_id: str | None = None,
) -> models.StockingRequest:
    request, claim = _owned_stocking_request(db, request_id, operator_name, lock=True)
    if request.status == "exported":
        raise RuntimeError("exported stocking request is read-only")
    opportunity = db.get(models.NewProductOpportunity, claim.opportunity_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    if opportunity.source_type == SALES_SELF_SELECTION and claim.needs_stocking is not True:
        raise RuntimeError("sales self selection does not need stocking")
    errors = []
    if request.request_type not in {"initial", "replenishment"}:
        errors.append("request_type")
    for field in ("application_date", "cost_price", "unit_volume", "daily_sales"):
        value = getattr(request, field)
        if value is None or (field != "application_date" and (not math.isfinite(value) or value <= 0)):
            errors.append(field)
    request.country = _clean_text(request.country)
    request.warehouse = _clean_text(request.warehouse)
    request.reason = _clean_text(request.reason)
    if not request.country:
        errors.append("country")
    if request.request_type == "replenishment" and not request.reason:
        errors.append("reason")
    if errors:
        raise ValueError(f"required stocking fields: {', '.join(errors)}")
    _recalculate_stocking_request(request)
    request.status = "submitted"
    request.submitted_at = datetime.now(timezone.utc)
    claim.claim_daily_sales = request.daily_sales
    claim.downstream_status = CLAIM_WAITING_EXPORT
    audit(
        db,
        "stocking.request_submitted",
        "stocking_request",
        request.id,
        {"quantity": request.quantity, "amount": request.amount, "volume": request.volume},
        operator_name,
        actor_user_id,
    )
    db.flush()
    return request


def update_stocking_decision(
    db: Session,
    claim_record_id: str,
    operator_name: str,
    payload: schemas.StockingDecisionUpdate,
    actor_user_id: str | None = None,
) -> schemas.OperatorStockingItemRead:
    request = db.scalar(
        select(models.StockingRequest)
        .where(models.StockingRequest.claim_record_id == claim_record_id)
        .with_for_update()
    )
    claim = db.scalar(
        select(models.SalesClaimForecast)
        .where(models.SalesClaimForecast.id == claim_record_id)
        .with_for_update()
    )
    if claim is None:
        raise LookupError("claim record not found")
    if claim.salesperson_name != operator_name:
        raise PermissionError("claim record belongs to another operator")
    opportunity = db.get(models.NewProductOpportunity, claim.opportunity_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    if opportunity.source_type != SALES_SELF_SELECTION:
        raise ValueError("stocking decisions are only available for sales self selections")
    if request is not None and (
        request.status in {"submitted", "exported"} or request.submitted_at is not None
    ):
        raise RuntimeError("submitted stocking request decision is read-only")
    claim.inventory_available = payload.inventory_available
    claim.needs_stocking = payload.needs_stocking
    claim.stocking_decision_updated_at = datetime.now(timezone.utc)
    claim.downstream_status = _stocking_decision_status(payload.inventory_available, payload.needs_stocking)
    if payload.needs_stocking:
        request = request or create_stocking_draft_for_claim(db, claim.id, operator_name)
    elif request is not None:
        request.status = "draft"
        request.submitted_at = None
    audit(
        db,
        "stocking.decision_updated",
        "sales_claim_forecast",
        claim.id,
        payload.model_dump(),
        operator_name,
        actor_user_id,
    )
    db.flush()
    return _operator_stocking_item(db, claim, opportunity, request)


def _stocking_decision_status(inventory_available: bool, needs_stocking: bool) -> str:
    if needs_stocking:
        return CLAIM_WAITING_STOCKING_REQUEST
    return CLAIM_WAITING_LISTING if inventory_available else CLAIM_STOCKING_PAUSED


def _owned_stocking_request(
    db: Session,
    request_id: str,
    operator_name: str,
    lock: bool = False,
) -> tuple[models.StockingRequest, models.SalesClaimForecast]:
    query = select(models.StockingRequest).where(models.StockingRequest.id == request_id)
    if lock:
        query = query.with_for_update()
    request = db.scalar(query)
    if request is None:
        raise LookupError("stocking request not found")
    claim_query = select(models.SalesClaimForecast).where(
        models.SalesClaimForecast.id == request.claim_record_id
    )
    if lock:
        claim_query = claim_query.with_for_update()
    claim = db.scalar(claim_query)
    if claim is None:
        raise LookupError("claim record not found")
    if claim.salesperson_name != operator_name or request.salesperson_name != operator_name:
        raise PermissionError("stocking request belongs to another operator")
    return request, claim


def _recalculate_stocking_request(request: models.StockingRequest) -> None:
    request.quantity = (
        stocking_quantity(request.daily_sales)
        if request.daily_sales is not None and request.daily_sales > 0
        else 0
    )
    request.amount = (
        request.cost_price * request.quantity
        if request.cost_price is not None and request.cost_price > 0 and request.quantity > 0
        else None
    )
    request.volume = (
        request.unit_volume * request.quantity
        if request.unit_volume is not None and request.unit_volume > 0 and request.quantity > 0
        else None
    )


def _operator_stocking_item(
    db: Session,
    claim: models.SalesClaimForecast,
    opportunity: models.NewProductOpportunity | None = None,
    request: models.StockingRequest | None = None,
) -> schemas.OperatorStockingItemRead:
    opportunity = opportunity or db.get(models.NewProductOpportunity, claim.opportunity_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    if request is None:
        request = db.scalar(
            select(models.StockingRequest).where(models.StockingRequest.claim_record_id == claim.id)
        )
    return schemas.OperatorStockingItemRead(
        opportunity_id=opportunity.id,
        claim_record_id=claim.id,
        request_id=request.id if request else None,
        business_period=opportunity.batch,
        country=opportunity.country,
        source_type=opportunity.source_type,
        salesperson_name=claim.salesperson_name or "",
        main_sku=opportunity.main_sku,
        main_sku_name=opportunity.main_sku_name,
        sub_sku=opportunity.sub_sku,
        sub_sku_name=opportunity.sub_sku_name,
        inventory_available=claim.inventory_available,
        needs_stocking=claim.needs_stocking,
        downstream_status=claim.downstream_status or "",
        request=request,
    )

def stocking_quantity(daily_sales: float) -> int:
    return math.ceil(daily_sales * 30)


def stocking_totals(cost_price: float, unit_volume: float, quantity: int) -> tuple[float, float]:
    return cost_price * quantity, unit_volume * quantity


def create_stocking_draft_for_claim(
    db: Session,
    claim_record_id: str,
    actor_name: str | None = None,
) -> models.StockingRequest:
    existing = db.scalar(
        select(models.StockingRequest).where(models.StockingRequest.claim_record_id == claim_record_id)
    )
    if existing:
        return existing
    claim = db.get(models.SalesClaimForecast, claim_record_id)
    if claim is None:
        raise LookupError("claim record not found")
    opportunity = db.get(models.NewProductOpportunity, claim.opportunity_id)
    if opportunity is None:
        raise LookupError("opportunity not found")
    quantity = stocking_quantity(claim.claim_daily_sales) if claim.claim_daily_sales is not None else 0
    cost_price = number_value(central_field_value(opportunity, "商品成本-含税（元）"))
    request = models.StockingRequest(
        opportunity_id=opportunity.id,
        claim_record_id=claim.id,
        application_date=datetime.now(EXCEL_TIMEZONE).date(),
        salesperson_name=claim.salesperson_name,
        main_sku=opportunity.main_sku,
        sub_sku=opportunity.sub_sku,
        cost_price=cost_price,
        unit_volume=None,
        daily_sales=claim.claim_daily_sales,
        quantity=quantity,
        country=opportunity.country,
        amount=cost_price * quantity if cost_price is not None else None,
        volume=None,
        status="draft",
    )
    db.add(request)
    db.flush()
    audit(db, "stocking.draft_created", "stocking_request", request.id, {"quantity": quantity}, actor_name)
    return request


def create_stocking_draft_from_claim(
    db: Session,
    opportunity_id: str,
    actor_name: str | None = None,
) -> models.StockingRequest | None:
    claim = db.scalar(
        select(models.SalesClaimForecast)
        .where(
            models.SalesClaimForecast.opportunity_id == opportunity_id,
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
        )
        .order_by(models.SalesClaimForecast.created_at.desc())
    )
    if claim is None or claim.claim_daily_sales is None:
        return None
    return create_stocking_draft_for_claim(db, claim.id, actor_name)


def _stocking_source_label(opportunity: models.NewProductOpportunity) -> str:
    return {
        "selection1_developer_claim_feedback": "选品1",
        "selection2_caigen_claim_feedback": "选品2/财根",
        SALES_SELF_SELECTION: "销售自选",
    }.get(opportunity.source_type, opportunity.source_type)


def _available_stocking_item(
    opportunity: models.NewProductOpportunity,
    claim: models.SalesClaimForecast,
    request: models.StockingRequest,
) -> schemas.AvailableStockingItem:
    return schemas.AvailableStockingItem(
        opportunity_id=opportunity.id,
        request_id=request.id,
        claim_record_id=claim.id,
        business_period=opportunity.batch,
        time=request.submitted_at,
        application_date=request.application_date,
        stocking_type="补货" if request.request_type == "replenishment" else "首次备货",
        selection_source=_stocking_source_label(opportunity),
        salesperson_name=request.salesperson_name,
        main_sku=request.main_sku or "",
        sub_sku=request.sub_sku or "",
        site=opportunity.site,
        claim_daily_sales=request.daily_sales or 0,
        quantity=request.quantity,
        stocking_country=request.country,
        warehouse=request.warehouse,
        cost_price=request.cost_price,
        unit_volume=request.unit_volume,
        amount=request.amount,
        volume=request.volume,
        replenishment_reason=request.reason,
        status=request.status,
    )


def list_available_stocking_items(
    db: Session,
    source_sheet: str | None = None,
    business_period: str | None = None,
    import_batch_id: str | None = None,
) -> list[schemas.AvailableStockingItem]:
    filters = [
        models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
        models.StockingRequest.status == "submitted",
        models.StockingRequest.opportunity_id == models.NewProductOpportunity.id,
        models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
        models.SalesClaimForecast.source_column == "platform",
        models.SalesClaimForecast.downstream_status == CLAIM_WAITING_EXPORT,
    ]
    if business_period:
        filters.append(models.NewProductOpportunity.batch == business_period)
    elif source_sheet:
        filters.append(or_(models.NewProductOpportunity.batch == source_sheet, models.NewProductOpportunity.source_sheet == source_sheet))
    if import_batch_id:
        filters.append(models.NewProductOpportunity.import_batch_id == import_batch_id)
    rows = db.execute(
        select(models.NewProductOpportunity, models.SalesClaimForecast, models.StockingRequest)
        .join(models.SalesClaimForecast, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
        .join(models.StockingRequest, models.StockingRequest.claim_record_id == models.SalesClaimForecast.id)
        .where(*filters)
        .order_by(models.NewProductOpportunity.updated_at.desc(), models.StockingRequest.id)
    ).all()
    return [_available_stocking_item(opportunity, claim, request) for opportunity, claim, request in rows]


def lock_selected_stocking_items(
    db: Session,
    request_ids: list[str],
) -> list[schemas.AvailableStockingItem]:
    requests = list(db.scalars(
        select(models.StockingRequest)
        .where(models.StockingRequest.id.in_(request_ids))
        .order_by(models.StockingRequest.id)
        .with_for_update()
    ))
    if len(requests) != len(request_ids):
        raise LookupError("stocking request not found")
    request_by_id = {request.id: request for request in requests}

    claim_ids = [request.claim_record_id for request in requests if request.claim_record_id]
    claims = list(db.scalars(
        select(models.SalesClaimForecast)
        .where(models.SalesClaimForecast.id.in_(claim_ids))
        .order_by(models.SalesClaimForecast.id)
        .with_for_update()
    ))
    claim_by_id = {claim.id: claim for claim in claims}

    opportunity_ids = sorted({request.opportunity_id for request in requests})
    opportunities = list(db.scalars(
        select(models.NewProductOpportunity)
        .where(models.NewProductOpportunity.id.in_(opportunity_ids))
        .order_by(models.NewProductOpportunity.id)
        .with_for_update()
    ))
    opportunity_by_id = {opportunity.id: opportunity for opportunity in opportunities}

    items = []
    for request_id in request_ids:
        request = request_by_id[request_id]
        claim = claim_by_id.get(request.claim_record_id or "")
        opportunity = opportunity_by_id.get(request.opportunity_id)
        if request.status != "submitted" or claim is None or claim.downstream_status != CLAIM_WAITING_EXPORT:
            raise RuntimeError("stocking request is not available for export")
        if (
            opportunity is None
            or opportunity.current_status == OPPORTUNITY_DISABLED
            or claim.claim_result != CLAIM_RESULT_CLAIM
            or claim.source_column != "platform"
            or claim.opportunity_id != request.opportunity_id
        ):
            raise RuntimeError("stocking request is not available for export")
        items.append(_available_stocking_item(opportunity, claim, request))
    return items


def build_available_stocking_workbook(items: list[schemas.AvailableStockingItem]) -> bytes:
    headers = [
        "操作状态", "申请日期", "备货类型", "选品数据源", "销售员", "主SKU", "子sku", "成本价",
        "单个体积", "备货单销", "备货数量", "备货国家", "备货仓库", "货值", "体积", "补货原因",
    ]
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, sheet_items in export_sheet_groups(items, "备货申请表"):
        worksheet = workbook.create_sheet(title=sheet_name)
        worksheet.append(headers)
        for item in sheet_items:
            worksheet.append([
                None, item.application_date, item.stocking_type, item.selection_source,
                item.salesperson_name, item.main_sku, item.sub_sku, item.cost_price,
                item.unit_volume, item.claim_daily_sales, item.quantity, item.stocking_country,
                item.warehouse, item.amount, item.volume, item.replenishment_reason,
            ])
        style_worksheet(worksheet, max_width=32, fill="D9EAF7")
        for cell in worksheet["B"][1:]:
            cell.number_format = "yyyy-mm-dd"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def record_export_batch(
    db: Session,
    items: list[schemas.AvailableStockingItem],
    file_name: str,
    scope: str,
    exported_by: str = "system",
    extra_row_count: int = 0,
    extra_rows: list[tuple[models.NewProductOpportunity, models.SalesClaimForecast]] | None = None,
) -> models.ExportBatch:
    extra_rows = extra_rows or []
    row_count = len(items) + extra_row_count
    batch = models.ExportBatch(exported_by=exported_by, file_name=file_name, scope=scope, row_count=row_count)
    db.add(batch)
    db.flush()
    for item in items:
        db.add(models.ExportRow(
            export_batch_id=batch.id,
            opportunity_id=item.opportunity_id,
            claim_record_id=item.claim_record_id,
            stocking_request_id=item.request_id,
            application_date=item.application_date,
            stocking_type="replenishment" if item.stocking_type == "补货" else "initial",
            selection_source=item.selection_source if scope == "stocking_available" else None,
            cost_price=item.cost_price,
            unit_volume=item.unit_volume,
            amount=item.amount,
            volume=item.volume,
            replenishment_reason=item.replenishment_reason,
            salesperson_name=item.salesperson_name,
            main_sku=item.main_sku,
            sub_sku=item.sub_sku,
            claim_daily_sales=item.claim_daily_sales,
            stocking_quantity=item.quantity,
            country=item.stocking_country,
            warehouse=item.warehouse,
        ))
        if scope == "stocking_available":
            request = db.get(models.StockingRequest, item.request_id)
            claim = db.get(models.SalesClaimForecast, item.claim_record_id)
            if request and request.status == "submitted" and claim and claim.downstream_status == CLAIM_WAITING_EXPORT:
                request.status = "exported"
                claim.downstream_status = CLAIM_WAITING_ARRIVAL
    for opportunity, claim in extra_rows:
        db.add(models.ExportRow(
            export_batch_id=batch.id,
            opportunity_id=opportunity.id,
            claim_record_id=claim.id,
            salesperson_name=claim.salesperson_name,
            main_sku=opportunity.main_sku,
            sub_sku=opportunity.sub_sku,
            claim_daily_sales=claim.claim_daily_sales or 0,
            stocking_quantity=0,
            country=opportunity.country,
            warehouse=None,
        ))

    audit(db, "export.created", "export_batch", batch.id, {"scope": scope, "row_count": row_count}, exported_by)
    return batch


SOURCE_EXPORT_META_HEADERS = [
    "source_file",
    "source_sheet",
    "source_row",
    "import_batch_id",
    "opportunity_id",
    "main_sku",
    "sub_sku",
    "current_status",
]


def list_source_snapshot_rows(
    db: Session,
    source_sheet: str | None = None,
    business_period: str | None = None,
    import_batch_id: str | None = None,
) -> list[tuple[models.NewProductOpportunity, models.SourceRecordSnapshot | None]]:
    query = (
        select(models.NewProductOpportunity, models.SourceRecordSnapshot)
        .outerjoin(models.SourceRecordSnapshot, models.SourceRecordSnapshot.opportunity_id == models.NewProductOpportunity.id)
        .order_by(
            models.NewProductOpportunity.source_sheet,
            models.NewProductOpportunity.source_row,
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
        )
    )
    if business_period:
        query = query.where(models.NewProductOpportunity.batch == business_period)
    elif source_sheet:
        query = query.where(or_(models.NewProductOpportunity.batch == source_sheet, models.NewProductOpportunity.source_sheet == source_sheet))
    if import_batch_id:
        query = query.where(models.NewProductOpportunity.import_batch_id == import_batch_id)
    return list(db.execute(query).all())


def build_source_snapshot_workbook(rows: list[tuple[models.NewProductOpportunity, models.SourceRecordSnapshot | None]]) -> bytes:
    payloads = [source_export_fields(snapshot.payload if snapshot else opportunity.snapshot) for opportunity, snapshot in rows]
    dynamic_headers: list[str] = []
    for payload in payloads:
        for key in payload:
            if key not in SOURCE_EXPORT_META_HEADERS and key not in dynamic_headers:
                dynamic_headers.append(key)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "source data"
    headers = SOURCE_EXPORT_META_HEADERS + dynamic_headers
    worksheet.append(headers)
    for (opportunity, snapshot), payload in zip(rows, payloads):
        worksheet.append(
            [
                snapshot.source_file if snapshot else opportunity.source_file,
                snapshot.source_sheet if snapshot else opportunity.source_sheet,
                snapshot.source_row if snapshot else opportunity.source_row,
                snapshot.import_batch_id if snapshot else opportunity.import_batch_id,
                opportunity.id,
                opportunity.main_sku,
                opportunity.sub_sku,
                opportunity.current_status,
            ]
            + [excel_value(payload.get(header)) for header in dynamic_headers]
        )
    style_worksheet(worksheet, max_width=36, fill="E2F0D9")
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def source_export_fields(payload: dict | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    fields = payload.get("fields_by_header")
    if isinstance(fields, dict) and fields:
        return {str(key): value for key, value in fields.items() if value not in (None, "")}
    fields = payload.get("fields_by_column")
    if isinstance(fields, dict) and fields:
        return {f"col_{key}": value for key, value in fields.items() if value not in (None, "")}
    return {
        str(key): value
        for key, value in payload.items()
        if value not in (None, "") and not isinstance(value, (dict, list))
    }


MARKET_MONITOR_COLUMNS = [
    ("A", "调研时间"),
    ("B", "货品"),
    ("C", "国家"),
    ("D", "销售员"),
    ("E", "主SKU"),
    ("F", "子sku"),
    ("G", "商品名称"),
    ("H", "一级类目"),
    ("I", "二级类目"),
    ("J", "海外仓成本"),
    ("K", "真实头程运费"),
    ("L", "计算头程"),
    ("M", "长(cm)-无头程填写"),
    ("N", "宽(cm)-无头程填写"),
    ("O", "高(cm)-无头程填写"),
    ("P", "关键词"),
    ("Q", "销售备注"),
    ("R", "最低价竞品链接1"),
    ("S", "竞品单价"),
    ("T", "竞品子sku月销"),
    ("U", "月销最高竞品链接2"),
    ("V", "竞品单价"),
    ("W", "竞品子sku月销"),
    ("X", "新晋竞品链接3"),
    ("Y", "竞品单价"),
    ("Z", "竞品子sku月销"),
    ("AA", "竞对参考单销"),
    ("AB", "竞对参考售价"),
    ("AC", "海外仓一次毛利率"),
    ("AD", "产品类型"),
    ("AE", "稳定期定价"),
    ("AF", "一次毛利额（人民币）"),
    ("AG", "稳定期利润率"),
    ("AH", "推广期定价"),
    ("AI", "推广期利润率"),
    ("AJ", "认领单销"),
    ("AK", "调研结论"),
    ("AL", "二次调研时间"),
    ("AM", "二次竞对链接"),
    ("AN", "二次调研结论"),
    ("AO", "产品定位"),
]

MARKET_MONITOR_HEADERS = [header for _, header in MARKET_MONITOR_COLUMNS]

MARKET_MONITOR_SOURCE_FIELDS: dict[str, tuple[list[str], str | None]] = {
    "A": (["调研时间"], None),
    "I": (["二级类目"], None),
    "J": (["海外仓成本", "商品成本-含税（元）", "进价"], None),
    "K": (["真实头程运费"], None),
    "L": (["计算头程"], None),
    "M": (["长(cm)-无头程填写", "产品包装后体积长(cm)"], "V"),
    "N": (["宽(cm)-无头程填写", "产品包装后体积宽(cm)"], "W"),
    "O": (["高(cm)-无头程填写", "产品包装后体积高(cm)"], "X"),
    "P": (["关键词"], None),
    "Q": (["销售备注"], None),
    "R": (["最低价竞品链接1", "最低价链接"], "Z"),
    "S": (["竞品单价", "售价1", "售价1(PHP）"], "AA"),
    "T": (["竞品子sku月销", "月销1"], "AB"),
    "U": (["月销最高竞品链接2", "月销最高链接链接", "most orders链接"], "AC"),
    "V": (["售价2", "售价2(PHP）"], "AD"),
    "W": (["月销2"], "AE"),
    "X": (["新晋竞品链接3", "新晋链接"], "AL"),
    "Y": (["售价3", "售价3(PHP）"], "AM"),
    "Z": (["月销3"], "AN"),
    "AA": (["竞对参考单销", "参考单销"], "AO"),
    "AB": (["竞对参考售价", "参考定价", "稳定期定价"], "AP"),
    "AC": (["海外仓一次毛利率", "稳定期利润率", "一次毛利率"], None),
    "AD": (["产品类型", "产品类型 / 引流or绑定or利润", "引流or绑定or利润"], "K"),
    "AE": (["稳定期定价", "稳定期定价（PHP）", "参考定价"], "AJ"),
    "AF": (["一次毛利额（人民币）", "一次毛利额\n（人民币）"], "AL"),
    "AG": (["稳定期利润率", "一次毛利率"], "AM"),
    "AH": (["推广期定价"], "AO"),
    "AI": (["推广期利润率"], "AP"),
}

MARKET_MONITOR_TRACEABILITY_HEADERS = [
    "source_file",
    "source_sheet",
    "source_row",
    "business_period",
    "import_batch_id",
    "opportunity_id",
    "claim_record_id",
    "source_snapshot_id",
    "salesperson_name",
    "main_sku",
    "sub_sku",
]


def list_market_monitor_rows(
    db: Session,
    source_sheet: str | None = None,
    business_period: str | None = None,
    import_batch_id: str | None = None,
) -> list[tuple[models.NewProductOpportunity, models.SalesClaimForecast, models.SourceRecordSnapshot | None]]:
    filters = [
        models.NewProductOpportunity.source_type == "selection1_developer_claim_feedback",
        models.SalesClaimForecast.source_column == "platform",
        models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
        models.SalesClaimForecast.secondary_research_submitted_at.is_not(None),
    ]
    if business_period:
        filters.append(models.NewProductOpportunity.batch == business_period)
    elif source_sheet:
        filters.append(or_(models.NewProductOpportunity.batch == source_sheet, models.NewProductOpportunity.source_sheet == source_sheet))
    if import_batch_id:
        filters.append(models.NewProductOpportunity.import_batch_id == import_batch_id)
    rows = db.execute(
        select(models.NewProductOpportunity, models.SalesClaimForecast)
        .join(models.SalesClaimForecast, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
        .where(*filters)
        .order_by(
            models.NewProductOpportunity.batch,
            models.NewProductOpportunity.source_sheet,
            models.NewProductOpportunity.source_row,
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
            models.SalesClaimForecast.salesperson_name,
        )
    ).all()
    return [(opportunity, claim, latest_source_snapshot(db, opportunity.id)) for opportunity, claim in rows]


def latest_source_snapshot(db: Session, opportunity_id: str) -> models.SourceRecordSnapshot | None:
    return db.scalar(
        select(models.SourceRecordSnapshot)
        .where(models.SourceRecordSnapshot.opportunity_id == opportunity_id)
        .order_by(models.SourceRecordSnapshot.created_at.desc(), models.SourceRecordSnapshot.id.desc())
    )


def build_market_monitor_workbook(
    rows: list[tuple[models.NewProductOpportunity, models.SalesClaimForecast, models.SourceRecordSnapshot | None]]
) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    groups: dict[str, list[tuple[models.NewProductOpportunity, models.SalesClaimForecast, models.SourceRecordSnapshot | None]]] = {}
    for row in rows:
        groups.setdefault(market_monitor_sheet_name(row[0]), []).append(row)
    if not groups:
        groups["市场监控"] = []

    for sheet_name in sorted(groups):
        worksheet = workbook.create_sheet(title=safe_sheet_title(sheet_name))
        worksheet.append(MARKET_MONITOR_HEADERS)
        for opportunity, claim, snapshot in groups[sheet_name]:
            worksheet.append(
                [
                    excel_value(market_monitor_value(opportunity, claim, snapshot, column))
                    for column, _header in MARKET_MONITOR_COLUMNS
                ]
            )
        style_worksheet(worksheet, max_width=36, fill="D9EAF7")
        for cell in worksheet["A"][1:] + worksheet["AL"][1:]:
            cell.number_format = "yyyy-mm-dd hh:mm"

    traceability = workbook.create_sheet(title="source_traceability")
    traceability.append(MARKET_MONITOR_TRACEABILITY_HEADERS)
    for opportunity, claim, snapshot in rows:
        traceability.append(
            [
                snapshot.source_file if snapshot else opportunity.source_file,
                snapshot.source_sheet if snapshot else opportunity.source_sheet,
                snapshot.source_row if snapshot else opportunity.source_row,
                opportunity.batch,
                snapshot.import_batch_id if snapshot else opportunity.import_batch_id,
                opportunity.id,
                claim.id,
                snapshot.id if snapshot else None,
                claim.salesperson_name,
                opportunity.main_sku,
                opportunity.sub_sku,
            ]
        )
    style_worksheet(traceability, max_width=36, fill="E2F0D9")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def market_monitor_sheet_name(opportunity: models.NewProductOpportunity) -> str:
    site = normalize_site_code(opportunity.site or opportunity.country) or "未填国家"
    return f"{site}精品" if site != "未填国家" else site


def market_monitor_value(
    opportunity: models.NewProductOpportunity,
    claim: models.SalesClaimForecast,
    snapshot: models.SourceRecordSnapshot | None,
    column: str,
) -> object:
    direct = {
        "B": opportunity.batch or opportunity.source_sheet,
        "C": opportunity.site or opportunity.country,
        "D": claim.salesperson_name,
        "E": opportunity.main_sku,
        "F": opportunity.sub_sku,
        "G": opportunity.sub_sku_name or opportunity.main_sku_name,
        "H": opportunity.category_level1,
        "AJ": claim.claim_daily_sales,
        "AK": claim.feedback_summary,
        "AL": claim.secondary_research_at,
        "AM": claim.secondary_competitor_url,
        "AN": claim.secondary_conclusion,
        "AO": claim.product_positioning,
    }
    if column in direct:
        return direct[column]
    aliases, fallback_column = MARKET_MONITOR_SOURCE_FIELDS.get(column, ([], None))
    value = market_monitor_source_value(opportunity, snapshot, aliases, fallback_column)
    if value is not None:
        return value
    if column == "P":
        return opportunity.keyword
    return None


def market_monitor_source_value(
    opportunity: models.NewProductOpportunity,
    snapshot: models.SourceRecordSnapshot | None,
    aliases: list[str],
    fallback_column: str | None,
) -> object:
    payloads = []
    if snapshot and isinstance(snapshot.payload, dict):
        payloads.append(snapshot.payload)
    if isinstance(opportunity.snapshot, dict):
        payloads.append(opportunity.snapshot)

    alias_keys = {normalize_header(alias) for alias in aliases}
    for payload in payloads:
        for field_name in ("central_fields", "fields_by_header"):
            fields = payload.get(field_name)
            if not isinstance(fields, dict):
                continue
            for key in aliases:
                value = fields.get(key)
                if value not in (None, ""):
                    return value
            for key in alias_keys:
                value = fields.get(key)
                if value not in (None, ""):
                    return value
        if fallback_column:
            for field_name in ("fields_by_column", "cells"):
                fields = payload.get(field_name)
                if isinstance(fields, dict):
                    value = fields.get(fallback_column)
                    if value not in (None, ""):
                        return value
    return None


def list_not_claim_traceability_rows(
    db: Session,
    source_sheet: str | None = None,
    business_period: str | None = None,
    import_batch_id: str | None = None,
) -> list[tuple[models.NewProductOpportunity, models.SalesClaimForecast, models.ReviewRecord | None]]:
    filters = [
        models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
        models.SalesClaimForecast.claim_result == CLAIM_RESULT_REJECT,
        models.SalesClaimForecast.source_column == "platform",
    ]
    if business_period:
        filters.append(models.NewProductOpportunity.batch == business_period)
    elif source_sheet:
        filters.append(or_(models.NewProductOpportunity.batch == source_sheet, models.NewProductOpportunity.source_sheet == source_sheet))
    if import_batch_id:
        filters.append(models.NewProductOpportunity.import_batch_id == import_batch_id)
    rows = db.execute(
        select(models.NewProductOpportunity, models.SalesClaimForecast)
        .join(models.SalesClaimForecast, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
        .where(*filters)
        .order_by(
            models.NewProductOpportunity.updated_at.desc(),
            models.SalesClaimForecast.last_updated_at.desc(),
            models.SalesClaimForecast.created_at.desc(),
        )
    ).all()
    output = []
    for opportunity, claim in rows:
        review = latest_review_for_claim(db, opportunity.id, claim)
        if review and review.review_status == REVIEW_CONFIRMED_NOT_CLAIM:
            output.append((opportunity, claim, review))
    return output


def list_export_period_summaries(db: Session) -> list[schemas.ExportPeriodSummary]:
    imported_periods = db.execute(
        select(models.ImportBatch.business_period, func.max(models.ImportBatch.imported_at))
        .where(models.ImportBatch.status != "disabled", models.ImportBatch.business_period.is_not(None))
        .group_by(models.ImportBatch.business_period)
        .order_by(func.max(models.ImportBatch.imported_at).desc())
    ).all()
    stocking_counts: defaultdict[str, int] = defaultdict(int)
    for item in list_available_stocking_items(db):
        if item.business_period:
            stocking_counts[item.business_period] += 1
    confirmed_reject_counts: defaultdict[str, int] = defaultdict(int)
    for opportunity, _, _ in list_not_claim_traceability_rows(db):
        if opportunity.batch:
            confirmed_reject_counts[opportunity.batch] += 1

    summaries = [
        schemas.ExportPeriodSummary(
            business_period=business_period,
            latest_imported_at=latest_imported_at,
            stocking_count=stocking_counts[business_period],
            traceability_count=stocking_counts[business_period] + confirmed_reject_counts[business_period],
        )
        for business_period, latest_imported_at in imported_periods
    ]
    imported_period_names = {business_period for business_period, _ in imported_periods}
    for business_period in sorted((set(stocking_counts) | set(confirmed_reject_counts)) - imported_period_names):
        summaries.append(
            schemas.ExportPeriodSummary(
                business_period=business_period,
                stocking_count=stocking_counts[business_period],
                traceability_count=stocking_counts[business_period] + confirmed_reject_counts[business_period],
            )
        )
    return summaries


def build_traceability_workbook(
    db: Session,
    items: list[schemas.AvailableStockingItem],
    scope: str = "traceability",
    export_batch: models.ExportBatch | None = None,
    not_claim_rows: list[tuple[models.NewProductOpportunity, models.SalesClaimForecast, models.ReviewRecord | None]]
    | None = None,
) -> bytes:
    headers = CENTRAL_TRACEABILITY_HEADERS + TRACEABILITY_PLATFORM_HEADERS
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, sheet_items in export_sheet_groups(items, "中央字段导出"):
        worksheet = workbook.create_sheet(title=sheet_name)
        worksheet.append(headers)
        product_images: list[tuple[int, str | None]] = []
        for item in sheet_items:
            opportunity = db.get(models.NewProductOpportunity, item.opportunity_id)
            claim = db.get(models.SalesClaimForecast, item.claim_record_id)
            review = latest_review_for_claim(db, item.opportunity_id, claim) if claim else None
            central_values = [central_field_value(opportunity, header, item, column) for column, header in CENTRAL_TRACEABILITY_COLUMNS]
            product_images.append((worksheet.max_row + 1, opportunity.image_url if opportunity else None))
            central_values[PRODUCT_IMAGE_COLUMN_INDEX] = None
            worksheet.append(
                central_values
                + [
                    opportunity.source_file if opportunity else None,
                    opportunity.source_sheet if opportunity else None,
                    opportunity.source_row if opportunity else None,
                    opportunity.import_batch_id if opportunity else None,
                    item.salesperson_name,
                    claim.claim_result if claim else None,
                    item.claim_daily_sales,
                    claim.reject_reason if claim else None,
                    claim.feedback_summary if claim else None,
                    review.review_status if review else item.review_status,
                    review.review_comment if review else None,
                    excel_value(claim.first_submitted_at) if claim else None,
                    excel_value(claim.last_updated_at) if claim else None,
                    export_batch.id if export_batch else None,
                    export_batch.exported_by if export_batch else None,
                    excel_value(export_batch.exported_at) if export_batch else None,
                    export_batch.file_name if export_batch else None,
                    scope,
                ]
            )
        style_worksheet(worksheet, max_width=36)
        embed_product_images(worksheet, product_images)

    not_claim_rows = not_claim_rows if not_claim_rows is not None else list_not_claim_traceability_rows(db)
    if not_claim_rows:
        worksheet = workbook.create_sheet(title="不认领结果")
        worksheet.append(headers + ["图片附件"])
        product_images = []
        for opportunity, claim, review in not_claim_rows:
            central_values = [central_field_value(opportunity, header, column=column) for column, header in CENTRAL_TRACEABILITY_COLUMNS]
            product_images.append((worksheet.max_row + 1, opportunity.image_url))
            central_values[PRODUCT_IMAGE_COLUMN_INDEX] = None
            worksheet.append(
                central_values
                + [
                    opportunity.source_file,
                    opportunity.source_sheet,
                    opportunity.source_row,
                    opportunity.import_batch_id,
                    claim.salesperson_name,
                    claim.claim_result,
                    claim.claim_daily_sales,
                    claim.reject_reason,
                    claim.feedback_summary,
                    review.review_status if review else None,
                    review.review_comment if review else None,
                    excel_value(claim.first_submitted_at),
                    excel_value(claim.last_updated_at),
                    export_batch.id if export_batch else None,
                    export_batch.exported_by if export_batch else None,
                    excel_value(export_batch.exported_at) if export_batch else None,
                    export_batch.file_name if export_batch else None,
                    "traceability_not_claim",
                    claim_evidence_summary(claim.note),
                ]
            )
        style_worksheet(worksheet, max_width=36, fill="FCE4D6")
        embed_product_images(worksheet, product_images)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def embed_product_images(worksheet, image_rows: list[tuple[int, str | None]]) -> None:
    if not image_rows:
        return
    worksheet.column_dimensions[PRODUCT_IMAGE_COLUMN_LETTER].width = 18
    for row_index, image_url in image_rows:
        data = read_product_image_bytes(image_url)
        if not data:
            continue
        try:
            image = ExcelImage(BytesIO(data))
        except Exception:
            continue
        fit_excel_image(image)
        worksheet.add_image(image, f"{PRODUCT_IMAGE_COLUMN_LETTER}{row_index}")
        worksheet.row_dimensions[row_index].height = max(worksheet.row_dimensions[row_index].height or 0, 60)


def read_product_image_bytes(image_url: str | None) -> bytes | None:
    if not image_url:
        return None
    if image_url.startswith(f"{PUBLIC_UPLOAD_PREFIX}/"):
        root = UPLOADED_SOURCES_ROOT.resolve()
        relative = image_url.removeprefix(f"{PUBLIC_UPLOAD_PREFIX}/").lstrip("/")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        return path.read_bytes()
    if image_url.startswith(("http://", "https://")):
        try:
            data, _content_type = read_oss_object_by_public_url(image_url, allowed_prefixes=("product-images/",))
            return data
        except Exception:
            return None
    return None


def fit_excel_image(image: ExcelImage) -> None:
    width = float(image.width or 0)
    height = float(image.height or 0)
    if width <= 0 or height <= 0:
        return
    scale = min(PRODUCT_IMAGE_MAX_WIDTH / width, PRODUCT_IMAGE_MAX_HEIGHT / height)
    image.width = max(1, int(width * scale))
    image.height = max(1, int(height * scale))


def central_field_value(
    opportunity: models.NewProductOpportunity | None,
    header: str,
    item: schemas.AvailableStockingItem | None = None,
    column: str | None = None,
) -> object:
    if opportunity is None:
        return None
    direct = {
        "站点": opportunity.site or opportunity.country,
        "国家": opportunity.site or opportunity.country,
        "开发部门": opportunity.developer_department,
        "开发员": opportunity.developer_name,
        "一级类目": opportunity.category_level1,
        "关键词": opportunity.keyword,
        "产品图片": opportunity.image_url,
        "主SKU名称": opportunity.main_sku_name,
        "主SKU": item.main_sku if item else opportunity.main_sku,
        "子SKU名称": opportunity.sub_sku_name,
        "子SKU": item.sub_sku if item else opportunity.sub_sku,
        "产品类型 / 引流or绑定or利润": opportunity.product_type,
        "开品理由": opportunity.reason,
    }
    if header in direct:
        return direct[header]

    snapshot = opportunity.snapshot if isinstance(opportunity.snapshot, dict) else {}
    value = lookup_snapshot_column(snapshot, column, opportunity.source_type)
    if value is not None:
        return value
    value = lookup_snapshot_header(snapshot, header)
    if value is not None:
        return value
    return None


def lookup_snapshot_column(snapshot: dict, column: str | None, source_type: str | None) -> object:
    if not column or source_type != "selection1_developer_claim_feedback":
        return None
    for field_name in ("fields_by_column", "cells"):
        fields = snapshot.get(field_name)
        if isinstance(fields, dict):
            value = fields.get(column)
            if value not in (None, ""):
                return value
    return None


def lookup_snapshot_header(snapshot: dict, header: str) -> object:
    fields = snapshot.get("central_fields")
    for key in header_lookup_keys(header):
        if isinstance(fields, dict):
            value = fields.get(key)
            if value is not None:
                return value
            value = fields.get(normalize_header(key))
            if value is not None:
                return value

    fields = snapshot.get("fields_by_header")
    if not isinstance(fields, dict):
        return None
    for key in header_lookup_keys(header):
        value = fields.get(normalize_header(key))
        if value is not None:
            return value
        value = fields.get(key)
        if value is not None:
            return value
    return None


def header_lookup_keys(header: str) -> list[str]:
    keys = [header, *CENTRAL_FIELD_ALIASES.get(header, [])]
    if "/" in header:
        keys.append(header.rsplit("/", 1)[-1].strip())
    return keys


def export_sheet_groups(items: list[schemas.AvailableStockingItem], empty_sheet_name: str) -> list[tuple[str, list[schemas.AvailableStockingItem]]]:
    if not items:
        return [(empty_sheet_name, [])]
    groups: dict[str, list[schemas.AvailableStockingItem]] = {}
    for item in items:
        country = normalize_site_code(item.stocking_country or item.site) or "未填国家"
        groups.setdefault(country, []).append(item)
    return [(safe_sheet_title(country), groups[country]) for country in sorted(groups)]


def safe_sheet_title(value: str) -> str:
    title = "".join("_" if char in r'[]:*?/\\' else char for char in value).strip() or "未填国家"
    return title[:31]


def style_worksheet(worksheet, max_width: int, fill: str | None = None) -> None:
    header_fill = PatternFill("solid", fgColor=fill) if fill else None
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
        if header_fill:
            cell.fill = header_fill
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column_cells in worksheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, max_width)
        worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = width


def excel_value(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(EXCEL_TIMEZONE).replace(tzinfo=None)
    return value


def latest_claim(db: Session, opportunity_id: str) -> models.SalesClaimForecast | None:
    return db.scalar(
        select(models.SalesClaimForecast)
        .where(
            models.SalesClaimForecast.opportunity_id == opportunity_id,
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
            models.SalesClaimForecast.source_column == "platform",
        )
        .order_by(models.SalesClaimForecast.created_at.desc())
    )


def latest_review_for_claim(
    db: Session,
    opportunity_id: str,
    claim: models.SalesClaimForecast,
) -> models.ReviewRecord | None:
    reviews = db.scalars(
        select(models.ReviewRecord)
        .where(
            models.ReviewRecord.opportunity_id == opportunity_id,
            or_(models.ReviewRecord.claim_record_id == claim.id, models.ReviewRecord.claim_record_id.is_(None)),
        )
        .order_by(models.ReviewRecord.created_at.desc(), models.ReviewRecord.claim_record_id.desc())
    )
    for review in reviews:
        if review.claim_record_id == claim.id:
            return review
        if not _same_or_later(review.created_at, claim.created_at):
            continue
        if review.review_status == REVIEW_APPROVED:
            return review
        if review.review_status in {REVIEW_CONFIRMED_NOT_CLAIM, REVIEW_RETURNED_FOR_SUPPLEMENT}:
            latest_submission = latest_platform_submission(db, opportunity_id, created_before=review.created_at)
            if latest_submission and latest_submission.id == claim.id:
                return review
    return None


def latest_review(db: Session, opportunity_id: str) -> models.ReviewRecord | None:
    return db.scalar(
        select(models.ReviewRecord)
        .where(models.ReviewRecord.opportunity_id == opportunity_id)
        .order_by(models.ReviewRecord.created_at.desc())
    )


def claim_evidence_summary(note: str | None) -> str | None:
    if not note:
        return None
    try:
        payload = json.loads(note)
    except json.JSONDecodeError:
        return None
    images = payload.get("evidence_images") if isinstance(payload, dict) else None
    if not isinstance(images, list):
        return None
    parts: list[str] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        labels = [str(image.get("name") or "").strip(), str(image.get("type") or "").strip()]
        size = image.get("size")
        if size:
            labels.append(str(size))
        text = " / ".join(label for label in labels if label)
        if text:
            parts.append(text)
    return "; ".join(parts) or None


def selection_source_label(opportunity: models.NewProductOpportunity) -> str:
    sheet = opportunity.source_sheet
    if opportunity.source_type == "selection1_developer_claim_feedback":
        label = "选品1-开发部门认领反馈"
    elif opportunity.source_type == "selection2_caigen_claim_feedback":
        label = "选品2-财根团队认领反馈"
    elif opportunity.source_type == SALES_SELF_SELECTION:
        label = "销售自选"
    else:
        label = opportunity.source_type
    return f"{label} + {sheet}" if sheet else label


def claim_prefill_salesperson(opportunity: models.NewProductOpportunity) -> str | None:
    if opportunity.source_type == "selection1_developer_claim_feedback":
        return None
    snapshot = opportunity.snapshot or {}
    claim = snapshot.get("claim_prefill") if isinstance(snapshot, dict) else None
    if isinstance(claim, dict):
        value = claim.get("salesperson_name")
        return str(value) if value else None
    cells = snapshot.get("cells") if isinstance(snapshot, dict) else None
    if isinstance(cells, dict):
        value = cells.get("CD")
        return str(value) if value else None
    return None


def create_notification_log(db: Session, payload: schemas.NotificationTestRequest) -> models.NotificationLog:
    existing = db.scalar(select(models.NotificationLog).where(models.NotificationLog.dedupe_key == payload.dedupe_key))
    if existing:
        return existing
    item = models.NotificationLog(
        dedupe_key=payload.dedupe_key,
        receiver_name=payload.receiver_name,
        channel=payload.channel,
        message_title=payload.title,
        send_status="logged",
    )
    db.add(item)
    audit(db, "notification.logged", "notification_log", item.id, payload.model_dump(), payload.receiver_name)
    return item


def send_dingtalk_new_product_todo_card(
    db: Session,
    payload: schemas.DingTalkNewProductTodoCardRequest,
    sender: DingTalkCardSender,
) -> models.NotificationLog:
    dedupe_key = payload.dedupe_key or f"dingtalk_card:{payload.receiver_role}:{payload.out_track_id}"
    message_title = payload.card_title or "新品待办"
    existing = db.scalar(select(models.NotificationLog).where(models.NotificationLog.dedupe_key == dedupe_key))
    if existing and existing.send_status == "sent":
        return existing
    if existing is None:
        item = models.NotificationLog(
            dedupe_key=dedupe_key,
            receiver_name=payload.receiver_name,
            channel="dingtalk_card",
            message_title=message_title,
            send_status="pending",
            provider_message_id=payload.out_track_id,
        )
        db.add(item)
        db.flush()
    else:
        item = existing
        item.receiver_name = payload.receiver_name
        item.message_title = message_title
        item.send_status = "pending"
        item.provider_message_id = payload.out_track_id
    try:
        result = sender.send_new_product_todo(
            NewProductTodoCard(
                receiver_dingtalk_user_id=payload.receiver_dingtalk_user_id,
                receiver_role=payload.receiver_role,
                left_count=payload.left_count,
                right_count=payload.right_count,
                action_url=payload.action_url,
                out_track_id=payload.out_track_id,
                subject_name=payload.subject_name or payload.receiver_name or "",
                card_title=payload.card_title or "",
                summary_text=payload.summary_text or "",
                left_label=payload.left_label or "",
                right_label=payload.right_label or "",
                tip_text=payload.tip_text or "",
            )
        )
    except Exception as exc:
        item.send_status = "failed"
        audit(
            db,
            "notification.dingtalk_card_failed",
            "notification_log",
            item.id,
            {
                "receiver_role": payload.receiver_role,
                "receiver_dingtalk_user_id": masked_dingtalk_user_id(payload.receiver_dingtalk_user_id),
                "error": str(exc),
            },
            payload.receiver_name,
        )
        return item

    item.send_status = "skipped" if result.get("skipped") else "sent"
    detail = {
        "receiver_role": payload.receiver_role,
        "receiver_dingtalk_user_id": masked_dingtalk_user_id(payload.receiver_dingtalk_user_id),
        "left_count": payload.left_count,
        "right_count": payload.right_count,
        "send_status": item.send_status,
    }
    if result.get("test_mode_redirect"):
        detail["test_mode_redirect"] = result["test_mode_redirect"]
    audit(
        db,
        "notification.dingtalk_card_sent",
        "notification_log",
        item.id,
        detail,
        payload.receiver_name,
    )
    return item


def notify_operator_new_product_todo_card(
    db: Session,
    operator_name: str | None,
    business_key: str,
    settings: Settings,
    sender: DingTalkCardSender,
) -> models.NotificationLog | None:
    if not operator_name or not settings.dingtalk_card_autosend_enabled:
        return None
    left_count = count_pending_claim_groups(db, operator_name)
    right_count = count_returned_supplement_groups(db, operator_name)
    return _send_or_skip_dingtalk_todo(
        db,
        receiver_name=operator_name,
        receiver_roles=("operator", "sales"),
        card_role="operator",
        left_count=left_count,
        right_count=right_count,
        action_url=dingtalk_action_url(settings, "operator"),
        out_track_id=f"new-product-todo-operator-{business_key}",
        sender=sender,
        test_receiver_name=settings.dingtalk_card_test_receiver_name,
    )


def notify_supervisor_new_product_todo_card(
    db: Session,
    business_key: str,
    settings: Settings,
    sender: DingTalkCardSender,
    supervisor_name: str = SUPERVISOR_NAME,
) -> models.NotificationLog | None:
    if not settings.dingtalk_card_autosend_enabled:
        return None
    left_count = count_pending_claim_reviews(db)
    right_count = count_pending_not_claim_reviews(db)
    return _send_or_skip_dingtalk_todo(
        db,
        receiver_name=supervisor_name,
        receiver_roles=("manager",),
        card_role="supervisor",
        left_count=left_count,
        right_count=right_count,
        action_url=dingtalk_action_url(settings, "supervisor"),
        out_track_id=f"new-product-todo-supervisor-{business_key}",
        sender=sender,
        test_receiver_name=settings.dingtalk_card_test_receiver_name,
    )


def count_pending_claim_groups(db: Session, operator_name: str) -> int:
    rows = db.execute(
        select(models.NewProductOpportunity.main_sku)
        .join(models.FlowInstance, models.FlowInstance.opportunity_id == models.NewProductOpportunity.id)
        .join(models.FlowTask, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .where(
            models.FlowTask.task_type == "sales_claim",
            models.FlowTask.status == TASK_PENDING,
            models.FlowTask.assignee_name == operator_name,
            models.NewProductOpportunity.current_status != OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
            models.NewProductOpportunity.current_status != OPPORTUNITY_DISABLED,
        )
    ).all()
    return len({row[0] for row in rows if row[0]})


def count_returned_supplement_groups(db: Session, operator_name: str) -> int:
    rows = db.execute(
        select(models.NewProductOpportunity.main_sku)
        .join(models.FlowInstance, models.FlowInstance.opportunity_id == models.NewProductOpportunity.id)
        .join(models.FlowTask, models.FlowTask.flow_instance_id == models.FlowInstance.id)
        .where(
            models.NewProductOpportunity.current_status == OPPORTUNITY_RETURNED_FOR_SUPPLEMENT,
            models.FlowTask.task_type == "sales_claim",
            models.FlowTask.status == TASK_PENDING,
            models.FlowTask.assignee_name == operator_name,
        )
    ).all()
    return len({row[0] for row in rows if row[0]})


def count_pending_claim_reviews(db: Session) -> int:
    return count_opportunities_by_status(db, OPPORTUNITY_CLAIM_SUBMITTED)


def count_pending_not_claim_reviews(db: Session) -> int:
    return count_opportunities_by_status(db, OPPORTUNITY_CLAIM_REJECTED)


def count_opportunities_by_status(db: Session, status: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(models.NewProductOpportunity)
            .where(models.NewProductOpportunity.current_status == status)
        )
        or 0
    )


def count_waiting_listing_groups(db: Session, owner: str | None = None) -> int:
    return sum(1 for task in list_pending_listing_tasks(db, owner) if task["requires_confirmation"])


def count_waiting_secondary_research_claims(db: Session, owner: str | None = None) -> int:
    filters = [
        models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH,
        models.SalesClaimForecast.secondary_research_submitted_at.is_(None),
    ]
    if owner:
        filters.append(models.SalesClaimForecast.salesperson_name == owner)
    return int(db.scalar(select(func.count()).select_from(models.SalesClaimForecast).where(*filters)) or 0)


def count_pending_review_observation_periods(db: Session, owner: str | None = None) -> int:
    statement = (
        select(func.count())
        .select_from(models.ItemObservationPeriod)
        .join(models.ListingRecord, models.ListingRecord.id == models.ItemObservationPeriod.listing_record_id)
        .where(
            models.ItemObservationPeriod.status == "pending_review",
            models.ItemObservationPeriod.record_source == "platform",
            models.ListingRecord.status == "active",
            models.ListingRecord.source_type != "history_finebi",
        )
    )
    if owner:
        statement = statement.where(models.ListingRecord.salesperson_name == owner)
    return int(db.scalar(statement) or 0)


def dingtalk_action_url(settings: Settings, role: str, view: str | None = None) -> str:
    role_param = "operator" if role == "operator" else "supervisor"
    url = f"{settings.platform_base_url.rstrip('/')}/?from=ding&role={role_param}"
    return f"{url}&view={view}" if view else url


def _send_or_skip_dingtalk_todo(
    db: Session,
    receiver_name: str,
    receiver_roles: tuple[str, ...],
    card_role: str,
    left_count: int,
    right_count: int,
    action_url: str,
    out_track_id: str,
    sender: DingTalkCardSender,
    test_receiver_name: str = "",
) -> models.NotificationLog:
    target_name = test_receiver_name.strip() or receiver_name
    target_roles = ("operator", "sales", "supervisor", "manager", "super_admin") if test_receiver_name.strip() else receiver_roles
    mapping = dingtalk_mapping_for_name(db, target_name, target_roles)
    dedupe_key = f"dingtalk_card:{card_role}:{out_track_id}"
    if mapping is not None and not test_receiver_name.strip() and not mapping.notification_enabled:
        return skipped_dingtalk_notification(db, dedupe_key, receiver_name, "skipped_notification_disabled")
    if mapping is None or not mapping.dingtalk_user_id:
        return skipped_dingtalk_notification(db, dedupe_key, target_name, "skipped_no_receiver")
    payload = schemas.DingTalkNewProductTodoCardRequest(
        receiver_dingtalk_user_id=mapping.dingtalk_user_id,
        receiver_name=target_name,
        receiver_role=card_role,
        subject_name=receiver_name,
        left_count=left_count,
        right_count=right_count,
        action_url=action_url,
        out_track_id=out_track_id,
        dedupe_key=dedupe_key,
    )
    return send_dingtalk_new_product_todo_card(db, payload, sender)


def dingtalk_mapping_for_name(
    db: Session,
    receiver_name: str,
    roles: tuple[str, ...],
) -> models.RoleMapping | None:
    return db.scalar(
        select(models.RoleMapping)
        .where(
            models.RoleMapping.enabled.is_(True),
            models.RoleMapping.name == receiver_name,
            models.RoleMapping.role.in_(roles),
        )
        .order_by(models.RoleMapping.updated_at.desc(), models.RoleMapping.created_at.desc())
    )


def skipped_dingtalk_notification(
    db: Session,
    dedupe_key: str,
    receiver_name: str,
    send_status: str,
) -> models.NotificationLog:
    existing = db.scalar(select(models.NotificationLog).where(models.NotificationLog.dedupe_key == dedupe_key))
    if existing:
        return existing
    item = models.NotificationLog(
        dedupe_key=dedupe_key,
        receiver_name=receiver_name,
        channel="dingtalk_card",
        message_title="新品待办",
        send_status=send_status,
    )
    db.add(item)
    audit(db, "notification.dingtalk_card_skipped", "notification_log", item.id, {"send_status": send_status}, receiver_name)
    return item


def reassign_task(
    db: Session,
    payload: schemas.ReassignRequest,
    actor_name: str | None = None,
    actor_user_id: str | None = None,
) -> models.FlowTask:
    task = db.get(models.FlowTask, payload.task_id)
    if task is None:
        raise LookupError("task not found")
    if task.status != TASK_PENDING:
        raise ValueError("only pending tasks can be reassigned")
    old_assignee = task.assignee_name
    task.assignee_name = payload.assignee_name
    task.assignee_user_id = payload.assignee_user_id
    task.status = TASK_PENDING
    audit(
        db,
        "task.reassigned",
        "flow_task",
        task.id,
        {"old_assignee": old_assignee, "new_assignee": payload.assignee_name, "reason": payload.reason},
        actor_name or payload.assignee_name,
        actor_user_id,
    )
    return task


def due_summary_date(base: datetime | None = None) -> datetime:
    start = base or datetime.now(timezone.utc)
    return start.replace(microsecond=0)
