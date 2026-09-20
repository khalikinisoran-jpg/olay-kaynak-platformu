"""README identity contract (G-05).

The README first-contact (entry) section must state the CURRENT TANUQ
product identity and must not carry stale branch/commit/tag references,
stale test/CI counts, or future-capability claims. Historical, vision
and roadmap content below the entry section is out of scope for this
contract.

Read-only static-content test: this verifies only the README identity
contract, never runtime behavior.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "readme.md"

# Entry section = everything before the feature list that follows the
# identity/vision/why/version blocks.
ENTRY_END_MARKER = "# Current Features"

CURRENT_IDENTITY_MARKERS = (
    "tanuq",
    "human-governed file-editing agent runtime",
    "modify",
    "create",
    "tanuq propose --stdin-json --json",
    "claude code",
    "tamper-evident",
    "docs/tanuq_project_state.md",
)

STALE_REFS = (
    # stale commit shas
    "9df6953",
    "d958237",
    "b2d6da7",
    "24c72d0",
    # stale branch identity
    "worker-action-pipeline",
    # stale tag
    "v0.5.0",
    # stale present-tense framing
    "experimental",
)

FUTURE_CLAIMS = (
    "future multi-agent support",
    "multi-agent support",
)


def _entry():
    text = README.read_text(encoding="utf-8")
    return text[: text.index(ENTRY_END_MARKER)].lower()


def test_readme_entry_states_current_product_identity():
    entry = _entry()
    for marker in CURRENT_IDENTITY_MARKERS:
        assert marker in entry, f"current identity marker missing: {marker}"


def test_readme_entry_has_no_stale_refs():
    entry = _entry()
    for ref in STALE_REFS:
        assert ref not in entry, f"stale ref in README entry section: {ref}"


def test_readme_entry_has_no_future_capability_claims():
    entry = _entry()
    for claim in FUTURE_CLAIMS:
        assert claim not in entry, f"future claim in README entry: {claim}"


def test_readme_entry_points_to_live_truth_source():
    entry = _entry()
    assert "docs/tanuq_project_state.md" in entry
