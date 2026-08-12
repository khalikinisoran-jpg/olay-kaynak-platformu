import re

from pathlib import Path


REDACTED_MARKER = "[REDACTED]"

SECRET_FILE_SUFFIXES = frozenset({
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".ppk",
    ".htpasswd",
    ".pwd",
    ".pgpass",
})

SECRET_FILE_NAMES = frozenset({
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".netrc",
    ".pypirc",
    ".npmrc",
    ".git-credentials",
    "credentials",
    "credentials.json",
    "secrets.yml",
    "secrets.yaml",
    "secret.yaml",
    "secret.yml",
})

_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*-----.*?-----END [A-Z ]*-----",
    re.DOTALL,
)

_AUTHORIZATION_HEADER = re.compile(
    r"(\bauthorization\s*[:=]\s*)"
    r"(?:Bearer\s+\S+|Basic\s+\S+)",
    re.IGNORECASE,
)

_SECRET_ASSIGNMENT = re.compile(
    r"(\b(?:api[_-]?key|secret|token|password|passwd|"
    r"client[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"private[_-]?key|auth[_-]?token|secret[_-]?key)\b"
    r"\s*[:=]\s*)(\"?)([^\"'\s,;]+)(\"?)",
    re.IGNORECASE,
)

_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")

_GITHUB_TOKEN = re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")

_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_\-]{10,}\."
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
)

_GENERIC_SECRET_LITERAL = re.compile(
    r"(\b(?:password|passwd|secret|token|api[_-]?key|"
    r"client[_-]?secret|access[_-]?token)\b"
    r"\s*=\s*[\"'])([^\"']{4,})([\"'])",
    re.IGNORECASE,
)

_REDACTION_PATTERNS = (
    _PEM_BLOCK,
    _AUTHORIZATION_HEADER,
    _SECRET_ASSIGNMENT,
    _AWS_KEY,
    _OPENAI_KEY,
    _GITHUB_TOKEN,
    _JWT,
    _GENERIC_SECRET_LITERAL,
)


def _mask_key_value(match):

    return match.group(1) + REDACTED_MARKER


def _mask_quoted_literal(match):

    return (
        match.group(1)
        + REDACTED_MARKER
        + match.group(3)
    )


_REDACTIONS = (
    (_PEM_BLOCK, REDACTED_MARKER),
    (_AUTHORIZATION_HEADER, _mask_key_value),
    (_SECRET_ASSIGNMENT, _mask_key_value),
    (_AWS_KEY, REDACTED_MARKER),
    (_OPENAI_KEY, REDACTED_MARKER),
    (_GITHUB_TOKEN, REDACTED_MARKER),
    (_JWT, REDACTED_MARKER),
    (_GENERIC_SECRET_LITERAL, _mask_quoted_literal),
)


def is_secret_file(path) -> bool:

    """Fail-closed whole-file secret classification.

    A file is treated as a secret file when its name matches a known
    credential file or its suffix matches a known secret-material
    suffix. Secret files are never read into the LLM analyzer.
    """

    if not isinstance(path, str) or not path:

        return False

    try:

        candidate = Path(path)

    except (TypeError, ValueError):

        return False

    name = candidate.name.lower()

    if name in SECRET_FILE_NAMES:

        return True

    if candidate.suffix.lower() in SECRET_FILE_SUFFIXES:

        return True

    if name in SECRET_FILE_SUFFIXES:

        return True

    return False


def redact_content(content) -> tuple[str, bool]:

    """Replace obvious secret material with ``REDACTED_MARKER``.

    Returns ``(redacted_content, was_redacted)``. The redaction only
    masks high-confidence secret values; it never removes surrounding
    structure, so normal source-code analysis of non-secret parts of a
    file keeps working. Redaction is a defense-in-depth boundary, not a
    guarantee: it cannot catch every possible secret representation.
    """

    if not isinstance(content, str):

        return content, False

    redacted = content

    was_redacted = False

    for pattern, replacement in _REDACTIONS:

        redacted, count = pattern.subn(
            replacement,
            redacted,
        )

        was_redacted = was_redacted or count > 0

    return redacted, was_redacted
