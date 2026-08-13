from simulation.agent.apply.apply_authorization import (
    ApplyAuthorization
)

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.apply.file_applier import (
    FileApplier
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


def _normalize_attempt(attempt):

    if (
        isinstance(attempt, int)
        and not isinstance(attempt, bool)
        and attempt >= 1
    ):

        return attempt

    return 1


class ApplyExecutor:

    """Bridge authorization -> real file write.

    When an ``apply_outcome_journal`` is wired (MISSION-019), every
    apply attempt records an INTENT, the write is bracketed by
    APPLY_STARTED / APPLIED (or APPLY_FAILED), and the returned
    ``ApplyResult`` carries the ``intent_id`` so the upper pipeline can
    record the terminal VERIFIED / ROLLBACK_* outcome. The journal is
    durable outcome evidence, never an authorization input.
    """

    def __init__(
        self,
        approval_store=None,
        governance=None,
        journal=None
    ):

        self.authorization = (
            ApplyAuthorization(
                approval_store=approval_store,
                governance=governance,
            )
        )

        self.file_applier = (
            FileApplier()
        )

        self.journal = journal

    def apply(
        self,
        patch: PatchProposal,
        decision: ControllerDecision,
        attempt=None
    ) -> ApplyResult:

        attempt = _normalize_attempt(attempt)

        intent_id = ""

        if self.journal is not None:

            intent_id = self.journal.record_intent(
                patch,
                attempt=attempt,
                approval_id=getattr(
                    decision,
                    "approval_id",
                    "",
                ),
            )

        if not self.authorization.authorize(
            decision,
            patch
        ):

            if self.journal is not None and intent_id:

                self.journal.record_apply_failed(
                    intent_id,
                    reason="apply denied",
                )

            return ApplyResult(
                success=False,
                path=patch.path,
                message=(
                    "Apply denied: "
                    "Controller approval does not "
                    "match this patch."
                ),
                intent_id=intent_id,
            )

        if self.journal is not None and intent_id:

            self.journal.record_apply_started(
                intent_id
            )

        success, message = (
            self.file_applier.apply(
                patch
            )
        )

        if self.journal is not None and intent_id:

            if success:

                self.journal.record_applied(
                    intent_id
                )

            else:

                self.journal.record_apply_failed(
                    intent_id,
                    reason=message,
                )

        return ApplyResult(
            success=success,
            path=patch.path,
            message=message,
            intent_id=intent_id,
        )

    def rollback(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        """Restore the patch target to its exact pre-apply content.

        Used by the apply/verify pipeline to roll a failed patch back
        before any recovery retry so retries never build on top of a
        corrupted or failed-verification state.
        """

        return self.file_applier.restore(
            patch
        )
