"""Usage Signal V1 (FAZ 1) — derivation, privacy and fail-silent tests.

Read-only contract tests for `tanuq/usage_signal.py`:
- event derivation from existing EventStore / ApplyOutcomeJournal data
- first_run / stable install_id semantics
- privacy deny-list on every emitted payload
- fail-silent behavior (never raises, never touches stdout/stderr)
- import boundary (simulation/** never references usage_signal)
- incremental performance sanity

No core/governance files are exercised as writers; inputs are synthetic
JSONL fixtures built in tmp_path.
"""
import json
import re
import time
import types
from collections import Counter
from pathlib import Path

import pytest

import tanuq.usage_signal as us

REPO = Path(__file__).resolve().parents[1]

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _ws_env(tmp_path, created_at="2026-01-01T00:00:00+00:00"):
    data = tmp_path / "ws" / ".tanuq" / "data"
    data.mkdir(parents=True, exist_ok=True)
    return types.SimpleNamespace(
        workspace=tmp_path / "ws",
        data_dir=data,
        config=types.SimpleNamespace(created_at=created_at),
    )


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _collect(env, tmp_path, name="usage", secret=None):
    return us.collect_usage_signals(
        env,
        usage_dir=tmp_path / name,
        secret_path=secret or str(tmp_path / "usage.key"),
    )


def _worker(event_type, payload):
    return {"event_type": event_type, "payload": dict(payload)}


def _journal(record_type, intent_id, **extra):
    record = {"record_type": record_type, "intent_id": intent_id}
    record.update(extra)
    return record


def _counts(signals):
    return Counter(s["event"] for s in signals)


# ---------------------------------------------------------------------------
# A. decision derivation
# ---------------------------------------------------------------------------

def _risk_fixture(tmp_path):
    events = []
    cases = [
        ("fp_allow", "LOW", True, False),
        ("fp_review", "HIGH", True, True),
        ("fp_deny", "CRITICAL", False, False),
        ("fp_unknown", "UNKNOWN", False, False),
    ]
    for fp, risk, allowed, requires in cases:
        events.append(_worker(
            "WorkerPatchProposed",
            {"patch_fingerprint": fp, "task_id": "t-" + fp},
        ))
        events.append(_worker(
            "WorkerRiskAssessed",
            {
                "patch_fingerprint": fp,
                "risk_level": risk,
                "allowed": allowed,
                "requires_human_approval": requires,
                # sensitive content that must NEVER reach a signal:
                "reason": "because /secret/path.py changed",
                "path": "C:\\Users\\bob\\secret.py",
            },
        ))
    _write_jsonl(_ws_env(tmp_path).data_dir / "events.jsonl", events)
    return cases


def test_decision_allow_review_deny_unknown(tmp_path):
    env = _ws_env(tmp_path)
    cases = _risk_fixture(tmp_path)
    signals = _collect(env, tmp_path)
    counts = _counts(signals)
    for name in ("decision_allow", "decision_review", "decision_deny",
                 "decision_unknown"):
        assert counts[name] == 1, (name, counts)
    by_event = {s["event"]: s for s in signals
                if s["event"].startswith("decision_")}
    assert by_event["decision_allow"]["risk_level"] == "LOW"
    assert by_event["decision_review"]["risk_level"] == "HIGH"
    assert by_event["decision_deny"]["risk_level"] == "CRITICAL"
    assert by_event["decision_unknown"]["risk_level"] == "UNKNOWN"
    for sig in by_event.values():
        assert sig["decision_class"] in us.DECISION_CLASSES
        assert sig["run_id"] and UUID_RE.match(sig["run_id"])
    # every run started exactly once
    assert counts["run_started"] == len(cases)


# ---------------------------------------------------------------------------
# B. apply / C. verify / D. run completion
# ---------------------------------------------------------------------------

def test_apply_success_dedup_across_worker_and_journal(tmp_path):
    env = _ws_env(tmp_path)
    data = env.data_dir
    _write_jsonl(data / "events.jsonl", [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpA", "task_id": "tA"}),
        _worker("WorkerPatchApplied",
                {"patch_fingerprint": "fpA", "task_id": "tA"}),
    ])
    _write_jsonl(data / "apply_journal.jsonl", [
        _journal("intent", "iA", patch_fingerprint="fpA"),
        _journal("applied", "iA"),
        _journal("apply_started", "iA"),
    ])
    signals = _collect(env, tmp_path)
    counts = _counts(signals)
    # worker event + journal "applied" => exactly ONE apply_success
    assert counts["apply_success"] == 1, counts
    run_ids = {s["run_id"] for s in signals if s["event"] == "apply_success"}
    assert len(run_ids) == 1


