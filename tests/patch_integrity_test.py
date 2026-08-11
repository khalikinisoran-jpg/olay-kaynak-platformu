import os
from pathlib import Path

import pytest

from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.apply.file_applier import (
    FileApplier
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)


def make_patch(
    target,
    old_content,
    new_content,
    allowed_paths
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Patch integrity hardening test.",
        old_content=old_content,
        new_content=new_content,
        allowed_paths=tuple(allowed_paths),
    )


def make_verification_result():
    return VerificationResult(
        status=PASS,
        exit_code=0,
        stdout="1 passed",
        stderr="",
        command=("venv-python", "-m", "pytest", "-q"),
    )


class FakeVerificationExecutor:

    def __init__(self, result):
        self.result = result

    def verify(self, paths, test_targets=()):
        return self.result


def _symlink_or_skip(source, link):
    try:
        os.symlink(source, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(
            f"Symlinks are not available here: {exc}"
        )


def test_file_applier_denies_concurrent_modification_between_validation_and_apply(
    tmp_path
):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    validator = PatchValidator()

    valid, _ = validator.validate(patch)

    assert valid is True

    target.write_text(
        "interleaved change\n",
        encoding="utf-8"
    )

    applier = FileApplier()

    ok, message = applier.apply(patch)

    assert ok is False

    assert "stale" in message.lower()

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == "interleaved change\n"
    )


def test_second_stale_patch_to_same_file_is_denied(
    tmp_path
):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    first = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    applier = FileApplier()

    ok, _ = applier.apply(first)

    assert ok is True

    stale = make_patch(
        target,
        original,
        "value = 3\n",
        (str(target),)
    )

    ok, message = applier.apply(stale)

    assert ok is False

    assert "stale" in message.lower()

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_file_applier_writes_through_in_scope_symlink_to_real_target(
    tmp_path
):

    scope = tmp_path / "scope"

    scope.mkdir()

    real_target = scope / "real.txt"

    original = "original\n"

    updated = "updated\n"

    real_target.write_text(
        original,
        encoding="utf-8"
    )

    link = scope / "link.txt"

    _symlink_or_skip(
        real_target,
        link
    )

    patch = make_patch(
        link,
        original,
        updated,
        (str(scope),)
    )

    applier = FileApplier()

    ok, message = applier.apply(patch)

    assert ok is True

    assert (
        real_target.read_text(
            encoding="utf-8"
        )
        == updated
    )

    assert (
        link.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_file_applier_detects_corrupted_write_and_restores(
    tmp_path,
    monkeypatch
):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    real_write = Path.write_text

    calls = {"n": 0}

    def corrupting_write(self, content, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            content = "CORRUPTED WRITE\n"
        return real_write(self, content, *args, **kwargs)

    monkeypatch.setattr(
        Path,
        "write_text",
        corrupting_write,
    )

    applier = FileApplier()

    ok, message = applier.apply(patch)

    assert ok is False

    assert "integrity check failed" in message.lower()

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )


def test_approved_fingerprint_matches_applied_content(
    tmp_path
):

    from simulation.agent.pipeline.apply_verify_pipeline import (
        ApplyVerifyPipeline
    )

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    decision = ControllerDecision(
        approved=True,
        reason="Integrity test approval.",
        patch_fingerprint=patch.fingerprint(),
    )

    pipeline = ApplyVerifyPipeline(
        verification_executor=FakeVerificationExecutor(
            make_verification_result()
        ),
    )

    result = pipeline.execute(
        patch,
        decision,
    )

    assert result.apply_success is True

    assert result.verification_passed is True

    assert decision.patch_fingerprint == patch.fingerprint()

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == updated
    )


def test_apply_executor_denies_fingerprint_mismatch_before_write(
    tmp_path
):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    other = make_patch(
        target,
        original,
        "value = 9\n",
        (str(target),)
    )

    decision = ControllerDecision(
        approved=True,
        reason="Approval for a different patch.",
        patch_fingerprint=other.fingerprint(),
    )

    executor = ApplyExecutor()

    result = executor.apply(
        patch,
        decision,
    )

    assert result.success is False

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )
