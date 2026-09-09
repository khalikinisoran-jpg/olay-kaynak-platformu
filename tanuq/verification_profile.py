"""Tanuq Verification Profile V1 — deterministic test-target selection.

Gives the product's ``VERIFIED`` outcome a workspace-relevant meaning:

    stage 1 (unchanged)  compileall -q -f over the protected workspace
    stage 2 (this file)  pytest over REAL workspace tests conventionally
                         related to the patched file, falling back to
                         the guaranteed dummy floor when none exist

Selection rules (deterministic; the agent cannot choose its own
verifiers — only the governed patch target path influences selection):

- only paths inside the protected workspace are considered
- anything under ``.tanuq`` (the dummy's home) is never a candidate
- a patched test module verifies itself
- otherwise the conventional pairs are checked for existence:
    <ws>/test_<stem>.py         <ws>/<stem>_test.py
    <ws>/tests/test_<stem>.py   <ws>/tests/<stem>_test.py
- symlink containment: a candidate is selected only if its RESOLVED
  path is still inside the workspace (a symlinked ``tests/`` directory
  or symlinked test file pointing outside is silently skipped)
- no globbing, no recursion: the candidate set is bounded by
  construction and capped at MAX_RELATED_TEST_TARGETS

Fail-closed semantics are untouched: VerificationExecutor remains the
only pass/fail authority, ``-p no:cacheprovider`` and the verification
timeout are unchanged, and a missing/failing/timeout target still
produces FAIL -> ROLLED_BACK exactly as before.
"""
from pathlib import Path

from tanuq.config import TANUQ_DIR_NAME

PROFILE_ID = "related-tests-v1"
MODE_RELATED = "related_tests"
MODE_DUMMY_FLOOR = "dummy_floor"
MAX_RELATED_TEST_TARGETS = 16


def _is_test_module_name(name: str) -> bool:
    return name.endswith(".py") and (
        name.startswith("test_") or name.endswith("_test.py")
    )


def related_test_candidates(workspace, patch_path):
    """Convention-based existing test candidates for one patch path.

    Pure path computation over a fixed candidate set; never globs,
    never recurses, never returns a path outside the workspace and
    never returns anything under ``.tanuq``.
    """
    try:
        resolved = Path(patch_path).resolve()
        ws = Path(workspace).resolve()
        rel = resolved.relative_to(ws)
    except Exception:
        return ()
    parts = rel.parts
    if not parts or TANUQ_DIR_NAME in parts:
        return ()
    name = parts[-1]
    if _is_test_module_name(name):
        candidates = (resolved,)
    else:
        stem = Path(name).stem
        candidates = tuple(
            base / pattern
            for base in (ws, ws / "tests")
            for pattern in (
                f"test_{stem}.py",
                f"{stem}_test.py",
            )
        )
    found = []
    for candidate in candidates:
        try:
            resolved_candidate = candidate.resolve()
            # Symlink containment (fail-closed): a candidate that is
            # lexically under the workspace but resolves outside it
            # (e.g. a symlinked ``tests/`` directory or a symlinked
            # test file) is never selected. Only real workspace tests
            # verify a workspace patch.
            resolved_candidate.relative_to(ws)
        except (OSError, ValueError):
            continue
        try:
            if resolved_candidate.is_file():
                found.append(str(resolved_candidate))
        except OSError:
            continue
    return tuple(dict.fromkeys(found))


def select_test_targets(env, patch_paths):
    """Pick the pytest targets for one governed execution.

    Returns ``(test_targets, profile_view)``. ``profile_view`` is a
    JSON-serializable, evidence-facing description of exactly what the
    tests stage verified, so a VERIFIED outcome is deterministically
    interpretable from the result and the recorded evidence alone.
    """
    related = []
    for patch_path in patch_paths:
        for candidate in related_test_candidates(env.workspace, patch_path):
            related.append(candidate)
        if len(related) >= MAX_RELATED_TEST_TARGETS:
            break
    related = sorted(dict.fromkeys(related))[:MAX_RELATED_TEST_TARGETS]
    if related:
        return tuple(related), {
            "profile": PROFILE_ID,
            "mode": MODE_RELATED,
            "test_targets": related,
        }
    dummy = env.ensure_dummy_test()
    return (str(dummy),), {
        "profile": PROFILE_ID,
        "mode": MODE_DUMMY_FLOOR,
        "test_targets": [str(dummy)],
    }
