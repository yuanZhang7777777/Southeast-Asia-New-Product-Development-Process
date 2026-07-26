import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_listing_observations.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, schemas, services  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["AUTH_SECRET_KEY"] = "test-auth-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    os.environ["AUTH_REQUIRED"] = "false"
    os.environ.pop("AUTH_SECRET_KEY", None)
    get_settings.cache_clear()


def test_business_period_is_thursday_through_wednesday() -> None:
    assert services.current_business_period_start(date(2026, 7, 16)) == date(2026, 7, 16)
    assert services.current_business_period_start(date(2026, 7, 22)) == date(2026, 7, 16)


def test_first_period_only_accepts_current_or_next_business_period() -> None:
    today = date(2026, 7, 20)

    services.validate_selectable_period_start(date(2026, 7, 16), today)
    services.validate_selectable_period_start(date(2026, 7, 23), today)
    with pytest.raises(ValueError, match="current or next"):
        services.validate_selectable_period_start(date(2026, 7, 9), today)
    with pytest.raises(ValueError, match="Thursday"):
        services.validate_selectable_period_start(date(2026, 7, 17), today)


def test_initial_observation_periods_are_four_independent_weeks() -> None:
    assert services.initial_observation_period_dates(date(2026, 7, 23)) == [
        (date(2026, 7, 23), date(2026, 7, 29)),
        (date(2026, 7, 30), date(2026, 8, 5)),
        (date(2026, 8, 6), date(2026, 8, 12)),
        (date(2026, 8, 13), date(2026, 8, 19)),
    ]


def test_listing_creation_overrides_manual_first_period_to_next_complete_cycle() -> None:
    create_waiting_listing_group("销售A", "MAIN-A")
    with SessionLocal() as db:
        task = next(task for task in services.list_pending_listing_tasks(db) if task["main_sku"] == "MAIN-A")
        records = services.create_listing_batch(
            db,
            task["task_key"],
            [schemas.ListingBatchRow(
                shop="Shopee-PH-A",
                item="10001",
                listing_strategy="低价切入",
                first_period_start="2026-07-23",
            )],
            actor_name="销售A",
            actor_user_id="user-a",
            actor_is_manager=False,
            operator_name="销售A",
            today=date(2026, 7, 24),
        )
        db.flush()
        period_starts = [period.period_start for period in records[0].periods]

    assert records[0].first_period_start == date(2026, 7, 30)
    assert period_starts[:2] == [date(2026, 7, 30), date(2026, 8, 6)]


def test_batch_creation_adds_multiple_items_and_four_periods_each() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    task = client.get("/listing-workbench", headers=headers).json()["pending_listing_tasks"][0]
    current = services.current_business_period_start(date.today())

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task["task_key"],
            "rows": [
                {
                    "shop": "Shopee-PH-A",
                    "item": "10001",
                    "listing_strategy": "低价切入",
                    "first_period_start": current.isoformat(),
                },
                {
                    "shop": "Shopee-PH-B",
                    "item": "10002",
                    "listing_strategy": "主图测试",
                    "first_period_start": (current + timedelta(days=7)).isoformat(),
                },
            ],
        },
    )

    assert response.status_code == 200
    assert [item["item"] for item in response.json()] == ["10001", "10002"]
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 2
        assert db.query(models.ItemObservationPeriod).count() == 8
        assert {claim.downstream_status for claim in db.query(models.SalesClaimForecast).all()} == {
            "listing_observation"
        }
        assert {log.actor_name for log in db.query(models.AuditLog).filter_by(action="listing.created")} == {
            "销售A"
        }

    workbench = client.get("/listing-workbench", headers=headers).json()
    assert [task["task_key"] for task in workbench["pending_listing_tasks"]] == [task["task_key"]]
    assert len(workbench["listing_records"]) == 2
    assert len(workbench["period_rows"]) == 8


def test_manual_listing_batch_creates_new_main_sku_without_claim_source() -> None:
    headers = login("销售A", "operator", "dt-a")
    current = services.current_business_period_start(date.today()).isoformat()

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": "manual:MAIN-MANUAL:PH:销售A",
            "manual_context": {
                "main_sku": "MAIN-MANUAL",
                "main_sku_name": "手工新增商品",
                "country": "PH",
                "site": "PH",
                "salesperson_name": "销售A",
            },
            "rows": [
                {
                    "shop": "Manual Shop",
                    "item": "MANUAL-ITEM-1",
                    "listing_strategy": "运营手工新增",
                    "first_period_start": current,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["main_sku"] == "MAIN-MANUAL"
    assert body[0]["source_business_periods"] == []
    with SessionLocal() as db:
        listing = db.query(models.ListingRecord).filter_by(item="MANUAL-ITEM-1").one()
        assert listing.source_type == "manual_listing"
        assert listing.source_claim_ids == []
        assert listing.country == "PH"
        assert listing.site == "PH"
        assert listing.salesperson_name == "销售A"
        assert db.query(models.ItemObservationPeriod).filter_by(listing_record_id=listing.id).count() == 4
        assert db.query(models.AuditLog).filter_by(action="listing.created", entity_id=listing.id).count() == 1

    workbench = client.get("/listing-workbench", headers=headers).json()
    assert any(item["main_sku"] == "MAIN-MANUAL" for item in workbench["listing_records"])
def test_listing_batch_rechecks_locked_claim_status_before_creation(monkeypatch) -> None:
    claim_ids = create_waiting_listing_group("销售A", "MAIN-RACE")
    with SessionLocal() as db:
        stale_task = next(task for task in services.list_pending_listing_tasks(db) if task["main_sku"] == "MAIN-RACE")
        for claim_id in claim_ids:
            db.get(models.SalesClaimForecast, claim_id).downstream_status = "disabled"
        db.commit()

        monkeypatch.setattr(services, "list_pending_listing_tasks", lambda _db, today=None: [stale_task])
        with pytest.raises(ValueError, match="no longer pending"):
            services.create_listing_batch(
                db,
                stale_task["task_key"],
                [schemas.ListingBatchRow(
                    shop="Shop Race",
                    item="ITEM-RACE",
                    listing_strategy="并发保护验证",
                    first_period_start="2026-07-16",
                )],
                actor_name="销售A",
                actor_user_id="user-a",
                actor_is_manager=False,
                operator_name="销售A",
                today=date(2026, 7, 20),
            )

        assert db.query(models.ListingRecord).count() == 0


def test_batch_validation_is_atomic_and_returns_row_errors() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    task_key = client.get("/listing-workbench", headers=headers).json()["pending_listing_tasks"][0]["task_key"]
    current = services.current_business_period_start(date.today()).isoformat()

    missing = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task_key,
            "rows": [
                {"shop": "", "item": "10001", "listing_strategy": "", "first_period_start": current},
                {"shop": "Shop B", "item": "", "listing_strategy": "策略", "first_period_start": current},
            ],
        },
    )

    assert missing.status_code == 400
    assert missing.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "shop", "message": "shop is required"},
        {"row_index": 0, "field": "listing_strategy", "message": "listing_strategy is required"},
        {"row_index": 1, "field": "item", "message": "item is required"},
    ]
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 0

    duplicate = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task_key,
            "rows": [
                {"shop": "Shop A", "item": " 10001 ", "listing_strategy": "策略A", "first_period_start": current},
                {"shop": "Shop B", "item": "10001", "listing_strategy": "策略B", "first_period_start": current},
            ],
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "item", "message": "item is duplicated in this batch"},
        {"row_index": 1, "field": "item", "message": "item is duplicated in this batch"},
    ]
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 0


