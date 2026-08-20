import re

from simulation.memory.memory_events import MemoryEvents
from simulation.memory.provenance import (
    TrustLevel,
    VerificationStatus,
)
from simulation.agent.approval.approval import now_iso


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

                name,

                source="user",

                source_type="user_input",

                timestamp=now_iso(),

                trust_level=TrustLevel.UNTRUSTED,

                verification_status=(
                    VerificationStatus.UNVERIFIED
                ),

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