from simulation.core.event import Event


class WorkerEventType:

    """Event types recorded for the worker action lifecycle.

    Every payload is intentionally secret-safe: patch content
    (old_text/new_text) is never stored; only the deterministic
    patch fingerprint is recorded. Verification stdout/stderr is
    never stored; only status, exit code and failure reason are.
    """

    TASK_CREATED = "WorkerTaskCreated"

    INSPECTION_COMPLETED = "WorkerInspectionCompleted"

    PATCH_PROPOSED = "WorkerPatchProposed"

    PATCH_VALIDATED = "WorkerPatchValidated"

    PATCH_APPROVED = "WorkerPatchApproved"

    PATCH_REJECTED = "WorkerPatchRejected"

    PATCH_APPLIED = "WorkerPatchApplied"

    PATCH_APPLY_FAILED = "WorkerPatchApplyFailed"

    VERIFICATION_COMPLETED = "WorkerVerificationCompleted"

    VERIFICATION_FAILED = "WorkerVerificationFailed"

    ROLLBACK_SUCCEEDED = "WorkerRollbackSucceeded"

    ROLLBACK_FAILED = "WorkerRollbackFailed"

    RECOVERY_ATTEMPTED = "WorkerRecoveryAttempted"

    RECOVERY_SUCCEEDED = "WorkerRecoverySucceeded"

    RECOVERY_FAILED = "WorkerRecoveryFailed"

    APPROVAL_GRANTED = "WorkerHumanApprovalGranted"

    RISK_ASSESSED = "WorkerRiskAssessed"

    ALL = frozenset([
        TASK_CREATED,
        INSPECTION_COMPLETED,
        PATCH_PROPOSED,
        PATCH_VALIDATED,
        PATCH_APPROVED,
        PATCH_REJECTED,
        PATCH_APPLIED,
        PATCH_APPLY_FAILED,
        VERIFICATION_COMPLETED,
        VERIFICATION_FAILED,
        ROLLBACK_SUCCEEDED,
        ROLLBACK_FAILED,
        RECOVERY_ATTEMPTED,
        RECOVERY_SUCCEEDED,
        RECOVERY_FAILED,
        APPROVAL_GRANTED,
        RISK_ASSESSED,
    ])


def build_worker_event(event_type, payload):

    if event_type not in WorkerEventType.ALL:

        raise ValueError(
            f"Unknown worker event type: {event_type}"
        )

    return Event(
        event_type=event_type,
        payload=dict(payload),
    )
