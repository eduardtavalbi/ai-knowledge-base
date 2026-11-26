# PostgreSQL backup and restore runbook

This runbook applies to the repository's Docker Compose deployment, where PostgreSQL is the `db` service and the application is the `api` service. Run the commands from the repository root with Docker Compose available and the deployment's `.env` file configured.

## 1. Create a backup

Run:

```bash
bash scripts/backup_postgres.sh
```

The script creates a timestamped custom-format archive under `backups/`, validates that PostgreSQL can list the archive, writes a SHA-256 checksum, and restricts local file permissions. To choose a different destination (for example, an encrypted mounted volume):

```bash
BACKUP_DIR=/secure/backup/location bash scripts/backup_postgres.sh
```

The checksum detects accidental file corruption; it does not replace encryption or an off-site copy.

- Keep backups outside the repository in production. The local `backups/` directory is only an example destination.
- Encrypt backups before transferring them to object storage or another host.
- Restrict access to the backup and checksum files; the database contains personal and potentially confidential documents.
- Define retention according to legal and contractual requirements. Do not rely on a developer workstation as the only backup location.

## 2. Verify a backup by restoring to a temporary database

Do this regularly, and before relying on a backup for disaster recovery. It does not stop the live API.

```bash
bash scripts/verify_postgres_backup.sh backups/mindbase-YYYYMMDDTHHMMSSZ.dump
```

The verifier creates a uniquely named temporary database, restores the archive with `pg_restore --exit-on-error`, checks that the Alembic migration version and application `documents` table are present, and drops the temporary database on exit (including when verification fails). It leaves the source database untouched. Before creating the temporary database, it also checks the adjacent SHA-256 file and rejects missing or modified archives.

A successful check verifies archive readability and the presence of the migrated application schema. Also perform application-level smoke checks against restored data before declaring a recovery test successful. The backend CI workflow runs these same backup and restore scripts against a disposable Compose PostgreSQL database.

## 3. Restore the live database

**Destructive operation.** Confirm the target environment and backup timestamp before running this procedure. Prefer testing the backup in a temporary database first. Ensure a recent pre-restore backup exists.

1. Put the application into maintenance mode and stop every API/worker process that writes to this database. For the Compose setup:

   ```bash
   docker compose stop api
   ```

2. Restore the archive into the configured database. `--single-transaction` makes the restore all-or-nothing if an error occurs.

   ```bash
   backup="/absolute/path/to/mindbase-backup.dump"
   test -s "$backup"

   docker compose exec -T db sh -ec \
     'pg_restore --clean --if-exists --single-transaction --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -' \
     < "$backup"
   ```

3. Start the API and verify readiness:

   ```bash
   docker compose start api
   docker compose ps
   curl --fail http://127.0.0.1:8000/ready
   ```

4. Sign in with a test account and verify document listing, opening a document, search and an AI answer. Check application logs before ending maintenance mode.

If the restore command fails, keep the application stopped until the database state has been checked. With `--single-transaction`, PostgreSQL rolls back the restore transaction on failure; inspect the error and verify the existing database before restarting writers.

## 4. Recovery notes

- PostgreSQL backups do not include the API image, environment secrets, SMTP credentials, Gemini credentials or external object storage. Back these up through their respective secure systems.
- Preserve the matching application release and Alembic migration history with each backup. Do not run a newer application against an older schema without applying its migrations.
- Restoring a database also restores its users, documents, sessions, refresh tokens, audit events and rate-limit buckets as of the backup time. Treat restored credentials and sessions as sensitive.
- Record backup time, source environment, application commit, archive checksum, restore-test result, recovery time and any data-loss window.
- Establish and test explicit RPO/RTO targets before production launch; this runbook does not itself provide continuous replication or point-in-time recovery.
