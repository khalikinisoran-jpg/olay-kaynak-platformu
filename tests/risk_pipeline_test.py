from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.approval.approval import (
    Approval
)

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)

from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent
)

from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.worker.validation_result import (
    ValidationResult
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)

from simulation.security.risk_engine import (
    RiskAssessment,
    RiskEngine,
)

from simulation.security.risk_level import (
    RiskLevel
)

from simulation.security.risk_policy import (
    RiskPolicy
)


class DualVerificationExecutor:

    def __init__(self, result):

        self.result = result

        self.verify_calls = []

        self.compile_calls = []

    def verify(
        self,
        paths,
        test_targets=()
    ):

        self.verify_calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        return self.result

    def verify_python_compile(
        self,
        paths
    ):

        self.compile_calls.append({
            "paths": tuple(paths),
        })

        return self.result


class RecordingApplyExecutor:

    def __init__(self, success=True):

        self.success = success

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
            message=(
                "File applied successfully."
                if self.success
                else "File apply failed."
            ),
        )


class RecordingApplyVerifyPipeline(ApplyVerifyPipeline):

    def __init__(
        self,
        apply_executor,
        verification_executor
    ):

        super().__init__(
            apply_executor=apply_executor,
            verification_executor=verification_executor,
        )

        self.calls = []

    def execute(
        self,
        patch,
        decision,
        verify_paths=None,
        test_targets=(),
        verification_depth=(
            ApplyVerifyPipeline.VERIFICATION_DEPTH_COMPILE_TESTS
        ),
    ):

        self.calls.append({
            "patch": patch,
            "decision": decision,
            "verification_depth": verification_depth,
        })

        return super().execute(
            patch,
            decision,
            verify_paths=verify_paths,
            test_targets=test_targets,
            verification_depth=verification_depth,
        )


class DenyRiskEngine:

    def classify(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ):

        return RiskAssessment(
            risk_level=RiskLevel.UNKNOWN,
            reason="Stub engine could not derive risk.",
        )


class StubApprovalStore:

    def __init__(self, approval):

        self.approval = approval

        self.queries = []

    def find_valid(
        self,
        fingerprint,
        path=None,
        action=None,
        risk_level=None,
        attempt=None,
        patch=None,
    ):

        self.queries.append(fingerprint)

        return self.approval

    def authorize_apply(self, approval_id, patch):

        return True


class ExplodingRiskEngine:

    def classify(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ):

        raise AssertionError(
            "Risk engine must not be consulted "
            "when the gate is disabled."
        )


class RecordingKernel:

    def __init__(self):

        self.events = []

    def dispatch(self, event):

        self.events.append(event)


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected."
        )

    def get_model_name(self):

        return "stub"


class StubWorkerExecutor:

    def execute(self, *args, **kwargs):

        raise AssertionError(
            "Worker executor not expected to run "
            "in the assembly construction test."
        )


def make_verification_result(
    status=PASS,
    exit_code=0,
    stdout="",
    stderr="",
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
    )


def make_patch(
    target,
    original,
    updated,
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Risk pipeline test.",
        old_content=original,
        new_content=updated,
        allowed_paths=(str(target),),
    )


def make_worker_result(*patches):

    return WorkerResult(
        task_id="worker-task",
        success=True,
        summary="Risk pipeline test.",
        patches=tuple(patches),
    )


def approved_decision(patch):

    return Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )


def make_valid_approval(
    patch,
    risk_level="HIGH",
    attempt=1,
    authorizer="human-test",
    expires_at=None,
):

    return Approval.create(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=attempt,
        authorizer=authorizer,
        expires_at=expires_at,
    )