def test_existing_item_conflict_and_unauthorized_task_create_nothing() -> None:
    owner_headers = login("销售A", "operator", "dt-a")
    other_headers = login("销售B", "operator", "dt-b")
    create_waiting_listing_group("销售A", "MAIN-A")
    task_key = client.get("/listing-workbench", headers=owner_headers).json()["pending_listing_tasks"][0]["task_key"]
    current = services.current_business_period_start(date.today()).isoformat()
    row = {"shop": "Shop A", "item": "10001", "listing_strategy": "策略A", "first_period_start": current}

    denied = client.post(
        "/listing-workbench/listings/batch",
        headers=other_headers,
        json={"task_key": task_key, "rows": [row]},
    )
    assert denied.status_code == 403

    assert client.post(
        "/listing-workbench/listings/batch",
        headers=owner_headers,
        json={"task_key": task_key, "rows": [row]},
    ).status_code == 200
    conflict = client.post(
        "/listing-workbench/listings/batch",
        headers=owner_headers,
        json={"task_key": task_key, "rows": [row]},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "item", "message": "item already exists"}
    ]
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).count() == 1


def test_later_business_period_reuses_active_items_and_links_new_claims_without_duplicates() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0703期",
        site="PH",
        positionings=("稳定款", "稳定款"),
    )
    existing = create_listing(headers, "ITEM-OLD", business_period="开发0703期")
    original_source_claim_ids = listing_source_claim_ids(existing["id"])
    later_claim_ids = create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0710期",
        site="菲律宾",
        positionings=("稳定款", "稳定款"),
    )
    later_task = listing_task_for_period(headers, "开发0710期")

    assert later_task["requires_confirmation"] is True
    assert later_task["reusable_listing_ids"] == [existing["id"]]

    current = services.current_business_period_start(date.today()).isoformat()
    statements: list[str] = []
    capture_for_update_statements(statements)
    try:
        response = client.post(
            "/listing-workbench/listings/batch",
            headers=headers,
            json={
                "task_key": later_task["task_key"],
                "reuse_listing_ids": [existing["id"]],
                "rows": [
                    {
                        "shop": "Shop New",
                        "item": "ITEM-NEW",
                        "listing_strategy": "新增店铺策略",
                        "first_period_start": current,
                    }
                ],
            },
        )
    finally:
        stop_capturing_for_update_statements(statements)

    assert response.status_code == 200
    assert any("listing_record" in statement for statement in statements)
    assert any("sales_claim_forecast" in statement for statement in statements)
    with SessionLocal() as db:
        listings = db.query(models.ListingRecord).order_by(models.ListingRecord.item).all()
        old_listing = db.get(models.ListingRecord, existing["id"])
        later_claims = [db.get(models.SalesClaimForecast, claim_id) for claim_id in later_claim_ids]
        assert [listing.item for listing in listings] == ["ITEM-NEW", "ITEM-OLD"]
        assert db.query(models.ItemObservationPeriod).count() == 8
        assert old_listing.source_claim_ids[: len(original_source_claim_ids)] == original_source_claim_ids
        assert set(old_listing.source_claim_ids[len(original_source_claim_ids) :]) == set(later_claim_ids)
        assert {claim.downstream_status for claim in later_claims} == {"listing_observation"}
        reuse_audit = db.query(models.AuditLog).filter_by(
            action="listing.reused",
            entity_id=existing["id"],
        ).one()
        assert reuse_audit.detail == {
            "task_key": later_task["task_key"],
            "added_claim_record_ids": later_task["claim_record_ids"],
        }


