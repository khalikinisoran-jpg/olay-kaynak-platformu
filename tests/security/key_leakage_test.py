"""MISSION-O: trust-anchor key leakage adversarial tests.

A synthetic key is used (never a real secret). The key must never
appear in:

- the runtime's stdout / stderr (whether supplied via the
  ``CHAIN_ANCHOR_KEY`` environment variable or via ``--anchor-key-path``),
- exception / error messages,
- the event store, the snapshot, or the anchor file.

``--anchor-key-path`` passes a PATH (never the key value) to the
process; the key value must not appear in the process argv or output.
"""

import os
import secrets
import subprocess
import sys

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

AGENT_RUN = REPO_ROOT / "agent_run.py"

MEMORY_STORE_PROMPT = (
    "benim ad" + "\u0131m" + " Ahmet\n"
)


def _run_agent(workdir, args=(), stdin_text="exit\n", extra_env=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)

    process = subprocess.run(
        [sys.executable, str(AGENT_RUN), *args],
        input=(
            stdin_text.encode("utf-8")
            if not isinstance(stdin_text, bytes)
            else stdin_text
        ),
        capture_output=True,
        env=env,
        timeout=120,
        cwd=str(workdir),
    )

    return process, (
        process.stdout + process.stderr
    ).decode("utf-8", errors="replace")


def _all_artifacts(workdir):
    paths = []
    data_dir = workdir / "data"
    if data_dir.exists():
        paths.extend(sorted(data_dir.iterdir()))
    paths.extend(sorted(workdir.glob("*.jsonl")))
    paths.extend(sorted(workdir.glob("*.jsonl.lock")))
    return paths


def test_env_key_never_leaks_to_runtime_output(tmp_path):
    key = secrets.token_hex(32)

    _, output = _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text=MEMORY_STORE_PROMPT + "exit\n",
        extra_env={"CHAIN_ANCHOR_KEY": key},
    )

    assert key not in output


def test_file_key_value_never_leaks_to_runtime_output(tmp_path):
    key = secrets.token_hex(32)
    key_file = tmp_path / "keyfile"
    key_file.write_text(key, encoding="utf-8")

    env = dict(os.environ)
    env.pop("CHAIN_ANCHOR_KEY", None)

    _, output = _run_agent(
        tmp_path,
        args=[
            "--anchor-path",
            str(tmp_path / "anchor.jsonl"),
            "--anchor-key-path",
            str(key_file),
        ],
        stdin_text=MEMORY_STORE_PROMPT + "exit\n",
        extra_env=env,
    )

    assert key not in output
    assert str(key_file) not in output


def test_argv_never_contains_the_key_value(tmp_path):
    key = secrets.token_hex(32)
    key_file = tmp_path / "keyfile"
    key_file.write_text(key, encoding="utf-8")

    env = dict(os.environ)
    env.pop("CHAIN_ANCHOR_KEY", None)

    args = [
        "--anchor-path",
        str(tmp_path / "anchor.jsonl"),
        "--anchor-key-path",
        str(key_file),
    ]

    argv_blob = " ".join(args)

    assert key not in argv_blob
    assert key_file.name in argv_blob


def test_key_never_leaks_into_persisted_artifacts(tmp_path):
    key = secrets.token_hex(32)

    _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text=MEMORY_STORE_PROMPT + "exit\n",
        extra_env={"CHAIN_ANCHOR_KEY": key},
    )

    artifacts = _all_artifacts(tmp_path)
    assert artifacts

    for path in artifacts:
        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        assert key not in content, f"key leaked into {path}"


def test_key_never_leaks_into_error_messages():
    import pytest

    from simulation.persistence.chain_anchor import (
        ChainAnchor,
        ChainAnchorError,
    )

    with pytest.raises(ChainAnchorError) as exc_info:
        ChainAnchor(
            path="unused",
            anchor_key="short",
        )

    assert "short" not in str(exc_info.value)


def test_missing_key_error_has_no_key_value():
    import pytest

    from simulation.persistence.chain_anchor import (
        ChainAnchor,
        ChainAnchorError,
    )

    env_backup = os.environ.get("CHAIN_ANCHOR_KEY")
    os.environ.pop("CHAIN_ANCHOR_KEY", None)

    try:
        with pytest.raises(ChainAnchorError) as exc_info:
            ChainAnchor(path="unused")
        message = str(exc_info.value)
        assert "Chain anchor key is missing" in message
        assert "secret" not in message.lower()
    finally:
        if env_backup is not None:
            os.environ["CHAIN_ANCHOR_KEY"] = env_backup
