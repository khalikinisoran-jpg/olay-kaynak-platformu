from dotenv import load_dotenv

load_dotenv()

from simulation.agent.agent import Agent
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore


def main():

    event_store = EventStore()

    kernel = Kernel(event_store)

    agent = Agent(kernel)

    print("=" * 50)
    print("Event Sourcing AI Agent")
    print("Çıkmak için: exit")
    print("=" * 50)

    while True:

        prompt = input("\nSen > ")

        if prompt.lower() == "exit":
            print("\nGörüşmek üzere.")
            break

        try:

            cevap = agent.ask(prompt)

            print("\nAgent >", cevap)

            print("\nToplam Event :", kernel.event_count())

        except Exception as e:

            print("\nHATA :", e)


if __name__ == "__main__":
    main()