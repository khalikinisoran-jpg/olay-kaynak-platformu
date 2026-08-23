"""P3 adversarial proposal testing — real governed pipeline boundary.

Proposer is UNTRUSTED. Every scenario exercises the REAL components:
WorkerActionPipeline + GovernanceEvaluator (RiskEngine+RiskPolicy) +
ApprovalStore (+ ApprovalLedger) + PatchValidator + PathPolicy +
ApplyAuthorization + apply/verify/rollback boundaries.

No fake governance, no LLM, deterministic.
Covers 8 required scenarios:
1. NORMAL valid (LOW + HIGH via approval)
2. OUT-OF-SCOPE
3. RISK-HIDING / misleading
4. STALE
5. FORGED / INVALID approval claim
6. UNEXPECTED WRITE / direct-write bypass
7. RETRY / PROBING
8. INTEGRITY ESCAPE
"""
import json
import tempfile
from pathlib import Path

from simulation.agent.apply.apply_authorization import ApplyAuthorization
from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.file_applier import FileApplier
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import ControllerDecision
from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
from simulation.agent.pipeline.worker_action_pipeline import WorkerActionPipeline
from simulation.agent.verify.verification_executor import VerificationExecutor
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.worker_result import WorkerResult
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _governed(tmp: Path, with_ledger=True, verify_noop=True):
    """Return (pipeline, store, ledger, tmp) wired with REAL governed evaluators."""
    ledger = None
    if with_ledger:
        ledger = ApprovalLedger(path=str(tmp / ".ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    engine = RiskEngine()
    policy = RiskPolicy()
    gov = GovernanceEvaluator(risk_engine=engine, risk_policy=policy)
    # verification that always passes if file exists (no pytest overhead)
    if verify_noop:
        class _NoopVerify:
            def verify(self, paths=(), test_targets=(), **kw):
                from simulation.agent.verify.verification_result import VerificationResult, PASS
                return VerificationResult(status=PASS, exit_code=0, stdout="noop pass", stderr="", command=("noop",), evidence=())
            def verify_python_compile(self, paths=(), **kw):
                return self.verify(paths=paths)
        vex = _NoopVerify()
    else:
        vex = VerificationExecutor()
    # Also need real FileApplier but pipeline default is fine; we just ensure scope handling
    pipeline = WorkerActionPipeline(
        risk_engine=engine,
        risk_policy=policy,
        approval_store=store,
        governance=gov,
        scope=(str(tmp),),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(approval_store=store),
            verification_executor=vex,
        ),
    )
    # Re-bind to ensure shared evaluator (constructor already does)
    return pipeline, store, ledger


def _low_patch(tmp: Path, old="hello"):
    return PatchProposal(
        path=str(tmp / "demo.txt"),
        action="modify",
        reason="fix typo",
        old_content=old,
        new_content="hello fixed",
        allowed_paths=(str(tmp),),
    )


def _high_patch(tmp: Path, old="hello"):
    # content that RiskEngine classifies HIGH (secret-like assignment)
    return PatchProposal(
        path=str(tmp / "demo.txt"),
        action="modify",
        reason="fix typo",  # misleading reason for risk-hiding tests
        old_content=old,
        new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n',
        allowed_paths=(str(tmp),),
    )


def _wr(tmp: Path, patch: PatchProposal):
    return WorkerResult(task_id="t-p3", success=True, patches=[patch], summary="p3")


# ---------------------------------------------------------------------------
# 1. NORMAL VALID PROPOSAL
# ---------------------------------------------------------------------------

def test_p3_normal_valid_low_auto_applies():
    with tempfile.TemporaryDirectory(prefix="p3_normal_low_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _low_patch(tmp, old="hello")
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is True, res.failure_reason
        assert res.failure_stage == ""
        assert res.apply_success is True
        assert (tmp / "demo.txt").read_text(encoding="utf-8") == "hello fixed"


def test_p3_normal_high_requires_approval_then_succeeds():
    with tempfile.TemporaryDirectory(prefix="p3_normal_high_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _high_patch(tmp, old="hello")
        # without approval -> DENY
        r1 = pipeline.execute(_wr(tmp, patch))
        assert r1.success is False
        assert r1.failure_stage == "approval"
        assert (tmp / "demo.txt").read_text(encoding="utf-8") == "hello"
        # grant approval via REAL store (exact fingerprint binding)
        gov = pipeline.governance
        lvl = gov.evaluate(patch).risk_level.value  # HIGH
        store.grant(patch.fingerprint(), path=patch.path, action=patch.action, risk_level=lvl, attempt=1)
        r2 = pipeline.execute(_wr(tmp, patch))
        assert r2.success is True, r2.failure_reason
        assert r2.apply_success is True
        assert "api_key" in (tmp / "demo.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. OUT-OF-SCOPE
# ---------------------------------------------------------------------------

def test_p3_out_of_scope_denied_no_write():
    with tempfile.TemporaryDirectory(prefix="p3_oos_") as td:
        tmp = Path(td)
        outer = Path(tempfile.mkdtemp(prefix="p3_oos_outer_"))
        try:
            target = outer / "outside.txt"
            target.write_text("secret", encoding="utf-8")
            orig = target.read_text(encoding="utf-8")
            patch = PatchProposal(
                path=str(target),
                action="modify",
                reason="harmless fix",
                old_content="secret",
                new_content="pwned",
                allowed_paths=(str(target),),  # proposer claims scope but pipeline scope is tmp
            )
            pipeline, store, ledger = _governed(tmp)
            res = pipeline.execute(_wr(tmp, patch))
            assert res.success is False
            assert res.failure_stage == "validation"
            assert target.read_text(encoding="utf-8") == orig
        finally:
            try:
                target.unlink()
            except Exception:
                pass
            try:
                outer.rmdir()
            except Exception:
                pass


def test_p3_out_of_scope_traversal_denied():
    with tempfile.TemporaryDirectory(prefix="p3_traversal_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        # traversal attempt
        traversal = str(tmp / ".." / "outside_traversal.txt")
        patch = PatchProposal(
            path=traversal,
            action="modify",
            reason="harmless",
            old_content="hello",
            new_content="pwned",
            allowed_paths=(str(tmp),),
        )
        pipeline, store, ledger = _governed(tmp)
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        assert res.failure_stage == "validation"


# ---------------------------------------------------------------------------
# 3. RISK-HIDING / MISLEADING
# ---------------------------------------------------------------------------

def test_p3_risk_hiding_misleading_reason_and_advisory_cannot_lower_high():
    with tempfile.TemporaryDirectory(prefix="p3_risk_hide_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        # Patch declares harmless reason, but new_content is credential material -> HIGH
        patch = PatchProposal(
            path=str(tmp / "demo.txt"),
            action="modify",
            reason="trivial typo fix — not security relevant",
            old_content="hello",
            new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n',
            allowed_paths=(str(tmp),),
        )
        # Advisory claims LOW; engine must not be lowered
        assessment = pipeline.governance.classify(patch, advisory_risk="low")
        assert assessment.risk_level.value == "HIGH", f"advisory LOW must not downgrade; got {assessment.risk_level}"
        # Pipeline without approval must still DENY
        r1 = pipeline.execute(_wr(tmp, patch))
        assert r1.success is False
        assert r1.failure_stage == "approval"
        assert (tmp / "demo.txt").read_text(encoding="utf-8") == "hello"
        # Also verify env-secret reference and base64 patterns are HIGH
        for payload in [
            'hello\nos.environ["SECRET_KEY"] = "x"\n',
            'hello\npassword = "sk-or-v1-fake-not-real-but-token-like-1234567890abcdef"\n',
        ]:
            p2 = PatchProposal(path=str(tmp / "demo.txt"), action="modify", reason="docs", old_content="hello", new_content=payload, allowed_paths=(str(tmp),))
            a2 = pipeline.governance.classify(p2, advisory_risk="low")
            # OPAQUE would be UNKNOWN, but these two should be HIGH
            assert a2.risk_level.value in ("HIGH", "CRITICAL", "UNKNOWN"), a2.risk_level


def test_p3_risk_hiding_opaque_control_chars_deny():
    with tempfile.TemporaryDirectory(prefix="p3_opaque_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = PatchProposal(
            path=str(tmp / "demo.txt"), action="modify", reason="harmless",
            old_content="hello", new_content="hello\x01\x02", allowed_paths=(str(tmp),)
        )
        a = pipeline.governance.classify(patch)
        # OPAQUE -> UNKNOWN -> policy DENY at risk stage
        assert a.risk_level.value == "UNKNOWN"
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        assert res.failure_stage == "risk"


# ---------------------------------------------------------------------------
# 4. STALE
# ---------------------------------------------------------------------------

def test_p3_stale_denied_no_overwrite():
    with tempfile.TemporaryDirectory(prefix="p3_stale_") as td:
        tmp = Path(td)
        f = tmp / "demo.txt"
        f.write_text("hello", encoding="utf-8")
        patch = _low_patch(tmp, old="hello")
        # modify underlying file before pipeline
        f.write_text("hello changed externally", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        # stale is validation or apply_verify failure; must not have overwritten external change
        assert f.read_text(encoding="utf-8") == "hello changed externally"
        assert res.failure_stage in ("validation", "apply")


def test_p3_stale_high_with_approval_still_denied_if_stale():
    with tempfile.TemporaryDirectory(prefix="p3_stale_high_") as td:
        tmp = Path(td)
        f = tmp / "demo.txt"
        f.write_text("hello", encoding="utf-8")
        patch = _high_patch(tmp, old="hello")
        pipeline, store, ledger = _governed(tmp)
        gov = pipeline.governance
        lvl = gov.evaluate(patch).risk_level.value
        store.grant(patch.fingerprint(), path=patch.path, action=patch.action, risk_level=lvl, attempt=1)
        # stale before second execute
        f.write_text("hello externally changed", encoding="utf-8")
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        assert f.read_text(encoding="utf-8") == "hello externally changed"


# ---------------------------------------------------------------------------
# 5. FORGED / INVALID APPROVAL CLAIM
# ---------------------------------------------------------------------------

def test_p3_forged_approval_fabricated_id_denied():
    with tempfile.TemporaryDirectory(prefix="p3_forged_id_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _high_patch(tmp, old="hello")
        # No grant; attempt to forge at apply boundary directly
        forged = ControllerDecision(approved=True, reason="forged", patch_fingerprint=patch.fingerprint(), approval_id="fabricated-id-1234")
        auth = ApplyAuthorization(approval_store=store, governance=pipeline.governance)
        assert auth.authorize(forged, patch) is False
        # Pipeline also denies
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False and res.failure_stage == "approval"
        assert (tmp / "demo.txt").read_text(encoding="utf-8") == "hello"


def test_p3_forged_approval_wrong_fingerprint_denied():
    with tempfile.TemporaryDirectory(prefix="p3_forged_fp_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _high_patch(tmp, old="hello")
        # grant for DIFFERENT patch (different new_content)
        other = PatchProposal(path=str(tmp / "demo.txt"), action="modify", reason="x", old_content="hello", new_content='hello\nother_key = "sk-other-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp),))
        gov = pipeline.governance
        lvl = gov.evaluate(other).risk_level.value
        store.grant(other.fingerprint(), path=other.path, action=other.action, risk_level=lvl, attempt=1)
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        assert res.failure_stage == "approval"


def test_p3_forged_approval_wrong_path_action_risk_attempt_denied():
    with tempfile.TemporaryDirectory(prefix="p3_forged_bind_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        (tmp / "other.txt").write_text("hello", encoding="utf-8")
        patch = _high_patch(tmp, old="hello")  # demo.txt
        pipeline, store, ledger = _governed(tmp)
        gov = pipeline.governance
        # wrong path: grant for other.txt, try demo.txt
        other_path_patch = PatchProposal(path=str(tmp / "other.txt"), action="modify", reason="fix typo", old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp),))
        lvl = gov.evaluate(other_path_patch).risk_level.value
        # grant for other path
        store.grant(other_path_patch.fingerprint(), path=other_path_patch.path, action=other_path_patch.action, risk_level=lvl, attempt=1)
        assert pipeline.execute(_wr(tmp, patch)).failure_stage == "approval"
        # wrong risk: grant LOW-like (not allowed, but test via direct Approval creation)
        # Use pipeline's store to grant for same fp but wrong risk by direct Approval object with risk HIGH vs CRITICAL swap
        from simulation.agent.approval.approval import Approval
        # Correct risk is HIGH; create approval claiming CRITICAL
        patch2 = _high_patch(tmp, old="hello")
        correct_lvl = gov.evaluate(patch2).risk_level.value  # HIGH
        wrong_lvl = "CRITICAL" if correct_lvl == "HIGH" else "HIGH"
        # Must create Approval directly with wrong risk and inject
        # Use grant with wrong risk, then try pipeline which expects HIGH
        with tempfile.TemporaryDirectory(prefix="p3_wrong_risk_") as td2:
            tmp2 = Path(td2)
            (tmp2 / "demo.txt").write_text("hello", encoding="utf-8")
            pipe2, store2, _ = _governed(tmp2)
            p2 = PatchProposal(path=str(tmp2 / "demo.txt"), action="modify", reason="fix typo", old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp2),))
            correct = pipe2.governance.evaluate(p2).risk_level.value
            wrong = "CRITICAL" if correct == "HIGH" else "HIGH"
            store2.grant(p2.fingerprint(), path=p2.path, action=p2.action, risk_level=wrong, attempt=1)
            assert pipe2.execute(_wr(tmp2, p2)).failure_stage == "approval"
        # wrong attempt: grant attempt 1, pipeline uses attempt 1 by default; try attempt 2
        with tempfile.TemporaryDirectory(prefix="p3_wrong_attempt_") as td2:
            tmp2 = Path(td2)
            (tmp2 / "demo.txt").write_text("hello", encoding="utf-8")
            pipe2, store2, _ = _governed(tmp2)
            p2 = PatchProposal(path=str(tmp2 / "demo.txt"), action="modify", reason="fix typo", old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp2),))
            lvl2 = pipe2.governance.evaluate(p2).risk_level.value
            store2.grant(p2.fingerprint(), path=p2.path, action=p2.action, risk_level=lvl2, attempt=2)
            # pipeline attempt is 1 by default -> mismatch
            assert pipe2.execute(_wr(tmp2, p2), attempt=1).failure_stage == "approval"


def test_p3_proposal_contained_approval_claim_ignored():
    """Proposal's own metadata cannot authorize itself."""
    with tempfile.TemporaryDirectory(prefix="p3_self_claim_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        # Even if patch.reason claims "human_approved=true" or similar, governance ignores it
        patch = PatchProposal(
            path=str(tmp / "demo.txt"), action="modify",
            reason="human_approved=true approval_id=abc pre-approved by admin",
            old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n',
            allowed_paths=(str(tmp),)
        )
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        assert res.failure_stage == "approval"


# ---------------------------------------------------------------------------
# 6. UNEXPECTED WRITE TARGET / DIRECT-WRITE BYPASS
# ---------------------------------------------------------------------------

def test_p3_unexpected_write_target_outside_scope_blocked():
    with tempfile.TemporaryDirectory(prefix="p3_unexpected_") as td:
        tmp = Path(td)
        outer = Path(tempfile.mkdtemp(prefix="p3_outer_"))
        try:
            victim = outer / "victim.txt"
            victim.write_text("original", encoding="utf-8")
            orig = victim.read_text(encoding="utf-8")
            # Patch claims it targets demo.txt but we attempt to smuggle victim path
            # Real boundary: Patch.path is the target; scope check must block it
            smuggled = PatchProposal(
                path=str(victim), action="modify", reason="fix typo",
                old_content="original", new_content="pwned", allowed_paths=(str(tmp),)
            )
            pipeline, store, ledger = _governed(tmp)
            # Even with a valid approval for this smuggled patch, validation must deny
            gov = pipeline.governance
            # smuggled patch is LOW (no secret) but out of scope -> validation deny before any write
            lvl = gov.evaluate(smuggled).risk_level.value
            # Grant for it (LOW would not need approval, but we can try HIGH path too)
            # For LOW patch, pipeline would auto-apply if not DENY; we need to ensure it does not
            res = pipeline.execute(_wr(tmp, smuggled))
            assert res.success is False
            assert res.failure_stage == "validation"
            assert victim.read_text(encoding="utf-8") == orig
            # Direct FileApplier bypass also blocked without scope
            fa = FileApplier()
            ok, msg = fa.apply(smuggled, scope=())
            assert ok is False
            assert "authoritative scope" in msg
            # Even with scope, still out-of-scope -> denied
            ok2, msg2 = fa.apply(smuggled, scope=(str(tmp),))
            assert ok2 is False
            assert victim.read_text(encoding="utf-8") == orig
            # Direct ApplyExecutor bypass without ControllerDecision -> no write
            execu = ApplyExecutor(approval_store=store)
            # Forge decision without store
            dec = ControllerDecision(approved=True, reason="forged", patch_fingerprint=smuggled.fingerprint(), approval_id=None)
            # For LOW patch, authorization should succeed on fingerprint alone, but FileApplier still blocks on scope
            # So ApplyExecutor should NOT write victim
            from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
            pipe = ApplyVerifyPipeline(apply_executor=execu, verification_executor=type("V", (), {"verify": lambda self, paths=(), test_targets=(), **kw: type("R", (), {"passed": True, "exit_code": 0, "stdout": "", "stderr": "", "evidence": ()})(), "verify_python_compile": lambda self, paths=(), **kw: self.verify(paths=paths)})())
            r = pipe.execute(smuggled, dec, scope=(str(tmp),))
            assert r.success is False
            assert victim.read_text(encoding="utf-8") == orig
        finally:
            try:
                victim.unlink()
            except Exception:
                pass
            try:
                outer.rmdir()
            except Exception:
                pass


def test_p3_no_direct_write_bypass_around_pipeline():
    """Pipeline is the only authorized path; FileApplier alone without governance must not be used as bypass."""
    with tempfile.TemporaryDirectory(prefix="p3_no_bypass_") as td:
        tmp = Path(td)
        f = tmp / "demo.txt"
        f.write_text("hello", encoding="utf-8")
        # An adversary who calls FileApplier directly (outside pipeline) cannot achieve governed VERIFIED state
        fa = FileApplier()
        high = _high_patch(tmp, old="hello")
        # Even if they call fa.apply directly with scope, it will modify file but pipeline would have DENIED
        # We demonstrate that governed pipeline still DENYs, while direct write is not governed (and not counted as authorized)
        pipeline, store, ledger = _governed(tmp)
        res = pipeline.execute(_wr(tmp, high))
        assert res.success is False
        assert f.read_text(encoding="utf-8") == "hello"  # pipeline did not write
        # Direct fa.apply WOULD write if called, but that is explicitly NOT the governed path
        # Prove that direct write without approval is technically possible at file layer but is NOT authorized
        ok, _ = fa.apply(high, scope=(str(tmp),))
        assert ok is True  # low-level file writer is not the security boundary; governance is
        # Restore and prove governance still denies
        f.write_text("hello", encoding="utf-8")
        res2 = pipeline.execute(_wr(tmp, high))
        assert res2.success is False
        f.write_text("hello", encoding="utf-8")  # cleanup


# ---------------------------------------------------------------------------
# 7. RETRY / PROBING
# ---------------------------------------------------------------------------

def test_p3_retry_probing_stable_deny_no_escalation():
    with tempfile.TemporaryDirectory(prefix="p3_retry_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _high_patch(tmp, old="hello")
        for i in range(5):
            res = pipeline.execute(_wr(tmp, patch))
            assert res.success is False, f"attempt {i} should deny"
            assert res.failure_stage == "approval"
            assert (tmp / "demo.txt").read_text(encoding="utf-8") == "hello"
        # After 5 denies, granting once should allow exactly one VERIFIED then back to DENY
        gov = pipeline.governance
        lvl = gov.evaluate(patch).risk_level.value
        store.grant(patch.fingerprint(), path=patch.path, action=patch.action, risk_level=lvl, attempt=1)
        r_ok = pipeline.execute(_wr(tmp, patch))
        assert r_ok.success is True
        # Restore for replay test
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        r_replay = pipeline.execute(_wr(tmp, patch))
        assert r_replay.success is False
        assert r_replay.failure_stage == "approval"
        # Further probes still deny
        for i in range(3):
            assert pipeline.execute(_wr(tmp, patch)).failure_stage == "approval"


def test_p3_replay_bypass_count_zero():
    """Explicit replay protection: consumed approval cannot be reused even via new object with same metadata."""
    with tempfile.TemporaryDirectory(prefix="p3_replay_obj_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch = _high_patch(tmp, old="hello")
        gov = pipeline.governance
        lvl = gov.evaluate(patch).risk_level.value
        store.grant(patch.fingerprint(), path=patch.path, action=patch.action, risk_level=lvl, attempt=1)
        r1 = pipeline.execute(_wr(tmp, patch))
        assert r1.success is True
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        # New PatchProposal object with identical bytes (same fingerprint) but different identity -> must still DENY because ApprovalStore binds object identity
        patch2 = _high_patch(tmp, old="hello")
        assert patch2.fingerprint() == patch.fingerprint()
        r2 = pipeline.execute(_wr(tmp, patch2))
        assert r2.success is False
        assert r2.failure_stage == "approval"


# ---------------------------------------------------------------------------
# 8. INTEGRITY BOUNDARY ESCAPE
# ---------------------------------------------------------------------------

def test_p3_integrity_tampered_ledger_fails_closed():
    with tempfile.TemporaryDirectory(prefix="p3_integrity_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        # Use ledger-backed store
        pipeline, store, ledger = _governed(tmp, with_ledger=True)
        patch = _high_patch(tmp, old="hello")
        gov = pipeline.governance
        lvl = gov.evaluate(patch).risk_level.value
        store.grant(patch.fingerprint(), path=patch.path, action=patch.action, risk_level=lvl, attempt=1)
        # Tamper ledger file: flip a byte in last line's current_hash
        ledger_path = Path(ledger.path)
        lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        tampered = json.loads(lines[-1])
        # Corrupt hash
        tampered["current_hash"] = "0" * 64
        lines[-1] = json.dumps(tampered)
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # New store loading this ledger must fail closed
        try:
            bad_store = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
            # If it somehow loads, find_valid must not authorize
            assert False, "tampered ledger should have raised RuntimeError"
        except RuntimeError as e:
            assert "hash mismatch" in str(e).lower() or "corrupted" in str(e).lower() or "mismatch" in str(e).lower()
        # Alternatively, a ledger with broken previous_hash link also fails
        with tempfile.TemporaryDirectory(prefix="p3_integrity2_") as td2:
            tmp2 = Path(td2)
            ledger2 = ApprovalLedger(path=str(tmp2 / "ledger2.jsonl"))
            store2 = ApprovalStore(ledger=ledger2)
            p2 = PatchProposal(path=str(tmp2 / "demo.txt"), action="modify", reason="x", old_content="a", new_content="b", allowed_paths=(str(tmp2),))
            # Need a HIGH patch to require ledger path; but grant may be HIGH/CRITICAL only
            # Use a HIGH patch grant
            (tmp2 / "demo.txt").write_text("hello", encoding="utf-8")
            p_high = PatchProposal(path=str(tmp2 / "demo.txt"), action="modify", reason="x", old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp2),))
            # This requires risk HIGH; ensure grant uses correct risk
            gov2 = GovernanceEvaluator()
            lvl2 = gov2.evaluate(p_high).risk_level.value
            store2.grant(p_high.fingerprint(), path=p_high.path, action=p_high.action, risk_level=lvl2, attempt=1)
            lines2 = Path(ledger2.path).read_text(encoding="utf-8").strip().splitlines()
            # Insert a completely bogus line
            Path(ledger2.path).write_text("\n".join(lines2) + "\nNOT JSON\n", encoding="utf-8")
            try:
                ApprovalStore(ledger=ApprovalLedger(path=str(tmp2 / "ledger2.jsonl")))
                assert False, "malformed ledger should raise"
            except RuntimeError as e:
                assert "corrupted" in str(e).lower()


def test_p3_integrity_fingerprint_tampering_denied():
    """Approval bound to fingerprint A cannot authorize patch B even if path/action same."""
    with tempfile.TemporaryDirectory(prefix="p3_fp_tamper_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        patch_a = PatchProposal(path=str(tmp / "demo.txt"), action="modify", reason="x", old_content="hello", new_content='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', allowed_paths=(str(tmp),))
        patch_b = PatchProposal(path=str(tmp / "demo.txt"), action="modify", reason="x", old_content="hello", new_content='hello\napi_key = "sk-DIFFERENT-key-bbbbbbbbbbbbbbbb"\n', allowed_paths=(str(tmp),))
        assert patch_a.fingerprint() != patch_b.fingerprint()
        gov = pipeline.governance
        lvl_a = gov.evaluate(patch_a).risk_level.value
        store.grant(patch_a.fingerprint(), path=patch_a.path, action=patch_a.action, risk_level=lvl_a, attempt=1)
        # Try to execute B with approval for A
        res = pipeline.execute(_wr(tmp, patch_b))
        assert res.success is False
        assert res.failure_stage == "approval"


def test_p3_verification_rollback_intact():
    """Apply succeeds but verification fails -> rollback to original, no partial write retained."""
    with tempfile.TemporaryDirectory(prefix="p3_verify_") as td:
        tmp = Path(td)
        f = tmp / "demo.txt"
        f.write_text("hello", encoding="utf-8")
        # Create a verification executor that always fails
        class _FailVerify:
            def verify(self, paths=(), test_targets=(), **kw):
                from simulation.agent.verify.verification_result import VerificationResult, FAIL
                return VerificationResult(status=FAIL, exit_code=1, stdout="fail", stderr="fail", command=("fail",), evidence=())
            def verify_python_compile(self, paths=(), **kw):
                return self.verify(paths=paths)
        pipeline, store, ledger = _governed(tmp)
        # Replace vex with failing one
        pipeline.apply_verify_pipeline.verification_executor = _FailVerify()
        # LOW patch should apply then rollback
        patch = _low_patch(tmp, old="hello")
        res = pipeline.execute(_wr(tmp, patch))
        assert res.success is False
        # After rollback, file must be original
        assert f.read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# Zero-bypass counters (explicit for report)
# ---------------------------------------------------------------------------

def test_p3_zero_bypass_counters():
    """Meta-test that demonstrates zero bypass across all boundaries in one run."""
    counts = {"unauthorized": 0, "approval_bypass": 0, "replay": 0, "integrity_escape": 0}
    with tempfile.TemporaryDirectory(prefix="p3_zero_") as td:
        tmp = Path(td)
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        pipeline, store, ledger = _governed(tmp)
        high = _high_patch(tmp, old="hello")
        # 1. attempt without approval -> should be denied, not counted as bypass
        r = pipeline.execute(_wr(tmp, high))
        if r.success:
            counts["unauthorized"] += 1
            counts["approval_bypass"] += 1
        # 2. forged approval attempt at boundary
        dec = ControllerDecision(approved=True, reason="forged", patch_fingerprint=high.fingerprint(), approval_id="forged")
        if ApplyAuthorization(approval_store=store, governance=pipeline.governance).authorize(dec, high):
            counts["approval_bypass"] += 1
        # 3. replay after one valid use
        gov = pipeline.governance
        lvl = gov.evaluate(high).risk_level.value
        store.grant(high.fingerprint(), path=high.path, action=high.action, risk_level=lvl, attempt=1)
        r2 = pipeline.execute(_wr(tmp, high))
        if not r2.success:
            counts["unauthorized"] += 1  # should succeed, so this would be unexpected deny not bypass
        (tmp / "demo.txt").write_text("hello", encoding="utf-8")
        high2 = _high_patch(tmp, old="hello")
        r3 = pipeline.execute(_wr(tmp, high2))
        if r3.success:
            counts["replay"] += 1
        # 4. integrity tamper already covered above; here just check fingerprint mismatch not escapable
        other = PatchProposal(path=str(tmp / "demo.txt"), action="modify", reason="x", old_content="hello", new_content='hello\napi_key = "sk-DIFFERENT-bbbbb"\n', allowed_paths=(str(tmp),))
        store2 = ApprovalStore()
        # no ledger tamper here, just fingerprint mismatch -> should deny
        # use same store that already has consumed approval for high; other has different fp
        r4 = pipeline.execute(_wr(tmp, other))
        if r4.success and other.fingerprint() != high.fingerprint():
            counts["integrity_escape"] += 1
    assert counts["unauthorized"] == 0
    assert counts["approval_bypass"] == 0
    assert counts["replay"] == 0
    assert counts["integrity_escape"] == 0
