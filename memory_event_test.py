from simulation.core.reducer import Reducer
from simulation.core.state import State
from simulation.core.event import Event


def main():

    reducer = Reducer()

    state = State()

    print()
    print("===================================")
    print(" MEMORY EVENT TEST")
    print("===================================")

    event = Event(

        event_type="MemoryStored",

        payload={

            "key": "user.name",

            "value": "Ahmet"

        }

    )

    state = reducer.apply(
        state,
        event
    )

    print()

    print("Memory:")

    print(state.memory)

    print()

    print("Event Counter:")

    print(state.event_counter)

    print()

    if state.memory.get("user.name") == "Ahmet":

        print("TEST PASSED")

    else:

        print("TEST FAILED")

    print("===================================")


if __name__ == "__main__":

    main()