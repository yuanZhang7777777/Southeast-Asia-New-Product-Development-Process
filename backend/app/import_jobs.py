from __future__ import annotations

from sqlalchemy import select

from app import models, schemas, selection1_importer, selection2_importer
from app.db import SessionLocal
from app.models import now_utc


def create_import_job(
    *,
    kind: str,
    source_file: str,
    source_sheet: str,
    business_period: str | None = None,
) -> models.ImportJob:
    if kind not in {"selection1", "selection2"}:
        raise ValueError("unsupported import job kind")
    return models.ImportJob(
        kind=kind,
        status="pending",
        source_file=source_file,
        source_sheet=source_sheet,
        business_period=business_period,
    )


def run_pending_import_jobs_once() -> int:
    processed = 0
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(models.ImportJob)
                .where(models.ImportJob.status == "pending")
                .order_by(models.ImportJob.created_at.asc())
                .limit(1)
            )
        )
        for job in jobs:
            job_id = job.id
            job.status = "running"
            job.started_at = now_utc()
            db.commit()
            try:
                if job.kind == "selection1":
                    result = selection1_importer.import_selection1_workbook(
                        db,
                        schemas.Selection1ImportRequest(
                            source_file=job.source_file,
                            source_sheet=job.source_sheet,
                            business_period=job.business_period,
                        ),
                    )
                elif job.kind == "selection2":
                    result = selection2_importer.import_selection2_workbook(
                        db,
                        schemas.Selection2ImportRequest(source_file=job.source_file, source_sheet=job.source_sheet),
                    )
                else:
                    raise ValueError(f"unsupported import job kind: {job.kind}")
                job.result = result.model_dump(mode="json")
                job.status = "completed"
                job.completed_at = now_utc()
                db.commit()
            except Exception as exc:
                db.rollback()
                job = db.get(models.ImportJob, job_id)
                if job is not None:
                    job.status = "failed"
                    job.error = str(exc)
                    job.completed_at = now_utc()
                    db.commit()
            processed += 1
    return processed
