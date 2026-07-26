import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app import models  # noqa: E402, F401
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402


def test_stocking_workflow_columns_are_migration_safe() -> None:
    claim = Base.metadata.tables["sales_claim_forecast"]
    request = Base.metadata.tables["stocking_request"]
    export_row = Base.metadata.tables["export_row"]

    assert {"inventory_available", "needs_stocking", "stocking_decision_updated_at"} <= set(claim.c.keys())
    assert {
        "claim_record_id",
        "application_date",
        "submitted_at",
        "unit_volume_source",
        "length_cm",
        "width_cm",
        "height_cm",
    } <= set(request.c.keys())
    assert {
        "stocking_request_id",
        "application_date",
        "stocking_type",
        "selection_source",
        "cost_price",
        "unit_volume",
        "amount",
        "volume",
        "replenishment_reason",
    } <= set(export_row.c.keys())
    assert all(
        column.nullable
        for column in (
            claim.c.inventory_available,
            claim.c.needs_stocking,
            claim.c.stocking_decision_updated_at,
            request.c.claim_record_id,
            request.c.application_date,
            request.c.submitted_at,
            request.c.unit_volume_source,
            request.c.length_cm,
            request.c.width_cm,
            request.c.height_cm,
            export_row.c.stocking_request_id,
            export_row.c.application_date,
            export_row.c.stocking_type,
            export_row.c.selection_source,
            export_row.c.cost_price,
            export_row.c.unit_volume,
            export_row.c.amount,
            export_row.c.volume,
            export_row.c.replenishment_reason,
        )
    )
    assert request.c.quantity.nullable is False
    assert any(index.unique and tuple(index.columns) == (request.c.claim_record_id,) for index in request.indexes)
    assert {foreign_key.target_fullname for foreign_key in request.c.claim_record_id.foreign_keys} == {
        "sales_claim_forecast.id"
    }


def test_stocking_workflow_migration_is_the_single_head() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["f1a2b3c4d567"]
    assert script.get_revision("e1f2a3b4c678").down_revision == "d0e2f3a4b567"


def test_sqlite_upgrade_from_previous_head_preserves_legacy_rows(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'stocking_migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "a8d4e6f7b901")
        now = "2026-07-21 00:00:00"
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO new_product_opportunity
                    (id, source_type, main_sku, sub_sku, current_status, snapshot, created_at, updated_at)
                    VALUES ('opportunity-legacy', 'manual', 'MAIN-LEGACY', 'SUB-LEGACY', 'ready_for_stocking', '{}', :now, :now)"""
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """INSERT INTO stocking_request
                    (id, opportunity_id, request_type, quantity, status, created_at, updated_at)
                    VALUES ('request-legacy', 'opportunity-legacy', 'initial', 30, 'draft', :now, :now)"""
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """INSERT INTO export_batch
                    (id, exported_at, file_name, scope, row_count, status, created_at, updated_at)
                    VALUES ('batch-legacy', :now, 'legacy.xlsx', 'stocking_available', 1, 'completed', :now, :now)"""
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    """INSERT INTO export_row
                    (id, export_batch_id, opportunity_id, main_sku, sub_sku, claim_daily_sales,
                     stocking_quantity, created_at, updated_at)
                    VALUES ('row-legacy', 'batch-legacy', 'opportunity-legacy', 'MAIN-LEGACY',
                            'SUB-LEGACY', 1, 30, :now, :now)"""
                ),
                {"now": now},
            )

        command.upgrade(config, "head")

        table_names = set(inspect(engine).get_table_names())
        assert {"stocking_request", "export_row"} <= table_names
        with engine.connect() as connection:
            request = connection.execute(
                text("SELECT id, claim_record_id FROM stocking_request WHERE id = 'request-legacy'")
            ).one()
            export_row = connection.execute(
                text("SELECT id, stocking_request_id, selection_source FROM export_row WHERE id = 'row-legacy'")
            ).one()
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert request == ("request-legacy", None)
        assert export_row == ("row-legacy", None, None)
        assert revision == "f1a2b3c4d567"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_listing_binding_backfill_on_upgrade(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'binding_migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "d7e8f9a0b123")
        now = "2026-07-21 00:00:00"
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO listing_record
                    (id, source_group_key, source_claim_ids, source_type, main_sku, salesperson_name, shop, item,
                     listing_strategy, first_period_start, first_period_end, status, tracking_status, created_at, updated_at)
                    VALUES ('listing-legacy', 'task-legacy', '[]', 'selection1_developer_claim_feedback', 'MAIN-LEGACY',
                            '销售L', 'Shopee-PH-L', 'ITEM-LEGACY', '策略', '2026-07-16', '2026-07-22', 'active', 'active',
                            :now, :now)"""
                ),
                {"now": now},
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            binding = connection.execute(
                text(
                    "SELECT listing_record_id, main_sku, sub_sku, salesperson_name, binding_source FROM listing_sku_binding"
                )
            ).one()
            listing = connection.execute(
                text("SELECT representative_rule, is_shared_item FROM listing_record WHERE id = 'listing-legacy'")
            ).one()
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert binding == ("listing-legacy", "MAIN-LEGACY", None, "销售L", "platform_migrated")
        assert listing[0] == "single_binding"
        assert not listing[1]
        assert revision == "f1a2b3c4d567"
    finally:
        engine.dispose()
        get_settings.cache_clear()
