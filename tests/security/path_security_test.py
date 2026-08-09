import os
import subprocess
import sys

import pytest

from simulation.security.path_policy import (
    PathPolicy
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.apply.file_applier import (
    FileApplier
)


@pytest.fixture
def policy():

    return PathPolicy()


def _make_patch(
    path,
    old_content,
    new_content,
    allowed_paths
):

    return PatchProposal(
        path=path,
        action="modify",
        reason="Path security regression test.",
        old_content=old_content,
        new_content=new_content,
        allowed_paths=allowed_paths
    )


def _symlink_or_skip(
    source,
    link
):

    try:

        os.symlink(
            source,
            link
        )

    except (OSError, NotImplementedError) as exc:

        pytest.skip(
            f"Symlinks are not available here: {exc}"
        )


def test_path_policy_rejects_empty_path(
    policy
):

    ok, message = policy.check_scope(
        "",
        ("target.txt",)
    )

    assert ok is False

    assert "Patch path is empty." in message


def test_path_policy_rejects_none_path(
    policy
):

    ok, message = policy.check_scope(
        None,
        ("target.txt",)
    )

    assert ok is False

    assert "Patch path" in message


def test_path_policy_rejects_empty_scope(
    policy
):

    ok, message = policy.check_scope(
        "target.txt",
        ()
    )

    assert ok is False

    assert "allowed_paths" in message


def test_path_policy_rejects_none_scope(
    policy
):

    ok, message = policy.check_scope(
        "target.txt",
        None
    )

    assert ok is False

    assert "allowed_paths" in message


def test_path_policy_rejects_scope_with_empty_entry(
    policy
):

    ok, message = policy.check_scope(
        "target.txt",
        ("target.txt", "")
    )

    assert ok is False

    assert "empty path entry" in message


def test_path_policy_rejects_null_byte_in_path(
    policy
):

    ok, message = policy.check_scope(
        "target\x00.txt",
        ("target.txt",)
    )

    assert ok is False

    assert "null byte" in message


def test_path_policy_rejects_null_byte_in_scope(
    policy
):

    ok, message = policy.check_scope(
        "target.txt",
        ("target\x00.txt",)
    )

    assert ok is False

    assert "null byte" in message


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../secret.txt",
        "allowed/../../etc/passwd",
        "a/../b.txt",
        "..",
        "allowed\\..\\secret.txt",
    ]
)
def test_path_policy_rejects_path_traversal(
    policy,
    traversal_path
):

    ok, message = policy.check_scope(
        traversal_path,
        ("allowed/",)
    )

    assert ok is False

    assert "traversal" in message


def test_path_policy_rejects_scope_traversal(
    policy
):

    ok, message = policy.check_scope(
        "target.txt",
        ("../target.txt",)
    )

    assert ok is False

    assert "traversal" in message


