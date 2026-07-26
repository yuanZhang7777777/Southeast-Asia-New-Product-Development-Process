"""add performance indexes for opportunity and snapshot lookups

Revision ID: f1a2b3c4d567
Revises: e0f1a2b3c456
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d567"
down_revision: str | None = "e0f1a2b3c456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if "ix_opportunity_source_batch_sub_sku" not in _index_names("new_product_opportunity"):
        op.create_index(
            "ix_opportunity_source_batch_sub_sku",
            "new_product_opportunity",
            ["source_type", "batch", "sub_sku"],
        )
    if "ix_source_record_snapshot_opportunity_id" not in _index_names("source_record_snapshot"):
        op.create_index(
            "ix_source_record_snapshot_opportunity_id",
            "source_record_snapshot",
            ["opportunity_id"],
        )


def downgrade() -> None:
    if "ix_source_record_snapshot_opportunity_id" in _index_names("source_record_snapshot"):
        op.drop_index("ix_source_record_snapshot_opportunity_id", table_name="source_record_snapshot")
    if "ix_opportunity_source_batch_sub_sku" in _index_names("new_product_opportunity"):
        op.drop_index("ix_opportunity_source_batch_sub_sku", table_name="new_product_opportunity")
