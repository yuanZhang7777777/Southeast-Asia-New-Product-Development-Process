from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.config import Settings
from app.dingtalk_card_sender import ArrivalCard, ArrivalCardItem, DingTalkCardSender
from app.plm_download import BEIJING
from app.workflow_status import (
    CLAIM_RESULT_CLAIM,
    CLAIM_WAITING_LISTING,
    CLAIM_WAITING_SECONDARY_RESEARCH,
)


MANAGER_ROLES = ("manager",)
TEST_RECEIVER_ROLES = ("operator", "sales", "supervisor", "manager", "super_admin")
ELIMINATION_POSITIONING = "淘汰款"
ELIMINATION_CARD_TITLE = "淘汰款提醒"
ELIMINATION_MARKED_TITLE = "淘汰款已汇总"
LISTING_REMINDER_CARD_TITLE = "已到货新品催办"
LISTING_REMINDER_TIP_LIMIT = 5
CURRENT_SECONDARY_SOURCE_COLUMNS = ("platform", "history_selection1", "plm_arrival_discovery", "manual_secondary")


@dataclass(frozen=True)
class _ArrivalGroup:
    arrival_date: str
    salesperson_name: str
    new_items: list[ArrivalCardItem]
    old_items: list[ArrivalCardItem]


@dataclass(frozen=True)
class _ListingReminderGroup:
    salesperson_name: str
    waiting_listing_count: int
    waiting_secondary_count: int
    items: list[tuple[str, str]]


@dataclass(frozen=True)
class _EliminationRow:
    id: str
    business_period: str
    site: str
    main_sku: str
    item: str
    owner: str
    product_name: str
    conclusion: str


def send_arrival_daily_cards(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    arrival_date: str,
) -> list[models.NotificationLog]:
    if not settings.dingtalk_card_autosend_enabled:
        return []
    logs: list[models.NotificationLog] = []
    groups = _arrival_groups(db, arrival_date)
    test_mapping = _test_receiver_mapping(db, settings) if groups else None
    for group in groups:
        dedupe_key = f"dingtalk_card:arrival:{group.arrival_date}:{group.salesperson_name}"
        mapping = test_mapping or services.dingtalk_mapping_for_name(db, group.salesperson_name, ("operator", "sales"))
        if mapping is None or not mapping.dingtalk_user_id:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_no_receiver"))
            continue
        if test_mapping is None and not mapping.notification_enabled:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_notification_disabled"))
            continue
        logs.append(
            _send_arrival_card(
                db,
                dedupe_key,
                mapping.dingtalk_user_id,
                group,
                settings,
                sender,
                action_text="去处理",
                action_url=services.dingtalk_action_url(settings, "operator", view="research"),
            )
        )
    return logs


def send_operator_listing_reminder_cards(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    reminder_date: str,
) -> list[models.NotificationLog]:
    if not settings.dingtalk_card_autosend_enabled:
        return []
    logs: list[models.NotificationLog] = []
    groups = _listing_reminder_groups(db)
    test_mapping = _test_receiver_mapping(db, settings) if groups else None
    for group in groups:
        if group.waiting_listing_count == 0 and group.waiting_secondary_count == 0:
            continue
        dedupe_key = f"dingtalk_card:listing-reminder:{reminder_date}:{group.salesperson_name}"
        mapping = test_mapping or services.dingtalk_mapping_for_name(db, group.salesperson_name, ("operator", "sales"))
        if mapping is None or not mapping.dingtalk_user_id:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_no_receiver"))
            continue
        if test_mapping is None and not mapping.notification_enabled:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_notification_disabled"))
            continue
        total = group.waiting_listing_count + group.waiting_secondary_count
        payload = schemas.DingTalkNewProductTodoCardRequest(
            receiver_dingtalk_user_id=mapping.dingtalk_user_id,
            receiver_name=mapping.name,
            receiver_role="operator",
            subject_name=group.salesperson_name,
            left_count=group.waiting_listing_count,
            right_count=group.waiting_secondary_count,
            action_url=services.dingtalk_action_url(settings, "operator", view="research"),
            out_track_id=dedupe_key,
            dedupe_key=dedupe_key,
            card_title=LISTING_REMINDER_CARD_TITLE,
            summary_text=f"你有 {total} 个已到货新品待跟进刊登",
            left_label="待刊登",
            right_label="待二调",
            tip_text=_listing_reminder_tip(group.items),
        )
        logs.append(services.send_dingtalk_new_product_todo_card(db, payload, sender))
    return logs


