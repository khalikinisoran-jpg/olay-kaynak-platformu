"""Tanuq Verification Profile V1 tests.

Proves the product-level verification change:

    - deterministic, convention-based related-test selection
    - dummy floor fallback when no related tests exist
    - VERIFIED now runs REAL workspace tests when they exist
    - fail-closed regression: failing related test -> ROLLED_BACK
    - existing dummy-floor behavior is preserved unchanged

The security core (VerificationExecutor pass/fail authority, timeout,
``-p no:cacheprovider``, rollback) is not re-tested here; it is covered
by the existing corpus and is unchanged by this profile.
"""
import json
import sys
from pathlib import Path

import pytest

from tanuq import agent_adapter
from tanuq.config import init_workspace, tanuq_data_dir, DUMMY_TEST_FILE_NAME
from tanuq.runtime import load_environment
from tanuq.verification_profile import (
    MAX_RELATED_TEST_TARGETS,
    MODE_DUMMY_FLOOR,
    MODE_RELATED,
    select_test_targets,
)


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


def _dummy_path(env):
    return str(tanuq_data_dir(env.workspace) / DUMMY_TEST_FILE_NAME)


# ---- selection (unit level) ----


def test_related_test_selected_from_tests_directory(env):
    (env.workspace / "tests").mkdir()
    related = env.workspace / "tests" / "test_mod.py"
    related.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    assert targets == (str(related.resolve()),)
    assert profile["mode"] == MODE_RELATED
    assert profile["profile"] == "related-tests-v1"


def test_related_test_selected_from_workspace_root(env):
    related = env.workspace / "mod_test.py"
    related.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    assert targets == (str(related.resolve()),)
    assert profile["mode"] == MODE_RELATED


def test_patched_test_file_verifies_itself(env):
    target = env.workspace / "test_mod.py"
    target.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    targets, profile = select_test_targets(env, [str(target)])
    assert targets == (str(target.resolve()),)
    assert profile["mode"] == MODE_RELATED


def test_no_related_tests_falls_back_to_dummy_floor(env):
    targets, profile = select_test_targets(env, [str(env.workspace / "demo.txt")])
    assert targets == (_dummy_path(env),)
    assert profile["mode"] == MODE_DUMMY_FLOOR
    assert profile["test_targets"] == [_dummy_path(env)]


def test_missing_candidate_file_is_not_selected(env):
    (env.workspace / "mod.py").write_text("x = 1\n", encoding="utf-8")
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    assert targets == (_dummy_path(env),)
    assert profile["mode"] == MODE_DUMMY_FLOOR


def test_outside_workspace_path_is_never_selected(env):
    outside = env.workspace.parent / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    targets, profile = select_test_targets(env, [str(outside)])
    assert targets == (_dummy_path(env),)
    assert profile["mode"] == MODE_DUMMY_FLOOR


def test_tanuq_data_dir_is_never_a_candidate(env):
    targets, profile = select_test_targets(
        env, [str(tanuq_data_dir(env.workspace) / DUMMY_TEST_FILE_NAME)]
    )
    assert targets == (_dummy_path(env),)
    assert profile["mode"] == MODE_DUMMY_FLOOR


def test_selection_is_deduplicated_and_capped(env):
    (env.workspace / "tests").mkdir()
    for index in range(MAX_RELATED_TEST_TARGETS + 4):
        related = env.workspace / "tests" / f"test_f{index}.py"
        related.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    patch_paths = [
        str(env.workspace / f"f{index}.py")
        for index in range(MAX_RELATED_TEST_TARGETS + 4)
    ]
    targets, profile = select_test_targets(env, patch_paths)
    assert len(targets) == MAX_RELATED_TEST_TARGETS
    assert targets == tuple(sorted(set(targets)))
    assert profile["mode"] == MODE_RELATED


def _symlink_or_skip(link, target, target_is_directory):
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        pytest.skip(
            "symlink creation not permitted on this platform/account"
        )


