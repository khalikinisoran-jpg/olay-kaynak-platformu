"""Tanuq OperationCoordinator facade tests (Phase: control plane).

The coordinator is a stateless delegation layer: every method must be
parity-equivalent with the underlying projection functions and must
never invent lifecycle/risk/approval state. These tests pin that
contract.
"""
import json

import pytest

from tanuq import agent_adapter, cli
from tanuq.config import init_workspace, tanuq_data_dir
from tanuq.coordinator import OperationCoordinator
from tanuq.evidence import export_evidence, operations
from tanuq.incidents import collect_incidents
from tanuq.runtime import load_environment


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


@pytest.fixture
def coord(env):
    return OperationCoordinator(env)


def _run_high_flow(env):
    target = env.workspace / "demo.txt"
    proposal = agent_adapter.propose(env, json.dumps({
        "path": str(target), "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }), session="coord-test")["proposals"][0]
    agent_adapter.approve(env, proposal["fingerprint"])
    agent_adapter.execute(env, proposal["fingerprint"])
    return proposal


def test_operations_parity_with_direct_projection(env, coord):
    _run_high_flow(env)
    direct = operations(env, fingerprint=None, limit=None)
    via_coord = coord.operations()
    assert via_coord["count"] == direct["count"]
    assert via_coord["operations"] == direct["operations"]


def test_lineage_and_incidents_parity(env, coord):
    _run_high_flow(env)
    assert coord.lineage()["chains"] == lineage_direct(env)["chains"]
    coord_report = coord.incidents()
    direct_report = collect_incidents(env)
    assert coord_report["incidents"] == direct_report["incidents"]
    assert coord_report["total"] == direct_report["total"]


def lineage_direct(env):
    from tanuq.evidence import lineage
    return lineage(env)


def test_export_parity_and_secret_safety(env, coord):
    _run_high_flow(env)
    bundle = coord.export()
    direct = export_evidence(env)
    # generated_at is the only call-time field; everything else must be
    # byte-identical between the facade and the direct projection.
    bundle.pop("generated_at")
    direct.pop("generated_at")
    assert bundle == direct
    assert bundle["product"] == "TANUQ"
    assert bundle["evidence"]["chain_valid"] is True
    dumped = json.dumps(bundle)
    assert "sk-test-aaaaaaaaaaaaaaaa" not in dumped
    assert "old_content" not in dumped and "new_content" not in dumped


def test_get_operation_by_full_id_prefix_and_fingerprint(env, coord):
    proposal = _run_high_flow(env)
    report = coord.operations(fingerprint=proposal["fingerprint"])
    op = report["operations"][0]
    full_id = op["operation_id"]

    by_id = coord.get_operation(full_id)
    assert by_id is not None
    assert by_id["operation_id"] == full_id

    by_prefix = coord.get_operation(full_id[:8])
    assert by_prefix["operation_id"] == full_id

    by_fingerprint = coord.get_operation(proposal["fingerprint"])
    assert by_fingerprint["fingerprint"] == proposal["fingerprint"]

    by_fp_prefix = coord.get_operation(proposal["fingerprint"][:12])
    assert by_fp_prefix["fingerprint"] == proposal["fingerprint"]

    assert coord.get_operation("ffffffffffff") is None


def test_incident_link_preserved_through_coordinator(env, coord):
    from simulation.agent.worker.patch_proposal import PatchProposal
    target = env.workspace / "demo.txt"
    patch = PatchProposal(
        path=str(target), action="modify", reason="crash coord",
        old_content="hello", new_content="hello crashed",
        allowed_paths=tuple(env.config.allowed_paths),
    )
    intent_id = env.apply_journal.record_intent(patch, attempt=1)
    env.apply_journal.record_apply_started(intent_id, reason="crash coord")

    report = coord.incidents()
    incident = [i for i in report["incidents"]
                if i["operation"] == intent_id][0]
    assert incident["type"] == "crashed_during_apply"
    assert incident["fingerprint"] == patch.fingerprint()

    op = coord.get_operation(intent_id)
    assert op["state"] == "INCIDENT"
    assert "crashed_during_apply" in op["incidents"]


def test_status_schema_is_stable(env, coord):
    status = coord.status()
    assert set(status.keys()) == {
        "workspace", "protected_scope", "governed", "verification_depth",
        "chain_valid", "anchor", "events", "pending", "limits",
    }
    assert status["governed"] is True
    assert status["anchor"] == "ACTIVE"
    assert status["limits"]["os_sandbox"] is False
    assert status["limits"]["network_enforcement"] is False


def test_coordinator_has_no_authority_surface(env, coord):
    from tanuq.pending import save_pending
    from simulation.agent.worker.patch_proposal import PatchProposal
    patch = PatchProposal(
        path=str(env.workspace / "demo.txt"), action="modify",
        reason="authority probe", old_content="hello",
        new_content="hello x", allowed_paths=tuple(env.config.allowed_paths),
    )
    save_pending(env.workspace, [patch])
    # Faz 2: execute() is a sanctioned DELEGATION to agent_adapter; it
    # must never become a direct grant/approve/consume/revoke/apply
    # authority surface.
    authority_methods = {
        name for name in dir(coord)
        if any(word in name.lower() for word in
               ("grant", "approve", "consume", "revoke", "apply",
                "write"))
    }
    assert not authority_methods
    # Pending store untouched by any coordinator call.
    coord.operations()
    coord.incidents()
    coord.status()
    assert len(load_pending_safe(env)) == 1
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"


def test_execute_delegates_without_bypassing_governance(env, coord):
    # HIGH proposal, no approval: the governed chain must deny exactly
    # as it does when agent_adapter is called directly.
    agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }), session="faz2")
    result = coord.execute()
    assert result["executed"] is True
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "approval"
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"


