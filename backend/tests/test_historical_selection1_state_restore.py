import os
import sys
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_state_restore.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_selection1_state_restore import restore_selection1_states  # noqa: E402
from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_restore_requires_an_explicit_new_arrival_window() -> None:
    snapshot = {
        "fields_by_cell": {
            "A": {"header": "主销售员", "value": "历史销售"},
            "B": {"header": "认领单销", "value": 1.5},
        }
    }
    history = {
        "matches": [
            {
                "country": "PH",
                "sub_sku": "SUB-1",
                "salesperson_name": "PLM销售",
                "arrival_date": "2026-07-22",
                "arrival_type": "new_arrival",
                "warehouse": "菲律宾仓",
            }
        ]
    }
    with SessionLocal() as db:
        db.add(models.NewProductOpportunity(
            source_type="history_selection1", source_sheet="开发0721期", source_row=3,
            batch="开发0721期", country="PH", site="PH", main_sku="MAIN-1",
            sub_sku="SUB-1", current_status="historical_archive", snapshot=snapshot,
        ))
        db.flush()

        blocked = restore_selection1_states(db, history, apply=True)
        assert blocked["activation_window_required"] == 1
        assert db.query(models.SalesClaimForecast).count() == 0
        assert db.query(models.ArrivalRecord).count() == 0

        report = restore_selection1_states(
            db, history, apply=True,
            arrival_from=date(2026, 7, 20), arrival_to=date(2026, 7, 26),
        )
        claim = db.query(models.SalesClaimForecast).one()
        assert report["waiting_secondary_research"] == 1
        assert claim.salesperson_name == "PLM销售"
        assert claim.downstream_status == "waiting_secondary_research"
        assert db.query(models.ArrivalRecord).count() == 1


def test_restore_skips_restock_and_arrivals_outside_the_window() -> None:
    snapshot = {"fields_by_cell": {"A": {"header": "主销售员", "value": "历史销售"}, "B": {"header": "认领单销", "value": 1.5}}}
    with SessionLocal() as db:
        for sub_sku in ("RESTOCK", "OUTSIDE"):
            db.add(models.NewProductOpportunity(
                source_type="history_selection1", source_sheet="开发0721期", source_row=3,
                batch="开发0721期", country="PH", site="PH", main_sku=sub_sku,
                sub_sku=sub_sku, current_status="historical_archive", snapshot=snapshot,
            ))
        db.flush()
        report = restore_selection1_states(
            db,
            {"matches": [
                {"country": "PH", "sub_sku": "RESTOCK", "arrival_date": "2026-07-22", "arrival_type": "restock"},
                {"country": "PH", "sub_sku": "OUTSIDE", "arrival_date": "2026-07-19", "arrival_type": "new_arrival"},
            ]},
            apply=True,
            arrival_from=date(2026, 7, 20), arrival_to=date(2026, 7, 26),
        )
        assert report["not_new_arrival"] == 1
        assert report["outside_arrival_window"] == 1
        assert db.query(models.SalesClaimForecast).count() == 0

def test_restore_uses_existing_current_selection_claim() -> None:
    history = {
        "matches": [
            {
                "country": "PH", "sub_sku": "SUB-CURRENT", "salesperson_name": "PLM销售",
                "arrival_date": "2026-07-24", "arrival_type": "new_arrival", "warehouse": "菲律宾仓",
            }
        ]
    }
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback", source_sheet="开发0721期", source_row=3,
            batch="开发新品0721期", country="PH", site="PH", main_sku="MAIN-CURRENT",
            sub_sku="SUB-CURRENT", current_status="claim_submitted", snapshot={},
        )
        db.add(opportunity)
        db.flush()
        db.add(models.SalesClaimForecast(
            opportunity_id=opportunity.id, salesperson_name="历史认领", claim_result="claim",
            claim_daily_sales=1.5, source_column="selection1_tail", claim_source="selection1_tail",
        ))
        db.flush()
        report = restore_selection1_states(
            db, history, apply=True,
            arrival_from=date(2026, 7, 20), arrival_to=date(2026, 7, 26),
        )
        active_claim = db.query(models.SalesClaimForecast).filter_by(source_column="platform").one()
        assert report["waiting_secondary_research"] == 1
        assert active_claim.salesperson_name == "PLM销售"
        assert active_claim.claim_daily_sales == 1.5
        assert db.query(models.ArrivalRecord).filter_by(claim_record_id=active_claim.id).count() == 1
