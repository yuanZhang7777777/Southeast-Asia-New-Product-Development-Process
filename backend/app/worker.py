import time

from app.config import get_settings
from app.import_jobs import run_pending_import_jobs_once


def main() -> None:
    settings = get_settings()
    print(f"worker started for {settings.app_env}", flush=True)
    while True:
        processed = run_pending_import_jobs_once()
        time.sleep(1 if processed else 5)


if __name__ == "__main__":
    main()
