import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from app import models  # noqa: E402, F401
from app.db import Base  # noqa: E402


def test_stocking_workflow_columns_are_migration_safe() -> None:
    claim = Base.metadata.tables["sales_claim_forecast"]
    request = Base.metadata.tables["stocking_request"]
    export_row = Base.metadata.tables["export_row"]

    assert {"inventory_available", "needs_stocking", "stocking_decision_updated_at"} <= set(claim.c.keys())
    assert {"claim_record_id", "application_date", "submitted_at", "unit_volume_source"} <= set(request.c.keys())
    assert {
        "stocking_request_id",
        "application_date",
        "stocking_type",
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
            export_row.c.stocking_request_id,
            export_row.c.application_date,
            export_row.c.stocking_type,
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

    assert script.get_heads() == ["c9d1e2f3a456"]
    assert script.get_revision("c9d1e2f3a456").down_revision == "a8d4e6f7b901"