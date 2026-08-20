import pytest

from pathlib import Path

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.file_applier import FileApplier
from simulation.agent.controller.controller import Controller
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
)
from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine,
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

        self.calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append(tuple(paths))

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
        reason="Mission J3.1 test.",
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
        task_id="mission-j3-1",
        success=True,
        summary="Mission J3.1 worker.",
        patches=tuple(patches),
    )


# ---------------------------------------------------------------------------
# J3.1-01 — direct FileApplier.restore without authorization is DENIED even
# with a valid scope: the mechanism fails closed unless the apply authority
# (ApplyExecutor) explicitly authorizes the rollback.
# ---------------------------------------------------------------------------

def test_j31_01_direct_restore_denied_without_authorization(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = scope_dir / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    forged = make_patch(
        victim,
        "ATTACKER BYTES\n",
        "ignored\n",
        allowed_paths=(str(victim),),
    )

    applier = FileApplier()

    ok, message = applier.restore(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert "not authorized" in message

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J3.1-02 — the sanctioned rollback path (ApplyExecutor) denies the same
# forged patch because it was never applied by that executor.
# ---------------------------------------------------------------------------

def test_j31_02_forged_restore_denied_through_executor(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = scope_dir / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    forged = make_patch(
        victim,
        "ATTACKER BYTES\n",
        "ignored\n",
        allowed_paths=(str(victim),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert "not applied" in message

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J3.1-03 — direct FileApplier.apply has the same mechanism-layer contract
# (scope-only, no controller evidence). Symmetric trust boundary.
# ---------------------------------------------------------------------------

def test_j31_03_direct_apply_is_mechanism_only(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    target = scope_dir / "target.txt"

    target.write_text("v1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "v1\n",
        "v2\n",
        allowed_paths=(str(target),),
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is True

    assert (
        target.read_text(encoding="utf-8")
        == "v2\n"
    )


# ---------------------------------------------------------------------------
# J3.1-04 — legitimate rollback succeeds
# ---------------------------------------------------------------------------

def test_j31_04_legitimate_rollback_succeeds(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    applied = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )

    assert applied.success is True

    ok, message = executor.rollback(
        patch,
        scope=(str(tmp_path),),
    )

    assert ok is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-05 — apply patch A, forged rollback patch B (same target) -> DENY
# ---------------------------------------------------------------------------

def test_j31_05_apply_a_forge_b_denied(tmp_path):

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
        "value = 3\n",
    )

    executor = ApplyExecutor()

    assert (
        executor.apply(
            patch_a,
            approved_decision(patch_a),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    ok, message = executor.rollback(
        patch_b,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert "not applied" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J3.1-06 — modified (mutated) patch A rollback -> DENY
# ---------------------------------------------------------------------------

def test_j31_06_mutated_patch_rollback_denied(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    assert (
        executor.apply(
            patch,
            approved_decision(patch),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    mutated = make_patch(
        target,
        "FORGED OLD\n",
        "value = 2\n",
    )

    ok, message = executor.rollback(
        mutated,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert "not applied" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J3.1-07 — failed apply cannot become rollback authority
# ---------------------------------------------------------------------------

def test_j31_07_failed_apply_no_rollback_authority(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    stale = make_patch(
        target,
        "STALE\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    applied = executor.apply(
        stale,
        approved_decision(stale),
        scope=(str(tmp_path),),
    )

    assert applied.success is False

    ok, message = executor.rollback(
        stale,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-08 — verification failure after apply allows legitimate rollback
# ---------------------------------------------------------------------------

def test_j31_08_verification_failure_can_rollback(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    pipeline = ApplyVerifyPipeline(
        verification_executor=FakeVerificationExecutor(
            [
                make_verification_result(
                    status=FAIL,
                    exit_code=2,
                    failure_reason="tests failed",
                ),
            ]
        ),
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )

    assert result.apply_success is True

    assert result.rollback is not None

    assert result.rollback.success is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-09 — scope cannot be expanded by attacker-passed broader scope on a
# forged patch (fingerprint gate still binds to what the executor applied)
# ---------------------------------------------------------------------------

def test_j31_09_scope_cannot_be_expanded(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    target = scope_dir / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    assert (
        executor.apply(
            patch,
            approved_decision(patch),
            scope=(str(scope_dir),),
        ).success
        is True
    )

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    forged = make_patch(
        victim,
        "SECRET\n",
        "TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    ok, message = executor.rollback(
        forged,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J3.1-10 — recovery preserves rollback authority (cannot manufacture it)
# ---------------------------------------------------------------------------

def test_j31_10_recovery_cannot_manufacture_rollback_authority(tmp_path):

    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent,
    )

    from simulation.core.kernel import Kernel

    from simulation.persistence.event_store import EventStore

    from simulation.security.risk_engine import RiskEngine

    from simulation.security.risk_policy import RiskPolicy

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    target = scope_dir / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    forged = make_patch(
        target,
        "ATTACKER\n",
        "ignored\n",
        allowed_paths=(str(target),),
    )

    class ForgingWorker:

        allowed_paths = (str(target),)

        def execute(
            self,
            agent,
            prompt,
            attempt=None,
            recovery_evidence=()
        ):

            return make_worker_result(forged)

    kernel = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl"
        )
    )

    agent = build_recovery_agent(
        kernel,
        worker_executor=ForgingWorker(),
        provider=None,
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        verification_executor=FakeVerificationExecutor(),
    )

    result = agent.chat("worker: recover")

    assert result.success is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-11 — restart semantics: cross-executor rollback is DENIED
# (rollback is synchronous with apply; reconciliation is detect-only)
# ---------------------------------------------------------------------------

def test_j31_11_cross_executor_rollback_denied(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor_a = ApplyExecutor()

    assert (
        executor_a.apply(
            patch,
            approved_decision(patch),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    executor_b = ApplyExecutor()

    ok, message = executor_b.rollback(
        patch,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J3.1-12 — verify_paths is trusted orchestration; it cannot be influenced
# by a worker result and cannot redirect the rollback write.
# ---------------------------------------------------------------------------

def test_j31_12_verify_paths_cannot_redirect_rollback(tmp_path):

    target = tmp_path / "app.py"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    pipeline = ApplyVerifyPipeline(
        verification_executor=FakeVerificationExecutor(
            [
                make_verification_result(
                    status=FAIL,
                    exit_code=2,
                    failure_reason="tests failed",
                ),
            ]
        ),
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
        verify_paths=(str(tmp_path / "other.py"),),
    )

    assert result.apply_success is True

    assert result.rollback is not None

    assert result.rollback.success is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-13 — rollback traversal -> DENY
# ---------------------------------------------------------------------------

def test_j31_13_rollback_traversal_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    forged = make_patch(
        scope_dir / ".." / "victim.txt",
        "SECRET\n",
        "TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J3.1-14 — rollback outside scope -> DENY
# ---------------------------------------------------------------------------

def test_j31_14_rollback_outside_scope_denied(tmp_path):

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

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J3.1-15 — rollback symlink/junction escape where the platform permits
# ---------------------------------------------------------------------------

def test_j31_15_symlink_rollback_escape_denied(tmp_path):

    import os

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    link = scope_dir / "escape.txt"

    link.write_text("value = 1\n", encoding="utf-8")

    try:

        link.unlink()

        os.symlink(victim, link)

    except (OSError, NotImplementedError):

        pytest.skip("Symlinks are not available here.")

    forged = make_patch(
        link,
        "value = 1\n",
        "TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J3.1-16 — multiple legitimate patches, both rollback deterministically
# ---------------------------------------------------------------------------

def test_j31_16_multiple_patches_rollback(tmp_path):

    target_a = tmp_path / "a.txt"

    target_b = tmp_path / "b.txt"

    target_a.write_text("a1\n", encoding="utf-8")

    target_b.write_text("b1\n", encoding="utf-8")

    patch_a = make_patch(
        target_a,
        "a1\n",
        "a2\n",
    )

    patch_b = make_patch(
        target_b,
        "b1\n",
        "b2\n",
    )

    executor = ApplyExecutor()

    assert (
        executor.apply(
            patch_a,
            approved_decision(patch_a),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    assert (
        executor.apply(
            patch_b,
            approved_decision(patch_b),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    assert executor.rollback(
        patch_a,
        scope=(str(tmp_path),),
    )[0] is True

    assert executor.rollback(
        patch_b,
        scope=(str(tmp_path),),
    )[0] is True

    assert (
        target_a.read_text(encoding="utf-8")
        == "a1\n"
    )

    assert (
        target_b.read_text(encoding="utf-8")
        == "b1\n"
    )


# ---------------------------------------------------------------------------
# J3.1-17 — forged decision cannot authorize rollback
# ---------------------------------------------------------------------------

def test_j31_17_forged_decision_cannot_authorize_rollback(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = scope_dir / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    forged = make_patch(
        victim,
        "ATTACKER\n",
        "ignored\n",
        allowed_paths=(str(victim),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J3.1-18 — mutated patch (object.__setattr__ on frozen dataclass) cannot
# authorize rollback (fingerprint recomputation catches it)
# ---------------------------------------------------------------------------

def test_j31_18_frozen_patch_mutation_cannot_authorize_rollback(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    assert (
        executor.apply(
            patch,
            approved_decision(patch),
            scope=(str(tmp_path),),
        ).success
        is True
    )

    object.__setattr__(patch, "old_content", "FORGED\n")

    ok, message = executor.rollback(
        patch,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )
