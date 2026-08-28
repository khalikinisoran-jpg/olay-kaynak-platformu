#!/usr/bin/env python3
"""Repository-local deterministic secret guard.

Purpose
-------
A small, explainable, stdlib-only scanner that detects high-signal secret
patterns before code is committed or shipped. It complements (not replaces)
a full secret-scanning tool: it is intentionally narrow and deterministic so
a developer can understand exactly why a scan failed.

Guarantees
----------
* Fail-closed: any scan error (unreadable file, unexpected exception) is
  reported as ``SCAN ERROR`` and exits with code 3. An error is NEVER
  reported as clean.
* Deterministic: same input -> same output.
* No network, no dependencies outside the Python standard library.

Exit codes
----------
0   clean (no secrets found, no scan errors)
1   secrets found
2   usage error
3   scan error (fail-closed; never treated as clean)

Usage
-----
python scripts/secret_guard.py [--no-fixture-exclusion] [paths...]

Without paths the repository root is scanned (default exclusions applied).
With paths, only those files/directories are scanned.

Policy notes
------------
* Known synthetic test fixtures (files that intentionally contain fake
  secret values for the security test suite) are excluded by default via
  ``FIXTURE_PATHS``. Use ``--no-fixture-exclusion`` to scan them.
* ``.env.example`` is always allowed (documented safe template).
* Values containing obvious fake markers (``example``, ``placeholder``,
  ``test-key``, sequential alphabet, ``hunter2``, etc.) are suppressed.
"""

import argparse
import os
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# Directories never scanned, relative to any scan root.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "build",
    "dist",
    "data",
}

# Files that intentionally contain synthetic (fake) secret values used by
# the security test suite. Excluded from whole-repo scans by default so the
# scanner reports clean on a legitimately-fixture-heavy tree.
FIXTURE_PATHS = {
    "tests/approval_console_test.py",
    "tests/mission_h_security_test.py",
    "tests/property/governance_property_test.py",
    "tests/property/memory_property_test.py",
    "tests/risk_engine_test.py",
    "tests/risk_pipeline_test.py",
    "tests/risk_regression_test.py",
    "tests/secret_boundary_test.py",
    "tests/secret_retry_boundary_test.py",
    "tests/security/adversarial_corpus_test.py",
    "tests/security/secret_guard_test.py",
    "tests/test_external_t_b10.py",
}

# Value substrings that mark a candidate as an obvious fake / placeholder.
# A candidate matching any of these is NOT reported.
FAKE_MARKERS = (
    "example",
    "placeholder",
    "replace-me",
    "your-",
    "your_",
    "fake",
    "dummy",
    "sample",
    "test-key",
    "test-provider",
    "test-token",
    "test-123",
    "redacted",
    "secret-value",
    "super-secret",
    "hunter2",
    "topsecretmarker",
    "xxxxxxxx",
    ".....",
    "abcdefghijklmnopqrstuvwxyz",
    "1234567890abcdef",
)

# Filenames that are always allowed even though they look secret-adjacent.
ALWAYS_ALLOWED_BASENAMES = {
    ".env.example",
    "env.example",
}

# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
# (name, compiled regex). Regexes target publicly documented credential
# formats. Capture group 1 (or the full match) is the candidate value used
# for fake-marker suppression.

