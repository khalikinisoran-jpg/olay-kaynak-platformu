"""Deterministic fake provider surface for the external-action spike (P10.3-R1).

No network, no secrets. All providers are in-memory and deterministic
so the suite remains hermetic.

Outcome semantics (mandatory distinction):

- KNOWN_SUCCESS   — provider explicitly confirms success
- KNOWN_FAILURE   — provider explicitly returns failure/rejection
- TIMEOUT_UNKNOWN — local timeout before outcome known (ambiguous)
- AMBIGUOUS_UNKNOWN — response lost / may have executed (ambiguous)

A provider that *supports* lookup would expose ``reconcile(idempotency_key)``
but the spike MUST prove the absence case: ``NoLookupProvider`` explicitly
lacks that capability and tests assert ambiguous remains unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Protocol

from simulation.agent.apply.external_action import ExternalAction


class ExternalOutcome(str, Enum):
    KNOWN_SUCCESS = "known_success"
    KNOWN_FAILURE = "known_failure"
    TIMEOUT_UNKNOWN = "timeout_unknown"
    AMBIGUOUS_UNKNOWN = "ambiguous_unknown"


@dataclass(frozen=True)
class ExternalResult:
    outcome: ExternalOutcome
    success: bool
    reason: str
    provider_response: Optional[dict] = None
    idempotency_key: str = ""
    fingerprint: str = ""

    @property
    def is_known(self) -> bool:
        return self.outcome in (
            ExternalOutcome.KNOWN_SUCCESS,
            ExternalOutcome.KNOWN_FAILURE,
        )

    @property
    def is_ambiguous(self) -> bool:
        return self.outcome in (
            ExternalOutcome.TIMEOUT_UNKNOWN,
            ExternalOutcome.AMBIGUOUS_UNKNOWN,
        )


class ExternalProvider(Protocol):
    def execute(self, action: ExternalAction) -> ExternalResult:  # pragma: no cover
        ...

    # Optional reconciliation — absence must be tested.
    # If provider does not support it, it simply does not implement ``reconcile``.


class ScriptedProvider:
    """Deterministic provider driven by a scripted queue or mapping.

    - ``script``: list of ExternalOutcome in call order (per-execute queue).
      If exhausted, repeats last outcome (fail-closed default).
    - ``mapping``: optional operation -> outcome mapping for KNOWN cases.
    - Tracks ``call_count`` and ``calls`` for negative bypass audits.
    """

    def __init__(
        self,
        script: Optional[List[ExternalOutcome]] = None,
        mapping: Optional[Dict[str, ExternalOutcome]] = None,
        name: str = "scripted",
    ):
        self.script: List[ExternalOutcome] = list(script) if script else []
        self.mapping: Dict[str, ExternalOutcome] = dict(mapping) if mapping else {}
        self.name = name
        self.call_count = 0
        self.calls: List[ExternalAction] = []
        self._cursor = 0

    def execute(self, action: ExternalAction) -> ExternalResult:
        self.call_count += 1
        self.calls.append(action)
        # mapping takes precedence for known operation routing
        if action.operation in self.mapping:
            outcome = self.mapping[action.operation]
        elif self._cursor < len(self.script):
            outcome = self.script[self._cursor]
            self._cursor += 1
        elif self.script:
            outcome = self.script[-1]
        else:
            outcome = ExternalOutcome.KNOWN_SUCCESS

        success = outcome == ExternalOutcome.KNOWN_SUCCESS
        # Known failure is explicit failure, not ambiguous
        if outcome == ExternalOutcome.KNOWN_FAILURE:
            success = False
        elif outcome in (ExternalOutcome.TIMEOUT_UNKNOWN, ExternalOutcome.AMBIGUOUS_UNKNOWN):
            success = False

        return ExternalResult(
            outcome=outcome,
            success=success,
            reason=f"provider:{self.name} outcome:{outcome.value} op:{action.operation}",
            provider_response={"provider": self.name, "operation": action.operation},
            idempotency_key=action.idempotency_key or "",
            fingerprint=action.fingerprint(),
        )


class AlwaysSuccessProvider(ScriptedProvider):
    def __init__(self):
        super().__init__(script=[ExternalOutcome.KNOWN_SUCCESS], name="always_success")


class AlwaysFailureProvider(ScriptedProvider):
    def __init__(self):
        super().__init__(script=[ExternalOutcome.KNOWN_FAILURE], name="always_failure")


class TimeoutProvider(ScriptedProvider):
    def __init__(self):
        super().__init__(script=[ExternalOutcome.TIMEOUT_UNKNOWN], name="timeout")


class AmbiguousProvider(ScriptedProvider):
    def __init__(self):
        super().__init__(script=[ExternalOutcome.AMBIGUOUS_UNKNOWN], name="ambiguous")


class NoLookupProvider(ScriptedProvider):
    """Provider that explicitly lacks reconciliation/status lookup.

    It does NOT implement ``reconcile``. Tests assert ambiguous remains
    ambiguous when this provider is used (no hidden getStatus assumption).
    """

    def __init__(self, script=None):
        super().__init__(
            script=script or [ExternalOutcome.TIMEOUT_UNKNOWN],
            name="no_lookup",
        )

    # Intentionally no ``reconcile`` — prove absence.


class ReconcilingFakeProvider(ScriptedProvider):
    """Fake provider that DOES support lookup — scoped to this provider only.

    This is used to prove the spike does NOT generalize fake deduplication
    to all providers. Its ``reconcile`` is a deterministic map.
    """

    def __init__(self, reconcile_map: Optional[Dict[str, ExternalOutcome]] = None):
        super().__init__(script=[ExternalOutcome.AMBIGUOUS_UNKNOWN], name="reconciling_fake")
        self.reconcile_map = dict(reconcile_map) if reconcile_map else {}
        self.reconcile_calls: List[str] = []

    def reconcile(self, idempotency_key: str) -> Optional[ExternalOutcome]:
        self.reconcile_calls.append(idempotency_key)
        return self.reconcile_map.get(idempotency_key)
