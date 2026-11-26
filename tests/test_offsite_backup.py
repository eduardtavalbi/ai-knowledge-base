from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "offsite_postgres_backup.sh"


def install_fake_tools(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    remote_root = tmp_path / "remote"
    remote_root.mkdir()

    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -eu
args="$*"
case "$args" in
  *pg_dump*) printf 'fake-postgres-archive' ;;
  *'SELECT version_num'*) printf 'abc123\\n' ;;
  *to_regclass*) printf 't\\n' ;;
esac
exit 0
"""
    )

    age = bin_dir / "age"
    age.write_text(
        """#!/usr/bin/env bash
set -eu
output=''
input=''
while (($#)); do
  if [[ "$1" == '--output' ]]; then
    output="$2"
    shift 2
  else
    input="$1"
    shift
  fi
done
test -n "$output" && test -n "$input"
cp "$input" "$output"
"""
    )

    rclone = bin_dir / "rclone"
    rclone.write_text(
        """#!/usr/bin/env bash
set -eu
remote_root="${RCLONE_TEST_REMOTE_ROOT:?}"
remote_path() {
  printf '%s/%s' "$remote_root" "${1#testremote:}"
}
case "$1" in
  copyto)
    source="$2"
    destination="$3"
    if [[ "$source" == testremote:* ]]; then
      cp "$(remote_path "$source")" "$destination"
    elif [[ "$destination" == testremote:* ]]; then
      target="$(remote_path "$destination")"
      mkdir -p "$(dirname "$target")"
      cp "$source" "$target"
    else
      exit 2
    fi
    ;;
  lsf)
    target="$(remote_path "${@: -1}")"
    find "$target" -maxdepth 1 -type f -name '*.dump.age' -printf '%f\\n' | sort
    ;;
  delete)
    exit 0
    ;;
  *)
    exit 2
    ;;
esac
"""
    )

    for tool in (docker, age, rclone):
        tool.chmod(0o755)
    return bin_dir, remote_root


def run_script(args: list[str], env: dict[str, str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_offsite_backup_upload_and_restore_drill(tmp_path: Path) -> None:
    bin_dir, remote_root = install_fake_tools(tmp_path)
    identity = tmp_path / "age-identity.txt"
    identity.write_text("AGE-SECRET-KEY-1FAKE\n")
    identity.chmod(0o600)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "RCLONE_TEST_REMOTE_ROOT": str(remote_root),
            "BACKUP_REMOTE": "testremote:bucket",
            "BACKUP_AGE_RECIPIENT": "age1fakepublicrecipient",
            "BACKUP_AGE_IDENTITY_FILE": str(identity),
            "BACKUP_RETENTION_DAYS": "30",
            "POSTGRES_PASSWORD": "test-password",
            "AUTH_SECRET_KEY": "test-auth-secret-key-that-is-long-enough",
        }
    )

    backup = run_script(["backup"], env)
    assert backup.returncode == 0, backup.stderr
    archives = list((remote_root / "bucket").glob("*.dump.age"))
    assert len(archives) == 1
    archive = archives[0]
    assert archive.read_bytes() == b"fake-postgres-archive"
    assert Path(f"{archive}.sha256").is_file()
    assert not list((remote_root / "bucket").glob("*.dump"))

    drill = run_script(["verify-latest"], env)
    assert drill.returncode == 0, drill.stdout + drill.stderr
    assert "Restore verified:" in drill.stdout
    assert "Off-site restore drill passed:" in drill.stdout


def test_offsite_backup_rejects_missing_remote_and_invalid_retention() -> None:
    env = os.environ.copy()
    env.pop("BACKUP_REMOTE", None)
    missing_remote = run_script(["prune"], env)
    assert missing_remote.returncode == 2
    assert "BACKUP_REMOTE" in missing_remote.stderr

    env["BACKUP_REMOTE"] = "remote:bucket"
    env["BACKUP_RETENTION_DAYS"] = "0"
    invalid_retention = run_script(["prune"], env)
    assert invalid_retention.returncode == 2
    assert "positive integer" in invalid_retention.stderr


def test_restore_drill_requires_private_identity(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["BACKUP_REMOTE"] = "remote:bucket"
    env.pop("BACKUP_AGE_IDENTITY_FILE", None)
    result = run_script(["verify-latest"], env)
    assert result.returncode != 0
    assert "BACKUP_AGE_IDENTITY_FILE" in result.stderr