def send_daily_elimination_summary(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    summary_date: str,
) -> list[models.NotificationLog]:
    if not settings.dingtalk_card_autosend_enabled:
        return []
    rows = _pending_elimination_rows(db)
    if not rows:
        return []
    row_ids = [row.id for row in rows]
    row_digest = hashlib.sha1(",".join(sorted(row_ids)).encode("utf-8")).hexdigest()[:12]
    logs = _send_manager_arrival_template_cards(db, settings, sender, summary_date, row_digest, rows)
    if logs and all(log.send_status in {"sent", "skipped_no_receiver"} for log in logs):
        _mark_elimination_rows_notified(db, rows)
    return logs


def send_daily_manager_review_summary(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    now: datetime,
) -> list[models.NotificationLog]:
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    if not settings.dingtalk_card_autosend_enabled:
        return []
    left_count = services.count_pending_claim_reviews(db)
    right_count = services.count_pending_not_claim_reviews(db)
    if left_count == 0 and right_count == 0:
        return []
    return _send_manager_todo_cards(
        db,
        settings,
        sender,
        business_key=f"manager-review-{current.date().isoformat()}",
        left_count=left_count,
        right_count=right_count,
    )


def send_thursday_manager_review_summary(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    now: datetime,
) -> list[models.NotificationLog]:
    return send_daily_manager_review_summary(db, settings, sender, now)


def _arrival_groups(db: Session, arrival_date: str) -> list[_ArrivalGroup]:
    arrival_day_start = datetime.strptime(arrival_date, "%Y-%m-%d").replace(tzinfo=BEIJING)
    arrival_utc_start = arrival_day_start.astimezone(timezone.utc)
    arrival_utc_end = (arrival_day_start + timedelta(days=1)).astimezone(timezone.utc)
    new_rows = db.execute(
        select(models.ArrivalRecord, models.PlmArrivalItem, models.SalesClaimForecast, models.NewProductOpportunity)
        .outerjoin(models.PlmArrivalBatch, models.ArrivalRecord.plm_arrival_batch_id == models.PlmArrivalBatch.id)
        .outerjoin(models.PlmArrivalItem, models.ArrivalRecord.plm_arrival_item_id == models.PlmArrivalItem.id)
        .join(models.SalesClaimForecast, models.ArrivalRecord.claim_record_id == models.SalesClaimForecast.id)
        .join(models.NewProductOpportunity, models.ArrivalRecord.opportunity_id == models.NewProductOpportunity.id)
        .where(
            or_(
                models.PlmArrivalBatch.arrival_date == arrival_date,
                and_(
                    models.ArrivalRecord.plm_arrival_batch_id.is_(None),
                    models.ArrivalRecord.arrived_at >= arrival_utc_start,
                    models.ArrivalRecord.arrived_at < arrival_utc_end,
                ),
            )
        )
        .where(
            or_(models.PlmArrivalItem.id.is_(None), models.PlmArrivalItem.arrival_type == "new_arrival"),
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
            models.SalesClaimForecast.source_column.in_(CURRENT_SECONDARY_SOURCE_COLUMNS),
            models.SalesClaimForecast.downstream_status == CLAIM_WAITING_SECONDARY_RESEARCH,
            models.SalesClaimForecast.secondary_research_submitted_at.is_(None),
        )
        .order_by(
            models.ArrivalRecord.salesperson_name,
            models.PlmArrivalItem.main_sku,
            models.NewProductOpportunity.main_sku,
            models.PlmArrivalItem.sub_sku,
            models.NewProductOpportunity.sub_sku,
        )
    ).all()
    old_rows = db.execute(
        select(models.PlmArrivalItem)
        .join(models.PlmArrivalBatch, models.PlmArrivalItem.batch_id == models.PlmArrivalBatch.id)
        .where(
            models.PlmArrivalBatch.arrival_date == arrival_date,
            models.PlmArrivalItem.arrival_type != "new_arrival",
        )
        .order_by(models.PlmArrivalItem.salesperson_name, models.PlmArrivalItem.main_sku, models.PlmArrivalItem.sub_sku)
    ).scalars()
    grouped: dict[str, dict[str, dict[str, set[str] | str]]] = defaultdict(dict)
    old_grouped: dict[str, dict[str, dict[str, set[str] | str]]] = defaultdict(dict)
    for record, row, claim, opportunity in new_rows:
        row_salesperson = row.salesperson_name if row else ""
        salesperson = (record.salesperson_name or claim.salesperson_name or row_salesperson or "").strip()
        main_sku = ((row.main_sku if row else None) or opportunity.main_sku or "").strip()
        if not salesperson or not main_sku:
            continue
        product_name = ((row.product_name if row else None) or opportunity.main_sku_name or opportunity.sub_sku_name or "").strip()
        item = grouped[salesperson].setdefault(main_sku, {"product_name": product_name, "sub_skus": set()})
        sub_sku = ((row.sub_sku if row else None) or opportunity.sub_sku or "").strip()
        if sub_sku:
            item["sub_skus"].add(sub_sku)
    for row in old_rows:
        salesperson = (row.salesperson_name or "").strip()
        main_sku = (row.main_sku or "").strip()
        if not salesperson or not main_sku:
            continue
        item = old_grouped[salesperson].setdefault(main_sku, {"product_name": row.product_name or "", "sub_skus": set()})
        if row.sub_sku:
            item["sub_skus"].add(row.sub_sku)
    names = sorted(set(grouped) | set(old_grouped))
    return [
        _ArrivalGroup(
            arrival_date=arrival_date,
            salesperson_name=name,
            new_items=_arrival_items(grouped.get(name, {})),
            old_items=_arrival_items(old_grouped.get(name, {})),
        )
        for name in names
    ]


