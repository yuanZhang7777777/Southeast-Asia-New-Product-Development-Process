#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:?app dir required}"
TMP_DIR="${2:?tmp dir required}"
LOCK_DIR="$(dirname "$APP_DIR")/.codex_locks"

mkdir -p "$LOCK_DIR"
exec 9>"$LOCK_DIR/global.lock"
flock -n 9

cd "$APP_DIR"

stamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="backups/selection1_dedupe_plm_rename_${stamp}"
mkdir -p "$backup_dir"

db_user="$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
echo "backup database: $db_name as $db_user"
docker compose exec -T postgres pg_dump -Fc -U "$db_user" "$db_name" > "$backup_dir/db_before.dump"
sha256sum "$backup_dir/db_before.dump" > "$backup_dir/db_before.sha256"
docker compose exec -T postgres pg_restore -l < "$backup_dir/db_before.dump" > "$backup_dir/db_before.list"
echo "backup verified: $backup_dir/db_before.dump"

cp backend/app/plm_processing.py "$backup_dir/plm_processing.py.before"
cp backend/app/plm_local_ingest.py "$backup_dir/plm_local_ingest.py.before"
cp "$TMP_DIR/plm_processing.py" backend/app/plm_processing.py
cp "$TMP_DIR/plm_local_ingest.py" backend/app/plm_local_ingest.py

docker compose cp "$TMP_DIR/dedupe_selection1_tail_and_rename_plm_discovery.py" api:/tmp/dedupe_selection1_tail_and_rename_plm_discovery.py >/dev/null
echo "apply dedupe and rename"
docker compose exec -T -e PYTHONPATH=/app api python /tmp/dedupe_selection1_tail_and_rename_plm_discovery.py --apply | tee "$backup_dir/apply.json"

echo "build backend services"
docker compose build api worker scheduler | tee "$backup_dir/build.log"
echo "restart backend services"
docker compose up -d --no-deps api worker scheduler | tee "$backup_dir/up.log"
docker compose exec -T api python -m compileall app/plm_processing.py app/plm_local_ingest.py | tee "$backup_dir/compileall.log"

api_container="$(docker compose ps -q api)"
health=""
for _ in $(seq 1 30); do
  health="$(docker inspect -f '{{.State.Health.Status}}' "$api_container" 2>/dev/null || true)"
  if [ "$health" = "healthy" ]; then
    break
  fi
  sleep 3
done
if [ "$health" != "healthy" ]; then
  docker compose ps
  docker compose logs --tail=120 api
  exit 1
fi

docker compose ps --format 'table {{.Name}}\t{{.Status}}' | tee "$backup_dir/compose_ps.txt"
echo "BACKUP_DIR=$APP_DIR/$backup_dir"