def build_gated_pipeline(
    verification_result,
    apply_executor=None,
    risk_engine=None,
    risk_policy=None,
    approval_store=None,
    apply_verify_pipeline=None,
):

    if apply_verify_pipeline is None:

        apply_verify_pipeline = ApplyVerifyPipeline(
            apply_executor=(
                apply_executor
                if apply_executor is not None
                else RecordingApplyExecutor()
            ),
            verification_executor=(
                DualVerificationExecutor(
                    verification_result
                )
            ),
        )

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=apply_verify_pipeline,
        risk_engine=(
            risk_engine
            if risk_engine is not None
            else RiskEngine()
        ),
        risk_policy=(
            risk_policy
            if risk_policy is not None
            else RiskPolicy()
        ),
        approval_store=approval_store,
    )


def test_gate_enabled_low_risk_flows_through_pipeline(
    tmp_path
):

    target = tmp_path / "notes.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_executor=ApplyExecutor(),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is True

    assert result.apply_success is True

    assert result.verification_passed is True

    assert len(result.patch_results) == 1

    stage = result.patch_results[0]

    assert stage.stage == "apply_verify"

    assert stage.success is True

    executor = (
        pipeline.apply_verify_pipeline.verification_executor
    )

    assert len(executor.verify_calls) == 1

    assert executor.compile_calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_gate_enabled_medium_risk_flows_through_pipeline(
    tmp_path
):

    target = tmp_path / "app.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_executor=ApplyExecutor(),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is True

    assert result.apply_success is True

    executor = (
        pipeline.apply_verify_pipeline.verification_executor
    )

    assert len(executor.verify_calls) == 1


def test_gate_enabled_risk_rejection_denies_apply(
    tmp_path
):

    target = tmp_path / "notes.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_executor=apply_executor,
        risk_engine=DenyRiskEngine(),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert result.failure_stage == "risk"

    assert len(result.patch_results) == 1

    assert result.patch_results[0].stage == "risk"

    assert result.patch_results[0].success is False

    assert apply_executor.calls == []

    executor = (
        pipeline.apply_verify_pipeline.verification_executor
    )

    assert executor.verify_calls == []

    assert executor.compile_calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_gate_enabled_high_risk_requires_human_approval(
    tmp_path
):

    target = tmp_path / "settings.secret.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_executor=apply_executor,
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert result.failure_stage == "approval"

    assert len(result.patch_results) == 1

    assert result.patch_results[0].stage == "approval"

    assert result.patch_results[0].success is False

    assert (
        result.failure_reason
        == "High-risk patch requires human approval."
    )

    assert apply_executor.calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_gate_enabled_critical_risk_requires_human_approval(
    tmp_path
):

    target = tmp_path / "secrets" / "app.pem"

    target.parent.mkdir()

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_executor=apply_executor,
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is False

    assert result.failure_stage == "approval"

    assert result.patch_results[0].stage == "approval"

    assert apply_executor.calls == []


def test_gate_enabled_high_risk_with_approval_flows_to_apply(
    tmp_path
):

    target = tmp_path / "settings.secret.txt"

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
    )

    approval = make_valid_approval(patch)

    store = StubApprovalStore(approval)

    apply_executor = ApplyExecutor()

    recorded = RecordingApplyVerifyPipeline(
        apply_executor=apply_executor,
        verification_executor=DualVerificationExecutor(
            make_verification_result()
        ),
    )

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_verify_pipeline=recorded,
        approval_store=store,
    )

    patch = make_patch(
        target,
        original,
        updated,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    assert result.apply_success is True

    assert result.verification_passed is True

    assert store.queries == [patch.fingerprint()]

    executor = (
        pipeline.apply_verify_pipeline.verification_executor
    )

    assert len(executor.verify_calls) == 1

    assert executor.compile_calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_policy_verification_depth_reaches_pipeline(
    tmp_path
):

    target = tmp_path / "settings.secret.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    recorded = RecordingApplyVerifyPipeline(
        apply_executor=RecordingApplyExecutor(),
        verification_executor=DualVerificationExecutor(
            make_verification_result()
        ),
    )

    patch = make_patch(
        target,
        original,
        updated,
    )

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_verify_pipeline=recorded,
        approval_store=StubApprovalStore(
            make_valid_approval(patch)
        ),
    )

    policy_depth = RiskPolicy.from_level(
        RiskLevel.HIGH
    ).verification_depth

    assert policy_depth == "compile+tests"

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    assert len(recorded.calls) == 1

    assert (
        recorded.calls[0]["verification_depth"]
        == policy_depth
    )


