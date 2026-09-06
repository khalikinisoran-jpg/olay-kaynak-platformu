"""Regression tests: pre-commit secret guard x staged deletions (P10.3-C).

The hook used to collect staged paths with
``git diff --cached --name-only -z`` — a list that includes staged
deletions — and passed every entry to ``scripts/secret_guard.py`` as a
filesystem path. A legitimate deletion-only commit therefore failed
closed with ``SCAN ERROR: path not found``. The hook now filters staged
deletions (``--diff-filter=ACMRT``).

These tests run the real hook inside an isolated temporary repository
(this repository's index is never touched) and prove:

A. a staged file with a synthetic secret is still blocked (rc 1);
B. a legitimate staged deletion commits cleanly (no spurious SCAN ERROR);
C. fail-closed is preserved: a path staged as added but missing from the
   working tree still produces SCAN ERROR and blocks the commit.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "githooks"
GUARD_SRC = REPO_ROOT / "scripts" / "secret_guard.py"

# Matches the guard's AWS access-key detector (AKIA + 16 [0-9A-Z]) and
# contains no FAKE_MARKERS substring, so it is reported, not suppressed.
# Assembled at runtime so this file itself never contains a full detector
# match and stays clean under repo-wide guard scans.
SYNTHETIC_SECRET = "AKIA" + "Q7W4C9N2M8B1V5X3"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True)


def _commit(repo: Path, message: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHON"] = sys.executable
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            f"core.hooksPath={HOOKS_DIR}",
            "commit",
            "-m",
            message,
        ],
        capture_output=True,
        env=env,
    )


def _out(result: subprocess.CompletedProcess) -> str:
    return (result.stdout + result.stderr).decode("utf-8", errors="replace")


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _git(repo, "init", "-q")
    assert result.returncode == 0, _out(result)
    assert _git(repo, "config", "user.name", "Guard Test").returncode == 0
    assert (
        _git(
            repo, "config", "user.email", "guard-test@example.invalid"
        ).returncode
        == 0
    )
    (repo / "scripts").mkdir()
    shutil.copyfile(GUARD_SRC, repo / "scripts" / "secret_guard.py")
    return repo


def test_case_a_staged_secret_is_still_blocked(temp_repo: Path):
    (temp_repo / "leak.txt").write_text(
        f"aws_access_key_id = {SYNTHETIC_SECRET}\n", encoding="utf-8"
    )
    assert _git(temp_repo, "add", "leak.txt").returncode == 0

    result = _commit(temp_repo, "case a: secret must block")

    assert result.returncode != 0
    assert "SECRET(S) FOUND" in _out(result)


def test_case_b_staged_deletion_commits_cleanly(temp_repo: Path):
    (temp_repo / "gone.txt").write_text("benign\n", encoding="utf-8")
    assert _git(temp_repo, "add", "gone.txt").returncode == 0
    first = _commit(temp_repo, "case b: initial commit")
    assert first.returncode == 0, _out(first)

    (temp_repo / "gone.txt").unlink()
    assert _git(temp_repo, "add", "gone.txt").returncode == 0

    result = _commit(temp_repo, "case b: deletion must not scan-error")

    assert result.returncode == 0, _out(result)
    assert "SCAN ERROR" not in _out(result)


def test_case_c_missing_scannable_path_still_fails_closed(temp_repo: Path):
    (temp_repo / "vanish.txt").write_text("benign\n", encoding="utf-8")
    assert _git(temp_repo, "add", "vanish.txt").returncode == 0
    # Remove from the working tree WITHOUT staging the deletion: the index
    # still records the file as added, so the hook must still scan it.
    (temp_repo / "vanish.txt").unlink()

    result = _commit(temp_repo, "case c: real scan error must block")

    assert result.returncode != 0
    assert "SCAN ERROR" in _out(result)
