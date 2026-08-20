"""MISSION-N.1: real-runtime anchored integration tests.

These tests execute the SHIPPED entry point ``agent_run.py`` as a real
subprocess with an isolated temporary working directory (so its default
``data/`` layout is fresh), a synthetic anchor key, and byte-safe UTF-8
stdin. They prove the production call chain

    agent_run.py -> Kernel -> EventStore -> ChainAnchor -> Recovery

end to end:

- an anchored runtime creates events AND anchor records for them;
- tail deletion of the anchored event log fails closed on the next
  start (rc != 0, "trust anchor" error);
- the default UNANCHORED runtime prints an explicit warning and would
  silently accept the truncated history (the documented adoption gap),
  which is why production is directed to ``--anchor-path``.

No real secret is used; the key is ``secrets.token_hex(32)``.
"""

import json
import os
import secrets
import subprocess
import sys

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

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

    output = (
        process.stdout + process.stderr
    ).decode("utf-8", errors="replace")

    return process.returncode, output


def _events(workdir):
    path = workdir / "data" / "events.jsonl"
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _anchor_lines(workdir):
    path = workdir / "anchor.jsonl"
    if not path.exists():
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_anchored_runtime_creates_events_and_anchor(tmp_path):
    key = secrets.token_hex(32)

    rc, output = _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text=MEMORY_STORE_PROMPT + "exit\n",
        extra_env={"CHAIN_ANCHOR_KEY": key},
    )

    assert rc == 0
    assert "ANCHORED" in output

    events = _events(tmp_path)
    assert len(events) == 3

    types = [json.loads(line)["event_type"] for line in events]
    assert "MemoryStored" in types

    anchors = _anchor_lines(tmp_path)
    assert len(anchors) == 3
    assert json.loads(anchors[-1])["sequence"] == 3


def test_anchored_runtime_fails_closed_on_tail_deletion(tmp_path):
    key = secrets.token_hex(32)

    rc, _ = _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text=MEMORY_STORE_PROMPT + "exit\n",
        extra_env={"CHAIN_ANCHOR_KEY": key},
    )
    assert rc == 0

    events = _events(tmp_path)
    assert events

    events_path = tmp_path / "data" / "events.jsonl"
    events_path.write_text(
        "\n".join(events[:-1]) + "\n",
        encoding="utf-8",
    )

    rc2, output2 = _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text="exit\n",
        extra_env={"CHAIN_ANCHOR_KEY": key},
    )

    assert rc2 != 0
    assert "anchor" in output2.lower()
    assert "verification failed" in output2.lower()


def test_anchored_runtime_fails_closed_on_missing_key(tmp_path):
    rc, output = _run_agent(
        tmp_path,
        args=["--anchor-path", str(tmp_path / "anchor.jsonl")],
        stdin_text="exit\n",
    )

    assert rc != 0
    assert "Chain anchor key is missing" in output


def test_unanchored_runtime_prints_adoption_warning(tmp_path):
    rc, output = _run_agent(tmp_path, stdin_text="exit\n")

    assert rc == 0
    assert "UNANCHORED" in output
    assert "--anchor-path" in output
