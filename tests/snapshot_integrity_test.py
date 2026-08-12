import json

import pytest

from simulation.core.kernel import Kernel
from simulation.core.reducer import Reducer
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.recovery.recovery_engine import RecoveryEngine
from simulation.security.hash_verifier import HashVerifier


def build_kernel(tmp_path):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        )
    )

    return (
        Kernel(
            store,
            snapshot_manager=snapshot_manager,
        ),
        store,
    )


def test_recovery_from_verified_snapshot_matches_replay(tmp_path):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(6):

        kernel.dispatch(
            Event(
                event_type="UserQuestionReceived",
                payload={"prompt": f"q{index}"},
            )
        )

    snapshot = json.loads(
        (tmp_path / "snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert snapshot.get("content_hash")

    reducer = Reducer()

    recovered = RecoveryEngine(
        event_store=EventStore(
            path=tmp_path / "events.jsonl"
        ),
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
        reducer=reducer,
    ).recover()

    assert recovered.event_counter == 6


def test_tampered_snapshot_falls_back_to_full_replay(tmp_path):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(6):

        kernel.dispatch(
            Event(
                event_type="UserQuestionReceived",
                payload={"prompt": f"q{index}"},
            )
        )

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["state"]["memory"] = {
        "forged": "tampered",
    }

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    reducer = Reducer()

    recovered = RecoveryEngine(
        event_store=EventStore(
            path=tmp_path / "events.jsonl"
        ),
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
        reducer=reducer,
    ).recover()

    assert recovered.event_counter == 6

    assert "forged" not in recovered.memory


def test_snapshot_claiming_more_events_than_store_is_rejected(
    tmp_path
):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(6):

        kernel.dispatch(
            Event(
                event_type="UserQuestionReceived",
                payload={"prompt": f"q{index}"},
            )
        )

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["last_sequence"] = 9999

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    reducer = Reducer()

    recovered = RecoveryEngine(
        event_store=EventStore(
            path=tmp_path / "events.jsonl"
        ),
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
        reducer=reducer,
    ).recover()

    assert recovered.event_counter == 6


def test_corrupted_event_chain_fails_closed(tmp_path):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    kernel.dispatch(
        Event(
            event_type="UserQuestionReceived",
            payload={"prompt": "q0"},
        )
    )

    event_path = tmp_path / "events.jsonl"

    records = [
        json.loads(line)
        for line in event_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    records[0]["payload"]["prompt"] = "tampered"

    event_path.write_text(
        "\n".join(
            json.dumps(record)
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )

    reducer = Reducer()

    with pytest.raises(RuntimeError):

        RecoveryEngine(
            event_store=EventStore(
                path=tmp_path / "events.jsonl"
            ),
            snapshot_store=SnapshotStore(
                path=tmp_path / "snapshot.json"
            ),
            reducer=reducer,
        ).recover()


def test_event_chain_still_verifies_after_new_snapshot_format(
    tmp_path
):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(4):

        kernel.dispatch(
            Event(
                event_type="UserQuestionReceived",
                payload={"prompt": f"q{index}"},
            )
        )

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert HashVerifier().verify(records) is True

    sequences = [
        record["sequence"]
        for record in records
    ]

    assert sequences == list(
        range(1, len(records) + 1)
    )


def build_recovery(tmp_path):

    return RecoveryEngine(
        event_store=EventStore(
            path=tmp_path / "events.jsonl"
        ),
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
        reducer=Reducer(),
    )


def dispatch_questions(kernel, count=6):

    from simulation.core.event import Event

    for index in range(count):

        kernel.dispatch(
            Event(
                event_type="UserQuestionReceived",
                payload={"prompt": f"q{index}"},
            )
        )


def test_content_hash_tampering_is_detected(tmp_path):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(6):

        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": "authoritative", "value": "yes"},
            )
        )

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["state"]["memory"] = {
        "forged": "injected",
    }

    snapshot["content_hash"] = "0" * 64

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6

    assert "forged" not in recovered.memory

    assert recovered.memory.get("authoritative") == "yes"


def test_missing_content_hash_falls_back_to_full_replay(
    tmp_path
):

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel)

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    del snapshot["content_hash"]

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6

    assert len(recovered.conversation_history) == 6


def test_unparseable_snapshot_falls_back_to_full_replay(
    tmp_path
):

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel)

    (tmp_path / "snapshot.json").write_text(
        "{ this is not valid json",
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6


@pytest.mark.parametrize(
    "bad_last_sequence",
    [
        "7",
        True,
        -1,
        7,
        9999,
    ],
)
def test_invalid_last_sequence_is_rejected(bad_last_sequence, tmp_path):

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel)

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["last_sequence"] = bad_last_sequence

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6


def test_valid_last_sequence_is_read_from_snapshot(tmp_path):

    from simulation.replay.replay_engine import ReplayEngine

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel, count=6)

    reducer = Reducer()

    stored_events = EventStore(
        path=tmp_path / "events.jsonl"
    ).read_all()

    state_after_four = ReplayEngine(
        reducer=reducer
    ).replay(
        events=stored_events[:4]
    )

    snapshot = {
        "version": 2,
        "last_sequence": 4,
        "created_at": "2026-01-01T00:00:00+00:00",
        "content_hash": RecoveryEngine._content_hash(
            state_after_four.to_dict()
        ),
        "state": state_after_four.to_dict(),
    }

    (tmp_path / "snapshot.json").write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6

    assert len(recovered.conversation_history) == 6


def test_non_hex_64_char_content_hash_is_rejected(tmp_path):

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel)

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["content_hash"] = "g" * 64

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    recovered = build_recovery(tmp_path).recover()

    assert recovered.event_counter == 6


def test_malformed_snapshot_shapes_fail_safely(tmp_path):

    kernel, store = build_kernel(tmp_path)

    dispatch_questions(kernel)

    snapshot_path = tmp_path / "snapshot.json"

    scenarios = [
        [1, 2, 3],
        {"no_state": True},
        {
            "state": ["not", "a", "dict"],
            "content_hash": "0" * 64,
            "last_sequence": 6,
        },
        {
            "state": {},
            "content_hash": "not-a-hex-digest",
            "last_sequence": 6,
        },
    ]

    for scenario in scenarios:

        snapshot_path.write_text(
            json.dumps(scenario),
            encoding="utf-8",
        )

        recovered = build_recovery(tmp_path).recover()

        assert recovered.event_counter == 6


def test_kernel_runtime_uses_integrity_checked_path(tmp_path):

    from simulation.core.event import Event

    kernel, store = build_kernel(tmp_path)

    for index in range(6):

        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": "authoritative", "value": "yes"},
            )
        )

    snapshot_path = tmp_path / "snapshot.json"

    snapshot = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )

    snapshot["state"]["memory"] = {
        "forged": "injected",
    }

    snapshot_path.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )

    restarted = build_kernel(tmp_path)[0]

    assert restarted.get_state().event_counter == 6

    assert "forged" not in restarted.get_state().memory

    assert restarted.get_state().memory.get(
        "authoritative"
    ) == "yes"
