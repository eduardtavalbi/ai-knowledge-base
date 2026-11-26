#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: bash scripts/verify_postgres_backup.sh path/to/backup.dump\n' >&2
  exit 2
fi

backup="$1"
if [[ ! -s "$backup" ]]; then
  printf 'Backup file is missing or empty: %s\n' "$backup" >&2
  exit 1
fi

checksum_file="$backup.sha256"
if [[ ! -s "$checksum_file" ]]; then
  printf 'Backup checksum file is missing or empty: %s\n' "$checksum_file" >&2
  exit 1
fi

expected_checksum="$(awk 'NR == 1 { print $1 }' "$checksum_file")"
if command -v sha256sum >/dev/null 2>&1; then
  actual_checksum="$(sha256sum "$backup" | awk '{ print $1 }')"
elif command -v shasum >/dev/null 2>&1; then
  actual_checksum="$(shasum -a 256 "$backup" | awk '{ print $1 }')"
else
  printf 'Neither sha256sum nor shasum is available.\n' >&2
  exit 1
fi

if [[ -z "$expected_checksum" || "$expected_checksum" != "$actual_checksum" ]]; then
  printf 'Backup checksum verification failed: %s\n' "$backup" >&2
  exit 1
fi

restore_db="mindbase_restore_check_$(date -u +%Y%m%d%H%M%S)_$RANDOM"
created=0

cleanup() {
  if [[ "$created" -eq 1 ]]; then
    docker compose exec -T db sh -ec \
      'dropdb --if-exists --username="$POSTGRES_USER" "$1"' sh "$restore_db" || {
        printf 'Warning: could not remove temporary database %s\n' "$restore_db" >&2
      }
  fi
}
trap cleanup EXIT

docker compose exec -T db sh -ec \
  'createdb --username="$POSTGRES_USER" "$1"' sh "$restore_db"
created=1

docker compose exec -T db sh -ec \
  'pg_restore --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$1"' \
  sh "$restore_db" < "$backup"

version="$(
  docker compose exec -T db sh -ec \
    'psql --set=ON_ERROR_STOP=1 --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$1" --command="SELECT version_num FROM alembic_version"' \
    sh "$restore_db"
)"
if [[ -z "$version" ]]; then
  printf 'Restored database has no Alembic migration version.\n' >&2
  exit 1
fi

documents_table="$(
  docker compose exec -T db sh -ec \
    'psql --set=ON_ERROR_STOP=1 --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$1" --command="$2"' \
    sh "$restore_db" "SELECT to_regclass('public.documents') IS NOT NULL"
)"
if [[ "$documents_table" != "t" ]]; then
  printf 'Restored database is missing public.documents.\n' >&2
  exit 1
fi

printf 'Restore verified: database=%s alembic_version=%s documents_table=present\n' \
  "$restore_db" "$version"
