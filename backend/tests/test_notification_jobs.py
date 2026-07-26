import os
import sys
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender, masked_dingtalk_user_id  # noqa: E402
from app.notification_jobs import (  # noqa: E402
    send_arrival_daily_cards,
    send_daily_elimination_summary,
    send_daily_manager_review_summary,
    send_operator_listing_reminder_cards,
)
from app.workflow_status import (  # noqa: E402
    CLAIM_DISABLED,
    CLAIM_WAITING_LISTING,
    CLAIM_WAITING_SECONDARY_RESEARCH,
    OPPORTUNITY_CLAIM_REJECTED,
    OPPORTUNITY_CLAIM_SUBMITTED,
)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeSender:
    def __init__(self, arrival_failures: int = 0) -> None:
        self.arrival_cards = []
        self.todo_cards = []
        self.arrival_failures = arrival_failures

    def send_arrival_card(self, card):
        self.arrival_cards.append(card)
        if self.arrival_failures:
            self.arrival_failures -= 1
            raise RuntimeError("arrival card failed")
        return {"ok": True}

    def send_new_product_todo(self, card):
        self.todo_cards.append(card)
        return {"ok": True}


def test_arrival_daily_cards_group_by_date_and_salesperson_and_dedupe() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="hash-1", bloc_name="集团八部", row_count=3)
        db.add(batch)
        db.flush()
        db.add_all(
            [
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    arrival_type="new_arrival",
                    salesperson_name="销售A",
                    main_sku="MAIN-1",
                    sub_sku="S1",
                    product_name="新品一",
                ),
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    arrival_type="new_arrival",
                    salesperson_name="销售A",
                    main_sku="MAIN-1",
                    sub_sku="S2",
                    product_name="新品一",
                ),
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    arrival_type="restock",
                    salesperson_name="销售A",
                    main_sku="MAIN-2",
                    sub_sku="S3",
                    product_name="老品二",
                ),
            ]
        )
        db.flush()

        first = send_arrival_daily_cards(db, settings, sender, "2026-07-12")
        second = send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert len(first) == 1
        assert [log.dedupe_key for log in second] == [log.dedupe_key for log in first]
        assert len(sender.arrival_cards) == 1
        card = sender.arrival_cards[0]
        assert card.receiver_dingtalk_user_id == "dt-sales-a"
        assert card.arrival_date == "2026-07-12"
        assert [(item.main_sku, item.child_sku_count, item.product_name) for item in card.new_items] == [("MAIN-1", 2, "新品一")]
        assert [(item.main_sku, item.child_sku_count, item.product_name) for item in card.old_items] == [("MAIN-2", 1, "老品二")]
        assert db.query(models.NotificationLog).count() == 1


def test_arrival_daily_cards_carry_handle_button_linking_to_platform() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="hash-btn", bloc_name="集团八部", row_count=1)
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                arrival_type="new_arrival",
                salesperson_name="销售A",
                main_sku="MAIN-1",
                sub_sku="S1",
                product_name="新品一",
            )
        )
        db.flush()

        send_arrival_daily_cards(db, settings, sender, "2026-07-12")

    assert len(sender.arrival_cards) == 1
    card = sender.arrival_cards[0]
    assert card.action_text == "去处理"
    assert card.action_url == "https://np.example/?from=ding&role=operator"

    payload = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret")
    ).build_arrival_create_and_deliver_payload(card)
    card_params = payload["cardData"]["cardParamMap"]
    assert card_params["action_text"] == "去处理"
    assert card_params["action_url"] == "https://np.example/?from=ding&role=operator"


