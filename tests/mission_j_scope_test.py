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
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent,
)
from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_result import WorkerResult
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


class FakeVerificationExecutor:

    def verify(self, paths, test_targets=()):

        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="ok",
            stderr="",
            command=(),
            failure_reason="",
        )

    def verify_python_compile(self, paths):

        return self.verify(paths)


def make_patch(
    target,
    original,
    updated,
    allowed_paths=None
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission J test.",
        old_content=original,
        new_content=updated,
        allowed_paths=tuple(
            allowed_paths
            if allowed_paths is not None
            else (str(target),)
        ),
    )


def make_worker_result(*patches):

    return WorkerResult(
        task_id="mission-j",
        success=True,
        summary="Mission J worker.",
        patches=tuple(patches),
    )


def make_decision(patch):

    return ControllerDecision(
        approved=True,
        reason="Mission J controller.",
        patch_fingerprint=patch.fingerprint(),
    )


def build_pipeline(scope=(), verify=None):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=(
                verify
                if verify is not None
                else FakeVerificationExecutor()
            ),
        ),
        scope=scope,
    )


# ---------------------------------------------------------------------------
# J01 — unscoped pipeline must not be apply-capable
# ---------------------------------------------------------------------------

def test_j01_unscoped_pipeline_cannot_apply(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    pipeline = build_pipeline()  # NO authoritative scope

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J02 — build_recovery_agent must not silently create an apply-capable
#       unscoped runtime
# ---------------------------------------------------------------------------

def test_j02_missing_worker_scope_cannot_build_apply_capable_runtime(
    tmp_path
):

    class ScopeLessWorkerExecutor:

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
            worker_executor=ScopeLessWorkerExecutor(),
            risk_engine=RiskEngine(),
            risk_policy=RiskPolicy(),
        )


# ---------------------------------------------------------------------------
# J03 — malicious proposal.allowed_paths cannot expand authority
# ---------------------------------------------------------------------------

def test_j03_proposal_cannot_expand_authoritative_scope(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    pipeline = build_pipeline(scope=(str(scope_dir),))

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J04 — forged WorkerResult cannot bypass scope
# ---------------------------------------------------------------------------

def test_j04_forged_worker_result_cannot_bypass_scope(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    forged_patch = PatchProposal(
        path=str(victim),
        action="modify",
        reason="forged",
        old_content="ORIGINAL\n",
        new_content="TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    forged = WorkerResult(
        task_id="forged",
        success=True,
        summary="forged result",
        patches=(forged_patch,),
    )

    pipeline = build_pipeline(scope=(str(scope_dir),))

    result = pipeline.execute(forged)

    assert result.success is False

    assert result.apply_success is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J05 — direct ApplyExecutor invocation without scope fails closed
# ---------------------------------------------------------------------------

def test_j05_direct_apply_without_scope_fails_closed(tmp_path):

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    result = ApplyExecutor().apply(
        patch,
        make_decision(patch),
    )

    assert result.success is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


def test_j05b_direct_file_applier_without_scope_fails_closed(tmp_path):

    from simulation.agent.apply.file_applier import FileApplier

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    ok, _ = FileApplier().apply(patch)

    assert ok is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


# ---------------------------------------------------------------------------
# J06 — default Agent stays proposal-only
# ---------------------------------------------------------------------------

def test_j06_default_agent_remains_proposal_only(tmp_path):

    from simulation.agent.agent import Agent

    kernel = Kernel(
        EventStore(
            path=tmp_path / "events.jsonl"
        )
    )

    agent = Agent(kernel)

    assert agent.worker_pipeline is None

    assert agent.recovery_engine is None


# ---------------------------------------------------------------------------
# J07 — normal governed scoped execution still succeeds
# ---------------------------------------------------------------------------

def test_j07_scoped_governed_execution_succeeds(tmp_path):

    target = tmp_path / "notes.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = make_patch(
        target,
        "value = 1\n",
        "value = 2\n",
        allowed_paths=(str(target),),
    )

    pipeline = build_pipeline(scope=(str(target),))

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    assert result.apply_success is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# J08 — traversal protection remains intact under scoped pipeline
# ---------------------------------------------------------------------------

def test_j08_traversal_denied_under_scoped_pipeline(tmp_path):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    outside = tmp_path / "secret.txt"

    outside.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        scope_dir / ".." / "secret.txt",
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(scope_dir),),
    )

    pipeline = build_pipeline(scope=(str(scope_dir),))

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert (
        outside.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )
