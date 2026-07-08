import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_caigen_opportunity_pool_allows_multiple_self_claims_for_one_child_sku() -> None:
    with SessionLocal() as db:
        opportunity = add_caigen_opportunity(db)
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="赵钰婷",
                claim_result="claim",
                claim_daily_sales=1.5,
                claim_source="caigen_self_claim",
            ),
        )
        services.submit_claim(
            db,
            schemas.ClaimCreate(
                opportunity_id=opportunity.id,
                salesperson_name="李干",
                claim_result="claim",
                claim_daily_sales=1,
                claim_source="caigen_self_claim",
            ),
        )
        db.commit()

        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.salesperson_name).all()

    assert [(claim.salesperson_name, claim.claim_daily_sales, claim.claim_source, claim.task_id) for claim in claims] == [
        ("李干", 1, "caigen_self_claim", None),
        ("赵钰婷", 1.5, "caigen_self_claim", None),
    ]


def test_caigen_self_claim_rejects_non_caigen_opportunity() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="W27",
            source_row=1,
            batch="W27",
            main_sku="MAIN-A",
            sub_sku="SUB-A",
        )
        db.add(opportunity)
        db.commit()

        with pytest.raises(PermissionError, match="caigen"):
            services.submit_claim(
                db,
                schemas.ClaimCreate(
                    opportunity_id=opportunity.id,
                    salesperson_name="Operator A",
                    claim_result="claim",
                    claim_daily_sales=1,
                    claim_source="caigen_self_claim",
                ),
            )


def add_caigen_opportunity(db) -> models.NewProductOpportunity:
    opportunity = models.NewProductOpportunity(
        source_type="selection2_caigen_claim_feedback",
        source_file="选品2.xlsx",
        source_sheet="5.26期",
        source_row=1,
        batch="BATCH-CAIGEN",
        country="PH",
        site="PH",
        category_level1="汽摩配",
        main_sku="HXG15GD",
        sub_sku="HXG15GD",
    )
    db.add(opportunity)
    db.flush()
    return opportunity
