#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 0 ]]; then
  printf 'Usage: BACKUP_DIR=backups bash scripts/backup_postgres.sh\n' >&2
  exit 2
fi

umask 077
backup_dir="${BACKUP_DIR:-backups}"
mkdir -p "$backup_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$backup_dir/mindbase-$timestamp.dump"
temporary="$backup.tmp"

if [[ -e "$backup" || -e "$temporary" ]]; then
  printf 'Refusing to overwrite existing backup: %s\n' "$backup" >&2
  exit 1
fi

cleanup() {
  rm -f "$temporary"
}
trap cleanup EXIT

docker compose exec -T db sh -ec \
  'pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$temporary"

test -s "$temporary"
docker compose exec -T db pg_restore --list < "$temporary" > /dev/null
mv "$temporary" "$backup"
sha256sum "$backup" > "$backup.sha256"
chmod 600 "$backup" "$backup.sha256"

printf '%s\n' "$backup"
