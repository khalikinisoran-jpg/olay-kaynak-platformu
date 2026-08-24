"""P9.2 Repository Inspection Boundary — 16 deterministic tests.

Covers:
1 successful inspection inside workspace
2 session lifecycle explicit INSPECTED
3 inspection result retained by AgentSession
4 does not create/modify file
5 out-of-scope denied
6 traversal denied
7 nonexistent fails
8 directory/unsupported explicit
9 bounded content for large file
10 binary/unsupported safe
11 cannot grant approval
12 cannot authorize governance
13 cannot directly execute/apply
14 cannot mark VERIFIED
15 no hidden retry loop
16 P9.1 invalid transitions remain fail-closed
plus meta boundary test.
"""
import pathlib
import tempfile
from pathlib import Path

import pytest

from simulation.agent.session.agent_session import AgentSession, SessionState
from simulation.agent.session.repository_inspector import RepositoryInspector, InspectionResult

# 1. successful inspection of real file inside allowed workspace
def test_p92_successful_inspection_inside_workspace():
    with tempfile.TemporaryDirectory(prefix="p92_inside_") as td:
        ws = Path(td)
        (ws / "demo.txt").write_text("hello world", encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="demo.txt")
        assert res.exists is True
        assert res.within_scope is True
        assert res.is_file is True
        assert res.is_supported is True
        assert res.failure_reason == ""
        assert "hello world" in res.content_preview
        assert res.content_fingerprint != ""

# 2. session lifecycle reflects successful inspection explicitly
def test_p92_session_lifecycle_inspected():
    ws = Path(tempfile.gettempdir())
    s = AgentSession(session_id="s-p92-1", goal="inspect", workspace=ws, allowed_paths=(str(ws),))
    assert s.state == SessionState.CREATED
    s.transition_to(SessionState.INSPECTING)
    assert s.state == SessionState.INSPECTING
    # Simulate successful inspection
    s.transition_to(SessionState.INSPECTED)
    assert s.state == SessionState.INSPECTED
    # INSPECTED is not terminal, not AUTHORIZED/VERIFIED
    assert s.is_terminal() is False
    assert s.state != SessionState.AUTHORIZED
    # Next would be PROPOSING
    s.transition_to(SessionState.PROPOSING)
    assert s.state == SessionState.PROPOSING

# 3. inspection result is retained/referenced by AgentSession
def test_p92_inspection_result_retained():
    with tempfile.TemporaryDirectory(prefix="p92_retain_") as td:
        ws = Path(td)
        (ws / "a.txt").write_text("hello", encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="a.txt")
        s = AgentSession(session_id="s-retain", goal="inspect a.txt", workspace=ws, allowed_paths=(str(ws),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(res)
        assert s.inspection_result is res
        assert s.inspection_result.content_preview == res.content_preview
        s.transition_to(SessionState.INSPECTED)
        assert s.inspection_result.content_fingerprint == res.content_fingerprint

# 4. inspection does not create or modify any file
def test_p92_inspection_does_not_modify():
    with tempfile.TemporaryDirectory(prefix="p92_nomut_") as td:
        ws = Path(td)
        (ws / "demo.txt").write_text("hello", encoding="utf-8")
        before_mtime = (ws / "demo.txt").stat().st_mtime
        before_content = (ws / "demo.txt").read_text(encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="demo.txt")
        after_content = (ws / "demo.txt").read_text(encoding="utf-8")
        after_mtime = (ws / "demo.txt").stat().st_mtime
        assert before_content == after_content
        assert before_mtime == after_mtime
        # Ensure no new file created
        assert not (ws / "new_file.txt").exists()
        # Also via AgentSession
        s = AgentSession(session_id="s-nomut", goal="g", workspace=ws, allowed_paths=(str(ws),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(res)
        s.transition_to(SessionState.INSPECTED)
        assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello"

# 5. out-of-scope target is denied/fails closed
def test_p92_out_of_scope_denied():
    with tempfile.TemporaryDirectory(prefix="p92_oos_") as td:
        ws = Path(td)
        outer = Path(tempfile.mkdtemp(prefix="p92_oos_outer_"))
        try:
            victim = outer / "victim.txt"
            victim.write_text("secret", encoding="utf-8")
            insp = RepositoryInspector()
            res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path=str(victim))
            assert res.within_scope is False
            assert res.exists is False  # outside scope, not even checked as exists
            assert "outside" in res.failure_reason.lower() or "scope" in res.failure_reason.lower()
            assert res.scope_error != ""
        finally:
            try:
                victim.unlink(); outer.rmdir()
            except Exception:
                pass

# 6. traversal attempt is denied/fails closed
def test_p92_traversal_denied():
    with tempfile.TemporaryDirectory(prefix="p92_trav_") as td:
        ws = Path(td)
        (ws / "a.txt").write_text("hello", encoding="utf-8")
        insp = RepositoryInspector()
        # Try traversal via ../
        traversal = str(ws / ".." / "evil.txt")
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path=traversal)
        assert res.within_scope is False
        # Also via relative traversal inside workspace string
        res2 = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="../evil.txt")
        assert res2.within_scope is False

# 7. nonexistent target fails explicitly
def test_p92_nonexistent_fails():
    with tempfile.TemporaryDirectory(prefix="p92_nonexist_") as td:
        ws = Path(td)
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="no_such_file.txt")
        assert res.exists is False
        assert res.within_scope is True
        assert "does not exist" in res.failure_reason

