import os
import subprocess
import sys

import pytest

from simulation.agent.worker.worker_agent import (
    WorkerAgent
)

from simulation.agent.worker.worker_task import (
    WorkerTask
)


class RecordingAnalyzer:

    def __init__(self):

        self.calls = []

    def analyze(
        self,
        path,
        content,
        description
    ):

        self.calls.append({
            "path": path,
            "content": content,
            "description": description
        })

        old_text = content

        new_text = (
            content
            + "\n# Recorded worker marker\n"
        )

        return (
            "Recorded analyzer produced a patch.",
            old_text,
            new_text
        )


@pytest.fixture
def analyzer():

    return RecordingAnalyzer()


@pytest.fixture
def worker(analyzer):

    return WorkerAgent(
        analyzer=analyzer
    )


def _make_task(
    allowed_paths,
    read_paths,
    description="Inspect read scope."
):

    return WorkerTask(
        task_id="read-scope-task",
        description=description,
        allowed_paths=allowed_paths,
        read_paths=read_paths
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


def _denied_entry(
    evidence,
    path
):

    matches = [
        entry
        for entry in evidence
        if entry["path"] == path
    ]

    return matches[0]


def test_worker_reads_allowed_file(
    tmp_path,
    worker,
    analyzer
):

    target = tmp_path / "allowed.txt"

    content = "allowed content\n"

    target.write_text(
        content,
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(str(target),),
        read_paths=()
    )

    result = worker.run(task)

    assert result.success is True

    assert (
        "Worker inspection and patch proposal completed."
        in result.summary
    )

    entry = _denied_entry(
        result.evidence,
        str(target)
    )

    assert entry["status"] == "success"

    assert result.patches

    assert result.patches[0].path == str(target)

    assert len(analyzer.calls) == 1

    assert analyzer.calls[0]["content"] == content


def test_worker_reads_allowed_file_with_explicit_read_paths(
    tmp_path,
    worker
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "file.txt"

    content = "in scope\n"

    target.write_text(
        content,
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(str(target),)
    )

    result = worker.run(task)

    assert result.success is True

    assert result.patches

    assert result.patches[0].path == str(target)


def test_worker_denies_out_of_scope_read(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside = tmp_path / "secret.txt"

    secret = "secret outside content\n"

    outside.write_text(
        secret,
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(str(outside),)
    )

    result = worker.run(task)

    assert result.success is False

    assert (
        "Worker denied out-of-scope file reads."
        in result.summary
    )

    entry = _denied_entry(
        result.evidence,
        str(outside)
    )

    assert entry["status"] == "denied"

    assert (
        "outside the allowed scope"
        in entry["error"]
    )

    assert not result.patches

    assert analyzer.calls == []

    assert (
        outside.read_text(
            encoding="utf-8"
        )
        == secret
    )


def test_worker_denies_traversal_read(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside = tmp_path / "secret.txt"

    outside.write_text(
        "secret\n",
        encoding="utf-8"
    )

    traversal = str(
        scope / ".." / "secret.txt"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(traversal,)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        traversal
    )

    assert entry["status"] == "denied"

    assert "traversal" in entry["error"]

    assert analyzer.calls == []


def test_worker_denies_absolute_outside_read(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside = tmp_path / "secret.txt"

    outside.write_text(
        "secret\n",
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(os.path.abspath(str(outside)),)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        os.path.abspath(str(outside))
    )

    assert entry["status"] == "denied"

    assert (
        "outside the allowed scope"
        in entry["error"]
    )

    assert analyzer.calls == []


def test_worker_denies_symlink_escape_read(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside = tmp_path / "secret.txt"

    secret = "secret symlink content\n"

    outside.write_text(
        secret,
        encoding="utf-8"
    )

    link = scope / "escape_link.txt"

    _symlink_or_skip(
        outside,
        link
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(str(link),)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        str(link)
    )

    assert entry["status"] == "denied"

    assert "symlink escape" in entry["error"]

    assert analyzer.calls == []


def test_worker_denies_junction_escape_read(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    outside_dir = tmp_path / "outside_dir"

    outside_dir.mkdir()

    secret = outside_dir / "secret.txt"

    secret.write_text(
        "secret junction content\n",
        encoding="utf-8"
    )

    link = scope / "linked"

    _junction_or_skip(
        link,
        outside_dir
    )

    escape_path = str(
        link / "secret.txt"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(escape_path,)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        escape_path
    )

    assert entry["status"] == "denied"

    assert "symlink escape" in entry["error"]

    assert analyzer.calls == []


def test_worker_read_fails_with_empty_allowed_paths(
    tmp_path,
    worker,
    analyzer
):

    target = tmp_path / "target.txt"

    target.write_text(
        "content\n",
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(),
        read_paths=(str(target),)
    )

    result = worker.run(task)

    assert result.success is False

    assert (
        "No allowed paths were provided."
        in result.summary
    )

    assert not result.patches

    assert analyzer.calls == []


def test_worker_read_fails_with_none_allowed_paths(
    tmp_path,
    worker,
    analyzer
):

    target = tmp_path / "target.txt"

    target.write_text(
        "content\n",
        encoding="utf-8"
    )

    task = WorkerTask(
        task_id="read-scope-task",
        description="Inspect read scope.",
        allowed_paths=None,
        read_paths=(str(target),)
    )

    result = worker.run(task)

    assert result.success is False

    assert (
        "No allowed paths were provided."
        in result.summary
    )

    assert not result.patches

    assert analyzer.calls == []


def test_worker_denies_scope_with_traversal(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    scope.mkdir()

    target = scope / "target.txt"

    target.write_text(
        "content\n",
        encoding="utf-8"
    )

    bad_scope = (
        str(tmp_path / ".." / "target.txt"),
    )

    task = _make_task(
        allowed_paths=bad_scope,
        read_paths=(str(target),)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        str(target)
    )

    assert entry["status"] == "denied"

    assert "traversal" in entry["error"]

    assert analyzer.calls == []


def test_worker_denies_scope_with_empty_entry(
    tmp_path,
    worker,
    analyzer
):

    target = tmp_path / "target.txt"

    target.write_text(
        "content\n",
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=("",),
        read_paths=(str(target),)
    )

    result = worker.run(task)

    assert result.success is False

    entry = _denied_entry(
        result.evidence,
        str(target)
    )

    assert entry["status"] == "denied"

    assert "empty path entry" in entry["error"]

    assert analyzer.calls == []


def test_worker_still_reads_within_directory_scope(
    tmp_path,
    worker,
    analyzer
):

    scope = tmp_path / "scope"

    nested = scope / "nested"

    nested.mkdir(
        parents=True
    )

    outside = tmp_path / "secret.txt"

    outside.write_text(
        "secret\n",
        encoding="utf-8"
    )

    in_scope = nested / "real.txt"

    in_scope.write_text(
        "real in-scope content\n",
        encoding="utf-8"
    )

    task = _make_task(
        allowed_paths=(str(scope),),
        read_paths=(
            str(in_scope),
            str(outside)
        )
    )

    result = worker.run(task)

    assert result.success is True

    assert (
        "Worker inspection and patch proposal completed."
        in result.summary
    )

    denied = [
        entry
        for entry in result.evidence
        if entry["status"] == "denied"
    ]

    assert len(denied) == 1

    assert denied[0]["path"] == str(outside)

    assert result.patches

    assert result.patches[0].path == str(in_scope)

    received = {
        call["path"]
        for call in analyzer.calls
    }

    assert str(outside) not in received