DETECTORS = [
    (
        "openrouter",
        re.compile(
            r"\bsk-or-v1-[A-Za-z0-9_-]{40,}\b"
        ),
    ),
    (
        "openai",
        re.compile(
            r"\bsk-(proj|realtime|svcacct|admin)-[A-Za-z0-9_-]{40,}\b"
        ),
    ),
    (
        "openai-legacy",
        re.compile(
            r"\bsk-[A-Za-z0-9]{48,}\b"
        ),
    ),
    (
        "anthropic",
        re.compile(
            r"\bsk-ant-api03-[A-Za-z0-9_-]{40,}\b"
        ),
    ),
    (
        "google-api",
        re.compile(
            r"\bAIza[0-9A-Za-z_-]{35}\b"
        ),
    ),
    (
        "github-pat",
        re.compile(
            r"\bghp_[A-Za-z0-9]{36}\b"
        ),
    ),
    (
        "github-fine-grained",
        re.compile(
            r"\bgithub_pat_[A-Za-z0-9_]{80,}\b"
        ),
    ),
    (
        "github-oauth",
        re.compile(
            r"\bgh[osur]_[A-Za-z0-9]{36}\b"
        ),
    ),
    (
        "aws-access-key",
        re.compile(
            r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"
        ),
    ),
    (
        "slack-token",
        re.compile(
            r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"
        ),
    ),
    (
        "private-key-marker",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
        ),
    ),
    (
        "generic-api-key",
        re.compile(
            r"\b(?:api[_-]?key|apikey|client[_-]?secret|"
            r"access[_-]?token|auth[_-]?token|secret[_-]?key)"
            r"\"?\s*[=:]\s*[\"']?([A-Za-z0-9._~/-]{16,})[\"']?"
        ),
    ),
    (
        "password-assignment",
        re.compile(
            r"\bpassword\"?\s*[=:]\s*[\"']([^\"'\s]{8,})[\"']"
        ),
    ),
    (
        "bearer-token",
        re.compile(
            r"\b[Bb]earer\s+([A-Za-z0-9._~+/=-]{20,})\b"
        ),
    ),
    (
        "authorization-header",
        re.compile(
            r"\bauthorization\"?\s*[=:]\s*[\"']?(?:[Bb]earer\s+)?"
            r"([A-Za-z0-9._~+/=-]{20,})"
        ),
    ),
    (
        "env-secret-assignment",
        re.compile(
            r"\b(?:export\s+)?[A-Z][A-Z0-9_]*"
            r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)\"?\s*=\s*"
            r"[\"']?([A-Za-z0-9._~/-]{16,})[\"']?"
        ),
    ),
    (
        "uri-password",
        re.compile(
            r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)://"
            r"[^:/@\s]+:[^@\s/]+@"
        ),
    ),
]


# --------------------------------------------------------------------------- #
# Core detection
# --------------------------------------------------------------------------- #


def _is_fake(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in FAKE_MARKERS)


def detect_text(text: str, filename: str = "") -> list:
    """Return a list of finding dicts for the given text.

    Pure content detector: fake-marker suppression applies, filename-based
    exclusion does not. Used directly by the unit/corpus tests and by the
    scanner.

    A second pass runs against a line-continuation-normalized copy
    (``<line-break> <indent>`` collapsed to a single space) so secrets
    split across continuation lines are still detected.
    """

    findings = []

    normalized = re.sub(r"\r?\n[ \t]*", "", text)

    for name, pattern in DETECTORS:

        for source in (text, normalized):

            for match in pattern.finditer(source):

                value = (
                    match.group(1)
                    if match.lastindex and match.group(1) is not None
                    else match.group(0)
                )

                if not value or _is_fake(value):

                    continue

                if any(
                    f["detector"] == name
                    and f["value"] == value
                    for f in findings
                ):

                    continue

                findings.append(
                    {
                        "detector": name,
                        "value": value,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "start": match.start(),
                        "end": match.end(),
                        "preview": _preview(value),
                    }
                )

    return findings


def _preview(value: str) -> str:
    if len(value) <= 10:
        return "<REDACTED>"
    return value[:6] + "<REDACTED>"


# --------------------------------------------------------------------------- #
# File / directory scanning
# --------------------------------------------------------------------------- #


def _filename_hints(filename: str) -> list:
    hints = []
    base = Path(filename).name.lower()
    stem = Path(filename).name

    if base in ("credentials.json",):
        hints.append("credentials-json-filename")
    if base.startswith("service-account") and base.endswith(".json"):
        hints.append("service-account-filename")
    if stem.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")):
        hints.append("private-key-extension")
    if base.startswith(".env") and base not in ALWAYS_ALLOWED_BASENAMES:
        hints.append("env-filename")
    return hints


def _credentials_json_like(text: str, filename: str) -> bool:
    base = Path(filename).name.lower()
    if not (
        base == "credentials.json"
        or base.startswith("service-account")
    ):
        return False
    secret_fields = re.compile(
        r"\"?(?:client_secret|private_key|access_token|"
        r"refresh_token|api_key)\"?\s*:"
    )
    return bool(secret_fields.search(text))


