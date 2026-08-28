"""External action spike — governed ambiguous-result foundation (P10.3-R1).

This module defines the minimal external-action abstraction that can be
governed by the existing WorkerActionPipeline authority without
introducing a second execution path for file actions.

Design:
- ExternalAction is a frozen contract with deterministic SHA-256 fingerprint
  over provider/operation/payload/idempotency_key/reason.
- For governance reuse, ExternalAction can be projected to a synthetic
  PatchProposal that reuses PatchValidator, GovernanceEvaluator,
  ApprovalStore and Controller without modifying their logic. The synthetic
  patch path is ``external://{provider}/{operation}`` and action is
  ``external_call`` so PathPolicy scope checks remain meaningful:
  ``allowed_paths`` must contain the external provider scope (e.g.
  ``external://payments`` or a shared ``external://`` prefix) exactly as
  file scope is checked.
- Payload and idempotency_key are stored as hashes in the journal;
  raw provider responses are never recorded as secret-safe evidence.

No real network, no secrets, no provider SDK.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint_parts(
    provider: str,
    operation: str,
    payload: str,
    idempotency_key: str,
    reason: str,
) -> str:
    return "|".join(
        [
            provider if isinstance(provider, str) else "",
            operation if isinstance(operation, str) else "",
            payload if isinstance(payload, str) else "",
            idempotency_key if isinstance(idempotency_key, str) else "",
            reason if isinstance(reason, str) else "",
        ]
    )


@dataclass(frozen=True)
class ExternalAction:
    """Governable external action request.

    ``provider`` — logical provider name (e.g. ``payments``, ``email``)
    ``operation`` — operation id (e.g. ``charge``, ``send``)
    ``payload`` — JSON-serialised or opaque payload string (secret-safe)
    ``idempotency_key`` — client-supplied correlation key; empty means
      no durable idempotency is claimed (truthful spike: no assumption
      of provider-side deduplication unless provider explicitly supports it)
    ``reason`` — human-readable intent
    """

    provider: str
    operation: str
    payload: str
    idempotency_key: str = ""
    reason: str = ""

    def fingerprint(self) -> str:
        return _sha256_hex(
            _fingerprint_parts(
                self.provider,
                self.operation,
                self.payload,
                self.idempotency_key,
                self.reason,
            )
        )

    def synthetic_path(self) -> str:
        # Canonical external path for scope and governance.
        # Using ``external://`` scheme keeps PathPolicy handling explicit
        # without colliding with file paths.
        prov = self.provider or "unknown"
        op = self.operation or "unknown"
        return f"external://{prov}/{op}"

    def to_patch_proposal(self, allowed_paths=()):
        """Project to a synthetic PatchProposal for governance reuse.

        The synthetic patch reuses the existing file-governance chain:
        ``path`` = external path, ``action`` = ``modify``,
        ``old_content`` = idempotency binding (if key present),
        ``new_content`` = payload, ``allowed_paths`` = scope for
        PathPolicy checks.

        Binding: ``idempotency_key`` is encoded deterministically into
        ``old_content`` as ``__idempotency_key:{key}`` so it becomes part
        of ``PatchProposal.fingerprint()`` and therefore part of the
        approval-binding identity.  Different keys produce different
        synthetic fingerprints, while empty key preserves "" for
        backward-compatible fingerprint (no binding drift for existing
        file-like actions).  Provider/operation/payload/reason remain
        semantically unchanged; only the synthetic projection carries the
        binding.
        """
        from simulation.agent.worker.patch_proposal import PatchProposal

        idem = self.idempotency_key if isinstance(self.idempotency_key, str) else ""
        old_binding = f"__idempotency_key:{idem}" if idem else ""

        return PatchProposal(
            path=self.synthetic_path(),
            action="modify",
            old_content=old_binding,
            new_content=self.payload if isinstance(self.payload, str) else "",
            reason=self.reason if isinstance(self.reason, str) else "",
            allowed_paths=tuple(allowed_paths) if allowed_paths else (),
        )
