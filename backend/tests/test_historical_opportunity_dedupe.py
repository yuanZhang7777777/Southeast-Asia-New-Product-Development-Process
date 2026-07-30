import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_opportunity_dedupe.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_opportunity_dedupe import reconcile_historical_opportunities  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_reconcile_merges_same_source_period_alias_and_keeps_one_pending_claim() -> None:
    with SessionLocal() as db:
        current = models.NewProductOpportunity(
            id="current",
            source_type="history_selection1",
            source_file="latest.xlsx",
            source_sheet="\u5f00\u53d10616\u671f",
            source_row=10,
            batch="\u5f00\u53d1\u65b0\u54c10616\u671f",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            current_status="claim_submitted",
            snapshot={"current": True},
        )
        history = models.NewProductOpportunity(
            id="history",
            source_type="history_selection1",
            source_file="old.xlsx",
            source_sheet="\u5f00\u53d10616\u671f",
            source_row=10,
            batch="\u5f00\u53d10616\u671f",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            current_status="claim_submitted",
            snapshot={"history": True},
        )
        db.add_all([current, history])
        db.flush()
        direct_claim = models.SalesClaimForecast(
            id="direct-claim",
            opportunity_id=current.id,
            salesperson_name="Sales A",
            claim_result="claim",
            claim_daily_sales=0.5,
            claim_source="selection1_claim_feedback",
        )
        restored_claim = models.SalesClaimForecast(
            id="restored-claim",
            opportunity_id=history.id,
            salesperson_name="Sales A",
            claim_result="claim",
            claim_daily_sales=0.5,
            claim_source="historical_selection1_state_restore",
            downstream_status="waiting_secondary_research",
            arrival_detected_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        )
        db.add_all([direct_claim, restored_claim])
        db.flush()
        db.add(models.ArrivalRecord(
            id="arrival",
            opportunity_id=history.id,
            claim_record_id=restored_claim.id,
            salesperson_name="Sales A",
            arrived_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ))
        db.add_all([
            models.SourceRecordSnapshot(id="snapshot-current", opportunity_id=current.id, payload={"source": "current"}),
            models.SourceRecordSnapshot(id="snapshot-history", opportunity_id=history.id, payload={"source": "history"}),
        ])
        db.commit()

        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert report["duplicate_groups"] == 1
        assert report["merged_opportunities"] == 1
        opportunities = db.query(models.NewProductOpportunity).order_by(models.NewProductOpportunity.id).all()
        assert [item.id for item in opportunities] == [current.id, history.id]
        assert db.get(models.NewProductOpportunity, current.id).batch == "\u5f00\u53d10616\u671f"
        assert db.get(models.NewProductOpportunity, history.id).current_status == "replaced_by_normalized_selection1"
        claims = db.query(models.SalesClaimForecast).all()
        assert [item.id for item in claims] == [direct_claim.id]
        assert claims[0].downstream_status == "waiting_secondary_research"
        assert claims[0].arrival_detected_at is not None
        arrival = db.query(models.ArrivalRecord).one()
        assert arrival.opportunity_id == current.id
        assert arrival.claim_record_id == direct_claim.id
        assert db.query(models.SourceRecordSnapshot).filter_by(opportunity_id=current.id).count() == 2


def test_reconcile_merges_selection1_history_with_current_but_keeps_selection2_separate() -> None:
    with SessionLocal() as db:
        for source_type in (
            "history_selection1",
            "selection1_developer_claim_feedback",
            "selection2_caigen_claim_feedback",
        ):
            db.add(models.NewProductOpportunity(
                source_type=source_type,
                source_sheet="\u5f00\u53d10616\u671f",
                batch="\u5f00\u53d10616\u671f",
                country="PH",
                site="PH",
                main_sku="MAIN-1",
                sub_sku="SUB-1",
            ))
        db.commit()

        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert report["duplicate_groups"] == 1
        assert db.query(models.NewProductOpportunity).count() == 2
        assert sorted(item.source_type for item in db.query(models.NewProductOpportunity).all()) == [
            "selection1_developer_claim_feedback",
            "selection2_caigen_claim_feedback",
        ]