def test_apply_failure_from_journal(tmp_path):
    env = _ws_env(tmp_path)
    data = env.data_dir
    _write_jsonl(data / "events.jsonl", [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpB", "task_id": "tB"}),
    ])
    _write_jsonl(data / "apply_journal.jsonl", [
        _journal("intent", "iB", patch_fingerprint="fpB"),
        _journal("apply_started", "iB"),
        _journal("apply_failed", "iB"),
    ])
    signals = _collect(env, tmp_path)
    counts = _counts(signals)
    assert counts["apply_failure"] == 1
    assert counts["run_completed"] == 1
    completed = [s for s in signals if s["event"] == "run_completed"]
    assert completed[0]["terminal_state"] == "apply_failed"


def test_verify_success_failure_and_terminals(tmp_path):
    env = _ws_env(tmp_path)
    data = env.data_dir
    events = [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpV", "task_id": "tV"}),
        _worker("WorkerVerificationCompleted",
                {"patch_fingerprint": "fpV", "task_id": "tV",
                 "passed": True, "status": "passed"}),
    ]
    _write_jsonl(data / "events.jsonl", events)
    _write_jsonl(data / "apply_journal.jsonl", [
        _journal("intent", "iV", patch_fingerprint="fpV"),
        _journal("verified", "iV"),
    ])
    counts = _counts(_collect(env, tmp_path))
    assert counts["verify_success"] == 1  # worker+journal deduped
    assert counts["run_completed"] == 1


def test_run_completed_terminal_states(tmp_path):
    terminals = [
        ("verified", "verify_success"),
        ("apply_failed", "apply_failure"),
        ("rolled_back", "verify_failure"),
        ("rollback_failed", "apply_failure"),
    ]
    for index, (terminal, _pair) in enumerate(terminals):
        env = _ws_env(tmp_path / f"case{index}")
        data = env.data_dir
        _write_jsonl(data / "events.jsonl", [
            _worker("WorkerPatchProposed",
                    {"patch_fingerprint": "fp" + terminal,
                     "task_id": "t" + terminal}),
        ])
        _write_jsonl(data / "apply_journal.jsonl", [
            _journal("intent", "i" + terminal,
                     patch_fingerprint="fp" + terminal),
            _journal(terminal, "i" + terminal),
        ])
        signals = _collect(env, tmp_path / f"case{index}")
        completed = [s for s in signals if s["event"] == "run_completed"]
        assert len(completed) == 1, (terminal, signals)
        assert completed[0]["terminal_state"] == terminal
    # rollback_failed carries BOTH outcomes per schema
    env = _ws_env(tmp_path / "rbf")
    _write_jsonl(env.data_dir / "events.jsonl", [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpR", "task_id": "tR"}),
    ])
    _write_jsonl(env.data_dir / "apply_journal.jsonl", [
        _journal("intent", "iR", patch_fingerprint="fpR"),
        _journal("rollback_failed", "iR"),
    ])
    counts = _counts(_collect(env, tmp_path / "rbf"))
    assert counts["apply_failure"] == 1
    assert counts["verify_failure"] == 1
    assert counts["run_completed"] == 1


# ---------------------------------------------------------------------------
# E. first run / F. stable id
# ---------------------------------------------------------------------------

def test_first_run_emitted_once_per_workspace(tmp_path):
    env = _ws_env(tmp_path)
    _write_jsonl(env.data_dir / "events.jsonl", [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpF", "task_id": "tF"}),
    ])
    first = _collect(env, tmp_path)
    assert _counts(first)["first_run"] == 1
    second = _collect(env, tmp_path)  # same usage state
    assert second == []
    # a workspace whose config has no created_at never emits first_run
    env2 = _ws_env(tmp_path / "nocfg", created_at="")
    _write_jsonl(env2.data_dir / "events.jsonl", [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": "fpN", "task_id": "tN"}),
    ])
    counts = _counts(_collect(env2, tmp_path / "nocfg"))
    assert "first_run" not in counts
    assert counts["run_started"] == 1


