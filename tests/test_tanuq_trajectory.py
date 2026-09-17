"""Tanuq trajectory telemetry projection tests.

Read-only projection over the existing evidence events: no
enforcement, no approval/risk/policy changes, no evidence mutation.
"""
import hashlib
import json

import pytest

from tanuq import trajectory
from tanuq.config import init_workspace, tanuq_data_dir
from tanuq.evidence import chain_status
from tanuq.runtime import load_environment
from tanuq.coordinator import OperationCoordinator
from tanuq import agent_adapter


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    yield


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    init_workspace(ws)
    return load_environment(ws), ws


def _propose_execute(env, path, old, new, reason, session="t"):
    payload = json.dumps({
        "path": str(path), "action": "modify", "reason": reason,
        "old_content": old, "new_content": new,
    })
    proposal = agent_adapter.propose(env, payload, session=session)
    first = proposal["proposals"][0]
    if first.get("governance", {}).get("approval_required"):
        agent_adapter.approve(env, first["fingerprint"])
    result = OperationCoordinator(env).execute(
        fingerprint=first["fingerprint"], session=session)
    return first, result


def _events_bytes(ws):
    return (tanuq_data_dir(ws) / "events.jsonl").read_bytes()


def _events_digest(ws):
    return hashlib.sha256(_events_bytes(ws)).hexdigest()


def test_empty_evidence_gives_empty_projection(env):
    e, ws = env
    projection = trajectory.trajectory_projection(e)
    assert projection["operation_count"] == 0
    assert projection["path_count"] == 0
    assert projection["paths"] == []


def test_single_operation_count_is_one(env, tmp_path):
    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "single op")
    projection = trajectory.trajectory_projection(e)
    assert projection["operation_count"] == 1
    assert projection["path_count"] == 1
    entry = projection["paths"][0]
    assert entry["operation_count"] == 1
    assert entry["consecutive_auto_apply_count"] == 1
    op = entry["operations"][0]
    assert op["action"] == "modify"
    assert op["outcome"] == "VERIFIED"
    assert op["verified"] is True
    assert op["auto_apply"] is True
    assert op["approval_required"] is False


def test_three_consecutive_medium_auto_applies(env, tmp_path):
    e, ws = env
    target = ws / "sample_util.py"
    content = 'def run_task():\n    return "ok"\n'
    target.write_text(content, encoding="utf-8", newline="")
    for i in range(1, 4):
        old, new = content, content + f"\n# step {i}\n"
        first, result = _propose_execute(
            e, target, old, new, f"step {i}")
        assert result.get("terminal") == "VERIFIED"
        content = new
    projection = trajectory.trajectory_projection(e)
    assert projection["operation_count"] == 3
    entry = projection["paths"][0]
    assert entry["operation_count"] == 3
    assert entry["consecutive_auto_apply_count"] == 3
    assert entry["risk_sequence"] == ["MEDIUM"] * 3
    assert entry["risk_transitions"] == []
    assert entry["failure_count"] == 0
    assert entry["rollback_count"] == 0
    assert all(op["auto_apply"] for op in entry["operations"])


def test_risk_transition_medium_to_high(env, tmp_path):
    e, ws = env
    target = ws / "sample_util.py"
    content = 'def run_task():\n    return "ok"\n'
    target.write_text(content, encoding="utf-8", newline="")
    first, result = _propose_execute(
        e, target, content, content + "\n# plain step\n", "plain step")
    assert result.get("terminal") == "VERIFIED"
    content = content + "\n# plain step\n"
    # base64-bearing content carries the encoded_material signal -> HIGH
    import base64
    blob = base64.b64encode(b"local_sink.txt").decode()
    encoded = content + f'\n_ENCODED = "{blob}"\n'
    first2, result2 = _propose_execute(
        e, target, content, encoded, "encoded step")
    assert first2["governance"]["risk"] == "HIGH"
    assert result2.get("terminal") == "VERIFIED"
    projection = trajectory.trajectory_projection(e)
    entry = projection["paths"][0]
    assert entry["risk_sequence"] == ["MEDIUM", "HIGH"]
    assert entry["risk_transitions"] == [["MEDIUM", "HIGH"]]
    assert entry["operations"][0]["auto_apply"] is True
    assert entry["operations"][1]["auto_apply"] is False
    assert entry["operations"][1]["approval_granted"] is True
    # the HIGH (non-auto) op breaks the consecutive auto run
    assert entry["consecutive_auto_apply_count"] == 1