def test_execute_is_pure_delegation_of_arguments_and_result(
        env, coord, monkeypatch):
    import tanuq.agent_adapter as adapter_module
    calls = []
    sentinel = {"executed": True, "terminal": "SENTINEL", "passthrough": True}

    def fake_execute(env_arg, fingerprint=None, run_all=False, session=None):
        calls.append({
            "env_is_same": env_arg is env,
            "fingerprint": fingerprint,
            "run_all": run_all,
            "session": session,
        })
        return sentinel

    monkeypatch.setattr(adapter_module, "execute", fake_execute)
    result = coord.execute(
        fingerprint="abc123", run_all=False, session="s1"
    )
    assert result is sentinel
    assert calls == [{
        "env_is_same": True,
        "fingerprint": "abc123",
        "run_all": False,
        "session": "s1",
    }]


def test_execute_in_flight_lifecycle_success(env, coord, monkeypatch):
    import threading
    import tanuq.agent_adapter as adapter_module

    target = env.workspace / "demo.txt"
    agent_adapter.propose(env, json.dumps({
        "path": str(target), "old_content": "hello",
        "new_content": "hello v2", "reason": "faz2",
    }), session="inflight")

    real_execute = adapter_module.execute
    observed = {}

    def slow_execute(env_arg, fingerprint=None, run_all=False, session=None):
        snap = coord.in_flight()
        observed["during"] = {
            "count": snap["count"],
            "state": snap["in_flight"][0]["state"] if snap["in_flight"] else None,
            "session": snap["in_flight"][0].get("session") if snap["in_flight"] else None,
        }
        return real_execute(
            env_arg, fingerprint=fingerprint, run_all=run_all,
            session=session,
        )

    monkeypatch.setattr(adapter_module, "execute", slow_execute)
    result = coord.execute(session="inflight")

    assert result["terminal"] == "VERIFIED"
    assert observed["during"]["count"] == 1
    assert observed["during"]["state"] == "IN_FLIGHT"
    assert observed["during"]["session"] == "inflight"
    # terminal: RAM-only in-flight record cleared after completion
    assert coord.in_flight()["count"] == 0


def test_execute_in_flight_cleared_on_exception(env, coord, monkeypatch):
    import tanuq.agent_adapter as adapter_module

    def exploding_execute(env_arg, **kwargs):
        raise RuntimeError("simulated crash during orchestration")

    monkeypatch.setattr(adapter_module, "execute", exploding_execute)
    with pytest.raises(RuntimeError):
        coord.execute()
    # fail-closed bookkeeping: the RAM-only slot is cleared, nothing
    # is presented as durable reality afterwards
    assert coord.in_flight()["count"] == 0


def test_execute_concurrent_same_selector_is_deterministic(
        env, coord, monkeypatch):
    import threading
    import tanuq.agent_adapter as adapter_module

    target = env.workspace / "demo.txt"
    agent_adapter.propose(env, json.dumps({
        "path": str(target), "old_content": "hello",
        "new_content": "hello v3", "reason": "faz2",
    }), session="race")
    release = threading.Event()
    hold_started = threading.Event()

    def holding_execute(env_arg, **kwargs):
        hold_started.set()
        release.wait(timeout=5)
        # fake result: does NOT consume pending, so the follow-up
        # execute in this test can run the real chain
        return {"executed": True, "terminal": "VERIFIED", "fake": True}

    monkeypatch.setattr(adapter_module, "execute", holding_execute)
    holder = threading.Thread(
        target=lambda: coord.execute(),
        daemon=True,
    )
    holder.start()
    assert hold_started.wait(timeout=5)
    second = coord.execute()  # same implicit NEXT selector
    assert second["executed"] is False
    assert second["in_flight"] is True
    release.set()
    holder.join(timeout=10)
    # after the in-flight holder completes, execution works again
    result = coord.execute()
    assert result["terminal"] == "VERIFIED"
    assert coord.in_flight()["count"] == 0


def test_in_flight_never_persisted_to_disk(env, coord, monkeypatch):
    import threading
    import tanuq.agent_adapter as adapter_module

    data_dir = tanuq_data_dir(env.workspace)
    before = {p.name for p in data_dir.iterdir()}
    real_execute = adapter_module.execute
    release = threading.Event()
    hold_started = threading.Event()

    def holding_execute(env_arg, **kwargs):
        hold_started.set()
        hold = coord.in_flight()
        assert hold["count"] == 1
        release.wait(timeout=5)
        return real_execute(env_arg, **kwargs)

    monkeypatch.setattr(adapter_module, "execute", holding_execute)
    thread = threading.Thread(target=lambda: coord.execute(), daemon=True)
    thread.start()
    assert hold_started.wait(timeout=5)
    release.set()
    thread.join(timeout=30)
    after = {p.name for p in data_dir.iterdir()}
    assert after == before  # RAM-only: no new durable artifact


def load_pending_safe(env):
    from tanuq.pending import load_pending
    return load_pending(env.workspace)


def test_cli_uses_coordinator_surface(env, coord, capsys):
    _run_high_flow(env)
    capsys.readouterr()
    assert cli.main(["history", "--workspace", str(env.workspace),
                     "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    coord_ops = coord.operations()["operations"]
    assert report["operations"] == coord_ops
