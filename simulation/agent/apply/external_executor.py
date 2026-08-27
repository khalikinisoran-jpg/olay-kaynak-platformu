"""Governed external-action executor — spike P10.3-R1 (Model B P10.3 remediation).

Single production primitive for external actions, analogous to
ApplyExecutor/FileApplier for file actions. It is NOT a second
authority; it is called only via ExternalActionPipeline after the
full governance chain (PatchValidator-like scope, Risk, Approval,
Controller, ApplyAuthorization). Direct provider execution is forbidden
outside this executor.

The executor:
- requires non-empty authoritative scope and synthetic_path in scope,
- requires ApplyAuthorization to succeed (typed ControllerDecision,
  fingerprint match, shared GovernanceEvaluator, store-verified approval
  for HIGH/CRITICAL/UNKNOWN),
- records to ExternalOutcomeJournal before and after provider call,
- never synthesizes success/failure, never auto-retries, never
  compensates — ambiguous remains ambiguous,
- never assumes provider supports reconcile/status lookup.
- MODEL B: initial execution uses stable intent_id via
  journal.record_intent(intent_id, action, attempt=1, approval_id=...)
  retry execution validates AttemptContext via journal.start_opened_attempt
  before provider call, never generates UUID.
"""

from __future__ import annotations

from simulation.agent.apply.apply_authorization import ApplyAuthorization
from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_outcome_journal import (
    AttemptContext,
    ExternalOutcomeJournal,
    TYPE_EXTERNAL_SUCCESS,
    TYPE_EXTERNAL_FAILED,
    TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
    TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN,
)
from simulation.agent.apply.external_provider import ExternalOutcome, ExternalResult


class ExternalAuthorizationFailed(Exception):
    pass


