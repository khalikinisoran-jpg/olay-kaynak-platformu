from simulation.memory.memory_events import MemoryEvents


def main():

    event = MemoryEvents.stored(

        "user.name",

        "Ahmet"

    )

    print()

    print("==============================")

    print(" MEMORY EVENTS TEST")

    print("==============================")

    print()

    print(event.event_type)

    print()

    print(event.payload)

    print()

    print("==============================")


if __name__ == "__main__":

    main()