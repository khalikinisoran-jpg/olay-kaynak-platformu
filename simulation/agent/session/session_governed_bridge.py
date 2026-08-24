"""P9.4 SessionGovernedBridge — orchestration to existing WorkerActionPipeline, no authority.

Bridge is the ONLY place where AgentSession submits its proposal set to the
existing governed pipeline. It MUST NOT:
 - write files (no FileApplier)
 - grant approvals (no ApprovalStore.grant)
 - classify risk (no RiskEngine)
 - verify (no VerificationExecutor)
 - modify fingerprints

All governance remains via WorkerActionPipeline.
"""
from pathlib import Path
from typing import Tuple, Optional

from simulation.agent.session.agent_session import AgentSession, SessionState


class SessionGovernedBridge:
    """Thin bridge: AgentSession (PROPOSING) → WorkerActionPipeline → SessionState."""

    def resume(
        self,
        session: AgentSession,
        pipeline,
        verify_paths: Optional[Tuple[str, ...]] = None,
        test_targets: Tuple[str, ...] = (),
    ):
        """Explicit same-session resume from WAITING_APPROVAL via authoritative pipeline.

        Security boundary:
        - Session NEVER grants approval. External approval must already exist in ApprovalStore.
        - This method re-enters GOVERNING and calls existing WorkerActionPipeline.execute exactly once.
        - Same session identity, same WorkerResult/PatchProposal (preserved), same attempt (not incremented).
        - No direct FileApplier / ApprovalStore / RiskEngine / GovernanceEvaluator / VerificationExecutor calls.

        Preconditions:
         - session.state == WAITING_APPROVAL (fail-closed otherwise)
         - session.worker_result_ref must be set
        Transitions:
         WAITING_APPROVAL -> GOVERNING -> {VERIFIED, WAITING_APPROVAL, DENIED, FAILED}
        Returns WorkerPipelineResult (authoritative).
        Exactly one pipeline execution per call, no hidden retry.
        """
        if session.state != SessionState.WAITING_APPROVAL:
            raise ValueError(f"resume requires WAITING_APPROVAL, was {session.state.value}")
        if session.worker_result_ref is None:
            raise ValueError("session has no proposal attached (cannot resume)")
        # Record explicit resume evidence (advisory, never authority) — preserve attempt
        before_attempt = session.attempt
        before_psid = session.proposal_set_id
        if hasattr(session, "record_resume_requested"):
            session.record_resume_requested()
        else:
            # fallback advisory
            try:
                session.resume_count += 1  # type: ignore
            except Exception:
                pass
        # Delegate to existing governed execution (sole authority) — exactly one call
        result = self.execute(session, pipeline, verify_paths=verify_paths, test_targets=test_targets)
        # Post-condition: attempt and proposal identity must be preserved
        assert session.attempt == before_attempt, "resume must not mutate attempt (approval binding preserved)"
        assert session.proposal_set_id == before_psid, "resume must preserve same proposal"
        return result

    def execute(
        self,
        session: AgentSession,
        pipeline,
        verify_paths: Optional[Tuple[str, ...]] = None,
        test_targets: Tuple[str, ...] = (),
    ):
        """Submit session's proposal set to the existing governed pipeline.

        Preconditions:
         - session.state in (PROPOSING, WAITING_APPROVAL) — fail-closed otherwise
         - session.worker_result_ref must be set (untrusted proposal)
         - pipeline must be WorkerActionPipeline (or compatible with execute)

        Transitions:
         PROPOSING/WAITING_APPROVAL → GOVERNING → {WAITING_APPROVAL, DENIED, VERIFIED, FAILED}
        No hidden retry, no approval creation.

        Returns the WorkerPipelineResult (authoritative).
        """
        if session.state not in (SessionState.PROPOSING, SessionState.WAITING_APPROVAL):
            raise ValueError(f"session must be in PROPOSING or WAITING_APPROVAL to govern, was {session.state.value}")

        if session.worker_result_ref is None:
            session.transition_to(SessionState.FAILED, reason="no proposal attached")
            raise ValueError("session has no proposal attached")

        # Explicit transition to GOVERNING (fail-closed if invalid)
        session.transition_to(SessionState.GOVERNING)

        # Delegate to existing pipeline — sole authority
        # Use session.attempt for ApprovalStore attempt binding
        # and session.workspace for verify_paths if not provided
        worker_result = session.worker_result_ref
        vp = tuple(verify_paths) if verify_paths is not None else (str(session.workspace),)
        tt = tuple(test_targets)

        result = pipeline.execute(
            worker_result,
            verify_paths=list(vp),
            test_targets=list(tt),
            attempt=session.attempt,
        )

        # Record governance outcome as advisory reference (not authority)
        session.record_governance(result)

        # Map pipeline result to session state (explicit, no bypass)
        if result.success and getattr(result, "verification_passed", False):
            # Successful apply+verify → VERIFIED (via AUTHORIZED in P9.1, but P9.4 adds VERIFIED)
            # For backward compat, allow either AUTHORIZED→VERIFIED or direct VERIFIED
            try:
                session.transition_to(SessionState.VERIFIED)
            except ValueError:
                # If VERIFIED not allowed from GOVERNING (should be), try AUTHORIZED→VERIFIED
                session.transition_to(SessionState.AUTHORIZED)
                session.transition_to(SessionState.VERIFIED)
        elif getattr(result, "failure_stage", "") == "approval":
            # HIGH without valid approval → WAITING_APPROVAL (not DENIED, allows resume)
            # Distinguish from other DENY cases
            try:
                session.transition_to(SessionState.WAITING_APPROVAL, reason=result.failure_reason)
            except ValueError:
                session.transition_to(SessionState.DENIED, reason=result.failure_reason)
        elif getattr(result, "failure_stage", "") in ("validation", "risk", "controller"):
            session.transition_to(SessionState.DENIED, reason=result.failure_reason)
        elif getattr(result, "failure_stage", "") in ("verification", "apply", "rollback"):
            session.transition_to(SessionState.FAILED, reason=result.failure_reason)
        else:
            # Fallback: any other failure → DENIED if not success
            if not result.success:
                # Prefer DENIED for governance denials, FAILED for system failures
                try:
                    session.transition_to(SessionState.DENIED, reason=result.failure_reason)
                except ValueError:
                    session.transition_to(SessionState.FAILED, reason=result.failure_reason)
            else:
                session.transition_to(SessionState.FAILED, reason="unexpected non-success without failure_stage")

        return result

    @staticmethod
    def _assert_no_authority_imports():
        """Meta-test helper: ensure this module does not import execution/approval primitives as bypass."""
        import pathlib
        import re
        text = pathlib.Path(__file__).read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+.*$", text, flags=re.MULTILINE)
        forbidden = []
        for line in imports:
            # Bridge may import AgentSession and WorkerActionPipeline type for hints, but must not import FileApplier/ApprovalStore directly
            if "simulation.agent.apply.file_applier" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_executor" in line:
                forbidden.append(line.strip())
            if "simulation.agent.approval.approval_store" in line:
                forbidden.append(line.strip())
            if "simulation.security.risk_engine" in line:
                forbidden.append(line.strip())
            if "simulation.agent.verify.verification_executor" in line:
                forbidden.append(line.strip())
            if "simulation.security.governance_evaluator" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_authorization" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"SessionGovernedBridge must not import authority modules: {forbidden}")
        # Check for actual grant calls (not the check string itself) — look for "store.grant" pattern outside this helper
        # Remove docstrings and helper string literals before scanning for authority bypass keywords
        # Strip first module docstring (non-authoritative mention of FileApplier is allowed)
        code_without_doc = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
        code_without_helper = code_without_doc.replace('".grant("', '').replace("'.grant('", "").replace('"FileApplier"', '').replace("'FileApplier'", '')
        if ".grant(" in code_without_helper and "ApprovalStore" in code_without_helper:
            raise AssertionError("SessionGovernedBridge must not call ApprovalStore.grant")
        # FileApplier reference outside docstring and outside this string literal is forbidden
        # Allow the string literal "FileApplier" in helper's error message above but not actual code use
        if "FileApplier" in code_without_helper:
            # ensure it's not just the helper's own error message string; remove that line
            filtered = "\n".join(l for l in code_without_helper.splitlines() if "FileApplier" not in l or "must not reference" in l)
            # If any remaining FileApplier remains, it's a bypass
            if "FileApplier" in filtered:
                raise AssertionError("SessionGovernedBridge must not reference FileApplier")
