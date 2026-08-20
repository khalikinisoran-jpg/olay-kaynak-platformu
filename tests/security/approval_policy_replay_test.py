"""MISSION-O.7: governance approval — policy/state replay forensic.

Question: can a valid governance approval be replayed later under a
DIFFERENT policy / state?

The apply boundary recomputes the patch risk with the CURRENT
engine/policy at apply time (single governance authority, MISSION-019)
and the approval is bound to a risk LEVEL (not a policy version). So:

- an approval whose risk binding no longer matches the CURRENT
  classification is DENIED (cannot be replayed across a policy change);
- an approval's claimed risk can never DOWNGRADE the recomputed risk
  (the boundary classifies first, the approval only gates HIGH/CRITICAL);
- the same approval cannot authorize a different patch object, a
  different fingerprint/path/action/attempt, an expired context, or a
  second apply (single-use).

Documented limitation (verified): the approval ledger is a local file
and is NOT bound to a machine/deployment identity, so a copied ledger
plus a byte-identical patch authorizes in a different environment
(stolen-governance-artifact scenario; approvals are single-use but the
artifact itself is portable).
"""

from pathlib import Path

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller import Controller
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
)
from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_result import WorkerResult
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


class PassingVerification:

    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="1 passed",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
        )


class AlwaysCriticalEngine(RiskEngine):

    """Simulates a policy mutation that upgrades every patch to CRITICAL."""

    def classify(self, patch, advisory_risk=None, advisory_confidence=None):
        return RiskEngine.classify(self, patch).__class__(
            risk_level=RiskLevel.CRITICAL,
            signals=(("policy_mutation", "always_critical"),),
        )


def _make_patch(target, original, new_content):
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="o7",
        old_content=original,
        new_content=new_content,
        allowed_paths=(str(target),),
    )


def _governed_pipeline(store, risk_engine=None, scope=()):
    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(
                approval_store=store,
            ),
            verification_executor=PassingVerification(),
        ),
        risk_engine=(risk_engine if risk_engine is not None else RiskEngine()),
        risk_policy=RiskPolicy(),
        approval_store=store,
        scope=scope,
    )


def test_low_risk_approval_cannot_exist_by_construction(tmp_path):
    """A LOW/MEDIUM approval is impossible by construction: the Approval
    contract only permits HIGH/CRITICAL (the only levels that require
    human approval). An attacker therefore cannot mint a downgraded
    approval artifact."""
    import pytest

    from simulation.agent.approval.approval import Approval

    target = tmp_path / "target.txt"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = _make_patch(target, original, "value = 2\n")

    with pytest.raises(ValueError):
        Approval.create(
            patch_fingerprint=patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level="LOW",
            attempt=1,
        )


def test_approval_cannot_replay_across_policy_upgrade(tmp_path):
    """Approval granted for HIGH; policy mutates so the same patch is
    CRITICAL. The stale HIGH approval must DENY (risk binding mismatch
    from the apply-boundary's own re-classification)."""
    target = tmp_path / "target.txt"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = _make_patch(target, original, "value = 2\n")

    store = ApprovalStore()
    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-o7",
        expires_at=3600,
    )

    pipeline = _governed_pipeline(
        store,
        risk_engine=AlwaysCriticalEngine(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="o7",
            success=True,
            summary="probe",
            patches=(patch,),
        )
    )

    assert result.success is False
    assert result.failure_stage == "approval"
    assert target.read_text(encoding="utf-8") == original


def test_fingerprint_mutation_denies(tmp_path):
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    target = secret_dir / "config.env"
    original = "mode = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = _make_patch(target, original, "mode = 2\n")
    other = _make_patch(target, original, "mode = 3\n")

    store = ApprovalStore()
    store.grant(
        patch_fingerprint=other.fingerprint(),
        path=other.path,
        action=other.action,
        risk_level="CRITICAL",
        attempt=1,
        authorizer="human-o7",
        expires_at=3600,
    )

    pipeline = _governed_pipeline(store, scope=(str(tmp_path),))
    result = pipeline.execute(
        WorkerResult(
            task_id="o7",
            success=True,
            summary="probe",
            patches=(patch,),
        )
    )

    assert result.success is False
    assert result.failure_stage == "approval"


def test_approval_single_use_across_restart(tmp_path):
    """A consumed approval stays consumed after a ledger reload."""
    target = tmp_path / "target.txt"
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = _make_patch(target, original, "value = 2\n")

    ledger_path = tmp_path / "ledger.jsonl"
    store = ApprovalStore(ledger=ApprovalLedger(path=ledger_path))
    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-o7",
        expires_at=3600,
    )

    consumed = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )
    assert consumed is not None

    reloaded = ApprovalStore(ledger=ApprovalLedger(path=ledger_path))
    assert (
        reloaded.find_valid(
            patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level="HIGH",
            attempt=1,
            patch=patch,
        )
        is None
    )


def test_stolen_ledger_artifact_is_portable_when_path_matches(tmp_path):
    """DOCUMENTED LIMITATION: the approval ledger is a local file with no
    machine/deployment binding. A copied ledger authorizes in a second
    store only when the patch is byte-identical AND at the SAME absolute
    path (the approval is path+action+fingerprint+risk+attempt bound).
    A different path is blocked by the path binding."""
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    target = secret_dir / "config.env"
    original = "mode = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = _make_patch(target, original, "mode = 2\n")
    other_path_patch = _make_patch(
        tmp_path / "other.env",
        original,
        "mode = 2\n",
    )
    (tmp_path / "other.env").write_text(original, encoding="utf-8")

    ledger_a = tmp_path / "ledger_a.jsonl"
    store_a = ApprovalStore(ledger=ApprovalLedger(path=ledger_a))
    store_a.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="CRITICAL",
        attempt=1,
        authorizer="human-o7",
        expires_at=3600,
    )

    ledger_b = tmp_path / "ledger_b.jsonl"
    ledger_b.write_text(
        ledger_a.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    store_b = ApprovalStore(ledger=ApprovalLedger(path=ledger_b))
    assert (
        store_b.find_valid(
            patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level="CRITICAL",
            attempt=1,
            patch=patch,
        )
        is not None
    )

    assert (
        store_b.find_valid(
            other_path_patch.fingerprint(),
            path=other_path_patch.path,
            action=other_path_patch.action,
            risk_level="CRITICAL",
            attempt=1,
            patch=other_path_patch,
        )
        is None
    )