@pytest.mark.parametrize(
    ("listing_status", "tracking_status"),
    [("voided", "stopped"), ("active", "stopped")],
    ids=["voided", "stopped"],
)
def test_reuse_and_new_rows_are_atomic_when_reused_listing_is_invalid(
    listing_status: str,
    tracking_status: str,
) -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A", business_period="开发0703期")
    existing = create_listing(headers, "ITEM-OLD", business_period="开发0703期")
    original_source_claim_ids = listing_source_claim_ids(existing["id"])
    later_claim_ids = create_waiting_listing_group("销售A", "MAIN-A", business_period="开发0710期")
    with SessionLocal() as db:
        listing = db.get(models.ListingRecord, existing["id"])
        listing.status = listing_status
        listing.tracking_status = tracking_status
        db.commit()

    later_task = listing_task_for_period(headers, "开发0710期")
    assert later_task["requires_confirmation"] is True
    assert later_task["reusable_listing_ids"] == []

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": later_task["task_key"],
            "reuse_listing_ids": [existing["id"]],
            "rows": [
                {
                    "shop": "Shop New",
                    "item": "ITEM-NEW",
                    "listing_strategy": "不应落库",
                    "first_period_start": services.current_business_period_start(date.today()).isoformat(),
                }
            ],
        },
    )

    assert response.status_code == 400
    with SessionLocal() as db:
        listing = db.get(models.ListingRecord, existing["id"])
        later_claims = [db.get(models.SalesClaimForecast, claim_id) for claim_id in later_claim_ids]
        assert db.query(models.ListingRecord).count() == 1
        assert db.query(models.ItemObservationPeriod).count() == 4
        assert listing.source_claim_ids == original_source_claim_ids
        assert {claim.downstream_status for claim in later_claims} == {"waiting_listing"}


def test_valid_reuse_and_invalid_new_row_are_atomic() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A", business_period="开发0703期")
    existing = create_listing(headers, "ITEM-OLD", business_period="开发0703期")
    original_source_claim_ids = listing_source_claim_ids(existing["id"])
    later_claim_ids = create_waiting_listing_group(
        "销售A", "MAIN-A", business_period="开发0710期", site="菲律宾"
    )
    later_task = listing_task_for_period(headers, "开发0710期")

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": later_task["task_key"],
            "reuse_listing_ids": [existing["id"]],
            "rows": [
                {
                    "shop": "Shop New",
                    "item": "ITEM-NEW",
                    "listing_strategy": "",
                    "first_period_start": services.current_business_period_start(date.today()).isoformat(),
                }
            ],
        },
    )

    assert response.status_code == 400
    with SessionLocal() as db:
        listing = db.get(models.ListingRecord, existing["id"])
        later_claims = [db.get(models.SalesClaimForecast, claim_id) for claim_id in later_claim_ids]
        assert db.query(models.ListingRecord).count() == 1
        assert db.query(models.ItemObservationPeriod).count() == 4
        assert listing.source_claim_ids == original_source_claim_ids
        assert {claim.downstream_status for claim in later_claims} == {"waiting_listing"}


@pytest.mark.parametrize("mismatch", ["main_sku", "site", "owner"])
def test_cross_period_reuse_does_not_match_other_site_owner_or_main_sku(mismatch: str) -> None:
    owner_headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A", "MAIN-A", business_period="开发0703期", site="PH"
    )
    existing = create_listing(owner_headers, "ITEM-OLD", business_period="开发0703期")
    original_source_claim_ids = listing_source_claim_ids(existing["id"])

    later_owner = "销售B" if mismatch == "owner" else "销售A"
    later_headers = login("销售B", "operator", "dt-b") if mismatch == "owner" else owner_headers
    later_claim_ids = create_waiting_listing_group(
        later_owner,
        "MAIN-B" if mismatch == "main_sku" else "MAIN-A",
        business_period="开发0710期",
        site="TH" if mismatch == "site" else "菲律宾",
    )

    later_task = listing_task_for_period(later_headers, "开发0710期")
    assert later_task["requires_confirmation"] is True
    assert later_task["reusable_listing_ids"] == []

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=later_headers,
        json={
            "task_key": later_task["task_key"],
            "reuse_listing_ids": [existing["id"]],
            "rows": [
                {
                    "shop": "Shop New",
                    "item": "ITEM-NEW",
                    "listing_strategy": "不应落库",
                    "first_period_start": services.current_business_period_start(date.today()).isoformat(),
                }
            ],
        },
    )

    assert response.status_code == 400
    with SessionLocal() as db:
        listing = db.get(models.ListingRecord, existing["id"])
        later_claims = [db.get(models.SalesClaimForecast, claim_id) for claim_id in later_claim_ids]
        assert db.query(models.ListingRecord).count() == 1
        assert db.query(models.ItemObservationPeriod).count() == 4
        assert listing.source_claim_ids == original_source_claim_ids
        assert {claim.downstream_status for claim in later_claims} == {"waiting_listing"}


def test_operator_scope_and_manager_owner_filter() -> None:
    operator_a = login("销售A", "operator", "dt-a")
    operator_b = login("销售B", "operator", "dt-b")
    manager = login("主管A", "manager", "dt-m")
    create_waiting_listing_group("销售A", "MAIN-A")
    create_waiting_listing_group("销售B", "MAIN-B")

    assert [task["salesperson_name"] for task in client.get("/listing-workbench", headers=operator_a).json()["pending_listing_tasks"]] == ["销售A"]
    assert [task["salesperson_name"] for task in client.get("/listing-workbench", headers=operator_b).json()["pending_listing_tasks"]] == ["销售B"]
    assert {task["salesperson_name"] for task in client.get("/listing-workbench", headers=manager).json()["pending_listing_tasks"]} == {"销售A", "销售B"}
    filtered = client.get(
        "/listing-workbench", headers=manager, params={"salesperson_name": "销售B"}
    ).json()
    assert [task["main_sku"] for task in filtered["pending_listing_tasks"]] == ["MAIN-B"]


