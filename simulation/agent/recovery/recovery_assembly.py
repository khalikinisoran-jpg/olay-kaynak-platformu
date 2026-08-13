from simulation.agent.agent import Agent

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger
)

from simulation.agent.approval.approval_store import (
    ApprovalStore
)

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

from simulation.security.risk_engine import (
    RiskEngine
)

from simulation.security.risk_policy import (
    RiskPolicy
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
    risk_engine=None,
    risk_policy=None,
    approval_store=None,
    approval_ledger_path=None,
    approval_gateway=None,
    governance=None,
    apply_journal=None,
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

    The risk gate is OFF unless BOTH ``risk_engine`` and ``risk_policy``
    are explicitly provided (or a ``governance`` evaluator is provided,
    in which case its engine and policy are used). Wiring it in makes
    HIGH/CRITICAL proposals require human approval. When the gate is
    enabled and no ``approval_store`` is supplied, a default
    ``ApprovalStore`` backed by the same evidence recorder is created so
    HIGH/CRITICAL patches have a real approval path (MISSION-012). The
    gate itself stays an explicit opt-in; the shipped default runtime
    never enables it.

    MISSION-019 additions:

    - ``governance`` is a single ``GovernanceEvaluator`` shared by the
      pipeline gate, the approval console and the apply boundary, so the
      three layers cannot drift on risk classification.
    - ``apply_journal`` wires an ``ApplyOutcomeJournal`` into the apply
      executor and the apply/verify pipeline so every apply intent and
      its terminal outcome is durably recorded and restart-reconcilable.
    """

    recorder = (
        evidence_recorder
        if evidence_recorder is not None
        else WorkerEvidenceRecorder(kernel=kernel)
    )

    if governance is not None:

        if risk_engine is None:

            risk_engine = governance.risk_engine

        if risk_policy is None:

            risk_policy = governance.risk_policy

    store = approval_store

    if store is None and (
        risk_engine is not None
        and risk_policy is not None
    ):

        ledger = None

        if approval_ledger_path is not None:

            ledger = ApprovalLedger(
                path=approval_ledger_path
            )

        store = ApprovalStore(
            evidence_recorder=recorder,
            ledger=ledger,
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
                else ApplyExecutor(
                    approval_store=store,
                    journal=apply_journal,
                )
            ),
            verification_executor=(
                verification_executor
                if verification_executor is not None
                else VerificationExecutor()
            ),
            journal=apply_journal,
        ),
        evidence_recorder=recorder,
        risk_engine=risk_engine,
        risk_policy=risk_policy,
        approval_store=store,
        approval_gateway=approval_gateway,
        governance=governance,
        apply_journal=apply_journal,
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


def run_startup_reconciliation(
    journal,
    allowed_paths=(),
    approval_store=None,
):

    """Detect-only restart reconciliation for the apply-outcome journal.

    Returns a ``ReconciliationReport`` classifying every journaled apply
    intent and flagging orphaned mutations / consumed approvals without
    a terminal outcome. Never mutates files and never bypasses the
    approval boundary. A corrupt journal raises ``RuntimeError``
    (fail-closed).
    """

    from simulation.agent.recovery.startup_reconciliation import (
        ReconciliationEngine,
    )

    engine = ReconciliationEngine(
        journal=journal,
        allowed_paths=tuple(allowed_paths),
        approval_store=approval_store,
    )

    return engine.detect()
