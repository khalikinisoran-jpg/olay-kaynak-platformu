"""FAZ 2.1 — telemetry opt-out / user-config contract (no network).

Contract under test:
- preference resolution: valid ENV > user config > DEFAULT ON
- invalid ENV is ignored deterministically (typo can never override
  an explicit config choice)
- config is honored only for real booleans; corrupt file -> default
- CLI: `tanuq usage on|off|status` (bare `usage` == status), exit 0
- NO network calls anywhere in FAZ 2.1 (transport = FAZ 2.2)
- governance isolation: new code never touches pipeline/authority
- privacy: status/commands print counts and flags only — never
  workspace paths, usernames, emails, secrets or identifiers
"""
import json
import os
import re
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest

import tanuq.config as tconfig

REPO = Path(__file__).resolve().parents[1]
BANNED_GOVERNANCE = (
    "WorkerActionPipeline",
    "GovernanceEvaluator",
    "FileApplier",
    "ApprovalStore",
    "authorize_apply",
    "RiskEngine",
    "RiskPolicy",
)


def _pref(env=None, config_path=None):
    return tconfig.read_usage_remote_preference(
        {} if env is None else env, config_path=config_path
    )


def _write_cfg(tmp_path, payload, name="user-config.json"):
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1-6: preference resolution
# ---------------------------------------------------------------------------

def test_default_is_on_without_config_and_env(tmp_path):
    assert _pref(env={}, config_path=tmp_path / "missing.json") == (
        True, "default",
    )


@pytest.mark.parametrize("raw, expected", [
    ("off", False), ("OFF", False), ("false", False), ("0", False),
    ("no", False), (" OFF ", False),
    ("on", True), ("ON", True), ("true", True), ("1", True),
    ("yes", True), (" Yes", True),
])
def test_env_values_accepted(tmp_path, raw, expected):
    env = {tconfig.USAGE_ENV_VAR: raw}
    enabled, source = _pref(env=env, config_path=tmp_path / "missing.json")
    assert (enabled, source) == (expected, "env")


def test_config_off_and_on(tmp_path):
    off = _write_cfg(tmp_path, {"usage_remote": False}, "off.json")
    on = _write_cfg(tmp_path, {"usage_remote": True}, "on.json")
    assert _pref(env={}, config_path=off) == (False, "config")
    assert _pref(env={}, config_path=on) == (True, "config")


def test_env_off_beats_config_on(tmp_path):
    cfg = _write_cfg(tmp_path, {"usage_remote": True})
    env = {tconfig.USAGE_ENV_VAR: "off"}
    assert _pref(env=env, config_path=cfg) == (False, "env")


def test_env_on_beats_config_off(tmp_path):
    cfg = _write_cfg(tmp_path, {"usage_remote": False})
    env = {tconfig.USAGE_ENV_VAR: "on"}
    assert _pref(env=env, config_path=cfg) == (True, "env")


def test_invalid_env_is_ignored_deterministically(tmp_path):
    # garbage env + no config -> DEFAULT ON (invalid treated as unset)
    env = {tconfig.USAGE_ENV_VAR: "garbage"}
    assert _pref(env=env, config_path=tmp_path / "missing.json") == (
        True, "default",
    )
    # garbage env must NOT override an explicit config OFF
    cfg = _write_cfg(tmp_path, {"usage_remote": False})
    assert _pref(env=env, config_path=cfg) == (False, "config")
    # empty/whitespace env -> also unset
    for raw in ("", "   "):
        env = {tconfig.USAGE_ENV_VAR: raw}
        assert _pref(env=env, config_path=cfg) == (False, "config")


def test_invalid_config_falls_back_to_default(tmp_path):
    corrupt = _write_cfg(tmp_path, "{not json", "bad.json")
    assert _pref(env={}, config_path=corrupt) == (True, "default")
    wrong_type = _write_cfg(tmp_path, {"usage_remote": "yes"}, "type.json")
    assert _pref(env={}, config_path=wrong_type) == (True, "default")
    not_object = _write_cfg(tmp_path, "[1, 2]", "arr.json")
    assert _pref(env={}, config_path=not_object) == (True, "default")


