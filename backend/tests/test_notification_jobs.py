import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.notification_jobs import (  # noqa: E402
    send_arrival_daily_cards,
    send_daily_elimination_summary,
    send_daily_manager_review_summary,
)
from app.workflow_status import OPPORTUNITY_CLAIM_REJECTED, OPPORTUNITY_CLAIM_SUBMITTED  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeSender:
    def __init__(self) -> None:
        self.arrival_cards = []
        self.todo_cards = []

    def send_arrival_card(self, card):
        self.arrival_cards.append(card)
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
        assert sender.todo_cards == []
        assert sender.arrival_cards == []
