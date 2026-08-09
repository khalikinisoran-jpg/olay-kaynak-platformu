from simulation.agent.worker.patch_proposal import PatchProposal


class PatchGenerator:

    def generate(
        self,
        path: str,
        old_content: str,
        description: str,
        allowed_paths: tuple[str, ...] = ()
    ) -> PatchProposal:

        new_content = (
            old_content
            + "\n\n"
            + "# Worker proposal: "
            + description
            + "\n"
        )

        return PatchProposal(
            path=path,
            action="modify",
            reason=description,
            old_content=old_content,
            new_content=new_content,
            allowed_paths=allowed_paths
        )