def test_symlinked_tests_dir_cannot_escape_workspace(env):
    outside = env.workspace.parent / "outside_tests"
    outside.mkdir()
    (outside / "test_mod.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    _symlink_or_skip(env.workspace / "tests", outside, True)
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    outside_resolved = str((outside / "test_mod.py").resolve())
    assert outside_resolved not in targets
    for target in targets:
        assert Path(target).resolve().relative_to(
            Path(env.workspace).resolve()
        )
    assert profile["mode"] == MODE_DUMMY_FLOOR


def test_symlinked_test_file_cannot_escape_workspace(env):
    outside = env.workspace.parent / "outside_tests"
    outside.mkdir()
    (outside / "test_mod.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    (env.workspace / "tests").mkdir()
    _symlink_or_skip(
        env.workspace / "tests" / "test_mod.py",
        outside / "test_mod.py",
        False,
    )
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    outside_resolved = str((outside / "test_mod.py").resolve())
    assert outside_resolved not in targets
    for target in targets:
        assert Path(target).resolve().relative_to(
            Path(env.workspace).resolve()
        )
    assert profile["mode"] == MODE_DUMMY_FLOOR


def test_junctioned_tests_dir_cannot_escape_workspace_windows(env):
    """Windows, unprivileged reparse-point variant of the symlink test.

    An NTFS junction needs no privileges, is a real reparse point and
    is followed by ``Path.resolve()`` exactly like a symlink, so this
    exercises the same containment rule on Windows where symlink
    creation would be skipped.
    """
    if sys.platform != "win32":
        pytest.skip("Windows junction test")
    import _winapi

    outside = env.workspace.parent / "outside_tests"
    outside.mkdir()
    (outside / "test_mod.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    link = env.workspace / "tests"
    try:
        _winapi.CreateJunction(str(outside), str(link))
    except OSError:
        pytest.skip("junction creation not permitted")
    resolved_link = link.resolve()
    assert resolved_link == outside.resolve()  # junction really reparse-resolves
    targets, profile = select_test_targets(env, [str(env.workspace / "mod.py")])
    outside_resolved = str((outside / "test_mod.py").resolve())
    assert outside_resolved not in targets
    for target in targets:
        assert Path(target).resolve().relative_to(
            Path(env.workspace).resolve()
        )
    assert profile["mode"] == MODE_DUMMY_FLOOR


# ---- governed end-to-end (real pipeline, real evidence) ----


def _propose(env, payload):
    return agent_adapter.propose(env, json.dumps(payload))


def test_verified_runs_real_related_workspace_test(env):
    (env.workspace / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="")
    (env.workspace / "tests").mkdir()
    (env.workspace / "tests" / "test_mod.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_mod_state():\n"
        "    target = Path(__file__).resolve().parent.parent / \"mod.py\"\n"
        "    assert \"x = 2\" in target.read_text(encoding=\"utf-8\")\n",
        encoding="utf-8",
    )
    _propose(env, {
        "path": str(env.workspace / "mod.py"),
        "old_content": "x = 1\n",
        "new_content": "x = 2\n",
        "reason": "real verification",
    })
    response = agent_adapter.execute(env)
    assert response["executed"] is True
    assert response["terminal"] == "VERIFIED"
    assert response["verification_passed"] is True
    assert response["verification_profile"]["mode"] == MODE_RELATED
    assert response["verification_profile"]["test_targets"] == [
        str((env.workspace / "tests" / "test_mod.py").resolve())
    ]
    assert (env.workspace / "mod.py").read_text(encoding="utf-8") == "x = 2\n"


def test_failing_related_test_rolls_back_fail_closed(env):
    (env.workspace / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="")
    (env.workspace / "tests").mkdir()
    (env.workspace / "tests" / "test_mod.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_mod_state():\n"
        "    target = Path(__file__).resolve().parent.parent / \"mod.py\"\n"
        "    assert \"x = 3\" in target.read_text(encoding=\"utf-8\")\n",
        encoding="utf-8",
    )
    _propose(env, {
        "path": str(env.workspace / "mod.py"),
        "old_content": "x = 1\n",
        "new_content": "x = 2\n",
        "reason": "should be rolled back",
    })
    response = agent_adapter.execute(env)
    assert response["executed"] is True
    assert response["terminal"] == "ROLLED_BACK"
    assert response["verification_passed"] is False
    assert (env.workspace / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


def test_dummy_floor_end_to_end_behavior_preserved(env):
    _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello fixed",
        "reason": "agent fix",
    })
    response = agent_adapter.execute(env)
    assert response["executed"] is True
    assert response["terminal"] == "VERIFIED"
    assert response["verification_passed"] is True
    assert response["verification_profile"]["mode"] == MODE_DUMMY_FLOOR
    assert response["verification_profile"]["test_targets"] == [_dummy_path(env)]
    assert (env.workspace / "demo.txt").read_text(encoding="utf-8") == "hello fixed"


def _verification_events(env):
    return [
        event for event in env.store.read_all()
        if "verification" in str(event.event_type).lower()
    ]


def test_journal_records_exactly_the_used_profile_related_mode(env):
    (env.workspace / "mod.py").write_text("x = 1\n", encoding="utf-8", newline="")
    (env.workspace / "tests").mkdir()
    (env.workspace / "tests" / "test_mod.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    _propose(env, {
        "path": str(env.workspace / "mod.py"),
        "old_content": "x = 1\n",
        "new_content": "x = 2\n",
        "reason": "journal correlation",
    })
    response = agent_adapter.execute(env)
    assert response["terminal"] == "VERIFIED"
    journal_profile = [
        event.payload["verification_profile"]
        for event in _verification_events(env)
        if "verification_profile" in event.payload
    ]
    assert len(journal_profile) == 1
    # the journaled profile is the REAL profile of the same execute
    # flow (verbatim), not a recomputation
    assert journal_profile[0] == response["verification_profile"]
    assert journal_profile[0]["profile"] == "related-tests-v1"
    assert journal_profile[0]["mode"] == MODE_RELATED
    assert journal_profile[0]["test_targets"] == [
        str((env.workspace / "tests" / "test_mod.py").resolve())
    ]
    # the journaled pytest command actually targets the profile targets
    verification_events = [
        event.payload for event in _verification_events(env)
        if "verification_profile" in event.payload
    ]
    commands = [
        tuple(command["command"])
        for command in verification_events[0]["commands"]
        if command["stage"] == "tests"
    ]
    assert commands and commands[0][-1] == journal_profile[0]["test_targets"][0]


def test_journal_records_exactly_the_used_profile_dummy_floor(env):
    _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello fixed",
        "reason": "journal correlation floor",
    })
    response = agent_adapter.execute(env)
    assert response["terminal"] == "VERIFIED"
    journal_profile = [
        event.payload["verification_profile"]
        for event in _verification_events(env)
        if "verification_profile" in event.payload
    ]
    assert len(journal_profile) == 1
    assert journal_profile[0] == response["verification_profile"]
    assert journal_profile[0]["mode"] == MODE_DUMMY_FLOOR
    assert journal_profile[0]["test_targets"] == [_dummy_path(env)]
