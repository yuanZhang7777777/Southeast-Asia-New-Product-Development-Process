"""add operator profile order and priority

Revision ID: d4f7a8c9b012
Revises: c6b2e1a0f4d9
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision: str = "d4f7a8c9b012"
down_revision: str | None = "c6b2e1a0f4d9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("operator_assignment_profile")}
    with op.batch_alter_table("operator_assignment_profile") as batch_op:
        if "assignment_priority" not in existing_columns:
            batch_op.add_column(sa.Column("assignment_priority", sa.Integer(), server_default="0", nullable=False))
        if "display_order" not in existing_columns:
            batch_op.add_column(sa.Column("display_order", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("operator_assignment_profile")}
    with op.batch_alter_table("operator_assignment_profile") as batch_op:
        if "display_order" in existing_columns:
            batch_op.drop_column("display_order")
        if "assignment_priority" in existing_columns:
            batch_op.drop_column("assignment_priority")
