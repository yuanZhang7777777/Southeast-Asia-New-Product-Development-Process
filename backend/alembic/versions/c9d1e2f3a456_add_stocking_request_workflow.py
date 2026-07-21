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
    with op.batch_alter_table("sales_claim_forecast", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("inventory_available", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("needs_stocking", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("stocking_decision_updated_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("stocking_request", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("claim_record_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("application_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("unit_volume_source", sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            "fk_stocking_request_claim_record",
            "sales_claim_forecast",
            ["claim_record_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_stocking_request_claim_record_id",
            ["claim_record_id"],
            unique=True,
        )

    with op.batch_alter_table("export_row", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("stocking_request_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("application_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("stocking_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("cost_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("unit_volume", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("volume", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("replenishment_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_export_row_stocking_request",
            "stocking_request",
            ["stocking_request_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("export_row", recreate="auto") as batch_op:
        batch_op.drop_constraint("fk_export_row_stocking_request", type_="foreignkey")
        batch_op.drop_column("replenishment_reason")
        batch_op.drop_column("volume")
        batch_op.drop_column("amount")
        batch_op.drop_column("unit_volume")
        batch_op.drop_column("cost_price")
        batch_op.drop_column("stocking_type")
        batch_op.drop_column("application_date")
        batch_op.drop_column("stocking_request_id")

    with op.batch_alter_table("stocking_request", recreate="auto") as batch_op:
        batch_op.drop_index("ix_stocking_request_claim_record_id")
        batch_op.drop_constraint("fk_stocking_request_claim_record", type_="foreignkey")
        batch_op.drop_column("unit_volume_source")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("application_date")
        batch_op.drop_column("claim_record_id")

    with op.batch_alter_table("sales_claim_forecast", recreate="auto") as batch_op:
        batch_op.drop_column("stocking_decision_updated_at")
        batch_op.drop_column("needs_stocking")
        batch_op.drop_column("inventory_available")
