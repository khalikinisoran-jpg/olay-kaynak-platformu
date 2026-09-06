"""Tanuq OperationCoordinator — single orchestration facade over the
existing TANUQ projections.

BOUNDARY CONTRACT: the coordinator is NOT a governance authority and
computes nothing on its own. Every method delegates to the existing,
tested projection layer:

    operations      -> tanuq.evidence.operations
    lineage         -> tanuq.evidence.lineage
    get_operation   -> tanuq.evidence.operations (selector)
    incidents       -> tanuq.incidents.collect_incidents
    export          -> tanuq.evidence.export_evidence
    status          -> chain_status + pending count + config summary

The facade is stateless: no persistent store, no cache, no in-memory
registry, no governance decision, no approval action. CLI and Web call
the SAME methods so both surfaces can never drift on what happened.
"""
from tanuq.config import tanuq_data_dir
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
