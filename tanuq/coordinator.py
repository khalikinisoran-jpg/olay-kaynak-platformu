"""Tanuq OperationCoordinator — single orchestration facade over the
existing TANUQ projections and the governed execution chain.

BOUNDARY CONTRACT: the coordinator is NOT a governance authority and
computes nothing on its own. Every method delegates to the existing,
tested layers:

    operations      -> tanuq.evidence.operations
    lineage         -> tanuq.evidence.lineage
    get_operation   -> tanuq.evidence.operations (selector)
    incidents       -> tanuq.incidents.collect_incidents
    export          -> tanuq.evidence.export_evidence
    status          -> chain_status + pending count + config summary
    execute         -> tanuq.agent_adapter.execute (governed pipeline)

``execute`` is pure orchestration/delegation: it never grants, never
consumes, never revokes, never applies and never recomputes a
governance decision — the full governed chain inside agent_adapter /
WorkerActionPipeline remains the only authority.

In-flight state is RAM-only orchestration bookkeeping (thread-safe,
process-local): it tracks that an execute is running, is cleared in a
``finally`` block on every outcome, and is never persisted or treated
as durable reality. Durable reality remains the four hash-chained
journals and their projections.
"""
import threading

from tanuq.config import tanuq_data_dir, now_iso
from tanuq.evidence import (
    chain_status,
    export_evidence,
    lineage,
    operations,
)
from tanuq.incidents import collect_incidents
from tanuq.pending import load_pending

_LIMITS = {
    "os_sandbox": False,
    "network_enforcement": False,
    "governed_channel_only": True,
}


class OperationCoordinator:

    def __init__(self, env):
        self.env = env
        self._in_flight = {}
        self._in_flight_lock = threading.Lock()

    @property
    def workspace(self):
        return self.env.workspace

    def _chain(self):
        key = None
        anchor = getattr(self.env.store, "chain_anchor", None)
        if anchor is not None:
            key = anchor.key
        return chain_status(tanuq_data_dir(self.env.workspace), key)

    def operations(self, fingerprint=None, operation_id=None, limit=20):
        return operations(
            self.env,
            fingerprint=fingerprint,
            operation_id=operation_id,
            limit=limit,
        )

    def get_operation(self, selector, limit=20):
        """Resolve one operation by operation/intent id (full or
        prefix) or by fingerprint (full or prefix). Returns the
        operation dict or None. Delegates to operations(); selector
        semantics are the existing ones."""
        report = self.operations(fingerprint=selector, limit=limit)
        matches = report["operations"]
        if not matches:
            report = self.operations(operation_id=selector, limit=limit)
            matches = report["operations"]
        if not matches:
            return None
        return matches[0]

    def lineage(self, fingerprint=None, limit=20):
        return lineage(self.env, fingerprint=fingerprint, limit=limit)

    def incidents(self):
        return collect_incidents(self.env)

    def export(self):
        return export_evidence(self.env)

    def status(self):
        config = self.env.config
        chain = self._chain()
        return {
            "workspace": str(self.env.workspace),
            "protected_scope": list(config.allowed_paths),
            "governed": True,
            "verification_depth": config.verification_depth,
            "chain_valid": chain["chain_valid"],
            "anchor": chain["anchor"],
            "events": chain["events"],
            "pending": len(load_pending(self.env.workspace)),
            "limits": dict(_LIMITS),
        }

    # ---- propose orchestration (delegation only) ----

    def propose(self, payload_text, session=None):
        """Delegate to agent_adapter.propose (no authority).

        Translates the generic proposal payload through the existing
        governance evaluation + pending registration chain and returns
        the machine-readable verdict unchanged.
        """
        from tanuq import agent_adapter
        return agent_adapter.propose(self.env, payload_text, session=session)

    # ---- execute orchestration (delegation only; RAM-only state) ----

    def _in_flight_key(self, fingerprint, run_all):
        if fingerprint:
            return f"fp:{fingerprint}"
        if run_all:
            return "ALL"
        return "NEXT"

    def execute(self, fingerprint=None, run_all=False, session=None):
        """Orchestrate one governed execution via agent_adapter.

        Delegation-only: the full governed chain (PatchValidator ->
        GovernanceEvaluator -> ApprovalStore -> Controller ->
        ApplyAuthorization -> FileApplier -> VerificationExecutor ->
        journals) runs inside agent_adapter/WorkerActionPipeline and
        the result is returned unchanged. The coordinator only
        reserves a RAM-only in-flight slot so two concurrent calls for
        the same selector cannot interleave; the slot is cleared in a
        ``finally`` block on every outcome (success, denial, exception).
        """
        from tanuq import agent_adapter

        key = self._in_flight_key(fingerprint, run_all)
        with self._in_flight_lock:
            if key in self._in_flight:
                return {
                    "executed": False,
                    "error": (
                        "an execution for this selector is already "
                        "in flight"
                    ),
                    "in_flight": True,
                    "selector": key,
                    "terminal": None,
                }
            self._in_flight[key] = {
                "key": key,
                "fingerprint": fingerprint,
                "run_all": bool(run_all),
                "session": session,
                "state": "IN_FLIGHT",
                "started_at": now_iso(),
            }
        try:
            return agent_adapter.execute(
                self.env,
                fingerprint=fingerprint,
                run_all=run_all,
                session=session,
            )
        finally:
            with self._in_flight_lock:
                self._in_flight.pop(key, None)

    def in_flight(self):
        """Read-only snapshot of RAM-only in-flight executions."""
        with self._in_flight_lock:
            return {
                "in_flight": [
                    dict(record)
                    for record in self._in_flight.values()
                ],
                "count": len(self._in_flight),
            }
