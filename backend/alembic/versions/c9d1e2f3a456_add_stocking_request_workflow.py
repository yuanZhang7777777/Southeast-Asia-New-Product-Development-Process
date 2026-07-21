"""add stocking request workflow

Revision ID: c9d1e2f3a456
Revises: a8d4e6f7b901
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9d1e2f3a456"
down_revision: str | None = "a8d4e6f7b901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sales_claim_forecast", sa.Column("inventory_available", sa.Boolean(), nullable=True))
    op.add_column("sales_claim_forecast", sa.Column("needs_stocking", sa.Boolean(), nullable=True))
    op.add_column(
        "sales_claim_forecast",
        sa.Column("stocking_decision_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column("stocking_request", sa.Column("claim_record_id", sa.String(length=36), nullable=True))
    op.add_column("stocking_request", sa.Column("application_date", sa.Date(), nullable=True))
    op.add_column("stocking_request", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stocking_request", sa.Column("unit_volume_source", sa.String(length=255), nullable=True))
    op.create_foreign_key(
        "fk_stocking_request_claim_record",
        "stocking_request",
        "sales_claim_forecast",
        ["claim_record_id"],
        ["id"],
    )
    op.create_index(
        "ix_stocking_request_claim_record_id",
        "stocking_request",
        ["claim_record_id"],
        unique=True,
    )

    op.add_column("export_row", sa.Column("stocking_request_id", sa.String(length=36), nullable=True))
    op.add_column("export_row", sa.Column("application_date", sa.Date(), nullable=True))
    op.add_column("export_row", sa.Column("stocking_type", sa.String(length=64), nullable=True))
    op.add_column("export_row", sa.Column("cost_price", sa.Float(), nullable=True))
    op.add_column("export_row", sa.Column("unit_volume", sa.Float(), nullable=True))
    op.add_column("export_row", sa.Column("amount", sa.Float(), nullable=True))
    op.add_column("export_row", sa.Column("volume", sa.Float(), nullable=True))
    op.add_column("export_row", sa.Column("replenishment_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_export_row_stocking_request",
        "export_row",
        "stocking_request",
        ["stocking_request_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_export_row_stocking_request", "export_row", type_="foreignkey")
    op.drop_column("export_row", "replenishment_reason")
    op.drop_column("export_row", "volume")
    op.drop_column("export_row", "amount")
    op.drop_column("export_row", "unit_volume")
    op.drop_column("export_row", "cost_price")
    op.drop_column("export_row", "stocking_type")
    op.drop_column("export_row", "application_date")
    op.drop_column("export_row", "stocking_request_id")

    op.drop_index("ix_stocking_request_claim_record_id", table_name="stocking_request")
    op.drop_constraint("fk_stocking_request_claim_record", "stocking_request", type_="foreignkey")
    op.drop_column("stocking_request", "unit_volume_source")
    op.drop_column("stocking_request", "submitted_at")
    op.drop_column("stocking_request", "application_date")
    op.drop_column("stocking_request", "claim_record_id")

    op.drop_column("sales_claim_forecast", "stocking_decision_updated_at")
    op.drop_column("sales_claim_forecast", "needs_stocking")
    op.drop_column("sales_claim_forecast", "inventory_available")