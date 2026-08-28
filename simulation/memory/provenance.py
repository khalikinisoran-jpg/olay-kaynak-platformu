"""Memory provenance envelope (MISSION-N).

``State.memory`` is a plain ``Dict[str, str]``. This module adds a
*parallel* provenance envelope per key so that, if memory is ever used
as decision context, the origin and trust status of every entry is
explicit and unforgeable-by-omission.

Authority separation (never violated here):

    PROVENANCE != AUTHORIZATION

The trust levels below are METADATA. No governance, approval, scope,
risk or apply decision reads ``MemoryProvenance``; a ``VERIFIED`` or
``HUMAN_APPROVED`` memory entry does NOT authorize an action, an apply
or a replay. Provenance records where an entry came from; it never
decides what may be done with it.

Trust levels (metadata only):

- UNTRUSTED      user/attacker-influenced input; never a fact.
- OBSERVED       recorded observation (e.g. inspection output); not
                 verified.
- VERIFIED       independently verified at record time (e.g. a
                 deterministic check). Does NOT imply approval.
- SYSTEM         produced by the runtime itself.
- HUMAN_APPROVED an entry a human explicitly acknowledged. Does NOT
                 grant apply/approval authority.

Verification status:

- UNVERIFIED     nothing has verified the claim.
- VERIFIED       a verification step confirmed it (at record time).
- CONFLICTED     a later observation contradicted it.
- STALE          recorded under a run/event context that is no longer
                 current.
"""

from dataclasses import dataclass, asdict, fields


class TrustLevel:

    UNTRUSTED = "UNTRUSTED"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    SYSTEM = "SYSTEM"
    HUMAN_APPROVED = "HUMAN_APPROVED"

    ALL = frozenset({
        UNTRUSTED,
        OBSERVED,
        VERIFIED,
        SYSTEM,
        HUMAN_APPROVED,
    })


class VerificationStatus:

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONFLICTED = "CONFLICTED"
    STALE = "STALE"

    ALL = frozenset({
        UNVERIFIED,
        VERIFIED,
        CONFLICTED,
        STALE,
    })


def _clamp(value, allowed, default):
    if value in allowed:
        return value
    return default


@dataclass(frozen=True)
class MemoryProvenance:

    """Immutable origin metadata for one memory entry.

    Defaults are deterministic (no clock, no run context) so replaying
    an event that carries no provenance always produces the same
    envelope. Field names are stable for snapshot serialization.
    """

    source: str = "unknown"
    source_type: str = "unclassified"
    timestamp: str = ""
    event_id: str = ""
    trust_level: str = TrustLevel.UNTRUSTED
    verification_status: str = VerificationStatus.UNVERIFIED
    run_id: str = ""
    agent_id: str = ""

    @classmethod
    def from_payload(
        cls,
        payload,
        event_id=""
    ):

        """Build a provenance envelope from a MemoryStored payload.

        Missing or malformed fields fall back to deterministic
        defaults. ``trust_level`` and ``verification_status`` are
        clamped to the allowed sets, so an event claiming
        ``trust_level="APPROVED"`` cannot smuggle an undefined label
        through the envelope.
        """

        if not isinstance(payload, dict):
            payload = {}

        source = payload.get("source")
        source_type = payload.get("source_type")
        timestamp = payload.get("timestamp")
        trust = payload.get("trust_level")
        status = payload.get("verification_status")
        run_id = payload.get("run_id")
        agent_id = payload.get("agent_id")

        return cls(
            source=source if isinstance(source, str) else "unknown",
            source_type=(
                source_type
                if isinstance(source_type, str)
                else "unclassified"
            ),
            timestamp=(
                timestamp
                if isinstance(timestamp, str)
                else ""
            ),
            event_id=(
                event_id
                if isinstance(event_id, str)
                else ""
            ),
            trust_level=_clamp(
                trust,
                TrustLevel.ALL,
                TrustLevel.UNTRUSTED,
            ),
            verification_status=_clamp(
                status,
                VerificationStatus.ALL,
                VerificationStatus.UNVERIFIED,
            ),
            run_id=run_id if isinstance(run_id, str) else "",
            agent_id=(
                agent_id
                if isinstance(agent_id, str)
                else ""
            ),
        )

    @classmethod
    def from_dict(cls, data):

        if not isinstance(data, dict):

            return cls()

        known = {field.name for field in fields(cls)}

        filtered = {
            key: data[key]
            for key in known
            if key in data
        }

        if "trust_level" in filtered:
            filtered["trust_level"] = _clamp(
                filtered["trust_level"],
                TrustLevel.ALL,
                TrustLevel.UNTRUSTED,
            )

        if "verification_status" in filtered:
            filtered["verification_status"] = _clamp(
                filtered["verification_status"],
                VerificationStatus.ALL,
                VerificationStatus.UNVERIFIED,
            )

        return cls(**filtered)

    def to_dict(self):

        return asdict(self)
