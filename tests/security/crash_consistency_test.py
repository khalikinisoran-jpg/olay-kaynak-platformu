"""MISSION-O: crash-consistency of the anchored append path.

Simulates the crash windows around ``append`` (event fsync, then anchor
update) with real files and asserts the recovery outcome is either
ACCEPT (complete) or DENY (fail closed) — never a silent partial trust:

1. crash before the event write         -> store unchanged / ACCEPT
2. crash after event write, before anchor -> events beyond anchored
   head -> DENY (N-18)
3. crash mid-event-write (partial line) -> parse error -> DENY
4. crash mid-anchor-write (partial line) -> anchor parse error -> DENY
5. crash after anchor update            -> complete -> ACCEPT
"""

import json

import pytest

from simulation.core.event import Event
from simulation.core.kernel import Kernel
from simulation.persistence.chain_anchor import ChainAnchorError
from simulation.persistence.event_store import EventStore
from simulation.security.hash_chain import HashChain


@pytest.fixture
def key(monkeypatch):
    from simulation.persistence.chain_anchor import generate_key_bytes

    value = generate_key_bytes()
    monkeypatch.setenv("CHAIN_ANCHOR_KEY", value)
    return value


def _anchored_store(tmp_path, key):
    return EventStore(
        path=tmp_path / "events.jsonl",
        anchor_path=tmp_path / "anchor.jsonl",
        anchor_key=key,
    )


def test_crash_before_event_write_is_clean(tmp_path, key):
    store = _anchored_store(tmp_path, key)
    kernel = Kernel(store)
    kernel.dispatch(
        Event(
            event_type="MemoryStored",
            payload={"key": "a", "value": "1"},
        )
    )

    recovered = Kernel(_anchored_store(tmp_path, key))
    assert recovered.state.memory == {"a": "1"}


def test_crash_after_event_write_before_anchor_update_denies(tmp_path, key):
    store = _anchored_store(tmp_path, key)
    _ = Kernel(store)
    store.append(
        Event(
            event_type="MemoryStored",
            payload={"key": "a", "value": "1"},
        )
    )

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    tail = records[-1]

    extra = {
        "event_id": "crash-after-write",
        "event_type": "MemoryStored",
        "payload": {"key": "b", "value": "2"},
        "sequence": tail["sequence"] + 1,
        "previous_hash": tail["current_hash"],
    }
    extra["current_hash"] = HashChain.calculate(extra)

    with open(store.path, "a", encoding="utf-8") as f:
        f.write(json.dumps(extra) + "\n")
        f.flush()

    with pytest.raises(RuntimeError):
        Kernel(_anchored_store(tmp_path, key))


def test_crash_mid_event_write_partial_line_denies(tmp_path, key):
    store = _anchored_store(tmp_path, key)
    kernel = Kernel(store)
    kernel.dispatch(
        Event(
            event_type="MemoryStored",
            payload={"key": "a", "value": "1"},
        )
    )

    with open(store.path, "a", encoding="utf-8") as f:
        f.write('{"event_id": "partial", "event_ty')
        f.flush()

    with pytest.raises((json.JSONDecodeError, RuntimeError)):
        Kernel(_anchored_store(tmp_path, key))


def test_crash_mid_anchor_write_partial_line_denies(tmp_path, key):
    store = _anchored_store(tmp_path, key)
    kernel = Kernel(store)
    kernel.dispatch(
        Event(
            event_type="MemoryStored",
            payload={"key": "a", "value": "1"},
        )
    )

    with open(tmp_path / "anchor.jsonl", "a", encoding="utf-8") as f:
        f.write('{"anchor_id": 99, "sequ')
        f.flush()

    with pytest.raises((ChainAnchorError, json.JSONDecodeError)):
        Kernel(_anchored_store(tmp_path, key))


def test_crash_after_anchor_update_is_complete(tmp_path, key):
    store = _anchored_store(tmp_path, key)
    kernel = Kernel(store)
    for index in range(3):
        kernel.dispatch(
            Event(
                event_type="MemoryStored",
                payload={"key": f"k{index}", "value": "v"},
            )
        )

    anchor_lines = [
        line
        for line in (tmp_path / "anchor.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert len(anchor_lines) == 3

    recovered = Kernel(_anchored_store(tmp_path, key))
    assert recovered.state.event_counter == 3
