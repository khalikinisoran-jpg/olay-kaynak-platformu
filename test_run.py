from simulation.core.kernel import Kernel
from simulation.core.event import Event
from simulation.persistence.event_store import EventStore


store = EventStore()

kernel = Kernel(
    event_store=store
)


for i in range(1, 11):

    event = Event(
        event_type="TaskCreated",
        payload={
            "task_id": f"T00{i}",
            "name": f"Test Task {i}"
        },
        sequence=i,
        event_id=f"EV00{i}"
    )

    kernel.dispatch(event)


print("Event sayısı:", kernel.event_count())

print("Disk kayıtları:")

print(store.read_all())