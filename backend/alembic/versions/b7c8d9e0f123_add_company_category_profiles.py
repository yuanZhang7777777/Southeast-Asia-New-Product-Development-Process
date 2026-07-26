"""add company category profiles

Revision ID: b7c8d9e0f123
Revises: f2a3b4c5d678, f6b0c2d3e456
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f123"
down_revision: str | tuple[str, str] | None = ("f2a3b4c5d678", "f6b0c2d3e456")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "company_category" not in tables:
        op.create_table(
            "company_category",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("level1", sa.String(length=128), nullable=False),
            sa.Column("level2", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("source_file", sa.String(length=255), nullable=True),
            sa.Column("source_sheet", sa.String(length=128), nullable=True),
            sa.Column("source_row", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("level1", "level2", name="uq_company_category_pair"),
        )
        op.create_index(op.f("ix_company_category_level1"), "company_category", ["level1"])

    profile_columns = {column["name"] for column in inspector.get_columns("operator_assignment_profile")}
    if "key_categories" not in profile_columns:
        with op.batch_alter_table("operator_assignment_profile") as batch_op:
            batch_op.add_column(sa.Column("key_categories", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    profile_columns = {column["name"] for column in inspector.get_columns("operator_assignment_profile")}
    if "key_categories" in profile_columns:
        with op.batch_alter_table("operator_assignment_profile") as batch_op:
            batch_op.drop_column("key_categories")

    if "company_category" in set(inspector.get_table_names()):
        op.drop_index(op.f("ix_company_category_level1"), table_name="company_category")
        op.drop_table("company_category")
