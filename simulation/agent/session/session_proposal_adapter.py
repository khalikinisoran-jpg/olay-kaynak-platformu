"""P9.3 SessionProposalAdapter — strict normalization boundary.

Consumes AgentSession (INSPECTED) + InspectionResult (evidence only)
and an UNTRUSTED proposer, produces normalized PatchProposal(s).

MUST NOT: call WorkerActionPipeline.execute, ApplyExecutor, FileApplier,
ApprovalStore, GovernanceEvaluator, VerificationExecutor, or create unbounded
retention. Proposer output is untrusted; only old_text/new_text/path/action
are normalized, all authority-like fields are stripped.

Reuses existing PathPolicy for scope and PatchProposal contract.
"""
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Any

from simulation.security.path_policy import PathPolicy
from simulation.agent.worker.patch_proposal import PatchProposal

# Bounded limits (deterministic, fail-closed if exceeded)
MAX_PATCHES = 5
MAX_OLD_NEW_CHARS = 4096
MAX_REASON_CHARS = 500
MAX_PROPOSAL_SET_BYTES = 1 << 20  # 1 MiB raw

# Untrusted fields that must never become authority (same as P4)
_UNTRUSTED_TOP_LEVEL = {
    "approved",
    "human_approved",
    "approval_id",
    "approval",
    "bypass_governance",
    "bypass",
    "human_approval",
    "verification_passed",
    "verified",
    "tests_passed",
    "test_passed",
    "risk_override",
    "risk_level",
    "risk_authority",
    "governance_override",
    "apply_directly",
    "write_directly",
    "path_override",
    "target_path",
    "approved_by",
    "authorizer",
}

# Actions allowed (from PatchValidator)
_ALLOWED_ACTIONS = {"modify"}


@dataclass(frozen=True)
class AdapterResult:
    """Result of proposal boundary — either proposals or explicit failure."""

    success: bool
    patches: Tuple[PatchProposal, ...]
    failure_reason: str
    raw_truncated: bool  # whether raw proposer output was bounded


def _strip_untrusted(data: dict) -> dict:
    """Return copy with untrusted top-level fields removed."""
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if k.lower() in _UNTRUSTED_TOP_LEVEL:
            continue
        # Also strip nested metadata authority-like keys if data contains metadata dict
        if k.lower() == "metadata" and isinstance(v, dict):
            # Keep metadata but strip authority-like keys inside
            cleaned = {mk: mv for mk, mv in v.items() if mk.lower() not in _UNTRUSTED_TOP_LEVEL}
            out[k] = cleaned
        else:
            out[k] = v
    return out


def _validate_path(proposer_path: str, session, inspection_result) -> str:
    """Validate proposer path claim against session allowed_paths and inspection evidence.

    Returns canonical resolved path string if valid, raises ValueError otherwise.
    Proposer path cannot override session allowed_paths, cannot escape scope,
    inspection evidence does not authorize different path.
    """
    if not isinstance(proposer_path, str) or not proposer_path.strip():
        raise ValueError("path must be non-empty string")
    # Reject control characters in path
    if any(ord(c) < 32 or ord(c) == 127 for c in proposer_path):
        raise ValueError("path contains control characters")
    # Reject absolute out-of-scope via PathPolicy, and traversal
    # Resolve relative to workspace if not absolute
    raw = Path(proposer_path)
    ws = Path(session.workspace).resolve()
    candidate = (ws / raw) if not raw.is_absolute() else raw
    try:
        resolved = str(candidate.resolve())
    except Exception as e:
        raise ValueError(f"path resolve failed: {e}")
    # Use PathPolicy for scope
    policy = PathPolicy()
    allowed = session.allowed_paths
    within, msg = policy.check_scope(resolved, allowed)
    if not within:
        raise ValueError(f"path outside allowed scope: {msg}")
    # Also ensure resolved is within workspace (for P9.2 confinement, but use allowed)
    # If inspection_result exists, its resolved_path is evidence, but not authority — proposer cannot claim different path
    # We already validated against allowed, so any within is ok
    return resolved


