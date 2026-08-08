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

        path = Path(patch.path)

        if not path.exists():
            return (
                False,
                f"File does not exist: {patch.path}"
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

        path.write_text(
            patch.new_content,
            encoding="utf-8"
        )

        return (
            True,
            "File applied successfully."
        )