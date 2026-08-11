#!/usr/bin/env bash
set -euo pipefail

app_dir="${1:?app dir required}"
script_dir="${2:?script dir required}"
stop_after="${3:-false}"
root_dir="$(dirname "$app_dir")"
lock_dir="$root_dir/.codex_locks"
mkdir -p "$lock_dir" "$app_dir/backups"

exec 9>"$lock_dir/global.lock"
flock -n 9

cd "$app_dir"
backup_dir="$app_dir/backups/uat_operator_cleanup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"

db_user="$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
docker compose exec -T postgres pg_dump -Fc -U "$db_user" "$db_name" > "$backup_dir/db_before.dump"
sha256sum "$backup_dir/db_before.dump" > "$backup_dir/db_before.dump.sha256"
docker compose exec -T postgres pg_restore -l < "$backup_dir/db_before.dump" > "$backup_dir/db_before.dump.list"

docker compose cp "$script_dir/remove_uat_operator_profiles.py" api:/tmp/remove_uat_operator_profiles.py >/dev/null
docker compose exec -T -e PYTHONPATH=/app api python /tmp/remove_uat_operator_profiles.py --apply | tee "$backup_dir/apply.json"
docker compose exec -T -e PYTHONPATH=/app api python /tmp/remove_uat_operator_profiles.py | tee "$backup_dir/verify_after.json"
docker compose ps --format 'table {{.Name}}\t{{.State}}\t{{.Status}}' | tee "$backup_dir/compose_before_stop.txt"

if [ "$stop_after" = "true" ]; then
  docker compose stop | tee "$backup_dir/compose_stop.txt"
  docker compose ps --format 'table {{.Name}}\t{{.State}}\t{{.Status}}' | tee "$backup_dir/compose_after_stop.txt"
fi

echo "BACKUP_DIR=$backup_dir"
