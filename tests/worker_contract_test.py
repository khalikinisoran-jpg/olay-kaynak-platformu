from tests.fake_worker_analyzer import (
    FakeWorkerAnalyzer
)
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.worker_task import (
    WorkerTask
)

from simulation.agent.worker.worker_policy import (
    WorkerPolicy
)

from simulation.agent.worker.patch_generator import (
    PatchGenerator
)


from simulation.agent.worker.worker_agent import (
    WorkerAgent
)


def test_worker_executor_contract():

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=("tests/worker_contract_test.py",),
    )

    result = executor.execute(
        None,
        "Add worker proposal marker"
    )

    assert result.success is True

    assert result.task_id == "worker-task"

    assert (
        "Worker inspection and patch proposal completed."
        in result.summary
    )

    assert result.evidence

    assert result.evidence[0]["status"] == "success"

    assert result.proposal is not None

    assert result.patches

    patch = result.patches[0]

    assert isinstance(
        patch,
        PatchProposal
    )

    assert patch.path == (
        "tests/worker_contract_test.py"
    )

    assert patch.action == "modify"

    assert patch.old_content != patch.new_content


def test_worker_task_security_contract():

    task = WorkerTask(
        task_id="worker-001",
        description="Inspect test system",
        allowed_paths=("tests/",),
        allowed_actions=("inspect",),
        expected_output="inspection summary"
    )

    assert task.task_id == "worker-001"

    assert task.allowed_paths == (
        "tests/",
    )

    assert task.allowed_actions == (
        "inspect",
    )

    assert task.expected_output == (
        "inspection summary"
    )


def test_worker_policy_contract():

    policy = WorkerPolicy()

    assert policy.allows("inspect") is True
    assert policy.allows("read") is True

    assert policy.allows("write") is False
    assert policy.allows("run_test") is False
    assert policy.allows("git") is False


def test_patch_generator_produces_real_change(
    tmp_path
):

    target = tmp_path / "worker_target.txt"

    target.write_text(
        "original worker content\n",
        encoding="utf-8"
    )

    generator = PatchGenerator()

    old_content = target.read_text(
        encoding="utf-8"
    )

    patch = generator.generate(
        path=str(target),
        old_content=old_content,
        description="Add worker proposal marker"
    )

    assert isinstance(
        patch,
        PatchProposal
    )

    assert patch.action == "modify"

    assert patch.old_content == (
        "original worker content\n"
    )

    assert patch.old_content != (
        patch.new_content
    )

    assert (
        "Add worker proposal marker"
        in patch.new_content
    )

    assert (
        "Add worker proposal marker"
        not in patch.old_content
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == old_content
    )


def test_patch_fingerprint_is_deterministic():

    patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Fingerprint test.",
        old_content="old\n",
        new_content="new\n"
    )

    fingerprint_1 = patch.fingerprint()

    fingerprint_2 = patch.fingerprint()

    assert fingerprint_1 == fingerprint_2

    assert len(fingerprint_1) == 64


def test_patch_fingerprint_changes_when_patch_changes():

    patch_1 = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Fingerprint test.",
        old_content="old\n",
        new_content="new\n"
    )

    patch_2 = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Fingerprint test.",
        old_content="old\n",
        new_content="different\n"
    )

    assert (
        patch_1.fingerprint()
        != patch_2.fingerprint()
    )


def test_worker_executor_creates_scoped_task():

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=("tests/worker_contract_test.py",),
    )

    result = executor.execute(
        None,
        "Inspect scoped worker task"
    )

    assert result.success is True

    assert result.patches

    patch = result.patches[0]

    assert patch.path == (
        "tests/worker_contract_test.py"
    )

    assert patch.action == "modify"

    assert patch.allowed_paths == (
        "tests/worker_contract_test.py",
    )


