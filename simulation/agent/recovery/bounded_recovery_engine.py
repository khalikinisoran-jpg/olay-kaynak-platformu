from simulation.agent.pipeline.worker_action_pipeline import (
    FAILURE_UNEXPECTED,
    FAILURE_VERIFICATION,
    FAILURE_WORKER,
)

from simulation.agent.recovery.recovery_attempt import (
    AttemptStatus,
    RecoveryAttempt,
)

from simulation.agent.recovery.recovery_result import (
    RecoveryResult
)


class RecoveryError(Exception):

    """Base class for recovery orchestration failures."""


class WorkerProductionError(RecoveryError):
    pass


class PipelineExecutionError(RecoveryError):
    pass


class BoundedRecoveryEngine:

    """Bounded iterative recovery orchestration for verification FAIL.

    The retry decision is made by this orchestrator, never by the
    Worker/LLM. The Worker can only produce a new proposal. The loop is
    an iterative for-loop over a single authoritative attempt counter;
    it never recurses.

    Retry eligibility (red line 4):

    - Validator FAIL        -> STOP (non-verification)
    - Controller REJECT     -> STOP (non-verification)
    - Apply FAIL            -> STOP (non-verification)
    - Verification FAIL     -> RETRY only when the attempt budget remains
    - Verification PASS     -> STOP immediately

    Strict attempt boundary (security contract):

    - attempt 1 FAIL -> RETRY
    - attempt 2 FAIL -> RETRY
    - attempt 3 FAIL -> TERMINAL
    - attempt 4       -> NEVER POSSIBLE

    The caller-provided max_attempts is clamped by a hard code cap of
    exactly 3 (red line 2). None, negative values, zero and non-integers
    fall back to the default. No caller value can produce unlimited
    retries and no caller value can produce a fourth attempt.
    """

    MAX_ATTEMPTS_CAP = 3

    DEFAULT_MAX_ATTEMPTS = 3

    STATUS_SUCCESS = "SUCCESS"

    STATUS_TERMINAL_FAILURE = "TERMINAL_FAILURE"

    def __init__(
        self,
        worker,
        worker_pipeline,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        evidence_recorder=None
    ):

        self.worker = worker

        self.worker_pipeline = worker_pipeline

        self.max_attempts = self._bounded_max_attempts(
            max_attempts
        )

        self.evidence_recorder = evidence_recorder

    def execute(
        self,
        agent,
        prompt,
        initial_worker_result=None,
        verify_paths=None,
        test_targets=(),
    ) -> RecoveryResult:

        attempts = []

        recovery_evidence = ()

        seen_fingerprints = set()

        attempt_number = 1

        effective_max = self.max_attempts

        while attempt_number <= effective_max:

            if (
                attempt_number == 1
                and initial_worker_result is not None
            ):

                worker_result = initial_worker_result

            else:

                try:

                    worker_result = self.worker.execute(
                        agent,
                        prompt,
                        attempt=attempt_number,
                        recovery_evidence=recovery_evidence,
                    )

                except Exception as exc:

                    attempt = self._error_attempt(
                        attempt_number,
                        "worker",
                        str(exc),
                        FAILURE_WORKER,
                    )

                    attempts.append(attempt)

                    self._record_attempt_event(attempt)

                    return self._terminal(
                        attempts,
                        (
                            "Worker exception on attempt "
                            f"{attempt_number}: {exc}"
                        ),
                        FAILURE_WORKER,
                    )

            if not self._has_proposals(worker_result):

                attempt = self._blocked_attempt(
                    attempt_number,
                    worker_result,
                    "Worker produced no patch proposals.",
                    FAILURE_WORKER,
                )

                attempts.append(attempt)

                self._record_attempt_event(attempt)

                return self._terminal(
                    attempts,
                    "Worker produced no patch proposals.",
                    FAILURE_WORKER,
                )

            fingerprints, terminal = self._safe_fingerprints(
                attempt_number,
                worker_result,
                attempts,
            )

            if terminal is not None:

                return terminal

            duplicate = self._first_duplicate(
                fingerprints,
                seen_fingerprints
            )

            if duplicate is not None:

                attempt = self._blocked_attempt(
                    attempt_number,
                    worker_result,
                    (
                        "Duplicate proposal fingerprint: "
                        f"{duplicate}"
                    ),
                    FAILURE_WORKER,
                    fingerprints,
                )

                attempts.append(attempt)

                self._record_attempt_event(attempt)

                return self._terminal(
                    attempts,
                    (
                        "Duplicate proposal fingerprint: "
                        f"{duplicate}"
                    ),
                    FAILURE_WORKER,
                )

            seen_fingerprints.update(fingerprints)

            try:

                pipeline_result = self.worker_pipeline.execute(
                    worker_result,
                    verify_paths=verify_paths,
                    test_targets=test_targets,
                    attempt=attempt_number,
                )

            except Exception as exc:

                attempt = self._error_attempt(
                    attempt_number,
                    "pipeline",
                    str(exc),
                    FAILURE_UNEXPECTED,
                )

                attempts.append(attempt)

                self._record_attempt_event(attempt)

                return self._terminal(
                    attempts,
                    (
                        "Pipeline exception on attempt "
                        f"{attempt_number}: {exc}"
                    ),
                    FAILURE_UNEXPECTED,
                )

            attempt = self._record_attempt(
                attempt_number,
                worker_result,
                pipeline_result,
                fingerprints,
            )

            attempts.append(attempt)

            self._record_attempt_event(attempt)

            if pipeline_result.success:

                return self._success(attempts)

            if pipeline_result.failure_stage != FAILURE_VERIFICATION:

                return self._terminal(
                    attempts,
                    pipeline_result.failure_reason,
                    pipeline_result.failure_stage,
                )

            recovery_evidence = pipeline_result.evidence

            governed = self._governed_budget(
                pipeline_result
            )

            if governed is not None:

                effective_max = min(
                    effective_max,
                    governed,
                )

            if attempt_number >= effective_max:

                return self._terminal(
                    attempts,
                    (
                        "Verification failed on the final "
                        "attempt."
                    ),
                    FAILURE_VERIFICATION,
                )

            attempt_number += 1

        return self._terminal(
            attempts,
            "Verification failed on the final attempt.",
            FAILURE_VERIFICATION,
        )

    def _governed_budget(self, pipeline_result) -> int | None:

        """Return the policy-enforced retry budget for a run, or None.

        The budget comes from the ``RiskPolicy`` via the governance
        decisions the pipeline produced (MISSION-H H-002). The policy
        is authoritative for the governed retry budget: the recovery
        engine's generic default can never raise it. When no governed
        decisions exist (ungoverned pipeline) None is returned and the
        caller-supplied bounded cap applies unchanged.
        """

        decisions = getattr(
            pipeline_result,
            "governance_decisions",
            (),
        )

        if not decisions:

            return None

        budgets = [
            decision.max_attempts
            for decision in decisions
        ]

        return min(budgets)

    def _has_proposals(self, worker_result) -> bool:

        if worker_result is None:

            return False

        if not worker_result.success:

            return False

        return bool(worker_result.patches)

    def _safe_fingerprints(
        self,
        attempt_number,
        worker_result,
        attempts,
    ):

        try:

            fingerprints = tuple(
                patch.fingerprint()
                for patch in worker_result.patches
            )

        except Exception as exc:

            attempt = self._error_attempt(
                attempt_number,
                "fingerprint",
                str(exc),
                FAILURE_UNEXPECTED,
            )

            attempts.append(attempt)

            self._record_attempt_event(attempt)

            return None, self._terminal(
                attempts,
                f"Fingerprint exception: {exc}",
                FAILURE_UNEXPECTED,
            )

        return fingerprints, None

    def _first_duplicate(self, fingerprints, seen) -> str | None:

        for fingerprint in fingerprints:

            if fingerprint in seen:

                return fingerprint

        return None

    def _record_attempt(
        self,
        attempt_number,
        worker_result,
        pipeline_result,
        fingerprints,
    ) -> RecoveryAttempt:

        if pipeline_result.success:

            status = AttemptStatus.SUCCESS

        elif (
            pipeline_result.failure_stage == FAILURE_VERIFICATION
        ):

            status = AttemptStatus.FAILED

        else:

            status = AttemptStatus.BLOCKED

        return RecoveryAttempt(
            attempt=attempt_number,
            status=status,
            worker_result=worker_result,
            pipeline_result=pipeline_result,
            failure_reason=pipeline_result.failure_reason,
            evidence=pipeline_result.evidence,
            patch_fingerprints=fingerprints,
            failure_stage=pipeline_result.failure_stage,
        )

    def _blocked_attempt(
        self,
        attempt_number,
        worker_result,
        reason,
        failure_stage=FAILURE_WORKER,
        fingerprints=(),
    ) -> RecoveryAttempt:

        return RecoveryAttempt(
            attempt=attempt_number,
            status=AttemptStatus.BLOCKED,
            worker_result=worker_result,
            failure_reason=reason,
            patch_fingerprints=tuple(fingerprints),
            failure_stage=failure_stage,
        )

    def _error_attempt(
        self,
        attempt_number,
        source,
        message,
        failure_stage=FAILURE_UNEXPECTED,
    ) -> RecoveryAttempt:

        return RecoveryAttempt(
            attempt=attempt_number,
            status=AttemptStatus.ERROR,
            failure_reason=f"{source} exception: {message}",
            failure_stage=failure_stage,
        )

    def _success(self, attempts) -> RecoveryResult:

        result = RecoveryResult(
            terminal_status=self.STATUS_SUCCESS,
            attempts_used=len(attempts),
            max_attempts=self.max_attempts,
            attempt_history=tuple(attempts),
        )

        self._record_outcome_event(result)

        return result

    def _terminal(
        self,
        attempts,
        failure_reason,
        failure_stage=FAILURE_UNEXPECTED,
    ) -> RecoveryResult:

        result = RecoveryResult(
            terminal_status=self.STATUS_TERMINAL_FAILURE,
            attempts_used=len(attempts),
            max_attempts=self.max_attempts,
            attempt_history=tuple(attempts),
            failure_reason=failure_reason,
            failure_stage=failure_stage,
        )

        self._record_outcome_event(result)

        return result

    def _record_attempt_event(self, attempt):

        if self.evidence_recorder is None:

            return

        self.evidence_recorder.record_recovery_attempt(
            attempt
        )

    def _record_outcome_event(self, result):

        if self.evidence_recorder is None:

            return

        self.evidence_recorder.record_recovery_outcome(
            result
        )

    def _bounded_max_attempts(self, value) -> int:

        if value is None:

            return self.DEFAULT_MAX_ATTEMPTS

        try:

            candidate = int(value)

        except (TypeError, ValueError):

            return self.DEFAULT_MAX_ATTEMPTS

        if candidate < 1:

            return self.DEFAULT_MAX_ATTEMPTS

        return min(
            candidate,
            self.MAX_ATTEMPTS_CAP
        )
