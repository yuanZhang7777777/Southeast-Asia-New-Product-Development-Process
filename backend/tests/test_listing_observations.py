import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def test_period_review_rejects_completed_or_inactive_rows_atomically() -> None:
    headers = login("销售A", "operator", "dt-a")
    create_waiting_listing_group("销售A", "MAIN-A")
    listing = create_listing(headers, "10001")
    with SessionLocal() as db:
        periods = db.query(models.ItemObservationPeriod).order_by(models.ItemObservationPeriod.week_number).all()
        periods[0].status = "completed"
        periods[1].status = "pending_review"
        db.commit()
        first_id, second_id = periods[0].id, periods[1].id

    payload = {
        "rows": [
            {"period_id": first_id, "product_positioning": "稳定款", "optimization_action": "不应重提"},
            {"period_id": second_id, "product_positioning": "利润款", "optimization_action": "保持原状"},
        ]
    }
    invalid_status = client.post("/listing-workbench/periods/review-batch", headers=headers, json=payload)
    assert invalid_status.status_code == 400
    assert invalid_status.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "period_id", "message": "period must be pending_review"}
    ]
    with SessionLocal() as db:
        assert db.get(models.ItemObservationPeriod, second_id).status == "pending_review"
        db.get(models.ListingRecord, listing["id"]).tracking_status = "stopped"
        db.commit()

    inactive = client.post(
        "/listing-workbench/periods/review-batch",
        headers=headers,
        json={
            "rows": [
                {"period_id": second_id, "product_positioning": "利润款", "optimization_action": "保持原状"}
            ]
        },
    )
    assert inactive.status_code == 400
    assert inactive.json()["detail"]["row_errors"] == [
        {"row_index": 0, "field": "period_id", "message": "listing is not active and tracked"}
    ]


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


def test_apply_week_metrics_calculates_rate_on_read_and_deduplicates_notification() -> None:
    with SessionLocal() as db:
        listing = seeded_listing("销售A", date(2026, 7, 16))
        listing.item = "ITEM-PROFIT"
        db.add(listing)
        db.commit()

    metrics = {"order_count": 8, "total_revenue": 200, "gross_profit_amount": 50}
    with SessionLocal() as db:
        period = services.apply_week_metrics(db, "ITEM-PROFIT", date(2026, 7, 16), metrics)
        services.apply_week_metrics(db, "ITEM-PROFIT", date(2026, 7, 16), metrics)
        db.commit()
        listing = db.get(models.ListingRecord, period.listing_record_id)
        row = services.observation_period_read(period, listing)
        notification_count = db.query(models.NotificationLog).count()

    assert row["gross_profit_rate"] == 0.25
    assert notification_count == 1


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


def create_waiting_listing_group(owner: str, main_sku: str) -> list[str]:
    with SessionLocal() as db:
        claim_ids = []
        for index in range(2):
            opportunity = models.NewProductOpportunity(
                source_type="selection1_developer_claim_feedback",
                source_file="选品1.xlsx",
                source_sheet="开发0710数据",
                source_row=index + 1,
                batch="开发0710期",
                country="PH",
                site="PH",
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
            )
            db.add(claim)
            db.flush()
            claim_ids.append(claim.id)
        db.commit()
    return claim_ids


def create_listing(headers: dict[str, str], item: str) -> dict:
    task_key = client.get("/listing-workbench", headers=headers).json()["pending_listing_tasks"][0]["task_key"]
    current = services.current_business_period_start(date.today()).isoformat()
    response = client.post(
        "/listing-workbench/listings/batch",
        headers=headers,
        json={
            "task_key": task_key,
            "rows": [
                {"shop": "Shop A", "item": item, "listing_strategy": "策略A", "first_period_start": current}
            ],
        },
    )
    assert response.status_code == 200
    return response.json()[0]


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
