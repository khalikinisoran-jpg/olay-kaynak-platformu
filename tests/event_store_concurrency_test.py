import json
import threading

import pytest

from simulation.core.event import Event
from simulation.persistence.event_store import EventStore
from simulation.security.hash_verifier import HashVerifier


def read_records(store):

    return [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_concurrent_appends_through_one_store_stay_consistent(
    tmp_path
):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    threads = []

    for worker_id in range(8):

        def append_loop(worker_id=worker_id):

            for index in range(50):

                store.append(
                    Event(
                        event_type="ConcurrentEvent",
                        payload={
                            "worker": worker_id,
                            "index": index,
                        },
                    )
                )

        threads.append(
            threading.Thread(
                target=append_loop
            )
        )

    for thread in threads:

        thread.start()

    for thread in threads:

        thread.join()

    records = read_records(store)

    assert len(records) == 8 * 50

    assert HashVerifier().verify(records) is True

    sequences = [
        record["sequence"]
        for record in records
    ]

    assert sorted(sequences) == list(
        range(1, len(records) + 1)
    )


def test_stale_supplied_sequence_cannot_create_duplicate(
    tmp_path
):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    assigned_first = store.append(
        Event(
            event_type="First",
            payload={"n": 1},
            sequence=5,
        )
    )

    assigned_second = store.append(
        Event(
            event_type="Second",
            payload={"n": 2},
            sequence=1,
        )
    )

    assigned_third = store.append(
        Event(
            event_type="Third",
            payload={"n": 3},
            sequence=0,
        )
    )

    assert assigned_first == 1

    assert assigned_second == 2

    assert assigned_third == 3

    records = read_records(store)

    assert HashVerifier().verify(records) is True

    sequences = [
        record["sequence"]
        for record in records
    ]

    assert sequences == [1, 2, 3]

    assert [
        record["event_type"]
        for record in records
    ] == ["First", "Second", "Third"]


def test_concurrent_kernel_dispatch_creates_unique_sequences(
    tmp_path
):

    from simulation.core.kernel import Kernel
    from simulation.persistence.snapshot import SnapshotStore
    from simulation.persistence.snapshot_manager import SnapshotManager

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        interval=1_000_000,
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
    )

    kernel = Kernel(
        store,
        snapshot_manager=snapshot_manager,
    )

    threads = []

    for worker_id in range(8):

        def dispatch_loop(worker_id=worker_id):

            for index in range(25):

                kernel.dispatch(
                    Event(
                        event_type="KernelDispatch",
                        payload={
                            "worker": worker_id,
                            "index": index,
                        },
                    )
                )

        threads.append(
            threading.Thread(
                target=dispatch_loop
            )
        )

    for thread in threads:

        thread.start()

    for thread in threads:

        thread.join()

    records = read_records(store)

    assert len(records) == 8 * 25

    assert HashVerifier().verify(records) is True

    sequences = sorted(
        record["sequence"]
        for record in records
    )

    assert sequences == list(
        range(1, len(records) + 1)
    )


def test_fsync_failure_fails_closed(tmp_path, monkeypatch):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    def raise_os_error(fd):

        raise OSError("fsync failed")

    monkeypatch.setattr(
        "simulation.persistence.event_store.os.fsync",
        raise_os_error,
    )

    with pytest.raises(OSError):

        store.append(
            Event(
                event_type="Durability",
                payload={"n": 1},
            )
        )


def test_next_sequence_tracks_tail(tmp_path):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    assert store.next_sequence() == 1

    store.append(
        Event(
            event_type="SeqEvent",
            payload={"n": 1},
        )
    )

    assert store.next_sequence() == 2

    store.append(
        Event(
            event_type="SeqEvent",
            payload={"n": 2},
        )
    )

    assert store.next_sequence() == 3

    assert store.tail_sequence() == 2

    assert store.tail_hash() != "GENESIS"
