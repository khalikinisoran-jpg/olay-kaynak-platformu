from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.apply_verify_result import (
    ApplyVerifyResult
)

from simulation.agent.pipeline.worker_action_pipeline import (
    PatchStageResult,
    WorkerActionPipeline,
    WorkerPipelineResult,
)

from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationEvidence,
    VerificationResult,
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)


def make_verification_result(
    status=PASS,
    exit_code=0,
    stdout="",
    stderr="",
    evidence=(),
    failure_reason=""
):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        command=(
            "venv-python",
            "-m",
            "pytest",
            "-q",
        ),
        evidence=tuple(evidence),
        failure_reason=failure_reason,
    )


class FakeVerificationExecutor:

    def __init__(self, result):

        self.result = result

        self.calls = []

    def verify(
        self,
        paths,
        test_targets=()
    ):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        return self.result


class RecordingApplyExecutor:

    def __init__(
        self,
        success=True,
        message="File applied successfully."
    ):

        self.success = success

        self.message = message

        self.calls = []

    def apply(
        self,
        patch,
        decision
    ):

        self.calls.append({
            "patch": patch,
            "decision": decision,
        })

        return ApplyResult(
            success=self.success,
            path=patch.path,
            message=self.message,
        )


class RecordingController:

    def __init__(self, decisions=None):

        self.decisions = (
            list(decisions)
            if decisions is not None
            else []
        )

        self.calls = []

    def approve(
        self,
        patch,
        validation_message
    ):

        self.calls.append({
            "patch": patch,
            "validation_message": validation_message,
        })

        if self.decisions:

            return self.decisions.pop(0)

        return Controller().approve(
            patch,
            validation_message
        )


def make_patch(
    target,
    original,
    updated,
    allowed_paths
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Worker action pipeline test.",
        old_content=original,
        new_content=updated,
        allowed_paths=allowed_paths,
    )


def make_worker_result(
    *patches,
    success=True,
    summary="Worker inspection and patch proposal completed."
):

    return WorkerResult(
        task_id="worker-task",
        success=success,
        summary=summary,
        patches=tuple(patches),
    )


def build_pipeline(
    apply_executor,
    verification_executor,
    controller=None
):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=(
            controller
            if controller is not None
            else Controller()
        ),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=apply_executor,
            verification_executor=verification_executor,
        ),
    )


