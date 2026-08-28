import pytest

from pathlib import Path

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.file_applier import FileApplier
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


def make_patch(
    target,
    original,
    updated,
    allowed_paths=None
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission J2 rollback test.",
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
        task_id="mission-j2",
        success=True,
        summary="Mission J2 worker.",
        patches=tuple(patches),
    )


# ---------------------------------------------------------------------------
# J2-01 — rollback with scope=None must be DENIED
# ---------------------------------------------------------------------------

def test_j2_01_rollback_without_scope_denied(tmp_path):

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

    ok, message = executor.rollback(patch, scope=None)

    assert ok is False

    assert "authoritative scope" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J2-02 — rollback with empty scope must be DENIED
# ---------------------------------------------------------------------------

def test_j2_02_rollback_with_empty_scope_denied(tmp_path):

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

    ok, message = executor.rollback(patch, scope=())

    assert ok is False

    assert "authoritative scope" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J2-03 — rollback target outside authoritative scope must be DENIED
# ---------------------------------------------------------------------------

def test_j2_03_rollback_outside_scope_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "SECRET\n",
        "ATTACKER WRITE\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J2-04 — rollback target inside authoritative scope ALLOWS when otherwise
#         authorized (a real applied patch at an in-scope path)
# ---------------------------------------------------------------------------

def test_j2_04_rollback_inside_scope_allows_when_authorized(tmp_path):

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

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )

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
# J2-05 — patch.allowed_paths must not expand authority during rollback
# ---------------------------------------------------------------------------

def test_j2_05_allowed_paths_cannot_expand_rollback_authority(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "SECRET\n",
        "ATTACKER WRITE\n",
        allowed_paths=(str(tmp_path),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J2-06 — forged patch targeting victim must be DENIED
# ---------------------------------------------------------------------------

def test_j2_06_forged_patch_rollback_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    forged = PatchProposal(
        path=str(victim),
        action="modify",
        reason="forged",
        old_content="FORGED WRITE\n",
        new_content="ignored\n",
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
# J2-07 — direct FileApplier.restore without authority must be DENIED
# ---------------------------------------------------------------------------

def test_j2_07_direct_restore_without_scope_denied(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    applier = FileApplier()

    ok, message = applier.restore(patch)

    assert ok is False

    assert "not authorized" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# J2-08 — direct ApplyExecutor.rollback without authority must be DENIED
# ---------------------------------------------------------------------------

def test_j2_08_direct_rollback_without_scope_denied(tmp_path):

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

    ok, message = executor.rollback(patch)

    assert ok is False

    assert "authoritative scope" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J2-09 — traversal rollback target must be DENIED
# ---------------------------------------------------------------------------

def test_j2_09_traversal_rollback_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("SECRET\n", encoding="utf-8")

    patch = make_patch(
        scope_dir / ".." / "victim.txt",
        "SECRET\n",
        "ATTACKER WRITE\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J2-10 — junction/symlink rollback escape must be DENIED where the platform
#         permits creating the link
# ---------------------------------------------------------------------------

def test_j2_10_symlink_rollback_escape_denied(tmp_path):

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

    patch = make_patch(
        link,
        "value = 1\n",
        "value = 2\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "SECRET\n"
    )


# ---------------------------------------------------------------------------
# J2-11 — legitimate rollback after legitimate apply must SUCCEED
# ---------------------------------------------------------------------------

def test_j2_11_legitimate_apply_then_rollback_succeeds(tmp_path):

    target = tmp_path / "notes.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    patch = make_patch(
        target,
        original,
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

    assert result.verification_passed is False

    assert result.rollback is not None

    assert result.rollback.success is True

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# J2-12 — rollback restores EXACT expected previous content
# ---------------------------------------------------------------------------

def test_j2_12_rollback_restores_exact_content(tmp_path):

    target = tmp_path / "sample.py"

    original = (
        "line one\n"
        "line two\n"
        "line three\n"
    )

    updated = (
        "line one\n"
        "line two CHANGED\n"
        "line three\n"
    )

    target.write_text(original, encoding="utf-8")

    patch = make_patch(
        target,
        original,
        updated,
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

    assert (
        target.read_text(encoding="utf-8")
        == updated
    )

    ok, message = executor.rollback(
        patch,
        scope=(str(tmp_path),),
    )

    assert ok is True

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# End-to-end exploit: unscoped rollback cannot write to victim
# ---------------------------------------------------------------------------

def test_j2_original_rollback_exploit_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    attacker = PatchProposal(
        path=str(victim),
        action="modify",
        reason="exploit",
        old_content="TAMPERED\n",
        new_content="ignored\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(attacker, scope=None)

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )

    applier = FileApplier()

    ok2, message2 = applier.restore(attacker)

    assert ok2 is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# Recovery path: scoped recovery rollback works, scopeless cannot exist
# ---------------------------------------------------------------------------

def test_j2_recovery_rollback_preserves_scope(tmp_path):

    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent,
    )

    from simulation.agent.worker.worker_agent import WorkerAgent

    from tests.fake_worker_analyzer import FakeWorkerAnalyzer

    from simulation.core.kernel import Kernel

    from simulation.persistence.event_store import EventStore

    from simulation.security.risk_engine import RiskEngine

    from simulation.security.risk_policy import RiskPolicy

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    class StaticWorker:

        allowed_paths = (str(target),)

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

    patch = make_patch(
        target,
        original,
        "value = 2\n",
    )

    kernel = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl"
        )
    )

    agent = build_recovery_agent(
        kernel,
        worker_executor=StaticWorker(patch),
        provider=None,
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        verification_executor=FakeVerificationExecutor(),
    )

    result = agent.chat("worker: recover")

    assert result.success is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


def test_j2_recovery_without_scope_fails_closed(tmp_path):

    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent,
    )

    from simulation.core.kernel import Kernel

    from simulation.persistence.event_store import EventStore

    from simulation.security.risk_engine import RiskEngine

    from simulation.security.risk_policy import RiskPolicy

    class ScopeLessWorker:

        def execute(self, *args, **kwargs):

            raise AssertionError(
                "Worker must not run in this probe."
            )

    kernel = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl"
        )
    )

    with pytest.raises(ValueError):

        build_recovery_agent(
            kernel,
            worker_executor=ScopeLessWorker(),
            risk_engine=RiskEngine(),
            risk_policy=RiskPolicy(),
        )


