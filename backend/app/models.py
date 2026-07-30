from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
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


class UserPassword(TimestampMixin, Base):
    __tablename__ = "user_password"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


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

    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class OperatorAssignmentProfile(TimestampMixin, Base):
    __tablename__ = "operator_assignment_profile"
    __table_args__ = (UniqueConstraint("operator_name", name="uq_operator_assignment_profile_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    operator_name: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str | None] = mapped_column(String(64))
    operator_level: Mapped[str | None] = mapped_column(String(64))
    business_type: Mapped[str | None] = mapped_column(String(128))
    key_site: Mapped[str | None] = mapped_column(String(32))
    key_category1: Mapped[str | None] = mapped_column(String(128))
    key_category2: Mapped[str | None] = mapped_column(String(128))
    key_categories: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assignment_priority: Mapped[int] = mapped_column(Integer, default=0)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class CompanyCategory(TimestampMixin, Base):
    __tablename__ = "company_category"
    __table_args__ = (UniqueConstraint("level1", "level2", name="uq_company_category_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    level1: Mapped[str] = mapped_column(String(128), index=True)
    level2: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)

class NewProductOpportunity(TimestampMixin, Base):
    __tablename__ = "new_product_opportunity"
    __table_args__ = (
        Index("ix_opportunity_source_trace", "source_type", "source_file", "source_sheet", "source_row"),
        Index("ix_opportunity_source_batch_sub_sku", "source_type", "batch", "sub_sku"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batch.id"))
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
    category_level2: Mapped[str | None] = mapped_column(String(128))
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

    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="opportunities")
    flow_instances: Mapped[list["FlowInstance"]] = relationship(back_populates="opportunity")


class ImportBatch(TimestampMixin, Base):
    __tablename__ = "import_batch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(64))
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    business_period: Mapped[str | None] = mapped_column(String(128), index=True)
    imported_by: Mapped[str | None] = mapped_column(String(128))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="completed")

    opportunities: Mapped[list[NewProductOpportunity]] = relationship(back_populates="import_batch")
    source_snapshots: Mapped[list["SourceRecordSnapshot"]] = relationship(back_populates="import_batch")


class SourceRecordSnapshot(TimestampMixin, Base):
    __tablename__ = "source_record_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batch.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"), index=True)
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)
    column_range: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="source_snapshots")


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

    @property
    def opportunity_id(self) -> str | None:
        return self.flow_instance.opportunity_id if self.flow_instance else None


class SalesClaimForecast(TimestampMixin, Base):
    __tablename__ = "sales_claim_forecast"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("flow_task.id"))
    platform: Mapped[str | None] = mapped_column(String(64))
    group_name: Mapped[str | None] = mapped_column(String(128))
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    claim_result: Mapped[str | None] = mapped_column(String(32))
    claim_daily_sales: Mapped[float | None] = mapped_column(Float)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    feedback_summary: Mapped[str | None] = mapped_column(Text)
    source_column: Mapped[str | None] = mapped_column(String(32))
    claim_source: Mapped[str] = mapped_column(String(64), default="assigned_task")
    first_submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    note: Mapped[str | None] = mapped_column(Text)
    downstream_status: Mapped[str | None] = mapped_column(String(64), index=True)
    inventory_available: Mapped[bool | None] = mapped_column(Boolean)
    needs_stocking: Mapped[bool | None] = mapped_column(Boolean)
    stocking_decision_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrival_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secondary_research_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    secondary_competitor_url: Mapped[str | None] = mapped_column(Text)
    secondary_conclusion: Mapped[str | None] = mapped_column(Text)
    product_positioning: Mapped[str | None] = mapped_column(String(32))
    secondary_target_daily_sales: Mapped[float | None] = mapped_column(Float)
    secondary_selling_points: Mapped[str | None] = mapped_column(Text)
    secondary_evidence_images: Mapped[list[dict] | None] = mapped_column(JSON, default=list)
    secondary_research_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewRecord(TimestampMixin, Base):
    __tablename__ = "review_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    claim_record_id: Mapped[str | None] = mapped_column(ForeignKey("sales_claim_forecast.id"), index=True)
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
    claim_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("sales_claim_forecast.id"), unique=True, index=True
    )
    application_date: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_type: Mapped[str] = mapped_column(String(64), default="initial")
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    main_sku: Mapped[str | None] = mapped_column(String(128))
    sub_sku: Mapped[str | None] = mapped_column(String(128))
    cost_price: Mapped[float | None] = mapped_column(Float)
    length_cm: Mapped[float | None] = mapped_column(Float)
    width_cm: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    unit_volume: Mapped[float | None] = mapped_column(Float)
    unit_volume_source: Mapped[str | None] = mapped_column(String(255))
    daily_sales: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(64))
    warehouse: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="draft")


