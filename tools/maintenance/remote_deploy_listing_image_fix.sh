#!/usr/bin/env bash
set -euo pipefail

app_dir="${1:?app dir required}"
payload_dir="${2:?payload dir required}"
build_and_restart="${3:-false}"
root_dir="$(dirname "$app_dir")"
lock_dir="$root_dir/.codex_locks"
mkdir -p "$lock_dir" "$app_dir/backups"

exec 9>"$lock_dir/global.lock"
flock -n 9

cd "$app_dir"
backup_dir="$app_dir/backups/listing_image_fix_$(date +%Y%m%d_%H%M%S)"
files=(
  "backend/app/schemas.py"
  "backend/app/services.py"
  "frontend/src/api.ts"
  "frontend/src/ListingObservationView.tsx"
)

for file in "${files[@]}"; do
  mkdir -p "$backup_dir/$(dirname "$file")"
  cp "$app_dir/$file" "$backup_dir/$file"
  cp "$payload_dir/$file" "$app_dir/$file"
done

if [ "$build_and_restart" = "true" ]; then
  docker compose build api frontend
  docker compose up -d --no-deps api frontend
  docker compose ps --format 'table {{.Name}}\t{{.State}}\t{{.Status}}' | tee "$backup_dir/compose_after_deploy.txt"
fi

echo "BACKUP_DIR=$backup_dir"
