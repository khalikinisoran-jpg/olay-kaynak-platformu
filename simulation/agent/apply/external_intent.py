"""External intent helper — stable business-operation identity (P10.3-C2b).

Pure, deterministic intent_id derivation for MODEL B stable lineage.

intent_id = sha256( ExternalAction.fingerprint() + "|" + workspace + "|" + request_nonce )[:16]

- Pure function: no journal write, no lock, no provider, no ApprovalStore/RiskEngine import.
- workspace: logical workspace string (e.g., str(Path) or "external://"), part of identity
- request_nonce: human-supplied request identifier (e.g., uuid4 hex or goal hash) that
  distinguishes NEW BUSINESS OPERATION (new nonce → new intent_id) vs SAME INTENT RETRY
  (reuse intent_id, no new create_intent call).

Retry reuses the same intent_id returned by the initial create_intent.
"""

from __future__ import annotations

import hashlib


def create_intent(
    provider: str,
    operation: str,
    payload: str,
    idempotency_key: str,
    reason: str,
    workspace: str,
    request_nonce: str,
) -> str:
    from simulation.agent.apply.external_action import ExternalAction

    action = ExternalAction(
        provider=provider if isinstance(provider, str) else "",
        operation=operation if isinstance(operation, str) else "",
        payload=payload if isinstance(payload, str) else "",
        idempotency_key=idempotency_key if isinstance(idempotency_key, str) else "",
        reason=reason if isinstance(reason, str) else "",
    )
    fp = action.fingerprint()
    ws = workspace if isinstance(workspace, str) else str(workspace) if workspace is not None else ""
    nonce = request_nonce if isinstance(request_nonce, str) else str(request_nonce) if request_nonce is not None else ""
    raw = f"{fp}|{ws}|{nonce}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