def test_arrival_daily_cards_send_every_salesperson_group_to_test_receiver() -> None:
    settings = Settings(
        dingtalk_card_autosend_enabled=True,
        dingtalk_card_test_receiver_name="刘学城",
        platform_base_url="https://np.example",
    )
    sender = FakeSender()
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True),
                models.RoleMapping(name="销售B", role="sales", dingtalk_user_id="dt-sales-b", enabled=True),
                models.RoleMapping(name="刘学城", role="super_admin", dingtalk_user_id="dt-liu", enabled=True),
            ]
        )
        batch = models.PlmArrivalBatch(
            arrival_date="2026-07-12",
            source_hash="hash-test-receiver",
            bloc_name="集团八部",
            row_count=2,
        )
        db.add(batch)
        db.flush()
        db.add_all(
            [
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    arrival_type="new_arrival",
                    salesperson_name="销售A",
                    main_sku="MAIN-A",
                    sub_sku="SUB-A",
                ),
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    arrival_type="restock",
                    salesperson_name="销售B",
                    main_sku="MAIN-B",
                    sub_sku="SUB-B",
                ),
            ]
        )
        db.flush()

        logs = send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert len(logs) == 2
        assert {card.salesperson_name for card in sender.arrival_cards} == {"销售A", "销售B"}
        assert {card.receiver_dingtalk_user_id for card in sender.arrival_cards} == {"dt-liu"}


def test_arrival_daily_cards_test_recipient_mode_redirects_and_keeps_original_in_logs() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        calls.append((url, headers, body))
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-test-mode-1"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret", test_recipient_user_id="dt-test-owner"),
        http_post=fake_post,
    )
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="hash-test-mode", bloc_name="集团八部", row_count=1)
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                arrival_type="new_arrival",
                salesperson_name="销售A",
                main_sku="MAIN-1",
                sub_sku="S1",
                product_name="新品一",
            )
        )
        db.flush()

        logs = send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert len(logs) == 1
        assert logs[0].send_status == "sent"
        assert logs[0].receiver_name == "销售A"
        deliver_call = calls[1]
        assert deliver_call[2]["userId"] == "dt-test-owner"
        assert deliver_call[2]["openSpaceId"] == "dtv1.card//im_robot.dt-test-owner"
        assert "（测试模式｜原收件人：销售A）" in deliver_call[2]["cardData"]["cardParamMap"]["summary_text"]
        db.flush()
        redirect_audit = db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_test_redirect").one()
        assert redirect_audit.entity_id == logs[0].id
        assert redirect_audit.detail["original_receiver"] == "销售A"
        assert redirect_audit.detail["original_receiver_dingtalk_user_id"] == masked_dingtalk_user_id("dt-sales-a")
        assert redirect_audit.detail["actual_receiver_dingtalk_user_id"] == masked_dingtalk_user_id("dt-test-owner")


def test_arrival_daily_cards_without_test_recipient_write_no_redirect_audit() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")

    def fake_post(url: str, headers: dict, body: dict) -> dict:
        if url.endswith("/oauth2/accessToken"):
            return {"accessToken": "token-value"}
        return {"cardInstanceId": "card-no-test-mode"}

    sender = DingTalkCardSender(
        DingTalkCardConfig(client_id="cid", client_secret="secret"),
        http_post=fake_post,
    )
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="hash-no-test-mode", bloc_name="集团八部", row_count=1)
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                arrival_type="new_arrival",
                salesperson_name="销售A",
                main_sku="MAIN-1",
                sub_sku="S1",
                product_name="新品一",
            )
        )
        db.flush()

        logs = send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert len(logs) == 1
        assert logs[0].send_status == "sent"
        assert db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_test_redirect").count() == 0


def test_arrival_daily_cards_do_not_fall_back_when_test_receiver_is_missing() -> None:
    settings = Settings(
        dingtalk_card_autosend_enabled=True,
        dingtalk_card_test_receiver_name="刘学城",
    )
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        batch = models.PlmArrivalBatch(
            arrival_date="2026-07-12",
            source_hash="hash-missing-test-receiver",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                arrival_type="new_arrival",
                salesperson_name="销售A",
                main_sku="MAIN-A",
                sub_sku="SUB-A",
            )
        )
        db.flush()

        with pytest.raises(RuntimeError, match="test receiver"):
            send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert sender.arrival_cards == []


def test_arrival_daily_cards_log_skip_when_salesperson_has_no_dingtalk_user_id() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True)
    sender = FakeSender()
    with SessionLocal() as db:
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="hash-2", bloc_name="集团八部", row_count=1)
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                arrival_type="new_arrival",
                salesperson_name="销售B",
                main_sku="MAIN-3",
                sub_sku="S4",
                product_name="新品三",
            )
        )
        db.flush()

        logs = send_arrival_daily_cards(db, settings, sender, "2026-07-12")

        assert len(logs) == 1
        assert logs[0].send_status == "skipped_no_receiver"
        assert sender.arrival_cards == []


