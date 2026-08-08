import json

from simulation.persistence.event_store import EventStore
from simulation.security.hash_verifier import HashVerifier


store = EventStore()

raw_events = []

with open(
    store.path,
    "r",
    encoding="utf-8"
) as f:

    for line in f:

        if line.strip():

            raw_events.append(
                json.loads(line)
            )


verifier = HashVerifier()

result = verifier.verify(
    raw_events
)


print("Hash doğrulama:")
print(result)


assert result is True, (
    "Event hash chain verification failed."
)


print("Hash Test Passed")