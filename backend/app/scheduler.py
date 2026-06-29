import time

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"scheduler started for {settings.app_env}", flush=True)
    while True:
        # ponytail: placeholder loop until reminder scans and sync jobs are implemented.
        time.sleep(60)


if __name__ == "__main__":
    main()