def test_install_id_stable_and_distinct(tmp_path):
    secret = us.load_usage_secret(str(tmp_path / "usage.key"))
    id_a = us.make_install_id(tmp_path / "ws", secret)
    id_b = us.make_install_id(tmp_path / "ws", secret)
    id_c = us.make_install_id(tmp_path / "other-ws", secret)
    assert id_a == id_b
    assert id_a != id_c
    assert HEX32_RE.match(id_a)
    # deriving signals for two workspaces keeps ids distinct
    for name in ("wsA", "wsB"):
        env = _ws_env(tmp_path / name)
        _write_jsonl(env.data_dir / "events.jsonl", [
            _worker("WorkerPatchProposed",
                    {"patch_fingerprint": "fp" + name,
                     "task_id": "t" + name}),
        ])
        _collect(env, tmp_path / name, secret=str(tmp_path / "usage.key"))
    out_a = (tmp_path / "wsA" / "usage" / "usage_signals.jsonl")
    out_b = (tmp_path / "wsB" / "usage" / "usage_signals.jsonl")
    ids = set()
    for path in (out_a, out_b):
        for line in path.read_text(encoding="utf-8").splitlines():
            ids.add(json.loads(line)["install_id"])
    assert len(ids) == 2


def test_workspace_path_never_leaks(tmp_path):
    env = _ws_env(tmp_path)
    _risk_fixture(tmp_path)
    signals = _collect(env, tmp_path)
    blob = json.dumps(signals, sort_keys=True)
    assert str(tmp_path / "ws") not in blob
    assert "secret.py" not in blob
    assert "bob" not in blob


# ---------------------------------------------------------------------------
# G. privacy deny-list
# ---------------------------------------------------------------------------

def _assert_safe_value(value):
    if isinstance(value, bool) or isinstance(value, int):
        return
    assert isinstance(value, str), value
    assert value == "" or (
        UUID_RE.match(value)
        or HEX32_RE.match(value)
        or ISO_RE.match(value)
        or value in us.RISK_VALUES
        or value in us.DECISION_CLASSES
        or value in us.TERMINAL_STATES
        or value in us.OS_FAMILIES
        or re.match(r"^\d+\.\d+\.\d+", value)          # version
        or re.match(r"^[A-Za-z][A-Za-z0-9_]*$", value)  # enum-ish
    ), f"unexpected signal value: {value!r}"


def test_privacy_deny_list_on_every_signal(tmp_path):
    env = _ws_env(tmp_path)
    data = env.data_dir
    sensitive_fp = "f" * 64
    events = [
        _worker("WorkerPatchProposed",
                {"patch_fingerprint": sensitive_fp, "task_id": "t-priv",
                 "path": "/repo/secret_module.py",
                 "reason": "because reasons", "action": "modify"}),
        _worker("WorkerRiskAssessed",
                {"patch_fingerprint": sensitive_fp, "risk_level": "HIGH",
                 "allowed": True, "requires_human_approval": True,
                 "reason": "because reasons"}),
        _worker("WorkerPatchApplied",
                {"patch_fingerprint": sensitive_fp, "task_id": "t-priv"}),
        _worker("WorkerVerificationFailed",
                {"patch_fingerprint": sensitive_fp, "task_id": "t-priv",
                 "status": "failed", "exit_code": 1,
                 "failure_reason": "tests failed: traceback follows"}),
    ]
    _write_jsonl(data / "events.jsonl", events)
    _write_jsonl(data / "apply_journal.jsonl", [
        _journal("intent", "i-priv", patch_fingerprint=sensitive_fp),
        _journal("applied", "i-priv"),
        _journal("rollback_failed", "i-priv"),
    ])
    signals = _collect(env, tmp_path)
    assert signals, "expected signals"
    banned_keys = {
        "path", "filename", "file", "content", "diff", "reason",
        "fingerprint", "patch_fingerprint", "task_id", "approval_id",
        "intent_id", "prompt", "email", "username", "repo", "secret",
        "stdout", "stderr", "traceback", "message", "old_content",
        "new_content", "commands", "exit_code", "failure_reason",
    }
    for signal in signals:
        assert set(signal) <= us.SIGNAL_KEYS, sorted(set(signal) - us.SIGNAL_KEYS)
        assert not (set(signal) & banned_keys)
        for key, value in signal.items():
            _assert_safe_value(value)
        blob = json.dumps(signal, sort_keys=True)
        assert sensitive_fp not in blob
        assert "t-priv" not in blob
        assert "i-priv" not in blob
        assert "traceback" not in blob
        assert "secret_module" not in blob


# ---------------------------------------------------------------------------
# H. fail-silent
# ---------------------------------------------------------------------------

