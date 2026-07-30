"""add scheduler job run

Revision ID: d7e8f9a0b123
Revises: b7c8d9e0f123
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b123"
down_revision: str | None = "b7c8d9e0f123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "scheduler_job_run" not in set(inspector.get_table_names()):
        op.create_table(
            "scheduler_job_run",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("job_name", sa.String(length=64), nullable=False),
            sa.Column("run_date", sa.String(length=10), nullable=False),
            sa.Column("report", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_name", "run_date", name="uq_scheduler_job_run"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "scheduler_job_run" in set(inspector.get_table_names()):
        op.drop_table("scheduler_job_run")
