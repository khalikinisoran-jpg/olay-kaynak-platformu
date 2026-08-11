from simulation.agent.agent import Agent

from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)

from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine
)

from simulation.agent.strategy_dispatcher import (
    StrategyDispatcher
)

from simulation.agent.verify.verification_executor import (
    VerificationExecutor
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)


def build_recovery_agent(
    kernel,
    worker_executor,
    apply_executor=None,
    verification_executor=None,
    controller=None,
    max_attempts=BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS,
    provider=None,
    evidence_recorder=None,
) -> Agent:

    """Explicit production assembly for bounded recovery.

    This is the ONLY way bounded recovery becomes active. The default
    Agent(kernel) path is untouched: it stays proposal-only with no
    worker_pipeline and no recovery_engine. Recovery is enabled only
    when the caller explicitly wires this assembly and passes the
    resulting Agent to the runtime.

    The optional evidence recorder binds every pipeline and recovery
    decision to the Kernel event store and decision trace. It defaults
    to a recorder backed by the supplied kernel, so the auditable
    trace is always active when this assembly is used.
    """

    recorder = (
        evidence_recorder
        if evidence_recorder is not None
        else WorkerEvidenceRecorder(kernel=kernel)
    )

    action_pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=(
            controller
            if controller is not None
            else Controller()
        ),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=(
                apply_executor
                if apply_executor is not None
                else ApplyExecutor()
            ),
            verification_executor=(
                verification_executor
                if verification_executor is not None
                else VerificationExecutor()
            ),
        ),
        evidence_recorder=recorder,
    )

    recovery_engine = BoundedRecoveryEngine(
        worker=worker_executor,
        worker_pipeline=action_pipeline,
        max_attempts=max_attempts,
        evidence_recorder=recorder,
    )

    return Agent(
        kernel,
        dispatcher=StrategyDispatcher(
            worker_executor=worker_executor
        ),
        provider=provider,
        worker_pipeline=action_pipeline,
        recovery_engine=recovery_engine,
    )
