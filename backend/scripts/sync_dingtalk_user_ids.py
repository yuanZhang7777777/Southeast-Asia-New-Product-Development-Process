from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.dingtalk_user_sync import fetch_access_token, list_dingtalk_users, sync_role_mapping_user_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    settings = get_settings()
    users = list_dingtalk_users(fetch_access_token(settings.dingtalk_client_id, settings.dingtalk_client_secret))
    with SessionLocal() as db:
        report = sync_role_mapping_user_ids(db, users, write=args.write, only_names=set(args.only) or None)
        if args.write:
            db.commit()

    output = Path(__file__).resolve().parents[2] / "outputs" / "dingtalk_user_sync_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "write" if args.write else "dry-run",
        **report,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in payload.items()}, ensure_ascii=False))
    print(output)


if __name__ == "__main__":
    main()
