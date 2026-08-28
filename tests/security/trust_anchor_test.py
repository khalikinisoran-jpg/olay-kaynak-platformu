"""MISSION-N: event-store trust anchor security corpus (N-01..N-10).

The unkeyed SHA-256 chain cannot detect deletion / edit of the LAST
event (the tail). ``ChainAnchor`` (``simulation/persistence/
chain_anchor.py``) closes that gap with an external keyed HMAC
chain-head anchor. These tests exercise the anchored production path
(EventStore + Kernel + RecoveryEngine) and the direct anchor primitive.

Authority separation is asserted throughout: the anchor is an INTEGRITY
authority only and is never consulted by approval / apply / scope /
risk (governance tests N-11..N-15 live in memory_provenance_test.py).

All keys are synthetic and generated per-test (never committed).
"""

import json
import os

import pytest

from simulation.core.event import Event
from simulation.core.kernel import Kernel
from simulation.persistence.chain_anchor import (
    ChainAnchor,
    ChainAnchorError,
    generate_key_bytes,
)
from simulation.persistence.event_store import EventStore
from simulation.security.hash_chain import HashChain


KEY_ENV = "CHAIN_ANCHOR_KEY"


@pytest.fixture
def key(monkeypatch):
    value = generate_key_bytes()
    monkeypatch.setenv(KEY_ENV, value)
    return value


def _store(tmp_path, key=None, anchor=True, anchor_path=None):
    if not anchor:
        return EventStore(path=tmp_path / "events.jsonl")
    return EventStore(
        path=tmp_path / "events.jsonl",
        anchor_path=anchor_path or (tmp_path / "anchor.jsonl"),
        anchor_key=key,
    )


def _kernel(tmp_path, key=None, anchor=True):
    return Kernel(_store(tmp_path, key=key, anchor=anchor))


def _memory_events(count):
    return [
        Event(
            event_type="MemoryStored",
            payload={"key": f"k{index}", "value": "v"},
        )
        for index in range(count)
    ]


def _write(store, count):
    kernel = Kernel(store)
    for event in _memory_events(count):
        kernel.dispatch(event)
    return kernel


