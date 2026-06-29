from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dingtalk_user_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RoleMapping(TimestampMixin, Base):
    __tablename__ = "role_mapping"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    dingtalk_user_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    group_name: Mapped[str | None] = mapped_column(String(128))
    site: Mapped[str | None] = mapped_column(String(32))
    manager_user_id: Mapped[str | None] = mapped_column(String(36))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NewProductOpportunity(TimestampMixin, Base):
    __tablename__ = "new_product_opportunity"
    __table_args__ = (
        UniqueConstraint("source_type", "source_file", "source_sheet", "source_row", name="uq_opportunity_source_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(64))
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)
    batch: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    site: Mapped[str | None] = mapped_column(String(32))
    developer_department: Mapped[str | None] = mapped_column(String(128))
    developer_name: Mapped[str | None] = mapped_column(String(128))
    category_level1: Mapped[str | None] = mapped_column(String(128))
    keyword: Mapped[str | None] = mapped_column(String(255))
    image_url: Mapped[str | None] = mapped_column(Text)
    main_sku_name: Mapped[str | None] = mapped_column(String(255))
    main_sku: Mapped[str] = mapped_column(String(128), index=True)
    sub_sku_name: Mapped[str | None] = mapped_column(String(255))
    sub_sku: Mapped[str] = mapped_column(String(128), index=True)
    product_type: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(String(64), default="pending_assignment")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    flow_instances: Mapped[list["FlowInstance"]] = relationship(back_populates="opportunity")


class SourceRecordSnapshot(TimestampMixin, Base):
    __tablename__ = "source_record_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)
    column_range: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class MarketResearchItem(TimestampMixin, Base):
    __tablename__ = "market_research_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    platform: Mapped[str] = mapped_column(String(64), default="Shopee")
    research_type: Mapped[str] = mapped_column(String(64))
    competitor_url: Mapped[str | None] = mapped_column(Text)
    competitor_price: Mapped[float | None] = mapped_column(Float)
    competitor_monthly_sales: Mapped[float | None] = mapped_column(Float)
    reference_daily_sales: Mapped[float | None] = mapped_column(Float)
    reference_price: Mapped[float | None] = mapped_column(Float)


class FlowInstance(TimestampMixin, Base):
    __tablename__ = "flow_instance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    current_node: Mapped[str] = mapped_column(String(64), default="assignment")
    current_status: Mapped[str] = mapped_column(String(64), default="open")
    owner_user_id: Mapped[str | None] = mapped_column(String(36))
    owner_role: Mapped[str | None] = mapped_column(String(64))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opportunity: Mapped[NewProductOpportunity] = relationship(back_populates="flow_instances")
    tasks: Mapped[list["FlowTask"]] = relationship(back_populates="flow_instance")


class FlowTask(TimestampMixin, Base):
    __tablename__ = "flow_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    flow_instance_id: Mapped[str] = mapped_column(ForeignKey("flow_instance.id"))
    node_code: Mapped[str] = mapped_column(String(64))
    task_type: Mapped[str] = mapped_column(String(64))
    assignee_user_id: Mapped[str | None] = mapped_column(String(36))
    assignee_name: Mapped[str | None] = mapped_column(String(128))
    assignee_role: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dingtalk_todo_id: Mapped[str | None] = mapped_column(String(255))

    flow_instance: Mapped[FlowInstance] = relationship(back_populates="tasks")


class SalesClaimForecast(TimestampMixin, Base):
    __tablename__ = "sales_claim_forecast"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    platform: Mapped[str | None] = mapped_column(String(64))
    group_name: Mapped[str | None] = mapped_column(String(128))
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    claim_result: Mapped[str | None] = mapped_column(String(32))
    claim_daily_sales: Mapped[float | None] = mapped_column(Float)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    feedback_summary: Mapped[str | None] = mapped_column(Text)
    source_column: Mapped[str | None] = mapped_column(String(32))


class ReviewRecord(TimestampMixin, Base):
    __tablename__ = "review_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    reviewer_user_id: Mapped[str | None] = mapped_column(String(36))
    reviewer_name: Mapped[str | None] = mapped_column(String(128))
    review_status: Mapped[str] = mapped_column(String(32))
    review_comment: Mapped[str | None] = mapped_column(Text)


class SupplyChainQuote(TimestampMixin, Base):
    __tablename__ = "supply_chain_quote"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    quote_user: Mapped[str | None] = mapped_column(String(128))
    quote_comment: Mapped[str | None] = mapped_column(Text)
    suggested_purchase_price: Mapped[float | None] = mapped_column(Float)
    developer_acceptance: Mapped[str | None] = mapped_column(String(64))
    quoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockingRequest(TimestampMixin, Base):
    __tablename__ = "stocking_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    request_type: Mapped[str] = mapped_column(String(64), default="initial")
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    main_sku: Mapped[str | None] = mapped_column(String(128))
    sub_sku: Mapped[str | None] = mapped_column(String(128))
    cost_price: Mapped[float | None] = mapped_column(Float)
    unit_volume: Mapped[float | None] = mapped_column(Float)
    daily_sales: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(64))
    warehouse: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="draft")


class ArrivalRecord(TimestampMixin, Base):
    __tablename__ = "arrival_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    warehouse: Mapped[str | None] = mapped_column(String(128))
    arrived_quantity: Mapped[int | None] = mapped_column(Integer)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing_status: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class FourWeekSummary(TimestampMixin, Base):
    __tablename__ = "four_week_summary"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    summary_user: Mapped[str | None] = mapped_column(String(128))
    achieved: Mapped[bool | None] = mapped_column(Boolean)
    out_of_stock_impact: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)


class NotificationLog(TimestampMixin, Base):
    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_dedupe_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dedupe_key: Mapped[str] = mapped_column(String(255))
    opportunity_id: Mapped[str | None] = mapped_column(String(36))
    task_id: Mapped[str | None] = mapped_column(String(36))
    receiver_user_id: Mapped[str | None] = mapped_column(String(36))
    receiver_name: Mapped[str | None] = mapped_column(String(128))
    channel: Mapped[str] = mapped_column(String(64))
    message_title: Mapped[str] = mapped_column(String(255))
    send_status: Mapped[str] = mapped_column(String(64), default="pending")
    provider_message_id: Mapped[str | None] = mapped_column(String(255))


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    actor_name: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(128))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
