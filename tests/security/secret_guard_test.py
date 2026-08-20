"""Adversarial corpus for the repository-local secret guard (RELEASE-03).

Every value below is a SYNTHETIC FAKE. No real credential is used. The
suite measures false-negative (missed secret) and false-positive (benign
text flagged) behaviour of ``scripts/secret_guard.py``.

This file is listed in the guard's ``FIXTURE_PATHS`` allowlist because it
intentionally contains fake secret values.
"""

import importlib.util
import zipfile
from pathlib import Path

import pytest

GUARD_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "secret_guard.py"
)

_spec = importlib.util.spec_from_file_location(
    "secret_guard",
    GUARD_PATH,
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------- #
# Adversarial: fake secrets that MUST be detected (false-negative check)
# --------------------------------------------------------------------------- #

# Deterministic non-sequential fake token segments (no fake markers).
T = "kZ9xR2mQ4vW8nB6cH3jF5sD7gA1pO0iU6yT4eR8wQ2zX9cV5bN7mJ3kH6gF1dS4aZ8x"

FAKE_SECRETS = [
    # 1. OpenRouter-like fake key (public format: sk-or-v1- + long token)
    ("openrouter", "sk-or-v1-" + T),
    # 2. generic API key
    ("generic-api-key", 'api_key = "kZ9xR2mQ4vW8nB6cH3jF5sD7gA1pO0iU6yT4eR8w"'),
    # 3. bearer token
    ("bearer", "Authorization: Bearer " + T),
    # 4. PEM private-key marker
    ("pem", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAA\n-----END RSA PRIVATE KEY-----"),
    # 5. credentials.json
    ("credentials-json", '{"client_id": "app123", "client_secret": "' + T + '"}'),
    # 6. cloud credential (AWS)
    ("aws", "AKIA" + "KZ9XR2MQ4VW8NB6C"),
    # 7. environment-variable secret assignment
    ("env-var", 'export OPENAI_API_KEY="sk-proj-' + T + '"'),
    # 8. password assignment
    ("password", 'password = "kZ9xR2mQ4vW8nB6cH3jF5sD7gA1pO0iU6yT4e"'),
    # 9. multiline secret (continuation across lines)
    ("multiline", 'OPENAI_API_KEY = "sk-proj-\n    ' + T + '"'),
    # 10. secret embedded in JSON
    ("json-embedded", '{"config": {"token": "ghp_' + "KZ9XR2MQ4VW8NB6CH3JF5SD7GA1PO0IU6YT4" + '"} }'),
    # 11. secret embedded in YAML
    ("yaml-embedded", "api_key: sk-ant-api03-" + T[:60]),
    # 12. secret embedded in Python
    ("python-embedded", "OPENROUTER_API_KEY = 'sk-or-v1-" + T + "'"),
    # 13. secret embedded in shell
    ("shell-embedded", "export ANTHROPIC_API_KEY='sk-ant-api03-" + T[:60] + "'"),
    # 14. secret in documentation
    ("docs-embedded", "connect with api_token sk-proj-" + T + " to the API"),
    # 15. secret in zip/snapshot fixture (stored, byte-searchable)
    ("zip-embedded", None),  # constructed below
]

# Additional provider-specific fake keys (Phase 8)
PROVIDER_FAKES = [
    ("openai-legacy", "sk-" + "KZ9XR2MQ4VW8NB6CH3JF5SD7GA1PO0IU6YT4ER8WQ2ZX9CV5BN7MJ3KH6GF1DS4AZ8X"),
    ("anthropic", "sk-ant-api03-" + T[:60]),
    ("google-api", "AIza" + T[:35]),
    ("github-pat", "ghp_" + "KZ9XR2MQ4VW8NB6CH3JF5SD7GA1PO0IU6YT4"),
    ("github-fine-grained", "github_pat_" + "KZ9XR2MQ4VW8NB6CH3JF5SD7GA1PO0IU6YT4ER8WQ2ZX9CV5BN7MJ3KH6GF1DS4AZ8X_1" + "0" * 30),
    ("slack-token", "xoxb-" + "KZ9XR2MQ4VW8NB6CH3JF5SD7"),
    ("uri-password", "postgres://app_user:" + T[:24] + "@db.internal:5432/app"),
]


def _zip_fixture(tmp_path):
    """Create a ZIP (stored, uncompressed) containing a fake .env entry."""

    archive = tmp_path / "snapshot-fixture.zip"

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:

        zf.writestr(
            ".env",
            "OPENROUTER_API_KEY=sk-or-v1-"
            + "QqWwEeRrTtYyUuIiOoPpAaSsDdFfGgHhJjKkLlZzXxCcVvBbNnMm11223344556677889900",
        )

    return archive


@pytest.mark.parametrize("name", [n for n, _ in FAKE_SECRETS])
def test_fake_secret_is_detected(name, tmp_path):
    if name == "zip-embedded":

        archive = _zip_fixture(tmp_path)

        findings, errors = guard.scan_path(str(archive))

        assert errors == []
        assert findings, f"zip fixture not detected ({name})"
        return

    text = dict(FAKE_SECRETS)[name]

    findings = guard.detect_text(text, "probe.txt")

    assert findings, f"fake secret not detected ({name})"


@pytest.mark.parametrize("name,text", PROVIDER_FAKES)
def test_provider_secret_is_detected(name, text):
    findings = guard.detect_text(text, "probe.txt")
    assert findings, f"provider fake not detected ({name})"


def test_pem_variants_are_detected():
    for marker in (
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN ENCRYPTED PRIVATE KEY-----",
    ):
        findings = guard.detect_text(marker, "key.pem")
        names = [f["detector"] for f in findings]
        assert "private-key-marker" in names, f"missed: {marker}"


def test_public_certificate_is_not_private_key():
    cert = "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAg\n-----END CERTIFICATE-----"
    findings = guard.detect_text(cert, "public.crt")
    names = [f["detector"] for f in findings]
    assert "private-key-marker" not in names


def test_credentials_json_file_detected(tmp_path):
    target = tmp_path / "credentials.json"
    target.write_text(
        '{"client_id": "app", "client_secret": "ssssssssssssssssssssssssss", '
        '"refresh_token": "rrrrrrrrrrrrrrrrrrrrrrrrrr"}',
        encoding="utf-8",
    )
    findings, errors = guard.scan_path(str(target))
    assert errors == []
    names = [f["detector"] for f in findings]
    assert "credentials-json-content" in names


def test_env_file_with_secret_detected(tmp_path):
    target = tmp_path / ".env.prod"
    target.write_text(
        "OPENROUTER_API_KEY=sk-or-v1-ZzzYyyXxxWwwVvvUuuTttSssRrrQqqPppOooNnnMmm",
        encoding="utf-8",
    )
    findings, errors = guard.scan_path(str(target))
    assert errors == []
    assert findings


# --------------------------------------------------------------------------- #
# Benign examples that MUST be allowed (false-positive check)
# --------------------------------------------------------------------------- #

BENIGN = [
    ("placeholder", "OPENROUTER_API_KEY=your-key-here"),
    ("example-key", 'api_key = "your-example-key-12345678"'),
    ("documentation", "See https://docs.example.com for the API reference."),
    ("fixture-no-secret", 'password = "test-fixture-value-123"'.replace("test-fixture-value-123", "placeholder-password")),
    ("normal-string", "The quick brown fox jumps over the lazy dog 1234567890"),
    ("hash-not-secret", "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
    ("uuid-not-secret", "550e8400-e29b-41d4-a716-446655440000"),
]


@pytest.mark.parametrize("name,text", BENIGN)
def test_benign_text_is_allowed(name, text):
    findings = guard.detect_text(text, "probe.txt")
    assert findings == [], f"false positive ({name}): {findings}"


def test_env_example_is_allowed(tmp_path):
    target = tmp_path / ".env.example"
    target.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    findings, errors = guard.scan_path(str(target))
    assert errors == []
    assert findings == []


def test_short_placeholder_api_key_is_allowed():
    text = 'api_key = "sk-test-provider-key"'
    findings = guard.detect_text(text, "probe.txt")
    assert findings == []


def test_repo_fixtures_are_allowed_by_default():
    repo = Path(__file__).resolve().parents[2]
    findings, errors = guard.scan_path(str(repo))
    assert errors == []
    fixture_files = {
        str(p) for p in repo.joinpath("tests").rglob("*.py")
        if "secret" in p.name or "adversarial" in p.name
    }
    flagged = {f["path"] for f in findings}
    assert not (flagged & fixture_files)


# --------------------------------------------------------------------------- #
# Fail-closed behaviour (Phase 4)
# --------------------------------------------------------------------------- #

def test_missing_path_is_scan_error_not_clean():
    missing = str(Path(__file__).resolve().parents[2] / "does-not-exist-xyz")
    findings, errors = guard.scan_path(missing)
    assert findings == []
    assert errors, "missing path must be a scan error, not clean"


def test_cli_exit_codes(tmp_path):
    fake = tmp_path / "fake.env"
    fake.write_text(
        "OPENROUTER_API_KEY=sk-or-v1-" + "A" * 60,
        encoding="utf-8",
    )
    assert guard.main([str(fake)]) == 1

    clean = tmp_path / "clean.txt"
    clean.write_text("no secrets here", encoding="utf-8")
    assert guard.main([str(clean)]) == 0


def test_fake_marker_suppression_is_deterministic():
    text = 'api_key = "abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnopqrstuvwxyz"'
    first = guard.detect_text(text, "a.txt")
    second = guard.detect_text(text, "a.txt")
    assert first == second
