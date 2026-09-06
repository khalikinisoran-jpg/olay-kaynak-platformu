"""Tanuq product lifecycle tests (Deep Moat sprint).

Covers product-level behaviors layered over the governed core:

- session/operation labels through the propose->execute lifecycle
- policy decision explainability (governance signals in the response)
- multi-process pending-store safety (concurrent agents never lose
  a pending proposal)
- persistence across restart
- tamper detection (modified evidence -> verify FAIL + incident)
- crash/restart incident lifecycle (orphaned apply -> incident)

The security core itself stays covered by the existing corpus.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tanuq import agent_adapter, cli
from tanuq.config import tanuq_data_dir, init_workspace
from tanuq.evidence import chain_status
from tanuq.incidents import collect_incidents
from tanuq.pending import load_pending
from tanuq.runtime import load_environment

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


def _propose(env, payload, session=None):
    return agent_adapter.propose(env, json.dumps(payload), session=session)


def test_session_label_flows_through_lifecycle(env):
    target = env.workspace / "demo.txt"
    response = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v2", "reason": "session test",
    }, session="fix-login")
    assert response["session"] == "fix-login"
    records = load_pending(env.workspace)
    assert records[0].get("session") == "fix-login"
    done = agent_adapter.execute(env)
    assert done["terminal"] == "VERIFIED"
    assert done["related_sessions"] == ["fix-login"]
    assert done["pending_count"] == 0


def test_session_label_used_as_evidence_task_id(env):
    target = env.workspace / "demo.txt"
    _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v2", "reason": "session test",
    }, session="ops-task")
    agent_adapter.execute(env, session="ops-run")
    events = (tanuq_data_dir(env.workspace) / "events.jsonl").read_text(
        encoding="utf-8"
    )
    assert "tanuq-session:ops-run" in events


def test_governance_response_is_explainable(env):
    response = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })
    gov = response["proposals"][0]["governance"]
    assert gov["risk"] == "HIGH"
    assert gov["approval_required"] is True
    assert isinstance(gov["signals"], list)
    assert isinstance(gov["assessment_reason"], str) and gov["assessment_reason"]
    assert gov["reason"]


def test_concurrent_propose_never_loses_a_pending_record(env, tmp_path):
    ws = env.workspace
    runner = tmp_path / "race_worker.py"
    runner.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, r'''{repo}''')\n"
        "from tanuq.pending import save_pending\n"
        "from simulation.agent.worker.patch_proposal import PatchProposal\n"
        "ws = Path(sys.argv[1])\n"
        "idx = sys.argv[2]\n"
        "patch = PatchProposal(\n"
        "    path=str(ws / ('race_' + idx + '.py')),\n"
        "    action='modify', reason='race ' + idx,\n"
        "    old_content='a', new_content='b',\n"
        "    allowed_paths=(str(ws),),\n"
        ")\n"
        "save_pending(ws, [patch])\n".format(repo=str(REPO)),
        encoding="utf-8",
    )
    workers = [
        subprocess.Popen(
            [sys.executable, str(runner), str(ws), str(i)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for i in range(6)
    ]
    failures = []
    for w in workers:
        out, err = w.communicate(timeout=60)
        if w.returncode != 0:
            failures.append(err)
    assert not failures, failures
    records = load_pending(ws)
    paths = {Path(r["path"]).name for r in records}
    assert {f"race_{i}.py" for i in range(6)} <= paths


def test_restart_keeps_state_intact(env):
    target = env.workspace / "demo.txt"
    _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v2", "reason": "restart test",
    }, session="restart-check")
    reopened = load_environment(env.workspace)
    records = load_pending(reopened.workspace)
    assert len(records) == 1
    assert records[0].get("session") == "restart-check"
    done = agent_adapter.execute(reopened)
    assert done["terminal"] == "VERIFIED"
    assert (target).read_text(encoding="utf-8") == "hello v2"


def test_tampered_evidence_fails_verify_and_raises_incident(env):
    target = env.workspace / "demo.txt"
    _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v2", "reason": "tamper test",
    })
    agent_adapter.execute(env)
    events_path = tanuq_data_dir(env.workspace) / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"]["task_id"] = "tampered"
    lines[0] = json.dumps(record)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert chain_status(
        tanuq_data_dir(env.workspace), None
    )["chain_valid"] is False
    # Fail-closed: the runtime refuses to start on a broken chain and
    # every command reports it scriptably instead of proceeding.
    assert cli.main(["verify", "--workspace", str(env.workspace)]) == 1
    assert cli.main(["incidents", "--workspace", str(env.workspace)]) == 1
    assert cli.main(["status", "--workspace", str(env.workspace)]) == 1


def test_orphaned_apply_becomes_a_visible_incident(env):
    from simulation.agent.worker.patch_proposal import PatchProposal
    target = env.workspace / "demo.txt"
    patch = PatchProposal(
        path=str(target), action="modify", reason="crash simulation",
        old_content="hello", new_content="hello crashed",
        allowed_paths=tuple(env.config.allowed_paths),
    )
    intent_id = env.apply_journal.record_intent(patch, attempt=1)
    env.apply_journal.record_apply_started(intent_id, reason="crash simulation")

    report = collect_incidents(env)
    match = [i for i in report["incidents"] if i["operation"] == intent_id]
    assert match, report
    incident = match[0]
    assert incident["type"] == "crashed_during_apply"
    assert incident["severity"] == "critical"
    assert "fail-closed" in incident["recovery_status"] or \
        "operator" in incident["recovery_status"]
    assert incident["recommended_action"]


def test_legacy_workspace_dir_migrates_to_tanuq(env):
    from tanuq.config import load_config
    legacy = env.workspace / ".hermes"
    (env.workspace / ".tanuq").rename(legacy)
    config = load_config(env.workspace)
    assert (env.workspace / ".tanuq").exists()
    assert not legacy.exists()
    assert config.allowed_paths == (str(env.workspace.resolve()),)


def test_legacy_device_home_migrates_to_tanuq(tmp_path, monkeypatch):
    from tanuq.config import migrate_legacy_device_home, tanuq_home
    fake = tmp_path / "home"
    fake.mkdir()
    (fake / ".hermes").mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake))
    monkeypatch.setenv("HOME", str(fake))
    assert tanuq_home() == fake / ".tanuq"
    assert migrate_legacy_device_home() is True
    assert (fake / ".tanuq").exists()
    assert not (fake / ".hermes").exists()
    assert migrate_legacy_device_home() is False


def test_export_bundle_is_secret_safe_and_complete(env, tmp_path, capsys):
    target = env.workspace / "demo.txt"
    proposal = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }, session="export-check")["proposals"][0]
    agent_adapter.approve(env, proposal["fingerprint"])
    agent_adapter.execute(env, proposal["fingerprint"])
    out_file = tmp_path / "bundle.json"
    assert cli.main(["export", "--workspace", str(env.workspace),
                     "--out", str(out_file)]) == 0
    bundle = json.loads(out_file.read_text(encoding="utf-8"))
    assert bundle["product"] == "TANUQ"
    assert bundle["governed"] is True
    assert bundle["evidence"]["chain_valid"] is True
    assert bundle["evidence"]["anchor"] == "ACTIVE"
    chains = bundle["lineage"]["chains"]
    assert any(c["outcome"] == "VERIFIED" for c in chains)
    dumped = json.dumps(bundle)
    assert "sk-test-aaaaaaaaaaaaaaaa" not in dumped
    assert "old_content" not in dumped and "new_content" not in dumped


def test_token_never_leaks_into_evidence_or_error_output(env, tmp_path):
    from tanuq.config import read_local_token
    token = read_local_token()
    target = env.workspace / "demo.txt"
    _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v9", "reason": "leak probe",
    })
    agent_adapter.execute(env)
    # exercise an error path as well
    agent_adapter.execute(env, fingerprint="nonexistent0000")
    scanned = ""
    for name in ("events.jsonl", "apply_journal.jsonl",
                 "pending_proposals.json", "approval_ledger.jsonl"):
        p = tanuq_data_dir(env.workspace) / name
        if p.exists():
            scanned += p.read_text(encoding="utf-8")
    report = json.dumps(collect_incidents(env))
    lineage_json = json.dumps(agent_adapter.load_pending(env.workspace))
    for haystack, label in ((scanned, "journals"),
                            (report, "incidents"),
                            (lineage_json, "pending")):
        assert token not in haystack, f"token leaked into {label}"


def test_ci_has_packaging_gate_for_both_platforms():
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "packaging-gate" in ci
    assert "test_tanuq_packaging.py" in ci
    assert "ubuntu-latest" in ci and "windows-latest" in ci
    assert "tanuq --version" in ci
    assert "compileall -q simulation tests p5 tanuq" in ci


def test_incident_command_clean_workspace(env, capsys):
    assert cli.main(["incidents", "--workspace", str(env.workspace)]) == 0
    out = capsys.readouterr().out
    assert "No incidents" in out


def test_lineage_stitches_full_high_chain(env):
    from tanuq.evidence import lineage
    target = env.workspace / "demo.txt"
    proposal = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }, session="lineage-a")["proposals"][0]
    agent_adapter.approve(env, proposal["fingerprint"])
    agent_adapter.execute(env, proposal["fingerprint"])

    report = lineage(env, fingerprint=proposal["fingerprint"])
    assert report["count"] == 1
    chain = report["chains"][0]
    assert chain["proposal"]["reason"] == "cli apply"
    assert chain["risk"]["risk"] == "HIGH"
    assert chain["risk"]["approval_required"] is True
    assert len(chain["approvals"]) == 1
    assert chain["approvals"][0]["status"] == "applied"
    assert chain["execution"]["terminal"] == "VERIFIED"
    assert chain["outcome"] == "VERIFIED"
    assert "lineage-a" in chain["sessions"]
    assert chain["refs"]
    dumped = json.dumps(report)
    assert "sk-test" not in dumped
    assert "old_content" not in dumped and "new_content" not in dumped


def test_lineage_includes_denied_proposal(env):
    from tanuq.evidence import lineage
    outside = env.workspace.parent / "outside.txt"
    outside.write_text("hello", encoding="utf-8", newline="")
    _propose(env, {
        "path": str(outside), "old_content": "hello",
        "new_content": "x", "reason": "escape",
    })
    report = lineage(env)
    denied = [c for c in report["chains"] if c["outcome"] == "DENIED"]
    assert denied, report
    assert "outside the protected workspace" in denied[0]["denied_reason"]
    assert denied[0]["execution"] is None


def test_workspace_registry_lists_initialized_workspaces(tmp_path, monkeypatch, capsys):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    ws_a = tmp_path / "ws_a"
    ws_b = tmp_path / "ws_b"
    ws_a.mkdir()
    ws_b.mkdir()
    assert cli.main(["init", "--workspace", str(ws_a), "--yes"]) == 0
    assert cli.main(["init", "--workspace", str(ws_b), "--yes"]) == 0
    capsys.readouterr()
    assert cli.main(["workspace"]) == 0
    out = capsys.readouterr().out
    assert str(ws_a.resolve()) in out
    assert str(ws_b.resolve()) in out


def test_ui_serves_external_app_js_without_inline_scripts(tmp_path):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from tanuq import web
    from tanuq.config import read_local_token

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    web.SERVICE = web.WorkspaceService(
        load_environment(ws), read_local_token()
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/app.js", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            assert "Tanuq control-plane" in body
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert "app.js" in html
            assert "<script>" not in html
    finally:
        server.shutdown()
        server.server_close()


def _operations(env, **kwargs):
    from tanuq.evidence import operations
    return operations(env, **kwargs)


def test_operations_projection_full_high_chain(env):
    target = env.workspace / "demo.txt"
    proposal = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }, session="ops-high")["proposals"][0]
    agent_adapter.approve(env, proposal["fingerprint"])
    agent_adapter.execute(env, proposal["fingerprint"])

    report = _operations(env, fingerprint=proposal["fingerprint"])
    assert report["count"] == 1
    op = report["operations"][0]
    assert op["state"] == "VERIFIED"
    assert op["outcome"] == "VERIFIED"
    assert op["fingerprint"] == proposal["fingerprint"]
    assert op["proposal"]["reason"] == "cli apply"
    assert op["risk"]["risk"] == "HIGH"
    assert op["approvals"][0]["status"] == "applied"
    assert op["execution"]["terminal"] == "VERIFIED"
    assert "ops-high" in op["sessions"]
    assert op["incidents"] == []
    assert op["evidence_refs"]["events"] >= 5
    dumped = json.dumps(report)
    assert "sk-test-aaaaaaaaaaaaaaaa" not in dumped
    assert "old_content" not in dumped


def test_operations_pending_and_denied_states(env):
    high = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })["proposals"][0]
    outside = env.workspace.parent / "ops-outside.txt"
    outside.write_text("hello", encoding="utf-8", newline="")
    denied = _propose(env, {
        "path": str(outside), "old_content": "hello",
        "new_content": "x", "reason": "escape",
    })

    report = _operations(env)
    states = {c["fingerprint"]: c["state"] for c in report["operations"]}
    assert states[high["fingerprint"]] == "PENDING_APPROVAL"
    denied_fp = denied["proposals"][0]["fingerprint"]
    assert states[denied_fp] == "DENIED"
    denied_op = [o for o in report["operations"]
                 if o["fingerprint"] == denied_fp][0]
    assert "outside the protected workspace" in denied_op["denied_reason"]
    assert denied_op["execution"] is None


def test_operations_approved_state_before_execution(env):
    proposal = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })["proposals"][0]
    agent_adapter.approve(env, proposal["fingerprint"])
    report = _operations(env, fingerprint=proposal["fingerprint"])
    assert report["operations"][0]["state"] == "APPROVED"


def test_history_json_and_operation_selector(env, capsys):
    target = env.workspace / "demo.txt"
    first = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello v1", "reason": "first",
    }, session="hist-a")["proposals"][0]
    agent_adapter.execute(env, fingerprint=first["fingerprint"])
    capsys.readouterr()  # drain fixture/banner output captured so far
    assert cli.main(["history", "--workspace", str(env.workspace),
                     "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["count"] >= 1
    assert report["operations"][0]["state"] == "VERIFIED"
    op_id = report["operations"][0]["operation_id"]
    capsys.readouterr()
    assert cli.main(["history", "--workspace", str(env.workspace),
                     "--operation", op_id[:8], "--json"]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["count"] == 1
    assert selected["operations"][0]["operation_id"] == op_id


def test_pending_command_lists_governance_detail(env, capsys):
    _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }, session="pend-check")
    capsys.readouterr()  # drain fixture/banner output captured so far
    assert cli.main(["pending", "--workspace", str(env.workspace),
                     "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["count"] == 1
    row = report["pending"][0]
    assert row["risk"] == "HIGH"
    assert row["approval_required"] is True
    assert row["session"] == "pend-check"
    assert row["signals"]
    assert "sk-test-aaaaaaaaaaaaaaaa" not in json.dumps(row)


def test_three_agent_concurrent_lifecycle_no_cross(env, tmp_path):
    ws = env.workspace
    runner = tmp_path / "op_race.py"
    runner.write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, r\"{repo}\")\n"
        "from tanuq.pending import save_pending\n"
        "from simulation.agent.worker.patch_proposal import PatchProposal\n"
        "ws = Path(sys.argv[1])\n"
        "idx = sys.argv[2]\n"
        "patch = PatchProposal(\n"
        "    path=str(ws / ('agent_' + idx + '.py')),\n"
        "    action='modify', reason='agent ' + idx,\n"
        "    old_content='a', new_content='b' + idx,\n"
        "    allowed_paths=(str(ws),),\n"
        ")\n"
        "save_pending(ws, [patch])\n".format(repo=str(REPO)),
        encoding="utf-8",
    )
    workers = [
        subprocess.Popen(
            [sys.executable, str(runner), str(ws), str(i)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for i in range(3)
    ]
    for w in workers:
        out, err = w.communicate(timeout=60)
        assert w.returncode == 0, err

    records = load_pending(ws)
    fingerprints = sorted(r["fingerprint"] for r in records)
    assert len(records) == 3
    assert len(set(fingerprints)) == 3

    for fp in fingerprints:
        rec = [r for r in records if r["fingerprint"] == fp][0]
        (ws / Path(rec["path"]).name).write_text(
            "a", encoding="utf-8", newline=""
        )
        done = agent_adapter.execute(env, fingerprint=fp)
        assert done["terminal"] == "VERIFIED", done
    report = _operations(env)
    agent_ops = [
        o for o in report["operations"]
        if Path(o["path"]).name.startswith("agent_")
    ]
    assert len(agent_ops) == 3
    assert {o["state"] for o in agent_ops} == {"VERIFIED"}
    assert len({o["fingerprint"] for o in agent_ops}) == 3
    for op in agent_ops:
        assert op["approvals"] == []  # LOW risk: no approvals to cross
        assert op["incidents"] == []


def test_high_approval_cannot_cross_between_operations(env):
    # Two DIFFERENT pending proposals, both valid against the same disk
    # state; an approval for one must never authorize the other.
    first = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })["proposals"][0]
    second = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-other-bbbbbbbbbbbbbbbb"\n',
        "reason": "cli apply other",
    })["proposals"][0]
    assert first["fingerprint"] != second["fingerprint"]
    agent_adapter.approve(env, first["fingerprint"])
    crossed = agent_adapter.execute(env, fingerprint=second["fingerprint"])
    assert crossed["terminal"] == "DENIED"
    assert crossed["failure_stage"] == "approval"
    done = agent_adapter.execute(env, fingerprint=first["fingerprint"])
    assert done["terminal"] == "VERIFIED"
    states = {
        o["fingerprint"]: o["state"]
        for o in _operations(env)["operations"]
    }
    assert states[first["fingerprint"]] == "VERIFIED"
    assert states[second["fingerprint"]] == "PENDING_APPROVAL"


def test_crash_restart_operation_incident_link(env):
    from simulation.agent.worker.patch_proposal import PatchProposal
    target = env.workspace / "demo.txt"
    patch = PatchProposal(
        path=str(target), action="modify", reason="crash ops",
        old_content="hello", new_content="hello crashed",
        allowed_paths=tuple(env.config.allowed_paths),
    )
    intent_id = env.apply_journal.record_intent(patch, attempt=1)
    env.apply_journal.record_apply_started(intent_id, reason="crash ops")

    report = _operations(env)
    op = [o for o in report["operations"]
          if o["operation_id"] == intent_id][0]
    assert op["state"] == "INCIDENT"
    assert "crashed_during_apply" in op["incidents"]
    assert op["execution"]["terminal"] == "APPLY_STARTED"
    reopened = load_environment(env.workspace)
    after = _operations(reopened, operation_id=intent_id)
    assert after["count"] == 1
    assert after["operations"][0]["incidents"] == ["crashed_during_apply"]
