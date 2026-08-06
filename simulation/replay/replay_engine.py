from simulation.core.state import State


class ReplayEngine:

    def __init__(
        self,
        reducer
    ):

        self.reducer = reducer

    def replay(
        self,
        events,
        initial_state=None
    ):

        if initial_state is None:

            state = State()

        else:

            state = initial_state

        for event in events:

            state = self.reducer.apply(
                state,
                event
            )

        return state