def _listing_reminder_groups(db: Session) -> list[_ListingReminderGroup]:
    arrival_exists = (
        select(models.ArrivalRecord.id)
        .where(models.ArrivalRecord.claim_record_id == models.SalesClaimForecast.id)
        .exists()
    )
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
        .where(
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
            models.SalesClaimForecast.source_column == "platform",
            models.SalesClaimForecast.downstream_status.in_((CLAIM_WAITING_LISTING, CLAIM_WAITING_SECONDARY_RESEARCH)),
            arrival_exists,
        )
        .order_by(
            models.SalesClaimForecast.salesperson_name,
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
        )
    ).all()
    listing_counts: dict[str, int] = defaultdict(int)
    secondary_counts: dict[str, int] = defaultdict(int)
    items: dict[str, dict[str, str]] = defaultdict(dict)
    for claim, opportunity in rows:
        salesperson = (claim.salesperson_name or "").strip()
        main_sku = (opportunity.main_sku or "").strip()
        if not salesperson or not main_sku:
            continue
        if claim.downstream_status == CLAIM_WAITING_LISTING:
            listing_counts[salesperson] += 1
        else:
            secondary_counts[salesperson] += 1
        items[salesperson].setdefault(main_sku, opportunity.main_sku_name or opportunity.sub_sku_name or "")
    return [
        _ListingReminderGroup(
            salesperson_name=name,
            waiting_listing_count=listing_counts[name],
            waiting_secondary_count=secondary_counts[name],
            items=list(items[name].items()),
        )
        for name in sorted(items)
    ]


def _listing_reminder_tip(items: list[tuple[str, str]]) -> str:
    parts = [f"{main_sku}|{name}" if name else main_sku for main_sku, name in items[:LISTING_REMINDER_TIP_LIMIT]]
    text = "、".join(parts)
    extra = len(items) - LISTING_REMINDER_TIP_LIMIT
    return f"{text} +{extra}" if extra > 0 else text


def _arrival_items(values: dict[str, dict[str, set[str] | str]]) -> list[ArrivalCardItem]:
    return [
        ArrivalCardItem(main_sku=main_sku, child_sku_count=len(value["sub_skus"]), product_name=str(value["product_name"]))
        for main_sku, value in sorted(values.items())
    ]


