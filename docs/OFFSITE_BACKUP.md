# Encrypted off-site PostgreSQL backups

This runbook adds client-side encryption and an off-site copy to the local Compose backup in [POSTGRES_BACKUP_RESTORE.md](POSTGRES_BACKUP_RESTORE.md). It uses [age](https://age-encryption.org/) for encryption and [rclone](https://rclone.org/) for storage transport. rclone supports S3-compatible object storage and other providers; no provider credentials or encryption private keys belong in this repository.

## Security model

- PostgreSQL is dumped locally using the existing custom-format backup script.
- The archive is encrypted with an age public recipient before upload. Only holders of the matching private identity can decrypt it.
- The SHA-256 sidecar covers the encrypted object and detects incomplete or corrupted transfers. It is not an authenticity signature; protect the storage account and rclone configuration.
- Configure `BACKUP_REMOTE` to a bucket/path or other rclone remote that is independent of the database host and its failure domain.
- Keep the age identity and rclone credentials outside the repository, readable only by the backup/restore operator. Use a separate least-privilege storage identity where the provider supports it.

## One-time host setup

Install Docker Compose, age and rclone on the host that can reach the production Compose database. Ensure the temporary staging directory used for plaintext dumps is on an encrypted filesystem or ephemeral storage; removing temporary files is not a secure-erasure guarantee. Generate an age key pair:

```bash
sudo install -d -o mindbase -g mindbase -m 0700 /etc/mindbase
sudo -u mindbase age-keygen -o /etc/mindbase/backup-age-identity.txt
sudo chmod 0600 /etc/mindbase/backup-age-identity.txt
sudo age-keygen -y /etc/mindbase/backup-age-identity.txt
```

The final command prints the public recipient. Store that value as `BACKUP_AGE_RECIPIENT`; keep the identity file private. Configure an rclone remote as the `mindbase` service user (or explicitly set `RCLONE_CONFIG` to its protected config), and make the config readable only by that account (for example, owner `mindbase`, mode 0600). Do not commit either file.

Create a root-owned environment file such as `/etc/mindbase/offsite-backup.env`:

```dotenv
BACKUP_REMOTE=remote-name:mindbase-production
BACKUP_AGE_RECIPIENT=age1...
BACKUP_AGE_IDENTITY_FILE=/etc/mindbase/backup-age-identity.txt
BACKUP_RETENTION_DAYS=30
RCLONE_CONFIG=/etc/rclone/rclone.conf
```

Keep this environment file root-owned with mode 0600; systemd reads it before starting the service. The age recipient is public, but the remote name and config location should still be controlled. The private identity and provider credentials must never be placed in this file as inline values.

## Operations

Create, encrypt, checksum and upload a backup:

```bash
set -a
. /etc/mindbase/offsite-backup.env
set +a
cd /opt/mindbase
bash scripts/offsite_postgres_backup.sh backup
```

The script uploads the checksum sidecar before the encrypted archive. It prunes objects older than `BACKUP_RETENTION_DAYS` only after the new upload succeeds. The default retention is 30 days; choose a value that satisfies legal, contractual and recovery requirements.

Run a complete off-site restore drill:

```bash
bash scripts/offsite_postgres_backup.sh verify-latest
```

The drill downloads the newest archive, verifies its checksum, decrypts it, then invokes the existing verifier to restore into a uniquely named temporary PostgreSQL database and check the migration version and application schema. It does not replace the live database. It tries older archives if the newest object is missing, corrupt, undecryptable or fails restore verification.

Prune expired objects manually if needed:

```bash
bash scripts/offsite_postgres_backup.sh prune
```

## Scheduling and recovery objectives

The repository includes systemd units for a six-hour backup cadence and a daily restore drill. Adjust the service account, repository path and environment-file path if your host differs:

```bash
sudo install -m 0644 deploy/systemd/mindbase-offsite-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/mindbase-offsite-backup.timer /etc/systemd/system/
sudo install -m 0644 deploy/systemd/mindbase-offsite-restore-drill.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/mindbase-offsite-restore-drill.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mindbase-offsite-backup.timer mindbase-offsite-restore-drill.timer
systemctl list-timers 'mindbase-offsite-*'
```

The `mindbase` service account must be able to use Docker (typically via the `docker` group), read the age identity and rclone config, and execute the repository scripts. Treat Docker group membership as root-equivalent. Inspect runs with `journalctl -u mindbase-offsite-backup.service` and `journalctl -u mindbase-offsite-restore-drill.service`. Connect non-zero exits to operational alerting; a timer without monitoring is not an operational guarantee.

A six-hour backup interval is a **proposed RPO target**, not a measured guarantee: actual data loss can exceed it when a run fails or upload is delayed. Measure the end-to-end restore drill, including provisioning, download, decryption, database restore and application smoke checks, before publishing an RTO. Record backup timestamp, source commit, checksum, restore duration and result for each drill. Test key recovery separately and maintain a protected, independently recoverable copy of the age identity; losing it makes client-side encrypted backups unrecoverable.

The restore verifier validates the PostgreSQL archive and schema in a temporary database on the configured Compose PostgreSQL service. A production recovery exercise should additionally validate representative application reads and search against restored data, and should be performed in an isolated recovery environment before declaring a disaster-recovery RTO achieved.

## Limitations

- This is scheduled logical backup, not continuous WAL archiving or point-in-time recovery.
- Retention is age-based and applies to encrypted archives and checksum sidecars. It is not an immutable/WORM policy; enable object lock/versioning at the provider if required.
- rclone remote configuration and credentials are deployment-specific. Validate provider lifecycle, versioning, encryption-at-rest and access policies independently.
- Backups contain personal documents, account records and session data. Treat both encrypted objects and the decryption identity as production secrets.