def _read_lines(store):
    return [
        line
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def _write_lines(store, lines):
    store.path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _expect_denied(store):
    with pytest.raises(RuntimeError):
        Kernel(store)


# ---------------------------------------------------------------------------
# N-01 .. N-10 anchor attacks on the production path
# ---------------------------------------------------------------------------


def test_n01_tail_deletion_is_detected_by_anchor(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)

    lines = _read_lines(store)
    _write_lines(store, lines[:-1])

    _expect_denied(_store(tmp_path, key=key))
    assert ChainAnchor.verify.__doc__ is not None


def test_n02_tail_edit_with_recomputed_hash_is_detected(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)

    lines = _read_lines(store)
    edited = json.loads(lines[-1])
    edited["payload"] = {"key": "k4", "value": "EVIL"}
    edited["current_hash"] = HashChain.calculate(
        {
            "event_id": edited["event_id"],
            "event_type": edited["event_type"],
            "payload": edited["payload"],
            "sequence": edited["sequence"],
            "previous_hash": edited["previous_hash"],
        }
    )
    _write_lines(store, lines[:-1] + [json.dumps(edited)])

    _expect_denied(_store(tmp_path, key=key))


def test_n03_hash_recomputed_middle_deletion_is_detected(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)

    records = [json.loads(line) for line in _read_lines(store)]
    deleted = records[:1] + records[2:]

    previous_hash = "GENESIS"
    rebuilt = []
    for index, record in enumerate(deleted):
        record["previous_hash"] = previous_hash
        record["current_hash"] = HashChain.calculate(
            {
                "event_id": record["event_id"],
                "event_type": record["event_type"],
                "payload": record["payload"],
                "sequence": record["sequence"],
                "previous_hash": previous_hash,
            }
        )
        rebuilt.append(record)
        previous_hash = record["current_hash"]

    _write_lines(
        store,
        [json.dumps(record) for record in rebuilt],
    )

    _expect_denied(_store(tmp_path, key=key))


def test_n04_forged_anchor_mac_is_rejected(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 2)

    anchor_path = tmp_path / "anchor.jsonl"
    lines = [
        line
        for line in anchor_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    forged = json.loads(lines[-1])
    forged["mac"] = "0" * 64
    anchor_path.write_text(
        "\n".join(lines[:-1] + [json.dumps(forged)]) + "\n",
        encoding="utf-8",
    )

    _expect_denied(_store(tmp_path, key=key))


def test_n05_stale_anchor_events_beyond_head_are_rejected(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 2)

    anchor_path = tmp_path / "anchor.jsonl"
    anchor_lines = [
        line
        for line in anchor_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    last = json.loads(anchor_lines[-1])
    last["sequence"] += 1
    last["mac"] = "0" * 64
    anchor_path.write_text(
        "\n".join(anchor_lines[:-1] + [json.dumps(last)]) + "\n",
        encoding="utf-8",
    )

    _expect_denied(_store(tmp_path, key=key))


def test_n06_anchor_rollback_is_detected(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)

    anchor_path = tmp_path / "anchor.jsonl"
    lines = [
        line
        for line in anchor_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    anchor_path.write_text(
        "\n".join(lines[:-1]) + "\n",
        encoding="utf-8",
    )

    _expect_denied(_store(tmp_path, key=key))


def test_n07_wrong_key_is_rejected_at_recovery(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 2)

    other_key = generate_key_bytes()
    _expect_denied(_store(tmp_path, key=other_key))


def test_n08_missing_key_fails_closed(tmp_path):
    if KEY_ENV in os.environ:
        del os.environ[KEY_ENV]

    with pytest.raises(ChainAnchorError):
        EventStore(
            path=tmp_path / "events.jsonl",
            anchor_path=tmp_path / "anchor.jsonl",
        )


def test_n09_reordered_events_fail_closed_even_anchored(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    lines = _read_lines(store)
    _write_lines(store, [lines[0], lines[2], lines[1]])

    _expect_denied(_store(tmp_path, key=key))


def test_n10_duplicate_events_fail_closed_even_anchored(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    lines = _read_lines(store)
    _write_lines(store, lines + [lines[-1]])

    _expect_denied(_store(tmp_path, key=key))


def test_n04_wrong_chain_anchor_is_rejected(tmp_path, key):
    """An anchor created for one event chain must not verify another."""
    from simulation.persistence.chain_anchor import ChainAnchor

    store_a = EventStore(
        path=tmp_path / "a.jsonl",
        anchor_path=tmp_path / "a_anchor.jsonl",
        anchor_key=key,
    )
    _write(store_a, 3)

    store_b = EventStore(
        path=tmp_path / "b.jsonl",
        anchor_path=tmp_path / "b_anchor.jsonl",
        anchor_key=key,
    )
    _write(store_b, 4)

    anchor_b = ChainAnchor(
        path=tmp_path / "b_anchor.jsonl",
        anchor_key=key,
    )

    b_records = [
        json.loads(line)
        for line in store_b.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    b_tail = b_records[-1]
    assert (
        anchor_b.verify(
            b_tail["sequence"],
            b_tail["current_hash"],
        )
        is True
    )

    a_records = [
        json.loads(line)
        for line in store_a.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    a_tail = a_records[-1]
    assert (
        anchor_b.verify(
            a_tail["sequence"],
            a_tail["current_hash"],
        )
        is False
    )


# ---------------------------------------------------------------------------
# Direct primitive checks
# ---------------------------------------------------------------------------


def test_anchor_verify_empty_empty_is_accept(tmp_path, key):
    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )
    assert anchor.verify(0, "GENESIS") is True


def test_anchor_verify_nonempty_store_with_empty_anchor_is_deny(
    tmp_path,
    key,
):
    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )
    assert anchor.verify(3, "abc") is False


def test_anchor_verify_wrong_sequence_is_deny(tmp_path, key):
    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )
    anchor.anchor(4, "hash4")
    assert anchor.verify(4, "hash4") is True
    assert anchor.verify(3, "hash4") is False
    assert anchor.verify(4, "hash5") is False


def test_anchor_gap_in_anchor_ids_is_deny(tmp_path, key):
    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )
    anchor.anchor(1, "h1")
    anchor.anchor(2, "h2")
    lines = [
        line
        for line in anchor.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    anchor.path.write_text(
        "\n".join(lines[:1]) + "\n",
        encoding="utf-8",
    )
    assert anchor.verify(2, "h2") is False
    assert anchor.verify(1, "h1") is True


def test_anchor_reanchor_rebuilds_head(tmp_path, key):
    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )
    anchor.anchor(2, "oldhead")
    anchor.reanchor(5, "newhead")
    assert anchor.verify(5, "newhead") is True
    assert anchor.verify(2, "oldhead") is False


def test_anchor_key_file_loading(tmp_path):
    key = generate_key_bytes()
    key_file = tmp_path / "keyfile"
    key_file.write_text(key, encoding="utf-8")

    anchor = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key_path=str(key_file),
    )
    anchor.anchor(1, "h")
    assert anchor.verify(1, "h") is True


def test_short_key_is_rejected(tmp_path):
    with pytest.raises(ChainAnchorError):
        ChainAnchor(
            path=tmp_path / "anchor.jsonl",
            anchor_key="short",
        )


# ---------------------------------------------------------------------------
# Anchor absence (Phase 6)
# ---------------------------------------------------------------------------


def test_n21_anchor_file_deleted_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    (tmp_path / "anchor.jsonl").unlink()

    _expect_denied(_store(tmp_path, key=key))


def test_n22_anchor_file_empty_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    (tmp_path / "anchor.jsonl").write_text("", encoding="utf-8")

    _expect_denied(_store(tmp_path, key=key))


def test_n23_malformed_anchor_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    (tmp_path / "anchor.jsonl").write_text(
        "this is not json\n",
        encoding="utf-8",
    )

    with pytest.raises(ChainAnchorError):
        _store(tmp_path, key=key)


def test_n24_anchor_path_is_directory_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    anchor_dir = tmp_path / "anchor.jsonl"
    anchor_dir.unlink()
    anchor_dir.mkdir()

    with pytest.raises((ChainAnchorError, OSError, RuntimeError)):
        Kernel(
            EventStore(
                path=tmp_path / "events.jsonl",
                anchor_path=str(anchor_dir),
                anchor_key=key,
            )
        )


# ---------------------------------------------------------------------------
# Key rotation (Phase 8)
# ---------------------------------------------------------------------------


def test_n25_key_rotation_without_reanchor_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 3)

    new_key = generate_key_bytes()
    _expect_denied(_store(tmp_path, key=new_key))


def test_n26_key_rotation_with_reanchor_works(tmp_path, key):
    from simulation.persistence.chain_anchor import ChainAnchor

    store = _store(tmp_path, key=key)
    _write(store, 3)

    records = [json.loads(line) for line in _read_lines(store)]
    tail = records[-1]

    new_key = generate_key_bytes()

    anchor_rotated = ChainAnchor(
        path=tmp_path / "anchor.jsonl",
        anchor_key=new_key,
    )
    anchor_rotated.reanchor(
        tail["sequence"],
        tail["current_hash"],
    )

    assert (
        anchor_rotated.verify(
            tail["sequence"],
            tail["current_hash"],
        )
        is True
    )

    recovered = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl",
            anchor_path=tmp_path / "anchor.jsonl",
            anchor_key=new_key,
        )
    )
    assert recovered.state.event_counter == 3


