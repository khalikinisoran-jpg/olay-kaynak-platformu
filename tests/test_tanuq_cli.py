"""Tanuq product-shell smoke tests.

These tests cover ONLY the tanuq/ shell (config, pending store, CLI)
wired over the real governed pipeline. The security core itself is
covered by the existing T01-T21 / A01-A75 corpus and is intentionally
not re-tested here.
"""
import io
import json

import pytest

from tanuq import cli
from tanuq.config import (
    tanuq_data_dir,
    init_workspace,
    key_path_for,
    load_config,
)
from tanuq.pending import load_pending


class _StdinWithBuffer:

    def __init__(self, data: str):
        self.buffer = io.BytesIO(data.encode("utf-8"))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep the device registry (~/.tanuq) out of the real user home."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    yield


@pytest.fixture
def workspace(tmp_path, monkeypatch, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    assert cli.main(["init", "--workspace", str(ws), "--yes"]) == 0
    capsys.readouterr()
    return ws


def _feed_proposal(ws, monkeypatch, payload):
    monkeypatch.setattr(
        "sys.stdin",
        _StdinWithBuffer(json.dumps(payload)),
    )
    return cli.main([
        "propose",
        "--workspace", str(ws),
        "--stdin-json",
        "--json",
    ])


def test_init_creates_config_and_anchor_key_outside_repo(workspace, tmp_path):
    config = load_config(workspace)
    assert config.verification_depth == "compile+tests"
    assert config.allowed_paths == (str(workspace.resolve()),)
    key_path = key_path_for(workspace)
    assert key_path.exists()
    assert key_path.is_relative_to(tmp_path.home())
    assert not key_path.is_relative_to(workspace)
    assert (tanuq_data_dir(workspace) / "events.jsonl").exists()
    assert key_path_for(workspace).read_bytes().strip() != b""


def test_init_rejects_scope_outside_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(Exception, match="Tighten-only"):
        init_workspace(ws, allowed_paths=(str(outside),))


def test_low_risk_proposal_executes_and_verifies(workspace, capsys):
    ws = workspace
    target = ws / "demo.txt"
    exit_code = _feed_proposal(ws, pytest.MonkeyPatch(), {
        "path": str(target),
        "action": "modify",
        "reason": "test",
        "old_content": "hello",
        "new_content": "hello fixed",
    })
    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"state": "PROPOSED"' in out
    assert '"risk": "LOW"' in out
    assert cli.main(["execute", "--workspace", str(ws)]) == 0
    assert target.read_text(encoding="utf-8") == "hello fixed"
    assert load_pending(ws) == []


def test_high_risk_requires_approval_and_is_single_use(workspace, capsys):
    ws = workspace
    target = ws / "demo.txt"
    _feed_proposal(ws, pytest.MonkeyPatch(), {
        "path": str(target),
        "action": "modify",
        "reason": "cli apply",
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
    })
    capsys.readouterr()
    assert cli.main(["execute", "--workspace", str(ws)]) == 1
    out = capsys.readouterr().out
    assert "terminal state: DENIED" in out
    assert "tanuq approve" in out
    assert target.read_text(encoding="utf-8") == "hello"
    assert cli.main(["approve", "--workspace", str(ws)]) == 0
    capsys.readouterr()
    assert cli.main(["execute", "--workspace", str(ws)]) == 0
    assert "sk-test-aaaaaaaaaaaaaaaa" in target.read_text(encoding="utf-8")
    capsys.readouterr()
    payload = {
        "path": str(target),
        "action": "modify",
        "reason": "cli apply",
        "old_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "new_content": "hello\n",
    }
    _feed_proposal(ws, pytest.MonkeyPatch(), payload)
    capsys.readouterr()
    assert cli.main(["execute", "--workspace", str(ws)]) == 0
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_out_of_scope_proposal_denied_and_removed(workspace, capsys):
    ws = workspace
    outside = ws.parent / "outside.txt"
    outside.write_text("hello", encoding="utf-8", newline="")
    exit_code = _feed_proposal(ws, pytest.MonkeyPatch(), {
        "path": str(outside),
        "action": "modify",
        "reason": "escape",
        "old_content": "hello",
        "new_content": "hello fixed",
    })
    assert exit_code == 1
    out = capsys.readouterr().out
    assert '"state": "DENIED"' in out
    assert load_pending(ws) == []
    assert outside.read_text(encoding="utf-8") == "hello"


def test_verification_failure_rolls_back(workspace, capsys):
    ws = workspace
    target = ws / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8", newline="")
    _feed_proposal(ws, pytest.MonkeyPatch(), {
        "path": str(target),
        "action": "modify",
        "reason": "breaking",
        "old_content": "x = 1\n",
        "new_content": "x = 1\ndef broken(:\n",
    })
    capsys.readouterr()
    assert cli.main(["execute", "--workspace", str(ws)]) == 1
    out = capsys.readouterr().out
    assert "terminal state: ROLLED_BACK" in out
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_verify_reports_valid_chain(workspace, capsys):
    ws = workspace
    assert cli.main(["verify", "--workspace", str(ws)]) == 0
    out = capsys.readouterr().out
    assert "Evidence chain:  VALID" in out
    assert "Anchor:          ACTIVE" in out


def test_execute_uses_coordinator_delegation(workspace, capsys, monkeypatch):
    """Faz 2b: CLI execute must route through OperationCoordinator."""
    from tanuq.coordinator import OperationCoordinator

    _feed_proposal(workspace, monkeypatch, {
        "path": str(workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello v2",
        "reason": "delegation probe",
    })
    calls = {}
    sentinel = {"executed": True, "terminal": "FAKE_TERMINAL",
                "failure_stage": "", "apply_success": True,
                "verification_passed": True, "patches": []}

    class FakeCoordinator:
        def __init__(self, env):
            calls["env_is_same"] = env is not None
        def execute(self, fingerprint=None, run_all=False, session=None):
            calls["fingerprint"] = fingerprint
            calls["run_all"] = run_all
            calls["session"] = session
            return sentinel

    monkeypatch.setattr(
        "tanuq.coordinator.OperationCoordinator", FakeCoordinator
    )
    exit_code = cli.main(["execute", "--workspace", str(workspace)])
    assert exit_code == 1  # FAKE_TERMINAL is not a verified state
    assert calls["env_is_same"] is True
    assert calls["run_all"] is False
    assert calls["session"] is None
    out = capsys.readouterr().out
    assert "terminal state: FAKE_TERMINAL" in out


def test_execute_cli_cannot_bypass_governance(workspace, capsys, monkeypatch):
    """Onaysiz HIGH proposal: CLI -> coordinator -> DENIED (approval)."""
    _feed_proposal(workspace, monkeypatch, {
        "path": str(workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })
    assert cli.main(["execute", "--workspace", str(workspace)]) == 1
    out = capsys.readouterr().out
    assert "terminal state: DENIED" in out
    assert (workspace / "demo.txt").read_text(encoding="utf-8") == "hello"
