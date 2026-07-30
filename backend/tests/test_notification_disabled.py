import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_notification_disabled.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.notification_jobs import send_arrival_daily_cards  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeSender:
    def __init__(self) -> None:
        self.cards = []

    def send_arrival_card(self, card):
        self.cards.append(card)
        return {"ok": True}


def test_arrival_card_skips_notification_disabled_operator() -> None:
    sender = FakeSender()
    with SessionLocal() as db:
        db.add(models.RoleMapping(name="销售静默", role="operator", dingtalk_user_id="dt-muted", enabled=True, notification_enabled=False))
        batch = models.PlmArrivalBatch(arrival_date="2026-07-12", source_hash="muted", bloc_name="集团八部", row_count=1)
        db.add(batch)
        db.flush()
        db.add(models.PlmArrivalItem(batch_id=batch.id, arrival_type="new_arrival", salesperson_name="销售静默", main_sku="MAIN-M", sub_sku="SUB-M"))
        db.flush()
        logs = send_arrival_daily_cards(db, Settings(dingtalk_card_autosend_enabled=True), sender, "2026-07-12")

        assert [log.send_status for log in logs] == ["skipped_notification_disabled"]
        assert sender.cards == []
        db.flush()
        assert db.query(models.NotificationLog).count() == 1
