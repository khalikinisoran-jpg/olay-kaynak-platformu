"""MISSION-019: single deterministic governance authority tests.

These tests prove the three governed layers (pipeline gate, approval
console, apply boundary) share ONE ``GovernanceEvaluator`` and therefore
cannot diverge on risk classification, while every MISSION-014 /
MISSION-018A / MISSION-018B invariant is preserved:

- a HIGH patch that a *custom* engine classifies HIGH is never silently
  downgraded to LOW by a differently-constructed default engine at the
  apply boundary (engine-substitution drift eliminated);
- HIGH / CRITICAL / UNKNOWN applies still require a store-verified,
  single-use approval; a missing store is a denial (MISSION-018B);
- LOW / MEDIUM keep the typed-decision + fingerprint contract.
"""

import pytest

from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import (
    ControllerDecision
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)
from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_result import WorkerResult
from simulation.security.governance_evaluator import (
    GovernanceDecision,
    GovernanceEvaluator,
)
from simulation.security.risk_engine import (
    RiskAssessment,
)
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


class AlwaysHighEngine:

    """A deterministic custom engine that classifies everything HIGH.

    Used to prove that when a caller wires this engine into the pipeline,
    the apply boundary keeps using THIS engine (not a fresh default one),
    so a patch can never be downgraded to LOW/MEDIUM at the boundary.
    """

    def classify(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ):

        return RiskAssessment(
            risk_level=RiskLevel.HIGH,
            reason="Custom engine: everything HIGH.",
        )


class PassingVerification:

    def verify(self, paths, test_targets=()):

        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="1 passed",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
        )


def make_patch(tmp_path, name="notes.txt"):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Governance test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def approved_decision(patch, approval_id=""):
    return ControllerDecision(
        approved=True,
        reason="Governance test approval.",
        patch_fingerprint=patch.fingerprint(),
        approval_id=approval_id,
    )


def test_evaluator_is_deterministic():
    first = GovernanceEvaluator().evaluate(
        make_patch_direct()
    )
    second = GovernanceEvaluator().evaluate(
        make_patch_direct()
    )
    assert first.risk_level == second.risk_level
    assert first.allowed == second.allowed
    assert first.requires_human_approval == (
        second.requires_human_approval
    )
    assert first.verification_depth == second.verification_depth


def make_patch_direct():
    return PatchProposal(
        path="C:/tmp/notes.txt",
        action="modify",
        reason="Governance test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=("C:/tmp",),
    )


def test_evaluator_bundles_assessment_and_policy_decision():
    decision = GovernanceEvaluator().evaluate(
        make_patch_direct()
    )
    assert isinstance(decision, GovernanceDecision)
    assert decision.assessment.risk_level == decision.risk_level
    assert decision.allowed is decision.policy.allowed


def test_evaluator_unknown_yields_deny(tmp_path):
    patch = make_patch(tmp_path)
    always_unknown = AlwaysHighEngine()

    class UnknownEngine(AlwaysHighEngine):
        def classify(self, patch, advisory_risk=None, advisory_confidence=None):
            return RiskAssessment(
                risk_level=RiskLevel.UNKNOWN,
                reason="unknown",
            )

    decision = GovernanceEvaluator(
        risk_engine=UnknownEngine(),
        risk_policy=RiskPolicy(),
    ).evaluate(patch)
    assert decision.risk_level == RiskLevel.UNKNOWN
    assert decision.allowed is False


def test_authorize_apply_high_requires_store_approval(tmp_path):
    patch = make_patch(tmp_path)
    evaluator = GovernanceEvaluator(
        risk_engine=AlwaysHighEngine(),
    )
    store = ApprovalStore()
    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-test",
        expires_at=3600,
    )
    released = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )
    decision = approved_decision(patch, released.approval_id)

    assert evaluator.authorize_apply(decision, patch, store) is True

    forged = approved_decision(patch, "agent-fabricated-id")
    assert evaluator.authorize_apply(forged, patch, store) is False

    assert evaluator.authorize_apply(decision, patch, None) is False

    no_id = approved_decision(patch, "")
    assert evaluator.authorize_apply(no_id, patch, store) is False