# ---------------------------------------------------------------------------
# Anchor rollback (Phase 10)
# ---------------------------------------------------------------------------


def test_n27_anchor_rollback_with_newer_events_is_deny(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)

    anchor_path = tmp_path / "anchor.jsonl"
    lines = [
        line
        for line in anchor_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    anchor_path.write_text(
        "\n".join(lines[:2]) + "\n",
        encoding="utf-8",
    )

    _expect_denied(_store(tmp_path, key=key))


def test_n28_consistent_rewind_is_historical_rollback_limitation(
    tmp_path,
    key,
):
    """Rewinding BOTH the event log and the anchor to an earlier
    genuinely-anchored state is accepted (historical rollback).

    This is the documented limitation of the HMAC anchor: without an
    external immutable log it cannot distinguish a rewind to a past
    state that WAS anchored from a fresh truncated history. Roll-FORWARD
    to a forged head remains impossible without the key.
    """
    store = _store(tmp_path, key=key)
    _write(store, 4)

    event_lines = _read_lines(store)
    anchor_path = tmp_path / "anchor.jsonl"
    anchor_lines = [
        line
        for line in anchor_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    _write_lines(store, event_lines[:2])
    anchor_path.write_text(
        "\n".join(anchor_lines[:2]) + "\n",
        encoding="utf-8",
    )

    recovered = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl",
            anchor_path=str(anchor_path),
            anchor_key=key,
        )
    )
    assert recovered.state.event_counter == 2
    assert recovered.state.memory == {"k0": "v", "k1": "v"}