def test_elimination_daily_summary_sends_unnotified_rows_to_managers_and_marks_done() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    submitted = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True),
                models.RoleMapping(name="管理员", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
                models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True),
            ]
        )
        db.add_all(
            [
                models.NewProductOpportunity(
                    id="op-1",
                    source_type="selection1",
                    main_sku="MAIN-E",
                    sub_sku="SUB-E",
                    main_sku_name="淘汰商品",
                    batch="2026-W29",
                    site="PH",
                ),
                models.NewProductOpportunity(
                    id="op-2",
                    source_type="selection1",
                    main_sku="MAIN-K",
                    sub_sku="SUB-K",
                    main_sku_name="保留商品",
                ),
                models.SalesClaimForecast(
                    opportunity_id="op-1",
                    salesperson_name="销售A",
                    product_positioning="淘汰款",
                    secondary_conclusion="销量趋势变差",
                    secondary_research_submitted_at=submitted,
                ),
                models.SalesClaimForecast(
                    opportunity_id="op-2",
                    salesperson_name="销售B",
                    product_positioning="引流款",
                    secondary_research_submitted_at=submitted,
                ),
            ]
        )
        db.flush()

        first = send_daily_elimination_summary(db, settings, sender, "2026-07-13")
        second = send_daily_elimination_summary(db, settings, sender, "2026-07-13")

        assert len(first) == 2
        assert second == []
        assert sender.todo_cards == []
        assert {card.receiver_dingtalk_user_id for card in sender.arrival_cards} == {"dt-manager-a", "dt-admin"}
        assert all(card.card_title == "淘汰款提醒" for card in sender.arrival_cards)
        assert all(card.left_label == "淘汰款" and card.left_count == 1 for card in sender.arrival_cards)
        assert all("2026-W29 | PH | MAIN-E | SUB-E | 销售A | 淘汰商品 | 销量趋势变差" in card.sku_markdown for card in sender.arrival_cards)
        assert db.query(models.NotificationLog).filter_by(message_title="淘汰款已汇总").count() == 1


def test_elimination_daily_summary_sends_once_to_test_receiver_instead_of_managers() -> None:
    settings = Settings(
        dingtalk_card_autosend_enabled=True,
        dingtalk_card_test_receiver_name="刘学城",
        platform_base_url="https://np.example",
    )
    sender = FakeSender()
    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True),
                models.RoleMapping(name="管理员", role="super_admin", dingtalk_user_id="dt-admin", enabled=True),
                models.RoleMapping(name="刘学城", role="super_admin", dingtalk_user_id="dt-liu", enabled=True),
            ]
        )
        db.add(
            models.NewProductOpportunity(
                id="op-test-receiver",
                source_type="test",
                main_sku="MAIN-E",
                sub_sku="SUB-E",
            )
        )
        db.add(
            models.SalesClaimForecast(
                id="claim-test-receiver",
                opportunity_id="op-test-receiver",
                salesperson_name="销售A",
                product_positioning="淘汰款",
                secondary_research_submitted_at=models.now_utc(),
            )
        )
        db.flush()

        logs = send_daily_elimination_summary(db, settings, sender, "2026-07-13")

        assert len(logs) == 1
        assert len(sender.arrival_cards) == 1
        assert sender.arrival_cards[0].receiver_dingtalk_user_id == "dt-liu"
        assert sender.arrival_cards[0].salesperson_name == "刘学城"