class ExternalActionExecutor:
    """Fail-closed executor for external provider calls."""

    def __init__(
        self,
        approval_store=None,
        governance=None,
        journal: ExternalOutcomeJournal | None = None,
    ):
        self.approval_store = approval_store
        self.governance = governance
        self.journal = journal
        # Reuse shared authorization primitive with same governance
        self.authorization = ApplyAuthorization(
            approval_store=approval_store,
            governance=governance,
        )

    def _check_scope(self, synthetic_path: str, scope: tuple[str, ...]) -> bool:
        if not scope:
            return False
        for allowed in scope:
            if not isinstance(allowed, str) or not allowed:
                continue
            if synthetic_path == allowed:
                return True
            if synthetic_path.startswith(allowed.rstrip("/") + "/"):
                return True
            if allowed == "external://":
                if synthetic_path.startswith("external://"):
                    return True
        return False

    def execute(
        self,
        action: ExternalAction,
        decision,
        synthetic_patch,
        scope: tuple[str, ...] = (),
        provider=None,
        intent_id: str | None = None,
        attempt_context: AttemptContext | None = None,
        attempt=None,
    ) -> ExternalResult:
        """Execute external action through provider after authorization.

        Model B frozen contract:
        - Exactly one of intent_id (initial) or attempt_context (retry) must be supplied.
        - Raw integer attempt is not authority — rejected fail-closed.
        - Initial calls journal.record_intent(intent_id, action, attempt=1, approval_id=...)
        - Retry validates via journal.start_opened_attempt(context, action, approval_id) before provider.

        Returns ExternalResult; records durable journal transitions.
        On authorization failure returns a synthetic KNOWN_FAILURE result
        without calling provider (provider call_count stays 0).
        """
        effective_scope = tuple(scope) if isinstance(scope, tuple) else tuple(scope) if scope else ()

        # Reject raw integer attempt bypass when Model B authority not supplied but attempt param present
        # If caller supplied attempt integer without intent_id/attempt_context, treat as legacy bypass -> deny
        if attempt is not None and intent_id is None and attempt_context is None:
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason="Raw integer attempt not allowed as retry authority",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Scope check (fail-closed)
        synthetic_path = action.synthetic_path()
        if not self._check_scope(synthetic_path, effective_scope):
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason=f"External scope denied: {synthetic_path} not in {effective_scope}",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Authority validation: exactly one of intent_id / attempt_context when journal present
        is_initial = intent_id is not None
        is_retry = attempt_context is not None
        if self.journal is not None:
            if (is_initial and is_retry) or (not is_initial and not is_retry):
                return ExternalResult(
                    outcome=ExternalOutcome.KNOWN_FAILURE,
                    success=False,
                    reason="Exactly one of intent_id or attempt_context required",
                    provider_response=None,
                    idempotency_key=action.idempotency_key or "",
                    fingerprint=action.fingerprint(),
                )
            if is_initial:
                if not isinstance(intent_id, str) or not intent_id:
                    return ExternalResult(
                        outcome=ExternalOutcome.KNOWN_FAILURE,
                        success=False,
                        reason="Invalid intent_id",
                        provider_response=None,
                        idempotency_key=action.idempotency_key or "",
                        fingerprint=action.fingerprint(),
                    )
            if is_retry:
                if not isinstance(attempt_context, AttemptContext):
                    return ExternalResult(
                        outcome=ExternalOutcome.KNOWN_FAILURE,
                        success=False,
                        reason="Invalid attempt_context",
                        provider_response=None,
                        idempotency_key=action.idempotency_key or "",
                        fingerprint=action.fingerprint(),
                    )
        else:
            # F4: Model B governed external path MUST have a journal — no in-memory fallback, no fake journal.
            # Absence of journal is a configuration failure → fail closed before provider.
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason="Missing journal authority — execution requires ExternalOutcomeJournal",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Journal handling
        journal_intent_id = None
        is_retry_path = is_retry

        if self.journal is not None:
            try:
                if is_initial:
                    # Initial execution: record intent with stable ID, attempt 1
                    approval_id_for_intent = getattr(decision, "approval_id", "") if decision is not None else ""
                    # MUST use Model B overload with explicit intent_id, never UUID legacy
                    journal_intent_id = self.journal.record_intent(
                        intent_id,
                        action,
                        attempt=1,
                        approval_id=approval_id_for_intent,
                        reason="governed external intent",
                    )
                    # record_started for attempt 1
                    self.journal.record_started(journal_intent_id, reason="governed execution started")
                else:
                    # Retry execution: validate context before anything else, appends external_started
                    approval_id_for_retry = getattr(decision, "approval_id", "") if decision is not None else ""
                    # Fail closed if approval_id does not match context (journal will also check)
                    if approval_id_for_retry != attempt_context.approval_id:
                        return ExternalResult(
                            outcome=ExternalOutcome.KNOWN_FAILURE,
                            success=False,
                            reason=f"Approval ID mismatch: decision {approval_id_for_retry!r} != context {attempt_context.approval_id!r}",
                            provider_response=None,
                            idempotency_key=action.idempotency_key or "",
                            fingerprint=action.fingerprint(),
                        )
                    self.journal.start_opened_attempt(
                        attempt_context,
                        action,
                        approval_id=approval_id_for_retry,
                    )
                    journal_intent_id = attempt_context.intent_id
            except Exception as exc:
                # Journal validation/intent failure is fail-closed before provider
                # Distinguish intent failure vs retry validation: both return failure without provider call
                reason = str(exc) if str(exc) else "External journal validation failed"
                # Ensure no provider call
                return ExternalResult(
                    outcome=ExternalOutcome.KNOWN_FAILURE,
                    success=False,
                    reason=f"External journal validation failed: {reason}",
                    provider_response=None,
                    idempotency_key=action.idempotency_key or "",
                    fingerprint=action.fingerprint(),
                )
        else:
            # Already returned above for journal=None; this branch is unreachable but keep fail-closed
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason="Missing journal authority",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Authorization — typed decision + fingerprint + recomputed risk + store
        try:
            authorized = self.authorization.authorize(decision, synthetic_patch)
        except Exception:
            authorized = False

        if not authorized:
            if journal_intent_id is not None and self.journal is not None:
                try:
                    self.journal.record_failed(journal_intent_id, reason="authorization denied")
                except Exception:
                    pass
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason="External authorization denied",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Provider must be supplied; no default real provider
        if provider is None:
            if journal_intent_id is not None and self.journal is not None:
                try:
                    self.journal.record_failed(journal_intent_id, reason="no provider supplied")
                except Exception:
                    pass
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason="No external provider supplied",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Call provider — deterministic fake in tests
        try:
            result: ExternalResult = provider.execute(action)
        except Exception as exc:
            if journal_intent_id is not None and self.journal is not None:
                try:
                    self.journal.record_failed(journal_intent_id, reason=f"provider exception: {exc}")
                except Exception:
                    pass
            return ExternalResult(
                outcome=ExternalOutcome.KNOWN_FAILURE,
                success=False,
                reason=f"Provider exception: {exc}",
                provider_response=None,
                idempotency_key=action.idempotency_key or "",
                fingerprint=action.fingerprint(),
            )

        # Record outcome to journal — must distinguish all four states,
        # never synthesize success/failure from ambiguous.
        if journal_intent_id is not None and self.journal is not None:
            try:
                if result.outcome == ExternalOutcome.KNOWN_SUCCESS:
                    self.journal.record_success(journal_intent_id, reason=result.reason or "external known success")
                elif result.outcome == ExternalOutcome.KNOWN_FAILURE:
                    self.journal.record_failed(journal_intent_id, reason=result.reason or "external known failure")
                elif result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN:
                    self.journal.record_timeout_unknown(journal_intent_id, reason=result.reason or "external timeout unknown")
                elif result.outcome == ExternalOutcome.AMBIGUOUS_UNKNOWN:
                    self.journal.record_ambiguous_unknown(journal_intent_id, reason=result.reason or "external ambiguous unknown")
                else:
                    self.journal.record_failed(journal_intent_id, reason=f"unknown outcome: {result.outcome}")
            except Exception:
                pass

        return result
