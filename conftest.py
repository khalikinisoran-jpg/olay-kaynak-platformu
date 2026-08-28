import pytest

from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore


def pytest_configure(config):

    config.addinivalue_line(
        "markers",
        "live_llm: runs a real LLM provider call; "
        "opt-in only (requires RUN_LIVE_LLM=1) and "
        "may incur API cost",
    )


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