class ExportBatch(TimestampMixin, Base):
    __tablename__ = "export_batch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exported_by: Mapped[str | None] = mapped_column(String(128))
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    file_name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(64), default="completed")

    rows: Mapped[list["ExportRow"]] = relationship(back_populates="export_batch")


class ExportRow(TimestampMixin, Base):
    __tablename__ = "export_row"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    export_batch_id: Mapped[str] = mapped_column(ForeignKey("export_batch.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    claim_record_id: Mapped[str | None] = mapped_column(ForeignKey("sales_claim_forecast.id"))
    stocking_request_id: Mapped[str | None] = mapped_column(ForeignKey("stocking_request.id"))
    application_date: Mapped[date | None] = mapped_column(Date)
    stocking_type: Mapped[str | None] = mapped_column(String(64))
    selection_source: Mapped[str | None] = mapped_column(String(128))
    cost_price: Mapped[float | None] = mapped_column(Float)
    unit_volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    replenishment_reason: Mapped[str | None] = mapped_column(Text)
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    main_sku: Mapped[str] = mapped_column(String(128))
    sub_sku: Mapped[str] = mapped_column(String(128))
    claim_daily_sales: Mapped[float] = mapped_column(Float)
    stocking_quantity: Mapped[int] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(64))
    warehouse: Mapped[str | None] = mapped_column(String(128))

    export_batch: Mapped[ExportBatch] = relationship(back_populates="rows")


class ArrivalRecord(TimestampMixin, Base):
    __tablename__ = "arrival_record"
    __table_args__ = (UniqueConstraint("plm_arrival_batch_id", "claim_record_id", name="uq_arrival_record_plm_batch_claim"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("new_product_opportunity.id"))
    claim_record_id: Mapped[str | None] = mapped_column(ForeignKey("sales_claim_forecast.id"), index=True)
    plm_arrival_batch_id: Mapped[str | None] = mapped_column(ForeignKey("plm_arrival_batch.id"))
    plm_arrival_item_id: Mapped[str | None] = mapped_column(ForeignKey("plm_arrival_item.id"))
    salesperson_name: Mapped[str | None] = mapped_column(String(128), index=True)
    country: Mapped[str | None] = mapped_column(String(64))
    warehouse: Mapped[str | None] = mapped_column(String(128))
    arrived_quantity: Mapped[int | None] = mapped_column(Integer)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing_status: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)


class PlmArrivalBatch(TimestampMixin, Base):
    __tablename__ = "plm_arrival_batch"
    __table_args__ = (UniqueConstraint("source_hash", name="uq_plm_arrival_batch_source_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    arrival_date: Mapped[str] = mapped_column(String(10), index=True)
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    bloc_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default="processed")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    row_count: Mapped[int] = mapped_column(Integer, default=0)


class PlmArrivalItem(TimestampMixin, Base):
    __tablename__ = "plm_arrival_item"
    __table_args__ = (Index("ix_plm_arrival_item_batch_claim", "batch_id", "matched_claim_record_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("plm_arrival_batch.id"), index=True)
    source_sheet: Mapped[str | None] = mapped_column(String(128))
    source_row: Mapped[int | None] = mapped_column(Integer)
    arrival_type: Mapped[str] = mapped_column(String(32), index=True)
    product_name: Mapped[str | None] = mapped_column(String(255))
    salesperson_name: Mapped[str | None] = mapped_column(String(128), index=True)
    country: Mapped[str | None] = mapped_column(String(64))
    warehouse: Mapped[str | None] = mapped_column(String(128))
    main_sku: Mapped[str | None] = mapped_column(String(128))
    sub_sku: Mapped[str | None] = mapped_column(String(128), index=True)
    latest_storage_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_listing_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_quantity: Mapped[float | None] = mapped_column(Float)
    real_stock_quantity: Mapped[float | None] = mapped_column(Float)
    daily_sales: Mapped[float | None] = mapped_column(Float)
    match_status: Mapped[str] = mapped_column(String(64), default="unmatched", index=True)
    matched_claim_record_id: Mapped[str | None] = mapped_column(ForeignKey("sales_claim_forecast.id"), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ListingRecord(TimestampMixin, Base):
    __tablename__ = "listing_record"
    __table_args__ = (
        Index(
            "uq_listing_record_shop_item_active",
            "shop",
            "item",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_listing_record_owner_status", "salesperson_name", "status", "tracking_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_group_key: Mapped[str] = mapped_column(String(512), index=True)
    source_claim_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(64))
    business_period: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(64))
    site: Mapped[str | None] = mapped_column(String(32))
    main_sku: Mapped[str] = mapped_column(String(128), index=True)
    main_sku_name: Mapped[str | None] = mapped_column(String(255))
    salesperson_name: Mapped[str] = mapped_column(String(128), index=True)
    shop: Mapped[str] = mapped_column(String(255))
    item: Mapped[str] = mapped_column(String(255))
    listing_strategy: Mapped[str] = mapped_column(Text)
    first_period_start: Mapped[date | None] = mapped_column(Date)
    first_period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="active")
    tracking_status: Mapped[str] = mapped_column(String(32), default="active")
    initial_observation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
    is_shared_item: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    representative_rule: Mapped[str | None] = mapped_column(String(64))
    representative_sub_sku: Mapped[str | None] = mapped_column(String(128))
    created_by_user_id: Mapped[str | None] = mapped_column(String(36))
    created_by_name: Mapped[str | None] = mapped_column(String(128))

    periods: Mapped[list["ItemObservationPeriod"]] = relationship(back_populates="listing_record")
    bindings: Mapped[list["ListingSkuBinding"]] = relationship(back_populates="listing_record")


class ListingSkuBinding(TimestampMixin, Base):
    __tablename__ = "listing_sku_binding"
    __table_args__ = (
        UniqueConstraint("listing_record_id", "main_sku", "sub_sku", name="uq_listing_sku_binding_sku"),
        Index(
            "uq_listing_sku_binding_main_level",
            "listing_record_id",
            "main_sku",
            unique=True,
            sqlite_where=text("sub_sku IS NULL"),
            postgresql_where=text("sub_sku IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    listing_record_id: Mapped[str] = mapped_column(ForeignKey("listing_record.id"), index=True)
    main_sku: Mapped[str] = mapped_column(String(128), index=True)
    sub_sku: Mapped[str | None] = mapped_column(String(128), index=True)
    salesperson_name: Mapped[str | None] = mapped_column(String(128))
    opportunity_id: Mapped[str | None] = mapped_column(String(36))
    claim_record_id: Mapped[str | None] = mapped_column(String(36))
    binding_source: Mapped[str] = mapped_column(String(32), default="platform_confirm", server_default="platform_confirm")

    listing_record: Mapped[ListingRecord] = relationship(back_populates="bindings")


class ItemObservationPeriod(TimestampMixin, Base):
    __tablename__ = "item_observation_period"
    __table_args__ = (
        UniqueConstraint("listing_record_id", "week_number", "record_source", name="uq_item_observation_period_week"),
        UniqueConstraint("listing_record_id", "period_start", "record_source", name="uq_item_observation_period_start"),
        Index("ix_item_observation_period_status_start", "status", "period_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    listing_record_id: Mapped[str] = mapped_column(ForeignKey("listing_record.id"), index=True)
    week_number: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="pending_data")
    record_source: Mapped[str] = mapped_column(String(32), default="platform", server_default="platform")
    metrics_origin: Mapped[str | None] = mapped_column(String(32))
    order_count: Mapped[int | None] = mapped_column(Integer)
    total_revenue: Mapped[float | None] = mapped_column(Float)
    gross_profit_amount: Mapped[float | None] = mapped_column(Float)
    product_positioning: Mapped[str | None] = mapped_column(String(32))
    optimization_action: Mapped[str | None] = mapped_column(Text)
    four_week_summary: Mapped[str | None] = mapped_column(Text)
    source_snapshot: Mapped[dict | None] = mapped_column(JSON)
    metrics_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    listing_record: Mapped[ListingRecord] = relationship(back_populates="periods")


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


class SchedulerJobRun(TimestampMixin, Base):
    __tablename__ = "scheduler_job_run"
    __table_args__ = (UniqueConstraint("job_name", "run_date", name="uq_scheduler_job_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_name: Mapped[str] = mapped_column(String(64))
    run_date: Mapped[str] = mapped_column(String(10))
    report: Mapped[dict] = mapped_column(JSON, default=dict)
