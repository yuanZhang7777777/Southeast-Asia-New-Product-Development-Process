import time
from datetime import datetime

from sqlalchemy import select

from app import models
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.dingtalk_card_sender import DingTalkCardConfig, DingTalkCardSender
from app.dingtalk_user_sync import sync_configured_dingtalk_user_ids
from app.notification_jobs import (
    send_arrival_daily_cards,
    send_daily_elimination_summary,
    send_daily_manager_review_summary,
)
from app.plm_download import BEIJING, download_plm_export, previous_beijing_date


SYNC_HOUR = 8
OPERATOR_NOTIFICATION_HOUR = 9
MANAGER_NOTIFICATION_HOUR = 10
RETRY_SECONDS = 300
CHECK_SECONDS = 30

JOB_PLM_SYNC = "plm_sync"
JOB_DAILY_NOTIFICATION = "daily_notification"
JOB_MANAGER_NOTIFICATION = "manager_notification"


def load_last_completed_date(job_name: str) -> str | None:
    try:
        with SessionLocal() as db:
            return db.scalar(
                select(models.SchedulerJobRun.run_date)
                .where(models.SchedulerJobRun.job_name == job_name)
                .order_by(models.SchedulerJobRun.run_date.desc())
                .limit(1)
            )
    except Exception as exc:
        print(f"job_run_load_failed job={job_name} error={exc}", flush=True)
        return None


def record_job_run(job_name: str, run_date: str, report: dict[str, object] | None = None) -> None:
    try:
        with SessionLocal() as db:
            existing = db.scalar(
                select(models.SchedulerJobRun).where(
                    models.SchedulerJobRun.job_name == job_name,
                    models.SchedulerJobRun.run_date == run_date,
                )
            )
            if existing:
                existing.report = report or {}
            else:
                db.add(models.SchedulerJobRun(job_name=job_name, run_date=run_date, report=report or {}))
            db.commit()
    except Exception as exc:
        print(f"job_run_record_failed job={job_name} error={exc}", flush=True)


def plm_sync_due(now: datetime, completed_date: str | None) -> bool:
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    target_date = previous_beijing_date(current)
    return current.hour >= SYNC_HOUR and completed_date != target_date


def dingtalk_user_sync_due(now: datetime, completed_at: datetime | None) -> bool:
    return False


def daily_notification_due(now: datetime, completed_date: str | None) -> bool:
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    today = current.date().isoformat()
    return current.hour >= OPERATOR_NOTIFICATION_HOUR and completed_date != today


def manager_notification_due(now: datetime, completed_date: str | None) -> bool:
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    today = current.date().isoformat()
    return current.hour >= MANAGER_NOTIFICATION_HOUR and completed_date != today


def thursday_notification_due(now: datetime, completed_date: str | None) -> bool:
    return manager_notification_due(now, completed_date)


def run_plm_sync(settings: Settings, date_text: str) -> str:
    path = download_plm_export(
        date_text,
        base_url=settings.plm_base_url,
        username=settings.plm_username,
        password=settings.plm_password,
        bloc_name=settings.plm_bloc_name,
        cache_dir=settings.plm_cache_dir,
    )
    return path.name


def run_dingtalk_user_sync(settings: Settings) -> dict[str, object]:
    with SessionLocal() as db:
        report = sync_configured_dingtalk_user_ids(db, settings, write=True)
        db.commit()
    return {key: len(value) if isinstance(value, list) else value for key, value in report.items()}


def run_daily_notification_jobs(settings: Settings, now: datetime) -> dict[str, int]:
    sender = DingTalkCardSender(DingTalkCardConfig.from_settings(settings))
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    arrival_date = previous_beijing_date(current)
    with SessionLocal() as db:
        arrival_logs = send_arrival_daily_cards(db, settings, sender, arrival_date)
        db.commit()
    return {"arrival": len(arrival_logs)}


def run_manager_notification_jobs(settings: Settings, now: datetime) -> dict[str, int]:
    sender = DingTalkCardSender(DingTalkCardConfig.from_settings(settings))
    current = now if now.tzinfo else now.replace(tzinfo=BEIJING)
    current = current.astimezone(BEIJING)
    today = current.date().isoformat()
    with SessionLocal() as db:
        elimination_logs = send_daily_elimination_summary(db, settings, sender, today)
        review_logs = send_daily_manager_review_summary(db, settings, sender, current)
        db.commit()
    return {"elimination": len(elimination_logs), "manager_review": len(review_logs)}


def run_thursday_notification_jobs(settings: Settings, now: datetime) -> dict[str, int]:
    return run_manager_notification_jobs(settings, now)


def main() -> None:
    settings = get_settings()
    print(f"scheduler started for {settings.app_env}; plm_sync={settings.plm_sync_enabled}", flush=True)
    completed_date: str | None = load_last_completed_date(JOB_PLM_SYNC)
    daily_notification_completed_date: str | None = load_last_completed_date(JOB_DAILY_NOTIFICATION)
    manager_notification_completed_date: str | None = load_last_completed_date(JOB_MANAGER_NOTIFICATION)
    dingtalk_user_synced_at: datetime | None = None
    retry_after = 0.0
    while True:
        now = datetime.now(BEIJING)
        if settings.plm_sync_enabled and plm_sync_due(now, completed_date) and time.monotonic() >= retry_after:
            date_text = previous_beijing_date(now)
            try:
                file_name = run_plm_sync(settings, date_text)
                completed_date = date_text
                retry_after = 0.0
                record_job_run(JOB_PLM_SYNC, date_text, {"file": file_name})
                print(f"plm_sync_completed date={date_text} file={file_name} bloc={settings.plm_bloc_name}", flush=True)
            except Exception as exc:
                retry_after = time.monotonic() + RETRY_SECONDS
                print(f"plm_sync_failed date={date_text} error={exc}", flush=True)
        if settings.dingtalk_user_sync_enabled and dingtalk_user_sync_due(now, dingtalk_user_synced_at):
            try:
                report = run_dingtalk_user_sync(settings)
                dingtalk_user_synced_at = now
                print(f"dingtalk_user_sync_completed report={report}", flush=True)
            except Exception as exc:
                print(f"dingtalk_user_sync_failed error={exc}", flush=True)
        if daily_notification_due(now, daily_notification_completed_date):
            try:
                report = run_daily_notification_jobs(settings, now)
                daily_notification_completed_date = now.date().isoformat()
                record_job_run(JOB_DAILY_NOTIFICATION, daily_notification_completed_date, dict(report))
                print(f"daily_notification_jobs_completed report={report}", flush=True)
            except Exception as exc:
                print(f"daily_notification_jobs_failed error={exc}", flush=True)
        if manager_notification_due(now, manager_notification_completed_date):
            try:
                report = run_manager_notification_jobs(settings, now)
                manager_notification_completed_date = now.date().isoformat()
                record_job_run(JOB_MANAGER_NOTIFICATION, manager_notification_completed_date, dict(report))
                print(f"manager_notification_jobs_completed report={report}", flush=True)
            except Exception as exc:
                print(f"manager_notification_jobs_failed error={exc}", flush=True)
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
