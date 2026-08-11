from simulation.agent.apply.apply_authorization import (
    ApplyAuthorization
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.validation_result import (
    ValidationResult
)


def make_patch(action="modify"):

    return PatchProposal(
        path="tests/controller_decision_test.py",
        action=action,
        reason="Controller decision hardening test.",
        old_content="old\n",
        new_content="new\n",
        allowed_paths=("tests/",),
    )


def test_controller_approves_structured_pass():

    decision = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )

    assert decision.approved is True

    assert (
        decision.reason
        == "Controller approved validated patch."
    )

    assert (
        decision.patch_fingerprint
        == make_patch().fingerprint()
    )


def test_controller_rejects_structured_fail():

    decision = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=False,
            message="Patch is stale.",
        ),
    )

    assert decision.approved is False

    assert (
        "validator did not approve"
        in decision.reason
    )

    assert decision.patch_fingerprint == ""


def test_controller_rejects_missing_result():

    decision = Controller().approve(
        make_patch(),
        None,
    )

    assert decision.approved is False

    assert (
        "Missing validator result."
        in decision.reason
    )

    assert decision.patch_fingerprint == ""


def test_controller_rejects_malformed_string_result():

    decision = Controller().approve(
        make_patch(),
        "Patch validation passed.",
    )

    assert decision.approved is False

    assert (
        "Malformed validator result."
        in decision.reason
    )


def test_controller_rejects_malformed_dict_result():

    decision = Controller().approve(
        make_patch(),
        {"valid": True, "message": "passed"},
    )

    assert decision.approved is False

    assert "Malformed validator result." in decision.reason


def test_controller_rejects_unknown_status_string_valid():

    decision = Controller().approve(
        make_patch(),
        ValidationResult(
            valid="yes",
            message="not a real boolean",
        ),
    )

    assert decision.approved is False

    assert (
        "validator did not approve"
        in decision.reason
    )


def test_controller_rejects_unknown_status_none_valid():

    decision = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=None,
            message="missing status",
        ),
    )

    assert decision.approved is False


def test_controller_rejects_truthy_non_bool_valid():

    decision = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=1,
            message="truthy but not bool",
        ),
    )

    assert decision.approved is False


def test_controller_rejects_unsupported_action_even_when_valid():

    decision = Controller().approve(
        make_patch(action="delete"),
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )

    assert decision.approved is False

    assert "unsupported" in decision.reason.lower()

    assert decision.patch_fingerprint == ""


def test_controller_decision_message_text_is_not_the_decision_signal():

    pass_odd_message = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=True,
            message="anything at all",
        ),
    )

    fail_expected_message = Controller().approve(
        make_patch(),
        ValidationResult(
            valid=False,
            message="Patch validation passed.",
        ),
    )

    assert pass_odd_message.approved is True

    assert fail_expected_message.approved is False


def test_apply_authorization_requires_exactly_true_approved():

    patch = make_patch()

    forged = ControllerDecision(
        approved=1,
        reason="Truthy but not bool approved.",
        patch_fingerprint=patch.fingerprint(),
    )

    authorization = ApplyAuthorization()

    assert (
        authorization.authorize(
            forged,
            patch,
        )
        is False
    )


def test_apply_authorization_requires_fingerprint_match():

    patch = make_patch()

    other = PatchProposal(
        path=patch.path,
        action="modify",
        reason=patch.reason,
        old_content=patch.old_content,
        new_content="different\n",
        allowed_paths=patch.allowed_paths,
    )

    decision = ControllerDecision(
        approved=True,
        reason="Approval for another patch.",
        patch_fingerprint=other.fingerprint(),
    )

    authorization = ApplyAuthorization()

    assert (
        authorization.authorize(
            decision,
            patch,
        )
        is False
    )


def test_pipeline_denies_unauthorized_scope_before_controller(tmp_path):

    from simulation.agent.pipeline.worker_action_pipeline import (
        WorkerActionPipeline
    )

    from simulation.agent.worker.worker_result import (
        WorkerResult
    )

    class CountingController:

        def __init__(self):
            self.calls = 0

        def approve(self, patch, validation):
            self.calls += 1
            return ControllerDecision(
                approved=True,
                reason="should never be reached",
                patch_fingerprint=patch.fingerprint(),
            )

    scope = tmp_path / "scope"

    scope.mkdir()

    outside = tmp_path / "secret.txt"

    outside.write_text(
        "secret\n",
        encoding="utf-8"
    )

    patch = PatchProposal(
        path=str(outside),
        action="modify",
        reason="Scope escape attempt.",
        old_content="secret\n",
        new_content="tampered\n",
        allowed_paths=(str(scope),),
    )

    worker_result = WorkerResult(
        task_id="scope-task",
        success=True,
        summary="Scope escape attempt.",
        patches=(patch,),
    )

    controller = CountingController()

    pipeline = WorkerActionPipeline(
        controller=controller,
    )

    result = pipeline.execute(
        worker_result,
    )

    assert result.success is False

    assert result.failure_stage == "validation"

    assert controller.calls == 0

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == "secret\n"
    )