def test_path_policy_accepts_exact_scope_match(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "file.txt"

    target.write_text(
        "x\n",
        encoding="utf-8"
    )

    ok, _ = policy.check_scope(
        str(target),
        (str(target),)
    )

    assert ok is True


def test_path_policy_accepts_descendant_in_directory_scope(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    nested = scope / "nested"

    nested.mkdir(
        parents=True
    )

    target = nested / "file.txt"

    target.write_text(
        "x\n",
        encoding="utf-8"
    )

    ok, _ = policy.check_scope(
        str(target),
        (str(scope),)
    )

    assert ok is True


def test_path_policy_rejects_sibling_out_of_scope(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    allowed = scope / "allowed.txt"

    allowed.write_text(
        "x\n",
        encoding="utf-8"
    )

    outside = tmp_path / "outside.txt"

    outside.write_text(
        "x\n",
        encoding="utf-8"
    )

    ok, message = policy.check_scope(
        str(outside),
        (str(allowed),)
    )

    assert ok is False

    assert "outside the allowed scope" in message


def test_path_policy_rejects_prefix_confusion(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    allowed = scope / "allowed.txt"

    allowed.write_text(
        "x\n",
        encoding="utf-8"
    )

    sibling = scope / "allowed.txt_secret"

    sibling.write_text(
        "x\n",
        encoding="utf-8"
    )

    ok, message = policy.check_scope(
        str(sibling),
        (str(allowed),)
    )

    assert ok is False

    assert "outside the allowed scope" in message


def test_path_policy_accepts_dot_normalized_in_scope(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "file.txt"

    target.write_text(
        "x\n",
        encoding="utf-8"
    )

    dot_path = os.path.join(
        str(scope),
        ".",
        "file.txt"
    )

    ok, _ = policy.check_scope(
        dot_path,
        (str(scope),)
    )

    assert ok is True


def test_path_policy_matches_relative_and_absolute_forms(
    tmp_path,
    policy,
    monkeypatch
):

    monkeypatch.chdir(tmp_path)

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "file.txt"

    target.write_text(
        "x\n",
        encoding="utf-8"
    )

    ok, _ = policy.check_scope(
        str(target),
        ("scope",)
    )

    assert ok is True

    ok, _ = policy.check_scope(
        "scope/file.txt",
        (str(scope),)
    )

    assert ok is True


def test_path_policy_rejects_symlink_escape(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    allowed = scope / "allowed.txt"

    allowed.write_text(
        "x\n",
        encoding="utf-8"
    )

    outside = tmp_path / "outside_secret.txt"

    outside.write_text(
        "secret\n",
        encoding="utf-8"
    )

    link = scope / "link.txt"

    _symlink_or_skip(
        outside,
        link
    )

    ok, message = policy.check_scope(
        str(link),
        (str(scope),)
    )

    assert ok is False

    assert "symlink escape" in message


def _junction_or_skip(
    link,
    target
):

    if not sys.platform.startswith("win"):

        pytest.skip(
            "Junctions are Windows-only."
        )

    result = subprocess.run(
        [
            "cmd",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(target)
        ],
        capture_output=True
    )

    if (
        result.returncode != 0
        or not link.exists()
    ):

        detail = result.stderr.decode(
            "utf-8",
            errors="replace"
        )

        pytest.skip(
            "Junctions are not available here: "
            + detail.strip()
        )


def test_path_policy_rejects_junction_escape(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside_dir = tmp_path / "outside_dir"

    outside_dir.mkdir()

    secret = outside_dir / "secret.txt"

    secret.write_text(
        "secret\n",
        encoding="utf-8"
    )

    link = scope / "linked"

    _junction_or_skip(
        link,
        outside_dir
    )

    ok, message = policy.check_scope(
        str(link / "secret.txt"),
        (str(scope),)
    )

    assert ok is False

    assert "symlink escape" in message


def test_path_policy_accepts_junction_within_scope(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    nested = scope / "nested"

    nested.mkdir(
        parents=True
    )

    real = nested / "real.txt"

    real.write_text(
        "x\n",
        encoding="utf-8"
    )

    link = scope / "linked"

    _junction_or_skip(
        link,
        nested
    )

    ok, _ = policy.check_scope(
        str(link / "real.txt"),
        (str(scope),)
    )

    assert ok is True


def test_path_policy_accepts_symlink_within_scope(
    tmp_path,
    policy
):

    scope = tmp_path / "scope"

    scope.mkdir()

    real = scope / "real.txt"

    real.write_text(
        "x\n",
        encoding="utf-8"
    )

    link = scope / "link.txt"

    _symlink_or_skip(
        real,
        link
    )

    ok, _ = policy.check_scope(
        str(link),
        (str(scope),)
    )

    assert ok is True


def test_patch_validator_rejects_traversal_path(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    original = "original\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    outside = tmp_path / "outside.txt"

    outside.write_text(
        original,
        encoding="utf-8"
    )

    patch = _make_patch(
        path=str(
            scope / ".." / "outside.txt"
        ),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    validator = PatchValidator()

    ok, message = validator.validate(
        patch
    )

    assert ok is False

    assert "traversal" in message

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_patch_validator_rejects_symlink_escape(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    original = "original\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    outside = tmp_path / "outside.txt"

    outside.write_text(
        original,
        encoding="utf-8"
    )

    link = scope / "escape_link.txt"

    _symlink_or_skip(
        outside,
        link
    )

    patch = _make_patch(
        path=str(link),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    validator = PatchValidator()

    ok, message = validator.validate(
        patch
    )

    assert ok is False

    assert "symlink escape" in message

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_traversal_path(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    original = "original\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    outside = tmp_path / "outside.txt"

    outside.write_text(
        original,
        encoding="utf-8"
    )

    patch = _make_patch(
        path=str(
            scope / ".." / "outside.txt"
        ),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch
    )

    assert ok is False

    assert "traversal" in message

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_scope_with_traversal(
    tmp_path
):

    target = tmp_path / "target.txt"

    original = "original\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = _make_patch(
        path=str(target),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(
            str(tmp_path / ".." / "target.txt"),
        )
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch
    )

    assert ok is False

    assert "traversal" in message

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_symlink_escape(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    original = "original\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    outside = tmp_path / "outside.txt"

    outside.write_text(
        original,
        encoding="utf-8"
    )

    link = scope / "escape_link.txt"

    _symlink_or_skip(
        outside,
        link
    )

    patch = _make_patch(
        path=str(link),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch
    )

    assert ok is False

    assert "symlink escape" in message

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_patch_validator_rejects_junction_escape(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside_dir = tmp_path / "outside_dir"

    outside_dir.mkdir()

    original = "original\n"

    secret = outside_dir / "secret.txt"

    secret.write_text(
        original,
        encoding="utf-8"
    )

    link = scope / "linked"

    _junction_or_skip(
        link,
        outside_dir
    )

    patch = _make_patch(
        path=str(link / "secret.txt"),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    validator = PatchValidator()

    ok, message = validator.validate(
        patch
    )

    assert ok is False

    assert "symlink escape" in message

    assert (
        secret.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_rejects_junction_escape(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside_dir = tmp_path / "outside_dir"

    outside_dir.mkdir()

    original = "original\n"

    secret = outside_dir / "secret.txt"

    secret.write_text(
        original,
        encoding="utf-8"
    )

    link = scope / "linked"

    _junction_or_skip(
        link,
        outside_dir
    )

    patch = _make_patch(
        path=str(link / "secret.txt"),
        old_content=original,
        new_content="evil\n",
        allowed_paths=(str(scope),)
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch
    )

    assert ok is False

    assert "symlink escape" in message

    assert (
        secret.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_file_applier_still_writes_inside_scope(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    original = "original\n"

    updated = "updated\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = _make_patch(
        path=str(target),
        old_content=original,
        new_content=updated,
        allowed_paths=(str(scope),)
    )

    applier = FileApplier()

    ok, message = applier.apply(
        patch
    )

    assert ok is True

    assert (
        message
        == "File applied successfully."
    )

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )
