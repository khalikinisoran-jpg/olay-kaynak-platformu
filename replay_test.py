from simulation.core.reducer import Reducer
from simulation.persistence.event_store import EventStore
from simulation.replay.replay_engine import ReplayEngine


def main():

    print("=" * 50)
    print(" Replay Test ")
    print("=" * 50)

    event_store = EventStore()

    reducer = Reducer()

    replay = ReplayEngine(
        event_store=event_store,
        reducer=reducer
    )

    state = replay.replay()

    print("\nReplay tamamlandı.")

    print(
        "Task sayısı :",
        len(state.tasks)
    )

    print(
        "Worker sayısı :",
        len(state.workers)
    )

    print(
        "Event Counter :",
        state.event_counter
    )


if __name__ == "__main__":

    main()