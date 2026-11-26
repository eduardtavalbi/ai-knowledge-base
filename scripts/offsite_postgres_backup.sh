#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  BACKUP_REMOTE=remote:mindbase BACKUP_AGE_RECIPIENT=age1... bash scripts/offsite_postgres_backup.sh backup
  BACKUP_REMOTE=remote:mindbase BACKUP_AGE_IDENTITY_FILE=/secure/age-key.txt bash scripts/offsite_postgres_backup.sh verify-latest
  BACKUP_REMOTE=remote:mindbase BACKUP_RETENTION_DAYS=30 bash scripts/offsite_postgres_backup.sh prune

BACKUP_REMOTE is an rclone remote path. Configure rclone credentials outside this repository.
USAGE
}

command_name="${1:-}"
if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

if [[ -z "${BACKUP_REMOTE:-}" || "$BACKUP_REMOTE" != *:* ]]; then
  printf 'BACKUP_REMOTE must be an rclone remote path (remote:path), not a local directory.\n' >&2
  exit 2
fi

retention_days="${BACKUP_RETENTION_DAYS:-30}"
if [[ ! "$retention_days" =~ ^[1-9][0-9]*$ ]]; then
  printf 'BACKUP_RETENTION_DAYS must be a positive integer.\n' >&2
  exit 2
fi

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Required command is missing: %s\n' "$1" >&2
    exit 1
  }
}

umask 077
work_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

case "$command_name" in
  backup)
    : "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT to an age public recipient}"
    require_command docker
    require_command age
    require_command rclone
    require_command sha256sum

    plain_backup="$(BACKUP_DIR="$work_dir" bash scripts/backup_postgres.sh)"
    archive_name="$(basename "$plain_backup").age"
    encrypted="$work_dir/$archive_name"

    age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "$encrypted" "$plain_backup"
    (
      cd "$work_dir"
      sha256sum "$archive_name" > "$archive_name.sha256"
    )

    # Upload the checksum first. A restore drill will reject incomplete or
    # partially uploaded archives because their checksum will not match.
    rclone copyto "$encrypted.sha256" "$BACKUP_REMOTE/$archive_name.sha256"
    rclone copyto "$encrypted" "$BACKUP_REMOTE/$archive_name"

    printf 'Encrypted backup uploaded: %s/%s\n' "$BACKUP_REMOTE" "$archive_name"
    BACKUP_REMOTE="$BACKUP_REMOTE" BACKUP_RETENTION_DAYS="$retention_days" bash "$0" prune
    ;;

  verify-latest)
    : "${BACKUP_AGE_IDENTITY_FILE:?Set BACKUP_AGE_IDENTITY_FILE to the age private identity file}"
    [[ -r "$BACKUP_AGE_IDENTITY_FILE" ]] || {
      printf 'Age identity file is not readable.\n' >&2
      exit 1
    }
    require_command age
    require_command rclone
    require_command sha256sum

    if ! rclone lsf --files-only --include '*.dump.age' "$BACKUP_REMOTE" | sort -r > "$work_dir/archive-list"; then
      printf 'Could not list off-site backups at %s.\n' "$BACKUP_REMOTE" >&2
      exit 1
    fi

    found=0
    while IFS= read -r archive_name; do
      [[ -n "$archive_name" ]] || continue
      found=1
      printf 'Testing off-site backup: %s\n' "$archive_name"

      if ! rclone copyto "$BACKUP_REMOTE/$archive_name" "$work_dir/$archive_name"; then
        printf 'Download failed; trying the previous backup.\n' >&2
        continue
      fi
      if ! rclone copyto "$BACKUP_REMOTE/$archive_name.sha256" "$work_dir/$archive_name.sha256"; then
        printf 'Checksum sidecar is missing; trying the previous backup.\n' >&2
        continue
      fi
      if ! (cd "$work_dir" && sha256sum --check "$archive_name.sha256"); then
        printf 'Checksum mismatch; trying the previous backup.\n' >&2
        continue
      fi

      plain_name="${archive_name%.age}"
      if ! age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" --output "$work_dir/$plain_name" "$work_dir/$archive_name"; then
        printf 'Decryption failed; trying the previous backup.\n' >&2
        continue
      fi
      if ! (cd "$work_dir" && sha256sum "$plain_name" > "$plain_name.sha256"); then
        printf 'Could not checksum decrypted archive.\n' >&2
        continue
      fi
      if bash scripts/verify_postgres_backup.sh "$work_dir/$plain_name"; then
        printf 'Off-site restore drill passed: %s\n' "$archive_name"
        exit 0
      fi
      printf 'Restore drill failed; trying the previous backup.\n' >&2
    done < "$work_dir/archive-list"

    if [[ "$found" -eq 0 ]]; then
      printf 'No encrypted PostgreSQL backups found at %s.\n' "$BACKUP_REMOTE" >&2
    else
      printf 'No available off-site backup passed download, checksum, decryption and restore verification.\n' >&2
    fi
    exit 1
    ;;

  prune)
    require_command rclone
    rclone delete "$BACKUP_REMOTE" --min-age "${retention_days}d" --include '*.dump.age'
    rclone delete "$BACKUP_REMOTE" --min-age "${retention_days}d" --include '*.dump.age.sha256'
    printf 'Off-site backups older than %s days pruned from %s.\n' "$retention_days" "$BACKUP_REMOTE"
    ;;

  *)
    usage >&2
    exit 2
    ;;
esac
