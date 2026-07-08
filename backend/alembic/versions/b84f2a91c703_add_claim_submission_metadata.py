"""add claim submission metadata

Revision ID: b84f2a91c703
Revises: 9c7d2b1a4e56
Create Date: 2026-07-03 10:17:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b84f2a91c703"
down_revision: str | None = "9c7d2b1a4e56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sales_claim_forecast") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("claim_source", sa.String(length=64), server_default="assigned_task", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "first_submitted_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))
        batch_op.create_foreign_key("fk_sales_claim_forecast_task_id", "flow_task", ["task_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("sales_claim_forecast") as batch_op:
        batch_op.drop_constraint("fk_sales_claim_forecast_task_id", type_="foreignkey")
        batch_op.drop_column("note")
        batch_op.drop_column("last_updated_at")
        batch_op.drop_column("first_submitted_at")
        batch_op.drop_column("claim_source")
        batch_op.drop_column("task_id")