def test_valid_anchored_chain_recovers(tmp_path, key):
    store = _store(tmp_path, key=key)
    _write(store, 4)
    recovered = _kernel(tmp_path, key=key)
    assert sorted(recovered.state.memory) == [
        "k0",
        "k1",
        "k2",
        "k3",
    ]


def test_unanchored_default_behavior_unchanged(tmp_path):
    store = _store(tmp_path, key=None, anchor=False)
    kernel = Kernel(store)
    kernel.dispatch(
        Event(
            event_type="MemoryStored",
            payload={"key": "k1", "value": "v"},
        )
    )
    assert store.chain_anchor is None
    assert store.verify_tail_anchor() is True
    recovered = Kernel(EventStore(path=tmp_path / "events.jsonl"))
    assert recovered.state.memory == {"k1": "v"}


# ---------------------------------------------------------------------------
# MISSION-N anchor failure matrix (gated summary)
# ---------------------------------------------------------------------------


class AnchorMatrix:

    def __init__(self):
        self.rows = []

    def record(self, condition, expected, actual, passed):
        self.rows.append((condition, expected, actual, passed))


@pytest.fixture(scope="module")
def anchor_matrix():
    return AnchorMatrix()


def test_n20_anchor_failure_matrix(anchor_matrix, tmp_path, key, monkeypatch):
    """Gated summary of the anchor fail-closed matrix. Every row must
    be DENY / DETECT; a single unexpected ACCEPT fails the suite."""

    def check(condition, expected, fn):
        try:
            outcome = fn()
        except RuntimeError:
            actual = "DENY"
        except ChainAnchorError:
            actual = "DENY"
        else:
            actual = "ACCEPT" if outcome else "DENY"
        passed = actual == expected
        anchor_matrix.record(condition, expected, actual, passed)
        return passed

    results = []

    store = _store(tmp_path, key=key)
    _write(store, 4)

    lines = _read_lines(store)

    store_del = _store(tmp_path / "del", key=key)
    _write(store_del, 4)
    del_lines = _read_lines(store_del)
    _write_lines(store_del, del_lines[:-1])

    results.append(
        check(
            "tail deletion",
            "DENY",
            lambda: _store(tmp_path / "del", key=key).verify_tail_anchor(),
        )
    )

    records = [json.loads(line) for line in lines]
    deleted = records[:1] + records[2:]
    prev = "GENESIS"
    rebuilt = []
    for record in deleted:
        record["previous_hash"] = prev
        record["current_hash"] = HashChain.calculate(
            {
                "event_id": record["event_id"],
                "event_type": record["event_type"],
                "payload": record["payload"],
                "sequence": record["sequence"],
                "previous_hash": prev,
            }
        )
        rebuilt.append(record)
        prev = record["current_hash"]
    middle_del_store = _store(tmp_path / "mid", key=key)
    _write_lines(
        middle_del_store,
        [json.dumps(r) for r in rebuilt],
    )
    results.append(
        check(
            "hash-recomputed middle deletion",
            "DENY",
            lambda: _store(tmp_path / "mid", key=key).verify_tail_anchor(),
        )
    )

    results.append(
        check(
            "valid anchored chain",
            "ACCEPT",
            lambda: _store(tmp_path, key=key).verify_tail_anchor(),
        )
    )

    anchor = ChainAnchor(
        path=tmp_path / "matrix_anchor.jsonl",
        anchor_key=key,
    )
    anchor.anchor(4, "h4")
    results.append(
        check(
            "valid anchor head",
            "ACCEPT",
            lambda: anchor.verify(4, "h4"),
        )
    )
    results.append(
        check(
            "wrong sequence vs anchor",
            "DENY",
            lambda: anchor.verify(3, "h4"),
        )
    )
    results.append(
        check(
            "wrong hash vs anchor",
            "DENY",
            lambda: anchor.verify(4, "h9"),
        )
    )

    empty_anchor = ChainAnchor(
        path=tmp_path / "matrix_empty.jsonl",
        anchor_key=key,
    )
    results.append(
        check(
            "missing anchor (empty store)",
            "DENY",
            lambda: empty_anchor.verify(2, "h2"),
        )
    )

    assert all(results), (
        "Anchor matrix violation: "
        + str(
            [
                row
                for row in anchor_matrix.rows
                if not row[3]
            ]
        )
    )


# ---------------------------------------------------------------------------
# Authority separation: the anchor is integrity authority, never apply
# authority
# ---------------------------------------------------------------------------


