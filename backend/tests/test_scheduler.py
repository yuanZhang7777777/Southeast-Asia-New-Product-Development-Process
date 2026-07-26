import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_scheduler.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.scheduler as scheduler
from app import models
from app.config import Settings
from app.db import Base, SessionLocal, engine
from app.scheduler import daily_notification_due, dingtalk_user_sync_due, manager_notification_due, plm_sync_due


def test_plm_sync_runs_once_after_0800_beijing() -> None:
    before = datetime(2026, 7, 10, 7, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    due = datetime(2026, 7, 10, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert not plm_sync_due(before, None)
    assert plm_sync_due(due, None)
    assert not plm_sync_due(due, "2026-07-09")


def test_dingtalk_user_sync_no_longer_runs_weekly() -> None:
    now = datetime(2026, 7, 13, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert not dingtalk_user_sync_due(now, None)
    assert not dingtalk_user_sync_due(now, datetime(2026, 7, 6, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_daily_notification_due_runs_once_after_0900_beijing() -> None:
    before = datetime(2026, 7, 13, 8, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    due = datetime(2026, 7, 13, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert not daily_notification_due(before, None)
    assert daily_notification_due(due, None)
    assert not daily_notification_due(due, "2026-07-13")


def test_manager_notification_due_runs_once_after_1000_beijing_daily() -> None:
    before = datetime(2026, 7, 13, 9, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    due = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert not manager_notification_due(before, None)
    assert manager_notification_due(due, None)
    assert not manager_notification_due(due, "2026-07-13")


def test_job_run_marker_persists_across_restart() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    assert scheduler.load_last_completed_date(scheduler.JOB_PLM_SYNC) is None
    scheduler.record_job_run(scheduler.JOB_PLM_SYNC, "2026-07-24", {"file": "a.xlsx"})
    scheduler.record_job_run(scheduler.JOB_PLM_SYNC, "2026-07-25", {"file": "b.xlsx"})
    scheduler.record_job_run(scheduler.JOB_PLM_SYNC, "2026-07-25", {"file": "c.xlsx"})

    restored = scheduler.load_last_completed_date(scheduler.JOB_PLM_SYNC)
    assert restored == "2026-07-25"
    assert not plm_sync_due(datetime(2026, 7, 26, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai")), restored)

    with SessionLocal() as db:
        runs = (
            db.query(models.SchedulerJobRun)
            .filter_by(job_name=scheduler.JOB_PLM_SYNC)
            .order_by(models.SchedulerJobRun.run_date)
            .all()
        )
    assert [(run.run_date, run.report["file"]) for run in runs] == [("2026-07-24", "a.xlsx"), ("2026-07-25", "c.xlsx")]


def test_operator_and_manager_notification_jobs_are_split(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self) -> None:
            calls.append("commit")

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(scheduler, "DingTalkCardSender", lambda _config: object())
    monkeypatch.setattr(scheduler, "send_arrival_daily_cards", lambda *_args: calls.append("arrival") or [object()])
    monkeypatch.setattr(scheduler, "send_daily_elimination_summary", lambda *_args: calls.append("elimination") or [object()])
    monkeypatch.setattr(scheduler, "send_daily_manager_review_summary", lambda *_args: calls.append("review") or [object()])

    settings = Settings(dingtalk_card_autosend_enabled=True)
    now = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert scheduler.run_daily_notification_jobs(settings, now) == {"arrival": 1}
    assert calls == ["arrival", "commit"]

    calls.clear()
    assert scheduler.run_manager_notification_jobs(settings, now) == {"elimination": 1, "manager_review": 1}
    assert calls == ["elimination", "review", "commit"]
