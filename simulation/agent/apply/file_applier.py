import os
import tempfile

from pathlib import Path

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.security.path_policy import (
    PathPolicy
)


class FileApplier:

    """Scoped, integrity-checked file writer.

    Apply semantics (MISSION-006, hardened in this sprint):

    - ``check_scope`` is re-run at write time and the write goes
      through the single canonical target produced by
      ``PathPolicy.resolve_target`` (one resolution, used for both the
      scope check and the write).
    - ``old_content`` must match the current file exactly, otherwise
      the patch is stale and denied before any write.
    - The write is atomic: content is staged in a temporary file in
      the same directory, flushed + fsynced, then ``os.replace``-d
      over the canonical target. A crash mid-write therefore leaves
      either the old file or the fully written new file, never a
      truncated mix. Original file permissions are preserved.
    - After the write the target is read back; any mismatch with the
      approved ``new_content`` triggers a bounded restore of
      ``old_content`` and a FAIL.

    ``restore`` exposes the same canonical, atomic, read-back-verified
    write for the pre-apply content so the pipeline can roll a failed
    patch back to the exact pre-apply state.

    TOCTOU note: resolving and then writing through one canonical path
    closes the lexical check/write gap, but a concurrent attacker with
    the ability to swap the directory entry between resolution and
    replace is outside this single-process trust model.
    """

    def __init__(self):

        self.path_policy = PathPolicy()

    def apply(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        if patch.action != "modify":

            return (
                False,
                f"Unsupported action: {patch.action}"
            )

        in_scope, scope_message = (
            self.path_policy.check_scope(
                patch.path,
                patch.allowed_paths
            )
        )

        if not in_scope:

            return (
                False,
                scope_message
            )

        path = self._resolve_target(patch)

        if path is None:

            return (
                False,
                "Patch target could not be "
                "resolved; rejected."
            )

        if not path.exists():

            return (
                False,
                f"File does not exist: {patch.path}"
            )

        if not path.is_file():

            return (
                False,
                f"Patch target is not a file: {patch.path}"
            )

        try:

            current_content = path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return (
                False,
                f"Unable to read patch target: {exc}"
            )

        if current_content != patch.old_content:

            return (
                False,
                "Patch is stale: current file content "
                "does not match old_content."
            )

        if patch.old_content == patch.new_content:

            return (
                False,
                "Patch does not contain a change."
            )

        try:

            self._write_atomic(
                path,
                patch.new_content,
            )

        except Exception as exc:

            return (
                False,
                f"Failed to write patch target: {exc}"
            )

        try:

            written = path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return (
                False,
                "Unable to verify patch target "
                f"after write: {exc}"
            )

        if written != patch.new_content:

            self._restore(
                path,
                patch.old_content
            )

            return (
                False,
                "Patch integrity check failed: "
                "written content does not match "
                "new_content; target restored."
            )

        return (
            True,
            "File applied successfully."
        )

    def restore(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        """Roll a patch back to its exact pre-apply content.

        Fail-closed: the canonical target must still exist and be a
        file, the restored bytes are read back and compared against
        ``old_content``, and any exception is reported instead of
        being swallowed.
        """

        if patch.action != "modify":

            return (
                False,
                f"Unsupported action: {patch.action}"
            )

        path = self._resolve_target(patch)

        if path is None:

            return (
                False,
                "Patch target could not be "
                "resolved; rejected."
            )

        if not path.exists():

            return (
                False,
                "Rollback failed: patch target "
                f"does not exist: {patch.path}"
            )

        if not path.is_file():

            return (
                False,
                "Rollback failed: patch target is "
                f"not a file: {patch.path}"
            )

        try:

            current_content = path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return (
                False,
                f"Rollback failed: unable to read "
                f"patch target: {exc}"
            )

        if current_content == patch.old_content:

            return (
                True,
                "Patch target already in the "
                "pre-apply state."
            )

        try:

            self._write_atomic(
                path,
                patch.old_content,
            )

        except Exception as exc:

            return (
                False,
                f"Rollback failed: unable to restore "
                f"patch target: {exc}"
            )

        try:

            restored = path.read_text(
                encoding="utf-8"
            )

        except Exception as exc:

            return (
                False,
                "Rollback failed: unable to verify "
                f"restored target: {exc}"
            )

        if restored != patch.old_content:

            return (
                False,
                "Rollback integrity check failed: "
                "restored content does not match "
                "old_content."
            )

        return (
            True,
            "Patch rolled back to the pre-apply state."
        )

    def _resolve_target(
        self,
        patch
    ) -> Path | None:

        canonical = self.path_policy.resolve_target(
            patch.path
        )

        if canonical is None:

            return None

        return Path(canonical)

    def _write_atomic(
        self,
        path: Path,
        content: str
    ) -> None:

        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".esp-tmp-",
        )

        try:

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
                newline="",
            ) as f:

                f.write(content)

                f.flush()

                os.fsync(f.fileno())

            self._preserve_mode(
                path,
                tmp,
            )

            self._replace(
                tmp,
                str(path),
            )

        except Exception:

            try:

                os.unlink(tmp)

            except OSError:

                pass

            raise

    def _preserve_mode(
        self,
        path: Path,
        tmp: str
    ) -> None:

        try:

            mode = os.stat(path).st_mode

        except OSError:

            return

        try:

            os.chmod(tmp, mode)

        except OSError:

            pass

    def _replace(
        self,
        tmp,
        target
    ):

        os.replace(tmp, target)

    @staticmethod
    def _restore(
        path,
        old_content
    ):

        try:

            path.write_text(
                old_content,
                encoding="utf-8"
            )

        except Exception:

            pass
