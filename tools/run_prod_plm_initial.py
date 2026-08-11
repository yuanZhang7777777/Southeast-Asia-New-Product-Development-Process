import json

from app.config import get_settings
from app.db import SessionLocal
from app.plm_download import download_plm_export
from app.plm_processing import process_plm_arrival_workbook

settings = get_settings()
dates = [f"2026-07-{day:02d}" for day in range(27, 32)] + [f"2026-08-{day:02d}" for day in range(1, 4)]
print(
    json.dumps(
        {
            "event": "plm_initial_start",
            "dates": dates,
            "bloc": settings.plm_bloc_name,
            "workflow": settings.workflow_automation_enabled,
        },
        ensure_ascii=False,
    ),
    flush=True,
)
for date_text in dates:
    print(json.dumps({"event": "date_start", "date": date_text}, ensure_ascii=False), flush=True)
    path = download_plm_export(
        date_text,
        base_url=settings.plm_base_url,
        username=settings.plm_username,
        password=settings.plm_password,
        bloc_name=settings.plm_bloc_name,
        cache_dir=settings.plm_cache_dir,
    )
    with SessionLocal() as db:
        report = process_plm_arrival_workbook(
            db,
            path,
            date_text,
            source_file=path.name,
            bloc_name=settings.plm_bloc_name,
            workflow_automation_enabled=settings.workflow_automation_enabled,
        )
    print(
        json.dumps({"event": "date_done", "date": date_text, "file": path.name, "report": report}, ensure_ascii=False, default=str),
        flush=True,
    )
print(json.dumps({"event": "plm_initial_done"}, ensure_ascii=False), flush=True)