# ---------------------------------------------------------------------------
# J3-001 — rollback authenticity: a forged in-scope patch must be DENIED
# ---------------------------------------------------------------------------

def test_j3_001_forged_in_scope_rollback_denied(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    target = scope_dir / "notes.txt"

    target.write_text("REAL CONTENT\n", encoding="utf-8")

    forged = make_patch(
        target,
        "ATTACKER INJECTED\n",
        "ignored\n",
        allowed_paths=(str(scope_dir),),
    )

    executor = ApplyExecutor()

    ok, message = executor.rollback(
        forged,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert "not applied" in message

    assert (
        target.read_text(encoding="utf-8")
        == "REAL CONTENT\n"
    )


# ---------------------------------------------------------------------------
# J3-002 — rollback of a legitimately applied patch SUCCEEDS
# ---------------------------------------------------------------------------

def test_j3_002_rollback_after_legitimate_apply_succeeds(tmp_path):

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
# J3-003 — rollback of a forged patch must fail even when a different patch
#         was legitimately applied on the same executor
# ---------------------------------------------------------------------------

def test_j3_003_rollback_only_tied_to_applied_patch(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    legitimate = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
    )

    executor = ApplyExecutor()

    applied = executor.apply(
        legitimate,
        approved_decision(legitimate),
        scope=(str(tmp_path),),
    )

    assert applied.success is True

    forged = make_patch(
        target,
        "ATTACKER\n",
        "other\n",
        allowed_paths=(str(tmp_path),),
    )

    ok, message = executor.rollback(
        forged,
        scope=(str(tmp_path),),
    )

    assert ok is False

    assert "not applied" in message

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )

    ok2, _ = executor.rollback(
        legitimate,
        scope=(str(tmp_path),),
    )

    assert ok2 is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )

