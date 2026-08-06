from simulation.core.state import State
from simulation.memory.memory_service import MemoryService


def main():

    state = State()

    memory = MemoryService()

    print()

    print("==============================")
    print(" MEMORY SERVICE TEST")
    print("==============================")

    state = memory.set(
        state,
        "user.name",
        "Ahmet"
    )

    state = memory.set(
        state,
        "user.city",
        "İstanbul"
    )

    print()

    print(memory.get(
        state,
        "user.name"
    ))

    print(memory.get(
        state,
        "user.city"
    ))

    print(memory.exists(
        state,
        "user.name"
    ))

    print(memory.exists(
        state,
        "user.age"
    ))

    print()

    print(memory.all(
        state
    ))

    state = memory.delete(
        state,
        "user.city"
    )

    print()

    print(memory.all(
        state
    ))

    print()

    print("==============================")


if __name__ == "__main__":

    main()