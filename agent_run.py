from simulation.agent.agent import Agent
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore


def main():

    print("=" * 50)
    print(" Event-Sourced AI Runtime")
    print("=" * 50)

    kernel = Kernel(
        EventStore()
    )

    agent = Agent(kernel)

    while True:

        message = input("\nSen > ")

        if message.lower() in [
            "exit",
            "quit"
        ]:
            print("\nÇıkılıyor...")
            break

        response = agent.chat(message)

        print("\nAgent >", response)

        print(
            "\nToplam Event :",
            kernel.event_count()
        )


if __name__ == "__main__":

    main()