def test_period_review_is_atomic_and_week_four_requires_summary() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    listing = create_listing(headers, "10001")
    with SessionLocal() as db:
        periods = db.query(models.ItemObservationPeriod).order_by(models.ItemObservationPeriod.week_number).all()
        for period in periods:
            period.status = "pending_review"
            period.order_count = 1
            period.total_revenue = 100
            period.gross_profit_amount = 20
            period.metrics_fetched_at = models.now_utc()
        db.commit()
        period_ids = [period.id for period in periods]

    invalid = client.post(
        "/listing-workbench/periods/review-batch",
        headers=headers,
        json={
            "rows": [
                {
                    "period_id": period_ids[0],
                    "product_positioning": "稳定款",
                    "optimization_action": "更新主图",
                },
                {
                    "period_id": period_ids[3],
                    "product_positioning": "利润款",
                    "optimization_action": "调整售价",
                },
            ]
        },
    )

    assert invalid.status_code == 400
    assert invalid.json()["detail"]["row_errors"] == [
        {"row_index": 1, "field": "four_week_summary", "message": "four_week_summary is required for week 4"}
    ]
    with SessionLocal() as db:
        assert {db.get(models.ItemObservationPeriod, period_id).status for period_id in period_ids} == {"pending_review"}

    rows = [
        {
            "period_id": period_id,
            "product_positioning": "稳定款",
            "optimization_action": f"第{index}周优化",
            **({"four_week_summary": "首轮总结"} if index == 4 else {}),
        }
        for index, period_id in enumerate(period_ids, start=1)
    ]
    completed = client.post(
        "/listing-workbench/periods/review-batch", headers=headers, json={"rows": rows}
    )

    assert completed.status_code == 200
    assert {item["status"] for item in completed.json()} == {"completed"}
    assert all(item["first_round_completed_at"] for item in completed.json())
    with SessionLocal() as db:
        saved = db.get(models.ListingRecord, listing["id"])
        assert saved.initial_observation_completed_at is not None
        assert db.query(models.AuditLog).filter_by(action="observation.reviewed", actor_name="销售A").count() == 4


def test_completed_period_can_be_edited_by_owner_and_manager() -> None:
    owner_headers = login("销售A", "operator", "dt-a")
    other_headers = login("销售B", "operator", "dt-b")
    manager_headers = login("主管A", "manager", "dt-manager")
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-EDIT"
        period = listing.periods[0]
        period.status = "completed"
        period.order_count = 8
        period.total_revenue = 200
        period.gross_profit_amount = 50
        period.metrics_fetched_at = models.now_utc()
        period.product_positioning = "利润款"
        period.optimization_action = "原复盘动作"
        period.reviewed_at = models.now_utc()
        db.add(listing)
        db.commit()
        period_id = period.id
        metrics_fetched_at = period.metrics_fetched_at

    denied = client.post(
        "/listing-workbench/periods/review-batch",
        headers=other_headers,
        json={
            "rows": [
                {"period_id": period_id, "product_positioning": "淘汰款", "optimization_action": "越权修改"}
            ]
        },
    )
    assert denied.status_code == 403

    owner_saved = client.post(
        "/listing-workbench/periods/review-batch",
        headers=owner_headers,
        json={
            "rows": [
                {"period_id": period_id, "product_positioning": "稳定款", "optimization_action": "负责人更新"}
            ]
        },
    )
    assert owner_saved.status_code == 200
    assert owner_saved.json()[0]["status"] == "completed"
    with SessionLocal() as db:
        saved = db.get(models.ItemObservationPeriod, period_id)
        assert (saved.order_count, saved.total_revenue, saved.gross_profit_amount) == (8, 200, 50)
        assert saved.metrics_fetched_at == metrics_fetched_at
        assert (saved.product_positioning, saved.optimization_action) == ("稳定款", "负责人更新")
        assert db.query(models.AuditLog).filter_by(
            action="observation.reviewed", entity_id=period_id, actor_name="销售A"
        ).count() == 1

    manager_saved = client.post(
        "/listing-workbench/periods/review-batch",
        headers=manager_headers,
        json={
            "rows": [
                {"period_id": period_id, "product_positioning": "利润款", "optimization_action": "主管更新"}
            ]
        },
    )
    assert manager_saved.status_code == 200
    assert manager_saved.json()[0]["status"] == "completed"
    with SessionLocal() as db:
        saved = db.get(models.ItemObservationPeriod, period_id)
        assert (saved.order_count, saved.total_revenue, saved.gross_profit_amount) == (8, 200, 50)
        assert saved.metrics_fetched_at == metrics_fetched_at
        assert (saved.product_positioning, saved.optimization_action) == ("利润款", "主管更新")
        audits = db.query(models.AuditLog).filter_by(
            action="observation.reviewed", entity_id=period_id
        ).all()
        assert len(audits) == 2
        assert {log.actor_name for log in audits} == {"销售A", "主管A"}


