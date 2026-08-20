"""MISSION-O.4: reader / writer concurrency — no-silent-corruption invariant.

``read_all`` / ``read_after`` / ``RecoveryEngine.recover`` are NOT under
the writer's OS lock. On filesystems where an append is not atomic to
concurrent readers (network FS, multi-syscall writes), a reader could
observe a partial line and fail with ``JSONDecodeError``. The invariant
this test pins is the FAIL-CLOSED property: a reader concurrent with a
writer NEVER silently returns corrupted data — every read either parses
cleanly or raises a fail-closed exception, and the store remains valid
afterwards.

On the local Windows/NTFS environment the append is effectively atomic
to readers, so the test is a bounded stress run (large records + many
readers) that asserts the invariant regardless of whether a partial
read is ever actually observed. It is a negative-space test: absence of
silent corruption is asserted, not absence of exceptions.
"""

import json
import secrets
import subprocess
import sys
import time

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_reader_during_concurrent_writer_never_silently_corrupts(tmp_path):
    events = tmp_path / "events.jsonl"
    trigger = tmp_path / "GO"

    writer_code = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
from simulation.persistence.event_store import EventStore
from simulation.core.event import Event
store = EventStore(path={str(events)!r})
while not Path({str(trigger)!r}).exists():
    time.sleep(0.005)
big = "x" * 80000
for i in range(10):
    store.append(Event(event_type="MemoryStored", payload={{"key": "k" + str(i), "value": big}}))
"""

    reader_code = f"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
from simulation.persistence.event_store import EventStore
while not Path({str(trigger)!r}).exists():
    time.sleep(0.005)
parsed_ok = 0
fail_closed = 0
for _ in range(120):
    try:
        events = EventStore(path={str(events)!r}).read_all()
        # a parsed read must be internally consistent: contiguous sequences
        seqs = [e.sequence for e in events]
        assert seqs == list(range(1, len(seqs) + 1))
        parsed_ok += 1
    except (json.JSONDecodeError, RuntimeError, ValueError):
        fail_closed += 1
    time.sleep(0.001)
print("PARSED_OK=" + str(parsed_ok) + " FAIL_CLOSED=" + str(fail_closed))
"""

    (tmp_path / "w.py").write_text(writer_code, encoding="utf-8")
    (tmp_path / "r.py").write_text(reader_code, encoding="utf-8")

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    writer = subprocess.Popen(
        [sys.executable, str(tmp_path / "w.py")],
        env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    reader = subprocess.Popen(
        [sys.executable, str(tmp_path / "r.py")],
        env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    time.sleep(0.5)
    trigger.write_text("go", encoding="utf-8")

    writer.communicate(timeout=180)
    out, err = reader.communicate(timeout=180)
    assert writer.returncode == 0
    assert reader.returncode == 0, err.decode("utf-8", errors="replace")

    output = out.decode("utf-8", errors="replace")
    assert "PARSED_OK=" in output

    # the store must still be fully valid afterwards
    from simulation.persistence.event_store import EventStore
    from simulation.security.hash_verifier import HashVerifier

    records = [
        json.loads(line)
        for line in events.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert HashVerifier().verify(records) is True
    sequences = [r["sequence"] for r in records]
    assert sequences == list(range(1, len(records) + 1))


def test_reader_during_crashed_partial_append_fails_closed(tmp_path):
    """A reader that opens the store right after a crashed writer leaves a
    partial line must fail closed (JSONDecodeError), never return silently
    truncated data."""
    from simulation.core.event import Event
    from simulation.core.kernel import Kernel
    from simulation.persistence.event_store import EventStore

    events = tmp_path / "events.jsonl"
    kernel = Kernel(EventStore(path=str(events)))
    kernel.dispatch(
        Event(event_type="MemoryStored", payload={"key": "a", "value": "1"})
    )

    with open(events, "a", encoding="utf-8") as f:
        f.write('{"event_id": "partial", "event_ty')
        f.flush()

    try:
        EventStore(path=str(events)).read_all()
        raise AssertionError("read_all must not return silently truncated data")
    except (json.JSONDecodeError, ValueError):
        pass
