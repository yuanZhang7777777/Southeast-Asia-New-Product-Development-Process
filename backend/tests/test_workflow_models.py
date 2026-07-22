import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, schemas  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from app import workflow_status  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_import_and_export_batches_link_source_and_export_rows() -> None:
    with SessionLocal() as db:
        import_batch = models.ImportBatch(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="开发0623期",
            imported_by="练玉君",
            created_count=1,
            updated_count=0,
            skipped_count=0,
            status="completed",
        )
        db.add(import_batch)
        db.flush()

        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="选品1.xlsx",
            source_sheet="开发0623期",
            source_row=3,
            main_sku="MAIN-001",
            sub_sku="SUB-001",
            import_batch_id=import_batch.id,
        )
        db.add(opportunity)
        db.flush()

        claim = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售A",
            claim_result="claim",
            claim_daily_sales=2,
        )
        export_batch = models.ExportBatch(
            exported_by="练玉君",
            file_name="备货申请表.xlsx",
            scope="approved_stocking",
            row_count=1,
            status="completed",
        )
        db.add_all([claim, export_batch])
        db.flush()

        export_row = models.ExportRow(
            export_batch_id=export_batch.id,
            opportunity_id=opportunity.id,
            claim_record_id=claim.id,
            salesperson_name="销售A",
            main_sku="MAIN-001",
            sub_sku="SUB-001",
            claim_daily_sales=2,
            stocking_quantity=60,
            country="TH",
            warehouse="泰国海外仓",
        )
        db.add(export_row)
        db.commit()

        saved_batch = db.get(models.ImportBatch, import_batch.id)
        saved_export = db.get(models.ExportBatch, export_batch.id)
        assert saved_batch is not None
        assert saved_export is not None
        saved_sub_sku = saved_batch.opportunities[0].sub_sku
        saved_quantity = saved_export.rows[0].stocking_quantity

    assert saved_sub_sku == "SUB-001"
    assert saved_quantity == 60


def test_batch_summary_schemas_read_model_metadata() -> None:
    import_batch = models.ImportBatch(
        id="import-batch-1",
        source_type="selection1_developer_claim_feedback",
        source_file="选品1.xlsx",
        source_sheet="开发0623期",
        created_count=2,
        updated_count=1,
        skipped_count=0,
        status="completed",
    )
    export_batch = models.ExportBatch(
        id="export-batch-1",
        exported_by="练玉君",
        file_name="备货申请表.xlsx",
        scope="approved_stocking",
        row_count=3,
        status="completed",
    )

    import_summary = schemas.ImportBatchSummary.model_validate(import_batch)
    export_summary = schemas.ExportBatchMetadata.model_validate(export_batch)

    assert import_summary.created_count == 2
    assert export_summary.row_count == 3


def test_listing_observation_tables_replace_legacy_four_week_summary() -> None:
    assert "listing_record" in Base.metadata.tables
    assert "item_observation_period" in Base.metadata.tables
    assert "four_week_summary" not in Base.metadata.tables

    listing_constraints = {constraint.name for constraint in Base.metadata.tables["listing_record"].constraints}
    period_constraints = {constraint.name for constraint in Base.metadata.tables["item_observation_period"].constraints}
    assert "uq_listing_record_item" in listing_constraints
    assert "uq_item_observation_period_week" in period_constraints
    assert "uq_item_observation_period_start" in period_constraints


def test_alembic_has_single_current_head() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))

    assert ScriptDirectory.from_config(config).get_current_head() == "e1f2a3b4c678"


def test_stocking_claim_statuses_are_explicit() -> None:
    assert workflow_status.CLAIM_WAITING_STOCKING_REQUEST == "waiting_stocking_request"
    assert workflow_status.CLAIM_STOCKING_PAUSED == "stocking_paused"
