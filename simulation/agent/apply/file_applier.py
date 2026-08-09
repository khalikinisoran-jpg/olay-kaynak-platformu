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

        path = Path(patch.path)

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

        current_content = path.read_text(
            encoding="utf-8"
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

        path.write_text(
            patch.new_content,
            encoding="utf-8"
        )

        return (
            True,
            "File applied successfully."
        )