def test_authorize_apply_high_without_store_is_denial(tmp_path):
    patch = make_patch(tmp_path)
    evaluator = GovernanceEvaluator(
        risk_engine=AlwaysHighEngine(),
    )
    decision = approved_decision(patch, "any-id")
    assert evaluator.authorize_apply(decision, patch, None) is False


def test_pipeline_binds_shared_governance_into_apply_boundary(tmp_path):
    """Engine-substitution drift is eliminated by construction.

    A custom engine wired into the pipeline must be the exact instance
    the apply boundary uses after ``_bind_approval_authority``.
    """

    patch = make_patch(tmp_path)
    custom_engine = AlwaysHighEngine()
    store = ApprovalStore()

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=PassingVerification(),
        ),
        risk_engine=custom_engine,
        risk_policy=RiskPolicy(),
        approval_store=store,
    )

    authorization = (
        pipeline.apply_verify_pipeline.apply_executor.authorization
    )

    assert authorization.governance.risk_engine is custom_engine

    assert authorization.governance.risk_policy is pipeline.risk_policy


def test_pipeline_with_custom_engine_requires_approval_for_high(tmp_path):
    """A patch the default engine would call LOW must be treated HIGH by
    BOTH the pipeline gate and the apply boundary when a custom engine
    classifies it HIGH, so no divergence can downgrade it."""

    target = tmp_path / "notes.txt"
    target.write_text("value = 1\n", encoding="utf-8")
    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Governance test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )

    store = ApprovalStore()
    custom_engine = AlwaysHighEngine()

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=PassingVerification(),
        ),
        risk_engine=custom_engine,
        risk_policy=RiskPolicy(),
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="governance",
            success=True,
            summary="probe",
            patches=(patch,),
        )
    )

    assert result.success is False
    assert result.failure_stage == "approval"
    assert target.read_text(encoding="utf-8") == "value = 1\n"

    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-test",
        expires_at=3600,
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="governance",
            success=True,
            summary="probe",
            patches=(patch,),
        )
    )

    assert result.success is True
    assert result.apply_success is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_gateway_reuses_shared_evaluator():
    from simulation.agent.approval.approval_console import (
        ConsoleApprovalGateway,
    )

    store = ApprovalStore()
    custom_engine = AlwaysHighEngine()
    evaluator = GovernanceEvaluator(
        risk_engine=custom_engine,
    )

    gateway = ConsoleApprovalGateway(
        store=store,
        governance=evaluator,
    )

    assert gateway.governance is evaluator
    assert gateway.risk_engine is custom_engine


# ---- RT-1 (G1): modifying an EXISTING verification test module
# requires human authorization ----


def _rt1_patch(tmp_path, name="test_guard.py", create=True):
    target = tmp_path / name
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("assert True\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="RT-1 G1 gate test.",
        old_content="assert True\n",
        new_content="assert False\n",
        allowed_paths=(str(tmp_path),),
    )


def test_modifying_existing_test_module_requires_human_approval(tmp_path):
    decision = GovernanceEvaluator().evaluate(
        _rt1_patch(tmp_path, name="test_guard.py")
    )
    assert decision.allowed is True
    assert decision.requires_human_approval is True
    assert decision.risk_level == RiskLevel.HIGH
    assert any(
        signal[0] == "modifies_existing_test_module"
        for signal in decision.assessment.signals
    )


def test_modifying_existing_conftest_requires_human_approval(tmp_path):
    decision = GovernanceEvaluator().evaluate(
        _rt1_patch(tmp_path, name="conftest.py")
    )
    assert decision.requires_human_approval is True
    assert decision.risk_level == RiskLevel.HIGH


def test_nonexistent_test_module_is_not_elevated(tmp_path):
    decision = GovernanceEvaluator().evaluate(
        _rt1_patch(tmp_path, name="test_new.py", create=False)
    )
    assert decision.requires_human_approval is False
    assert decision.risk_level != RiskLevel.HIGH
    assert not any(
        signal[0] == "modifies_existing_test_module"
        for signal in decision.assessment.signals
    )


def test_modifying_existing_non_test_file_is_not_elevated(tmp_path):
    decision = GovernanceEvaluator().evaluate(
        _rt1_patch(tmp_path, name="helper_impl.py")
    )
    assert decision.requires_human_approval is False
    assert not any(
        signal[0] == "modifies_existing_test_module"
        for signal in decision.assessment.signals
    )
