"""add listing sku binding and item archive columns

Revision ID: e0f1a2b3c456
Revises: d7e8f9a0b123
Create Date: 2026-07-26
"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e0f1a2b3c456"
down_revision: str | None = "d7e8f9a0b123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "listing_sku_binding" not in tables:
        op.create_table(
            "listing_sku_binding",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("listing_record_id", sa.String(length=36), sa.ForeignKey("listing_record.id"), nullable=False),
            sa.Column("main_sku", sa.String(length=128), nullable=False),
            sa.Column("sub_sku", sa.String(length=128), nullable=True),
            sa.Column("salesperson_name", sa.String(length=128), nullable=True),
            sa.Column("opportunity_id", sa.String(length=36), nullable=True),
            sa.Column("claim_record_id", sa.String(length=36), nullable=True),
            sa.Column("binding_source", sa.String(length=32), nullable=False, server_default="platform_confirm"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("listing_record_id", "main_sku", "sub_sku", name="uq_listing_sku_binding_sku"),
        )
        op.create_index(op.f("ix_listing_sku_binding_listing_record_id"), "listing_sku_binding", ["listing_record_id"])
        op.create_index(op.f("ix_listing_sku_binding_main_sku"), "listing_sku_binding", ["main_sku"])
        op.create_index(op.f("ix_listing_sku_binding_sub_sku"), "listing_sku_binding", ["sub_sku"])
    binding_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("listing_sku_binding")}
    if "uq_listing_sku_binding_main_level" not in binding_indexes:
        op.create_index(
            "uq_listing_sku_binding_main_level",
            "listing_sku_binding",
            ["listing_record_id", "main_sku"],
            unique=True,
            postgresql_where=sa.text("sub_sku IS NULL"),
            sqlite_where=sa.text("sub_sku IS NULL"),
        )

    listing_columns = {column["name"] for column in inspector.get_columns("listing_record")}
    listing_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("listing_record")}
    with op.batch_alter_table("listing_record") as batch_op:
        if "is_shared_item" not in listing_columns:
            batch_op.add_column(sa.Column("is_shared_item", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "representative_rule" not in listing_columns:
            batch_op.add_column(sa.Column("representative_rule", sa.String(length=64), nullable=True))
        if "representative_sub_sku" not in listing_columns:
            batch_op.add_column(sa.Column("representative_sub_sku", sa.String(length=128), nullable=True))
        batch_op.alter_column("first_period_start", existing_type=sa.Date(), nullable=True)
        batch_op.alter_column("first_period_end", existing_type=sa.Date(), nullable=True)
        if "uq_listing_record_item" in listing_uniques:
            batch_op.drop_constraint("uq_listing_record_item", type_="unique")
    listing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("listing_record")}
    if "uq_listing_record_shop_item_active" not in listing_indexes:
        op.create_index(
            "uq_listing_record_shop_item_active",
            "listing_record",
            ["shop", "item"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        )

    period_columns = {column["name"] for column in inspector.get_columns("item_observation_period")}
    period_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("item_observation_period")}
    with op.batch_alter_table("item_observation_period") as batch_op:
        if "record_source" not in period_columns:
            batch_op.add_column(sa.Column("record_source", sa.String(length=32), nullable=False, server_default="platform"))
        if "metrics_origin" not in period_columns:
            batch_op.add_column(sa.Column("metrics_origin", sa.String(length=32), nullable=True))
        batch_op.alter_column("period_start", existing_type=sa.Date(), nullable=True)
        batch_op.alter_column("period_end", existing_type=sa.Date(), nullable=True)
        if "uq_item_observation_period_week" in period_uniques:
            batch_op.drop_constraint("uq_item_observation_period_week", type_="unique")
        if "uq_item_observation_period_start" in period_uniques:
            batch_op.drop_constraint("uq_item_observation_period_start", type_="unique")
        batch_op.create_unique_constraint(
            "uq_item_observation_period_week", ["listing_record_id", "week_number", "record_source"]
        )
        batch_op.create_unique_constraint(
            "uq_item_observation_period_start", ["listing_record_id", "period_start", "record_source"]
        )

    listings = bind.execute(
        sa.text(
            "SELECT lr.id, lr.main_sku, lr.salesperson_name, lr.created_at, lr.updated_at FROM listing_record lr "
            "WHERE NOT EXISTS (SELECT 1 FROM listing_sku_binding b WHERE b.listing_record_id = lr.id)"
        )
    ).all()
    for row in listings:
        bind.execute(
            sa.text(
                "INSERT INTO listing_sku_binding "
                "(id, listing_record_id, main_sku, sub_sku, salesperson_name, binding_source, created_at, updated_at) "
                "VALUES (:id, :listing_record_id, :main_sku, NULL, :salesperson_name, 'platform_migrated', :created_at, :updated_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "listing_record_id": row.id,
                "main_sku": row.main_sku,
                "salesperson_name": row.salesperson_name,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
        )
    bind.execute(
        sa.text("UPDATE listing_record SET representative_rule = 'single_binding' WHERE representative_rule IS NULL")
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    blockers = {
        "listing_record.item 跨店铺/作废重刊登重复": (
            "SELECT item FROM listing_record GROUP BY item HAVING count(*) > 1"
        ),
        "item_observation_period 同周多来源行": (
            "SELECT listing_record_id FROM item_observation_period GROUP BY listing_record_id, week_number HAVING count(*) > 1"
        ),
        "item_observation_period 同起始日多来源行": (
            "SELECT listing_record_id FROM item_observation_period GROUP BY listing_record_id, period_start HAVING count(*) > 1"
        ),
        "item_observation_period 存在空周窗行": (
            "SELECT id FROM item_observation_period WHERE period_start IS NULL"
        ),
        "listing_record 存在空首周行": (
            "SELECT id FROM listing_record WHERE first_period_start IS NULL"
        ),
    }
    conflicts = [label for label, query in blockers.items() if bind.execute(sa.text(query)).first() is not None]
    if conflicts:
        raise RuntimeError(
            "downgrade blocked: 新口径数据与旧唯一约束冲突（"
            + "；".join(conflicts)
            + "）。请先人工归并/删除冲突行，或直接用备份恢复。"
        )

    period_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("item_observation_period")}
    period_columns = {column["name"] for column in inspector.get_columns("item_observation_period")}
    with op.batch_alter_table("item_observation_period") as batch_op:
        if "uq_item_observation_period_week" in period_uniques:
            batch_op.drop_constraint("uq_item_observation_period_week", type_="unique")
        if "uq_item_observation_period_start" in period_uniques:
            batch_op.drop_constraint("uq_item_observation_period_start", type_="unique")
        batch_op.create_unique_constraint("uq_item_observation_period_week", ["listing_record_id", "week_number"])
        batch_op.create_unique_constraint("uq_item_observation_period_start", ["listing_record_id", "period_start"])
        batch_op.alter_column("period_start", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("period_end", existing_type=sa.Date(), nullable=False)
        if "metrics_origin" in period_columns:
            batch_op.drop_column("metrics_origin")
        if "record_source" in period_columns:
            batch_op.drop_column("record_source")

    listing_indexes = {index["name"] for index in inspector.get_indexes("listing_record")}
    if "uq_listing_record_shop_item_active" in listing_indexes:
        op.drop_index("uq_listing_record_shop_item_active", table_name="listing_record")
    listing_columns = {column["name"] for column in inspector.get_columns("listing_record")}
    with op.batch_alter_table("listing_record") as batch_op:
        batch_op.create_unique_constraint("uq_listing_record_item", ["item"])
        batch_op.alter_column("first_period_start", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("first_period_end", existing_type=sa.Date(), nullable=False)
        if "representative_sub_sku" in listing_columns:
            batch_op.drop_column("representative_sub_sku")
        if "representative_rule" in listing_columns:
            batch_op.drop_column("representative_rule")
        if "is_shared_item" in listing_columns:
            batch_op.drop_column("is_shared_item")

    if "listing_sku_binding" in set(inspector.get_table_names()):
        binding_indexes = {index["name"] for index in inspector.get_indexes("listing_sku_binding")}
        if "uq_listing_sku_binding_main_level" in binding_indexes:
            op.drop_index("uq_listing_sku_binding_main_level", table_name="listing_sku_binding")
        op.drop_index(op.f("ix_listing_sku_binding_sub_sku"), table_name="listing_sku_binding")
        op.drop_index(op.f("ix_listing_sku_binding_main_sku"), table_name="listing_sku_binding")
        op.drop_index(op.f("ix_listing_sku_binding_listing_record_id"), table_name="listing_sku_binding")
        op.drop_table("listing_sku_binding")
