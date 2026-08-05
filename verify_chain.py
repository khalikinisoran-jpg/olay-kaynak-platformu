import json
from pathlib import Path

from simulation.security.hash_chain import HashChain


EVENT_FILE = Path("data/events.jsonl")


def main():

    print("=" * 60)
    print(" HASH CHAIN VERIFIER")
    print("=" * 60)

    if not EVENT_FILE.exists():

        print("Event file not found.")
        return

    previous_hash = "GENESIS"

    valid = True

    with open(
        EVENT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for index, line in enumerate(f, start=1):

            record = json.loads(line)

            expected_previous = previous_hash

            actual_previous = record["previous_hash"]

            current_hash = record["current_hash"]

            calculated = HashChain.calculate({

                "event_id": record["event_id"],
                "event_type": record["event_type"],
                "payload": record["payload"],
                "sequence": record["sequence"],
                "previous_hash": actual_previous

            })

            if expected_previous != actual_previous:

                print(
                    f"✗ Event {index} previous hash mismatch"
                )

                valid = False

            elif calculated != current_hash:

                print(
                    f"✗ Event {index} current hash mismatch"
                )

                valid = False

            else:

                print(
                    f"✓ Event {index}"
                )

            previous_hash = current_hash

    print()

    print("=" * 60)

    if valid:

        print("CHAIN STATUS : VALID")

    else:

        print("CHAIN STATUS : INVALID")

    print("=" * 60)


if __name__ == "__main__":

    main()