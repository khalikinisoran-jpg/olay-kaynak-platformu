"""MISSION-O: multi-process single-writer enforcement (real subprocesses).

MISSION-N.1 reproduced the multi-process race (two OS processes sharing
one event-store file): 59/60 records, 29 duplicate sequences, broken
chain. MISSION-O adds an OS-level advisory file lock
(``simulation/persistence/process_lock.py``) plus size-based tail
re-sync, so cooperating ``EventStore`` writers serialize and the
follower re-reads the current tail before allocating a sequence.

Security-relevant results (all VERIFIED here):

- Two / three concurrent writers all succeed, every record is unique
  and contiguous, the chain verifies, recovery accepts.
- A writer that crashes while holding the lock releases it (OS
  behavior): the next writer proceeds — no stale lock.
- A stuck writer that exceeds the lock timeout causes the contending
  writer to FAIL CLOSED with ``EventStoreBusyError`` (never a partial
  write, never a permanent deadlock).

The tests are bounded (20-30 appends x 2-3 subprocesses, timeouts). No
real secret is used.
"""

import json
import os
import secrets
import subprocess
import sys
import time

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

CHILD_TEMPLATE = """
import sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
from simulation.persistence.event_store import EventStore
from simulation.core.event import Event

store = EventStore(path={events!r}, anchor_path={anchor})

while not Path({trigger!r}).exists():
    time.sleep(0.005)

for index in range({count}):
    store.append(
        Event(
            event_type="MemoryStored",
            payload={{"key": "p" + sys.argv[1] + "-e" + str(index), "value": "v"}},
        )
    )
print("done-" + sys.argv[1])
"""


