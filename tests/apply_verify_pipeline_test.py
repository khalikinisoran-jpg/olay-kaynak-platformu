from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.apply_verify_result import (
    ApplyVerifyResult
)

from simulation.agent.verify.verification_executor import (
    VerificationExecutor
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

from simulation.agent.worker.validation_result import (
    ValidationResult
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


def make_patch(
    target,
    original,
    updated,
    allowed_paths
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Apply verify pipeline test.",
        old_content=original,
        new_content=updated,
        allowed_paths=allowed_paths,
    )


def approved_decision(patch):

    controller = Controller()

    return controller.approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        )
    )


def build_pipeline(verification_result):

    return ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(),
        verification_executor=(
            FakeVerificationExecutor(
                verification_result
            )
        ),
    )


def test_apply_success_verification_success(
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
        status=PASS,
        exit_code=0,
        stdout="1 passed",
    )

    pipeline = build_pipeline(verification)

    result = pipeline.execute(
        patch,
        approved_decision(patch)
    )

    assert isinstance(
        result,
        ApplyVerifyResult
    )

    assert result.apply_result.success is True

    assert result.verification_ran is True

    assert result.verification is verification

    assert result.verification_passed is True

    assert result.success is True

    assert result.failure_reason == ""

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_apply_success_verification_failure_is_pipeline_failure(
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
            exit_code=2,
            stdout="1 failed",
            stderr="FAILED sample_test::test_x",
        ),
    )

    verification = make_verification_result(
        status=FAIL,
        exit_code=2,
        stdout="1 failed",
        stderr="FAILED sample_test::test_x",
        evidence=evidence,
        failure_reason=(
            "Test execution verification returned "
            "non-zero exit code 2."
        ),
    )

    pipeline = build_pipeline(verification)

    result = pipeline.execute(
        patch,
        approved_decision(patch)
    )

    assert result.apply_result.success is True

    assert result.verification_ran is True

    assert result.verification.failed is True

    assert result.verification_passed is False

    assert result.success is False

    assert result.apply_success is True

    assert result.exit_code == 2

    assert result.stdout == "1 failed"

    assert result.stderr == "FAILED sample_test::test_x"

    assert result.evidence == evidence

    assert (
        "non-zero exit code 2"
        in result.failure_reason
    )

    assert result.rollback is not None

    assert result.rollback.success is True

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

    verification = make_verification_result()

    pipeline = build_pipeline(verification)

    result = pipeline.execute(
        patch,
        approved_decision(patch)
    )

    assert result.apply_result.success is False

    assert result.verification_ran is False

    assert result.verification is None

    assert result.verification_passed is False

    assert result.success is False

    assert result.failure_reason != ""

    assert (
        result.evidence == ()
    )

    assert (
        result.stdout == ""
    )

    assert (
        result.stderr == ""
    )

    assert (
        result.exit_code == -1
    )

    fake = pipeline.verification_executor

    assert fake.calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == current
    )


def test_apply_denial_skips_verification(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    approved_patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    decision = Controller().approve(
        approved_patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        )
    )

    different_patch = make_patch(
        target,
        original,
        "different\n",
        (str(target),)
    )

    verification = make_verification_result()

    pipeline = build_pipeline(verification)

    denied = pipeline.execute(
        different_patch,
        decision
    )

    assert denied.apply_result.success is False

    assert (
        denied.apply_result.message
        == (
            "Apply denied: "
            "Controller approval does not "
            "match this patch."
        )
    )

    assert denied.verification_ran is False

    assert denied.verification is None

    assert denied.success is False

    assert (
        pipeline.verification_executor.calls == []
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

    pipeline = build_pipeline(verification)

    result = pipeline.execute(
        patch,
        approved_decision(patch)
    )

    assert (
        result.evidence
        == (
            compile_evidence,
            test_evidence,
        )
    )

    assert (
        result.verification.evidence
        == result.evidence
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


def test_pipeline_uses_existing_verification_executor_contract(
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

    pipeline = build_pipeline(
        make_verification_result()
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
        test_targets=(
            "tests/sample_test.py",
        ),
    )

    assert result.success is True

    call = pipeline.verification_executor.calls[0]

    assert call["paths"] == (str(target),)

    assert call["test_targets"] == (
        "tests/sample_test.py",
    )


def test_pipeline_accepts_explicit_verify_paths(
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

    pipeline = build_pipeline(
        make_verification_result()
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
        verify_paths=(
            str(target),
            str(tmp_path / "util.py"),
        ),
        test_targets=(),
    )

    assert result.success is True

    call = pipeline.verification_executor.calls[0]

    assert call["paths"] == (
        str(target),
        str(tmp_path / "util.py"),
    )

    assert call["test_targets"] == ()


def test_existing_apply_executor_remains_backward_compatible(
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

    decision = approved_decision(patch)

    executor = ApplyExecutor()

    apply_result = executor.apply(
        patch,
        decision
    )

    assert apply_result.success is True

    assert (
        apply_result.message
        == "File applied successfully."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_pipeline_defaults_construct_real_executors():

    pipeline = ApplyVerifyPipeline()

    assert isinstance(
        pipeline.apply_executor,
        ApplyExecutor
    )

    assert isinstance(
        pipeline.verification_executor,
        VerificationExecutor
    )
