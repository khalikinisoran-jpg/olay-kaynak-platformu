import re

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from simulation.security.risk_level import RiskLevel


_ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)

_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def now_iso() -> str:

    """Current UTC time as an ISO-8601 string (``YYYY-MM-DDTHH:MM:SSZ``)."""

    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_in_future(seconds: int) -> str:

    """UTC time ``seconds`` in the future as an ISO-8601 string."""

    from datetime import timedelta

    return (
        datetime.now(timezone.utc)
        + timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_in_past(seconds: int) -> str:

    """UTC time ``seconds`` in the past as an ISO-8601 string."""

    from datetime import timedelta

    return (
        datetime.now(timezone.utc)
        - timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Approval:

    """Immutable human-approval authorization contract.

    An approval authorizes exactly ONE patch within ONE risk/attempt
    context. It is bound to every piece of identity the boundary
    enforces:

    - ``patch_fingerprint``   deterministic SHA-256 of the patch
    - ``path``                exact patch target path
    - ``action``              exact patch action
    - ``risk_level``          risk context the approval was granted for
    - ``attempt``             1-based attempt context
    - ``authorizer``          authorization identity (human)
    - ``created_at``          grant time (ISO-8601 UTC)
    - ``expires_at``          expiry time, or ``""`` for no expiry

    The frozen contract fails closed on malformed values: any missing,
    empty, non-string or structurally invalid binding field raises at
    construction, so a forged approval with a well-typed shape cannot
    carry garbage identity fields either.
    """

    approval_id: str
    patch_fingerprint: str
    path: str
    action: str
    risk_level: str
    attempt: int
    authorizer: str
    created_at: str
    expires_at: str = ""

    def __post_init__(self):

        if not isinstance(self.approval_id, str) or not self.approval_id:

            raise ValueError("Approval id is missing.")

        if not isinstance(
            self.patch_fingerprint,
            str,
        ) or not _FINGERPRINT_RE.match(
            self.patch_fingerprint
        ):

            raise ValueError(
                "Approval patch_fingerprint must be a "
                "64-char lowercase SHA-256 hex digest."
            )

        if not isinstance(self.path, str) or not self.path:

            raise ValueError("Approval path is missing.")

        if not isinstance(self.action, str) or not self.action:

            raise ValueError("Approval action is missing.")

        try:

            level = RiskLevel.parse(self.risk_level)

        except ValueError:

            raise ValueError(
                f"Approval risk_level is malformed: "
                f"{self.risk_level!r}"
            )

        if level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):

            raise ValueError(
                "Approval risk_level must be HIGH or "
                "CRITICAL (the only levels that require "
                "human approval)."
            )

        if (
            not isinstance(self.attempt, int)
            or isinstance(self.attempt, bool)
            or self.attempt < 1
        ):

            raise ValueError(
                "Approval attempt must be a positive integer."
            )

        if not isinstance(self.authorizer, str) or not self.authorizer:

            raise ValueError("Approval authorizer is missing.")

        if not isinstance(self.created_at, str) or not _ISO_UTC_RE.match(
            self.created_at
        ):

            raise ValueError(
                f"Approval created_at is malformed: "
                f"{self.created_at!r}"
            )

        if not isinstance(self.expires_at, str):

            raise ValueError(
                f"Approval expires_at is malformed: "
                f"{self.expires_at!r}"
            )

        if self.expires_at and not _ISO_UTC_RE.match(
            self.expires_at
        ):

            raise ValueError(
                f"Approval expires_at is malformed: "
                f"{self.expires_at!r}"
            )

    @classmethod
    def create(
        cls,
        patch_fingerprint,
        path,
        action,
        risk_level,
        attempt=1,
        authorizer="human",
        expires_at=None,
    ):

        """Build a new approval with fresh id and grant timestamp.

        ``expires_at`` may be a fixed ISO-8601 UTC string or an int
        (TTL in seconds); ``None`` means the approval never expires.
        """

        if isinstance(expires_at, int) and not isinstance(
            expires_at,
            bool,
        ):

            expires_at = iso_in_future(expires_at)

        return cls(
            approval_id=str(uuid4()),
            patch_fingerprint=patch_fingerprint,
            path=path,
            action=action,
            risk_level=risk_level,
            attempt=attempt,
            authorizer=authorizer,
            created_at=now_iso(),
            expires_at=(
                expires_at
                if expires_at is not None
                else ""
            ),
        )

    def is_expired(self, now=None) -> bool:

        """Fail-closed expiry check.

        An empty ``expires_at`` means the approval never expires.
        Any non-empty expiry in the past makes the approval
        unusable. Malformed timestamps cannot reach this point
        because construction rejects them.
        """

        if not self.expires_at:

            return False

        current = now if now is not None else now_iso()

        return self.expires_at < current
