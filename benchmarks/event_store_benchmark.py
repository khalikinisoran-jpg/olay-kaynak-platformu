"""Event store append benchmark (standalone, not part of the suite).

Run:
    .venv\\Scripts\\python.exe benchmarks\\event_store_benchmark.py

Measures EventStore.append throughput at 1k / 10k / 100k events using a
throwaway store in a temporary directory. The results are reported but
are NOT a substitute for a real load/IO benchmark.
"""

import os
import sys
import tempfile
import time

from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
    ),
)

from simulation.core.event import Event
from simulation.persistence.event_store import EventStore


def run_benchmark(events, path):

    store = EventStore(path=path)

    start = time.perf_counter()

    for index in range(events):

        store.append(
            Event(
                event_type="BenchmarkEvent",
                payload={
                    "index": index,
                    "blob": "x" * 64,
                },
            )
        )

    elapsed = time.perf_counter() - start

    return elapsed, events / elapsed


def main():

    print("EVENT STORE APPEND BENCHMARK")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:

        for count in (1000, 10000, 100000):

            path = Path(tmp) / f"events_{count}.jsonl"

            elapsed, rate = run_benchmark(count, path)

            print(
                f"{count:>7} events : {elapsed:8.3f}s "
                f"({rate:10.1f} appends/s)"
            )

    print("=" * 60)


if __name__ == "__main__":

    main()
