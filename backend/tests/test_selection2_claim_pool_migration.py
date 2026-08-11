import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402


def test_selection2_claim_pool_migration_opens_only_normal_selection2(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'selection2_claim_pool.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "f3a4b5c6d789")
        now = "2026-07-31 00:00:00"
        with engine.begin() as connection:
            for opportunity_id, source_type in (
                ("normal-selection2", "selection2_caigen_claim_feedback"),
                ("history-selection2", "history_selection2"),
                ("selection1", "selection1_developer_claim_feedback"),
            ):
                connection.execute(
                    text(
                        """INSERT INTO new_product_opportunity
                        (id, source_type, main_sku, sub_sku, current_status, snapshot, created_at, updated_at)
                        VALUES (:id, :source_type, :id, :id, 'pending_assignment', '{}', :now, :now)"""
                    ),
                    {"id": opportunity_id, "source_type": source_type, "now": now},
                )

        command.upgrade(config, "a7b8c9d0e123")

        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id, claim_pool_open FROM new_product_opportunity ORDER BY id")
            ).all()
        assert rows == [
            ("history-selection2", 0),
            ("normal-selection2", 1),
            ("selection1", 0),
        ]
    finally:
        engine.dispose()
        get_settings.cache_clear()
