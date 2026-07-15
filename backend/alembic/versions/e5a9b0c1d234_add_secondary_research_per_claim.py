"""add secondary research per claim

Revision ID: e5a9b0c1d234
Revises: d4f7a8c9b012
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision: str = "e5a9b0c1d234"
down_revision: str | None = "d4f7a8c9b012"
branch_labels: str | None = None
depends_on: str | None = None


def add_columns(table_name: str, columns: list[sa.Column]) -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        for column in columns:
            if column.name not in existing:
                batch_op.add_column(column)


def upgrade() -> None:
    add_columns(
        "sales_claim_forecast",
        [
            sa.Column("downstream_status", sa.String(length=64), nullable=True),
            sa.Column("arrival_detected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("secondary_research_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("secondary_competitor_url", sa.Text(), nullable=True),
            sa.Column("secondary_conclusion", sa.Text(), nullable=True),
            sa.Column("product_positioning", sa.String(length=32), nullable=True),
            sa.Column("secondary_evidence_images", sa.JSON(), nullable=True),
            sa.Column("secondary_research_submitted_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    add_columns(
        "review_record",
        [
            sa.Column(
                "claim_record_id",
                sa.String(length=36),
                sa.ForeignKey("sales_claim_forecast.id", name="fk_review_record_claim_record"),
                nullable=True,
            )
        ],
    )
    add_columns(
        "arrival_record",
        [
            sa.Column(
                "claim_record_id",
                sa.String(length=36),
                sa.ForeignKey("sales_claim_forecast.id", name="fk_arrival_record_claim_record"),
                nullable=True,
            ),
            sa.Column("salesperson_name", sa.String(length=128), nullable=True),
            sa.Column("country", sa.String(length=64), nullable=True),
        ],
    )


def downgrade() -> None:
    for table_name, names in [
        ("arrival_record", ["country", "salesperson_name", "claim_record_id"]),
        ("review_record", ["claim_record_id"]),
        (
            "sales_claim_forecast",
            [
                "secondary_research_submitted_at",
                "secondary_evidence_images",
                "product_positioning",
                "secondary_conclusion",
                "secondary_competitor_url",
                "secondary_research_at",
                "arrival_detected_at",
                "downstream_status",
            ],
        ),
    ]:
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}
        with op.batch_alter_table(table_name) as batch_op:
            for name in names:
                if name in existing:
                    batch_op.drop_column(name)
