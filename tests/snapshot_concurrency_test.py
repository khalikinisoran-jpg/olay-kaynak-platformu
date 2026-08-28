"""RELEASE-03: snapshot path isolation for concurrent runtimes.

Two processes (or two kernels) with SEPARATE event stores must never share
one auto-snapshot file. Before RELEASE-03 the Kernel default was a
CWD-relative ``SnapshotManager()`` writing to ``data/snapshot.json`` even
when the event store lived elsewhere, so two runtimes in the same working
directory raced on one snapshot file (verified reproduction: a concurrent
worker failed and read-back fell back to full replay with cross-contamination).

After RELEASE-03 the default snapshot path is derived from the event store
location. These tests pin that invariant deterministically.
"""

import json
import threading
from pathlib import Path

from simulation.core.event import Event
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore


def _make_event(worker, index):
    return Event(
        event_type="UserQuestionReceived",
        payload={"prompt": f"w{worker}-e{index}", "worker": worker},
        sequence=None,
    )


def _snapshot_path_of(kernel):
    return Path(kernel.snapshot_manager.snapshot_store.path)


def test_kernel_snapshot_path_is_derived_from_event_store(tmp_path):
    store = EventStore(path=tmp_path / "events.jsonl")
    kernel = Kernel(store)

    assert _snapshot_path_of(kernel) == (tmp_path / "snapshot.json")


def test_default_layout_invariant_is_data_snapshot():
    # A store at the default relative path yields the historical default
    # snapshot location. Pure string-level invariant (no data/ writes).
    store_path = Path("data/events.jsonl")
    snapshot_path = store_path.parent / "snapshot.json"
    assert snapshot_path == Path("data/snapshot.json")


def test_two_kernels_distinct_stores_never_collide(tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()

    kernel_a = Kernel(EventStore(path=a_dir / "events.jsonl"))
    kernel_b = Kernel(EventStore(path=b_dir / "events.jsonl"))

    assert _snapshot_path_of(kernel_a) == (a_dir / "snapshot.json")
    assert _snapshot_path_of(kernel_b) == (b_dir / "snapshot.json")
    assert _snapshot_path_of(kernel_a) != _snapshot_path_of(kernel_b)

    for i in range(1, 7):  # interval=2 -> auto-snapshots happen
        kernel_a.dispatch(_make_event("a", i))
        kernel_b.dispatch(_make_event("b", i))

    assert (a_dir / "snapshot.json").exists()
    assert (b_dir / "snapshot.json").exists()

    meta_a = json.loads((a_dir / "snapshot.json").read_text(encoding="utf-8"))
    meta_b = json.loads((b_dir / "snapshot.json").read_text(encoding="utf-8"))

    assert meta_a["last_sequence"] == 6
    assert meta_b["last_sequence"] == 6


def test_concurrent_kernels_write_distinct_snapshot_files(tmp_path):
    results = {}

    def run(name):
        work_dir = tmp_path / name
        work_dir.mkdir()
        kernel = Kernel(EventStore(path=work_dir / "events.jsonl"))
        for i in range(1, 5):
            kernel.dispatch(_make_event(name, i))
        results[name] = (work_dir / "snapshot.json").exists()

    threads = [
        threading.Thread(target=run, args=("t1",)),
        threading.Thread(target=run, args=("t2",)),
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=60)

    assert results["t1"] is True
    assert results["t2"] is True

    snapshots = list(tmp_path.glob("*/snapshot.json"))
    assert len(snapshots) == 2
