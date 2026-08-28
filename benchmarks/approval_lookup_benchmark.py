"""Approval lookup benchmark (standalone, not part of the suite).

Run:
    .venv\\Scripts\\python.exe benchmarks\\approval_lookup_benchmark.py

Measures ApprovalStore.find_valid lookup throughput at 1k / 10k grants
using an in-memory store (no ledger, no fsync). The results are reported
but are NOT a substitute for a real load/IO benchmark. They measure the
in-memory O(1)-ish lookup path only; ledger-backed runs add an fsync per
append.
"""

import sys
import time

from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
    ),
)

from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.approval.approval import Approval


def run_benchmark(count):

    store = ApprovalStore()

    fingerprints = []

    for index in range(count):

        fingerprint = f"{index:064x}"

        fingerprints.append(fingerprint)

        store.grant(
            patch_fingerprint=fingerprint,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
            authorizer="benchmark",
            expires_at=3600,
        )

    start = time.perf_counter()

    for fingerprint in fingerprints:

        store.find_valid(
            fingerprint,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )

    elapsed = time.perf_counter() - start

    return elapsed


def main():

    print("APPROVAL LOOKUP BENCHMARK")
    print("=" * 60)

    for count in (1000, 10000):

        elapsed = run_benchmark(count)

        rate = count / elapsed

        print(
            f"{count:>7} grants : {elapsed:8.3f}s "
            f"({rate:7.1f} lookups/s)"
        )

    print("=" * 60)
    print(
        "In-memory lookup only; a ledger-backed store appends "
        "an fsynced record per grant/consume."
    )


if __name__ == "__main__":

    main()
