import pytest

from pathlib import Path

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import (
    ControllerDecision,
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.validation_result import ValidationResult
from simulation.agent.worker.worker_result import WorkerResult


class FakeVerificationExecutor:

    def __init__(self, results=None):

        self.results = (
            list(results)
            if results is not None
            else [make_verification_result()]
        )

    def verify(self, paths, test_targets=()):

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)

    def verify_python_compile(self, paths):

        return self.verify(paths)


def make_verification_result(
    status=PASS,
    exit_code=0,
    failure_reason=""
):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout="1 passed" if status == PASS else "1 failed",
        stderr="",
        command=("venv-python", "-m", "pytest", "-q"),
        failure_reason=failure_reason,
    )


def make_patch(target, original, updated, allowed_paths=None):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission J3 test.",
        old_content=original,
        new_content=updated,
        allowed_paths=tuple(
            allowed_paths
            if allowed_paths is not None
            else (str(target),)
        ),
    )


def approved_decision(patch):

    return Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )


def make_worker_result(*patches):

    return WorkerResult(
        task_id="mission-j3",
        success=True,
        summary="Mission J3 worker.",
        patches=tuple(patches),
    )


# ---------------------------------------------------------------------------
# J3-A — forged patch (in-scope target, attacker content) through the full
#        pipeline must be DENIED at validation (never applied, never written)
# ---------------------------------------------------------------------------

def test_j3a_forged_in_scope_patch_denied_by_pipeline(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    target = scope_dir / "notes.txt"

    target.write_text("REAL\n", encoding="utf-8")

    forged = make_patch(
        target,
        "ATTACKER\n",
        "ignored\n",
        allowed_paths=(str(scope_dir),),
    )

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(),
        ),
        scope=(str(scope_dir),),
    )

    result = pipeline.execute(make_worker_result(forged))

    assert result.success is False

    assert result.apply_success is False

    assert (
        target.read_text(encoding="utf-8")
        == "REAL\n"
    )


# ---------------------------------------------------------------------------
# J3-B — valid decision + changed patch fingerprint must be DENIED at apply
# ---------------------------------------------------------------------------

def test_j3b_decision_for_different_patch_denied(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch_a = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    patch_b = make_patch(
        target,
        "value = 1\n",
        "value = 99\n",
    )

    decision = approved_decision(patch_a)

    executor = ApplyExecutor()

    result = executor.apply(
        patch_b,
        decision,
        scope=(str(tmp_path),),
    )

    assert result.success is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3-C — retry cannot turn a validation DENY into an ALLOW
# ---------------------------------------------------------------------------

def test_j3c_retry_cannot_convert_deny_to_allow(tmp_path):

    from simulation.agent.recovery.bounded_recovery_engine import (
        BoundedRecoveryEngine,
    )

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    forged = make_patch(
        victim,
        "SECRET\n",
        "TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    class ForgingWorker:

        def __init__(self, patch):

            self.patch = patch

            self.calls = 0

        def execute(
            self,
            agent,
            prompt,
            attempt=None,
            recovery_evidence=()
        ):

            self.calls += 1

            return make_worker_result(self.patch)

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(),
        ),
        scope=(str(scope_dir),),
    )

    engine = BoundedRecoveryEngine(
        worker=ForgingWorker(forged),
        worker_pipeline=pipeline,
        max_attempts=3,
    )

    result = engine.execute(agent=None, prompt="recover")

    assert result.terminal_failure is True

    assert result.failure_stage == "validation"

    assert engine.worker.calls == 1

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J3-D — recovery cannot reuse a consumed/rolled-back patch as a new write
# ---------------------------------------------------------------------------

def test_j3d_recovery_duplicate_fingerprint_denied(tmp_path):

    from simulation.agent.recovery.bounded_recovery_engine import (
        BoundedRecoveryEngine,
    )

    target = tmp_path / "app.py"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    class FixedWorker:

        def __init__(self, patch):

            self.patch = patch

            self.calls = 0

        def execute(
            self,
            agent,
            prompt,
            attempt=None,
            recovery_evidence=()
        ):

            self.calls += 1

            return make_worker_result(self.patch)

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(
                [
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        failure_reason="first fails",
                    ),
                    make_verification_result(),
                ]
            ),
        ),
        scope=(str(tmp_path),),
    )

    engine = BoundedRecoveryEngine(
        worker=FixedWorker(patch),
        worker_pipeline=pipeline,
        max_attempts=3,
    )

    result = engine.execute(agent=None, prompt="recover")

    assert result.terminal_failure is True

    assert "Duplicate proposal fingerprint" in result.failure_reason

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )
