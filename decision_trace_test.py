from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.decision.decision_trace import DecisionTrace


event_store = EventStore()

kernel = Kernel(
    event_store=event_store
)

trace = DecisionTrace()

trace.record(
    stage="Test",
    message="Decision trace contract test"
)

trace.generate(kernel)

assert trace.steps, (
    "DecisionTrace should contain at least one recorded step."
)

assert trace.steps[0]["stage"] == "Test"

print()
print("Decision Trace Test Passed")