def test_verification_failure_and_rollback_counters(env, tmp_path):
    """Derivation over the real evidence schema: a verification-failed
    lifecycle recorded through the real evidence recorder increments
    failure_count; rollbacks stay 0 when none occurred."""
    from simulation.agent.worker.patch_proposal import PatchProposal

    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "single op")

    failed_patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="fixture failed lifecycle",
        old_content="hello fixed",
        new_content="hello broken",
        allowed_paths=tuple(e.config.allowed_paths),
    )
    decision = e.governance.evaluate(failed_patch)
    e.recorder.record_patch_proposed("traj-fixture", failed_patch)
    e.recorder.record_risk_assessed("traj-fixture", failed_patch, decision)
    e.recorder.record_patch_validated(
        "traj-fixture", failed_patch, True, "validated")

    class _FailedVerification:
        passed = False
        status = "FAILED"
        exit_code = 1
        failure_reason = "fixture verification failure"
        evidence = ()

    e.recorder.record_verification_result(
        "traj-fixture", failed_patch, _FailedVerification())

    projection = trajectory.trajectory_projection(e)
    entry = projection["paths"][0]
    assert entry["operation_count"] == 2
    assert entry["failure_count"] == 1
    assert entry["rollback_count"] == 0
    assert entry["verification_sequence"] == [True, False]
    assert entry["outcome_sequence"][1] == "VERIFICATION_FAILED"
    assert entry["consecutive_auto_apply_count"] == 1


def test_cprime_style_six_step_reference_trajectory(env, tmp_path):
    e, ws = env
    target = ws / "sample_util.py"
    content = 'def run_task():\n    return "ok"\n'
    target.write_text(content, encoding="utf-8", newline="")
    for i in range(1, 7):
        old, new = content, content + f"\n# step {i}\n"
        first, result = _propose_execute(
            e, target, old, new, f"cprime step {i}")
        assert result.get("terminal") == "VERIFIED"
        content = new
    projection = trajectory.trajectory_projection(e)
    assert projection["operation_count"] == 6
    assert projection["path_count"] == 1
    entry = projection["paths"][0]
    assert entry["operation_count"] == 6
    assert entry["consecutive_auto_apply_count"] == 6
    assert all(op["action"] == "modify" for op in entry["operations"])
    assert entry["risk_sequence"] == ["MEDIUM"] * 6
    assert entry["outcome_sequence"] == ["VERIFIED"] * 6
    assert entry["verification_sequence"] == [True] * 6
    assert all(op["auto_apply"] for op in entry["operations"])
    assert entry["failure_count"] == 0
    assert entry["rollback_count"] == 0


def test_projection_is_deterministic_and_read_only(env, tmp_path):
    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "op")

    digest_before = _events_digest(ws)
    first = trajectory.trajectory_projection(e)
    second = trajectory.trajectory_projection(e)
    digest_after = _events_digest(ws)

    assert json.dumps(first, sort_keys=True) == json.dumps(
        second, sort_keys=True)
    assert digest_before == digest_after
    status = chain_status(tanuq_data_dir(ws), None)
    assert status["chain_valid"] is True
    assert status["events"] > 0


def test_existing_evidence_reads_unaffected_by_projection(env, tmp_path):
    from tanuq.evidence import lineage

    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "op")

    before = lineage(e)
    trajectory.trajectory_projection(e)
    after = lineage(e)
    assert json.dumps(before, sort_keys=True) == json.dumps(
        after, sort_keys=True)