def test_n16_anchor_is_integrity_authority_never_apply_authority(
    tmp_path,
    key,
    monkeypatch,
):
    """An anchored store's valid recovery grants NO apply authority.

    The anchor proves only that the chain head was previously anchored.
    A HIGH/CRITICAL patch still requires a store-backed single-use
    approval; the anchor is never consulted by approval / apply / scope
    / risk.
    """
    from simulation.agent.apply.apply_executor import ApplyExecutor
    from simulation.agent.approval.approval_store import ApprovalStore
    from simulation.agent.controller.controller import Controller
    from simulation.agent.pipeline.apply_verify_pipeline import (
        ApplyVerifyPipeline,
    )
    from simulation.agent.pipeline.worker_action_pipeline import (
        WorkerActionPipeline,
    )
    from simulation.agent.verify.verification_result import (
        VerificationResult,
    )
    from simulation.agent.worker.patch_proposal import PatchProposal
    from simulation.agent.worker.patch_validator import PatchValidator
    from simulation.agent.worker.worker_result import WorkerResult
    from simulation.security.risk_engine import RiskEngine
    from simulation.security.risk_policy import RiskPolicy

    store = _store(tmp_path, key=key)
    kernel = Kernel(store)
    for index in range(4):
        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": f"k{index}", "value": "v"},
            )
        )

    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    target = secret_dir / "config.env"
    original = "mode = 1\n"
    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="authority separation",
        old_content=original,
        new_content="mode = 2\n",
        allowed_paths=(str(target),),
    )

    class PassVerify:
        def verify(self, paths, test_targets=()):
            return VerificationResult(
                status="PASS",
                exit_code=0,
                stdout="",
                stderr="",
                failure_reason="",
            )

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=PassVerify(),
        ),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=ApprovalStore(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="n16",
            success=True,
            summary="probe",
            patches=(patch,),
        )
    )

    assert result.success is False
    assert result.failure_stage == "approval"
    assert target.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Tail deletion + snapshot interplay (MISSION-N Phase 16)
# ---------------------------------------------------------------------------


def test_n17_tail_deletion_with_valid_snapshot_fails_closed(
    tmp_path,
    key,
):
    """Snapshot present + tail event deleted: the anchor must still
    fail closed even though the snapshot alone would hide the loss."""
    store = _store(tmp_path, key=key)
    kernel = Kernel(store)
    for index in range(4):
        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": f"k{index}", "value": "v"},
            )
        )
    assert (tmp_path / "snapshot.json").exists()

    lines = _read_lines(store)
    _write_lines(store, lines[:-1])

    _expect_denied(_store(tmp_path, key=key))


# ---------------------------------------------------------------------------
# Crash consistency: event written but anchor not updated -> fail closed
# ---------------------------------------------------------------------------


def test_n18_crash_between_event_and_anchor_fails_closed(tmp_path, key):
    """A crash after the event fsync but before the anchor update
    leaves events beyond the anchored head. The next recovery rejects
    them (FAIL CLOSED): a partially-anchored tail is never trusted."""
    store = _store(tmp_path, key=key)
    _write(store, 2)

    records = [json.loads(line) for line in _read_lines(store)]
    previous_hash = records[-1]["current_hash"]
    tail = records[-1]

    extra = {
        "event_id": "crash-event",
        "event_type": "MemoryStored",
        "payload": {"key": "k3", "value": "crash"},
        "sequence": tail["sequence"] + 1,
        "previous_hash": previous_hash,
    }
    extra["current_hash"] = HashChain.calculate(extra)

    _write_lines(store, _read_lines(store) + [json.dumps(extra)])

    _expect_denied(_store(tmp_path, key=key))


def test_n19_anchor_verified_against_current_tail_detects_late_mutation(
    tmp_path,
    key,
):
    """TOCTOU direction: verify_tail_anchor is checked against the
    store's current tail, so a mutation after a Kernel was built is
    detectable on the next verification (and never silently trusted)."""
    store = _store(tmp_path, key=key)
    kernel = Kernel(store)
    for index in range(3):
        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": f"k{index}", "value": "v"},
            )
        )

    live_memory = dict(kernel.state.memory)
    assert len(live_memory) == 3

    lines = _read_lines(store)
    _write_lines(store, lines[:-1])

    with pytest.raises(ChainAnchorError):
        store.verify_tail_anchor()
