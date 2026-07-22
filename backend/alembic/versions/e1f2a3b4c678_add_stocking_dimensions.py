"""add stocking request dimensions

Revision ID: e1f2a3b4c678
Revises: d0e2f3a4b567
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c678"
down_revision: str | None = "d0e2f3a4b567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stocking_request", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("length_cm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("width_cm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("height_cm", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stocking_request", recreate="auto") as batch_op:
        batch_op.drop_column("height_cm")
        batch_op.drop_column("width_cm")
        batch_op.drop_column("length_cm")
