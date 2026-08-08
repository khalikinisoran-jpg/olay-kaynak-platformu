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


def test_worker_executor_contract():

    executor = WorkerExecutor()

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


def test_worker_executor_creates_scoped_task():

    executor = WorkerExecutor()

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
        new_content=new_content
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
        new_content="new content\n"
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
        new_content=content
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


def test_worker_validator_controller_pipeline():

    from simulation.agent.worker.patch_validator import (
        PatchValidator
    )

    from simulation.agent.controller.controller import (
        Controller
    )

    executor = WorkerExecutor()

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


def test_apply_authorization_accepts_controller_approval():

    from simulation.agent.apply.apply_authorization import (
        ApplyAuthorization
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
    )

    authorization = ApplyAuthorization()

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch."
    )

    assert (
        authorization.authorize(decision)
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

    decision = ControllerDecision(
        approved=False,
        reason="Controller rejected patch."
    )

    assert (
        authorization.authorize(decision)
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
        new_content="should not be written\n"
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
        == "Apply denied: Controller approval required."
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

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
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
        new_content=updated
    )

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch."
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
        new_content=updated
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
        new_content="new content\n"
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
        new_content=""
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


def test_apply_executor_performs_approved_real_write(
    tmp_path
):

    from simulation.agent.apply.apply_executor import (
        ApplyExecutor
    )

    from simulation.agent.controller.controller_decision import (
        ControllerDecision
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
        new_content=updated
    )

    decision = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch."
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