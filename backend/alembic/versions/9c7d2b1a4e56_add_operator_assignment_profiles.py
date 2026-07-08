"""add operator assignment profiles

Revision ID: 9c7d2b1a4e56
Revises: 7aaf1f78c47d
Create Date: 2026-07-03 10:05:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9c7d2b1a4e56"
down_revision: str | None = "7aaf1f78c47d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operator_assignment_profile",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operator_name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("operator_level", sa.String(length=64), nullable=True),
        sa.Column("business_type", sa.String(length=128), nullable=True),
        sa.Column("key_site", sa.String(length=32), nullable=True),
        sa.Column("key_category1", sa.String(length=128), nullable=True),
        sa.Column("key_category2", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operator_name", name="uq_operator_assignment_profile_name"),
    )
    op.create_index(
        op.f("ix_operator_assignment_profile_operator_name"),
        "operator_assignment_profile",
        ["operator_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_operator_assignment_profile_operator_name"), table_name="operator_assignment_profile")
    op.drop_table("operator_assignment_profile")
