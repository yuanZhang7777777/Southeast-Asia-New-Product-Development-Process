"""separate business period from source sheet

Revision ID: f6b0c2d3e456
Revises: e5a9b0c1d234
Create Date: 2026-07-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6b0c2d3e456"
down_revision: str | None = "e5a9b0c1d234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("import_batch") as batch_op:
        batch_op.add_column(sa.Column("business_period", sa.String(length=128), nullable=True))
        batch_op.create_index("ix_import_batch_business_period", ["business_period"])

    with op.batch_alter_table("new_product_opportunity") as batch_op:
        batch_op.drop_constraint("uq_opportunity_source_row", type_="unique")
        batch_op.create_index(
            "ix_opportunity_source_trace",
            ["source_type", "source_file", "source_sheet", "source_row"],
        )


def downgrade() -> None:
    with op.batch_alter_table("new_product_opportunity") as batch_op:
        batch_op.drop_index("ix_opportunity_source_trace")
        batch_op.create_unique_constraint(
            "uq_opportunity_source_row",
            ["source_type", "source_file", "source_sheet", "source_row"],
        )

    with op.batch_alter_table("import_batch") as batch_op:
        batch_op.drop_index("ix_import_batch_business_period")
        batch_op.drop_column("business_period")
