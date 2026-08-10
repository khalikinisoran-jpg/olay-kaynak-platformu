from simulation.agent.agent import Agent

from simulation.agent.apply.apply_executor import (
    ApplyExecutor
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
) -> Agent:

    """Explicit production assembly for bounded recovery.

    This is the ONLY way bounded recovery becomes active. The default
    Agent(kernel) path is untouched: it stays proposal-only with no
    worker_pipeline and no recovery_engine. Recovery is enabled only
    when the caller explicitly wires this assembly and passes the
    resulting Agent to the runtime.
    """

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
    )

    recovery_engine = BoundedRecoveryEngine(
        worker=worker_executor,
        worker_pipeline=action_pipeline,
        max_attempts=max_attempts,
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