def test_elimination_daily_summary_sends_each_observation_transition_once() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True))
        listing = models.ListingRecord(
            id="listing-weekly",
            source_group_key="task-weekly",
            source_claim_ids=[],
            source_type="test",
            business_period="开发0710期",
            country="PH",
            main_sku="MAIN-W",
            main_sku_name="周期淘汰商品",
            salesperson_name="销售A",
            shop="Shop A",
            item="ITEM-W",
            listing_strategy="策略",
            first_period_start=date(2026, 7, 16),
            first_period_end=date(2026, 7, 22),
        )
        listing.periods.append(
            models.ItemObservationPeriod(
                id="period-elimination",
                week_number=1,
                period_start=date(2026, 7, 16),
                period_end=date(2026, 7, 22),
                status="completed",
                product_positioning="稳定款",
                optimization_action="继续观察",
                reviewed_at=models.now_utc(),
            )
        )
        db.add(listing)
        db.add_all(
            [
                models.AuditLog(
                    id="audit-enter-1",
                    action="observation.elimination_entered",
                    entity_type="item_observation_period",
                    entity_id="period-elimination",
                    detail={
                        "listing_record_id": "listing-weekly",
                        "week_number": 1,
                        "previous_positioning": "利润款",
                        "product_positioning": "淘汰款",
                    },
                    actor_name="销售A",
                ),
                models.AuditLog(
                    id="audit-enter-2",
                    action="observation.elimination_entered",
                    entity_type="item_observation_period",
                    entity_id="period-elimination",
                    detail={
                        "listing_record_id": "listing-weekly",
                        "week_number": 1,
                        "previous_positioning": "稳定款",
                        "product_positioning": "淘汰款",
                    },
                    actor_name="销售A",
                ),
                models.AuditLog(
                    id="audit-reviewed-clearance",
                    action="observation.reviewed",
                    entity_type="item_observation_period",
                    entity_id="period-elimination",
                    detail={"week_number": 1, "product_positioning": "清仓款"},
                    actor_name="销售A",
                ),
            ]
        )
        db.flush()

        first = send_daily_elimination_summary(db, settings, sender, "2026-07-30")
        second = send_daily_elimination_summary(db, settings, sender, "2026-07-30")

        assert len(first) == 1
        assert second == []
        assert len(sender.arrival_cards) == 1
        assert sender.arrival_cards[0].left_count == 2
        assert sender.arrival_cards[0].sku_markdown.count(
            "开发0710期 | PH | MAIN-W | ITEM-W | 销售A | 周期淘汰商品 | 第1周"
        ) == 2
        marked_ids = {
            log.provider_message_id
            for log in db.query(models.NotificationLog).filter_by(message_title="淘汰款已汇总")
        }
        assert marked_ids == {"audit-enter-1", "audit-enter-2"}


def test_elimination_daily_summary_retries_failed_observation_transition() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender(arrival_failures=1)
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True))
        listing = models.ListingRecord(
            id="listing-transition-retry",
            source_group_key="task-transition-retry",
            source_claim_ids=[],
            source_type="test",
            main_sku="MAIN-RETRY",
            salesperson_name="销售A",
            shop="Shop A",
            item="ITEM-RETRY",
            listing_strategy="策略",
            first_period_start=date(2026, 7, 16),
            first_period_end=date(2026, 7, 22),
        )
        listing.periods.append(
            models.ItemObservationPeriod(
                id="period-transition-retry",
                week_number=1,
                period_start=date(2026, 7, 16),
                period_end=date(2026, 7, 22),
                status="completed",
                product_positioning="淘汰款",
                optimization_action="停止投放",
                reviewed_at=models.now_utc(),
            )
        )
        db.add(listing)
        db.add(
            models.AuditLog(
                id="audit-transition-retry",
                action="observation.elimination_entered",
                entity_type="item_observation_period",
                entity_id="period-transition-retry",
                detail={
                    "listing_record_id": "listing-transition-retry",
                    "week_number": 1,
                    "previous_positioning": "利润款",
                    "product_positioning": "淘汰款",
                },
                actor_name="销售A",
            )
        )
        db.flush()

        first = send_daily_elimination_summary(db, settings, sender, "2026-07-30")

        assert len(first) == 1
        assert first[0].send_status == "failed"
        assert db.query(models.NotificationLog).filter_by(message_title="淘汰款已汇总").count() == 0

        second = send_daily_elimination_summary(db, settings, sender, "2026-07-30")

        assert len(second) == 1
        assert second[0].send_status == "sent"
        assert len(sender.arrival_cards) == 2
        marked = db.query(models.NotificationLog).filter_by(message_title="淘汰款已汇总").one()
        assert marked.provider_message_id == "audit-transition-retry"


