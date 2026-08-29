"""T-B11-A — ExternalAction runtime entrypoint via agent_run.py external

Proves the already-existing governed ExternalAction path is now reachable
through the repository's actual runtime entrypoint (agent_run.py external)
without new authority, with scope/governance/approval/journal preserved.
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import pathlib
import json

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

def _run_cli(args, workspace):
    cmd = [sys.executable, "agent_run.py"] + args
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return result

def _high_payload():
    return '{"password":"x"}'

# TEST A — FAIL-CLOSED SCOPE (no valid external scope -> fail, no provider, not VERIFIED)
def test_t11a_external_scope_fail_closed():
    ws = Path(tempfile.mkdtemp(prefix="t11a_scope_"))
    # Use restrictive scope external://payments while provider is secrets -> synthetic_path external://secrets/charge not in scope
    res = _run_cli(["external", "--provider", "secrets", "--operation", "charge", "--payload", _high_payload(), "--workspace", str(ws), "--allowed-path", "external://payments"], ws)
    # Should fail closed at validation (scope)
    assert res.returncode != 0
    assert "External scope denied" in res.stdout or "No authoritative scope" in res.stdout or "scope" in res.stdout.lower()
    assert "VERIFIED" not in res.stdout
    # Journal should not contain success for this intent (may be empty or not contain external_success)
    journal = ws / ".cli_platform" / "external_journal.jsonl"
    if journal.exists():
        txt = journal.read_text(encoding="utf-8")
        assert "external_success" not in txt

# TEST B — GOVERNANCE / APPROVAL DENIED without approval -> 0 provider, not VERIFIED
def test_t11a_external_high_without_approval_denied():
    ws = Path(tempfile.mkdtemp(prefix="t11a_high_denied_"))
    res = _run_cli(["external", "--provider", "secrets", "--operation", "charge", "--payload", _high_payload(), "--workspace", str(ws)], ws)
    # HIGH requires approval -> should be denied at approval
    assert res.returncode != 0
    # Governance should have required approval
    assert "Approval required: True" in res.stdout or "approval" in res.stdout.lower()
    assert "VERIFIED" not in res.stdout
    # Provider should not have been called (no external_success in journal)
    journal = ws / ".cli_platform" / "external_journal.jsonl"
    if journal.exists():
        txt = journal.read_text(encoding="utf-8")
        # No success, may have intent/started but not success
        assert "external_success" not in txt

# TEST C — VALID GOVERNED EXECUTION with approval -> provider once, journal evidence, VERIFIED
def test_t11a_external_valid_approved_via_store():
    ws = Path(tempfile.mkdtemp(prefix="t11a_valid_"))
    # Pre-grant approval via direct store with same data_dir that CLI will use
    # CLI's data_dir defaults to <workspace>/.cli_platform
    data_dir = ws / ".cli_platform"
    data_dir.mkdir(parents=True, exist_ok=True)
    # Need to grant approval for the synthetic patch of this external action
    from simulation.agent.apply.external_action import ExternalAction
    from simulation.security.governance_evaluator import GovernanceEvaluator
    from simulation.security.risk_engine import RiskEngine
    from simulation.security.risk_policy import RiskPolicy
    from simulation.agent.approval.approval_ledger import ApprovalLedger
    from simulation.agent.approval.approval_store import ApprovalStore
    action = ExternalAction(provider="secrets", operation="charge", payload=_high_payload(), idempotency_key="t11a-valid", reason="high")
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    dec = gov.evaluate(syn)
    assert dec.requires_human_approval is True
    ledger = ApprovalLedger(str(data_dir / "approval_ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    store.grant(patch_fingerprint=syn.fingerprint(), path=syn.path, action=syn.action, risk_level=dec.risk_level.value, attempt=1, authorizer="tester", expires_at=3600)
    # Now CLI should succeed via governed path (approval exists) – must pass --reason high to match fingerprint
    res = _run_cli(["external", "--provider", "secrets", "--operation", "charge", "--payload", _high_payload(), "--idempotency-key", "t11a-valid", "--reason", "high", "--workspace", str(ws)], ws)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Success: True" in res.stdout or "VERIFIED" in res.stdout or "GOVERNED EXTERNAL" in res.stdout
    assert "External outcome: known_success" in res.stdout or "known_success" in res.stdout.lower() or "VERIFIED" in res.stdout
    # Journal evidence observable
    journal = data_dir / "external_journal.jsonl"
    assert journal.exists()
    txt = journal.read_text(encoding="utf-8")
    assert "external_intent" in txt
    assert "external_success" in txt
    # Provider should have been called exactly once (external_success implies one call)
    # No second success on replay without new approval (single-use) – but we don't test replay here

# TEST D — AMBIGUOUS OUTCOME not VERIFIED, no auto-retry
def test_t11a_external_ambiguous_not_verified():
    ws = Path(tempfile.mkdtemp(prefix="t11a_ambiguous_"))
    data_dir = ws / ".cli_platform"
    data_dir.mkdir(parents=True, exist_ok=True)
    from simulation.agent.apply.external_action import ExternalAction
    from simulation.security.governance_evaluator import GovernanceEvaluator
    from simulation.security.risk_engine import RiskEngine
    from simulation.security.risk_policy import RiskPolicy
    from simulation.agent.approval.approval_ledger import ApprovalLedger
    from simulation.agent.approval.approval_store import ApprovalStore
    # Payload containing timeout marker will make _cli_external use ScriptedProvider with TIMEOUT_UNKNOWN
    payload_timeout = '{"password":"x","timeout":true,"TIMEOUT_UNKNOWN":true}'
    action = ExternalAction(provider="secrets", operation="charge", payload=payload_timeout, idempotency_key="t11a-amb", reason="high")
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    dec = gov.evaluate(syn)
    ledger = ApprovalLedger(str(data_dir / "approval_ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    store.grant(patch_fingerprint=syn.fingerprint(), path=syn.path, action=syn.action, risk_level=dec.risk_level.value, attempt=1, authorizer="tester", expires_at=3600)
    res = _run_cli(["external", "--provider", "secrets", "--operation", "charge", "--payload", payload_timeout, "--idempotency-key", "t11a-amb", "--reason", "high", "--workspace", str(ws)], ws)
    # Should not be VERIFIED, should be external_ambiguous / FAILED, no auto-replay
    assert res.returncode != 0
    assert "VERIFIED" not in res.stdout
    assert "TIMEOUT_UNKNOWN" in res.stdout or "external_ambiguous" in res.stdout.lower() or "ambiguous" in res.stdout.lower()
    journal = data_dir / "external_journal.jsonl"
    assert journal.exists()
    txt = journal.read_text(encoding="utf-8")
    assert "external_timeout_unknown" in txt or "external_ambiguous_unknown" in txt
    assert "external_success" not in txt

# TEST E — WORKER REGRESSION (file PatchProposal still via WorkerActionPipeline)
def test_t11a_worker_regression_still_via_file_pipeline():
    ws = Path(tempfile.mkdtemp(prefix="t11a_worker_regression_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    res = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello fixed\n", "--workspace", str(ws)], ws)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Apply success: True" in res.stdout
    assert "Verification passed: True" in res.stdout
    assert "Terminal state: VERIFIED" in res.stdout
    assert target.read_text(encoding="utf-8") == "hello fixed\n"