def test_stopped_listing_can_complete_already_fetched_pending_review() -> None:
    headers = login("销售A", "operator", "dt-a")
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-STOP-REVIEW"
        listing.tracking_status = "stopped"
        period = listing.periods[0]
        period.status = "pending_review"
        period.order_count = 3
        period.total_revenue = 90
        period.gross_profit_amount = 18
        period.metrics_fetched_at = models.now_utc()
        db.add(listing)
        db.commit()
        period_id = period.id

    response = client.post(
        "/listing-workbench/periods/review-batch",
        headers=headers,
        json={
            "rows": [
                {"period_id": period_id, "product_positioning": "利润款", "optimization_action": "完成已取数复盘"}
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "completed"
    with SessionLocal() as db:
        saved = db.get(models.ItemObservationPeriod, period_id)
        assert (saved.order_count, saved.total_revenue, saved.gross_profit_amount) == (3, 90, 18)
        assert (saved.product_positioning, saved.optimization_action) == ("利润款", "完成已取数复盘")


def test_voided_listing_period_cannot_be_reviewed_atomically() -> None:
    headers = login("销售A", "operator", "dt-a")
    with SessionLocal() as db:
        voided_listing = seeded_listing("销售A", date(2026, 7, 16))
        voided_listing.item = "ITEM-VOIDED"
        voided_listing.status = "voided"
        voided_period = voided_listing.periods[0]
        voided_period.status = "pending_review"
        voided_period.metrics_fetched_at = models.now_utc()
        voided_period.product_positioning = "稳定款"
        voided_period.optimization_action = "作废前原值"
        active_listing = seeded_listing("销售A", date(2026, 8, 13))
        active_listing.item = "ITEM-ACTIVE"
        active_period = active_listing.periods[0]
        active_period.status = "pending_review"
        active_period.metrics_fetched_at = models.now_utc()
        active_period.product_positioning = "稳定款"
        active_period.optimization_action = "有效行原值"
        db.add_all([voided_listing, active_listing])
        db.commit()
        voided_period_id = voided_period.id
        active_period_id = active_period.id

    response = client.post(
        "/listing-workbench/periods/review-batch",
        headers=headers,
        json={
            "rows": [
                {"period_id": voided_period_id, "product_positioning": "淘汰款", "optimization_action": "不应修改"},
                {"period_id": active_period_id, "product_positioning": "利润款", "optimization_action": "整批不应修改"},
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "period_id", "message": "listing is not active and tracked"}
    ]
    with SessionLocal() as db:
        voided_saved = db.get(models.ItemObservationPeriod, voided_period_id)
        active_saved = db.get(models.ItemObservationPeriod, active_period_id)
        assert (voided_saved.status, voided_saved.product_positioning, voided_saved.optimization_action) == (
            "pending_review",
            "稳定款",
            "作废前原值",
        )
        assert (active_saved.status, active_saved.product_positioning, active_saved.optimization_action) == (
            "pending_review",
            "稳定款",
            "有效行原值",
        )
        assert db.query(models.AuditLog).filter_by(action="observation.reviewed").count() == 0


def test_observation_elimination_events_only_on_transitions() -> None:
    headers = login("销售A", "operator", "dt-a")
    with SessionLocal() as db:
        sequence_listing = seeded_listing("销售A", date(2026, 7, 16))
        sequence_listing.item = "ITEM-SEQUENCE"
        sequence_period = sequence_listing.periods[0]
        sequence_period.status = "pending_review"
        sequence_period.metrics_fetched_at = models.now_utc()

        batch_listing = seeded_listing("销售A", date(2026, 8, 13))
        batch_listing.item = "ITEM-BATCH"
        batch_periods = sorted(batch_listing.periods, key=lambda period: period.week_number)[:2]
        for period in batch_periods:
            period.status = "pending_review"
            period.metrics_fetched_at = models.now_utc()
        db.add_all([sequence_listing, batch_listing])
        db.commit()
        sequence_period_id = sequence_period.id
        batch_listing_id = batch_listing.id
        batch_period_ids = [period.id for period in batch_periods]

    for positioning in ["利润款", "淘汰款", "淘汰款", "稳定款", "淘汰款"]:
        response = client.post(
            "/listing-workbench/periods/review-batch",
            headers=headers,
            json={
                "rows": [
                    {
                        "period_id": sequence_period_id,
                        "product_positioning": positioning,
                        "optimization_action": f"调整为{positioning}",
                    }
                ]
            },
        )
        assert response.status_code == 200

    with SessionLocal() as db:
        sequence_events = db.query(models.AuditLog).filter_by(
            action="observation.elimination_entered", entity_id=sequence_period_id
        ).order_by(models.AuditLog.created_at).all()
        assert [event.detail["previous_positioning"] for event in sequence_events] == ["利润款", "稳定款"]

    batch_response = client.post(
        "/listing-workbench/periods/review-batch",
        headers=headers,
        json={
            "rows": [
                {
                    "period_id": batch_period_ids[1],
                    "product_positioning": "淘汰款",
                    "optimization_action": "第2周淘汰",
                },
                {
                    "period_id": batch_period_ids[0],
                    "product_positioning": "淘汰款",
                    "optimization_action": "第1周淘汰",
                },
            ]
        },
    )

    assert batch_response.status_code == 200
    with SessionLocal() as db:
        batch_events = db.query(models.AuditLog).filter(
            models.AuditLog.action == "observation.elimination_entered",
            models.AuditLog.entity_id.in_(batch_period_ids),
        ).all()
        assert [event.entity_id for event in batch_events] == [batch_period_ids[0]]
        assert batch_events[0].detail == {
            "listing_record_id": batch_listing_id,
            "week_number": 1,
            "previous_positioning": None,
            "product_positioning": "淘汰款",
        }


def test_observation_review_locks_listing_and_period_history_before_transition_decision() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-LOCK-REVIEW"
        period = listing.periods[0]
        period.status = "pending_review"
        period.metrics_fetched_at = models.now_utc()
        db.add(listing)
        db.commit()
        period_id = period.id

    statements: list[str] = []
    with SessionLocal() as db:
        capture_for_update_statements(statements)
        try:
            services.review_observation_periods(
                db,
                [
                    schemas.ObservationPeriodReviewRow(
                        period_id=period_id,
                        product_positioning="淘汰款",
                        optimization_action="并发门禁",
                    )
                ],
                "销售A",
                None,
                False,
                "销售A",
            )
            db.commit()
        finally:
            stop_capturing_for_update_statements(statements)

    assert any("listing_record" in statement for statement in statements)
    assert any("item_observation_period" in statement for statement in statements)


def test_authenticated_account_name_is_audit_actor_not_operator_owner() -> None:
    headers = login_with_distinct_account_name("账号显示名", "销售A", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    task = client.get("/listing-workbench", headers=headers).json()["pending_listing_tasks"][0]
    current = services.current_business_period_start(date.today()).isoformat()

    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task["task_key"],
            "rows": [
                {"shop": "Shop A", "item": "ITEM-A", "listing_strategy": "策略", "first_period_start": current}
            ],
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(models.ListingRecord).one().salesperson_name == "销售A"
        assert db.query(models.AuditLog).filter_by(action="listing.created").one().actor_name == "账号显示名"


def test_summary_returns_read_only_listing_history_for_main_sku() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    create_listing(headers, "ITEM-A")

    response = client.get("/listing-workbench/summary", headers=headers, params={"main_sku": "MAIN-A"})

    assert response.status_code == 200
    body = response.json()
    assert body["pending_listing_tasks"] == []
    assert [item["item"] for item in body["listing_records"]] == ["ITEM-A"]
    assert len(body["period_rows"]) == 4


def test_summary_exposes_source_business_periods_for_frontend_grouping() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A", business_period="开发0703期")
    listing = create_listing(headers, "ITEM-A", business_period="开发0703期")
    later_claim_ids = create_waiting_listing_group("销售A", "MAIN-A", business_period="开发0710期")
    with SessionLocal() as db:
        saved = db.get(models.ListingRecord, listing["id"])
        saved.source_claim_ids = list(reversed(list(saved.source_claim_ids) + later_claim_ids))
        for claim_id in later_claim_ids:
            db.get(models.SalesClaimForecast, claim_id).downstream_status = "listing_observation"
        db.commit()

    response = client.get("/listing-workbench/summary", headers=headers, params={"main_sku": "MAIN-A"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["listing_records"]) == 1
    assert body["listing_records"][0]["business_period"] == "开发0703期"
    assert body["listing_records"][0]["source_business_periods"] == ["开发0703期", "开发0710期"]
    assert {row["business_period"] for row in body["period_rows"]} == {"开发0703期"}


def test_workbench_returns_week_one_secondary_positioning_default_without_persisting_it() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0703期",
        positionings=("稳定款", "稳定款"),
    )
    listing = create_listing(headers, "ITEM-A", business_period="开发0703期")

    row = observation_row(headers, listing["id"], 1)

    assert row["product_positioning"] is None
    assert row["default_product_positioning"] == "稳定款"
    with SessionLocal() as db:
        period = db.query(models.ItemObservationPeriod).filter_by(
            listing_record_id=listing["id"], week_number=1
        ).one()
        assert period.product_positioning is None


def test_later_week_defaults_to_latest_earlier_nonempty_positioning() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0703期",
        positionings=("稳定款", "稳定款"),
    )
    listing = create_listing(headers, "ITEM-A", business_period="开发0703期")
    with SessionLocal() as db:
        periods = db.query(models.ItemObservationPeriod).filter_by(
            listing_record_id=listing["id"]
        ).order_by(models.ItemObservationPeriod.week_number).all()
        periods[0].product_positioning = "利润款"
        periods[1].product_positioning = "引流款"
        db.commit()

    row = observation_row(headers, listing["id"], 3)

    assert row["product_positioning"] is None
    assert row["default_product_positioning"] == "引流款"
    with SessionLocal() as db:
        period = db.query(models.ItemObservationPeriod).filter_by(
            listing_record_id=listing["id"], week_number=3
        ).one()
        assert period.product_positioning is None


def test_later_week_falls_back_to_secondary_positioning_when_history_is_empty() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0703期",
        positionings=("利润款", "利润款"),
    )
    listing = create_listing(headers, "ITEM-A", business_period="开发0703期")

    row = observation_row(headers, listing["id"], 3)

    assert row["product_positioning"] is None
    assert row["default_product_positioning"] == "利润款"
    with SessionLocal() as db:
        assert db.query(models.ItemObservationPeriod).filter_by(
            listing_record_id=listing["id"], product_positioning=None
        ).count() == 4


def test_mixed_secondary_positions_do_not_choose_an_arbitrary_default() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group(
        "销售A",
        "MAIN-A",
        business_period="开发0703期",
        positionings=("引流款", "利润款"),
    )
    listing = create_listing(headers, "ITEM-A", business_period="开发0703期")

    row = observation_row(headers, listing["id"], 1)

    assert row["product_positioning"] is None
    assert row["default_product_positioning"] is None
    with SessionLocal() as db:
        period = db.query(models.ItemObservationPeriod).filter_by(
            listing_record_id=listing["id"], week_number=1
        ).one()
        assert period.product_positioning is None


def test_shop_item_and_start_lock_after_metrics_but_strategy_remains_editable() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        db.add(listing)
        listing.periods[0].metrics_fetched_at = models.now_utc()
        db.commit()
        listing_id = listing.id

    with SessionLocal() as db:
        with pytest.raises(ValueError, match="shop cannot be changed"):
            services.update_listing_record(
                db,
                listing_id,
                schemas.ListingRecordUpdate(shop="Other Shop"),
                "销售A",
                None,
                False,
            )
        updated = services.update_listing_record(
            db,
            listing_id,
            schemas.ListingRecordUpdate(listing_strategy="调整后的策略"),
            "销售A",
            None,
            False,
        )
        assert updated.listing_strategy == "调整后的策略"


def test_concurrent_item_conflict_commits_before_building_update_response(monkeypatch) -> None:
    headers = login("销售A", "operator", "dt-a")
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-A"
        conflict = seeded_listing("销售A", date(2026, 8, 13))
        conflict.item = "ITEM-B"
        db.add_all([listing, conflict])
        db.commit()
        listing_id = listing.id

    def force_concurrent_conflict(db, listing_id, *_args, **_kwargs):
        listing = db.get(models.ListingRecord, listing_id)
        listing.item = "ITEM-B"
        return listing

    source_context_calls = 0
    original_source_context = services.listing_source_context

    def tracked_source_context(*args, **kwargs):
        nonlocal source_context_calls
        source_context_calls += 1
        return original_source_context(*args, **kwargs)

    monkeypatch.setattr(services, "update_listing_record", force_concurrent_conflict)
    monkeypatch.setattr(services, "listing_source_context", tracked_source_context)

    response = client.patch(
        f"/listing-workbench/listings/{listing_id}",
        headers=headers,
        json={"item": "ITEM-B"},
    )

    assert response.status_code == 409
    assert source_context_calls == 0
    with SessionLocal() as db:
        assert db.get(models.ListingRecord, listing_id).item == "ITEM-A"


def test_only_manager_can_void_a_listing() -> None:
    operator_headers = login("销售A", "operator", "dt-a")
    manager_headers = login("主管A", "manager", "dt-manager")
    create_waiting_listing_group("销售A", "MAIN-A")
    listing = create_listing(operator_headers, "ITEM-VOID")

    forbidden = client.patch(
        f"/listing-workbench/listings/{listing['id']}",
        headers=operator_headers,
        json={"status": "voided", "void_reason": "运营无权作废"},
    )

    assert forbidden.status_code == 403
    with SessionLocal() as db:
        assert db.get(models.ListingRecord, listing["id"]).status == "active"

    allowed = client.patch(
        f"/listing-workbench/listings/{listing['id']}",
        headers=manager_headers,
        json={"status": "voided", "void_reason": "主管确认下架"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["status"] == "voided"


def test_stop_resume_preserves_reviewed_history_and_replans_pending_data() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 5, 7))
        db.add(listing)
        periods = sorted(listing.periods, key=lambda period: period.week_number)
        periods[0].status = "completed"
        periods[1].status = "pending_review"
        db.commit()
        listing_id = listing.id
        fixed_dates = [periods[0].period_start, periods[1].period_start]

    with SessionLocal() as db:
        stopped = services.update_listing_record(
            db,
            listing_id,
            schemas.ListingRecordUpdate(tracking_status="stopped"),
            "销售A",
            None,
            False,
            today=date(2026, 7, 20),
        )
        db.commit()
        assert stopped.tracking_status == "stopped"

    with SessionLocal() as db:
        resumed = services.update_listing_record(
            db,
            listing_id,
            schemas.ListingRecordUpdate(tracking_status="active"),
            "销售A",
            None,
            False,
            today=date(2026, 7, 20),
        )
        db.commit()
        periods = db.query(models.ItemObservationPeriod).order_by(models.ItemObservationPeriod.week_number).all()
        resumed_status = resumed.tracking_status
        replanned_dates = [period.period_start for period in periods]

    assert resumed_status == "active"
    assert replanned_dates[:2] == fixed_dates
    assert replanned_dates[2:] == [date(2026, 7, 23), date(2026, 7, 30)]


def test_resume_does_not_move_an_earlier_missing_week_after_a_later_fetched_week() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 5, 7))
        db.add(listing)
        periods = sorted(listing.periods, key=lambda period: period.week_number)
        periods[1].status = "pending_review"
        periods[1].metrics_fetched_at = models.now_utc()
        db.commit()
        listing_id = listing.id
        original_first_two_dates = [periods[0].period_start, periods[1].period_start]

    with SessionLocal() as db:
        services.update_listing_record(
            db,
            listing_id,
            schemas.ListingRecordUpdate(tracking_status="stopped"),
            "销售A",
            None,
            False,
            today=date(2026, 7, 20),
        )
        db.commit()

    with SessionLocal() as db:
        services.update_listing_record(
            db,
            listing_id,
            schemas.ListingRecordUpdate(tracking_status="active"),
            "销售A",
            None,
            False,
            today=date(2026, 7, 20),
        )
        db.commit()
        periods = db.query(models.ItemObservationPeriod).order_by(models.ItemObservationPeriod.week_number).all()
        replanned_dates = [period.period_start for period in periods]

    assert replanned_dates[:2] == original_first_two_dates
    assert replanned_dates[2:] == [date(2026, 7, 23), date(2026, 7, 30)]
    assert replanned_dates == sorted(replanned_dates)


def test_completed_first_round_can_add_a_later_period() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 5, 7))
        db.add(listing)
        listing.initial_observation_completed_at = models.now_utc()
        for period in listing.periods:
            period.status = "completed"
        db.commit()
        listing_id = listing.id

    with SessionLocal() as db:
        period = services.add_observation_period(
            db,
            listing_id,
            date(2026, 7, 23),
            "销售A",
            None,
            False,
            today=date(2026, 7, 20),
        )
        db.commit()
        saved = (period.week_number, period.period_start, period.period_end, period.status)

    assert saved == (5, date(2026, 7, 23), date(2026, 7, 29), "pending_data")