def test_reconcile_hides_referenced_selection1_duplicate_after_moving_refs() -> None:
    with SessionLocal() as db:
        current = models.NewProductOpportunity(
            id="current",
            source_type="selection1_developer_claim_feedback",
            source_file="selection1-clean.xlsx",
            source_sheet="开发0623期",
            source_row=82,
            batch="开发0623期",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            current_status="claim_submitted",
            snapshot={"clean": True},
        )
        dirty = models.NewProductOpportunity(
            id="dirty",
            source_type="history_selection1",
            source_file="old.xlsx",
            source_sheet="开发新品0623期",
            source_row=82,
            batch="开发新品0623期",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            image_url="/uploaded-sources/product-images/old.png",
            current_status="historical_archive",
            snapshot={"old": True},
        )
        db.add_all([current, dirty])
        db.flush()
        flow = models.FlowInstance(opportunity_id=dirty.id, current_node="sales_claim")
        db.add(flow)
        db.flush()
        db.add(models.FlowTask(flow_instance_id=flow.id, node_code="sales_claim", task_type="sales_claim"))
        db.commit()

        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert report["duplicate_groups"] == 1
        assert report["hidden_replaced_opportunities"] == 1
        assert report["deleted_opportunities"] == 0
        assert db.get(models.FlowInstance, flow.id).opportunity_id == current.id
        assert db.get(models.NewProductOpportunity, current.id).image_url == "/uploaded-sources/product-images/old.png"
        hidden = db.get(models.NewProductOpportunity, dirty.id)
        assert hidden.current_status == "replaced_by_normalized_selection1"
        assert hidden.snapshot["replaced_by_opportunity_id"] == current.id


def test_reconcile_normalizes_periods_by_source_without_cross_source_merge() -> None:
    with SessionLocal() as db:
        selection1 = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_sheet="\u5f00\u53d10616\u671f",
            batch="\u5f00\u53d1\u65b0\u54c10616\u671f",
            country="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        selection1_caigen = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_sheet="\u5f00\u53d1-\u8d22\u6839\u56e2\u961f\u6c47\u603b",
            batch="\u5f00\u53d10727\u671f-\u8d22\u6839",
            country="PH",
            main_sku="MAIN-2",
            sub_sku="SUB-2",
        )
        selection1_caigen_alias = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_sheet="\u5f00\u53d1-\u8d22\u6839\u56e2\u961f\u6c47\u603b",
            batch="\u5f00\u53d1-\u8d22\u6839\u56e2\u961f\u6c47\u603b-20260727",
            country="PH",
            main_sku="MAIN-4",
            sub_sku="SUB-4",
        )
        selection2 = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_sheet="5.26\u671f",
            batch="5.26\u671f",
            country="PH",
            main_sku="MAIN-3",
            sub_sku="SUB-3",
        )
        db.add_all([selection1, selection1_caigen, selection1_caigen_alias, selection2])
        db.commit()

        reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert selection1.batch == "\u5f00\u53d10616\u671f"
        assert selection1_caigen.batch == "\u5f00\u53d10727\u671f-\u8d22\u6839"
        assert selection1_caigen_alias.batch == "\u5f00\u53d10727\u671f-\u8d22\u6839"
        assert selection2.batch == "5.26\u671f"

def test_reconcile_normalizes_readonly_selection2_source_with_its_own_namespace() -> None:
    with SessionLocal() as db:
        selection1 = models.NewProductOpportunity(
            source_type="history_selection1",
            source_sheet="\u5f00\u53d10616\u671f",
            batch="\u5f00\u53d10616\u671f",
            country="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        selection2 = models.NewProductOpportunity(
            source_type="history_selection2",
            source_sheet="5.26\u671f",
            batch="5.26\u671f",
            country="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        db.add_all([selection1, selection2])
        db.commit()

        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert report["duplicate_groups"] == 0
        assert selection1.batch == "\u5f00\u53d10616\u671f"
        assert selection2.batch == "5.26\u671f"



def test_reconcile_uses_source_sheet_to_dedupe_missing_location_rows() -> None:
    with SessionLocal() as db:
        same_sheet = [
            models.NewProductOpportunity(
                source_type="history_selection1",
                source_sheet="\u5f00\u53d10616\u671f-PH",
                batch="\u5f00\u53d10616\u671f",
                main_sku="MAIN-1",
                sub_sku="SUB-1",
            ),
            models.NewProductOpportunity(
                source_type="history_selection1",
                source_sheet="\u5f00\u53d10616\u671f-PH",
                batch="\u5f00\u53d10616\u671f",
                main_sku="MAIN-1",
                sub_sku="SUB-1",
            ),
        ]
        other_sheet = models.NewProductOpportunity(
            source_type="history_selection1",
            source_sheet="\u5f00\u53d10616\u671f-TH",
            batch="\u5f00\u53d10616\u671f",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        db.add_all([*same_sheet, other_sheet])
        db.commit()

        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()

        assert report["duplicate_groups"] == 1
        assert db.query(models.NewProductOpportunity).count() == 2


def test_reconcile_does_not_merge_different_business_periods() -> None:
    with SessionLocal() as db:
        db.add_all([
            models.NewProductOpportunity(source_type="history_selection1", batch="\u5f00\u53d10616\u671f", country="PH", main_sku="MAIN-1", sub_sku="SUB-1"),
            models.NewProductOpportunity(source_type="history_selection1", batch="\u5f00\u53d10623\u671f", country="PH", main_sku="MAIN-1", sub_sku="SUB-1"),
        ])
        db.commit()
        report = reconcile_historical_opportunities(db, apply=True)
        db.commit()
        assert report["duplicate_groups"] == 0
        assert db.query(models.NewProductOpportunity).count() == 2