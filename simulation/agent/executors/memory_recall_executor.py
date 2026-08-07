class MemoryRecallExecutor:

    def execute(
        self,
        agent,
        prompt
    ):

        state = agent.kernel.state

        name = state.memory.get(
            "user.name"
        )

        class Response:

            model = "memory"

            tokens_used = 0

        if name:

            Response.content = f"Adın {name}."

        else:

            Response.content = (
                "İsmini henüz bilmiyorum."
            )

        return Response()