def test_apply_week_metrics_distinguishes_missing_source_from_true_zero() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-ZERO"
        db.add(listing)
        db.commit()

    with SessionLocal() as db:
        missing = services.apply_week_metrics(db, "ITEM-ZERO", date(2026, 7, 16), None)
        db.commit()
        assert missing.status == "pending_data"
        assert missing.metrics_fetched_at is None
        assert missing.order_count is None
        assert db.query(models.NotificationLog).count() == 0

    with SessionLocal() as db:
        zero = services.apply_week_metrics(
            db,
            "ITEM-ZERO",
            date(2026, 7, 16),
            {
                "order_count": 0,
                "total_revenue": 0,
                "gross_profit_amount": 0,
                "source_snapshot": {"file": "week.zip", "row": 2},
            },
        )
        db.commit()
        assert zero.status == "pending_review"
        assert (zero.order_count, zero.total_revenue, zero.gross_profit_amount) == (0, 0, 0)
        assert zero.metrics_fetched_at is not None
        assert zero.source_snapshot == {"file": "week.zip", "row": 2}
        saved_listing = db.get(models.ListingRecord, zero.listing_record_id)
        assert services.observation_period_read(zero, saved_listing)["gross_profit_rate"] is None
        assert db.query(models.NotificationLog).count() == 1


