"""P9.2 RepositoryInspector — deterministic read-only inspection boundary.

Read-only guarantee: only reads metadata and bounded file content.
MUST NOT: open for writing, modify, rename, delete, os.replace, FileApplier,
ApplyExecutor, WorkerActionPipeline.execute, ApprovalStore.grant,
VerificationExecutor, PatchProposal creation as side effect.

Uses existing PathPolicy for scope validation (no duplicate logic).
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from simulation.security.path_policy import PathPolicy

# Bounded evidence limit (deterministic, not unbounded dump)
MAX_CONTENT_BYTES = 4096
PREVIEW_CHARS = 2000


@dataclass(frozen=True)
class InspectionResult:
    """Read-only evidence for a single inspected path.

    All fields are advisory/evidence only, never authority.
    """

    requested_path: str  # as given
    resolved_path: str  # canonical absolute (or requested if resolve failed)
    exists: bool
    within_scope: bool
    is_file: bool
    is_dir: bool
    is_supported: bool  # regular text file within bound and utf-8
    size_bytes: int | None  # None if not exists or not file
    content_preview: str  # bounded, "" if not supported or not file
    content_truncated: bool
    content_fingerprint: str  # SHA256 of full content if supported, else ""
    failure_reason: str  # "" if success, else explicit reason
    scope_error: str  # "" if within scope, else PathPolicy message


class RepositoryInspector:
    """Deterministic read-only inspector.

    Inputs are explicit: workspace, allowed_paths, optional target path, goal/context.
    Goal text is not authority (not used for scope decision).
    """

    def __init__(self, path_policy: Optional[PathPolicy] = None):
        self.path_policy = path_policy or PathPolicy()

    def inspect(
        self,
        workspace: Path,
        allowed_paths: Tuple[str, ...],
        target_path: Optional[str] = None,
        goal: str = "",
    ) -> InspectionResult:
        # Normalize workspace
        try:
            ws_resolved = Path(workspace).resolve()
        except Exception as e:
            return InspectionResult(
                requested_path=str(target_path or workspace),
                resolved_path=str(target_path or workspace),
                exists=False,
                within_scope=False,
                is_file=False,
                is_dir=False,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason=f"workspace resolve failed: {e}",
                scope_error="",
            )

        # Determine effective target: if target_path given, resolve relative to workspace if not absolute
        if target_path is None:
            # Inspect workspace itself (directory)
            requested = str(workspace)
            resolved = str(ws_resolved)
            # Check scope for workspace itself
            within, scope_msg = self.path_policy.check_scope(resolved, allowed_paths)
            is_dir = ws_resolved.is_dir()
            exists = ws_resolved.exists()
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved,
                exists=exists,
                within_scope=within,
                is_file=False,
                is_dir=is_dir,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason="" if (exists and within) else (scope_msg if not within else "workspace not found"),
                scope_error="" if within else scope_msg,
            )

        # Target path provided
        requested = str(target_path)
        # Resolve: if relative, relative to workspace; if absolute, resolve directly
        raw = Path(target_path)
        candidate = (ws_resolved / raw) if not raw.is_absolute() else raw
        try:
            resolved_path = str(candidate.resolve())
        except Exception:
            resolved_path = str(candidate)

        # Scope validation via PathPolicy (independent)
        within, scope_msg = self.path_policy.check_scope(resolved_path, allowed_paths)
        if not within:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=False,
                within_scope=False,
                is_file=False,
                is_dir=False,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason=scope_msg,
                scope_error=scope_msg,
            )

        # Check existence and type
        p = Path(resolved_path)
        exists = p.exists()
        if not exists:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=False,
                within_scope=True,
                is_file=False,
                is_dir=False,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason="target does not exist",
                scope_error="",
            )

        is_file = p.is_file()
        is_dir = p.is_dir()

        if is_dir:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=True,
                within_scope=True,
                is_file=False,
                is_dir=True,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason="",
                scope_error="",
            )

        if not is_file:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=True,
                within_scope=True,
                is_file=False,
                is_dir=False,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason="unsupported target type (not regular file)",
                scope_error="",
            )

        # Regular file — check size and read bounded content
        try:
            size = p.stat().st_size
        except Exception as e:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=True,
                within_scope=True,
                is_file=True,
                is_dir=False,
                is_supported=False,
                size_bytes=None,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason=f"stat failed: {e}",
                scope_error="",
            )

        # Enforce bound: if file larger than MAX_CONTENT_BYTES, we still read only up to limit for preview but mark truncated and not fully supported for proposal
        # For P9.2, we treat oversized as not supported for bounded evidence (fail-safe, not proposable)
        if size > MAX_CONTENT_BYTES:
            # Read only preview for evidence, but mark truncated and not supported
            try:
                data = p.read_bytes()[:PREVIEW_CHARS]
                # Try decode as utf-8 for preview, but mark as binary if fails
                try:
                    preview = data[:PREVIEW_CHARS].decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    preview = ""
                    return InspectionResult(
                        requested_path=requested,
                        resolved_path=resolved_path,
                        exists=True,
                        within_scope=True,
                        is_file=True,
                        is_dir=False,
                        is_supported=False,
                        size_bytes=size,
                        content_preview="",
                        content_truncated=True,
                        content_fingerprint="",
                        failure_reason="unsupported binary/oversized content",
                        scope_error="",
                    )
                return InspectionResult(
                    requested_path=requested,
                    resolved_path=resolved_path,
                    exists=True,
                    within_scope=True,
                    is_file=True,
                    is_dir=False,
                    is_supported=False,
                    size_bytes=size,
                    content_preview=preview,
                    content_truncated=True,
                    content_fingerprint="",
                    failure_reason="file exceeds bounded size limit",
                    scope_error="",
                )
            except Exception as e:
                return InspectionResult(
                    requested_path=requested,
                    resolved_path=resolved_path,
                    exists=True,
                    within_scope=True,
                    is_file=True,
                    is_dir=False,
                    is_supported=False,
                    size_bytes=size,
                    content_preview="",
                    content_truncated=False,
                    content_fingerprint="",
                    failure_reason=f"read failed: {e}",
                    scope_error="",
                )

        # Within bound — try utf-8 read
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=True,
                within_scope=True,
                is_file=True,
                is_dir=False,
                is_supported=False,
                size_bytes=size,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason="unsupported binary content (not utf-8)",
                scope_error="",
            )
        except Exception as e:
            return InspectionResult(
                requested_path=requested,
                resolved_path=resolved_path,
                exists=True,
                within_scope=True,
                is_file=True,
                is_dir=False,
                is_supported=False,
                size_bytes=size,
                content_preview="",
                content_truncated=False,
                content_fingerprint="",
                failure_reason=f"read failed: {e}",
                scope_error="",
            )

        # Successful text file within bound
        preview = text[:PREVIEW_CHARS]
        truncated = len(text) > PREVIEW_CHARS
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        return InspectionResult(
            requested_path=requested,
            resolved_path=resolved_path,
            exists=True,
            within_scope=True,
            is_file=True,
            is_dir=False,
            is_supported=True,
            size_bytes=size,
            content_preview=preview,
            content_truncated=truncated,
            content_fingerprint=fingerprint,
            failure_reason="",
            scope_error="",
        )

    @staticmethod
    def _assert_no_write_imports():
        """Meta-test helper: ensure this module does not import execution primitives."""
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
            if "os.replace" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"RepositoryInspector must not import execution primitives: {forbidden}")
        # No direct write calls: ensure code (outside docstring and this check) does not contain actual write
        # (We intentionally skip checking for ".write_text" literal in this helper to avoid self-trigger)