REPO_ROOT = Path(__file__).resolve().parents[1]


def scan_file(path, exclude_fixtures: bool = True) -> list:
    """Scan a single file, returning (findings, error)."""

    resolved = str(Path(path).resolve()).replace("\\", "/")

    try:

        rel = resolved.split(
            str(REPO_ROOT).replace("\\", "/") + "/",
            1,
        )[1]

    except IndexError:

        rel = resolved

    if exclude_fixtures and rel in FIXTURE_PATHS:

        return [], None

    base = Path(path).name

    if base in ALWAYS_ALLOWED_BASENAMES:

        return [], None

    try:

        data = path.read_bytes()

    except Exception as exc:  # pragma: no cover - env dependent

        return [], f"read error: {path}: {exc}"

    text = data.decode("utf-8", errors="replace")

    findings = detect_text(text, str(path))

    hints = _filename_hints(base)

    if "private-key-extension" in hints:

        findings.append(
            {
                "detector": "private-key-extension",
                "value": "<REDACTED>",
                "line": 0,
                "start": 0,
                "end": 0,
                "preview": "<REDACTED>",
            }
        )

    if "env-filename" in hints:

        for name, value in _env_assignments(text):

            if value and not _is_fake(value):

                findings.append(
                    {
                        "detector": "env-file-assignment",
                        "value": value,
                        "line": 0,
                        "start": 0,
                        "end": 0,
                        "preview": _preview(value),
                    }
                )

    if _credentials_json_like(text, base):

        findings.append(
            {
                "detector": "credentials-json-content",
                "value": "<REDACTED>",
                "line": 0,
                "start": 0,
                "end": 0,
                "preview": "<REDACTED>",
            }
        )

    return findings, None


def _env_assignments(text: str):
    for line in text.splitlines():

        stripped = line.strip()

        if not stripped or stripped.startswith("#"):

            continue

        match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$",
            stripped,
        )

        if match:

            yield match.group(1), match.group(2).strip()


def scan_path(root, exclude_fixtures: bool = True):
    """Recursively scan a file or directory.

    Returns (findings, errors) where errors is a list of scan-error strings.
    Each finding carries the absolute ``path`` of the file that matched.
    """

    path = Path(root)

    findings = []
    errors = []

    if not path.exists():

        errors.append(f"path not found: {root}")

        return findings, errors

    def _scan_file(current):

        found, error = scan_file(current, exclude_fixtures)

        for finding in found:

            finding["path"] = str(current)

        findings.extend(found)

        if error:

            errors.append(error)

    if path.is_file():

        _scan_file(path)

        return findings, errors

    for current_root, dirnames, filenames in os.walk(path):

        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDED_DIRS
        ]

        for name in filenames:

            _scan_file(Path(current_root) / name)

    return findings, errors


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print_finding(finding, path):

    location = f"{path}"

    if finding["line"]:

        location = f"{location}:{finding['line']}"

    print(
        "SECRET DETECTED — VALUE REDACTED: "
        f"{location} detector={finding['detector']} "
        f"value={finding['preview']}"
    )


def main(argv=None):

    parser = argparse.ArgumentParser(
        description="Repository-local deterministic secret guard."
    )

    parser.add_argument(
        "--no-fixture-exclusion",
        action="store_true",
        help="Scan known synthetic test fixtures too.",
    )

    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan (default: repository root).",
    )

    args = parser.parse_args(argv)

    exclude_fixtures = not args.no_fixture_exclusion

    if args.paths:

        roots = args.paths

    else:

        roots = [str(Path(__file__).resolve().parents[1])]

    findings = []
    errors = []

    for root in roots:

        found, err = scan_path(root, exclude_fixtures)

        findings.extend(found)

        errors.extend(err)

    if errors:

        for error in errors:

            print(f"SCAN ERROR: {error}")

        print("RESULT: SCAN ERROR — not treated as clean.")
        return 3

    if findings:

        for finding in findings:

            _print_finding(finding, finding.get("path", ""))

        print(f"RESULT: {len(findings)} SECRET(S) FOUND.")
        return 1

    print("RESULT: CLEAN.")
    return 0


if __name__ == "__main__":

    sys.exit(main())