def test_patch_validator_accepts_valid_patch(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    target = tmp_path / "validator_target.txt"

    old_content = "original content\n"

    new_content = "updated content\n"

    target.write_text(
        old_content,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Update test content.",
        old_content=old_content,
        new_content=new_content,
        allowed_paths=(str(target),)
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is True

    assert message == (
        "Patch validation passed."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == old_content
    )


def test_patch_validator_rejects_stale_patch(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    target = tmp_path / "validator_target.txt"

    target.write_text(
        "current content\n",
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Stale patch test.",
        old_content="old content\n",
        new_content="new content\n",
        allowed_paths=(str(target),)
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is False

    assert (
        "stale"
        in message.lower()
    )


def test_patch_validator_rejects_no_change(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    target = tmp_path / "validator_target.txt"

    content = "same content\n"

    target.write_text(
        content,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="No change test.",
        old_content=content,
        new_content=content,
        allowed_paths=(str(target),)
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is False

    assert (
        "does not contain a change"
        in message
    )


def test_patch_validator_rejects_out_of_scope_patch(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    allowed = tmp_path / "allowed.txt"

    outside = tmp_path / "outside.txt"

    old_content = "old\n"

    new_content = "new\n"

    allowed.write_text(
        old_content,
        encoding="utf-8"
    )

    outside.write_text(
        old_content,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(outside),
        action="modify",
        reason="Scope violation test.",
        old_content=old_content,
        new_content=new_content,
        allowed_paths=(str(allowed),)
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is False

    assert (
        "outside the allowed scope"
        in message
    )


def test_patch_validator_rejects_empty_allowed_paths(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    target = tmp_path / "empty_scope_target.txt"

    old_content = "original content\n"

    target.write_text(
        old_content,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Empty scope test.",
        old_content=old_content,
        new_content="changed content\n",
        allowed_paths=()
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is False

    assert (
        "allowed_paths"
        in message
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == old_content
    )


def test_patch_validator_rejects_none_allowed_paths(
    tmp_path
):

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    target = tmp_path / "none_scope_target.txt"

    old_content = "original content\n"

    target.write_text(
        old_content,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="None scope test.",
        old_content=old_content,
        new_content="changed content\n",
        allowed_paths=None
    )

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is False

    assert (
        "allowed_paths"
        in message
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == old_content
    )


def test_controller_approves_validated_patch():

    from simulation.agent.controller.controller import (
        Controller
    )

    controller = Controller()

    patch = PatchProposal(
        path="tests/worker_contract_test.py",
        action="modify",
        reason="Controller approval test.",
        old_content="old\n",
        new_content="new\n"
    )

    decision = controller.approve(
        patch,
        "Patch validation passed."
    )

    assert decision.approved is True

    assert (
        decision.reason
        == "Controller approved validated patch."
    )

    assert (
        decision.patch_fingerprint
        == patch.fingerprint()
    )


def test_controller_rejects_invalid_validation():

    from simulation.agent.controller.controller import (
        Controller
    )

    controller = Controller()

    patch = PatchProposal(
        path="tests/worker_contract_test.py",
        action="modify",
        reason="Invalid patch test.",
        old_content="old\n",
        new_content="new\n"
    )

    decision = controller.approve(
        patch,
        "Patch is stale: current file content "
        "does not match old_content."
    )

    assert decision.approved is False

    assert (
        "validator did not approve"
        in decision.reason
    )

    assert decision.patch_fingerprint == ""


def test_controller_rejects_unsupported_action():

    from simulation.agent.controller.controller import (
        Controller
    )

    controller = Controller()

    patch = PatchProposal(
        path="tests/worker_contract_test.py",
        action="delete",
        reason="Unsupported action test.",
        old_content="old\n",
        new_content=""
    )

    decision = controller.approve(
        patch,
        "Patch validation passed."
    )

    assert decision.approved is False

    assert (
        "unsupported"
        in decision.reason.lower()
    )

    assert decision.patch_fingerprint == ""


def test_worker_validator_controller_pipeline():

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    from simulation.agent.controller.controller import (
        Controller
    )

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=("tests/worker_contract_test.py",),
    )

    result = executor.execute(
        None,
        "Inspect worker pipeline"
    )

    assert result.success is True

    assert result.patches

    patch = result.patches[0]

    validator = PatchValidator()

    valid, message = validator.validate(
        patch
    )

    assert valid is True

    assert message == (
        "Patch validation passed."
    )

    controller = Controller()

    decision = controller.approve(
        patch,
        message
    )

    assert decision.approved is True

    assert (
        decision.reason
        == "Controller approved validated patch."
    )

    assert (
        decision.patch_fingerprint
        == patch.fingerprint()
    )


def test_apply_authorization_accepts_controller_approval():

    from simulation.agent.apply.apply_authorization import (
        ApplyAuthorization
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    authorization = ApplyAuthorization()

    patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Authorization test.",
        old_content="old\n",
        new_content="new\n"
    )

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch.",
        patch_fingerprint=patch.fingerprint()
    )

    assert (
        authorization.authorize(
            decision,
            patch
        )
        is True
    )


def test_apply_authorization_rejects_controller_rejection():

    from simulation.agent.apply.apply_authorization import (
        ApplyAuthorization
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    authorization = ApplyAuthorization()

    patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Authorization rejection test.",
        old_content="old\n",
        new_content="new\n"
    )

    decision = ControllerDecision(
        approved=False,
        reason="Controller rejected patch.",
        patch_fingerprint=patch.fingerprint()
    )

    assert (
        authorization.authorize(
            decision,
            patch
        )
        is False
    )


def test_apply_authorization_rejects_missing_fingerprint():

    from simulation.agent.apply.apply_authorization import (
        ApplyAuthorization
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    authorization = ApplyAuthorization()

    patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Missing fingerprint test.",
        old_content="old\n",
        new_content="new\n"
    )

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch."
    )

    assert (
        authorization.authorize(
            decision,
            patch
        )
        is False
    )


def test_apply_authorization_rejects_wrong_patch():

    from simulation.agent.apply.apply_authorization import (
        ApplyAuthorization
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    authorization = ApplyAuthorization()

    approved_patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Approved patch.",
        old_content="old\n",
        new_content="new\n"
    )

    different_patch = PatchProposal(
        path="example.txt",
        action="modify",
        reason="Different patch.",
        old_content="old\n",
        new_content="different\n"
    )

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch.",
        patch_fingerprint=approved_patch.fingerprint()
    )

    assert (
        authorization.authorize(
            decision,
            different_patch
        )
        is False
    )


def test_apply_executor_requires_controller_approval(
    tmp_path
):

    from simulation.agent.apply.apply_executor import (
        ApplyExecutor
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    target = tmp_path / "denied_target.txt"

    original = "original content\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Apply rejection test.",
        old_content=original,
        new_content="should not be written\n",
        allowed_paths=(str(target),)
    )

    decision = ControllerDecision(
        approved=False,
        reason="Controller rejected patch."
    )

    executor = ApplyExecutor()

    result = executor.apply(
        patch,
        decision
    )

    assert result.success is False

    assert result.path == str(target)

    assert (
        result.message
        == (
            "Apply denied: "
            "Controller approval does not "
            "match this patch."
        )
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_apply_executor_accepts_controller_approval(
    tmp_path
):

    from simulation.agent.apply.apply_executor import (
        ApplyExecutor
    )

    from simulation.agent.controller.controller import (
        Controller
    )

    target = tmp_path / "approved_target.txt"

    original = (
        "executor original content\n"
    )

    updated = (
        "executor updated content\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Approved apply test.",
        old_content=original,
        new_content=updated,
        allowed_paths=(str(target),)
    )

    controller = Controller()

    decision = controller.approve(
        patch,
        "Patch validation passed."
    )

    executor = ApplyExecutor()

    result = executor.apply(
        patch,
        decision
    )

    assert result.success is True

    assert result.path == str(target)

    assert (
        result.message
        == "File applied successfully."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_file_applier_performs_real_write(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    target = tmp_path / "real_write_target.txt"

    original = (
        "original content\n"
    )

    updated = (
        "updated content\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Real write test.",
        old_content=original,
        new_content=updated,
        allowed_paths=(str(target),)
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is True

    assert (
        message
        == "File applied successfully."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_file_applier_rejects_stale_patch(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    target = tmp_path / "stale_target.txt"

    target.write_text(
        "current content\n",
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Stale FileApplier test.",
        old_content="old content\n",
        new_content="new content\n",
        allowed_paths=(str(target),)
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is False

    assert (
        "stale"
        in message.lower()
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == "current content\n"
    )


def test_file_applier_rejects_unsupported_action(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    target = tmp_path / "unsupported_target.txt"

    original = (
        "original content\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="delete",
        reason="Unsupported action test.",
        old_content=original,
        new_content="",
        allowed_paths=(str(target),)
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is False

    assert (
        message
        == "Unsupported action: delete"
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_out_of_scope_patch(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    allowed = tmp_path / "allowed.txt"

    outside = tmp_path / "outside.txt"

    original = "original content\n"

    allowed.write_text(
        original,
        encoding="utf-8"
    )

    outside.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(outside),
        action="modify",
        reason="Scope enforcement test.",
        old_content=original,
        new_content="changed content\n",
        allowed_paths=(str(allowed),)
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is False

    assert (
        "outside the allowed scope"
        in message
    )

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_empty_allowed_paths(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    target = tmp_path / "applier_empty_scope.txt"

    original = "original content\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Applier empty scope test.",
        old_content=original,
        new_content="changed content\n",
        allowed_paths=()
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is False

    assert (
        "allowed_paths"
        in message
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_none_allowed_paths(
    tmp_path
):

    from simulation.agent.apply.file_applier import (
        FileApplier
    )

    target = tmp_path / "applier_none_scope.txt"

    original = "original content\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Applier None scope test.",
        old_content=original,
        new_content="changed content\n",
        allowed_paths=None
    )

    applier = FileApplier()

    success, message = applier.apply(
        patch
    )

    assert success is False

    assert (
        "allowed_paths"
        in message
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_apply_executor_denies_empty_scope_patch(
    tmp_path
):

    from simulation.agent.apply.apply_executor import (
        ApplyExecutor
    )

    from simulation.agent.controller.controller import (
        Controller
    )

    target = tmp_path / "executor_empty_scope.txt"

    original = "original content\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Executor empty scope test.",
        old_content=original,
        new_content="changed content\n",
        allowed_paths=()
    )

    controller = Controller()

    decision = controller.approve(
        patch,
        "Patch validation passed."
    )

    executor = ApplyExecutor()

    result = executor.apply(
        patch,
        decision
    )

    assert result.success is False

    assert (
        "allowed_paths"
        in result.message
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_apply_executor_performs_approved_real_write(
    tmp_path
):

    from simulation.agent.apply.apply_executor import (
        ApplyExecutor
    )

    from simulation.agent.controller.controller import (
        Controller
    )

    target = tmp_path / "executor_write_target.txt"

    original = (
        "executor original content\n"
    )

    updated = (
        "executor updated content\n"
    )

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Approved executor write test.",
        old_content=original,
        new_content=updated,
        allowed_paths=(str(target),)
    )

    controller = Controller()

    decision = controller.approve(
        patch,
        "Patch validation passed."
    )

    executor = ApplyExecutor()

    result = executor.apply(
        patch,
        decision
    )

    assert result.success is True

    assert result.path == str(target)

    assert (
        result.message
        == "File applied successfully."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )