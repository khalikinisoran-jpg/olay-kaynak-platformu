"""Deterministic system-derived risk classification (fail-closed).

Security principle (MISSION-018A): ``not detected`` is never treated as
``safe``. Content is classified into three states:

- SAFE        -> plain, simple content with no credential-like, encoded or
                 opaque material. Only SAFE content can keep the LOW/MEDIUM
                 baseline that the policy may auto-apply.
- SUSPICIOUS  -> structural credential material (JSON/YAML/TOML/dotenv
                 credential keys, bare token prefixes, base64/encoded
                 material, URLs with userinfo, shell credential flags,
                 environment secret references, authorization headers).
                 Elevates to HIGH so a human approval is required.
- OPAQUE      -> content that cannot be analyzed as plain text (control
                 characters). Yields UNKNOWN so the policy DENYs it.

RiskEngine only classifies; execution policy lives in RiskPolicy and
human authorization stays in the ApprovalStore/ApplyAuthorization boundary.
"""

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

_EXECUTABLE_SOURCE_SUFFIXES = (
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

_TOKEN_SPLIT = re.compile(r"[^a-z0-9_]+")

_TOKEN_BOUNDARY_FRAGMENTS = frozenset({
    "auth",
    "token",
    "secret",
})

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
    r"credential|authorization)\s*[:=]\s*(?P<value>\S+)"
)

PEM_PATTERN = re.compile(r"-----BEGIN")

# ---------------------------------------------------------------------------
# MISSION-018A fail-closed hardening: "not detected" is never treated as
# "safe". The engine distinguishes three content states:
#   SAFE       -> plain, simple content with no credential-like / encoded /
#                 opaque material (LOW/MEDIUM baseline may auto-apply).
#   SUSPICIOUS -> structural credential material (HIGH; human approval).
#   OPAQUE     -> content that cannot be analyzed as plain text, e.g.
#                 control characters (UNKNOWN; policy DENY, no apply).
# The patterns below are structural heuristics that lift the evasion
# classes identified by the MISSION-018 audit out of LOW/MEDIUM. They are
# deterministic and compiled once; no network or secret-scanning service.
# ---------------------------------------------------------------------------

_BACKUP_OR_TEMP_SUFFIXES = (
    ".bak",
    ".backup",
    ".old",
    ".orig",
    ".original",
    ".tmp",
    ".temp",
    ".swp",
    ".swo",
    ".save",
    ".saved",
    ".part",
    ".new",
)

_HIDDEN_CREDENTIAL_FILE_NAMES = frozenset({
    ".creds",
    ".credentials",
    ".pgpass",
    ".aws",
    ".azure",
    ".gcloud",
    ".dockercfg",
    ".git-credentials",
    ".kubeconfig",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".ssh",
    ".env",
})

_CREDENTIAL_DIRECTORY_TOKENS = frozenset({
    "secret",
    "secrets",
    "credential",
    "credentials",
    "token",
    "tokens",
    "keys",
    "keyring",
    "certs",
    "certificates",
    "private",
    "auth",
    "ssh",
    "pki",
    "vault",
})

_PRODUCT_ENVIRONMENT_TOKENS = frozenset({
    "prod",
    "production",
    "staging",
    "uat",
    "preprod",
    "pre-prod",
})

_CREDENTIAL_KEY_PREFIXES = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "access_key",
    "access-key",
    "accesskey",
    "secret_key",
    "secret-key",
    "secretkey",
    "client_secret",
    "client-secret",
    "refresh_token",
    "refresh-token",
    "auth_token",
    "auth-token",
    "credential",
    "credentials",
    "creds",
    "private_key",
    "private-key",
    "privatekey",
    "consumer_key",
    "consumer-key",
    "auth",
)

