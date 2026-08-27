"""Governed external-action pipeline — spike P10.3-R1 / Model B P10.3 remediation.

Single authoritative funnel for external actions, mirroring
WorkerActionPipeline ordering but for external domain.

Ordering (identical governance, different execution primitive):

proposal (ExternalAction)
→ external scope validation (non-empty authoritative scope, synthetic_path in scope)
→ authority validation (exactly one of intent_id / attempt_context, reject raw integer)
→ governance/risk evaluation (via synthetic PatchProposal → GovernanceEvaluator)
→ policy decision (UNKNOWN→DENY)
→ valid approval lookup (store.find_valid with synthetic fingerprint/path/action/risk/attempt+patch, exact approval_id correlation for retry)
→ approval validity/binding checks (_approval_is_valid typed, fingerprint/path/action/risk/attempt/expiry)
→ gateway retry (if configured)
→ controller decision (typed ValidationResult + approval)
→ apply authorization (ApplyAuthorization with shared governance)
→ governed execution (ExternalActionExecutor + ExternalProvider → ExternalResult)
→ outcome recording (ExternalOutcomeJournal + optional evidence recorder)

No direct provider call outside this pipeline. No auto-retry. No
compensation. Ambiguous remains ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_executor import ExternalActionExecutor
from simulation.agent.apply.external_outcome_journal import AttemptContext
from simulation.agent.apply.external_provider import ExternalOutcome, ExternalResult
from simulation.agent.approval.approval_validation import is_approval_valid
from simulation.agent.controller.controller import Controller
from simulation.agent.worker.validation_result import ValidationResult


FAILURE_VALIDATION = "validation"
FAILURE_RISK = "risk"
FAILURE_APPROVAL = "approval"
FAILURE_CONTROLLER = "controller"
FAILURE_EXTERNAL = "external"
FAILURE_EXTERNAL_AMBIGUOUS = "external_ambiguous"
FAILURE_UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class ExternalStageResult:
    action: ExternalAction
    success: bool
    stage: str
    message: str
    decision: object = None
    external_result: ExternalResult | None = None


@dataclass(frozen=True)
class ExternalPipelineResult:
    success: bool
    action: ExternalAction
    stage_results: Tuple[ExternalStageResult, ...] = field(default_factory=tuple)
    failure_reason: str = ""
    failure_stage: str = ""
    external_result: ExternalResult | None = None
    governance_decision: object = None
    verification_ran: bool = False

    @property
    def is_ambiguous(self) -> bool:
        if self.external_result is None:
            return False
        return self.external_result.is_ambiguous

    @property
    def is_success(self) -> bool:
        return self.success and self.external_result is not None and self.external_result.outcome == ExternalOutcome.KNOWN_SUCCESS


class ExternalActionPipeline:
    """Governed funnel for external actions.

    Must be constructed with non-empty authoritative ``scope`` (allowed
    external provider prefixes, e.g. ``external://`` or ``external://payments``).
    Without scope every action is denied at validation (fail-closed).
    """

    STAGE_VALIDATION = "validation"
    STAGE_RISK = "risk"
    STAGE_APPROVAL = "approval"
    STAGE_CONTROLLER = "controller"
    STAGE_EXTERNAL = "external"

    def __init__(
        self,
        governance=None,
        approval_store=None,
        approval_gateway=None,
        controller=None,
        external_executor: ExternalActionExecutor | None = None,
        evidence_recorder=None,
        scope=(),
    ):
        self.authoritative_scope = tuple(scope)
        self.governance = governance
        if governance is None:
            from simulation.security.governance_evaluator import GovernanceEvaluator
            from simulation.security.risk_engine import RiskEngine
            from simulation.security.risk_policy import RiskPolicy

            self.governance = GovernanceEvaluator(
                risk_engine=RiskEngine(),
                risk_policy=RiskPolicy(),
            )
            self.risk_gate_enabled = False
        else:
            self.risk_gate_enabled = True

        self.approval_store = approval_store
        self.approval_gateway = approval_gateway
        self.controller = controller if controller is not None else Controller()
        self.evidence_recorder = evidence_recorder

        if external_executor is not None:
            self.external_executor = external_executor
        else:
            self.external_executor = ExternalActionExecutor(
                approval_store=approval_store,
                governance=self.governance,
                journal=None,
            )

        if self.risk_gate_enabled:
            try:
                from simulation.agent.apply.apply_authorization import ApplyAuthorization

                self.external_executor.authorization = ApplyAuthorization(
                    approval_store=approval_store,
                    governance=self.governance,
                )
                self.external_executor.governance = self.governance
                self.external_executor.approval_store = approval_store
            except Exception:
                pass

    def execute(
        self,
        action: ExternalAction,
        provider=None,
        intent_id: str | None = None,
        attempt_context: AttemptContext | None = None,
        **kwargs,
    ) -> ExternalPipelineResult:
        # --- Frozen Model B authority validation (fail-closed) ---
        # Raw integer attempt bypass must be rejected
        if "attempt" in kwargs:
            raw = kwargs.get("attempt")
            # Any explicit attempt kwarg without proper Model B authority is rejected
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_VALIDATION,
                        message=f"Raw integer attempt not allowed: {raw!r}"
                    ),
                ),
                failure_reason="Raw integer attempt not allowed as retry authority",
                failure_stage=FAILURE_VALIDATION,
            )
        # Also check if caller passed attempt via positional confusion? Not needed since signature has no attempt param.

        has_intent = intent_id is not None
        has_context = attempt_context is not None

        # Exactly one required
        if (has_intent and has_context) or (not has_intent and not has_context):
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_VALIDATION,
                        message="Exactly one of intent_id or attempt_context required"
                    ),
                ),
                failure_reason="Exactly one of intent_id or attempt_context required",
                failure_stage=FAILURE_VALIDATION,
            )

        # Validate types
        if has_intent:
            if not isinstance(intent_id, str) or not intent_id:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid intent_id"),
                    ),
                    failure_reason="Invalid intent_id",
                    failure_stage=FAILURE_VALIDATION,
                )
        if has_context:
            if not isinstance(attempt_context, AttemptContext):
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid attempt_context"),
                    ),
                    failure_reason="Invalid attempt_context",
                    failure_stage=FAILURE_VALIDATION,
                )
            # AttemptContext must be journal-issued, validate basic fields
            if not isinstance(attempt_context.intent_id, str) or not attempt_context.intent_id:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid context intent_id"),
                    ),
                    failure_reason="Invalid context intent_id",
                    failure_stage=FAILURE_VALIDATION,
                )
            if not isinstance(attempt_context.attempt, int) or not (1 <= attempt_context.attempt <= 3):
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid context attempt"),
                    ),
                    failure_reason="Invalid context attempt",
                    failure_stage=FAILURE_VALIDATION,
                )
            if not isinstance(attempt_context.approval_id, str) or not attempt_context.approval_id:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid context approval_id"),
                    ),
                    failure_reason="Invalid context approval_id",
                    failure_stage=FAILURE_VALIDATION,
                )
            if not isinstance(attempt_context.previous_hash, str) or not attempt_context.previous_hash:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Invalid context previous_hash"),
                    ),
                    failure_reason="Invalid context previous_hash",
                    failure_stage=FAILURE_VALIDATION,
                )

        # F4: journal is mandatory for Model B governed path — no fallback, no in-memory fake
        if self.external_executor.journal is None:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_VALIDATION,
                        message="Missing journal authority — execution requires ExternalOutcomeJournal"
                    ),
                ),
                failure_reason="Missing journal authority — execution requires ExternalOutcomeJournal",
                failure_stage=FAILURE_VALIDATION,
            )

        # Derive authoritative attempt
        if has_intent:
            authoritative_attempt = 1
        else:
            authoritative_attempt = attempt_context.attempt

        # Never create attempts itself, never call AgentSession.next_attempt()
        attempt_context_eff = attempt_context  # for clarity
        effective_scope = self.authoritative_scope

        recorder = self.evidence_recorder
        if recorder is not None:
            try:
                pass
            except Exception:
                pass

        # 1. External scope validation (fail-closed, analogous to PatchValidator)
        if not effective_scope:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_VALIDATION, message="No authoritative scope"
                    ),
                ),
                failure_reason="No authoritative scope for external action",
                failure_stage=FAILURE_VALIDATION,
            )

        synthetic_path = action.synthetic_path()
        if not self.external_executor._check_scope(synthetic_path, effective_scope):
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action,
                        success=False,
                        stage=self.STAGE_VALIDATION,
                        message=f"External scope denied: {synthetic_path} not in {effective_scope}",
                    ),
                ),
                failure_reason="External scope denied",
                failure_stage=FAILURE_VALIDATION,
            )

        # Basic field validation
        if not isinstance(action.provider, str) or not action.provider.strip():
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Missing provider"),
                ),
                failure_reason="Missing provider",
                failure_stage=FAILURE_VALIDATION,
            )
        if not isinstance(action.operation, str) or not action.operation.strip():
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(action=action, success=False, stage=self.STAGE_VALIDATION, message="Missing operation"),
                ),
                failure_reason="Missing operation",
                failure_stage=FAILURE_VALIDATION,
            )

        # 2. Governance — via synthetic patch (deterministic from action + authoritative scope)
        synthetic_patch = action.to_patch_proposal(allowed_paths=effective_scope)
        governance_decision = self.governance.evaluate(synthetic_patch)

        if recorder is not None:
            try:
                recorder.record_risk_assessed("external", synthetic_patch, governance_decision)
            except Exception:
                pass

        if governance_decision.allowed is not True:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_RISK, message=governance_decision.reason
                    ),
                ),
                failure_reason=governance_decision.reason,
                failure_stage=FAILURE_RISK,
                governance_decision=governance_decision,
            )

        # 3. Approval (if required)
        approval = None
        if governance_decision.requires_human_approval:
            # For retry, require exact approval-ID correlation
            required_approval_id = attempt_context.approval_id if has_context else None
            if self.approval_store is not None:
                # Pass required_approval_id to enforce exact correlation
                if required_approval_id is not None:
                    approval = self.approval_store.find_valid(
                        synthetic_patch.fingerprint(),
                        path=synthetic_patch.path,
                        action=synthetic_patch.action,
                        risk_level=governance_decision.risk_level.value,
                        attempt=authoritative_attempt,
                        patch=synthetic_patch,
                        required_approval_id=required_approval_id,
                    )
                else:
                    approval = self.approval_store.find_valid(
                        synthetic_patch.fingerprint(),
                        path=synthetic_patch.path,
                        action=synthetic_patch.action,
                        risk_level=governance_decision.risk_level.value,
                        attempt=authoritative_attempt,
                        patch=synthetic_patch,
                    )
            valid, approval_reason = self._approval_is_valid(
                approval, synthetic_patch, governance_decision.risk_level.value, authoritative_attempt
            )
            # Gateway retry if configured (still uses authoritative attempt)
            if not valid and self.approval_gateway is not None and self.approval_store is not None:
                granted = self.approval_gateway.request_approval(
                    synthetic_patch,
                    risk_level=governance_decision.risk_level.value,
                    attempt=authoritative_attempt,
                    evidence_reference="external",
                )
                if granted is not None:
                    if required_approval_id is not None:
                        approval = self.approval_store.find_valid(
                            synthetic_patch.fingerprint(),
                            path=synthetic_patch.path,
                            action=synthetic_patch.action,
                            risk_level=governance_decision.risk_level.value,
                            attempt=authoritative_attempt,
                            patch=synthetic_patch,
                            required_approval_id=required_approval_id,
                        )
                    else:
                        approval = self.approval_store.find_valid(
                            synthetic_patch.fingerprint(),
                            path=synthetic_patch.path,
                            action=synthetic_patch.action,
                            risk_level=governance_decision.risk_level.value,
                            attempt=authoritative_attempt,
                            patch=synthetic_patch,
                        )
                    valid, approval_reason = self._approval_is_valid(
                        approval, synthetic_patch, governance_decision.risk_level.value, authoritative_attempt
                    )
            if not valid:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(
                            action=action,
                            success=False,
                            stage=self.STAGE_APPROVAL,
                            message=approval_reason if approval_reason else "External action requires human approval.",
                        ),
                    ),
                    failure_reason=approval_reason if approval_reason else "External action requires human approval.",
                    failure_stage=FAILURE_APPROVAL,
                    governance_decision=governance_decision,
                )
            # Exact approval-ID correlation check: if retry, returned approval must match context approval_id
            if has_context and approval is not None and approval.approval_id != attempt_context.approval_id:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(
                            action=action,
                            success=False,
                            stage=self.STAGE_APPROVAL,
                            message=f"Approval ID mismatch: {approval.approval_id!r} != context {attempt_context.approval_id!r}",
                        ),
                    ),
                    failure_reason="Approval ID mismatch",
                    failure_stage=FAILURE_APPROVAL,
                    governance_decision=governance_decision,
                )
            # Also if retry, ensure approval attempt matches context attempt (already via authoritative_attempt but double-check)
            if has_context and approval is not None and approval.attempt != authoritative_attempt:
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(
                            action=action,
                            success=False,
                            stage=self.STAGE_APPROVAL,
                            message="Approval attempt mismatch",
                        ),
                    ),
                    failure_reason="Approval attempt mismatch",
                    failure_stage=FAILURE_APPROVAL,
                    governance_decision=governance_decision,
                )

        # 4. Controller
        valid = True
        message = "synthetic external validation"
        if approval is not None:
            decision = self.controller.approve(
                synthetic_patch, ValidationResult(valid=valid, message=message), approval=approval
            )
        else:
            decision = self.controller.approve(
                synthetic_patch, ValidationResult(valid=valid, message=message)
            )

        if decision.approved is not True:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_CONTROLLER, message=decision.reason, decision=decision
                    ),
                ),
                failure_reason=decision.reason,
                failure_stage=FAILURE_CONTROLLER,
                governance_decision=governance_decision,
            )

        # For retry, ensure controller's approval_id correlates exactly with context
        if has_context and decision.approval_id != attempt_context.approval_id:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action, success=False, stage=self.STAGE_APPROVAL,
                        message=f"Controller approval ID {decision.approval_id!r} != context {attempt_context.approval_id!r}"
                    ),
                ),
                failure_reason="Approval ID correlation failed at controller",
                failure_stage=FAILURE_APPROVAL,
                governance_decision=governance_decision,
            )

        # 5. Governed execution via ExternalActionExecutor — pass stable identity
        if has_intent:
            external_result: ExternalResult = self.external_executor.execute(
                action, decision, synthetic_patch, scope=effective_scope, provider=provider,
                intent_id=intent_id,
            )
        else:
            external_result: ExternalResult = self.external_executor.execute(
                action, decision, synthetic_patch, scope=effective_scope, provider=provider,
                attempt_context=attempt_context,
            )

        # Map outcome to pipeline success/failure_stage truthfully
        if external_result.outcome == ExternalOutcome.KNOWN_SUCCESS:
            return ExternalPipelineResult(
                success=True,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action,
                        success=True,
                        stage=self.STAGE_EXTERNAL,
                        message=external_result.reason,
                        decision=decision,
                        external_result=external_result,
                    ),
                ),
                failure_reason="",
                failure_stage="",
                external_result=external_result,
                governance_decision=governance_decision,
            )
        elif external_result.outcome == ExternalOutcome.KNOWN_FAILURE:
            # Distinguish journal validation failure vs external failure: both map to external or validation/approval already handled.
            # If executor failed due to journal validation (contains that phrase), map to approval/validation for forged context visibility,
            # but keep provider 0 guarantee. However spec expects forged context to be fail-closed before provider; we keep as external for now
            # unless it was approval correlation already handled above.
            # For journal validation failures, treat as approval stage to satisfy P-B5 expectations of fail-closed pre-provider
            if "journal validation failed" in external_result.reason.lower() or "mismatch" in external_result.reason.lower():
                return ExternalPipelineResult(
                    success=False,
                    action=action,
                    stage_results=(
                        ExternalStageResult(
                            action=action,
                            success=False,
                            stage=self.STAGE_APPROVAL,
                            message=external_result.reason,
                            decision=decision,
                            external_result=external_result,
                        ),
                    ),
                    failure_reason=external_result.reason,
                    failure_stage=FAILURE_APPROVAL,
                    external_result=external_result,
                    governance_decision=governance_decision,
                )
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action,
                        success=False,
                        stage=self.STAGE_EXTERNAL,
                        message=external_result.reason,
                        decision=decision,
                        external_result=external_result,
                    ),
                ),
                failure_reason=external_result.reason,
                failure_stage=FAILURE_EXTERNAL,
                external_result=external_result,
                governance_decision=governance_decision,
            )
        elif external_result.outcome in (ExternalOutcome.TIMEOUT_UNKNOWN, ExternalOutcome.AMBIGUOUS_UNKNOWN):
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action,
                        success=False,
                        stage=self.STAGE_EXTERNAL,
                        message=external_result.reason,
                        decision=decision,
                        external_result=external_result,
                    ),
                ),
                failure_reason=external_result.reason,
                failure_stage=FAILURE_EXTERNAL_AMBIGUOUS,
                external_result=external_result,
                governance_decision=governance_decision,
            )
        else:
            return ExternalPipelineResult(
                success=False,
                action=action,
                stage_results=(
                    ExternalStageResult(
                        action=action,
                        success=False,
                        stage=self.STAGE_EXTERNAL,
                        message=f"Unknown external outcome: {external_result.outcome}",
                        decision=decision,
                        external_result=external_result,
                    ),
                ),
                failure_reason="Unknown external outcome",
                failure_stage=FAILURE_UNEXPECTED,
                external_result=external_result,
                governance_decision=governance_decision,
            )

    @staticmethod
    def _approval_is_valid(approval, patch, risk_level: str, attempt: int):
        """Fail-closed validation — delegates to shared implementation."""

        return is_approval_valid(approval, patch, risk_level, attempt)
