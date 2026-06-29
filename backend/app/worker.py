import time

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"worker started for {settings.app_env}", flush=True)
    while True:
        # ponytail: placeholder loop until Redis-backed jobs exist in Phase 2.
        time.sleep(60)


if __name__ == "__main__":
    main()
