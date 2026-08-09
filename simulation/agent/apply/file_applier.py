from pathlib import Path

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


class FileApplier:

    def apply(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        if patch.action != "modify":

            return (
                False,
                f"Unsupported action: {patch.action}"
            )

        allowed_paths = patch.allowed_paths

        if not allowed_paths:

            return (
                False,
                "Patch scope is empty; "
                "allowed_paths must be provided."
            )

        if patch.path not in allowed_paths:

            return (
                False,
                "Patch path is outside the allowed scope."
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