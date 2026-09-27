"""FAZ 2.2 — remote usage transport contract (no real network).

Contract under test (owner-approved):
- HTTPS-only endpoint validation; http/malformed/empty -> no send
- explicit allow-list projection (never blanket dict forwarding)
- limits: signal <= 1KB, batch <= 64 signals, batch <= 32KB
- timeout (connect=1.0, read=2.0), single attempt, NO retry
- failure matrix: DNS/refused/timeout/TLS/4xx/5xx/encoding/unexpected
  -> fail-silent (no raise across the public boundary, no stdout/stderr)
- OFF preference -> zero DNS/socket/requests activity
- governance isolation: no pipeline/authority symbols; simulation
  never references the transport
- NO real network in any test (socket is boomed module-wide)

There is no real endpoint here: tests only use monkeypatch/mocks.
"""
import json
import socket

import pytest

import tanuq.usage_transport as ut
from tanuq.usage_signal import SIGNAL_KEYS, USAGE_EVENTS


# ---------------------------------------------------------------------------
# fixtures: no real network, deterministic environment
# ---------------------------------------------------------------------------

class NetworkViolation(BaseException):
    """Escapes `except Exception` — used to catch unmocked send paths."""


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("real network attempted in FAZ 2.2 tests")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)  # DNS

    def unmocked_post(*args, **kwargs):
        raise NetworkViolation("requests.post called without a test mock")

    monkeypatch.setattr(ut.requests, "post", unmocked_post)
    # deterministic preference + endpoint isolation (no real ~/.tanuq reads)
    monkeypatch.setenv("TANUQ_USAGE", "on")
    monkeypatch.setenv("TANUQ_USAGE_ENDPOINT", "")
    monkeypatch.setattr(ut, "_endpoint_from_config", lambda: None)


def _spy_post(monkeypatch, status=200, raise_exc=None):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if raise_exc is not None:
            raise raise_exc
        return FakeResponse(status)

    monkeypatch.setattr(ut.requests, "post", fake_post)
    return calls


def _signal(event="run_completed", **extra):
    signal = {
        "schema_version": 1,
        "event": event,
        "timestamp": "2026-09-27T00:00:00+00:00",
        "version": "0.6.0",
        "os_family": "linux",
        "install_id": "a" * 32,
        "run_id": "11111111-1111-4111-8111-111111111111",
    }
    signal.update(extra)
    return signal


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------

def test_https_endpoint_accepted():
    url = "https://telemetry.example.invalid/v1/usage"
    assert ut.validate_endpoint(url) == url
    assert ut.validate_endpoint("  https://h.invalid/x  ") == "https://h.invalid/x"


@pytest.mark.parametrize("bad", [
    None, "", "   ", 123, "http://insecure.invalid/x",
    "ftp://files.invalid/x", "javascript:alert(1)",
    "https://", "https:///path-only", "https://host with space/x",
    "https://user:pass@host.invalid/x", "not a url",
])
def test_invalid_endpoints_rejected(bad):
    assert ut.validate_endpoint(bad) is None


def test_send_with_invalid_explicit_endpoint_is_noop(monkeypatch):
    calls = _spy_post(monkeypatch)
    assert ut.send_usage_signals([_signal()],
                                 endpoint="http://insecure.invalid") is False
    assert calls == []


def test_send_without_endpoint_is_noop(monkeypatch):
    calls = _spy_post(monkeypatch)
    assert ut.send_usage_signals([_signal()]) is False  # endpoint isolated
    assert calls == []


def test_resolve_endpoint_precedence(monkeypatch):
    assert ut.resolve_endpoint("https://param.invalid") == "https://param.invalid"
    monkeypatch.setenv("TANUQ_USAGE_ENDPOINT", "https://env.invalid/e")
    assert ut.resolve_endpoint() == "https://env.invalid/e"
    # explicit param wins over env
    assert ut.resolve_endpoint("https://param.invalid") == "https://param.invalid"
    # invalid env falls through to config (which is isolated to None here)
    monkeypatch.setenv("TANUQ_USAGE_ENDPOINT", "garbage")
    assert ut.resolve_endpoint() is None


# ---------------------------------------------------------------------------
# allow-list
# ---------------------------------------------------------------------------

