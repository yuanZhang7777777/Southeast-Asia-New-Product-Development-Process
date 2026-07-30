"""add secondary research target and selling points

Revision ID: f2a3b4c5d678
Revises: e1f2a3b4c678
Create Date: 2026-07-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d678"
down_revision: str | None = "e1f2a3b4c678"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sales_claim_forecast")}
    with op.batch_alter_table("sales_claim_forecast") as batch_op:
        if "secondary_target_daily_sales" not in existing:
            batch_op.add_column(sa.Column("secondary_target_daily_sales", sa.Float(), nullable=True))
        if "secondary_selling_points" not in existing:
            batch_op.add_column(sa.Column("secondary_selling_points", sa.Text(), nullable=True))


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sales_claim_forecast")}
    with op.batch_alter_table("sales_claim_forecast") as batch_op:
        if "secondary_selling_points" in existing:
            batch_op.drop_column("secondary_selling_points")
        if "secondary_target_daily_sales" in existing:
            batch_op.drop_column("secondary_target_daily_sales")
