import pytest

from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore


@pytest.fixture
def isolated_event_store(tmp_path):
    return EventStore(
        path=tmp_path / "events.jsonl"
    )


@pytest.fixture
def isolated_snapshot_store(tmp_path):
    return SnapshotStore(
        path=tmp_path / "snapshot.json"
    )