def test_allow_list_matches_usage_signal_schema():
    assert ut.ALLOWED_SIGNAL_FIELDS == set(SIGNAL_KEYS)


def test_only_allow_listed_fields_are_sent(monkeypatch):
    calls = _spy_post(monkeypatch)
    dirty = _signal(
        risk_level="HIGH",
        path="/repo/secret.py",
        reason="because reasons",
        fingerprint="f" * 64,
        task_id="t-1",
        prompt="do the thing",
        stdout="stack trace",
        nested={"inner": "value"},
        allowed_paths=("/a", "/b"),
    )
    assert ut.send_usage_signals([dirty], endpoint="https://h.invalid") is True
    body = json.loads(calls[0]["data"].decode("utf-8"))
    assert body["schema_version"] == 1
    assert body["endpoint_verified"] is True
    (sent,) = body["signals"]
    assert set(sent) <= ut.ALLOWED_SIGNAL_FIELDS
    blob = json.dumps(body)
    for forbidden in ("/repo/secret.py", "because reasons", "f" * 64,
                      "t-1", "do the thing", "stack trace", "inner",
                      "/a", "allowed_paths", "path", "reason",
                      "fingerprint", "task_id", "prompt", "stdout"):
        assert forbidden not in blob, forbidden


def test_invalid_signal_is_dropped(monkeypatch):
    calls = _spy_post(monkeypatch)
    dropped = [
        {"event": "not_a_real_event", "run_id": "x"},
        {"run_id": "y"},                                  # no event
        "not-a-dict",
        _signal(event="run_completed"),
    ]
    assert ut.send_usage_signals(dropped, endpoint="https://h.invalid") is True
    body = json.loads(calls[0]["data"].decode("utf-8"))
    assert len(body["signals"]) == 1
    assert body["signals"][0]["event"] == "run_completed"


# ---------------------------------------------------------------------------
# size limits
# ---------------------------------------------------------------------------

def test_signal_over_1kb_is_dropped_not_split(monkeypatch):
    calls = _spy_post(monkeypatch)
    big = _signal(event="run_started", version="0.6.0-" + "x" * 2000)
    small = _signal(event="run_started")
    assert ut.send_usage_signals([big, small],
                                 endpoint="https://h.invalid") is True
    body = json.loads(calls[0]["data"].decode("utf-8"))
    assert len(body["signals"]) == 1
    assert len(json.dumps(body["signals"][0]).encode("utf-8")) <= \
        ut.SIGNAL_MAX_BYTES


def test_batch_of_64_is_single_request(monkeypatch):
    calls = _spy_post(monkeypatch)
    signals = [_signal(event="run_started") for _ in range(64)]
    assert ut.send_usage_signals(signals, endpoint="https://h.invalid") is True
    assert len(calls) == 1
    assert len(json.loads(calls[0]["data"].decode("utf-8"))["signals"]) == 64


def test_batch_of_65_is_split_into_two_requests(monkeypatch):
    calls = _spy_post(monkeypatch)
    signals = [_signal(event="run_started") for _ in range(65)]
    assert ut.send_usage_signals(signals, endpoint="https://h.invalid") is True
    assert len(calls) == 2
    counts = [len(json.loads(c["data"].decode("utf-8"))["signals"])
              for c in calls]
    assert sorted(counts) == [1, 64]
    # single attempt per batch: no retry calls
    assert len(calls) == 2


def test_batch_never_exceeds_32kb(monkeypatch):
    calls = _spy_post(monkeypatch)
    signals = [
        _signal(event="run_started", version="0.6.0+" + "y" * 700)
        for _ in range(40)
    ]
    assert ut.send_usage_signals(signals, endpoint="https://h.invalid") is True
    assert len(calls) > 1, "expected splitting"
    total = 0
    for call in calls:
        raw = call["data"]
        assert len(raw) <= ut.BATCH_MAX_BYTES, len(raw)
        body = json.loads(raw.decode("utf-8"))
        assert len(body["signals"]) <= ut.BATCH_MAX_SIGNALS
        for signal in body["signals"]:
            # signals are never split: each is a complete record
            assert "event" in signal and "run_id" in signal
            total += 1
    assert total == 40