def test_elimination_daily_summary_retries_failed_manager_card() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    submitted = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    claim_digest = hashlib.sha1("claim-retry".encode("utf-8")).hexdigest()[:12]
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True))
        db.add(
            models.NewProductOpportunity(
                id="op-retry",
                source_type="selection1",
                main_sku="MAIN-R",
                sub_sku="SUB-R",
                main_sku_name="待重试商品",
            )
        )
        db.add(
            models.SalesClaimForecast(
                id="claim-retry",
                opportunity_id="op-retry",
                salesperson_name="销售A",
                product_positioning="淘汰款",
                secondary_research_submitted_at=submitted,
            )
        )
        db.add(
            models.NotificationLog(
                dedupe_key=f"dingtalk_card:elimination:{claim_digest}:经理A",
                receiver_name="经理A",
                channel="dingtalk_card",
                message_title="淘汰款提醒",
                send_status="failed",
                provider_message_id=claim_digest,
            )
        )
        db.flush()

        logs = send_daily_elimination_summary(db, settings, sender, "2026-07-13")

        assert len(logs) == 1
        assert logs[0].send_status == "sent"
        assert len(sender.arrival_cards) == 1
        assert db.query(models.NotificationLog).filter_by(message_title="淘汰款已汇总").count() == 1


def _seed_arrived_claim(
    db,
    claim_id: str,
    salesperson: str,
    main_sku: str,
    sub_sku: str,
    downstream_status: str,
    product_name: str | None = None,
    with_arrival: bool = True,
    claim_result: str = "claim",
    source_column: str = "platform",
) -> None:
    opportunity_id = f"op-{claim_id}"
    db.add(
        models.NewProductOpportunity(
            id=opportunity_id,
            source_type="test",
            main_sku=main_sku,
            sub_sku=sub_sku,
            main_sku_name=product_name,
        )
    )
    db.add(
        models.SalesClaimForecast(
            id=claim_id,
            opportunity_id=opportunity_id,
            salesperson_name=salesperson,
            claim_result=claim_result,
            source_column=source_column,
            downstream_status=downstream_status,
        )
    )
    if with_arrival:
        db.add(
            models.ArrivalRecord(
                opportunity_id=opportunity_id,
                claim_record_id=claim_id,
                salesperson_name=salesperson,
            )
        )


def test_listing_reminder_cards_count_statuses_and_dedupe_per_operator_per_day() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        db.add(models.RoleMapping(name="销售B", role="operator", dingtalk_user_id="dt-sales-b", enabled=True))
        _seed_arrived_claim(db, "claim-l1", "销售A", "MAIN-1", "SUB-1", CLAIM_WAITING_LISTING, product_name="新品一")
        _seed_arrived_claim(db, "claim-l2", "销售A", "MAIN-1", "SUB-2", CLAIM_WAITING_LISTING, product_name="新品一")
        _seed_arrived_claim(db, "claim-s1", "销售A", "MAIN-2", "SUB-3", CLAIM_WAITING_SECONDARY_RESEARCH, product_name="新品二")
        _seed_arrived_claim(db, "claim-x1", "销售B", "MAIN-5", "SUB-6", CLAIM_WAITING_LISTING, source_column="excel")
        _seed_arrived_claim(db, "claim-x2", "销售B", "MAIN-6", "SUB-7", CLAIM_WAITING_LISTING, claim_result="reject")
        db.flush()

        first = send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27")
        second = send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27")

        assert [log.dedupe_key for log in first] == ["dingtalk_card:listing-reminder:2026-07-27:销售A"]
        assert [log.dedupe_key for log in second] == [log.dedupe_key for log in first]
        assert len(sender.todo_cards) == 1
        card = sender.todo_cards[0]
        assert card.receiver_dingtalk_user_id == "dt-sales-a"
        assert card.left_count == 2
        assert card.right_count == 1
        assert card.card_title == "已到货新品催办"
        assert card.left_label == "待刊登"
        assert card.right_label == "待二调"
        assert card.tip_text == "MAIN-1|新品一、MAIN-2|新品二"
        assert card.action_url == "https://np.example/?from=ding&role=operator"
        db.flush()
        log = db.query(models.NotificationLog).one()
        assert log.send_status == "sent"
        assert log.message_title == "已到货新品催办"
        assert log.receiver_name == "销售A"
        audit = db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_sent", entity_id=log.id).one()
        assert audit.detail["left_count"] == 2
        assert audit.detail["right_count"] == 1
        assert audit.detail["send_status"] == "sent"

        third = send_operator_listing_reminder_cards(db, settings, sender, "2026-07-28")

        assert [log.dedupe_key for log in third] == ["dingtalk_card:listing-reminder:2026-07-28:销售A"]
        assert len(sender.todo_cards) == 2


