from enum import Enum


_SEVERITY = {
    "UNKNOWN": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


class RiskLevel(Enum):

    """Deterministic, ordered risk classification.

    Ordering (most restrictive wins):

        UNKNOWN < LOW < MEDIUM < HIGH < CRITICAL

    ``UNKNOWN`` is the fail-closed classification for anything the
    engine cannot derive; it is never auto-approvable.
    """

    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def parse(cls, raw):

        if isinstance(raw, cls):

            return raw

        if raw is None:

            raise ValueError("Risk level is missing.")

        if not isinstance(raw, str):

            raise ValueError(
                "Risk level must be a string label."
            )

        normalized = raw.strip().upper()

        if normalized not in cls._value2member_map_:

            raise ValueError(
                f"Unknown risk level: {raw!r}"
            )

        return cls(normalized)

    @property
    def severity(self) -> int:

        return _SEVERITY[self.value]

    def at_least(self, other) -> bool:

        if not isinstance(other, RiskLevel):

            other = RiskLevel.UNKNOWN

        return self.severity >= other.severity

    @staticmethod
    def max_level(*levels):

        """Most restrictive risk level; malformed inputs never dominate."""

        highest = RiskLevel.UNKNOWN

        for level in levels:

            if not isinstance(level, RiskLevel):

                continue

            if level.severity > highest.severity:

                highest = level

        return highest
