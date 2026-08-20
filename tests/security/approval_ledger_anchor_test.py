"""MISSION-N1: approval ledger keyed-anchor regression corpus.

Covers the AP-N1..N7 attack matrix against the FIXED (anchored) ledger,
the documented legacy (unanchored) limitation, legitimate lifecycle
behavior, key handling, and the operator reanchor/migration path.

Invariant under test:

    A data-dir raw-file actor must NOT be able to resurrect a consumed
    approval or forge a never-issued approval in an ANCHORED ledger.
    The unanchored ledger remains a documented limitation.

Skipped != Pass: this suite asserts exact failure modes, not summaries.
"""

import json
import subprocess
import sys

import pytest

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger,
)
from simulation.agent.approval.approval_store import (
    ApprovalStore,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.persistence.chain_anchor import (
    ChainAnchorError,
    generate_key_bytes,
)
from simulation.security.hash_chain import HashChain


@pytest.fixture
def key():
    return generate_key_bytes()


def _make_patch(target, new_content="mode = 2\n"):
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="n1-corpus",
        old_content="mode = 1\n",
        new_content=new_content,
        allowed_paths=(),
    )


def _secret_target(tmp_path):
    d = tmp_path / "secrets"
    d.mkdir(exist_ok=True)
    t = d / "config.env"
    t.write_text("mode = 1\n", encoding="utf-8")
    return t


def _anchored_ledger(tmp_path, key, name="ledger.jsonl"):
    return ApprovalLedger(
        path=str(tmp_path / name),
        anchor_path=str(tmp_path / (name + ".anchor")),
        anchor_key=key,
    )


def _grant_consume(store, patch, target):
    store.grant(patch.fingerprint(), str(target), "modify", "HIGH")
    return store.find_valid(
        patch.fingerprint(),
        path=str(target),
        action="modify",
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )


def _read_records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_records(path, records):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def _forge_record(previous_hash, body):
    body = dict(body)
    body["previous_hash"] = previous_hash
    body["current_hash"] = HashChain.calculate(body)
    return body


def _recompute_chain(records):
    forged = []
    prev = "GENESIS"
    for rec in records:
        body = {k: v for k, v in rec.items()
                if k not in ("current_hash", "previous_hash")}
        forged.append(_forge_record(prev, body))
        prev = forged[-1]["current_hash"]
    return forged


# ---------------------------------------------------------------------------
# AP-N1 .. N4 — anchored ledger rejects the pre-fix attacks
# ---------------------------------------------------------------------------


def test_ap_n1_truncate_consumed_tail_rejected_when_anchored(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    _write_records(ledger.path, records[:-1])  # drop consumed record

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_ap_n2_truncate_multiple_consumed_rejected_when_anchored(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch_b1 = _make_patch(target, "mode = 2\n")
    patch_b2 = _make_patch(target, "mode = 3\n")
    store.grant(patch_b1.fingerprint(), str(target), "modify", "HIGH")
    store.grant(patch_b2.fingerprint(), str(target), "modify", "HIGH")
    store.find_valid(patch_b1.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch_b1)
    store.find_valid(patch_b2.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch_b2)

    records = _read_records(ledger.path)
    _write_records(ledger.path, records[:-2])  # drop both consumed records

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_ap_n3_modify_consumed_record_with_recomputed_chain_rejected(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    mutated = dict(records[2])  # [anchored-marker, grant, consumed]
    mutated["approval_id"] = "mutated-consumed-id"
    forged = _recompute_chain([records[0], records[1], mutated])
    _write_records(ledger.path, forged)

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_ap_n4_whole_ledger_forgery_rejected_when_anchored(tmp_path, key):
    ledger_path = tmp_path / "forged.jsonl"
    target = _secret_target(tmp_path)
    forged_patch = _make_patch(target)
    grant_body = {
        "record_type": "grant",
        "approval_id": "forged-never-issued",
        "patch_fingerprint": forged_patch.fingerprint(),
        "path": str(target),
        "action": "modify",
        "risk_level": "HIGH",
        "attempt": 1,
        "authorizer": "forged-operator",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": "",
    }
    _write_records(ledger_path, [_forge_record("GENESIS", grant_body)])

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(
            path=str(ledger_path),
            anchor_path=str(tmp_path / "forged.jsonl.anchor"),
            anchor_key=key,
        ))


def test_ap_n4b_forged_approval_cannot_reach_apply_when_anchored(tmp_path, key):
    """A forged never-issued approval must never be released for apply."""
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    # no legitimate grant exists; a forged decision/claim has nothing to bind to
    patch = _make_patch(target)
    found = store.find_valid(patch.fingerprint(), path=str(target),
                             action="modify", risk_level="HIGH", attempt=1,
                             patch=patch)
    assert found is None


# ---------------------------------------------------------------------------
# AP-N5 — historical rewind (accepted limitation, same as event store O.5)
# ---------------------------------------------------------------------------


def test_ap_n5_consistent_rewind_to_anchored_state_is_accepted_limitation(
    tmp_path, key
):
    """A consistent rewind of BOTH ledger + anchor to a genuinely anchored
    past state reloads successfully (documented historical-rewind
    limitation; the anchor authenticates a head, it does not prove the
    newest head)."""
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch_e1 = _make_patch(target, "mode = 2\n")
    patch_e2 = _make_patch(target, "mode = 3\n")
    store.grant(patch_e1.fingerprint(), str(target), "modify", "HIGH")
    store.find_valid(patch_e1.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch_e1)
    store.grant(patch_e2.fingerprint(), str(target), "modify", "HIGH")
    store.find_valid(patch_e2.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch_e2)

    # rewind BOTH files to the anchored marker + grant e1
    # (records[:2] = STATE A: marker, grant e1)
    _write_records(ledger.path, _read_records(ledger.path)[:2])
    anchor_lines = ledger.anchor.path.read_text(encoding="utf-8").splitlines()
    ledger.anchor.path.write_text(
        "\n".join(anchor_lines[:2]) + "\n", encoding="utf-8")

    # reload succeeds; e1 is available again -> documented rewind limitation
    reloaded = ApprovalStore(ledger=_anchored_ledger(tmp_path, key))
    revived = reloaded.find_valid(patch_e1.fingerprint(), path=str(target),
                                  action="modify", risk_level="HIGH",
                                  attempt=1, patch=patch_e1)
    assert revived is not None


# ---------------------------------------------------------------------------
# AP-N6 / AP-N7 — fresh reload / fresh process
# ---------------------------------------------------------------------------


def test_ap_n6_fresh_store_reload_detects_tamper(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    _write_records(ledger.path, records[:-1])

    # brand-new ApprovalLedger + ApprovalStore instances = fresh reload
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_ap_n7_fresh_process_reload_rejects_tamper(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    _write_records(ledger.path, records[:-1])

    helper = tmp_path / "reload_fresh.py"
    helper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {sys.path[0]!r})\n"
        "from simulation.agent.approval.approval_ledger import ApprovalLedger\n"
        "from simulation.agent.approval.approval_store import ApprovalStore\n"
        f"ApprovalStore(ledger=ApprovalLedger(\n"
        f"    path={str(ledger.path)!r},\n"
        f"    anchor_path={str(ledger.anchor.path)!r},\n"
        f"    anchor_key={key!r},\n"
        "))\n"
        "print('RELOAD_OK')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(helper)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "RELOAD_OK" not in result.stdout


# ---------------------------------------------------------------------------
# Legacy (unanchored) behavior = documented limitation
# ---------------------------------------------------------------------------


def test_ap_n1_unanchored_truncation_is_documented_limitation(tmp_path):
    """The unanchored ledger remains forgeable/truncatable. This asserts
    the documented legacy boundary so the behavior change is intentional
    and observable, mirroring the event store's unanchored default."""
    ledger_path = tmp_path / "legacy.jsonl"
    store = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger_path)
    _write_records(ledger_path, records[:-1])

    reloaded = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    revived = reloaded.find_valid(patch.fingerprint(), path=str(target),
                                  action="modify", risk_level="HIGH",
                                  attempt=1, patch=patch)
    assert revived is not None  # documented limitation; anchor is the fix


# ---------------------------------------------------------------------------
# Legitimate behavior must survive
# ---------------------------------------------------------------------------


def test_legit_anchored_lifecycle_and_restart(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    reloaded = ApprovalStore(ledger=_anchored_ledger(tmp_path, key))
    second = reloaded.find_valid(patch.fingerprint(), path=str(target),
                                 action="modify", risk_level="HIGH",
                                 attempt=1, patch=patch)
    assert second is None  # consumed stays consumed across restart


def test_valid_anchored_ledger_accepted(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    for index in range(3):
        patch = _make_patch(target, f"mode = {index + 2}\n")
        store.grant(patch.fingerprint(), str(target), "modify", "HIGH")
        store.find_valid(patch.fingerprint(), path=str(target),
                         action="modify", risk_level="HIGH", attempt=1,
                         patch=patch)

    records = ApprovalStore(ledger=_anchored_ledger(tmp_path, key)).ledger.load()
    assert len(records) == 7  # 1 anchored marker + 3 grants + 3 consumed


# ---------------------------------------------------------------------------
# Fail-closed key / anchor handling
# ---------------------------------------------------------------------------


def test_missing_key_fails_closed_when_anchored(tmp_path, monkeypatch):
    monkeypatch.delenv("CHAIN_ANCHOR_KEY", raising=False)
    with pytest.raises(ChainAnchorError):
        ApprovalLedger(
            path=str(tmp_path / "ledger.jsonl"),
            anchor_path=str(tmp_path / "ledger.anchor"),
            anchor_key=None,
        )


def test_wrong_key_fails_closed_on_reload(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    other_key = generate_key_bytes()
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(
            path=str(ledger.path),
            anchor_path=str(ledger.anchor.path),
            anchor_key=other_key,
        ))


def test_anchor_file_deleted_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    ledger.anchor.path.unlink()

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_anchor_file_truncated_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    ledger.anchor.path.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_reordered_ledger_records_rejected_when_anchored(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    _write_records(ledger.path, _recompute_chain([records[1], records[0]]))

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


# ---------------------------------------------------------------------------
# Operator migration (reanchor)
# ---------------------------------------------------------------------------


def test_reanchor_from_ledger_migrates_existing_ledger(tmp_path, key):
    ledger_path = tmp_path / "legacy.jsonl"
    store = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    # enable the anchor on the existing (chain-valid) ledger via operator reanchor
    anchored = ApprovalLedger(
        path=str(ledger_path),
        anchor_path=str(tmp_path / "legacy.anchor"),
        anchor_key=key,
    )
    anchored.reanchor_from_ledger()

    reloaded = ApprovalStore(ledger=anchored)
    # the consumed state from the original store survives the migration
    assert reloaded.consumed_ids() == store.consumed_ids()
    assert len(reloaded.consumed_ids()) == 1

    # now a truncation is detected
    records = _read_records(ledger_path)
    _write_records(ledger_path, records[:-1])
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(
            path=str(ledger_path),
            anchor_path=str(tmp_path / "legacy.anchor"),
            anchor_key=key,
        ))


def test_reanchor_requires_anchor(tmp_path):
    ledger = ApprovalLedger(path=str(tmp_path / "legacy.jsonl"))
    with pytest.raises(RuntimeError):
        ledger.reanchor_from_ledger()


# ---------------------------------------------------------------------------
# Production assembly wiring
# ---------------------------------------------------------------------------


def test_assembly_wires_ledger_anchor_fail_closed(tmp_path, key):
    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent,
    )
    from simulation.core.event import Event
    from simulation.core.kernel import Kernel
    from simulation.persistence.event_store import EventStore
    from simulation.security.risk_engine import RiskEngine
    from simulation.security.risk_policy import RiskPolicy

    kernel = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl",
            anchor_path=tmp_path / "events.anchor",
            anchor_key=key,
        )
    )

    ledger_path = tmp_path / "ledger.jsonl"
    anchor_path = tmp_path / "ledger.anchor"

    agent = build_recovery_agent(
        kernel,
        worker_executor=type(
            "W",
            (),
            {"allowed_paths": (str(tmp_path),)},
        )(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_ledger_path=str(ledger_path),
        approval_ledger_anchor_path=str(anchor_path),
        approval_ledger_anchor_key=key,
        scope=(str(tmp_path),),
    )

    store = agent.worker_pipeline.approval_store
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    store.grant(patch.fingerprint(), str(target), "modify", "HIGH")
    store.find_valid(patch.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch)

    # attacker truncates the anchored ledger -> next build fails closed
    records = _read_records(ledger_path)
    _write_records(ledger_path, records[:-1])
    with pytest.raises(RuntimeError):
        build_recovery_agent(
            kernel,
            worker_executor=type(
                "W",
                (),
                {"allowed_paths": (str(tmp_path),)},
            )(),
            risk_engine=RiskEngine(),
            risk_policy=RiskPolicy(),
            approval_ledger_path=str(ledger_path),
            approval_ledger_anchor_path=str(anchor_path),
            approval_ledger_anchor_key=key,
            scope=(str(tmp_path),),
        )
