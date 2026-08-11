from dataclasses import dataclass, field
from typing import Any


ADVISORY_RISK_LEVELS = frozenset({
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
    "UNKNOWN",
})


@dataclass(frozen=True)
class AnalysisResult:

    """Structured, fail-closed analysis contract produced by an analyzer.

    Core contract (enforced at construction):

    - ``diagnosis`` must be a non-empty string.
    - ``old_text`` must be a non-empty string and occur exactly once in
      the analyzed content (checked by the Worker).
    - ``new_text`` must be a non-empty string and differ from ``old_text``
      (an empty proposal is rejected).

    Advisory-only fields:

    - ``confidence`` is a signal, never a security decision. It must be
      ``None`` or a finite number within ``[0, 1]``.
    - ``risk`` is a label the model may attach. It is advisory only; the
      deterministic RiskEngine is the risk authority. It must be ``None``
      or one of the known advisory labels (case-insensitive).
    - ``evidence``, ``explanation`` and ``metadata`` carry optional
      context for auditability. They never influence security decisions.

    Any malformed value fails closed: constructing a result raises, and
    the Worker records the inspection as failed instead of proposing.
    """

    diagnosis: str
    old_text: str
    new_text: str
    evidence: tuple[str, ...] = ()
    confidence: float | None = None
    risk: str | None = None
    explanation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):

        if (
            not isinstance(self.diagnosis, str)
            or not self.diagnosis.strip()
        ):

            raise ValueError(
                "AnalysisResult diagnosis must be a "
                "non-empty string."
            )

        if (
            not isinstance(self.old_text, str)
            or not self.old_text
        ):

            raise ValueError(
                "AnalysisResult old_text must be a "
                "non-empty string."
            )

        if (
            not isinstance(self.new_text, str)
            or not self.new_text
        ):

            raise ValueError(
                "AnalysisResult new_text must be a "
                "non-empty string."
            )

        if self.old_text == self.new_text:

            raise ValueError(
                "AnalysisResult must propose a change; "
                "old_text equals new_text."
            )

        if self.confidence is not None:

            if (
                isinstance(self.confidence, bool)
                or not isinstance(
                    self.confidence,
                    (int, float),
                )
            ):

                raise ValueError(
                    "AnalysisResult confidence must be "
                    "a number or None."
                )

            value = float(self.confidence)

            if not (0.0 <= value <= 1.0):

                raise ValueError(
                    "AnalysisResult confidence must lie "
                    "within [0, 1]."
                )

            object.__setattr__(
                self,
                "confidence",
                value,
            )

        if self.risk is not None:

            if not isinstance(self.risk, str):

                raise ValueError(
                    "AnalysisResult risk must be a "
                    "string label or None."
                )

            normalized = self.risk.strip().upper()

            if normalized not in ADVISORY_RISK_LEVELS:

                raise ValueError(
                    "AnalysisResult risk must be one of "
                    + ", ".join(
                        sorted(ADVISORY_RISK_LEVELS)
                    )
                    + "."
                )

            object.__setattr__(
                self,
                "risk",
                normalized,
            )

        if not isinstance(self.evidence, tuple):

            raise ValueError(
                "AnalysisResult evidence must be a tuple."
            )

        for entry in self.evidence:

            if not isinstance(entry, str):

                raise ValueError(
                    "AnalysisResult evidence entries "
                    "must be strings."
                )

        if not isinstance(self.explanation, str):

            raise ValueError(
                "AnalysisResult explanation must be a "
                "string."
            )

        if not isinstance(self.metadata, dict):

            raise ValueError(
                "AnalysisResult metadata must be a dict."
            )
