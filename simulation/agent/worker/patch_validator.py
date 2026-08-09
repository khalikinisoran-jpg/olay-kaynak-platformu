from pathlib import Path

from simulation.agent.worker.patch_proposal import PatchProposal


class PatchValidator:

    ALLOWED_ACTIONS = {
        "modify",
    }

    def validate(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        if not patch.path:

            return (
                False,
                "Patch path is empty."
            )

        if patch.action not in self.ALLOWED_ACTIONS:

            return (
                False,
                f"Unsupported patch action: {patch.action}"
            )

        if patch.allowed_paths:

            if patch.path not in patch.allowed_paths:

                return (
                    False,
                    "Patch path is outside the allowed scope."
                )

        path = Path(patch.path)

        if not path.exists():

            return (
                False,
                f"Patch target does not exist: {patch.path}"
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

        return (
            True,
            "Patch validation passed."
        )