def test_endpoint_presence_check_never_returns_value(tmp_path):
    cfg = _write_cfg(tmp_path, {"usage_endpoint": "https://example.invalid/x"})
    assert tconfig.is_usage_endpoint_configured(config_path=cfg) is True
    assert tconfig.is_usage_endpoint_configured(
        env={}, config_path=tmp_path / "missing.json") is False
    env = {tconfig.USAGE_ENDPOINT_ENV_VAR: "  "}
    assert tconfig.is_usage_endpoint_configured(
        env=env, config_path=tmp_path / "missing.json") is False


def test_write_preference_is_atomic_boolean_only(tmp_path):
    cfg = tmp_path / "user-config.json"
    cfg.write_text(json.dumps({"keep_me": 42}), encoding="utf-8")
    enabled, source = tconfig.write_usage_remote_preference(False, cfg)
    assert (enabled, source) == (False, "config")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data == {"keep_me": 42, "usage_remote": False}
    tconfig.write_usage_remote_preference(True, cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["usage_remote"] is True
    assert not (tmp_path / "user-config.tmp").exists()


# ---------------------------------------------------------------------------
# 7: NO NETWORK (FAZ 2.1)
# ---------------------------------------------------------------------------

def test_no_network_calls_anywhere(tmp_path, monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise AssertionError("network call attempted in FAZ 2.1")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)

    cfg = _write_cfg(tmp_path, {"usage_remote": False})
    assert _pref(env={}, config_path=cfg) == (False, "config")
    tconfig.write_usage_remote_preference(True, cfg)
    tconfig.is_usage_endpoint_configured(config_path=cfg)

    # ISOLATION: the CLI commands resolve ~/.tanuq via Path.home()
    # (USERPROFILE on Windows / HOME on POSIX). Point both into tmp so
    # `usage on/off` can never write the real user config.
    home = tmp_path / "isolated-home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))

    args = types.SimpleNamespace()
    from tanuq.cli import cmd_usage_off, cmd_usage_on, cmd_usage_status
    assert cmd_usage_on(args) == 0
    assert cmd_usage_off(args) == 0
    assert cmd_usage_status(args) == 0
    # proof: the write landed inside the isolated home only
    written = json.loads(
        (home / ".tanuq" / "config.json").read_text(encoding="utf-8")
    )
    assert written == {"usage_remote": False}
    out = capsys.readouterr()
    assert out.err == ""

    # no network modules in the config module source
    cfg_src = Path(tconfig.__file__).read_text(encoding="utf-8")
    assert "import socket" not in cfg_src
    assert "requests" not in cfg_src
    assert "urlopen" not in cfg_src


# ---------------------------------------------------------------------------
# 8 + 9: CLI behavior and exit codes
# ---------------------------------------------------------------------------

def _run_cli(home, *cli_args, extra_env=None):
    env = dict(os.environ)
    env["USERPROFILE"] = str(home)  # isolated home (Windows Path.home)
    env["HOME"] = str(home)
    env.pop(tconfig.USAGE_ENV_VAR, None)
    env.pop(tconfig.USAGE_ENDPOINT_ENV_VAR, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "tanuq", *cli_args],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=180,
    )


def test_cli_status_on_off_flow(tmp_path):
    home = tmp_path / "privmarker-home"
    home.mkdir()

    # default
    run = _run_cli(home, "usage", "status")
    assert run.returncode == 0, run.stderr
    assert "usage remote: ON (source: default)" in run.stdout
    assert "endpoint configured: no" in run.stdout
    assert "local signals recorded: 0" in run.stdout
    assert "network: none in this build" in run.stdout

    # off persists to user config
    run = _run_cli(home, "usage", "off")
    assert run.returncode == 0, run.stderr
    assert "OFF (source: config)" in run.stdout
    cfg = json.loads((home / ".tanuq" / "config.json").read_text(
        encoding="utf-8"))
    assert cfg == {"usage_remote": False}  # boolean only, no user data

    run = _run_cli(home, "usage", "status")
    assert run.returncode == 0
    assert "OFF (source: config)" in run.stdout

    # on persists
    run = _run_cli(home, "usage", "on")
    assert run.returncode == 0
    assert "ON (source: config)" in run.stdout
    run = _run_cli(home, "usage", "status")
    assert "ON (source: config)" in run.stdout

    # bare `usage` behaves like status
    run = _run_cli(home, "usage")
    assert run.returncode == 0
    assert "usage remote: ON (source: config)" in run.stdout

    # env still wins over config at CLI level
    run = _run_cli(home, "usage", "status", extra_env={
        tconfig.USAGE_ENV_VAR: "off"})
    assert run.returncode == 0
    assert "OFF (source: env)" in run.stdout

    # invalid env at CLI level -> deterministic default/config fallback
    run = _run_cli(home, "usage", "status", extra_env={
        tconfig.USAGE_ENV_VAR: "garbage"})
    assert run.returncode == 0
    assert "ON (source: config)" in run.stdout


