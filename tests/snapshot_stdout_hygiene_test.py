"""Snapshot output-hygiene regression tests (frozen-boundary exception).

Contract: the automatic snapshot notice is a human-only diagnostic.
It is emitted to stderr ONLY when stderr is an interactive TTY; every
machine-readable surface stays silent:

- Claude Code PreToolUse hook stdout: exactly one decision JSON
- tanuq CLI ``--json`` stdout: directly ``json.loads``-able
- captured/piped stderr (e.g. P5/P6 structured log capture): untouched
- stdout: never receives the notice in any scenario
"""
import io
import json
import sys

from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager

SNAPSHOT_NOTICE = "Otomatik snapshot alindi"


class _StdinWithBuffer:

    def __init__(self, data: str):
        self.buffer = io.BytesIO(data.encode("utf-8"))


def _feed_stdin(monkeypatch, data: str):
    monkeypatch.setattr(sys, "stdin", _StdinWithBuffer(data))


class _FakeStderr(io.StringIO):
    """Deterministic stderr double with controllable isatty()."""

    def __init__(self, isatty: bool):
        super().__init__()
        self._isatty = isatty
        self.buffer = io.BytesIO()

    def isatty(self):
        return self._isatty


def _make_manager(tmp_path):
    return SnapshotManager(
        snapshot_store=SnapshotStore(path=tmp_path / "snapshot.json")
    )


# ---- A) notice channel gating: TTY vs non-TTY, stdout always clean ----


def test_notice_reaches_stderr_only_on_real_tty(tmp_path, monkeypatch, capsys):
    fake = _FakeStderr(isatty=True)
    monkeypatch.setattr(sys, "stderr", fake)
    manager = _make_manager(tmp_path)
    manager.event_applied()
    manager.event_applied()
    manager.save_snapshot(state={"k": "v"}, last_sequence=2)
    captured = capsys.readouterr()
    assert captured.out == ""          # stdout machine contract: silent
    assert SNAPSHOT_NOTICE in fake.getvalue()
    assert "Event sayisi: 2" in fake.getvalue()
    assert captured.err == ""          # real stderr untouched in test


def test_notice_is_silent_on_non_tty_capture(tmp_path, monkeypatch, capsys):
    """Hook/CLI/server log-capture scenario: stderr is a pipe or an
    in-memory capture — the notice must not be emitted at all."""
    fake = _FakeStderr(isatty=False)
    monkeypatch.setattr(sys, "stderr", fake)
    manager = _make_manager(tmp_path)
    manager.event_applied()
    manager.event_applied()
    manager.save_snapshot(state={"k": "v"}, last_sequence=2)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert fake.getvalue() == ""
    assert fake.buffer.getvalue() == b""
    assert captured.err == ""


def test_unicode_fallback_writes_stderr_buffer_on_tty(
        tmp_path, monkeypatch):
    """Regression for the UnicodeEncodeError fallback branch (TTY
    scenario only): the replacement-encoded notice must land on
    stderr.buffer, never on stdout."""

    class _EncodeBrokenTtyStderr(_FakeStderr):

        def write(self, text):
            raise UnicodeEncodeError(
                "cp1252", SNAPSHOT_NOTICE, 0, 1, "character maps to <undefined>"
            )

    broken = _EncodeBrokenTtyStderr(isatty=True)
    monkeypatch.setattr(sys, "stderr", broken)
    manager = _make_manager(tmp_path)
    manager.event_applied()
    manager.event_applied()
    manager.save_snapshot(state={"k": "v"}, last_sequence=2)
    payload = broken.buffer.getvalue().decode("utf-8")
    assert SNAPSHOT_NOTICE in payload
    assert "Event sayisi: 2" in payload


# ---- B) Claude Code hook: stdout is exactly one decision JSON ----


def _hook_payload(ws, old, new):
    return json.dumps({
        "session_id": "sess-123",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(ws / "demo.txt"),
            "old_string": old,
            "new_string": new,
        },
    })


def test_hook_stdout_is_single_parseable_decision_json(
        tmp_path, monkeypatch, capsys):
    """Real propose -> execute hook flow: stdout must parse as exactly
    one PreToolUse decision JSON object with no snapshot notices (the
    hook and its captures are never a TTY)."""
    from tanuq.claude_code_adapter import main as adapter_main
    from tanuq.config import init_workspace
    from tanuq.runtime import load_environment

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    monkeypatch.chdir(ws)
    init_workspace(ws)
    load_environment(ws)
    capsys.readouterr()  # drain init/banner noise

    # two governed VERIFIED flows dispatch multiple evidence events;
    # with interval=2 automatic snapshots fire inside the loop
    edits = [("hello", "hello fixed"), ("hello fixed", "hello fixed v2")]
    for old, new in edits:
        _feed_stdin(monkeypatch, _hook_payload(ws, old, new))
        assert adapter_main() == 0
        captured = capsys.readouterr()
        decision = json.loads(captured.out)  # must be a single JSON object
        assert decision["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert SNAPSHOT_NOTICE not in captured.out
        assert SNAPSHOT_NOTICE not in captured.err
    assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello fixed v2"


# ---- C) CLI --json: stdout parses directly as JSON ----


def test_cli_propose_json_stdout_is_directly_parseable(
        tmp_path, monkeypatch, capsys):
    from tanuq import cli

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    assert cli.main(["init", "--workspace", str(ws), "--yes"]) == 0
    capsys.readouterr()

    payload = {
        "path": str(ws / "demo.txt"),
        "action": "modify",
        "reason": "stdout hygiene",
        "old_content": "hello",
        "new_content": "hello fixed",
    }
    # two proposes: automatic snapshots fire across the interval, yet
    # the machine-readable output must stay clean throughout
    for _ in range(2):
        _feed_stdin(monkeypatch, json.dumps(payload))
        assert cli.main([
            "propose",
            "--workspace", str(ws),
            "--stdin-json",
            "--json",
        ]) == 0
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert isinstance(report, dict)
        assert SNAPSHOT_NOTICE not in captured.out
        assert SNAPSHOT_NOTICE not in captured.err