def _send_arrival_card(
    db: Session,
    dedupe_key: str,
    dingtalk_user_id: str,
    group: _ArrivalGroup,
    settings: Settings,
    sender: DingTalkCardSender,
    *,
    message_title: str = "到货通知",
    provider_message_id: str | None = None,
    action_url: str | None = None,
    card_title: str = "到货通知",
    summary_text: str = "",
    left_label: str = "主SKU数",
    left_count: int | None = None,
    action_text: str = "进入系统查看",
    sku_markdown: str | None = None,
) -> models.NotificationLog:
    existing = db.scalar(select(models.NotificationLog).where(models.NotificationLog.dedupe_key == dedupe_key))
    if existing and existing.send_status == "sent":
        return existing
    if existing is None:
        item = models.NotificationLog(
            dedupe_key=dedupe_key,
            receiver_name=group.salesperson_name,
            channel="dingtalk_card",
            message_title=message_title,
            send_status="pending",
            provider_message_id=provider_message_id or dedupe_key,
        )
        db.add(item)
        db.flush()
    else:
        item = existing
        item.receiver_name = group.salesperson_name
        item.message_title = message_title
        item.send_status = "pending"
        item.provider_message_id = provider_message_id or dedupe_key
    try:
        result = sender.send_arrival_card(
            ArrivalCard(
                receiver_dingtalk_user_id=dingtalk_user_id,
                arrival_date=group.arrival_date,
                salesperson_name=group.salesperson_name,
                new_items=group.new_items,
                old_items=group.old_items,
                action_url=action_url or services.dingtalk_action_url(settings, "operator"),
                out_track_id=dedupe_key,
                card_title=card_title,
                summary_text=summary_text,
                left_label=left_label,
                left_count=left_count,
                action_text=action_text,
                sku_markdown=sku_markdown,
            )
        )
        item.send_status = "skipped" if result.get("skipped") else "sent"
        if result.get("test_mode_redirect"):
            services.audit(
                db,
                "notification.dingtalk_card_test_redirect",
                "notification_log",
                item.id,
                dict(result["test_mode_redirect"]),
                group.salesperson_name,
            )
    except Exception:
        item.send_status = "failed"
    return item


def _pending_elimination_rows(db: Session) -> list[_EliminationRow]:
    notified_ids = _notified_elimination_row_ids(db)
    claim_rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.SalesClaimForecast.opportunity_id == models.NewProductOpportunity.id)
        .where(
            models.SalesClaimForecast.product_positioning == ELIMINATION_POSITIONING,
            models.SalesClaimForecast.secondary_research_submitted_at.is_not(None),
        )
        .order_by(
            models.SalesClaimForecast.secondary_research_submitted_at,
            models.NewProductOpportunity.main_sku,
            models.NewProductOpportunity.sub_sku,
        )
    ).all()
    period_rows = db.execute(
        select(models.AuditLog, models.ItemObservationPeriod, models.ListingRecord)
        .join(models.ItemObservationPeriod, models.ItemObservationPeriod.id == models.AuditLog.entity_id)
        .join(models.ListingRecord, models.ListingRecord.id == models.ItemObservationPeriod.listing_record_id)
        .where(models.AuditLog.action == "observation.elimination_entered")
        .order_by(models.AuditLog.created_at, models.ListingRecord.main_sku, models.ListingRecord.item)
    ).all()
    rows = [
        _EliminationRow(
            id=claim.id,
            business_period=opportunity.batch or "-",
            site=opportunity.site or opportunity.country or "-",
            main_sku=opportunity.main_sku or "-",
            item=opportunity.sub_sku or "-",
            owner=claim.salesperson_name or "-",
            product_name=opportunity.main_sku_name or opportunity.sub_sku_name or "",
            conclusion=claim.secondary_conclusion or "",
        )
        for claim, opportunity in claim_rows
    ]
    rows.extend(
        _EliminationRow(
            id=event.id,
            business_period=listing.business_period or "-",
            site=listing.site or listing.country or "-",
            main_sku=listing.main_sku,
            item=listing.item,
            owner=listing.salesperson_name,
            product_name=listing.main_sku_name or "",
            conclusion=f"第{period.week_number}周",
        )
        for event, period, listing in period_rows
    )
    return [row for row in rows if row.id not in notified_ids]


def _notified_elimination_row_ids(db: Session) -> set[str]:
    values = db.scalars(
        select(models.NotificationLog.provider_message_id).where(
            models.NotificationLog.message_title == ELIMINATION_MARKED_TITLE,
            models.NotificationLog.send_status == "sent",
        )
    )
    return {value for value in values if value}


def _mark_elimination_rows_notified(
    db: Session,
    rows: list[_EliminationRow],
) -> None:
    for row in rows:
        dedupe_key = f"dingtalk_card:elimination-item:{row.id}"
        existing = db.scalar(select(models.NotificationLog).where(models.NotificationLog.dedupe_key == dedupe_key))
        if existing:
            existing.send_status = "sent"
            existing.provider_message_id = row.id
            existing.message_title = ELIMINATION_MARKED_TITLE
            continue
        db.add(
            models.NotificationLog(
                dedupe_key=dedupe_key,
                receiver_name="主管汇总",
                channel="dingtalk_card",
                message_title=ELIMINATION_MARKED_TITLE,
                send_status="sent",
                provider_message_id=row.id,
            )
        )
    db.flush()


