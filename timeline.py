import json
from pathlib import Path


EVENT_FILE = Path("data/events.jsonl")


def main():

    print("=" * 60)
    print(" EVENT SOURCING PLATFORM - TIMELINE")
    print("=" * 60)

    if not EVENT_FILE.exists():
        print("Event dosyası bulunamadı.")
        return

    event_counts = {}
    sequence_errors = []

    total_events = 0

    with open(EVENT_FILE, "r", encoding="utf-8") as f:

        for index, line in enumerate(f, start=1):

            total_events = index

            event = json.loads(line)

            event_type = event.get("event_type", "Unknown")

            event_counts[event_type] = (
                event_counts.get(event_type, 0) + 1
            )

            expected = index
            actual = event.get("sequence", 0)

            if actual != expected:

                sequence_errors.append(
                    (index, expected, actual)
                )

            print()

            print(f"#{index}")

            print(f"Type : {event_type}")

            print(f"ID   : {event['event_id']}")

            print(f"Seq  : {actual}")

            payload = event.get("payload", {})

            if payload:

                print("Payload:")

                for key, value in payload.items():

                    text = str(value)

                    if len(text) > 120:
                        text = text[:120] + "..."

                    print(f"   {key}: {text}")

            print("-" * 60)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"Total Events : {total_events}")
    print()

    print("Event Types")
    print("-" * 60)

    for name, count in sorted(event_counts.items()):

        print(f"{name:<25} {count}")

    print()
    print("-" * 60)

    if sequence_errors:

        print("SYSTEM STATUS : WARNING")
        print()
        print(f"Sequence Problems : {len(sequence_errors)}")
        print()

        for idx, expected, actual in sequence_errors:

            print(
                f"Event #{idx:<3} Expected:{expected:<3} Found:{actual}"
            )

    else:

        print("SYSTEM STATUS : HEALTHY")
        print("No sequence problems detected.")

    print("=" * 60)


if __name__ == "__main__":
    main()