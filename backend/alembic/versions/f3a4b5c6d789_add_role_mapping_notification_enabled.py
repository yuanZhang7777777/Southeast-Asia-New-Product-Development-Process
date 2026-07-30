"""add role mapping notification preference

Revision ID: f3a4b5c6d789
Revises: f1a2b3c4d567
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d789"
down_revision: str | None = "f1a2b3c4d567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("role_mapping")}
    if "notification_enabled" not in columns:
        with op.batch_alter_table("role_mapping") as batch_op:
            batch_op.add_column(sa.Column("notification_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("role_mapping")}
    if "notification_enabled" in columns:
        with op.batch_alter_table("role_mapping") as batch_op:
            batch_op.drop_column("notification_enabled")
