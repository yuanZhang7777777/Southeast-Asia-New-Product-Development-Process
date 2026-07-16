"""add listing observation workbench

Revision ID: a8d4e6f7b901
Revises: a7c1d3e4f567
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a8d4e6f7b901"
down_revision: str | None = "a7c1d3e4f567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_group_key", sa.String(length=512), nullable=False),
        sa.Column("source_claim_ids", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("business_period", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("site", sa.String(length=32), nullable=True),
        sa.Column("main_sku", sa.String(length=128), nullable=False),
        sa.Column("main_sku_name", sa.String(length=255), nullable=True),
        sa.Column("salesperson_name", sa.String(length=128), nullable=False),
        sa.Column("shop", sa.String(length=255), nullable=False),
        sa.Column("item", sa.String(length=255), nullable=False),
        sa.Column("listing_strategy", sa.Text(), nullable=False),
        sa.Column("first_period_start", sa.Date(), nullable=False),
        sa.Column("first_period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tracking_status", sa.String(length=32), nullable=False),
        sa.Column("initial_observation_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item", name="uq_listing_record_item"),
    )
    op.create_index("ix_listing_record_main_sku", "listing_record", ["main_sku"])
    op.create_index("ix_listing_record_salesperson_name", "listing_record", ["salesperson_name"])
    op.create_index("ix_listing_record_source_group_key", "listing_record", ["source_group_key"])
    op.create_index(
        "ix_listing_record_owner_status", "listing_record", ["salesperson_name", "status", "tracking_status"]
    )

    op.create_table(
        "item_observation_period",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("listing_record_id", sa.String(length=36), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("order_count", sa.Integer(), nullable=True),
        sa.Column("total_revenue", sa.Float(), nullable=True),
        sa.Column("gross_profit_amount", sa.Float(), nullable=True),
        sa.Column("product_positioning", sa.String(length=32), nullable=True),
        sa.Column("optimization_action", sa.Text(), nullable=True),
        sa.Column("four_week_summary", sa.Text(), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
        sa.Column("metrics_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_record_id"], ["listing_record.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_record_id", "week_number", name="uq_item_observation_period_week"),
        sa.UniqueConstraint("listing_record_id", "period_start", name="uq_item_observation_period_start"),
    )
    op.create_index("ix_item_observation_period_listing_record_id", "item_observation_period", ["listing_record_id"])
    op.create_index("ix_item_observation_period_status_start", "item_observation_period", ["status", "period_start"])
    op.drop_table("four_week_summary")


def downgrade() -> None:
    op.create_table(
        "four_week_summary",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("summary_user", sa.String(length=128), nullable=True),
        sa.Column("achieved", sa.Boolean(), nullable=True),
        sa.Column("out_of_stock_impact", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["new_product_opportunity.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.drop_index("ix_item_observation_period_status_start", table_name="item_observation_period")
    op.drop_index("ix_item_observation_period_listing_record_id", table_name="item_observation_period")
    op.drop_table("item_observation_period")
    op.drop_index("ix_listing_record_owner_status", table_name="listing_record")
    op.drop_index("ix_listing_record_source_group_key", table_name="listing_record")
    op.drop_index("ix_listing_record_salesperson_name", table_name="listing_record")
    op.drop_index("ix_listing_record_main_sku", table_name="listing_record")
    op.drop_table("listing_record")
