class DecisionTrace:

    def generate(self, kernel):

        state = kernel.get_state()

        print()

        print("==================================================")
        print(" DECISION TRACE")
        print("==================================================")

        print()

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

        print(f"Events                 : {state.event_counter}")

        print(f"Tasks                  : {len(state.tasks)}")

        print(f"Workers                : {len(state.workers)}")

        print(
            f"Conversation Messages  : "
            f"{len(state.conversation_history)}"
        )

        print()

        print("==================================================")