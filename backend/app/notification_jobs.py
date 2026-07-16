from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.config import Settings
from app.dingtalk_card_sender import ArrivalCard, ArrivalCardItem, DingTalkCardSender
from app.plm_download import BEIJING


MANAGER_ROLES = ("manager", "super_admin")
ELIMINATION_POSITIONING = "淘汰款"
ELIMINATION_CARD_TITLE = "淘汰款提醒"
ELIMINATION_MARKED_TITLE = "淘汰款已汇总"


@dataclass(frozen=True)
class _ArrivalGroup:
    arrival_date: str
    salesperson_name: str
    new_items: list[ArrivalCardItem]
    old_items: list[ArrivalCardItem]


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
    for group in _arrival_groups(db, arrival_date):
        dedupe_key = f"dingtalk_card:arrival:{group.arrival_date}:{group.salesperson_name}"
        mapping = services.dingtalk_mapping_for_name(db, group.salesperson_name, ("operator", "sales"))
        if mapping is None or not mapping.dingtalk_user_id:
            logs.append(services.skipped_dingtalk_notification(db, dedupe_key, group.salesperson_name, "skipped_no_receiver"))
            continue
        logs.append(_send_arrival_card(db, dedupe_key, mapping.dingtalk_user_id, group, settings, sender))
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
    rows = db.execute(
        select(models.PlmArrivalItem)
        .join(models.PlmArrivalBatch, models.PlmArrivalItem.batch_id == models.PlmArrivalBatch.id)
        .where(models.PlmArrivalBatch.arrival_date == arrival_date)
        .order_by(models.PlmArrivalItem.salesperson_name, models.PlmArrivalItem.main_sku, models.PlmArrivalItem.sub_sku)
    ).scalars()
    grouped: dict[str, dict[str, dict[str, set[str] | str]]] = defaultdict(dict)
    old_grouped: dict[str, dict[str, dict[str, set[str] | str]]] = defaultdict(dict)
    for row in rows:
        salesperson = (row.salesperson_name or "").strip()
        main_sku = (row.main_sku or "").strip()
        if not salesperson or not main_sku:
            continue
        target = grouped if row.arrival_type == "new_arrival" else old_grouped
        item = target[salesperson].setdefault(main_sku, {"product_name": row.product_name or "", "sub_skus": set()})
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
        select(models.ItemObservationPeriod, models.ListingRecord)
        .join(models.ListingRecord, models.ListingRecord.id == models.ItemObservationPeriod.listing_record_id)
        .where(
            models.ItemObservationPeriod.product_positioning == ELIMINATION_POSITIONING,
            models.ItemObservationPeriod.status == "completed",
            models.ItemObservationPeriod.reviewed_at.is_not(None),
        )
        .order_by(models.ItemObservationPeriod.reviewed_at, models.ListingRecord.main_sku, models.ListingRecord.item)
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
            id=period.id,
            business_period=listing.business_period or "-",
            site=listing.site or listing.country or "-",
            main_sku=listing.main_sku,
            item=listing.item,
            owner=listing.salesperson_name,
            product_name=listing.main_sku_name or "",
            conclusion=f"第{period.week_number}周",
        )
        for period, listing in period_rows
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
    for mapping in _manager_mappings(db):
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
    for mapping in _manager_mappings(db):
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


def _manager_mappings(db: Session) -> list[models.RoleMapping]:
    return list(
        db.scalars(
            select(models.RoleMapping)
            .where(models.RoleMapping.enabled.is_(True), models.RoleMapping.role.in_(MANAGER_ROLES))
            .order_by(models.RoleMapping.role, models.RoleMapping.name)
        )
    )