def test_listing_reminder_cards_send_nothing_when_no_qualifying_claims() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售B", role="operator", dingtalk_user_id="dt-sales-b", enabled=True))
        _seed_arrived_claim(db, "claim-n1", "销售B", "MAIN-1", "SUB-1", CLAIM_WAITING_LISTING, with_arrival=False)
        _seed_arrived_claim(db, "claim-n2", "销售B", "MAIN-2", "SUB-2", CLAIM_DISABLED)
        _seed_arrived_claim(db, "claim-n3", "销售B", "MAIN-3", "SUB-3", "listing_observation")
        db.flush()

        assert send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27") == []
        assert sender.todo_cards == []
        assert db.query(models.NotificationLog).count() == 0


def test_listing_reminder_tip_limits_to_five_main_skus_with_overflow() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售A", role="operator", dingtalk_user_id="dt-sales-a", enabled=True))
        for index in range(1, 8):
            _seed_arrived_claim(
                db,
                f"claim-{index}",
                "销售A",
                f"MAIN-{index}",
                f"SUB-{index}",
                CLAIM_WAITING_LISTING,
                product_name=f"新品{index}",
            )
        db.flush()

        send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27")

        assert len(sender.todo_cards) == 1
        card = sender.todo_cards[0]
        assert card.left_count == 7
        assert card.right_count == 0
        assert card.tip_text == "MAIN-1|新品1、MAIN-2|新品2、MAIN-3|新品3、MAIN-4|新品4、MAIN-5|新品5 +2"


def test_listing_reminder_cards_log_skip_when_operator_has_no_dingtalk_mapping() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True)
    sender = FakeSender()
    with SessionLocal() as db:
        _seed_arrived_claim(db, "claim-nomap", "销售C", "MAIN-9", "SUB-9", CLAIM_WAITING_SECONDARY_RESEARCH)
        db.flush()

        logs = send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27")

        assert len(logs) == 1
        assert logs[0].send_status == "skipped_no_receiver"
        assert logs[0].dedupe_key == "dingtalk_card:listing-reminder:2026-07-27:销售C"
        assert sender.todo_cards == []
        db.flush()
        assert db.query(models.AuditLog).filter_by(action="notification.dingtalk_card_skipped").count() == 1


def test_daily_manager_review_summary_runs_on_any_day() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=True, platform_base_url="https://np.example")
    sender = FakeSender()
    wednesday = datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True))
        db.add_all(
            [
                models.NewProductOpportunity(
                    source_type="test",
                    main_sku="MAIN-C",
                    sub_sku="S1",
                    current_status=OPPORTUNITY_CLAIM_SUBMITTED,
                ),
                models.NewProductOpportunity(
                    source_type="test",
                    main_sku="MAIN-R",
                    sub_sku="S2",
                    current_status=OPPORTUNITY_CLAIM_REJECTED,
                ),
            ]
        )
        db.flush()

        logs = send_daily_manager_review_summary(db, settings, sender, wednesday)

        assert len(logs) == 1
        assert len(sender.todo_cards) == 1
        assert sender.todo_cards[0].left_count == 1
        assert sender.todo_cards[0].right_count == 1


def test_notification_jobs_do_not_send_when_autosend_disabled() -> None:
    settings = Settings(dingtalk_card_autosend_enabled=False)
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="经理A", role="manager", dingtalk_user_id="dt-manager-a", enabled=True))
        db.flush()

        assert send_daily_elimination_summary(db, settings, sender, "2026-07-13") == []
        assert send_daily_manager_review_summary(db, settings, sender, datetime(2026, 7, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))) == []
        assert send_arrival_daily_cards(db, settings, sender, "2026-07-12") == []
        assert send_operator_listing_reminder_cards(db, settings, sender, "2026-07-27") == []
        assert sender.todo_cards == []
        assert sender.arrival_cards == []
