"""add plm arrival batches

Revision ID: a7c1d3e4f567
Revises: f6b0c2d3e456
Create Date: 2026-07-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7c1d3e4f567"
down_revision: str | None = "f6b0c2d3e456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plm_arrival_batch",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("arrival_date", sa.String(length=10), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("bloc_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash", name="uq_plm_arrival_batch_source_hash"),
    )
    op.create_index("ix_plm_arrival_batch_arrival_date", "plm_arrival_batch", ["arrival_date"])
    op.create_index("ix_plm_arrival_batch_source_hash", "plm_arrival_batch", ["source_hash"])
    op.create_table(
        "plm_arrival_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("source_sheet", sa.String(length=128), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("arrival_type", sa.String(length=32), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("salesperson_name", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("warehouse", sa.String(length=128), nullable=True),
        sa.Column("main_sku", sa.String(length=128), nullable=True),
        sa.Column("sub_sku", sa.String(length=128), nullable=True),
        sa.Column("latest_storage_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_listing_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_quantity", sa.Float(), nullable=True),
        sa.Column("real_stock_quantity", sa.Float(), nullable=True),
        sa.Column("daily_sales", sa.Float(), nullable=True),
        sa.Column("match_status", sa.String(length=64), nullable=False),
        sa.Column("matched_claim_record_id", sa.String(length=36), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["plm_arrival_batch.id"]),
        sa.ForeignKeyConstraint(["matched_claim_record_id"], ["sales_claim_forecast.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plm_arrival_item_batch_id", "plm_arrival_item", ["batch_id"])
    op.create_index("ix_plm_arrival_item_arrival_type", "plm_arrival_item", ["arrival_type"])
    op.create_index("ix_plm_arrival_item_match_status", "plm_arrival_item", ["match_status"])
    op.create_index("ix_plm_arrival_item_salesperson_name", "plm_arrival_item", ["salesperson_name"])
    op.create_index("ix_plm_arrival_item_sub_sku", "plm_arrival_item", ["sub_sku"])
    op.create_index("ix_plm_arrival_item_matched_claim_record_id", "plm_arrival_item", ["matched_claim_record_id"])
    op.create_index("ix_plm_arrival_item_batch_claim", "plm_arrival_item", ["batch_id", "matched_claim_record_id"])
    with op.batch_alter_table("arrival_record") as batch_op:
        batch_op.add_column(sa.Column("plm_arrival_batch_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("plm_arrival_item_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key("fk_arrival_record_plm_batch", "plm_arrival_batch", ["plm_arrival_batch_id"], ["id"])
        batch_op.create_foreign_key("fk_arrival_record_plm_item", "plm_arrival_item", ["plm_arrival_item_id"], ["id"])
        batch_op.create_unique_constraint("uq_arrival_record_plm_batch_claim", ["plm_arrival_batch_id", "claim_record_id"])


def downgrade() -> None:
    with op.batch_alter_table("arrival_record") as batch_op:
        batch_op.drop_constraint("uq_arrival_record_plm_batch_claim", type_="unique")
        batch_op.drop_constraint("fk_arrival_record_plm_item", type_="foreignkey")
        batch_op.drop_constraint("fk_arrival_record_plm_batch", type_="foreignkey")
        batch_op.drop_column("plm_arrival_item_id")
        batch_op.drop_column("plm_arrival_batch_id")
    op.drop_index("ix_plm_arrival_item_batch_claim", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_matched_claim_record_id", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_sub_sku", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_salesperson_name", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_match_status", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_arrival_type", table_name="plm_arrival_item")
    op.drop_index("ix_plm_arrival_item_batch_id", table_name="plm_arrival_item")
    op.drop_table("plm_arrival_item")
    op.drop_index("ix_plm_arrival_batch_source_hash", table_name="plm_arrival_batch")
    op.drop_index("ix_plm_arrival_batch_arrival_date", table_name="plm_arrival_batch")
    op.drop_table("plm_arrival_batch")