def test_cli_exit_codes_are_zero(tmp_path):
    home = tmp_path / "exit-home"
    home.mkdir()
    for args in (("usage", "status"), ("usage", "on"), ("usage", "off")):
        run = _run_cli(home, *args)
        assert run.returncode == 0, (args, run.returncode, run.stderr)


# ---------------------------------------------------------------------------
# 10: governance isolation
# ---------------------------------------------------------------------------

def test_governance_isolation():
    cfg_src = Path(tconfig.__file__).read_text(encoding="utf-8")
    usage_region = cfg_src[cfg_src.index("USAGE_ENV_VAR"):]
    for symbol in BANNED_GOVERNANCE:
        assert symbol not in usage_region, symbol
    assert "from simulation.agent" not in usage_region

    cli_src = (REPO / "tanuq" / "cli.py").read_text(encoding="utf-8")
    # slice the usage command block up to build_parser: the commands
    # themselves must stay free of governance execution symbols
    usage_cli = cli_src[cli_src.index("def cmd_usage_on"):]
    usage_cli = usage_cli.split("def build_parser", 1)[0]
    for symbol in BANNED_GOVERNANCE:
        assert symbol not in usage_cli, symbol

    # simulation must not know about the preference at all
    for path in (REPO / "simulation").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("usage_remote", "TANUQ_USAGE", "usage_signal",
                       "cmd_usage"):
            assert marker not in text, f"{path}: {marker}"

    # usage_signal does not depend on the CLI (no reverse dependency)
    us_src = (REPO / "tanuq" / "usage_signal.py").read_text(encoding="utf-8")
    assert "tanuq.cli" not in us_src


# ---------------------------------------------------------------------------
# 11: PRIVACY
# ---------------------------------------------------------------------------

def test_status_output_contains_no_user_data(tmp_path):
    home = tmp_path / "privmarker-home"
    home.mkdir()
    run = _run_cli(home, "usage", "status")
    assert run.returncode == 0
    blob = (run.stdout + run.stderr)
    low = blob.lower()
    # privacy marker: the isolated home path must never be printed
    assert "privmarker" not in low
    for banned in ("secret", "fingerprint", "task_id", "intent_id",
                   "workspace", "@", ".tanuq/"):
        assert banned not in low, f"privacy leak in status output: {banned}"
    # numbers/flags only: every printed line matches the contract
    for line in run.stdout.splitlines():
        assert re.match(
            r"^(usage remote: (ON|OFF) \(source: (default|config|env)\)|"
            r"endpoint configured: (yes|no)|"
            r"local signals recorded: \d+ \(state: (saved|absent)\)|"
            r"network: none in this build \(remote transport = FAZ 2\.2\))$",
            line,
        ), f"unexpected status line: {line!r}"


def test_write_preference_stores_no_user_data(tmp_path):
    home = tmp_path / "clean-home"
    home.mkdir()
    assert _run_cli(home, "usage", "off").returncode == 0
    cfg_path = home / ".tanuq" / "config.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert set(data) == {"usage_remote"}
    assert isinstance(data["usage_remote"], bool)
    blob = json.dumps(data).lower()
    for banned in ("path", "user", "email", "secret", "fingerprint",
                   "workspace", "@"):
        assert banned not in blob, banned