def _run_writers(workdir, count=20, names=("A", "B"), anchored=False):
    trigger = workdir / "GO"
    events = workdir / "events.jsonl"
    anchor = workdir / "anchor.jsonl" if anchored else None

    child_code = CHILD_TEMPLATE.format(
        repo=str(REPO_ROOT),
        trigger=str(trigger),
        events=str(events),
        anchor=repr(str(anchor)) if anchor else "None",
        count=count,
    )
    child_file = workdir / "child.py"
    child_file.write_text(child_code, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    key = None
    if anchored:
        key = secrets.token_hex(32)
        env["CHAIN_ANCHOR_KEY"] = key

    processes = [
        subprocess.Popen(
            [sys.executable, str(child_file), name],
            env=env,
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for name in names
    ]

    time.sleep(0.5)
    trigger.write_text("go", encoding="utf-8")

    for process in processes:
        out, err = process.communicate(timeout=240)
        err_text = err.decode("utf-8", errors="replace")
        assert process.returncode == 0, err_text

    return events, anchor, key


def _records(path):
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    try:
        return [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        return None


def _assert_clean(events, expected_count):
    from simulation.security.hash_verifier import HashVerifier

    records = _records(events)
    assert records is not None, "partial write detected"
    sequences = [record["sequence"] for record in records]
    assert len(records) == expected_count
    assert len(set(sequences)) == expected_count
    assert sequences == list(range(1, expected_count + 1))
    assert HashVerifier().verify(records) is True


def test_two_concurrent_writers_are_serialized_no_corruption(tmp_path):
    events, _, _ = _run_writers(tmp_path, count=20, names=("A", "B"))
    _assert_clean(events, 40)


def test_three_concurrent_writers_are_serialized_no_corruption(tmp_path):
    events, _, _ = _run_writers(tmp_path, count=20, names=("A", "B", "C"))
    _assert_clean(events, 60)


def test_four_concurrent_writers_are_serialized_no_corruption(tmp_path):
    events, _, _ = _run_writers(
        tmp_path,
        count=15,
        names=("A", "B", "C", "D"),
    )
    _assert_clean(events, 60)


def test_repeated_two_writer_runs_are_always_clean(tmp_path):
    """Run the 2-writer scenario several times; every run must produce a
    valid, unique, contiguous chain (no flaky interleaving)."""
    for round_index in range(3):
        workdir = tmp_path / f"round-{round_index}"
        workdir.mkdir()
        events, _, _ = _run_writers(
            workdir,
            count=12,
            names=("A", "B"),
        )
        _assert_clean(events, 24)


def test_delayed_writer_follower_resyncs(tmp_path):
    """Writer B constructs AFTER writer A has already appended several
    records. B must read the real tail at construction and continue the
    chain (follower re-sync), never colliding."""
    import time as _time

    trigger = tmp_path / "GO"
    events = tmp_path / "events.jsonl"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    leader_code = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
from simulation.persistence.event_store import EventStore
from simulation.core.event import Event
store = EventStore(path={str(events)!r})
while not Path({str(trigger)!r}).exists():
    time.sleep(0.005)
for i in range(12):
    store.append(Event(event_type="MemoryStored", payload={{"key": "A-e" + str(i), "value": "v"}}))
"""

    follower_code = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
while not Path({str(trigger)!r}).exists():
    time.sleep(0.005)
time.sleep(0.5)  # deliberately start AFTER the leader has appended
from simulation.persistence.event_store import EventStore
from simulation.core.event import Event
store = EventStore(path={str(events)!r})
for i in range(12):
    store.append(Event(event_type="MemoryStored", payload={{"key": "B-e" + str(i), "value": "v"}}))
"""

    (tmp_path / "leader.py").write_text(leader_code, encoding="utf-8")
    (tmp_path / "follower.py").write_text(follower_code, encoding="utf-8")

    leader = subprocess.Popen(
        [sys.executable, str(tmp_path / "leader.py")],
        env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    follower = subprocess.Popen(
        [sys.executable, str(tmp_path / "follower.py")],
        env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    _time.sleep(0.5)
    trigger.write_text("go", encoding="utf-8")

    leader.communicate(timeout=180)
    follower.communicate(timeout=180)

    assert leader.returncode == 0
    assert follower.returncode == 0

    _assert_clean(events, 24)


def test_writer_crash_before_anchor_update_is_detected(tmp_path):
    """A real subprocess writer that dies between the event write and the
    anchor update must make the anchored store fail closed on recovery
    (events beyond the anchored head), never silently accepted."""
    key = secrets.token_hex(32)
    events = tmp_path / "events.jsonl"
    anchor = tmp_path / "anchor.jsonl"
    trigger = tmp_path / "GO"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["CHAIN_ANCHOR_KEY"] = key

    crash_code = f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
from simulation.persistence import chain_anchor as ca_mod
from simulation.persistence.event_store import EventStore
from simulation.core.event import Event
store = EventStore(path={str(events)!r}, anchor_path={str(anchor)!r})
while not Path({str(trigger)!r}).exists():
    time.sleep(0.005)
orig = ca_mod.ChainAnchor.anchor
def slow_anchor(self, sequence, current_hash):
    time.sleep(30)  # die before the anchor update completes
    return orig(self, sequence, current_hash)
ca_mod.ChainAnchor.anchor = slow_anchor
store.append(Event(event_type="MemoryStored", payload={{"key": "a", "value": "1"}}))
"""

    (tmp_path / "crash.py").write_text(crash_code, encoding="utf-8")
    child = subprocess.Popen(
        [sys.executable, str(tmp_path / "crash.py")],
        env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(0.5)
    trigger.write_text("go", encoding="utf-8")
    time.sleep(1.0)
    child.kill()
    child.wait(timeout=30)

    from simulation.core.kernel import Kernel
    from simulation.persistence.event_store import EventStore

    try:
        Kernel(
            EventStore(
                path=str(events),
                anchor_path=str(anchor),
                anchor_key=key,
            )
        )
        raise AssertionError(
            "anchored store must fail closed after a crash before anchor update"
        )
    except RuntimeError:
        pass


def test_two_concurrent_anchored_writers_are_serialized(tmp_path):
    events, anchor, key = _run_writers(
        tmp_path,
        count=15,
        names=("A", "B"),
        anchored=True,
    )
    _assert_clean(events, 30)

    from simulation.core.kernel import Kernel
    from simulation.persistence.event_store import EventStore

    recovered = Kernel(
        EventStore(
            path=str(events),
            anchor_path=str(anchor),
            anchor_key=key,
        )
    )
    assert recovered.state.event_counter == 30


# ---------------------------------------------------------------------------
# Crash-holding-the-lock -> OS releases it (no stale lock)
# ---------------------------------------------------------------------------

HOLD_CHILD = """
import sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
from simulation.persistence.process_lock import _ProcessFileLock

lock = _ProcessFileLock({events!r}, timeout=60.0)
lock.acquire()
print("HELD", flush=True)
time.sleep({hold_seconds})
lock.release()
print("RELEASED", flush=True)
"""


def test_crash_holding_lock_releases_it_for_next_writer(tmp_path):
    """A writer that dies while holding the lock must not leave a stale
    lock: the OS releases it, so the next writer proceeds."""
    events = tmp_path / "events.jsonl"
    events.touch(exist_ok=True)

    hold_code = HOLD_CHILD.format(
        repo=str(REPO_ROOT),
        events=str(events),
        hold_seconds=30,
    )
    hold_file = tmp_path / "hold.py"
    hold_file.write_text(hold_code, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    holder = subprocess.Popen(
        [sys.executable, str(hold_file)],
        env=env,
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    line = holder.stdout.readline().decode(
        "utf-8",
        errors="replace",
    ).strip()
    assert line == "HELD"

    holder.kill()
    holder.wait(timeout=30)

    time.sleep(0.5)

    from simulation.persistence.process_lock import _ProcessFileLock

    lock = _ProcessFileLock(events, timeout=2.0)
    lock.acquire()
    lock.release()


# ---------------------------------------------------------------------------
# Stuck writer beyond the timeout -> contender fails closed
# ---------------------------------------------------------------------------

BUSY_HOLDER_CHILD = """
import sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
from simulation.persistence.process_lock import _ProcessFileLock

lock = _ProcessFileLock({events!r}, timeout=60.0)
lock.acquire()
print("HELD", flush=True)
time.sleep({hold_seconds})
lock.release()
"""


def test_stuck_writer_beyond_timeout_fails_closed(tmp_path):
    """A holder that does not release within the timeout causes the
    contender to raise ``EventStoreBusyError`` (FAIL CLOSED) instead of
    corrupting the store or deadlocking forever."""
    events = tmp_path / "events.jsonl"
    events.touch(exist_ok=True)

    busy_code = BUSY_HOLDER_CHILD.format(
        repo=str(REPO_ROOT),
        events=str(events),
        hold_seconds=30,
    )
    busy_file = tmp_path / "busy.py"
    busy_file.write_text(busy_code, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    holder = subprocess.Popen(
        [sys.executable, str(busy_file)],
        env=env,
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    line = holder.stdout.readline().decode(
        "utf-8",
        errors="replace",
    ).strip()
    assert line == "HELD"

    from simulation.persistence.process_lock import (
        EventStoreBusyError,
        _ProcessFileLock,
    )

    lock = _ProcessFileLock(events, timeout=1.0)
    try:
        lock.acquire()
        assert False, "must fail closed on a stuck holder"
    except EventStoreBusyError:
        pass

    holder.kill()
    holder.wait(timeout=30)
