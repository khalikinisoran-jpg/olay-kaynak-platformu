"""Create-action (new-file) tests.

New-file product support: a governed ``create`` action that reuses the
existing mutation/governance chain without any new identity mechanism.

Invariants pinned here:

- fingerprint semantics unchanged (create is just action="create" with
  the canonical old_content="" marker in the existing schema)
- governance needs NO new rule: create classifies HIGH -> requires
  human approval (existing RiskEngine behavior)
- create validation: target must NOT exist, parent must exist,
  old_content must be exactly "", scope/traversal checks unchanged
- create apply: atomic write through the existing primitive, target
  re-checked at apply time (stale create fail-closed), read-back
  verified
- create rollback (MISSION-J2/J3 invariants): authorized + applied
  registry + scope still required; a created file is deleted ONLY if
  its content still matches the approved new_content exactly --
  unknown/drifted content is NEVER auto-deleted (fail-closed)
- no approval -> DENY; consumed/expired approval -> DENY; approval is
  never transferred between fingerprints
"""
import json
import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.file_applier import FileApplier
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller import Controller
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline,
)
from simulation.agent.evidence.worker_events import WorkerEventType
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.validation_result import ValidationResult
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy

from tanuq import agent_adapter
from tanuq.config import init_workspace
from tanuq.runtime import load_environment
from tanuq.verification_profile import select_test_targets


# ---------------------------------------------------------------------------
# Shared helpers (mission-J2 style)
# ---------------------------------------------------------------------------


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


def make_create(
    target,
    content="created content\n",
    allowed_paths=None,
    old_content="",
):
    return PatchProposal(
        path=str(target),
        action="create",
        reason="create action test",
        old_content=old_content,
        new_content=content,
        allowed_paths=tuple(
            allowed_paths
            if allowed_paths is not None
            else ()
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


def approved_high_decision(patch, risk_level="HIGH", **grant_overrides):
    """A store-backed approval + decision for a HIGH create patch.

    Create classifies HIGH, so the apply boundary (MISSION-018B)
    requires a real ApprovalStore grant bound to this exact patch; the
    returned store must be wired into the ApplyExecutor under test.
    """
    store = ApprovalStore()
    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=1,
        authorizer="human-test",
        **grant_overrides,
    )
    approval = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=1,
        patch=patch,
    )
    assert approval is not None, "grant+find_valid must succeed in test setup"
    decision = Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
        approval,
    )
    return decision, store


@pytest.fixture
def env(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)
    init_workspace(ws)
    return load_environment(ws)


# ---------------------------------------------------------------------------
# Validation (PatchValidator)
# ---------------------------------------------------------------------------


def test_create_validation_valid(tmp_path):
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / "notes.txt"),
        scope=(str(tmp_path),),
    )
    assert ok is True


def test_create_validation_existing_target_denied(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("existing", encoding="utf-8")
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(target),
        scope=(str(tmp_path),),
    )
    assert ok is False
    assert "already exists" in message


def test_create_validation_parent_missing_denied(tmp_path):
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / "missing_dir" / "notes.txt"),
        scope=(str(tmp_path),),
    )
    assert ok is False
    assert "parent directory" in message


def test_create_validation_outside_scope_denied(tmp_path):
    inside = tmp_path / "scope"
    inside.mkdir()
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / "outside.txt"),
        scope=(str(inside),),
    )
    assert ok is False


def test_create_validation_traversal_denied(tmp_path):
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / ".." / "escape.txt"),
        scope=(str(tmp_path),),
    )
    assert ok is False


def test_create_validation_old_content_nonempty_denied(tmp_path):
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / "notes.txt", old_content="x"),
        scope=(str(tmp_path),),
    )
    assert ok is False
    assert 'exactly ""' in message


def test_create_validation_empty_new_content_denied(tmp_path):
    validator = PatchValidator()
    ok, message = validator.validate(
        make_create(tmp_path / "notes.txt", content=""),
        scope=(str(tmp_path),),
    )
    assert ok is False
    assert "does not contain a change" in message


# ---------------------------------------------------------------------------
# Apply (FileApplier)
# ---------------------------------------------------------------------------


def test_create_apply_writes_file(tmp_path):
    applier = FileApplier()
    target = tmp_path / "notes.txt"
    ok, message = applier.apply(
        make_create(target),
        scope=(str(tmp_path),),
    )
    assert ok is True
    assert target.read_text(encoding="utf-8") == "created content\n"


def test_create_apply_atomic_no_temp_leftovers(tmp_path):
    applier = FileApplier()
    target = tmp_path / "notes.txt"
    ok, _ = applier.apply(
        make_create(target),
        scope=(str(tmp_path),),
    )
    assert ok is True
    leftovers = [
        p.name for p in tmp_path.iterdir()
        if p.name.startswith(".esp-tmp-")
    ]
    assert leftovers == []


