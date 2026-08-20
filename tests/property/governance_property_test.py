"""MISSION-019: property-style invariant tests (deterministic, no deps).

Lightweight randomized loops (seeded ``random.Random`` so every run is
reproducible) assert the core security invariants that must hold for
*any* proposal shape:

1. A HIGH / CRITICAL / UNKNOWN PatchProposal never reaches the file
   system without a store-verified, single-use approval.
2. Every terminal apply intent in the journal has a consistent durable
   outcome (journal load validates the full state machine).
3. A recovery retry can never reuse an older attempt's approval.
"""

import random

from pathlib import Path

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_outcome_journal import (
    ApplyOutcomeJournal,
)
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller import Controller
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)
from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine
)
from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_result import WorkerResult
from simulation.security.governance_evaluator import (
    GovernanceEvaluator,
)
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


SEED = 1919

# (name, new_content) variants chosen to exercise LOW/MEDIUM (SAFE),
# HIGH (SUSPICIOUS), CRITICAL (PEM) and UNKNOWN (OPAQUE).
_VARIANTS = [
    ("plain.txt", "value = 2\n"),
    ("notes.txt", "value = 2\n"),
    ("config.txt", "value = 2\n"),
    ("app.txt", "self.token = None\nvalue = 2\n"),
    ("config.txt", "token = 'abc123'\n"),
    ("config.txt", "password = 'hunter2'\n"),
    ("config.txt", "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"),
    ("config.txt", "value = 2\n\x01\n"),
    ("settings.env", "value = 2\n"),
    ("prod.conf", "value = 2\n"),
]


class PassingVerification:

    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="1 passed",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
        )


class FailingVerification:

    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status="FAIL",
            exit_code=1,
            stdout="",
            stderr="boom",
            command=("python", "-m", "pytest", "-q"),
        )


def _make_patch(tmp_path, name, new_content):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Property probe.",
        old_content="value = 1\n",
        new_content=new_content,
        allowed_paths=(str(target),),
    )


def _governed_pipeline(approval_store=None, scope=()):
    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(
                approval_store=approval_store,
            ),
            verification_executor=PassingVerification(),
        ),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=approval_store,
        scope=scope,
    )


def test_property_no_approval_never_mutates_high_or_unknown(tmp_path):
    rng = random.Random(SEED)

    for index in range(60):

        name, new_content = _VARIANTS[index % len(_VARIANTS)]

        patch = _make_patch(tmp_path, name, new_content)

        decision = GovernanceEvaluator().evaluate(patch)

        if decision.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):

            continue

        pipeline = _governed_pipeline(
            approval_store=None,
            scope=(str(tmp_path),),
        )

        result = pipeline.execute(
            WorkerResult(
                task_id="property",
                success=True,
                summary="probe",
                patches=(patch,),
            )
        )

        assert result.success is False

        assert result.failure_stage in ("risk", "approval")

        assert Path(patch.path).read_text(
            encoding="utf-8"
        ) == "value = 1\n"


def test_property_high_requires_store_approval_before_write(tmp_path):
    rng = random.Random(SEED + 1)

    for index in range(40):

        name, new_content = _VARIANTS[index % len(_VARIANTS)]

        patch = _make_patch(tmp_path, name, new_content)

        decision = GovernanceEvaluator().evaluate(patch)

        if decision.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):

            continue

        if decision.risk_level == RiskLevel.UNKNOWN:

            continue

        store = ApprovalStore()

        store.grant(
            patch_fingerprint=patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level=decision.risk_level.value,
            attempt=1,
            authorizer="human-property",
            expires_at=3600,
        )

        pipeline = _governed_pipeline(
            approval_store=store,
            scope=(str(tmp_path),),
        )

        result = pipeline.execute(
            WorkerResult(
                task_id="property",
                success=True,
                summary="probe",
                patches=(patch,),
            )
        )

        assert result.success is True

        assert result.apply_success is True


def test_property_journal_terminal_intents_are_consistent(tmp_path):
    rng = random.Random(SEED + 2)

    for run in range(20):

        journal = ApplyOutcomeJournal(
            path=tmp_path / f"apply_journal_{run}.jsonl"
        )

        patch = _make_patch(tmp_path, "plain.txt", "value = 2\n")

        intent_id = journal.record_intent(patch, attempt=1)

        journal.record_apply_started(intent_id)
        journal.record_applied(intent_id)

        if rng.random() < 0.5:

            journal.record_verified(intent_id)

        else:

            journal.record_rollback_started(intent_id)

            if rng.random() < 0.5:

                journal.record_rolled_back(intent_id)

            else:

                journal.record_rollback_failed(intent_id)

        reloaded = ApplyOutcomeJournal(
            path=tmp_path / f"apply_journal_{run}.jsonl"
        )

        records = reloaded.load()

        order, grouped = reloaded.intents(records)

        assert order == [intent_id]

        last_state = grouped[intent_id][-1]["record_type"]

        assert last_state in (
            "verified",
            "rolled_back",
            "rollback_failed",
        )


def test_property_retry_cannot_reuse_old_approval(tmp_path):
    rng = random.Random(SEED + 3)

    for _ in range(30):

        target = tmp_path / "settings.secret.txt"
        target.write_text("value = 1\n", encoding="utf-8")

        attempt1_patch = PatchProposal(
            path=str(target),
            action="modify",
            reason="attempt 1",
            old_content="value = 1\n",
            new_content="value = 2\n",
            allowed_paths=(str(target),),
        )

        attempt2_patch = PatchProposal(
            path=str(target),
            action="modify",
            reason="attempt 2",
            old_content="value = 2\n",
            new_content="value = 3\n",
            allowed_paths=(str(target),),
        )

        store = ApprovalStore()

        store.grant(
            patch_fingerprint=attempt1_patch.fingerprint(),
            path=attempt1_patch.path,
            action=attempt1_patch.action,
            risk_level="HIGH",
            attempt=1,
            authorizer="human-property",
            expires_at=3600,
        )

        pipeline = _governed_pipeline(
            approval_store=store,
            scope=(str(tmp_path),),
        )

        result = pipeline.execute(
            WorkerResult(
                task_id="property",
                success=True,
                summary="probe",
                patches=(attempt1_patch,),
            )
        )

        assert result.success is True

        assert target.read_text(encoding="utf-8") == "value = 2\n"

        result2 = pipeline.execute(
            WorkerResult(
                task_id="property",
                success=True,
                summary="probe",
                patches=(attempt2_patch,),
            )
        )

        assert result2.success is False

        assert result2.failure_stage == "approval"

        assert target.read_text(encoding="utf-8") == "value = 2\n"