def test_policy_medium_depth_reaches_pipeline(
    tmp_path
):

    target = tmp_path / "app.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    recorded = RecordingApplyVerifyPipeline(
        apply_executor=RecordingApplyExecutor(),
        verification_executor=DualVerificationExecutor(
            make_verification_result()
        ),
    )

    pipeline = build_gated_pipeline(
        make_verification_result(),
        apply_verify_pipeline=recorded,
    )

    policy_depth = RiskPolicy.from_level(
        RiskLevel.MEDIUM
    ).verification_depth

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is True

    assert (
        recorded.calls[0]["verification_depth"]
        == policy_depth
    )


def test_gate_disabled_never_consults_risk_engine(
    tmp_path
):

    target = tmp_path / "notes.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=RecordingApplyExecutor(),
            verification_executor=DualVerificationExecutor(
                make_verification_result()
            ),
        ),
        risk_engine=ExplodingRiskEngine(),
    )

    assert pipeline.risk_gate_enabled is False

    result = pipeline.execute(
        make_worker_result(
            make_patch(
                target,
                original,
                updated,
            )
        )
    )

    assert result.success is True

    assert result.apply_success is True


def test_apply_verify_compile_depth_uses_compile_only(
    tmp_path
):

    target = tmp_path / "app.py"

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
    )

    decision = approved_decision(patch)

    executor = DualVerificationExecutor(
        make_verification_result()
    )

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(),
        verification_executor=executor,
    )

    result = pipeline.execute(
        patch,
        decision,
        verification_depth=(
            ApplyVerifyPipeline.VERIFICATION_DEPTH_COMPILE
        ),
    )

    assert result.success is True

    assert result.verification_ran is True

    assert len(executor.compile_calls) == 1

    assert executor.verify_calls == []

    assert executor.compile_calls[0]["paths"] == (
        str(target),
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_apply_verify_default_depth_uses_full_verify(
    tmp_path
):

    target = tmp_path / "app.py"

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
    )

    decision = approved_decision(patch)

    executor = DualVerificationExecutor(
        make_verification_result()
    )

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(),
        verification_executor=executor,
    )

    result = pipeline.execute(
        patch,
        decision,
    )

    assert result.success is True

    assert len(executor.verify_calls) == 1

    assert executor.compile_calls == []


def test_apply_verify_explicit_compile_tests_depth_uses_full_verify(
    tmp_path
):

    target = tmp_path / "app.py"

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
    )

    decision = approved_decision(patch)

    executor = DualVerificationExecutor(
        make_verification_result()
    )

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(),
        verification_executor=executor,
    )

    result = pipeline.execute(
        patch,
        decision,
        verification_depth=(
            ApplyVerifyPipeline.VERIFICATION_DEPTH_COMPILE_TESTS
        ),
    )

    assert result.success is True

    assert len(executor.verify_calls) == 1

    assert executor.compile_calls == []


def test_assembly_default_risk_gate_disabled():

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is not None

    assert agent.worker_pipeline.risk_gate_enabled is False


def test_assembly_opt_in_risk_gate_enabled():

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
    )

    assert agent.worker_pipeline is not None

    assert agent.worker_pipeline.risk_gate_enabled is True

    assert isinstance(
        agent.worker_pipeline.risk_engine,
        RiskEngine,
    )

    assert isinstance(
        agent.worker_pipeline.risk_policy,
        RiskPolicy,
    )


def test_assembly_risk_gate_requires_both_engine_and_policy():

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is False

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
        risk_policy=RiskPolicy(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is False