def _send_manager_arrival_template_cards(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    summary_date: str,
    claim_digest: str,
    rows: list[_EliminationRow],
) -> list[models.NotificationLog]:
    logs: list[models.NotificationLog] = []
    count = len(rows)
    markdown = _elimination_markdown(rows)
    summary_text = f"{summary_date} 有 {count} 个淘汰款待外部处理"
    for mapping in _manager_mappings(db, settings):
        dedupe_key = f"dingtalk_card:elimination:{claim_digest}:{mapping.name}"
        if not mapping.dingtalk_user_id:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, mapping.name, "skipped_no_receiver"))
            continue
        group = _ArrivalGroup(arrival_date=summary_date, salesperson_name=mapping.name, new_items=[], old_items=[])
        logs.append(
            _send_arrival_card(
                db,
                dedupe_key,
                mapping.dingtalk_user_id,
                group,
                settings,
                sender,
                message_title=ELIMINATION_CARD_TITLE,
                provider_message_id=claim_digest,
                action_url=services.dingtalk_action_url(settings, "supervisor"),
                card_title=ELIMINATION_CARD_TITLE,
                summary_text=summary_text,
                left_label=ELIMINATION_POSITIONING,
                left_count=count,
                action_text="查看商品看板",
                sku_markdown=markdown,
            )
        )
    return logs


def _elimination_markdown(rows: list[_EliminationRow]) -> str:
    lines = [f"**{ELIMINATION_POSITIONING}**"]
    for index, row in enumerate(rows, start=1):
        suffix = f" | {row.product_name}" if row.product_name else ""
        conclusion = f" | {row.conclusion}" if row.conclusion else ""
        lines.append(
            f"{index}. {row.business_period} | {row.site} | {row.main_sku} | {row.item} | {row.owner}{suffix}{conclusion}"
        )
    return "\n".join(lines)


def _send_manager_todo_cards(
    db: Session,
    settings: Settings,
    sender: DingTalkCardSender,
    business_key: str,
    left_count: int,
    right_count: int,
) -> list[models.NotificationLog]:
    logs: list[models.NotificationLog] = []
    for mapping in _manager_mappings(db, settings):
        dedupe_key = f"dingtalk_card:supervisor:{business_key}:{mapping.name}"
        if not mapping.dingtalk_user_id:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, mapping.name, "skipped_no_receiver"))
            continue
        payload = schemas.DingTalkNewProductTodoCardRequest(
            receiver_dingtalk_user_id=mapping.dingtalk_user_id,
            receiver_name=mapping.name,
            receiver_role="supervisor",
            subject_name=mapping.name,
            left_count=left_count,
            right_count=right_count,
            action_url=services.dingtalk_action_url(settings, "supervisor"),
            out_track_id=dedupe_key,
            dedupe_key=dedupe_key,
        )
        logs.append(services.send_dingtalk_new_product_todo_card(db, payload, sender))
    return logs


def _manager_mappings(db: Session, settings: Settings) -> list[models.RoleMapping]:
    test_mapping = _test_receiver_mapping(db, settings)
    if test_mapping is not None:
        return [test_mapping]
    return list(
        db.scalars(
            select(models.RoleMapping)
            .where(
                models.RoleMapping.enabled.is_(True),
                models.RoleMapping.notification_enabled.is_(True),
                models.RoleMapping.role.in_(MANAGER_ROLES),
            )
            .order_by(models.RoleMapping.role, models.RoleMapping.name)
        )
    )


def _test_receiver_mapping(db: Session, settings: Settings) -> models.RoleMapping | None:
    receiver_name = settings.dingtalk_card_test_receiver_name.strip()
    if not receiver_name:
        return None
    mappings = list(
        db.scalars(
            select(models.RoleMapping).where(
                models.RoleMapping.enabled.is_(True),
                models.RoleMapping.name == receiver_name,
                models.RoleMapping.role.in_(TEST_RECEIVER_ROLES),
            )
        )
    )
    if len(mappings) != 1 or not mappings[0].dingtalk_user_id:
        raise RuntimeError("DingTalk test receiver is not configured uniquely")
    return mappings[0]
