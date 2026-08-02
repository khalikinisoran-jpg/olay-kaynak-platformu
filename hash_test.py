from simulation.persistence.event_store import EventStore
from simulation.security.hash_verifier import HashVerifier


store = EventStore()

events = store.read_all()


verifier = HashVerifier()


result = verifier.verify(events)


print("Hash doğrulama:")
print(result)