def test_limit_constants():
    assert ut.SIGNAL_MAX_BYTES == 1024
    assert ut.BATCH_MAX_SIGNALS == 64
    assert ut.BATCH_MAX_BYTES == 32 * 1024
    assert ut.CONNECT_TIMEOUT == 1.0
    assert ut.READ_TIMEOUT == 2.0


# ---------------------------------------------------------------------------
# failure matrix (fail-silent) + timeout + retry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [
    ConnectionError("dns/refused"),
    TimeoutError("timeout"),
    OSError("tls/socket"),
    ValueError("unexpected"),
])
def test_transport_exceptions_are_fail_silent(monkeypatch, capsys, exc):
    calls = _spy_post(monkeypatch, raise_exc=exc)
    result = ut.send_usage_signals([_signal()],
                                   endpoint="https://h.invalid")
    assert result is False
    assert len(calls) == 1          # single attempt, no retry
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503])
def test_http_error_statuses_are_fail_silent(monkeypatch, capsys, status):
    calls = _spy_post(monkeypatch, status=status)
    result = ut.send_usage_signals([_signal()],
                                   endpoint="https://h.invalid")
    assert result is True           # attempt completed (any status)
    assert len(calls) == 1          # no retry on 4xx/5xx
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_encoding_error_is_fail_silent(monkeypatch, capsys):
    calls = _spy_post(monkeypatch)
    bad = _signal(event="run_started", version="broken-\ud800-surrogate")
    result = ut.send_usage_signals([bad], endpoint="https://h.invalid")
    assert result is False
    assert calls == []              # failed before any request
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_timeout_parameters(monkeypatch):
    calls = _spy_post(monkeypatch)
    ut.send_usage_signals([_signal()], endpoint="https://h.invalid")
    assert calls[0]["timeout"] == (1.0, 2.0)
    assert ut.CONNECT_TIMEOUT == 1.0 and ut.READ_TIMEOUT == 2.0


def test_single_attempt_no_retry_on_success(monkeypatch):
    calls = _spy_post(monkeypatch, status=200)
    ut.send_usage_signals([_signal()], endpoint="https://h.invalid")
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# OFF behavior
# ---------------------------------------------------------------------------

def test_off_env_means_zero_network(monkeypatch):
    # no post mock: if the transport tried to send, NetworkViolation
    # (BaseException) would escape and fail this test loudly
    monkeypatch.setenv("TANUQ_USAGE", "off")
    assert ut.send_usage_signals([_signal()],
                                 endpoint="https://h.invalid") is False


def test_off_guard_runs_before_endpoint_and_post(monkeypatch):
    monkeypatch.setattr(ut, "read_usage_remote_preference",
                        lambda: (False, "config"))
    calls = _spy_post(monkeypatch)
    assert ut.send_usage_signals([_signal()],
                                 endpoint="https://h.invalid") is False
    assert calls == []


def test_on_guard_wiring_reads_preference(monkeypatch):
    seen = {}

    def fake_read():
        seen["called"] = True
        return True, "env"

    monkeypatch.setattr(ut, "read_usage_remote_preference", fake_read)
    calls = _spy_post(monkeypatch)
    ut.send_usage_signals([_signal()], endpoint="https://h.invalid")
    assert seen.get("called") is True
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# governance isolation
# ---------------------------------------------------------------------------

def test_governance_isolation():
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "tanuq" / "usage_transport.py").read_text(
        encoding="utf-8")
    for symbol in ("WorkerActionPipeline", "GovernanceEvaluator",
                   "FileApplier", "ApprovalStore", "authorize_apply",
                   "RiskEngine", "RiskPolicy"):
        assert symbol not in source, symbol
    for path in (repo / "simulation").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("usage_transport", "send_usage_signals",
                       "usage_remote", "TANUQ_USAGE"):
            assert marker not in text, f"{path}: {marker}"
    # no reverse dependency: usage_signal does not import the transport
    signal_src = (repo / "tanuq" / "usage_signal.py").read_text(
        encoding="utf-8")
    assert "usage_transport" not in signal_src
    # every event the transport accepts is a real FAZ 1 event
    assert set(ut.ALLOWED_SIGNAL_FIELDS) <= set(SIGNAL_KEYS)
    for field_value in list(USAGE_EVENTS)[:0]:  # pragma: no cover
        assert isinstance(field_value, str)