def test_fail_silent_on_corrupt_and_missing_inputs(tmp_path, capsys):
    env = _ws_env(tmp_path)
    data = env.data_dir
    (data / "events.jsonl").write_bytes(b'{"event_type": "WorkerPatchProposed"\nGARBAGE-NOT-JSON\n')
    (data / "apply_journal.jsonl").write_bytes(b"{ truncated")
    signals = _collect(env, tmp_path)   # must NOT raise
    assert isinstance(signals, list)
    # corrupt/complete lines are skipped silently; offsets still advance
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    # missing data dir entirely
    empty_env = types.SimpleNamespace(
        workspace=tmp_path / "nope", data_dir=tmp_path / "nope" / "d",
        config=types.SimpleNamespace(created_at="2026-01-01T00:00:00+00:00"),
    )
    assert isinstance(_collect(empty_env, tmp_path, "u-missing"), list)
    # usage target is a FILE (mkdir/write fails) -> silent
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    assert _collect(env, tmp_path, "u-x", secret=str(tmp_path / "usage.key")) is not None
    result = us.collect_usage_signals(
        env, usage_dir=blocker, secret_path=str(tmp_path / "usage.key"),
    )
    assert isinstance(result, list)
    # corrupt state.json does not raise
    bad_state = tmp_path / "u-state"
    bad_state.mkdir(exist_ok=True)
    (bad_state / "state.json").write_text("{not json", encoding="utf-8")
    assert isinstance(_collect(env, tmp_path, "u-state"), list)
    out = capsys.readouterr()
    assert out.out == "" and out.err == "", (out.out, out.err)


def test_fail_silent_error_signal_builder(tmp_path, capsys):
    # invalid class names are rejected (raw messages never stored)
    assert us.record_usage_error("Boom: bad message",
                                 usage_dir=tmp_path / "u-err") is None
    assert us.record_usage_error("has space",
                                 usage_dir=tmp_path / "u-err") is None
    assert us.record_usage_error("", usage_dir=tmp_path / "u-err") is None
    # valid class name produces an anonymous error signal
    signal = us.record_usage_error("ProtocolError",
                                   workspace=tmp_path / "ws",
                                   usage_dir=tmp_path / "u-err")
    assert signal is not None
    assert signal["event"] == "error"
    assert signal["error_class"] == "ProtocolError"
    assert "message" not in signal and "traceback" not in signal
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ---------------------------------------------------------------------------
# I. import boundary
# ---------------------------------------------------------------------------

def test_simulation_never_imports_usage_signal():
    offenders = []
    for path in (REPO / "simulation").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "usage_signal" in text or "collect_usage_signals" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], offenders


def test_usage_module_does_not_touch_pipeline_symbols():
    text = (REPO / "tanuq" / "usage_signal.py").read_text(encoding="utf-8")
    for banned in ("WorkerActionPipeline(", "GovernanceEvaluator(",
                   "ApprovalStore(", "FileApplier(", ".execute(",
                   "authorize_apply"):
        assert banned not in text, banned


# ---------------------------------------------------------------------------
# J. performance (10k events)
# ---------------------------------------------------------------------------

def test_incremental_performance_10k(tmp_path):
    env = _ws_env(tmp_path)
    records = []
    for i in range(5000):
        fp = f"fp{i:x}"
        records.append(_worker(
            "WorkerPatchProposed",
            {"patch_fingerprint": fp, "task_id": f"t{i}"},
        ))
        records.append(_worker(
            "WorkerRiskAssessed",
            {"patch_fingerprint": fp, "risk_level": "LOW",
             "allowed": True, "requires_human_approval": False},
        ))
    assert len(records) == 10000
    _write_jsonl(env.data_dir / "events.jsonl", records)

    started = time.perf_counter()
    first = _collect(env, tmp_path, "u-perf")
    cold_ms = (time.perf_counter() - started) * 1000
    assert len(first) > 0

    # incremental: +100 records only
    extra = []
    for i in range(50):
        fp = f"nfp{i:x}"
        extra.append(_worker("WorkerPatchProposed",
                             {"patch_fingerprint": fp, "task_id": f"n{i}"}))
        extra.append(_worker("WorkerRiskAssessed",
                             {"patch_fingerprint": fp, "risk_level": "LOW",
                              "allowed": True,
                              "requires_human_approval": False}))
    with open(env.data_dir / "events.jsonl", "a", encoding="utf-8") as fh:
        for record in extra:
            fh.write(json.dumps(record) + "\n")
    started = time.perf_counter()
    second = _collect(env, tmp_path, "u-perf")
    warm_ms = (time.perf_counter() - started) * 1000
    assert len(second) == 100

    # reported for the audit; generous CI bound (target: cold < 100ms
    # locally, asserted loosely to avoid CI flakiness)
    print(f"\nusage-signal perf: cold(10k)={cold_ms:.1f}ms "
          f"incremental(100)={warm_ms:.1f}ms")
    assert cold_ms < 1000, cold_ms
    assert warm_ms < 250, warm_ms
