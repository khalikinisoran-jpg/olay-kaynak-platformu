from simulation.core.state import State


class ReplayEngine:

    def __init__(
        self,
        event_store,
        reducer
    ):

        self.event_store = event_store
        self.reducer = reducer

    def replay(self):

        state = State()

        events = self.event_store.read_all()

        for event in events:

            state = self.reducer.apply(
                state,
                event
            )

        return state