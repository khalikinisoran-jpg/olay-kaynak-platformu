import re

from simulation.memory.memory_events import MemoryEvents


class MemoryStoreExecutor:

    def execute(
        self,
        agent,
        prompt
    ):

        match = re.search(

            r"benim adım\s+(.+)",

            prompt,

            re.IGNORECASE

        )

        if not match:

            class Response:

                content = "İsmini anlayamadım."

                model = "memory"

                tokens_used = 0

            return Response()

        name = match.group(1).strip()

        agent.kernel.dispatch(

            MemoryEvents.stored(

                "user.name",

                name

            )

        )

        class Response:

            content = (
                f"Memnun oldum {name}. "
                f"İsmini hatırlayacağım."
            )

            model = "memory"

            tokens_used = 0

        return Response()