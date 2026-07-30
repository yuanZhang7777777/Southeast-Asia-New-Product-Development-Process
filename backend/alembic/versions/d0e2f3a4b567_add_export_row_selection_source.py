"""add export row selection source snapshot

Revision ID: d0e2f3a4b567
Revises: c9d1e2f3a456
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d0e2f3a4b567"
down_revision: str | None = "c9d1e2f3a456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("export_row", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("selection_source", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("export_row", recreate="auto") as batch_op:
        batch_op.drop_column("selection_source")