from simulation.persistence.event_store import EventStore
from simulation.persistence.recovery import Recovery


store = EventStore()


recovery = Recovery(
    store
)


state = recovery.rebuild()


print("Recovery sonucu:")
print(state)