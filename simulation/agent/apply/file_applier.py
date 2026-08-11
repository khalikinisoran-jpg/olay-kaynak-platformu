from pathlib import Path

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.security.path_policy import (
    PathPolicy
)


class FileApplier:

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

        canonical = (
            self.path_policy.resolve_target(
                patch.path
            )
        )

        if canonical is None:

            return (
                False,
                "Patch target could not be "
                "resolved; rejected."
            )

        path = Path(canonical)

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

            path.write_text(
                patch.new_content,
                encoding="utf-8"
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