def test_worker_proposal_validation_approval_apply_verification_pass(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    evidence = (
        VerificationEvidence(
            stage="tests",
            command=(
                "venv-python",
                "-m",
                "pytest",
                "-q",
            ),
            exit_code=0,
            stdout="1 passed",
            stderr="",
        ),
    )

    verification = make_verification_result(
        status=PASS,
        exit_code=0,
        stdout="1 passed",
        evidence=evidence,
    )

    pipeline = build_pipeline(
        ApplyExecutor(),
        FakeVerificationExecutor(verification),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert isinstance(
        result,
        WorkerPipelineResult
    )

    assert result.success is True

    assert result.apply_success is True

    assert result.verification_passed is True

    assert result.verification_ran is True

    assert result.exit_code == 0

    assert result.failure_reason == ""

    assert result.evidence == evidence

    assert len(result.patch_results) == 1

    stage = result.patch_results[0]

    assert stage.stage == "apply_verify"

    assert stage.success is True

    assert stage.patch is patch

    assert (
        stage.pipeline_result.apply_result.success
        is True
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_validation_failure_skips_controller_apply_and_verification(
    tmp_path
):

    target = tmp_path / "sample.py"

    current = "current content\n"

    target.write_text(
        current,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        "stale old content\n",
        "new content\n",
        (str(target),)
    )

    apply_executor = RecordingApplyExecutor()

    verification_executor = FakeVerificationExecutor(
        make_verification_result()
    )

    controller = RecordingController()

    pipeline = build_pipeline(
        apply_executor,
        verification_executor,
        controller=controller,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_passed is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert "stale" in result.failure_reason.lower()

    assert len(result.patch_results) == 1

    assert result.patch_results[0].stage == "validation"

    assert result.patch_results[0].success is False

    assert controller.calls == []

    assert apply_executor.calls == []

    assert verification_executor.calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == current
    )


def test_controller_rejection_skips_apply_and_verification(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    rejection = ControllerDecision(
        approved=False,
        reason="Controller rejected validated patch."
    )

    apply_executor = RecordingApplyExecutor()

    verification_executor = FakeVerificationExecutor(
        make_verification_result()
    )

    controller = RecordingController(
        decisions=[rejection]
    )

    pipeline = build_pipeline(
        apply_executor,
        verification_executor,
        controller=controller,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert (
        result.failure_reason
        == "Controller rejected validated patch."
    )

    assert len(result.patch_results) == 1

    assert result.patch_results[0].stage == "controller"

    assert result.patch_results[0].decision is rejection

    assert len(controller.calls) == 1

    assert controller.calls[0]["patch"] is patch

    assert (
        controller.calls[0]["validation_message"].valid
        is True
    )

    assert (
        controller.calls[0]["validation_message"].message
        == "Patch validation passed."
    )

    assert apply_executor.calls == []

    assert verification_executor.calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_apply_failure_skips_verification(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    apply_executor = RecordingApplyExecutor(
        success=False,
        message="File is already in the requested state.",
    )

    verification_executor = FakeVerificationExecutor(
        make_verification_result()
    )

    pipeline = build_pipeline(
        apply_executor,
        verification_executor,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_passed is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert (
        result.failure_reason
        == "File is already in the requested state."
    )

    assert len(result.patch_results) == 1

    assert result.patch_results[0].stage == "apply_verify"

    assert result.patch_results[0].success is False

    assert (
        result.patch_results[0].pipeline_result.verification
        is None
    )

    assert verification_executor.calls == []

    assert len(apply_executor.calls) == 1


def test_apply_success_verification_failure_is_overall_failure(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    verification = make_verification_result(
        status=FAIL,
        exit_code=2,
        stdout="1 failed",
        stderr="FAILED sample_test::test_x",
        failure_reason=(
            "Test execution verification returned "
            "non-zero exit code 2."
        ),
    )

    pipeline = build_pipeline(
        ApplyExecutor(),
        FakeVerificationExecutor(verification),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is True

    assert result.verification_passed is False

    assert result.verification_ran is True

    assert result.exit_code == 2

    assert result.stdout == "1 failed"

    assert result.stderr == "FAILED sample_test::test_x"

    assert (
        "non-zero exit code 2"
        in result.failure_reason
    )

    stage = result.patch_results[0]

    assert stage.success is False

    assert (
        stage.pipeline_result.apply_result.success
        is True
    )

    assert (
        stage.pipeline_result.verification.failed
        is True
    )

    assert (
        stage.pipeline_result.rollback is not None
    )

    assert (
        stage.pipeline_result.rollback.success
        is True
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_verification_evidence_preserved_upstream(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    compile_evidence = VerificationEvidence(
        stage="compile",
        command=(
            "venv-python",
            "-m",
            "compileall",
            "-q",
        ),
        exit_code=0,
        stdout="compiled 1 file",
        stderr="",
    )

    test_evidence = VerificationEvidence(
        stage="tests",
        command=(
            "venv-python",
            "-m",
            "pytest",
            "-q",
        ),
        exit_code=0,
        stdout="3 passed",
        stderr="pytest warning",
    )

    verification = make_verification_result(
        status=PASS,
        exit_code=0,
        stdout="compiled 1 file\n3 passed",
        stderr="pytest warning",
        evidence=(
            compile_evidence,
            test_evidence,
        ),
    )

    pipeline = build_pipeline(
        ApplyExecutor(),
        FakeVerificationExecutor(verification),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.evidence == (
        compile_evidence,
        test_evidence,
    )

    assert (
        "compiled 1 file"
        in result.stdout
    )

    assert (
        "3 passed"
        in result.stdout
    )

    assert (
        "pytest warning"
        in result.stderr
    )

    assert (
        result.evidence[0].stdout
        == "compiled 1 file"
    )

    assert (
        result.evidence[1].stage
        == "tests"
    )


def test_multiple_patches_apply_in_safe_order_with_approval_per_patch(
    tmp_path
):

    target_a = tmp_path / "alpha.py"

    target_b = tmp_path / "beta.py"

    original_a = "alpha = 1\n"

    updated_a = "alpha = 2\n"

    original_b = "beta = 1\n"

    updated_b = "beta = 2\n"

    target_a.write_text(
        original_a,
        encoding="utf-8"
    )

    target_b.write_text(
        original_b,
        encoding="utf-8"
    )

    patch_a = make_patch(
        target_a,
        original_a,
        updated_a,
        (str(target_a),)
    )

    patch_b = make_patch(
        target_b,
        original_b,
        updated_b,
        (str(target_b),)
    )

    controller = RecordingController()

    pipeline = build_pipeline(
        ApplyExecutor(),
        FakeVerificationExecutor(
            make_verification_result(
                status=PASS,
                exit_code=0,
                stdout="2 passed",
            )
        ),
        controller=controller,
    )

    result = pipeline.execute(
        make_worker_result(
            patch_a,
            patch_b
        )
    )

    assert result.success is True

    assert result.verification_ran is True

    assert len(result.patch_results) == 2

    assert (
        result.patch_results[0].patch.path
        == str(target_a)
    )

    assert (
        result.patch_results[1].patch.path
        == str(target_b)
    )

    assert all(
        stage.stage == "apply_verify"
        for stage in result.patch_results
    )

    assert all(
        stage.success
        for stage in result.patch_results
    )

    assert len(controller.calls) == 2

    assert controller.calls[0]["patch"] is patch_a

    assert controller.calls[1]["patch"] is patch_b

    assert all(
        call["validation_message"].valid is True
        for call in controller.calls
    )

    assert all(
        call["validation_message"].message
        == "Patch validation passed."
        for call in controller.calls
    )

    assert (
        target_a.read_text(
            encoding="utf-8"
        )
        == updated_a
    )

    assert (
        target_b.read_text(
            encoding="utf-8"
        )
        == updated_b
    )


def test_later_patch_rejection_prevents_apply_without_approval(
    tmp_path
):

    target_a = tmp_path / "alpha.py"

    target_b = tmp_path / "beta.py"

    original_a = "alpha = 1\n"

    updated_a = "alpha = 2\n"

    original_b = "beta = 1\n"

    target_a.write_text(
        original_a,
        encoding="utf-8"
    )

    target_b.write_text(
        original_b,
        encoding="utf-8"
    )

    patch_a = make_patch(
        target_a,
        original_a,
        updated_a,
        (str(target_a),)
    )

    patch_b = make_patch(
        target_b,
        original_b,
        "beta = 2\n",
        (str(target_b),)
    )

    approve_a = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch.",
        patch_fingerprint=patch_a.fingerprint(),
    )

    reject_b = ControllerDecision(
        approved=False,
        reason="Controller rejected validated patch."
    )

    controller = RecordingController(
        decisions=[approve_a, reject_b]
    )

    apply_executor = RecordingApplyExecutor()

    verification_executor = FakeVerificationExecutor(
        make_verification_result()
    )

    pipeline = build_pipeline(
        apply_executor,
        verification_executor,
        controller=controller,
    )

    result = pipeline.execute(
        make_worker_result(
            patch_a,
            patch_b
        )
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_ran is True

    assert len(result.patch_results) == 2

    assert result.patch_results[0].stage == "apply_verify"

    assert result.patch_results[0].success is True

    assert result.patch_results[1].stage == "controller"

    assert result.patch_results[1].success is False

    assert len(apply_executor.calls) == 1

    assert apply_executor.calls[0]["patch"] is patch_a

    assert len(verification_executor.calls) == 1


def test_worker_without_proposals_never_applies_or_verifies(
    tmp_path
):

    apply_executor = RecordingApplyExecutor()

    verification_executor = FakeVerificationExecutor(
        make_verification_result()
    )

    controller = RecordingController()

    pipeline = build_pipeline(
        apply_executor,
        verification_executor,
        controller=controller,
    )

    worker_result = make_worker_result(
        success=False,
        summary="Worker inspection failed to produce "
        "a patch proposal.",
    )

    result = pipeline.execute(
        worker_result
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_passed is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert (
        result.failure_reason
        == "Worker produced no patch proposals."
    )

    assert result.patch_results == ()

    assert controller.calls == []

    assert apply_executor.calls == []

    assert verification_executor.calls == []


def test_worker_pipeline_defaults_construct_real_gates():

    pipeline = WorkerActionPipeline()

    assert isinstance(
        pipeline.patch_validator,
        PatchValidator
    )

    assert isinstance(
        pipeline.controller,
        Controller
    )

    assert isinstance(
        pipeline.apply_verify_pipeline,
        ApplyVerifyPipeline
    )

    assert isinstance(
        pipeline.apply_verify_pipeline.apply_executor,
        ApplyExecutor
    )


def test_pipeline_result_mirrors_apply_verify_result_fields(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    evidence = (
        VerificationEvidence(
            stage="tests",
            command=(
                "venv-python",
                "-m",
                "pytest",
                "-q",
            ),
            exit_code=0,
            stdout="1 passed",
            stderr="",
        ),
    )

    verification = make_verification_result(
        status=PASS,
        exit_code=0,
        stdout="1 passed",
        evidence=evidence,
    )

    pipeline = build_pipeline(
        ApplyExecutor(),
        FakeVerificationExecutor(verification),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert isinstance(
        result.patch_results[0].pipeline_result,
        ApplyVerifyResult
    )

    assert (
        result.evidence
        == result.patch_results[0].pipeline_result.evidence
    )

    assert (
        result.stdout
        == result.patch_results[0].pipeline_result.stdout
    )

    assert (
        result.stderr
        == result.patch_results[0].pipeline_result.stderr
    )

    assert (
        result.exit_code
        == result.patch_results[0].pipeline_result.exit_code
    )

    assert isinstance(
        result.patch_results[0],
        PatchStageResult
    )
