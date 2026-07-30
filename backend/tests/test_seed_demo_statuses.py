import os
import sys
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from scripts import seed_demo_statuses  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def teardown_function() -> None:
    # SQLite keeps PRAGMA foreign_keys on the pooled connection; dispose it so
    # this module cannot change the assumptions of unrelated test modules.
    engine.dispose()


def test_demo_seed_creates_exportable_ready_for_stocking_rows() -> None:
    seed_demo_statuses.main()

    with SessionLocal() as db:
        requests = (
            db.query(models.StockingRequest)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.StockingRequest.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku.in_(["DEMO-READY", "DEMO-MIXED"]))
            .all()
        )
        for request in requests:
            request.status = "submitted"
            db.get(models.SalesClaimForecast, request.claim_record_id).downstream_status = "waiting_export"
        db.flush()
        rows = services.list_available_stocking_items(db)

    assert {(row.main_sku, row.sub_sku, row.salesperson_name, row.quantity) for row in rows} >= {
        ("DEMO-READY", "DEMO-READY-A", "李干", 45),
        ("DEMO-MIXED", "DEMO-MIXED-A", "陈丽妹", 30),
    }


def test_demo_seed_creates_assignment_preview_data() -> None:
    seed_demo_statuses.main()

    with SessionLocal() as db:
        pending_main_skus = {
            row.main_sku
            for row in db.query(models.NewProductOpportunity)
            .filter(
                models.NewProductOpportunity.source_type == seed_demo_statuses.DEMO_SOURCE_TYPE,
                models.NewProductOpportunity.current_status == "pending_assignment",
            )
            .all()
        }

    assert pending_main_skus >= {
        "DEMO-PENDING",
        "DEMO-PENDING-PH-HOME",
        "DEMO-PENDING-PH-AUTO",
        "DEMO-PENDING-VN-OFFICE",
        "DEMO-PENDING-FALLBACK",
    }


def test_demo_seed_reproducibly_covers_stocking_request_branches() -> None:
    seed_demo_statuses.main()
    seed_demo_statuses.main()

    with SessionLocal() as db:
        claims = (
            db.query(models.SalesClaimForecast)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku == "DEMO-SELF-STOCKING")
            .all()
        )
        statuses = {
            db.get(models.NewProductOpportunity, claim.opportunity_id).sub_sku: claim.downstream_status
            for claim in claims
        }
        requests = {
            request.sub_sku: request
            for request in db.query(models.StockingRequest)
            .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.StockingRequest.opportunity_id)
            .filter(models.NewProductOpportunity.main_sku == "DEMO-SELF-STOCKING")
            .all()
        }
        export_rows = services.list_available_stocking_items(db)

    assert statuses == {
        "DEMO-SELF-DRAFT": "waiting_stocking_request",
        "DEMO-SELF-SUBMITTED": "waiting_export",
        "DEMO-SELF-LIST": "waiting_listing",
        "DEMO-SELF-PAUSED": "stocking_paused",
    }
    assert set(requests) == {"DEMO-SELF-DRAFT", "DEMO-SELF-SUBMITTED"}
    assert requests["DEMO-SELF-DRAFT"].status == "draft"
    assert requests["DEMO-SELF-SUBMITTED"].status == "submitted"
    assert {
        (row.main_sku, row.sub_sku, row.quantity, row.amount, row.volume)
        for row in export_rows
    } >= {("DEMO-SELF-STOCKING", "DEMO-SELF-SUBMITTED", 61, 762.5, 0.122)}


def test_demo_seed_cleans_downstream_records_without_removing_shared_rows() -> None:
    seed_demo_statuses.main()

    with SessionLocal() as db:
        demo_opportunity = db.query(models.NewProductOpportunity).filter_by(sub_sku="DEMO-SELF-SUBMITTED").one()
        demo_claim = db.query(models.SalesClaimForecast).filter_by(opportunity_id=demo_opportunity.id).one()
        demo_request = db.query(models.StockingRequest).filter_by(claim_record_id=demo_claim.id).one()
        real_opportunity = models.NewProductOpportunity(
            source_type="real_source",
            source_file="real.xlsx",
            source_sheet="Sheet1",
            source_row=1,
            country="PH",
            site="PH",
            main_sku="REAL-SKU",
            sub_sku="REAL-SKU-A",
            current_status="waiting_arrival",
            snapshot={},
        )
        db.add(real_opportunity)
        db.flush()
        real_claim = models.SalesClaimForecast(
            opportunity_id=real_opportunity.id,
            salesperson_name="真实运营",
            claim_result="claim",
            claim_daily_sales=1,
            source_column="platform",
            downstream_status="waiting_arrival",
        )
        db.add(real_claim)
        db.flush()

        demo_batch = models.ExportBatch(file_name="demo-only.xlsx", scope="stocking_available", row_count=1)
        shared_batch = models.ExportBatch(file_name="shared.xlsx", scope="stocking_available", row_count=2)
        db.add_all([demo_batch, shared_batch])
        db.flush()
        demo_only_export = models.ExportRow(
            export_batch_id=demo_batch.id,
            opportunity_id=demo_opportunity.id,
            claim_record_id=demo_claim.id,
            stocking_request_id=demo_request.id,
            salesperson_name=demo_claim.salesperson_name,
            main_sku=demo_opportunity.main_sku,
            sub_sku=demo_opportunity.sub_sku,
            claim_daily_sales=2.01,
            stocking_quantity=61,
            country="PH",
        )
        shared_demo_export = models.ExportRow(
            export_batch_id=shared_batch.id,
            opportunity_id=demo_opportunity.id,
            claim_record_id=demo_claim.id,
            stocking_request_id=demo_request.id,
            salesperson_name=demo_claim.salesperson_name,
            main_sku=demo_opportunity.main_sku,
            sub_sku=demo_opportunity.sub_sku,
            claim_daily_sales=2.01,
            stocking_quantity=61,
            country="PH",
        )
        shared_real_export = models.ExportRow(
            export_batch_id=shared_batch.id,
            opportunity_id=real_opportunity.id,
            claim_record_id=real_claim.id,
            salesperson_name=real_claim.salesperson_name,
            main_sku=real_opportunity.main_sku,
            sub_sku=real_opportunity.sub_sku,
            claim_daily_sales=1,
            stocking_quantity=30,
            country="PH",
        )
        db.add_all([demo_only_export, shared_demo_export, shared_real_export])

        plm_batch = models.PlmArrivalBatch(
            arrival_date="2026-07-21",
            source_file="plm.xlsx",
            source_hash="seed-cleanup-regression",
            bloc_name="集团八部",
            row_count=2,
        )
        db.add(plm_batch)
        db.flush()
        mixed_plm_item = models.PlmArrivalItem(
            batch_id=plm_batch.id,
            arrival_type="new_arrival",
            sub_sku=demo_opportunity.sub_sku,
            match_status="matched",
            matched_claim_record_id=demo_claim.id,
            raw_payload={"_matched_claim_record_ids": [demo_claim.id, real_claim.id]},
        )
        demo_plm_item = models.PlmArrivalItem(
            batch_id=plm_batch.id,
            arrival_type="new_arrival",
            sub_sku=demo_opportunity.sub_sku,
            match_status="matched",
            matched_claim_record_id=demo_claim.id,
            raw_payload={"_matched_claim_record_ids": [demo_claim.id]},
        )
        db.add_all([mixed_plm_item, demo_plm_item])
        db.flush()
        arrival = models.ArrivalRecord(
            opportunity_id=demo_opportunity.id,
            claim_record_id=demo_claim.id,
            plm_arrival_batch_id=plm_batch.id,
            plm_arrival_item_id=mixed_plm_item.id,
            salesperson_name=demo_claim.salesperson_name,
            country="PH",
        )
        db.add(arrival)

        demo_listing = models.ListingRecord(
            source_group_key="demo-only",
            source_claim_ids=[demo_claim.id],
            source_type="demo",
            country="PH",
            main_sku=demo_opportunity.main_sku,
            salesperson_name=demo_claim.salesperson_name or "demo",
            shop="demo-shop",
            item="DEMO-ITEM",
            listing_strategy="demo",
            first_period_start=date(2026, 7, 16),
            first_period_end=date(2026, 7, 22),
        )
        shared_listing = models.ListingRecord(
            source_group_key="shared",
            source_claim_ids=[demo_claim.id, real_claim.id],
            source_type="shared",
            country="PH",
            main_sku=real_opportunity.main_sku,
            salesperson_name=real_claim.salesperson_name or "real",
            shop="real-shop",
            item="SHARED-ITEM",
            listing_strategy="shared",
            first_period_start=date(2026, 7, 16),
            first_period_end=date(2026, 7, 22),
        )
        db.add_all([demo_listing, shared_listing])
        db.flush()
        demo_period = models.ItemObservationPeriod(
            listing_record_id=demo_listing.id,
            week_number=1,
            period_start=date(2026, 7, 16),
            period_end=date(2026, 7, 22),
        )
        shared_period = models.ItemObservationPeriod(
            listing_record_id=shared_listing.id,
            week_number=1,
            period_start=date(2026, 7, 16),
            period_end=date(2026, 7, 22),
        )
        db.add_all([demo_period, shared_period])

        demo_notification = models.NotificationLog(
            dedupe_key="seed-cleanup-demo",
            opportunity_id=demo_opportunity.id,
            channel="dingtalk",
            message_title="demo",
        )
        real_notification = models.NotificationLog(
            dedupe_key="seed-cleanup-real",
            opportunity_id=real_opportunity.id,
            channel="dingtalk",
            message_title="real",
        )
        demo_audit = models.AuditLog(
            action="demo",
            entity_type="sales_claim_forecast",
            entity_id=demo_claim.id,
            detail={},
        )
        real_audit = models.AuditLog(
            action="real",
            entity_type="sales_claim_forecast",
            entity_id=real_claim.id,
            detail={},
        )
        db.add_all([demo_notification, real_notification, demo_audit, real_audit])
        db.commit()

        saved_ids = {
            "demo_batch": demo_batch.id,
            "shared_batch": shared_batch.id,
            "real_export": shared_real_export.id,
            "plm_batch": plm_batch.id,
            "mixed_plm_item": mixed_plm_item.id,
            "demo_plm_item": demo_plm_item.id,
            "arrival": arrival.id,
            "demo_listing": demo_listing.id,
            "shared_listing": shared_listing.id,
            "demo_period": demo_period.id,
            "shared_period": shared_period.id,
            "demo_notification": demo_notification.id,
            "real_notification": real_notification.id,
            "demo_audit": demo_audit.id,
            "real_audit": real_audit.id,
        }
        demo_entity_ids = {demo_opportunity.id, demo_claim.id, demo_request.id}
        real_opportunity_id = real_opportunity.id
        real_claim_id = real_claim.id

    seed_demo_statuses.main()

    with SessionLocal() as db:
        assert all(db.get(model, item_id) is None for model, item_id in [
            (models.NewProductOpportunity, demo_opportunity.id),
            (models.SalesClaimForecast, demo_claim.id),
            (models.StockingRequest, demo_request.id),
            (models.ExportBatch, saved_ids["demo_batch"]),
            (models.ArrivalRecord, saved_ids["arrival"]),
            (models.ListingRecord, saved_ids["demo_listing"]),
            (models.ItemObservationPeriod, saved_ids["demo_period"]),
            (models.NotificationLog, saved_ids["demo_notification"]),
            (models.AuditLog, saved_ids["demo_audit"]),
        ])
        export_rows = db.query(models.ExportRow).all()
        assert demo_entity_ids.isdisjoint(
            {row.opportunity_id for row in export_rows}
            | {row.claim_record_id for row in export_rows}
            | {row.stocking_request_id for row in export_rows}
        )

        assert all(db.get(model, item_id) is not None for model, item_id in [
            (models.NewProductOpportunity, real_opportunity_id),
            (models.SalesClaimForecast, real_claim_id),
            (models.ExportBatch, saved_ids["shared_batch"]),
            (models.ExportRow, saved_ids["real_export"]),
            (models.PlmArrivalBatch, saved_ids["plm_batch"]),
            (models.ListingRecord, saved_ids["shared_listing"]),
            (models.ItemObservationPeriod, saved_ids["shared_period"]),
            (models.NotificationLog, saved_ids["real_notification"]),
            (models.AuditLog, saved_ids["real_audit"]),
        ])
        assert db.get(models.ExportBatch, saved_ids["shared_batch"]).row_count == 1
        assert db.get(models.ListingRecord, saved_ids["shared_listing"]).source_claim_ids == [real_claim_id]

        mixed_item = db.get(models.PlmArrivalItem, saved_ids["mixed_plm_item"])
        assert mixed_item.matched_claim_record_id == real_claim_id
        assert mixed_item.raw_payload["_matched_claim_record_ids"] == [real_claim_id]
        assert mixed_item.match_status == "matched"
        demo_item = db.get(models.PlmArrivalItem, saved_ids["demo_plm_item"])
        assert demo_item.matched_claim_record_id is None
        assert demo_item.raw_payload["_matched_claim_record_ids"] == []
        assert demo_item.match_status == "unmatched"

        fresh_demo_rows = db.query(models.NewProductOpportunity).filter_by(
            source_type=seed_demo_statuses.DEMO_SOURCE_TYPE
        ).all()
        assert fresh_demo_rows
        assert demo_entity_ids.isdisjoint({row.id for row in fresh_demo_rows})
