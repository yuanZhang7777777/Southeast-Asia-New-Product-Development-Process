import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_environment_sync.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_selection1_environment_sync import (  # noqa: E402
    plan_visibility_cleanup,
    sync_selection1_environment,
)
from app.historical_selection1_import import SOURCE_TYPE  # noqa: E402
from app.workflow_status import OPPORTUNITY_DISABLED  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _snapshot(owner: str = "销售甲", flag: str = "是", daily_sales: object = 1) -> dict:
    return {
        "archive_type": "historical_selection1",
        "business_period": "开发0414期",
        "fields_by_cell": {
            "A": {"header": "站点", "value": "菲律宾"},
            "H": {"header": "主SKU", "value": "MAIN1"},
            "J": {"header": "子SKU", "value": "SUB1"},
            "BZ": {"header": "不认领理由", "value": None},
            "CA": {"header": "主销售员", "value": owner},
            "CB": {"header": "是否认领", "value": flag},
            "CC": {"header": "认领单销", "value": daily_sales},
        },
    }


def _row(sub_sku: str = "SUB1") -> dict:
    return {
        "source_type": SOURCE_TYPE,
        "source_file": "clean.xlsx",
        "source_sheet": "开发0414期",
        "source_row": 2,
        "batch": "开发0414期",
        "country": "PH",
        "site": "菲律宾",
        "main_sku": "MAIN1",
        "sub_sku": sub_sku,
        "main_sku_name": "主品",
        "sub_sku_name": "子品",
        "snapshot": _snapshot(),
    }


def test_visibility_cleanup_keeps_clean_identity_and_disables_dirty_rows() -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                models.NewProductOpportunity(
                    source_type=SOURCE_TYPE,
                    source_file="old.xlsx",
                    source_sheet="开发0414期",
                    source_row=10,
                    batch="开发0414期",
                    country="PH",
                    site="菲律宾",
                    main_sku="MAIN1",
                    sub_sku="SUB1",
                    current_status="historical_archive",
                    snapshot=_snapshot(),
                ),
                models.NewProductOpportunity(
                    source_type=SOURCE_TYPE,
                    source_file="old.xlsx",
                    source_sheet="开发0414期",
                    source_row=11,
                    batch="开发0414期",
                    country="PH",
                    site="菲律宾",
                    main_sku="MAIN1",
                    sub_sku="STALE",
                    current_status="historical_archive",
                    snapshot=_snapshot(),
                ),
                models.NewProductOpportunity(
                    source_type=SOURCE_TYPE,
                    source_file="test.xlsx",
                    source_sheet="8.4期",
                    source_row=1,
                    batch="8.4期",
                    country="PH",
                    site="菲律宾",
                    main_sku="TEST",
                    sub_sku="TEST1",
                    current_status="historical_archive",
                    snapshot={},
                ),
            ]
        )
        db.commit()

        plan = plan_visibility_cleanup(db, [_row()])

        assert plan["kept"] == 1
        assert plan["to_disable"] == 2
        assert plan["disable_by_reason"] == {
            "identity_not_in_clean_source": 1,
            "period_not_in_scope": 1,
        }


def test_sync_imports_archive_and_history_claims_without_flow_tasks() -> None:
    payload = {
        "source_file": "clean.xlsx",
        "source_sha256": "sha",
        "rows": [_row()],
    }
    with SessionLocal() as db:
        report = sync_selection1_environment(
            db,
            payload,
            rows_path=Path("clean.json"),
            apply=True,
            batch_tag="sync-test",
            actor="tester",
            cleanup_source_types=(SOURCE_TYPE,),
        )
        db.commit()

        assert report["import"]["created"] == 1
        assert report["claims"]["created"] == 1
        assert report["cleanup"]["disabled"] == 0
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.FlowInstance).count() == 0
        claim = db.query(models.SalesClaimForecast).one()
        assert claim.salesperson_name == "销售甲"
        assert claim.claim_result == "claim"
        assert db.query(models.NewProductOpportunity).one().current_status != OPPORTUNITY_DISABLED
