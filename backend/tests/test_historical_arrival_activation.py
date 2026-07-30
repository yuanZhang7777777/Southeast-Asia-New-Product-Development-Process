import os
import sys
import json
from datetime import datetime
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_arrival_activation.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402
from app.db import Base  # noqa: E402
from app.historical_arrival_activation import activate_historical_arrival  # noqa: E402


engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_activation_uses_each_mapped_historical_claimant_not_the_plm_salesperson() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        _add_enabled_operator(db, "历史销售乙")
        first_claim, second_claim = _add_historical_evidence(db)
        batch, item = _add_plm_batch_item(db)
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

        active_claims = db.query(models.SalesClaimForecast).filter_by(source_column="platform").all()
        assert result["status"] == "activated"
        assert result["historical_claim_ids"] == [first_claim.id, second_claim.id]
        assert {claim.salesperson_name for claim in active_claims} == {"历史销售甲", "历史销售乙"}
        assert {claim.claim_source for claim in active_claims} == {"historical_arrival_activation"}
        assert {
            json.loads(claim.note or "{}") ["plm_arrival_salesperson"]
            for claim in active_claims
        } == {"PLM销售"}
        assert db.query(models.ArrivalRecord).count() == 2
        assert db.get(models.NewProductOpportunity, first_claim.opportunity_id).current_status == "claim_submitted"
        assert db.get(models.NewProductOpportunity, second_claim.opportunity_id).current_status == "claim_submitted"

        repeated = activate_historical_arrival(db, item, apply=True)
        db.commit()
        assert repeated["status"] == "already_activated"
        assert db.query(models.SalesClaimForecast).filter_by(source_column="platform").count() == 2
        assert db.query(models.ArrivalRecord).count() == 2


def test_activation_does_not_repeat_an_existing_arrival_record() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        _add_historical_evidence(db)
        _, first_item = _add_plm_batch_item(db)
        db.commit()

        first = activate_historical_arrival(db, first_item, apply=True)
        db.commit()

        second_batch = models.PlmArrivalBatch(
            arrival_date="2026-07-22",
            source_file="plm-reexport.xlsx",
            source_hash="test-source-hash-reexport",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(second_batch)
        db.flush()
        second_item = models.PlmArrivalItem(
            batch_id=second_batch.id,
            source_sheet="到货",
            source_row=2,
            arrival_type="new_arrival",
            salesperson_name="PLM销售",
            country="PH",
            warehouse="PH仓",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
        )
        db.add(second_item)
        db.flush()

        repeated = activate_historical_arrival(db, second_item, apply=True)
        db.commit()

        assert first["status"] == "activated"
        assert repeated["status"] == "already_activated"
        assert db.query(models.SalesClaimForecast).filter_by(source_column="platform").count() == 1
        assert db.query(models.ArrivalRecord).count() == 1

def test_activation_requires_an_enabled_operator_mapping() -> None:
    with SessionLocal() as db:
        _add_historical_evidence(db)
        _, item = _add_plm_batch_item(db)
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

        assert result["status"] == "owner_unmapped"
        assert db.query(models.SalesClaimForecast).filter_by(source_column="platform").count() == 0
        assert db.query(models.ArrivalRecord).count() == 0


def test_activation_allows_a_different_bound_child_sku() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        _add_historical_evidence(db)
        _, item = _add_plm_batch_item(db)
        item.salesperson_name = "PLM_OPERATOR"
        listing = models.ListingRecord(
            source_group_key="history:MAIN-1",
            source_claim_ids=[],
            source_type="history_listing",
            business_period="history",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            salesperson_name="PLM_OPERATOR",
            shop="Shopee-PH",
            item="ITEM-OTHER",
            listing_strategy="history",
            status="active",
            tracking_status="active",
        )
        db.add(listing)
        db.flush()
        db.add(
            models.ListingSkuBinding(
                listing_record_id=listing.id,
                main_sku="MAIN-1",
                sub_sku="SUB-OTHER",
                binding_source="history_listing",
            )
        )
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

        assert result["status"] == "activated"
        assert db.query(models.ArrivalRecord).count() == 1

def test_activation_skips_exact_child_sku_with_an_active_item() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        _add_historical_evidence(db)
        _, item = _add_plm_batch_item(db)
        listing = models.ListingRecord(
            source_group_key="history:MAIN-1",
            source_claim_ids=[],
            source_type="history_listing",
            business_period="历史",
            country="PH",
            site="PH",
            main_sku="MAIN-1",
            salesperson_name="PLM销售",
            shop="Shopee-PH",
            item="ITEM-1",
            listing_strategy="历史",
            status="active",
            tracking_status="active",
        )
        db.add(listing)
        db.flush()
        db.add(
            models.ListingSkuBinding(
                listing_record_id=listing.id,
                main_sku="MAIN-1",
                sub_sku="SUB-1",
                binding_source="history_listing",
            )
        )
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

        assert result["status"] == "already_listed"
        assert db.query(models.SalesClaimForecast).filter_by(source_column="platform").count() == 0
        assert db.query(models.ArrivalRecord).count() == 0


def test_activation_does_not_cross_country_match_the_same_sub_sku() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        opportunity = _historical_opportunity(db, "history_selection1", "开发0623期", 1, "MAIN-1")
        opportunity.country = opportunity.site = "TH"
        db.add(opportunity)
        db.flush()
        db.add(
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="历史销售甲",
                claim_result="claim",
                claim_daily_sales=1,
                source_column="history_selection1",
            )
        )
        _, item = _add_plm_batch_item(db)
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

    assert result["status"] == "no_historical_claim"
    with SessionLocal() as db:
        assert db.query(models.ArrivalRecord).count() == 0