def test_apply_week_metrics_freezes_first_success() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-PROFIT"
        db.add(listing)
        db.commit()

    metrics_a = {
        "order_count": 8,
        "total_revenue": 200,
        "gross_profit_amount": 50,
        "source_snapshot": {"file": "week-a.zip", "row": 1},
    }
    metrics_b = {
        "order_count": 99,
        "total_revenue": 999,
        "gross_profit_amount": 1,
        "source_snapshot": {"file": "week-b.zip", "row": 9},
    }
    with SessionLocal() as db:
        first = services.apply_week_metrics(db, "ITEM-PROFIT", date(2026, 7, 16), metrics_a)
        db.commit()
        first_fetched_at = first.metrics_fetched_at

        period = services.apply_week_metrics(db, "ITEM-PROFIT", date(2026, 7, 16), metrics_b)
        db.commit()
        listing = db.get(models.ListingRecord, period.listing_record_id)
        row = services.observation_period_read(period, listing)
        saved_snapshot = period.source_snapshot
        saved_fetched_at = period.metrics_fetched_at
        notification_count = db.query(models.NotificationLog).count()
        metrics_audit_count = db.query(models.AuditLog).filter_by(action="observation.metrics_applied").count()

    assert (row["order_count"], row["total_revenue"], row["gross_profit_amount"]) == (8, 200, 50)
    assert row["gross_profit_rate"] == 0.25
    assert saved_snapshot == {"file": "week-a.zip", "row": 1}
    assert saved_fetched_at == first_fetched_at
    assert notification_count == 1
    assert metrics_audit_count == 1