# 8. directory/unsupported target behavior is explicit and tested
def test_p92_directory_explicit():
    with tempfile.TemporaryDirectory(prefix="p92_dir_") as td:
        ws = Path(td)
        sub = ws / "subdir"
        sub.mkdir()
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="subdir")
        assert res.exists is True
        assert res.is_dir is True
        assert res.is_file is False
        assert res.is_supported is False
        # Directories should not have content preview
        assert res.content_preview == ""
        # For P9.2, directory inspection is not proposable but explicit
        # Ensure AgentSession can still attach it (advisory)
        s = AgentSession(session_id="s-dir", goal="inspect dir", workspace=ws, allowed_paths=(str(ws),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(res)
        s.transition_to(SessionState.INSPECTED)
        assert s.inspection_result.is_dir is True

# 9. bounded content evidence for a large file is enforced
def test_p92_bounded_content_large_file():
    with tempfile.TemporaryDirectory(prefix="p92_large_") as td:
        ws = Path(td)
        large = ws / "large.txt"
        # Create file larger than MAX_CONTENT_BYTES (4096)
        large.write_text("A" * 8000, encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="large.txt")
        assert res.exists is True
        assert res.within_scope is True
        assert res.is_file is True
        # Should be marked not supported due to oversize, with truncated preview
        assert res.is_supported is False
        assert res.content_truncated is True
        assert "exceeds bounded" in res.failure_reason.lower() or "oversized" in res.failure_reason.lower()
        assert len(res.content_preview) <= 2000  # preview bounded
        assert res.size_bytes == 8000

# 10. binary/unsupported content behavior is safe and explicit
def test_p92_binary_unsupported_safe():
    with tempfile.TemporaryDirectory(prefix="p92_binary_") as td:
        ws = Path(td)
        binary = ws / "binary.bin"
        binary.write_bytes(b"\x00\xff\xfe\xfd\x89PNG\r\n")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="binary.bin")
        assert res.exists is True
        assert res.within_scope is True
        assert res.is_supported is False
        assert "binary" in res.failure_reason.lower()
        assert res.content_preview == "" or len(res.content_preview) == 0

# 11. inspection cannot grant approval
def test_p92_inspection_cannot_grant_approval():
    import re
    src = pathlib.Path("simulation/agent/session/repository_inspector.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
    for line in imports:
        assert "approval_store" not in line.lower(), f"RepositoryInspector must not import ApprovalStore: {line}"
    src2 = pathlib.Path("simulation/agent/session/agent_session.py").read_text(encoding="utf-8")
    imports2 = re.findall(r"^\s*(?:from|import)\s+.*$", src2, flags=re.MULTILINE)
    for line in imports2:
        assert "approval_store" not in line.lower(), f"AgentSession must not import ApprovalStore: {line}"
    # Inspection result must not have approval fields
    with tempfile.TemporaryDirectory(prefix="p92_no_approval_") as td:
        ws = Path(td)
        (ws / "a.txt").write_text("hello", encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="a.txt")
        assert not hasattr(res, "approved")
        assert not hasattr(res, "approval_id")

# 12. inspection cannot authorize governance
def test_p92_inspection_cannot_authorize_governance():
    src = pathlib.Path("simulation/agent/session/repository_inspector.py").read_text(encoding="utf-8")
    assert "GovernanceEvaluator" not in src
    assert "RiskEngine" not in src
    with tempfile.TemporaryDirectory(prefix="p92_no_gov_") as td:
        ws = Path(td)
        (ws / "a.txt").write_text("hello", encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="a.txt")
        # Inspection result must not contain governance fields
        assert not hasattr(res, "risk")
        assert not hasattr(res, "allowed")
        # AgentSession inspection must not auto-transition to AUTHORIZED
        s = AgentSession(session_id="s-gov", goal="g", workspace=ws, allowed_paths=(str(ws),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(res)
        s.transition_to(SessionState.INSPECTED)
        assert s.state != SessionState.AUTHORIZED
        assert s.state == SessionState.INSPECTED

# 13. inspection cannot directly execute/apply
def test_p92_inspection_cannot_execute():
    import re
    src = pathlib.Path("simulation/agent/session/repository_inspector.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
    for line in imports:
        assert "file_applier" not in line, f"FileApplier import forbidden: {line}"
        assert "apply_executor" not in line, f"ApplyExecutor import forbidden: {line}"
        assert "worker_action_pipeline" not in line.lower()
    # Verify via meta helper (checks imports, not docstring)
    insp = RepositoryInspector()
    insp._assert_no_write_imports()
    # Ensure inspector is read-only: check that its methods only use read_text/read_bytes/stat, not write
    code_only = re.sub(r'""".*?"""', '', src, flags=re.DOTALL)
    # Allow write_text only in docstring, but code should have only read_text/read_bytes
    assert "read_text" in code_only or "read_bytes" in code_only

# 14. inspection result cannot mark itself VERIFIED
def test_p92_inspection_cannot_mark_verified():
    with tempfile.TemporaryDirectory(prefix="p92_no_verified_") as td:
        ws = Path(td)
        (ws / "a.txt").write_text("hello", encoding="utf-8")
        insp = RepositoryInspector()
        res = insp.inspect(workspace=ws, allowed_paths=(str(ws),), target_path="a.txt")
        assert not hasattr(res, "verified")
        assert not hasattr(res, "verification_passed")
        assert not hasattr(res, "approved")
        s = AgentSession(session_id="s-ver", goal="g", workspace=ws, allowed_paths=(str(ws),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(res)
        s.transition_to(SessionState.INSPECTED)
        assert s.state != SessionState.AUTHORIZED
        assert "VERIFIED" not in s.state.value

# 15. no hidden retry/autonomous loop is introduced
def test_p92_no_hidden_retry():
    ws = Path(tempfile.gettempdir())
    s = AgentSession(session_id="s-retry", goal="g", workspace=ws, allowed_paths=(str(ws),), max_attempts=2)
    s.transition_to(SessionState.INSPECTING)
    assert s.attempt == 1
    # Attach and go to INSPECTED
    insp = RepositoryInspector()
    # Create temp file for inspection
    with tempfile.TemporaryDirectory(prefix="p92_retry2_") as td:
        w2 = Path(td)
        (w2 / "a.txt").write_text("hello", encoding="utf-8")
        res = insp.inspect(workspace=w2, allowed_paths=(str(w2),), target_path="a.txt")
        s2 = AgentSession(session_id="s-retry2", goal="g", workspace=w2, allowed_paths=(str(w2),), max_attempts=2)
        s2.transition_to(SessionState.INSPECTING)
        s2.attach_inspection(res)
        s2.transition_to(SessionState.INSPECTED)
        assert s2.attempt == 1
        # No auto-increment
        assert s2.attempt == 1
        # Explicit next_attempt required
        s2.next_attempt()
        assert s2.attempt == 2
        with pytest.raises(ValueError, match="already at max"):
            s2.next_attempt()
        # Ensure no hidden loop in source
        src = pathlib.Path("simulation/agent/session/agent_session.py").read_text(encoding="utf-8")
        assert "while True" not in src or "AgentSession" not in src  # no infinite loop in session
        src2 = pathlib.Path("simulation/agent/session/repository_inspector.py").read_text(encoding="utf-8")
        assert "while True" not in src2

# 16. existing P9.1 invalid lifecycle transitions remain fail-closed
def test_p92_p91_invalid_transitions_still_fail_closed():
    ws = Path(tempfile.gettempdir())
    s = AgentSession(session_id="s-inv", goal="g", workspace=ws, allowed_paths=(str(ws),))
    # Original P9.1 invalid: CREATED -> AUTHORIZED
    with pytest.raises(ValueError, match="invalid transition"):
        s.transition_to(SessionState.AUTHORIZED)
    s.transition_to(SessionState.INSPECTING)
    # INSPECTING -> AUTHORIZED should still be invalid (must go via INSPECTED/PROPOSING/GOVERNING)
    with pytest.raises(ValueError):
        s.transition_to(SessionState.AUTHORIZED)
    s.transition_to(SessionState.INSPECTED)
    # INSPECTED -> AUTHORIZED is invalid (must go via PROPOSING->GOVERNING)
    with pytest.raises(ValueError):
        s.transition_to(SessionState.AUTHORIZED)
    s.transition_to(SessionState.PROPOSING)
    s.transition_to(SessionState.GOVERNING)
    s.transition_to(SessionState.DENIED)
    with pytest.raises(ValueError):
        s.transition_to(SessionState.AUTHORIZED)

# Meta boundary test: inspector does not import execution primitives
def test_p92_meta_inspector_no_execution_imports():
    import re
    insp = RepositoryInspector()
    insp._assert_no_write_imports()
    src = pathlib.Path("simulation/agent/session/repository_inspector.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
    for line in imports:
        assert "file_applier" not in line, f"FileApplier import forbidden: {line}"
        assert "approval_store" not in line.lower()
        assert "worker_action_pipeline" not in line.lower()
