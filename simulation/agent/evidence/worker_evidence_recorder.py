from simulation.agent.evidence.worker_events import (
    WorkerEventType,
    build_worker_event,
)


class WorkerEvidenceRecorder:

    """Records worker action decisions into the event store.

    The recorder is the only bridge between the worker action
    pipeline/recovery loop and the existing event-sourcing
    infrastructure. Every recorded decision becomes a normal Event
    dispatched through the Kernel, so ordering, sequence assignment,
    hash-chain integrity, snapshotting and replay behave exactly like
    any other system event. No parallel evidence store is introduced.

    Payload contract:

    - Never contains patch old_content/new_content; only the
      deterministic patch fingerprint (SHA-256) is stored.
    - Never contains verification stdout/stderr; only status, exit
      code and failure reason are stored.
    - Never contains API keys or environment secrets.
    """

    def __init__(self, kernel):

        self.kernel = kernel

    def record_task_created(self, worker_result):

        payload = {
            "task_id": worker_result.task_id,
            "success": bool(worker_result.success),
            "summary": worker_result.summary,
            "patch_count": len(worker_result.patches),
        }

        self._emit(
            WorkerEventType.TASK_CREATED,
            payload,
            trace_message="Worker task recorded.",
        )

    def record_inspection(self, worker_result):

        results = []

        for record in worker_result.evidence:

            item = {
                "path": record.get("path"),
                "action": record.get("action"),
                "status": record.get("status"),
            }

            if record.get("characters") is not None:

                item["characters"] = record["characters"]

            results.append(item)

        payload = {
            "task_id": worker_result.task_id,
            "results": results,
        }

        self._emit(
            WorkerEventType.INSPECTION_COMPLETED,
            payload,
            trace_message=(
                "Worker inspection completed."
            ),
        )

    def record_patch_proposed(
        self,
        task_id,
        patch
    ):

        payload = {
            "task_id": task_id,
            "patch_fingerprint": patch.fingerprint(),
            "path": patch.path,
            "action": patch.action,
            "reason": patch.reason,
        }

        self._emit(
            WorkerEventType.PATCH_PROPOSED,
            payload,
            trace_message=(
                "Worker proposed a patch."
            ),
        )

    def record_patch_validated(
        self,
        task_id,
        patch,
        valid,
        message
    ):

        payload = {
            "task_id": task_id,
            "patch_fingerprint": patch.fingerprint(),
            "path": patch.path,
            "valid": bool(valid),
            "message": message,
        }

        self._emit(
            WorkerEventType.PATCH_VALIDATED,
            payload,
            trace_message=(
                "Patch validated."
                if valid
                else "Patch validation failed."
            ),
        )

    def record_controller_decision(
        self,
        task_id,
        patch,
        decision
    ):

        approved = decision.approved is True

        payload = {
            "task_id": task_id,
            "patch_fingerprint": (
                decision.patch_fingerprint
                or patch.fingerprint()
            ),
            "path": patch.path,
            "approved": approved,
            "reason": decision.reason,
        }

        event_type = (
            WorkerEventType.PATCH_APPROVED
            if approved
            else WorkerEventType.PATCH_REJECTED
        )

        self._emit(
            event_type,
            payload,
            trace_message=(
                "Controller approved patch."
                if approved
                else "Controller rejected patch."
            ),
        )

    def record_apply_result(
        self,
        task_id,
        patch,
        apply_result
    ):

        payload = {
            "task_id": task_id,
            "patch_fingerprint": patch.fingerprint(),
            "path": apply_result.path,
            "success": bool(apply_result.success),
            "message": apply_result.message,
        }

        event_type = (
            WorkerEventType.PATCH_APPLIED
            if apply_result.success
            else WorkerEventType.PATCH_APPLY_FAILED
        )

        self._emit(
            event_type,
            payload,
            trace_message=(
                "Patch applied."
                if apply_result.success
                else "Patch apply failed."
            ),
        )

    def record_verification_result(
        self,
        task_id,
        patch,
        verification_result
    ):

        passed = bool(verification_result.passed)

        payload = {
            "task_id": task_id,
            "patch_fingerprint": patch.fingerprint(),
            "status": verification_result.status,
            "passed": passed,
            "exit_code": verification_result.exit_code,
            "failure_reason": verification_result.failure_reason,
        }

        event_type = (
            WorkerEventType.VERIFICATION_COMPLETED
            if passed
            else WorkerEventType.VERIFICATION_FAILED
        )

        self._emit(
            event_type,
            payload,
            trace_message=(
                "Verification passed."
                if passed
                else "Verification failed."
            ),
        )

    def record_recovery_attempt(self, attempt):

        task_id = ""

        if attempt.worker_result is not None:

            task_id = attempt.worker_result.task_id

        payload = {
            "task_id": task_id,
            "attempt": attempt.attempt,
            "status": attempt.status,
            "failure_stage": attempt.failure_stage,
            "failure_reason": attempt.failure_reason,
            "patch_fingerprints": tuple(
                attempt.patch_fingerprints
            ),
        }

        self._emit(
            WorkerEventType.RECOVERY_ATTEMPTED,
            payload,
            trace_message=(
                f"Recovery attempt {attempt.attempt} "
                f"recorded as {attempt.status}."
            ),
        )

    def record_recovery_outcome(self, result):

        task_id = ""

        final = result.final_attempt

        if final is not None and final.worker_result is not None:

            task_id = final.worker_result.task_id

        payload = {
            "task_id": task_id,
            "terminal_status": result.terminal_status,
            "success": bool(result.success),
            "attempts_used": result.attempts_used,
            "max_attempts": result.max_attempts,
            "retry_count": result.retry_count,
            "failure_reason": result.failure_reason,
            "failure_stage": result.failure_stage,
        }

        event_type = (
            WorkerEventType.RECOVERY_SUCCEEDED
            if result.success
            else WorkerEventType.RECOVERY_FAILED
        )

        self._emit(
            event_type,
            payload,
            trace_message=(
                "Recovery succeeded."
                if result.success
                else "Recovery failed."
            ),
        )

    def _emit(
        self,
        event_type,
        payload,
        trace_message
    ):

        event = build_worker_event(
            event_type,
            payload,
        )

        self.kernel.dispatch(event)

        self._record_trace(
            event_type,
            trace_message,
            payload,
        )

    def _record_trace(
        self,
        stage,
        message,
        metadata
    ):

        get_trace = getattr(
            self.kernel,
            "get_decision_trace",
            None,
        )

        if get_trace is None:

            return

        trace = get_trace()

        if trace is None:

            return

        record = getattr(
            trace,
            "record",
            None,
        )

        if record is None:

            return

        record(
            stage=stage,
            message=message,
            metadata=dict(metadata),
        )