def test_path_filter(env, tmp_path):
    e, ws = env
    demo = ws / "demo.txt"
    demo.write_text("hello", encoding="utf-8", newline="")
    other = ws / "notes.md"
    other.write_text("note\n", encoding="utf-8", newline="")
    _propose_execute(e, demo, "hello", "hello fixed", "op demo")
    _propose_execute(e, other, "note\n", "note v2\n", "op notes")
    projection = trajectory.trajectory_projection(
        e, path=str(other))
    assert projection["path_count"] == 1
    assert projection["paths"][0]["path"] == str(other)
    assert projection["paths"][0]["operation_count"] == 1


# ---- CLI consumer surface ----


def _cli_json(ws, extra=()):
    from tanuq import cli
    import io as _io
    from contextlib import redirect_stdout
    buf = _io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(["trajectory", "--workspace", str(ws),
                         "--json", *extra])
    return code, json.loads(buf.getvalue())


def test_cli_trajectory_human_view(env, capsys):
    from tanuq import cli
    e, ws = env
    target = ws / "sample_util.py"
    content = 'def run_task():\n    return "ok"\n'
    target.write_text(content, encoding="utf-8", newline="")
    for i in range(1, 7):
        old, new = content, content + f"\n# step {i}\n"
        _, result = _propose_execute(e, target, old, new, f"step {i}")
        assert result.get("terminal") == "VERIFIED"
        content = new
    code = cli.main(["trajectory", "--workspace", str(ws)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Tanuq trajectory" in out
    assert "6 operation(s)" in out
    assert "sample_util.py" in out
    assert "consecutive auto-apply: 6" in out
    assert "MEDIUM × 6" in out
    assert "VERIFIED × 6" in out
    assert "Failures:     0" in out


def test_cli_trajectory_json_matches_projection_and_is_deterministic(
        env, capsys):
    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "op")
    code1, first = _cli_json(ws)
    code2, second = _cli_json(ws)
    assert code1 == code2 == 0
    assert first == second
    assert first == trajectory.trajectory_projection(e)
    assert first["operation_count"] == 1
    assert first["paths"][0]["risk_sequence"] == ["LOW"]


def test_cli_trajectory_empty_workspace(env, capsys):
    from tanuq import cli
    e, ws = env
    code = cli.main(["trajectory", "--workspace", str(ws)])
    assert code == 0
    out = capsys.readouterr().out
    assert "No trajectory data." in out
    code, report = _cli_json(ws)
    assert code == 0
    assert report["operation_count"] == 0
    assert report["paths"] == []


def test_cli_trajectory_path_filter(env, tmp_path, capsys):
    from tanuq import cli
    e, ws = env
    demo = ws / "demo.txt"
    demo.write_text("hello", encoding="utf-8", newline="")
    other = ws / "notes.md"
    other.write_text("note\n", encoding="utf-8", newline="")
    _propose_execute(e, demo, "hello", "hello fixed", "op demo")
    _propose_execute(e, other, "note\n", "note v2\n", "op notes")
    code, report = _cli_json(ws, extra=["--path", str(other)])
    assert code == 0
    assert report["path_count"] == 1
    assert report["paths"][0]["path"] == str(other)
    code = cli.main(["trajectory", "--workspace", str(ws),
                     "--path", "notes.md"])
    assert code == 0
    out = capsys.readouterr().out
    assert "notes.md" in out
    assert "demo.txt" not in out


def test_cli_trajectory_does_not_mutate_evidence(env, tmp_path, capsys):
    from tanuq import cli
    from tanuq.evidence import chain_status
    e, ws = env
    target = ws / "demo.txt"
    target.write_text("hello", encoding="utf-8", newline="")
    _propose_execute(e, target, "hello", "hello fixed", "op")
    digest_before = _events_digest(ws)
    assert cli.main(["trajectory", "--workspace", str(ws)]) == 0
    capsys.readouterr()
    assert cli.main(["trajectory", "--workspace", str(ws), "--json"]) == 0
    capsys.readouterr()
    assert _events_digest(ws) == digest_before
    status = chain_status(tanuq_data_dir(ws), None)
    assert status["chain_valid"] is True
