class DecisionTrace:

    def __init__(self):

        self.steps = []

    def record(
        self,
        stage,
        message,
        metadata=None
    ):

        if metadata is None:

            metadata = {}

        self.steps.append({

            "stage": stage,

            "message": message,

            "metadata": metadata

        })

    def clear(self):

        self.steps.clear()

    def generate(self, kernel):

        state = kernel.get_state()

        print()

        print("==================================================")
        print(" DECISION TRACE")
        print("==================================================")

        print()

        print("Decision Steps")

        print("------------------------------------------")

        if not self.steps:

            print("No decision steps recorded.")

        else:

            for index, step in enumerate(
                self.steps,
                start=1
            ):

                print(
                    f"[{index}] {step['stage']}"
                )

                print(
                    f"    {step['message']}"
                )

                if step["metadata"]:

                    for key, value in step[
                        "metadata"
                    ].items():

                        print(
                            f"    {key}: {value}"
                        )

                print()

        print("------------------------------------------")

        print("Conversation")

        print("------------------------------------------")

        if not state.conversation_history:

            print("No conversation available.")

        else:

            for message in state.conversation_history:

                role = message["role"].upper()

                print()

                print(role)

                print(message["content"])

        print()

        print("------------------------------------------")

        print("Current Runtime")

        print("------------------------------------------")

        print(
            f"Events                 : {state.event_counter}"
        )

        print(
            f"Tasks                  : {len(state.tasks)}"
        )

        print(
            f"Workers                : {len(state.workers)}"
        )

        print(
            f"Conversation Messages  : "
            f"{len(state.conversation_history)}"
        )

        print()

        print("==================================================")