def test_create_apply_target_appeared_at_apply_time_denied(tmp_path):
    target = tmp_path / "notes.txt"
    validator = PatchValidator()
    ok, _ = validator.validate(
        make_create(target),
        scope=(str(tmp_path),),
    )
    assert ok is True
    target.write_text("raced", encoding="utf-8")
    applier = FileApplier()
    applied, message = applier.apply(
        make_create(target),
        scope=(str(tmp_path),),
    )
    assert applied is False
    assert "already exists" in message
    assert target.read_text(encoding="utf-8") == "raced"


def test_create_apply_parent_missing_denied(tmp_path):
    applier = FileApplier()
    ok, message = applier.apply(
        make_create(tmp_path / "missing" / "notes.txt"),
        scope=(str(tmp_path),),
    )
    assert ok is False
    assert "parent directory" in message
    assert not (tmp_path / "missing").exists()


def test_create_apply_outside_scope_denied(tmp_path):
    inside = tmp_path / "scope"
    inside.mkdir()
    applier = FileApplier()
    ok, _ = applier.apply(
        make_create(tmp_path / "outside.txt"),
        scope=(str(inside),),
    )
    assert ok is False
    assert not (tmp_path / "outside.txt").exists()


# ---------------------------------------------------------------------------
# Rollback (ApplyExecutor -> FileApplier.restore, MISSION-J2/J3 style)
# ---------------------------------------------------------------------------


def test_create_rollback_deletes_created_file(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    applied = executor.apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert applied.success is True
    ok, message = executor.rollback(patch, scope=(str(tmp_path),))
    assert ok is True
    assert not target.exists()


def test_create_rollback_modified_content_fail_closed(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    applied = executor.apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert applied.success is True
    target.write_text("tampered", encoding="utf-8")
    ok, message = executor.rollback(patch, scope=(str(tmp_path),))
    assert ok is False
    assert "unknown" in message
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "tampered"


def test_create_rollback_idempotent_when_already_gone(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    applied = executor.apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert applied.success is True
    target.unlink()
    ok, message = executor.rollback(patch, scope=(str(tmp_path),))
    assert ok is True
    assert "pre-apply state" in message


def test_create_rollback_without_apply_denied(tmp_path):
    patch = make_create(tmp_path / "notes.txt")
    executor = ApplyExecutor()
    ok, message = executor.rollback(patch, scope=(str(tmp_path),))
    assert ok is False
    assert "not applied" in message
    assert not (tmp_path / "notes.txt").exists()


def test_create_rollback_without_scope_denied(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    applied = executor.apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert applied.success is True
    ok, message = executor.rollback(patch, scope=None)
    assert ok is False
    assert "authoritative scope" in message
    assert target.exists()


# ---------------------------------------------------------------------------
# Pipeline level: apply -> verify FAIL -> rollback
# ---------------------------------------------------------------------------


def test_create_pipeline_verification_failure_rolls_back_to_absence(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    pipeline = ApplyVerifyPipeline(
        apply_executor=executor,
        verification_executor=FakeVerificationExecutor(
            [make_verification_result(FAIL, 1)]
        ),
    )
    result = pipeline.execute(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert result.success is False
    assert result.verification_ran is True
    assert result.rollback is not None
    assert result.rollback.success is True
    assert not target.exists()


def test_create_pipeline_rollback_failure_is_terminal(tmp_path):
    target = tmp_path / "notes.txt"
    patch = make_create(target)
    decision, store = approved_high_decision(patch)
    executor = ApplyExecutor(approval_store=store)
    pipeline = ApplyVerifyPipeline(
        apply_executor=executor,
        verification_executor=FakeVerificationExecutor(
            [make_verification_result(FAIL, 1)]
        ),
    )
    result = pipeline.execute(
        patch,
        decision,
        scope=(str(tmp_path),),
    )
    assert result.success is False
    assert result.rollback.success is True
    target.write_text("drifted after the fact", encoding="utf-8")
    ok, message = executor.rollback(patch, scope=(str(tmp_path),))
    assert ok is False
    assert target.exists()


def test_create_pipeline_wrong_fingerprint_apply_denied(tmp_path):
    target = tmp_path / "notes.txt"
    other = tmp_path / "other.txt"
    other.write_text("existing", encoding="utf-8")
    other_patch = PatchProposal(
        path=str(other),
        action="modify",
        reason="decoy",
        old_content="existing",
        new_content="changed",
        allowed_paths=(str(tmp_path),),
    )
    patch = make_create(target)
    executor = ApplyExecutor()
    applied = executor.apply(
        patch,
        approved_decision(other_patch),
        scope=(str(tmp_path),),
    )
    assert applied.success is False
    assert "does not match this patch" in applied.message
    assert not target.exists()


# ---------------------------------------------------------------------------
# Governance: create is HIGH and requires human approval (no new rule)
# ---------------------------------------------------------------------------


def test_create_risk_is_high_and_requires_approval(tmp_path):
    patch = make_create(tmp_path / "notes.txt")
    assessment = RiskEngine().classify(patch)
    assert assessment.risk_level == RiskLevel.HIGH
    decision = RiskPolicy().decide(assessment)
    assert decision.allowed is True
    assert decision.requires_human_approval is True


# ---------------------------------------------------------------------------
# Adapter level E2E: propose -> approve -> execute -> evidence
# ---------------------------------------------------------------------------


def test_adapter_create_with_nonempty_old_content_rejected(env):
    payload = json.dumps({
        "path": str(env.workspace / "notes.txt"),
        "action": "create",
        "old_content": "not empty",
        "new_content": "content",
    })
    with pytest.raises(agent_adapter.ProtocolError):
        agent_adapter.propose(env, payload)


def test_adapter_create_proposal_requires_approval_and_is_pending(env):
    target = env.workspace / "notes.txt"
    payload = json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    })
    response = agent_adapter.propose(env, payload)
    proposal = response["proposals"][0]
    assert proposal["state"] == "APPROVAL_REQUIRED"
    assert proposal["risk"] == "HIGH"
    assert proposal["approval_required"] is True
    assert not target.exists()
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 1
    assert records[0]["action"] == "create"
    assert records[0]["old_content"] == ""


def test_adapter_create_without_approval_denied_fail_closed(env):
    target = env.workspace / "notes.txt"
    agent_adapter.propose(env, json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    }))
    result = agent_adapter.execute(env)
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "approval"
    assert not target.exists()


def test_adapter_create_full_governed_chain_verified(env):
    target = env.workspace / "notes.txt"
    payload = json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    })
    proposed = agent_adapter.propose(env, payload)
    assert proposed["proposals"][0]["state"] == "APPROVAL_REQUIRED"
    granted = agent_adapter.approve(env)
    assert granted["count"] == 1
    result = agent_adapter.execute(env)
    assert result["terminal"] == "VERIFIED"
    assert result["apply_success"] is True
    assert result["verification_passed"] is True
    assert target.read_text(encoding="utf-8") == "created\n"
    assert result["pending_count"] == 0


