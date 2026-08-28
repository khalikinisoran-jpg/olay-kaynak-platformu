"""MISSION-N2: approval authority boundary hardening regression corpus.

Covers the configuration-downgrade fix (anchored -> unanchored reload
must fail closed), the reanchor operator boundary, crash/fsync windows,
cross-binding mismatches, and stale-approval rejection with the anchored
ledger in the loop.

Invariant under test:

    No configuration change, malformed state, crash window, or operator
    recovery step may cause an approval to reach authorization/apply
    without passing the anchored Approval Ledger boundary.
"""

import json

import pytest

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger,
)
from simulation.agent.approval.approval_store import (
    ApprovalStore,
)
from simulation.agent.apply.apply_executor import ApplyExecutor
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
from simulation.persistence.chain_anchor import (
    generate_key_bytes,
)
from simulation.security.hash_chain import HashChain
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


@pytest.fixture
def key():
    return generate_key_bytes()


def _make_patch(target, new_content="mode = 2\n"):
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="n2-corpus",
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


# ---------------------------------------------------------------------------
# Configuration downgrade (anchored -> unanchored restart)
# ---------------------------------------------------------------------------


def test_config_downgrade_unanchored_reload_of_anchored_ledger_fails_closed(
    tmp_path, key
):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    # operator/attacker restarts WITHOUT the anchor option: the ledger's
    # in-chain "anchored" marker must make the unanchored load fail closed
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(path=str(ledger.path)))


def test_config_downgrade_fresh_anchored_ledger_refuses_unanchored_load(
    tmp_path, key
):
    ledger = _anchored_ledger(tmp_path, key)  # marker appended at creation
    assert len(_read_records(ledger.path)) == 1  # marker only

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(path=str(ledger.path)))


def test_legacy_unanchored_ledger_without_marker_still_loads(tmp_path):
    """The unanchored legacy default (no marker) is unchanged."""
    ledger = ApprovalLedger(path=str(tmp_path / "legacy.jsonl"))
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    reloaded = ApprovalStore(ledger=ApprovalLedger(path=str(ledger.path)))
    second = reloaded.find_valid(patch.fingerprint(), path=str(target),
                                 action="modify", risk_level="HIGH",
                                 attempt=1, patch=patch)
    assert second is None  # consumed stays consumed (legacy, documented)


def test_reanchor_adds_marker_and_blocks_downgrade(tmp_path, key):
    ledger_path = tmp_path / "legacy.jsonl"
    store = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    anchored = ApprovalLedger(
        path=str(ledger_path),
        anchor_path=str(tmp_path / "legacy.anchor"),
        anchor_key=key,
    )
    anchored.reanchor_from_ledger()
    ApprovalStore(ledger=anchored)  # anchored load works after migration

    # unanchored reload after migration must now fail closed
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))


# ---------------------------------------------------------------------------
# Reanchor operator boundary (key-gated; documents behavior)
# ---------------------------------------------------------------------------


def test_reanchor_is_key_gated_and_forged_state_rejected_before_reanchor(
    tmp_path, key
):
    target = _secret_target(tmp_path)
    forged_patch = _make_patch(target)
    forged = [{
        "record_type": "grant",
        "approval_id": "forged-by-attacker",
        "patch_fingerprint": forged_patch.fingerprint(),
        "path": str(target),
        "action": "modify",
        "risk_level": "HIGH",
        "attempt": 1,
        "authorizer": "forged",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": "",
        "previous_hash": "GENESIS",
    }]
    forged[0]["current_hash"] = HashChain.calculate(forged[0])
    _write_records(tmp_path / "forged.jsonl", forged)

    # BEFORE reanchor: the forged ledger is rejected by an anchored store
    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(
            path=str(tmp_path / "forged.jsonl"),
            anchor_path=str(tmp_path / "forged.anchor"),
            anchor_key=key,
        ))

    # reanchor is an operator recovery operation gated by KEY POSSESSION;
    # without a key it cannot even construct the anchor
    with pytest.raises(RuntimeError):
        ApprovalLedger(path=str(tmp_path / "forged.jsonl")).reanchor_from_ledger()

    # A key-holder re-anchoring is an explicit trust-asserting operator act
    # (documented boundary); the forged state is trusted only because the
    # key holder asserted it. This does not weaken the boundary for an
    # attacker who lacks the key.
    keyed = ApprovalLedger(
        path=str(tmp_path / "forged.jsonl"),
        anchor_path=str(tmp_path / "forged.anchor"),
        anchor_key=key,
    )
    keyed.reanchor_from_ledger()
    store = ApprovalStore(ledger=keyed)
    assert len(store) == 1  # forged grant is now under the operator's key


# ---------------------------------------------------------------------------
# Crash / fsync windows
# ---------------------------------------------------------------------------


def test_crash_ledger_newer_than_anchor_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    records = _read_records(ledger.path)
    extra = dict(records[-1])
    extra["record_type"] = "consumed"
    extra["approval_id"] = "crash-window-consumed"
    extra["previous_hash"] = records[-1]["current_hash"]
    extra["current_hash"] = HashChain.calculate(
        {k: v for k, v in extra.items() if k != "current_hash"})
    _write_records(ledger.path, records + [extra])

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_crash_partial_ledger_line_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    with open(ledger.path, "a", encoding="utf-8") as f:
        f.write('{"record_type": "gra')
        f.flush()

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_crash_partial_anchor_line_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    with open(ledger.anchor.path, "a", encoding="utf-8") as f:
        f.write('{"anchor_id": 9')
        f.flush()

    with pytest.raises((RuntimeError, Exception)):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


def test_crash_anchor_newer_than_ledger_fails_closed(tmp_path, key):
    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    assert _grant_consume(store, patch, target) is not None

    # delete the last ledger record but keep the anchor -> anchor ahead
    _write_records(ledger.path, _read_records(ledger.path)[:-1])

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=_anchored_ledger(tmp_path, key))


# ---------------------------------------------------------------------------
# Cross-binding
# ---------------------------------------------------------------------------


def test_cross_ledger_anchor_mismatch_fails_closed(tmp_path, key):
    la = _anchored_ledger(tmp_path, key, name="ledgerA.jsonl")
    sa = ApprovalStore(ledger=la)
    ta = _secret_target(tmp_path)
    pa = _make_patch(ta)
    assert _grant_consume(sa, pa, ta)

    lb = _anchored_ledger(tmp_path, key, name="ledgerB.jsonl")
    sb = ApprovalStore(ledger=lb)
    tb = _secret_target(tmp_path)
    pb = _make_patch(tb, "mode = 3\n")
    assert _grant_consume(sb, pb, tb)

    with pytest.raises(RuntimeError):
        ApprovalStore(ledger=ApprovalLedger(
            path=str(la.path),
            anchor_path=str(lb.anchor.path),
            anchor_key=key,
        ))


# ---------------------------------------------------------------------------
# Stale approval across policy change (anchored ledger in the loop)
# ---------------------------------------------------------------------------


def test_stale_approval_denied_after_policy_change_anchored(tmp_path, key):
    class AlwaysCriticalEngine(RiskEngine):
        def classify(self, patch, advisory_risk=None, advisory_confidence=None):
            return RiskEngine.classify(self, patch).__class__(
                risk_level=RiskLevel.CRITICAL,
                signals=(("policy_mutation", "always_critical"),),
            )

    class V:
        def verify(self, paths, test_targets=()):
            return VerificationResult(status="PASS", exit_code=0,
                                      stdout="", stderr="", failure_reason="")

    ledger = _anchored_ledger(tmp_path, key)
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    store.grant(patch.fingerprint(), str(target), "modify", "HIGH")

    pipe = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(approval_store=store),
            verification_executor=V(),
        ),
        risk_engine=AlwaysCriticalEngine(),
        risk_policy=RiskPolicy(),
        approval_store=store,
        scope=(str(target),),
    )
    result = pipe.execute(WorkerResult(
        task_id="n2", success=True, summary="n2", patches=(patch,)))
    assert result.failure_stage == "approval"
    assert result.success is False