def _normalize_single_patch(data: dict, session, inspection_result) -> PatchProposal:
    """Normalize one proposer dict into PatchProposal, fail-closed on malformed."""
    # Strip untrusted top-level
    data = _strip_untrusted(data)

    # Required fields
    for field in ("old_text", "new_text"):
        if field not in data:
            raise ValueError(f"missing required patch field: {field}")
        if not isinstance(data[field], str):
            raise ValueError(f"{field} must be string")
        if len(data[field]) > MAX_OLD_NEW_CHARS:
            raise ValueError(f"{field} exceeds bounded size {MAX_OLD_NEW_CHARS}")
        # Control characters in old/new where unsafe: allow \n, \t, \r only
        # For P9.3, treat control chars as fail-closed (opaque)
        for c in data[field]:
            o = ord(c)
            if o < 32 and o not in (9, 10, 13):
                raise ValueError(f"{field} contains control characters")

    old_text = data["old_text"]
    new_text = data["new_text"]
    if old_text == new_text:
        raise ValueError("old_text equals new_text (no change)")
    if not old_text:
        raise ValueError("old_text must be non-empty")

    # path: proposer may suggest path, but we validate against session
    raw_path = data.get("path") or getattr(inspection_result, "resolved_path", None) or str(session.workspace / "demo.txt")
    # If inspection_result is provided and has resolved_path, prefer proposer's path if present else inspection's
    # But proposer path must still be validated
    canonical_path = _validate_path(str(raw_path), session, inspection_result)

    # action
    action = data.get("action", "modify")
    if not isinstance(action, str):
        raise ValueError("action must be string")
    action = action.strip() or "modify"
    if action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported action: {action}")

    # reason: bounded, from proposer diagnosis/reason
    reason = data.get("reason") or data.get("diagnosis") or "session proposal"
    if not isinstance(reason, str):
        reason = str(reason)
    reason = reason.strip()[:MAX_REASON_CHARS] or "session proposal"

    # old/new content for PatchProposal are full-file old/new, but proposer gives old_text/new_text diff snippet
    # For P9.3, we need to construct full old_content/new_content via inspection evidence
    # Simplest: use inspection's content_preview as old_content if available and matches old_text, else use old_text as full
    # But to keep deterministic and bounded, we treat old_text as the exact old_content to be replaced in file
    # However PatchProposal expects full-file old_content. We will use old_text as old_content and new_text as new_content for now,
    # and later validation will check old_content exists in file via PatchValidator (authoritative, not here).
    # For P9.3, we keep old_content = old_text, new_content = new_text (as proposer snippet), and allowed_paths = session.allowed_paths
    # This is sufficient for proposal boundary; full file content will be validated later by WorkerActionPipeline (authoritative).
    # To stay minimal, we use old_text/new_text directly as old_content/new_content for PatchProposal
    # (This matches how WorkerAgent constructs PatchProposal from old_text/new_text via file read + replace)
    # For session proposal, we don't have full file content here, so we use the snippet as full content for now and let future execution validate.

    # For inspection-based proposal, if inspection has content_preview, we can use it as context but not authority
    # We keep PatchProposal old_content = old_text, new_content = new_text for P9.3

    # Ensure proposer does not inject oversized raw set
    # (Checked at adapter entry)

    return PatchProposal(
        path=canonical_path,
        action=action,
        reason=reason,
        old_content=old_text,
        new_content=new_text,
        allowed_paths=session.allowed_paths,
    )


