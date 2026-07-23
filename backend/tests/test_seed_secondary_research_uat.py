import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_seed_secondary_research_uat.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from scripts.seed_secondary_research_uat import (  # noqa: E402
    UAT_LISTING_SOURCE_TYPE,
    UAT_SOURCE_FILE,
    UAT_SOURCE_TYPE,
    ensure_development_environment,
    seed_secondary_research_uat,
)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_seed_cli_rejects_non_development_environment() -> None:
    ensure_development_environment(SimpleNamespace(app_env="development"))
    with pytest.raises(RuntimeError, match="development"):
        ensure_development_environment(SimpleNamespace(app_env="production"))


def test_seed_secondary_research_uat_is_rich_and_idempotent() -> None:
    with SessionLocal() as db:
        first = seed_secondary_research_uat(db)
        db.commit()
        second = seed_secondary_research_uat(db)
        db.commit()

        opportunity_count = db.scalar(
            select(func.count()).select_from(models.NewProductOpportunity).where(
                models.NewProductOpportunity.source_file == UAT_SOURCE_FILE
            )
        )
        claims = db.scalars(
            select(models.SalesClaimForecast)
            .join(models.NewProductOpportunity)
            .where(models.NewProductOpportunity.source_file == UAT_SOURCE_FILE)
        ).all()
        listings = db.scalars(
            select(models.ListingRecord).where(models.ListingRecord.source_type == UAT_LISTING_SOURCE_TYPE)
        ).all()
        periods = db.scalars(
            select(models.ItemObservationPeriod)
            .join(models.ListingRecord)
            .where(models.ListingRecord.source_type == UAT_LISTING_SOURCE_TYPE)
        ).all()
        groups = db.execute(
            select(
                models.NewProductOpportunity.country,
                models.NewProductOpportunity.batch,
                models.NewProductOpportunity.main_sku,
            )
            .where(models.NewProductOpportunity.source_file == UAT_SOURCE_FILE)
            .distinct()
        ).all()
        listing_period_counts = sorted(len(listing.periods) for listing in listings)
        completed_listing_count = sum(listing.initial_observation_completed_at is not None for listing in listings)

    expected = {"opportunities": 54, "claims": 54, "listings": 6, "periods": 18}
    assert first == expected
    assert second == expected
    assert opportunity_count == 54
    assert len(claims) == 54
    assert len(listings) == 6
    assert all(UAT_SOURCE_FILE in listing.source_group_key for listing in listings)
    assert len(periods) == 18
    assert len(groups) == 18
    assert {country for country, _, _ in groups} == {"TH", "VN", "PH"}
    assert {period for _, period, _ in groups} == {"UAT-SR-20260710", "UAT-SR-20260717"}
    assert sum(claim.downstream_status == "waiting_secondary_research" for claim in claims) == 18
    assert sum(claim.secondary_research_submitted_at is not None for claim in claims) == 36
    assert sum(claim.downstream_status == "listing_observation" for claim in claims) == 18
    assert listing_period_counts == [2, 2, 2, 4, 4, 4]
    assert completed_listing_count == 3