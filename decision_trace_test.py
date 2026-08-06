from simulation.core.kernel import Kernel
from simulation.decision.decision_trace import DecisionTrace


kernel = Kernel()

trace = DecisionTrace()

trace.generate(kernel)