from simulation.persistence.event_store import EventStore


store = EventStore()

events = store.read_after(10)

print()

print("===================================")
print(" READ AFTER TEST")
print("===================================")

print(f"Events after #10 : {len(events)}")

for event in events:

    print(
        f"{event.sequence} -> {event.event_type}"
    )

print("===================================")