class SessionProposalAdapter:
    """Strict boundary: UNTRUSTED proposer -> normalized PatchProposal(s).

    Does not call WorkerActionPipeline, FileApplier, ApprovalStore, etc.
    """

    def __init__(self, path_policy: PathPolicy | None = None):
        self.path_policy = path_policy or PathPolicy()

    def propose(
        self,
        session,
        inspection_result,
        proposer_callable,
    ) -> AdapterResult:
        """Consume INSPECTED session + inspection evidence + untrusted proposer callable.

        proposer_callable: zero-arg callable returning raw JSON string/dict/list or AnalysisResult-like
        Returns AdapterResult with patches or failure_reason.

        Must be called only when session.state == INSPECTED, otherwise fail-closed.
        """
        # Validate session state
        from simulation.agent.session.agent_session import SessionState

        if session.state != SessionState.INSPECTED:
            return AdapterResult(success=False, patches=(), failure_reason=f"session not in INSPECTED (was {session.state.value})", raw_truncated=False)

        if inspection_result is None:
            return AdapterResult(success=False, patches=(), failure_reason="missing inspection_result", raw_truncated=False)

        # Call proposer (untrusted)
        try:
            raw_output = proposer_callable()
        except Exception as e:
            return AdapterResult(success=False, patches=(), failure_reason=f"proposer raised: {e}", raw_truncated=False)

        # Bound raw output size
        raw_truncated = False
        raw_str = ""
        if isinstance(raw_output, (dict, list)):
            try:
                raw_str = json.dumps(raw_output)
            except Exception:
                raw_str = str(raw_output)
        elif isinstance(raw_output, str):
            raw_str = raw_output
        else:
            # Could be AnalysisResult-like object with old_text/new_text
            # Try to extract
            if hasattr(raw_output, "old_text") and hasattr(raw_output, "new_text"):
                # Already structured, treat as single patch dict
                raw_str = json.dumps({
                    "old_text": getattr(raw_output, "old_text", ""),
                    "new_text": getattr(raw_output, "new_text", ""),
                    "reason": getattr(raw_output, "diagnosis", "") or getattr(raw_output, "reason", ""),
                    "path": getattr(raw_output, "path", None) or getattr(inspection_result, "resolved_path", ""),
                })
            else:
                return AdapterResult(success=False, patches=(), failure_reason="proposer returned unsupported type", raw_truncated=False)

        if len(raw_str.encode("utf-8")) > MAX_PROPOSAL_SET_BYTES:
            return AdapterResult(success=False, patches=(), failure_reason="proposer output exceeds bounded size", raw_truncated=True)

        # Parse JSON if string
        data = None
        if isinstance(raw_output, str):
            try:
                data = json.loads(raw_str)
            except Exception as e:
                return AdapterResult(success=False, patches=(), failure_reason=f"invalid JSON: {e}", raw_truncated=False)
        elif isinstance(raw_output, (dict, list)):
            data = raw_output
        else:
            # From AnalysisResult case above, data is already dict
            try:
                data = json.loads(raw_str)
            except Exception:
                return AdapterResult(success=False, patches=(), failure_reason="invalid structured output", raw_truncated=False)

        # Normalize to list of patch dicts
        patch_dicts: List[dict] = []
        if isinstance(data, dict):
            # Could be single patch dict or {patches: [...]}
            if "patches" in data and isinstance(data["patches"], list):
                patch_dicts = data["patches"]
            else:
                patch_dicts = [data]
        elif isinstance(data, list):
            patch_dicts = data
        else:
            return AdapterResult(success=False, patches=(), failure_reason="proposer output must be object or list", raw_truncated=False)

        if not patch_dicts:
            return AdapterResult(success=False, patches=(), failure_reason="empty proposal set", raw_truncated=False)
        if len(patch_dicts) > MAX_PATCHES:
            return AdapterResult(success=False, patches=(), failure_reason=f"too many patches ({len(patch_dicts)} > {MAX_PATCHES})", raw_truncated=False)

        # For multi-patch, ensure no partial acceptance if one fails: entire set rejected
        patches: List[PatchProposal] = []
        for idx, pd in enumerate(patch_dicts):
            if not isinstance(pd, dict):
                return AdapterResult(success=False, patches=(), failure_reason=f"patch {idx} not an object", raw_truncated=False)
            # Check for ambiguous authority instructions inside patch (e.g., nested approved)
            # We already strip top-level, but also check for any key that looks like authority inside patch dict
            # If any untrusted key present, we strip it (already via _strip_untrusted), but we also ensure it doesn't become proposal
            # For P9.3, we strictly require only allowed keys; extra untrusted keys are stripped, not failed, to match P4 behavior
            # However, multi-target scope escape: if any patch fails validation, entire set fails
            try:
                # Inject inspection path if not present and only one patch and inspection is for a file
                if "path" not in pd or not pd["path"]:
                    # Use inspection's resolved_path as default (evidence, not authority to escape)
                    pd = dict(pd)  # copy
                    pd["path"] = getattr(inspection_result, "resolved_path", str(session.workspace))
                norm = _normalize_single_patch(pd, session, inspection_result)
                patches.append(norm)
            except ValueError as e:
                return AdapterResult(success=False, patches=(), failure_reason=f"patch {idx} invalid: {e}", raw_truncated=False)
            except Exception as e:
                return AdapterResult(success=False, patches=(), failure_reason=f"patch {idx} error: {e}", raw_truncated=False)

        # Success: all patches normalized, none escaped scope individually, entire set is valid
        # Note: This does NOT mean AUTHORIZED; just PROPOSING with normalized PatchProposal(s)
        return AdapterResult(success=True, patches=tuple(patches), failure_reason="", raw_truncated=False)

    @staticmethod
    def _assert_no_authority_imports():
        """Meta-test: ensure this module does not import execution/authority primitives."""
        import pathlib
        import re
        text = pathlib.Path(__file__).read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+.*$", text, flags=re.MULTILINE)
        forbidden = []
        for line in imports:
            if "simulation.agent.apply.file_applier" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_executor" in line:
                forbidden.append(line.strip())
            if "simulation.agent.pipeline.worker_action_pipeline" in line and "WorkerActionPipeline" in line:
                forbidden.append(line.strip())
            if "simulation.agent.approval.approval_store" in line:
                forbidden.append(line.strip())
            if "simulation.agent.verify.verification_executor" in line:
                forbidden.append(line.strip())
            if "simulation.security.risk_engine" in line and "RiskEngine" in line:
                forbidden.append(line.strip())
            if "simulation.security.governance_evaluator" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"SessionProposalAdapter must not import authority/execution modules: {forbidden}")
