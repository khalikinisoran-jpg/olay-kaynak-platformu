from simulation.context.context_builder import ContextBuilder
from simulation.core.reducer import Reducer
from simulation.persistence.event_store import EventStore
from simulation.replay.replay_engine import ReplayEngine


def main():

    print("=" * 50)
    print(" Context Builder Test ")
    print("=" * 50)

    event_store = EventStore()

    reducer = Reducer()

    replay = ReplayEngine(
        event_store=event_store,
        reducer=reducer
    )

    state = replay.replay()

    builder = ContextBuilder()

    context = builder.build(state)

    print()
    print(context)


if __name__ == "__main__":

    main()