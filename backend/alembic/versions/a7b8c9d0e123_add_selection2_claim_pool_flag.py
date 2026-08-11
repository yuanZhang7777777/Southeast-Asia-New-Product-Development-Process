"""add selection2 claim pool flag

Revision ID: a7b8c9d0e123
Revises: f3a4b5c6d789
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e123"
down_revision: str | None = "f3a4b5c6d789"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("new_product_opportunity") as batch_op:
        batch_op.add_column(
            sa.Column("claim_pool_open", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        sa.text(
            "UPDATE new_product_opportunity "
            "SET claim_pool_open = true "
            "WHERE source_type = 'selection2_caigen_claim_feedback'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("new_product_opportunity") as batch_op:
        batch_op.drop_column("claim_pool_open")