def test_apply_week_metrics_locks_listing_and_period_before_first_success_check() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-LOCK-METRICS"
        db.add(listing)
        db.commit()

    statements: list[str] = []
    with SessionLocal() as db:
        capture_for_update_statements(statements)
        try:
            services.apply_week_metrics(
                db,
                "ITEM-LOCK-METRICS",
                date(2026, 7, 16),
                {"order_count": 1, "total_revenue": 10, "gross_profit_amount": 2},
            )
            db.commit()
        finally:
            stop_capturing_for_update_statements(statements)

    assert any("listing_record" in statement for statement in statements)
    assert any("item_observation_period" in statement for statement in statements)


def test_apply_week_metrics_skips_stopped_listing() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-STOPPED"
        listing.tracking_status = "stopped"
        db.add(listing)
        db.commit()

    with SessionLocal() as db:
        period = services.apply_week_metrics(
            db,
            "ITEM-STOPPED",
            date(2026, 7, 16),
            {"order_count": 1, "total_revenue": 10, "gross_profit_amount": 2},
        )
        db.commit()
        saved_status = period.status
        notification_count = db.query(models.NotificationLog).count()

    assert saved_status == "pending_data"
    assert notification_count == 0


_for_update_capture_handlers: dict[int, object] = {}


def capture_for_update_statements(statements: list[str]) -> None:
    def capture(_conn, _clauseelement, _multiparams, _params, _execution_options) -> None:
        if getattr(_clauseelement, "_for_update_arg", None) is not None:
            statements.append(str(_clauseelement))

    _for_update_capture_handlers[id(statements)] = capture
    event.listen(engine, "before_execute", capture)


def stop_capturing_for_update_statements(statements: list[str]) -> None:
    capture = _for_update_capture_handlers.pop(id(statements))
    event.remove(engine, "before_execute", capture)


def login(name: str, role: str, dingtalk_user_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name=name, role=role, dingtalk_user_id=dingtalk_user_id, enabled=True))
        db.commit()
    response = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": dingtalk_user_id})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login_with_distinct_account_name(account_name: str, operator_name: str, dingtalk_user_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        user = models.User(dingtalk_user_id=dingtalk_user_id, name=account_name)
        db.add(user)
        db.flush()
        db.add(
            models.RoleMapping(
                user_id=user.id,
                name=operator_name,
                role="operator",
                dingtalk_user_id=dingtalk_user_id,
                enabled=True,
            )
        )
        db.commit()
    response = client.post("/auth/dingtalk/login", json={"dingtalk_user_id": dingtalk_user_id})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_waiting_listing_group(
    owner: str,
    main_sku: str,
    *,
    business_period: str = "开发0710期",
    site: str = "PH",
    positionings: tuple[str | None, str | None] = (None, None),
) -> list[str]:
    with SessionLocal() as db:
        claim_ids = []
        for index in range(2):
            opportunity = models.NewProductOpportunity(
                source_type="selection1_developer_claim_feedback",
                source_file="选品1.xlsx",
                source_sheet="开发0710数据",
                source_row=index + 1,
                batch=business_period,
                country="PH",
                site=site,
                main_sku=main_sku,
                main_sku_name=f"{main_sku} 商品",
                sub_sku=f"{main_sku}-SUB-{index + 1}",
            )
            db.add(opportunity)
            db.flush()
            claim = models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name=owner,
                claim_result="claim",
                downstream_status="waiting_listing",
                product_positioning=positionings[index],
            )
            db.add(claim)
            db.flush()
            claim_ids.append(claim.id)
        db.commit()
    return claim_ids


def listing_task_for_period(headers: dict[str, str], business_period: str) -> dict:
    response = client.get("/listing-workbench", headers=headers)
    assert response.status_code == 200
    return next(
        task for task in response.json()["pending_listing_tasks"] if task["business_period"] == business_period
    )


def create_listing(headers: dict[str, str], item: str, business_period: str | None = None) -> dict:
    tasks = client.get("/listing-workbench", headers=headers).json()["pending_listing_tasks"]
    task = next(task for task in tasks if task["business_period"] == business_period) if business_period else tasks[0]
    current = services.current_business_period_start(date.today()).isoformat()
    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task["task_key"],
            "rows": [
                {"shop": "Shop A", "item": item, "listing_strategy": "策略A", "first_period_start": current}
            ],
        },
    )
    assert response.status_code == 200
    return response.json()[0]


def observation_row(headers: dict[str, str], listing_id: str, week_number: int) -> dict:
    response = client.get("/listing-workbench", headers=headers)
    assert response.status_code == 200
    return next(
        row
        for row in response.json()["period_rows"]
        if row["listing_record_id"] == listing_id and row["week_number"] == week_number
    )


def listing_source_claim_ids(listing_id: str) -> list[str]:
    with SessionLocal() as db:
        return list(db.get(models.ListingRecord, listing_id).source_claim_ids)


def seeded_listing(owner: str, first_period_start: date) -> models.ListingRecord:
    listing = models.ListingRecord(
        id=models.new_id(),
        source_group_key="seed-task",
        source_claim_ids=[],
        source_type="test",
        main_sku="MAIN-SEED",
        salesperson_name=owner,
        shop="Shop Seed",
        item=models.new_id(),
        listing_strategy="种子策略",
        first_period_start=first_period_start,
        first_period_end=first_period_start + timedelta(days=6),
    )
    for week_number, (period_start, period_end) in enumerate(
        services.initial_observation_period_dates(first_period_start), start=1
    ):
        listing.periods.append(
            models.ItemObservationPeriod(
                id=models.new_id(), week_number=week_number, period_start=period_start, period_end=period_end
            )
        )
    return listing
