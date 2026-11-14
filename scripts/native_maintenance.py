#!/usr/bin/env python3
"""Rotate logs and retain a bounded set of private local backups."""

import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


MAX_LOG_BYTES = 20 * 1024 * 1024
LOG_KEEP = 5
BACKUP_KEEP = 7


def rotate_if_needed(path: Path, log_dir: Path) -> None:
    if not path.is_file() or path.stat().st_size <= MAX_LOG_BYTES:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived = log_dir / f"{path.name}.{stamp}.gz"
    with path.open("rb") as source, gzip.open(archived, "wb") as target:
        shutil.copyfileobj(source, target)
    with path.open("wb"):
        pass
    archived.chmod(0o600)
    archives = sorted(
        log_dir.glob(f"{path.name}.*.gz"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for kept in archives[:LOG_KEEP]:
        kept.chmod(0o600)
    for stale in archives[LOG_KEEP:]:
        stale.unlink(missing_ok=True)


def prune_backups(backup_dir: Path) -> None:
    backups = sorted(
        backup_dir.glob("cowagent-*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for kept in backups[:BACKUP_KEEP]:
        kept.chmod(0o600)
    for stale in backups[BACKUP_KEEP:]:
        stale.unlink(missing_ok=True)


def main() -> int:
    data_root = Path(os.environ.get("COW_DATA_DIR", "~/.cow")).expanduser()
    log_dir = Path(os.environ.get("COW_LOG_DIR", "~/Library/Logs/CowAgent")).expanduser()
    backup_dir = Path(os.environ.get("COW_BACKUP_DIR", "~/Backups/CowAgent")).expanduser()
    project_root = Path(__file__).resolve().parent.parent

    for directory, mode in ((log_dir, 0o700), (backup_dir, 0o700)):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(mode)

    for data_file in data_root.glob("*"):
        if data_file.is_file():
            data_file.chmod(0o600)

    for path in (
        data_root / "run.log",
        log_dir / "service.out.log",
        log_dir / "service.err.log",
        log_dir / "maintenance.out.log",
        log_dir / "maintenance.err.log",
    ):
        if path.is_file():
            path.chmod(0o600)
        rotate_if_needed(path, log_dir)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = backup_dir / f"cowagent-{stamp}.zip"
    env = os.environ.copy()
    env["COW_DATA_DIR"] = str(data_root)
    subprocess.run(
        [str(project_root / ".venv/bin/cow"), "backup", "--output", str(archive)],
        cwd=str(project_root),
        env=env,
        check=True,
    )
    archive.chmod(0o600)
    prune_backups(backup_dir)
    print(f"backup={archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