def test_activation_requires_a_unique_main_sku_when_plm_main_sku_does_not_match() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        first = _historical_opportunity(db, "history_selection1", "开发0623期", 1, "MAIN-A")
        second = _historical_opportunity(db, "history_selection1", "开发0623期", 2, "MAIN-B")
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                models.SalesClaimForecast(
                    opportunity_id=first.id,
                    salesperson_name="历史销售甲",
                    claim_result="claim",
                    claim_daily_sales=1,
                    source_column="history_selection1",
                ),
                models.SalesClaimForecast(
                    opportunity_id=second.id,
                    salesperson_name="历史销售甲",
                    claim_result="claim",
                    claim_daily_sales=1,
                    source_column="history_selection1",
                ),
            ]
        )
        _, item = _add_plm_batch_item(db)
        item.main_sku = "MAIN-C"
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

    assert result["status"] == "main_sku_ambiguous"
    with SessionLocal() as db:
        assert db.query(models.ArrivalRecord).count() == 0


def test_activation_skips_history_that_already_has_secondary_research() -> None:
    with SessionLocal() as db:
        _add_enabled_operator(db, "历史销售甲")
        first_claim, _ = _add_historical_evidence(db)
        first_claim.secondary_research_submitted_at = datetime(2026, 7, 20, 9, 0, 0)
        _, item = _add_plm_batch_item(db)
        db.commit()

        result = activate_historical_arrival(db, item, apply=True)
        db.commit()

    assert result["status"] == "historical_secondary_research"
    with SessionLocal() as db:
        assert db.query(models.ArrivalRecord).count() == 0


def _add_enabled_operator(db, name: str) -> None:
    user = models.User(name=name, dingtalk_user_id=f"dt-{name}", enabled=True)
    db.add(user)
    db.flush()
    db.add(
        models.RoleMapping(
            user_id=user.id,
            name=name,
            dingtalk_user_id=user.dingtalk_user_id,
            role="operator",
            enabled=True,
        )
    )


def _add_historical_evidence(db) -> tuple[models.SalesClaimForecast, models.SalesClaimForecast]:
    first = _historical_opportunity(db, "history_selection1", "开发0623期", 1, "MAIN-1")
    second = _historical_opportunity(db, "history_selection1", "开发0623期", 2, "MAIN-1")
    db.add_all([first, second])
    db.flush()
    first_claim = models.SalesClaimForecast(
        opportunity_id=first.id,
        salesperson_name="历史销售甲",
        claim_result="claim",
        claim_daily_sales=1.0,
        source_column="history_selection1",
        claim_source="history_selection1",
    )
    second_claim = models.SalesClaimForecast(
        opportunity_id=second.id,
        salesperson_name="历史销售乙",
        claim_result="claim",
        claim_daily_sales=2.0,
        source_column="history_selection1",
        claim_source="history_selection1",
    )
    db.add_all([first_claim, second_claim])
    db.flush()
    return first_claim, second_claim


def _historical_opportunity(db, source_type: str, batch: str, source_row: int, main_sku: str) -> models.NewProductOpportunity:
    return models.NewProductOpportunity(
        source_type=source_type,
        source_file=f"{source_type}.xlsx",
        source_sheet=batch,
        source_row=source_row,
        batch=batch,
        country="PH",
        site="PH",
        main_sku=main_sku,
        sub_sku="SUB-1",
        current_status="historical_archive",
        snapshot={},
    )


def _add_plm_batch_item(db) -> tuple[models.PlmArrivalBatch, models.PlmArrivalItem]:
    batch = models.PlmArrivalBatch(
        arrival_date="2026-07-22",
        source_file="plm.xlsx",
        source_hash="test-source-hash",
        bloc_name="集团八部",
        row_count=1,
    )
    db.add(batch)
    db.flush()
    item = models.PlmArrivalItem(
        batch_id=batch.id,
        source_sheet="到货",
        source_row=2,
        arrival_type="new_arrival",
        salesperson_name="PLM销售",
        country="PH",
        warehouse="PH仓",
        main_sku="MAIN-1",
        sub_sku="SUB-1",
    )
    db.add(item)
    db.flush()
    return batch, item
