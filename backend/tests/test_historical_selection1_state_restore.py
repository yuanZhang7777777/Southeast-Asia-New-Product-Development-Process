import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_state_restore.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.historical_selection1_state_restore import restore_selection1_states  # noqa: E402


from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_restore_opens_secondary_research_only_for_claimed_plm_arrivals() -> None:
    snapshot = {
        "fields_by_cell": {
            "A": {"header": "主销售员", "value": "历史销售"},
            "B": {"header": "认领单销", "value": 1.5},
        }
    }
    with SessionLocal() as db:
        claimed = models.NewProductOpportunity(
            source_type="history_selection1",
            source_sheet="开发0721期",
            source_row=3,
            batch="开发0721期",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            current_status="historical_archive",
            snapshot=snapshot,
        )
        waiting_arrival = models.NewProductOpportunity(
            source_type="history_selection1",
            source_sheet="开发0721期",
            source_row=5,
            batch="开发0721期",
            country="PH",
            site="PH",
            main_sku="MAIN-3",
            sub_sku="SUB-3",
            current_status="historical_archive",
            snapshot=snapshot,
        )
        rejected = models.NewProductOpportunity(
            source_type="history_selection1",
            source_sheet="开发0721期",
            source_row=4,
            batch="开发0721期",
            country="PH",
            site="PH",
            main_sku="MAIN-2",
            sub_sku="SUB-2",
            current_status="historical_archive",
            snapshot={"fields_by_cell": {"A": {"header": "主销售员", "value": "历史销售"}, "B": {"header": "不认领原因", "value": "侵权"}}},
        )
        db.add_all([claimed, waiting_arrival, rejected])
        db.flush()

        report = restore_selection1_states(
            db,
            {"matches": [{"country": "PH", "sub_sku": "SUB-1", "salesperson_name": "PLM销售", "arrival_date": "2026-07-22", "warehouse": "菲律宾仓"}]},
            apply=True,
        )

        claims = list(db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.opportunity_id))
        assert report["waiting_secondary_research"] == 1
        assert report["waiting_arrival"] == 1
        assert {(claim.claim_result, claim.salesperson_name): claim.downstream_status for claim in claims} == {
            ("claim", "PLM销售"): "waiting_secondary_research",
            ("claim", "历史销售"): "waiting_arrival",
            ("reject", "历史销售"): None,
        }
        assert db.query(models.ArrivalRecord).count() == 1
