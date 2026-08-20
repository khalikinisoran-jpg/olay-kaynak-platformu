"""MISSION-O: process-lock safety unit tests (in-process semantics).

The cross-process exclusion is tested with real subprocesses in
``multiprocess_concurrency_test.py``. These tests pin the in-process
contract of ``_ProcessFileLock``:

- acquire / release / re-acquire round trip
- release without acquire is a no-op
- double release is a no-op
- a second acquire while held (same instance) is a no-op
- contention fails closed with ``EventStoreBusyError`` after the
  timeout instead of deadlocking forever
"""

import pytest

from simulation.persistence.process_lock import (
    EventStoreBusyError,
    _ProcessFileLock,
)


def test_acquire_release_reacquire_round_trip(tmp_path):
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)

    lock.acquire()
    lock.release()
    lock.acquire()
    lock.release()


def test_release_without_acquire_is_noop(tmp_path):
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)
    lock.release()
    lock.release()


def test_double_release_is_noop(tmp_path):
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)
    lock.acquire()
    lock.release()
    lock.release()


def test_reacquire_while_held_same_instance_is_noop(tmp_path):
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)
    lock.acquire()
    lock.acquire()
    lock.release()
    lock.acquire()
    lock.release()


def test_context_manager_releases(tmp_path):
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)
    with lock:
        assert lock._acquired is True
    assert lock._acquired is False
    lock.acquire()
    lock.release()


def test_contention_fails_closed_after_timeout(tmp_path):
    holder = _ProcessFileLock(
        tmp_path / "events.jsonl",
        timeout=60.0,
    )
    holder.acquire()

    contender = _ProcessFileLock(
        tmp_path / "events.jsonl",
        timeout=0.2,
    )

    with pytest.raises(EventStoreBusyError):
        contender.acquire()

    assert contender._acquired is False

    holder.release()

    contender.acquire()
    contender.release()


def test_lock_is_never_a_security_boundary(tmp_path):
    """The lock is a write-exclusion mechanism; it must NOT be mistaken
    for authorization. Its file holds one marker byte and no key or
    event data."""
    lock = _ProcessFileLock(tmp_path / "events.jsonl", timeout=1.0)
    lock.acquire()
    lock.release()

    content = lock.lock_path.read_bytes()
    assert content == b"\x00"