# Credential assignments in any structural format (dotenv / assignment,
# JSON, YAML, TOML, INI, connection strings). The key may be quoted and may
# carry a part-numbered suffix (token_part1, token_2), and a dict-subscript
# separator ("]") is tolerated so `config["token"] = ...` is caught. The
# suffix MUST start with `_`, `-` or a digit, so `tokenizer` / `tokenize`
# are not misclassified. The value is captured and checked for triviality
# in Python so `self.token = None` stays benign.
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?im)(?:^|[\s.\[{(,;])([\"']?)(?:"
    + "|".join(
        re.escape(prefix)
        for prefix in _CREDENTIAL_KEY_PREFIXES
    )
    + r")(?:[_\-\d][A-Za-z0-9_\-]*)?(\1)\s*\]?\s*[:=]\s*"
    r"(?P<value>[^\r\n]*)"
)

# Bare credential tokens: sk-.../pk-... style, GitHub ghp_/gho_/ghs_,
# Slack xox*, AWS AKIA, OAuth ya29., JWTs (eyJ...), Google AIza, SendGrid
# SG., and other high-entropy prefixed secrets.
_TOKEN_LIKE_RE = re.compile(
    r"(?i)(?:sk|pk|ghp|gho|ghs|xox[baprs]|hf|whk)[-_][\w-]{12,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|ya29\.[\w-]{20,}"
    r"|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"
    r"|AIza[\w-]{20,}"
    r"|SG\.[\w-]{20,}"
)

# Encoded/opaque material: a delimited run of base64-alphabet characters.
# _looks_encoded then requires either base64 padding (short padded blobs)
# or a long mixed-property run (>= 32 chars with digit + upper + lower),
# so plain camelCase identifiers without digits stay benign.
_BASE64_MATERIAL_RE = re.compile(
    r"(?:^|[^A-Za-z0-9+/])"
    r"([A-Za-z0-9+/]{16,}={0,2})"
    r"(?:$|[^A-Za-z0-9+/])"
)

# URLs embedding credentials (user:pass@).
_CREDENTIAL_URL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s@:]+:[^@/\s]+@"
)

# Shell commands carrying credential flags (curl -u, --password, ...).
_SHELL_CREDENTIAL_RE = re.compile(
    r"(?i)(?:^|[;\s|&])(?:-u|-U|--user|--username|--password|--pass|"
    r"--token|--api-key|--api_key|--secret|--access-key)\b"
)

# Authorization header constructions and Bearer/Basic tokens. The optional
# quote tolerates dict literals like {"Authorization": "Bearer ..."}.
_AUTH_HEADER_RE = re.compile(
    r"(?i)(?:authorization|proxy-authorization|x-api-key|x-auth-token)"
    r"\s*[\"']?\s*[:=]"
)

_BEARER_RE = re.compile(
    r"(?i)\b(?:bearer|basic)\s+[a-z0-9_\-\./+=]{8,}"
)

# Environment secret references (os.environ["API_KEY"], process.env.TOKEN,
# os.environ.get("SECRET"), getenv("PASSWORD"), ${SECRET_KEY}, ...). The
# accessed variable name must itself contain a credential keyword, so
# os.environ["HOME"] stays benign.
_ENV_SECRET_REFERENCE_RE = re.compile(
    r"(?i)(?:os\s*(?:\.\s*environ|\[\s*[\"']environ[\"']\s*\])|process\s*\.\s*env|environ|getenv|env)"
    r"(?:\s*\.\s*get|\.|\s*\(|\s*\[)"
    r"\s*\(?\s*[fFrRbBuU]*[\"']?(?:[^\"'\]\)]*(?:password|passwd|secret|token|api[_-]?key|"
    r"access[_-]?key|credential|auth[_-]?key|client[_-]?secret)"
    r"[^\"'\]\)]*)"
)

_SHELL_ENV_REFERENCE_RE = re.compile(
    r"(?i)\$\{?\s*[\w]*?(?:secret|token|password|passwd|api[_-]?key|"
    r"access[_-]?key|credential|auth[_-]?key|client[_-]?secret|"
    r"db_password)[\w]*\s*\}?"
)

# Generic alias-aware secret get (covers e.get("SECRET"), getattr(...).get, etc.)
# Catches any .get("...SECRET...") even without os.environ prefix, to close alias dataflow gap.
_GENERIC_GET_SECRET_RE = re.compile(
    r"(?i)\.get\s*\(\s*[fFrRbBuU]*[\"'][^\"']*(?:secret|token|password|passwd|api[_-]?key|access[_-]?key|credential|auth[_-]?key|client[_-]?secret)[^\"']*[\"']"
)

_TRIVIAL_LITERALS = frozenset({
    "null",
    "none",
    "nil",
    "true",
    "false",
    "undefined",
    "0",
    "1",
    "[]",
    "{}",
    "()",
    "''",
    '""',
})


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

            if self._has_sensitive_fragment(path_text):

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

            elif suffix in _EXECUTABLE_SOURCE_SUFFIXES:

                signals.append(
                    ("executable_source", suffix)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.MEDIUM,
                )

            name = Path(path_text).name

            if RiskEngine._is_backup_or_temp_path(
                name,
                suffix,
            ):

                signals.append(
                    ("backup_or_temp_path", name)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            if name in _HIDDEN_CREDENTIAL_FILE_NAMES:

                signals.append(
                    ("hidden_credential_file", name)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            if RiskEngine._has_credential_directory(
                path_text
            ):

                signals.append(
                    ("credential_directory", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            if RiskEngine._has_product_environment(
                path_text
            ):

                signals.append(
                    ("prod_environment", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

            # RT-1 (G1): an EXISTING verification test module is part
            # of the verification mechanism. Modifying it without
            # human authorization lets the writer weaken its own
            # future verifiers (self-verifier exploit), so the
            # modification is elevated to HIGH (human approval
            # required by policy). Existence is checked at
            # classification time; creation of new files is handled
            # by the normal validation/apply gates.
            if (
                RiskEngine._is_test_module_name(
                    Path(path_text).name
                )
                and Path(raw_path).exists()
            ):

                signals.append(
                    ("modifies_existing_test_module", path_text)
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
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

        content_signals, content_level = (
            RiskEngine._content_signals(new_content)
        )

        if content_level is RiskLevel.UNKNOWN:

            level = RiskLevel.UNKNOWN

        elif content_level is not RiskLevel.LOW:

            level = RiskLevel.max_level(
                level,
                content_level,
            )

        signals.extend(content_signals)

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
    def _has_sensitive_fragment(path_text):

        """Sensitive-path detection with targeted boundary matching.

        The short, ambiguous fragments (``auth``, ``token``,
        ``secret``) only raise risk when they appear as delimited path
        tokens, so ordinary words that merely contain them
        (``authentication.py``, ``tokenizer.py``, ``secretary.py``)
        are not over-classified. Longer fragments (``credential``,
        ``password``, ``.env``, ...) keep substring matching so
        ``credentials.py`` and ``config.env`` stay sensitive.
        """

        for fragment in SECURITY_SENSITIVE_FRAGMENTS:

            if fragment in _TOKEN_BOUNDARY_FRAGMENTS:

                if RiskEngine._boundary_search(
                    path_text,
                    fragment,
                ):

                    return True

            elif fragment in path_text:

                return True

        return False

    @staticmethod
    def _is_test_module_name(name):

        """RT-1 (G1): verification test-module naming convention.

        Mirrors the verification target selection convention
        (``test_*.py`` / ``*_test.py``) plus ``conftest.py``.
        """

        return name == "conftest.py" or (
            name.endswith(".py")
            and (
                name.startswith("test_")
                or name.endswith("_test.py")
            )
        )

        """Sensitive-path detection with targeted boundary matching.

        The short, ambiguous fragments (``auth``, ``token``,
        ``secret``) only raise risk when they appear as delimited path
        tokens, so ordinary words that merely contain them
        (``authentication.py``, ``tokenizer.py``, ``secretary.py``)
        are not over-classified. Longer fragments (``credential``,
        ``password``, ``.env``, ...) keep substring matching so
        ``credentials.py`` and ``config.env`` stay sensitive.
        """

        for fragment in SECURITY_SENSITIVE_FRAGMENTS:

            if fragment in _TOKEN_BOUNDARY_FRAGMENTS:

                if RiskEngine._boundary_search(
                    path_text,
                    fragment,
                ):

                    return True

            elif fragment in path_text:

                return True

        return False

    @staticmethod
    def _boundary_search(path_text, fragment):

        pattern = re.compile(
            r"(?:^|[^a-z0-9])"
            + re.escape(fragment)
            + r"(?:$|[^a-z0-9])"
        )

        return pattern.search(path_text) is not None

    @staticmethod
    def _is_backup_or_temp_path(name, suffix):

        if suffix in _BACKUP_OR_TEMP_SUFFIXES:

            return True

        if name.endswith("~"):

            return True

        if name.startswith(".#") or name.endswith(".#"):

            return True

        if ".swp" in name or ".swo" in name:

            return True

        return False

    @staticmethod
    def _has_credential_directory(path_text):

        for token in _CREDENTIAL_DIRECTORY_TOKENS:

            if RiskEngine._boundary_search(path_text, token):

                return True

        return False

    @staticmethod
    def _has_product_environment(path_text):

        for token in _PRODUCT_ENVIRONMENT_TOKENS:

            if RiskEngine._boundary_search(path_text, token):

                return True

        return False

    @staticmethod
    def _credential_value_looks_real(value):

        """Distinguish a real credential value from trivial literals.

        ``self.token = None`` or ``{"token": ""}`` are benign; a quoted or
        unquoted non-trivial value is treated as credential-like.
        """

        v = value.strip()

        if not v:

            return False

        if v.startswith("#"):

            return False

        if v.lower() in _TRIVIAL_LITERALS:

            return False

        if (
            v.startswith('"')
            and v.endswith('"')
            and len(v) <= 2
        ) or (
            v.startswith("'")
            and v.endswith("'")
            and len(v) <= 2
        ):

            return False

        return True

    @staticmethod
    def _looks_encoded(blob):

        """A base64-looking run is treated as encoded material when it is
        padded (short padded blob with a letter and a digit) or is a long
        mixed-property run (>= 32 chars with digit + upper + lower), which
        plain camelCase identifiers without digits do not."""

        padded = "=" in blob

        has_digit = any(ch.isdigit() for ch in blob)

        if padded:

            has_letter = any(ch.isalpha() for ch in blob)

            return has_digit and has_letter

        if len(blob) >= 32:

            has_upper = any(ch.isupper() for ch in blob)

            has_lower = any(ch.islower() for ch in blob)

            return has_digit and has_upper and has_lower

        return False

    @staticmethod
    def _contains_control_chars(text):

        """True when the content is not analyzable as plain text (control
        characters other than tab/newline/CR). Such content is OPAQUE and
        must fail closed (UNKNOWN -> policy DENY)."""

        for ch in text:

            o = ord(ch)

            if o in (9, 10, 13):

                continue

            if o < 32 or o == 127:

                return True

        return False

    @staticmethod
    def _content_signals(new_content):

        """Structural content heuristics (MISSION-018A).

        Returns ``(signals, level)`` where the level reflects the most
        restrictive content-derived finding:

        - SAFE plain content keeps the LOW baseline (no elevation).
        - SUSPICIOUS credential-like material elevates to HIGH (human
          approval; never auto-apply).
        - OPAQUE content (control characters) yields UNKNOWN so the policy
          DENYs it; ``not detected`` is never treated as ``safe``.

        Deterministic, no external calls, no secret-scanning service.
        """

        signals = []

        level = RiskLevel.LOW

        if not isinstance(new_content, str):

            return signals, level

        if RiskEngine._contains_control_chars(new_content):

            signals.append(
                ("opaque_content", "control_chars")
            )

            return signals, RiskLevel.UNKNOWN

        if PEM_PATTERN.search(new_content):

            signals.append(
                ("secret_material", "pem_block")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.CRITICAL,
            )

        for match in SECRET_ASSIGNMENT_PATTERN.finditer(
            new_content
        ):

            if RiskEngine._credential_value_looks_real(
                match.group("value")
            ):

                signals.append(
                    ("secret_like_content", "assignment")
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

                break

        for match in _CREDENTIAL_ASSIGNMENT_RE.finditer(
            new_content
        ):

            if RiskEngine._credential_value_looks_real(
                match.group("value")
            ):

                signals.append(
                    ("structured_credential", "assignment")
                )

                level = RiskLevel.max_level(
                    level,
                    RiskLevel.HIGH,
                )

                break

        if _TOKEN_LIKE_RE.search(new_content):

            signals.append(
                ("credential_token", "token_like")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        if any(
            RiskEngine._looks_encoded(match.group(1))
            for match in _BASE64_MATERIAL_RE.finditer(
                new_content
            )
        ):

            signals.append(
                ("encoded_material", "base64_like")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        if _CREDENTIAL_URL_RE.search(new_content):

            signals.append(
                ("credential_url", "userinfo")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        if _SHELL_CREDENTIAL_RE.search(new_content):

            signals.append(
                ("shell_credential", "flag")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        if (
            _ENV_SECRET_REFERENCE_RE.search(new_content)
            or _SHELL_ENV_REFERENCE_RE.search(new_content)
            or _GENERIC_GET_SECRET_RE.search(new_content)
        ):

            signals.append(
                ("env_secret_reference", "environment")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        if (
            _AUTH_HEADER_RE.search(new_content)
            or _BEARER_RE.search(new_content)
        ):

            signals.append(
                ("authorization_material", "header")
            )

            level = RiskLevel.max_level(
                level,
                RiskLevel.HIGH,
            )

        return signals, level

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