def test_adapter_create_consumed_approval_replay_denied(env):
    target = env.workspace / "notes.txt"
    patch = make_create(target, content="created\n")
    agent_adapter.propose(env, json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    }))
    assert agent_adapter.approve(env)["count"] == 1
    first = agent_adapter.execute(env)
    assert first["terminal"] == "VERIFIED"
    # Genuine consumed-approval replay: the created file is removed so
    # the same create proposal is validation-valid again, but the
    # single-use approval was already consumed by the first apply.
    target.unlink()
    from tanuq.pending import save_pending
    save_pending(env.workspace, [patch])
    replay = agent_adapter.execute(env)
    assert replay["terminal"] == "DENIED"
    assert replay["failure_stage"] == "approval"
    assert not target.exists()


def test_adapter_create_expired_approval_denied(env):
    target = env.workspace / "notes.txt"
    patch = make_create(target, content="created\n")
    agent_adapter.propose(env, json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    }))
    env.approval_store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action="create",
        risk_level="high",
        attempt=1,
        authorizer="human-operator",
        expires_at=-60,
    )
    result = agent_adapter.execute(env)
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "approval"
    assert not target.exists()


def test_adapter_create_evidence_records_create_action(env):
    target = env.workspace / "notes.txt"
    agent_adapter.propose(env, json.dumps({
        "path": str(target),
        "action": "create",
        "old_content": "",
        "new_content": "created\n",
    }))
    pending_fp = agent_adapter.load_pending(env.workspace)[0]["fingerprint"]
    agent_adapter.approve(env)
    agent_adapter.execute(env)
    proposed = [
        event for event in env.kernel.events
        if event.event_type == WorkerEventType.PATCH_PROPOSED
    ]
    assert proposed, "no PATCH_PROPOSED evidence recorded"
    for event in proposed:
        assert event.payload["action"] == "create"
    validated = [
        event for event in env.kernel.events
        if event.event_type == WorkerEventType.PATCH_VALIDATED
    ]
    assert validated, "no PATCH_VALIDATED evidence recorded"
    # The validated-event payload does not repeat the action field;
    # the patch fingerprint it records is content-bound and therefore
    # pins action="create" cryptographically.
    for event in validated:
        assert event.payload["patch_fingerprint"] == pending_fp


# ---------------------------------------------------------------------------
# Verification target integrity (RT-1 R1) for created test modules
# ---------------------------------------------------------------------------


def test_created_test_module_never_verifies_itself(env):
    target = env.workspace / "tests" / "test_newmod.py"
    target.parent.mkdir(exist_ok=True)
    test_targets, profile = select_test_targets(env, [str(target)])
    assert profile["mode"] == "dummy_floor"
    assert all(str(target) != t for t in test_targets)
