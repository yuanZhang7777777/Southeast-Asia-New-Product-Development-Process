from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app import models
from app.db import SessionLocal


PREFIX = "UAT"


def run(apply: bool) -> dict:
    with SessionLocal() as db:
        profiles = list(
            db.scalars(
                select(models.OperatorAssignmentProfile).where(models.OperatorAssignmentProfile.operator_name.like(f"{PREFIX}%"))
            )
        )
        names = sorted({profile.operator_name for profile in profiles})
        users = list(db.scalars(select(models.User).where(models.User.name.in_(names)))) if names else []
        roles = list(db.scalars(select(models.RoleMapping).where(models.RoleMapping.name.in_(names)))) if names else []
        notifications = (
            list(
                db.scalars(
                    select(models.NotificationLog).where(
                        models.NotificationLog.receiver_name.in_(names)
                        | models.NotificationLog.message_title.like("%UAT运营%")
                        | models.NotificationLog.dedupe_key.like("%UAT运营%")
                    )
                )
            )
            if names
            else []
        )
        audit_logs = []
        if names:
            for row in db.scalars(select(models.AuditLog)):
                text = json.dumps(row.detail or {}, ensure_ascii=False)
                if row.actor_name in names or any(name in text for name in names):
                    audit_logs.append(row)
        result = {
            "apply": apply,
            "names": names,
            "operator_profiles": len(profiles),
            "users": len(users),
            "roles": len(roles),
            "notifications": len(notifications),
            "audit_logs": len(audit_logs),
        }
        if apply:
            for row in notifications:
                db.delete(row)
            for row in audit_logs:
                db.delete(row)
            for row in profiles:
                db.delete(row)
            for row in roles:
                db.delete(row)
            for row in users:
                db.delete(row)
            db.add(
                models.AuditLog(
                    actor_name="Codex",
                    action="uat_operator_cleanup",
                    entity_type="maintenance",
                    detail={
                        "removed_names": names,
                        "removed_operator_profiles": len(profiles),
                        "removed_notifications": len(notifications),
                        "removed_audit_logs": len(audit_logs),
                        "ran_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            db.commit()
        else:
            db.rollback()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.apply), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
