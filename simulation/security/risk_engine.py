import re

from dataclasses import dataclass, field
from pathlib import Path

from simulation.security.risk_level import RiskLevel


SECURITY_SENSITIVE_FRAGMENTS = (
    ".env",
    "secret",
    "credential",
    "password",
    "passwd",
    "auth",
    "token",
    "id_rsa",
    ".ssh",
    "kubeconfig",
    ".netrc",
    ".pypirc",
    ".npmrc",
)

PRIVILEGE_BOUNDARY_FRAGMENTS = (
    "/etc/",
    "/usr/",
    "/opt/",
    "/var/",
    "/home/",
    "/root/",
    "system32",
    "\\windows\\system32",
)

PRODUCTION_CONFIG_FRAGMENTS = (
    "production",
    "prod.conf",
    "deploy",
    "release",
    "terraform",
    "main.tf",
    "k8s",
    "docker-compose",
    "compose.yml",
    "helm",
)

SECRET_FILE_SUFFIXES = (
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".htpasswd",
    ".pwd",
)

EXECUTABLE_SOURCE_SUFFIXES = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".sh",
    ".bash",
    ".ps1",
    ".cmd",
    ".bat",
    ".c",
    ".cpp",
    ".h",
    ".php",
    ".pl",
)

DESTRUCTIVE_ACTIONS = frozenset({
    "delete",
    "drop",
    "truncate",
    "format",
    "remove",
    "purge",
    "reset",
    "replace",
})

LARGE_CHANGE_CHARS = 500

SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|"
    r"credential|authorization)\s*[:=]\s*\S+"
)

PEM_PATTERN = re.compile(r"-----BEGIN")


@dataclass(frozen=True)
class RiskAssessment:

    """Deterministic risk classification for a single proposal.

    ``risk_level`` is derived from system signals (path, action, change
    size, content, location). ``advisory_risk``/``advisory_confidence``
    may carry an LLM estimate, but that estimate can only raise the
    level, never lower it, and is never the authority.
    """

    risk_level: RiskLevel
    signals: tuple[tuple[str, str], ...] = field(
        default_factory=tuple
    )
    advisory_risk: RiskLevel | None = None
    advisory_confidence: float | None = None
    reason: str = ""


class RiskEngine:

    """System-derived risk classifier (fail-closed).

    The engine never trusts an LLM label. ``classify`` returns an
    assessment whose level is derived from observable proposal
    properties; an advisory LLM risk, when present, is folded in only as
    an upper bound (most restrictive wins). Malformed input produces
    ``RiskLevel.UNKNOWN``, which the policy layer treats as DENY.
    """

    def classify(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ) -> RiskAssessment:

        if patch is None:

            return RiskAssessment(
                risk_level=RiskLevel.UNKNOWN,
                reason="Missing patch for risk assessment.",
            )

        signals = []

        level = RiskLevel.LOW

        action = getattr(patch, "action", None)

        if not isinstance(action, str) or not action:

            signals.append(("action", "missing"))

            level = RiskLevel.UNKNOWN

        elif action != "modify":

            signals.append(("action", action))

            level = RiskLevel.max_level(
                level,
                (
                    RiskLevel.CRITICAL
                    if action in DESTRUCTIVE_ACTIONS
                    else RiskLevel.HIGH
                ),
            )

        raw_path = getattr(patch, "path", "")

        path_text = (
            str(raw_path)
            if raw_path is not None
            else ""
        ).lower()

        if path_text:

            if any(
                fragment in path_text
                for fragment in SECURITY_SENSITIVE_FRAGMENTS
            ):

                signals.append(
                    ("security_sensitive_path", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            if any(
                fragment in path_text
                for fragment in PRIVILEGE_BOUNDARY_FRAGMENTS
            ):

                signals.append(
                    ("privilege_boundary", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.CRITICAL,
                )

            if any(
                fragment in path_text
                for fragment in PRODUCTION_CONFIG_FRAGMENTS
            ):

                signals.append(
                    ("production_configuration", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            suffix = Path(path_text).suffix

            if (
                suffix in SECRET_FILE_SUFFIXES
                or Path(path_text).name in SECRET_FILE_SUFFIXES
            ):

                signals.append(
                    ("secret_file", suffix)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.CRITICAL,
                )

            elif suffix in EXECUTABLE_SOURCE_SUFFIXES:

                signals.append(
                    ("executable_source", suffix)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.MEDIUM,
                )

        old_content = getattr(patch, "old_content", "")

        new_content = getattr(patch, "new_content", "")

        if isinstance(old_content, str) and isinstance(
            new_content,
            str,
        ):

            change_size = abs(
                len(new_content) - len(old_content)
            )

            if change_size > LARGE_CHANGE_CHARS:

                signals.append(
                    ("large_change", str(change_size))
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            if PEM_PATTERN.search(new_content):

                signals.append(
                    ("secret_material", "pem_block")
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.CRITICAL,
                )

            elif SECRET_ASSIGNMENT_PATTERN.search(
                new_content
            ):

                signals.append(
                    ("secret_like_content", "assignment")
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

        advisory = None

        if advisory_risk is not None:

            try:

                advisory = RiskLevel.parse(
                    advisory_risk
                )

            except ValueError:

                advisory = None

            if (
                advisory is not None
                and advisory != RiskLevel.UNKNOWN
            ):

                signals.append(
                    ("advisory_llm_risk", advisory.value)
                )

                level = RiskLevel.max_level(
                    level,
                    advisory,
                )

        return RiskAssessment(
            risk_level=level,
            signals=tuple(signals),
            advisory_risk=advisory,
            advisory_confidence=(
                advisory_confidence
                if isinstance(
                    advisory_confidence,
                    (int, float),
                )
                else None
            ),
            reason=self._reason(level, signals),
        )

    @staticmethod
    def _reason(level, signals):

        if not signals:

            return (
                f"System-derived risk is {level.value} "
                "(no elevated signals)."
            )

        labels = ", ".join(
            f"{name}={value}"
            for name, value in signals
        )

        return (
            f"System-derived risk is {level.value} "
            f"from signals: {labels}."
        )
