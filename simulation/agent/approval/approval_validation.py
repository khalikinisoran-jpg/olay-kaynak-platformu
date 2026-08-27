"""Shared approval validation — single implementation for both pipelines (P10.3-B).

Extracted from WorkerActionPipeline and ExternalActionPipeline duplicated
``_approval_is_valid`` to prevent drift. Both pipelines must call this
same function.

Preserves all existing checks:
- approval type (must be Approval)
- patch fingerprint
- path
- action
- risk level
- attempt
- expiry

Fail-closed: any mismatch is denial.
"""

from __future__ import annotations

from simulation.agent.approval.approval import Approval


def is_approval_valid(approval, patch, risk_level: str, attempt: int) -> tuple[bool, str]:
    """Fail-closed validation of a returned approval.

    The pipeline never trusts whatever the approval store hands back.
    A usable approval must be a typed ``Approval`` bound to this exact
    patch fingerprint, path, action, risk context and attempt, and it
    must not be expired.
    """

    if approval is None:
        return False, ""

    if not isinstance(approval, Approval):
        return False, (
            "Malformed approval: expected an Approval "
            "authorization record."
        )

    if approval.patch_fingerprint != patch.fingerprint():
        return False, (
            "Approval is bound to a different patch "
            "fingerprint."
        )

    if approval.path != patch.path:
        return False, (
            "Approval is bound to a different path."
        )

    if approval.action != patch.action:
        return False, (
            "Approval is bound to a different action."
        )

    if approval.risk_level != risk_level:
        return False, (
            "Approval is bound to a different risk context."
        )

    if approval.attempt != attempt:
        return False, (
            "Approval is bound to a different attempt."
        )

    if approval.is_expired():
        return False, "Approval has expired."

    return True, ""
