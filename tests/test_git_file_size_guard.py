"""Tests for the local and CI Git large-file guard."""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARD = PROJECT_ROOT / "scripts" / "check_git_file_sizes.py"


def run_git(repo, *args):
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def init_repo(path):
    run_git(path, "init", "-q")
    run_git(path, "config", "user.name", "Guard Test")
    run_git(path, "config", "user.email", "guard@example.com")


def run_guard(repo, *args):
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return subprocess.run(
        [sys.executable, str(GUARD)] + list(args),
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_staged_small_file_passes(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("small\n", encoding="utf-8")
    run_git(tmp_path, "add", "notes.txt")

    result = run_guard(tmp_path, "staged")

    assert result.returncode == 0, result.stderr


def test_staged_large_file_is_blocked(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "asset.bin").write_bytes(b"x" * 1025)
    run_git(tmp_path, "add", "asset.bin")

    result = run_guard(tmp_path, "staged", "--max-file-bytes", "1024")

    assert result.returncode == 1
    assert "oversized file: asset.bin" in result.stderr


def test_runtime_cache_path_is_blocked_even_when_small(tmp_path):
    init_repo(tmp_path)
    cache = tmp_path / "ms-playwright" / "browser.bin"
    cache.parent.mkdir()
    cache.write_bytes(b"x")
    run_git(tmp_path, "add", "ms-playwright/browser.bin")

    result = run_guard(tmp_path, "staged")

    assert result.returncode == 1
    assert "blocked path: ms-playwright/browser.bin" in result.stderr


def test_staged_total_size_is_blocked(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "one.bin").write_bytes(b"x" * 600)
    (tmp_path / "two.bin").write_bytes(b"y" * 600)
    run_git(tmp_path, "add", "one.bin", "two.bin")

    result = run_guard(
        tmp_path,
        "staged",
        "--max-file-bytes",
        "1024",
        "--max-total-bytes",
        "1000",
    )

    assert result.returncode == 1
    assert "total new content" in result.stderr


def test_range_catches_large_blob_deleted_by_later_commit(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    run_git(tmp_path, "add", "README.md")
    run_git(tmp_path, "commit", "-qm", "base")
    base = run_git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    (tmp_path / "asset.bin").write_bytes(b"x" * 1025)
    run_git(tmp_path, "add", "asset.bin")
    run_git(tmp_path, "commit", "-qm", "add asset")
    (tmp_path / "asset.bin").unlink()
    run_git(tmp_path, "add", "-u")
    run_git(tmp_path, "commit", "-qm", "remove asset")

    result = run_guard(
        tmp_path,
        "range",
        base,
        "HEAD",
        "--max-file-bytes",
        "1024",
    )

    assert result.returncode == 1
    assert "asset.bin" in result.stderr
