"""Cross-process single-writer enforcement for the event store (MISSION-O).

The per-process ``threading.Lock`` in ``EventStore`` serializes threads
WITHIN one process only. Two OS processes sharing one event-store file
both cache the same tail and therefore allocate the same sequence
(duplicate sequence / lost update / broken chain), which MISSION-N.1
reproduced deterministically.

``_ProcessFileLock`` adds an OS-level advisory lock over the append
critical section (read tail -> allocate -> write record -> update
anchor):

- Windows: ``msvcrt.locking`` (``LK_NBLCK`` / ``LK_UNLCK``).
- POSIX:   ``fcntl.flock`` (``LOCK_EX | LOCK_NB`` / ``LOCK_UN``).

Properties:

- Bounded: a writer waits up to ``timeout`` for the holder, then fails
  with ``EventStoreBusyError`` (FAIL CLOSED, never a permanent
  deadlock). Cooperating writers serialize and both succeed.
- Crash-safe: the OS releases the lock automatically when the holder
  process terminates, so a crashed writer never leaves a stale lock.
- The lock is advisory: only writers that honour it are protected,
  which is exactly the set of ``EventStore`` instances (all appends
  go through this primitive). It is a WRITE-exclusion mechanism, NOT
  a security boundary: it prevents corruption among cooperating
  writers, it does not authenticate them.
- No-op on platforms with neither ``msvcrt`` nor ``fcntl`` (documented
  limitation: cross-process protection unavailable there).
"""

import os
import threading
import time

from pathlib import Path


try:

    import msvcrt

    _HAS_MSVCRT = True

except ImportError:

    _HAS_MSVCRT = False

    msvcrt = None


try:

    import fcntl

    _HAS_FCNTL = True

except ImportError:

    _HAS_FCNTL = False

    fcntl = None


class EventStoreBusyError(RuntimeError):

    """Raised when the store lock cannot be acquired within the timeout.

    The caller fails closed: no partial write, no silent corruption.
    """


class _ProcessFileLock:

    """Non-blocking-with-bounded-retry OS file lock over a lock file.

    The lock file is a sidecar ``<events>.lock`` containing one marker
    byte. It is only the *lock region*; it never carries event data or
    anchor key material.
    """

    DEFAULT_TIMEOUT = 5.0

    RETRY_SLEEP = 0.01

    def __init__(self, events_path, timeout=DEFAULT_TIMEOUT):

        self._events_path = Path(events_path)

        self._lock_path = self._events_path.with_name(
            self._events_path.name + ".lock"
        )

        self._lock_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not self._lock_path.exists():

            try:

                self._lock_path.write_bytes(b"\x00")

            except OSError:

                pass

        self.timeout = float(timeout)

        self._fd = None

        self._acquired = False

        self._guard = threading.Lock()

    @property
    def lock_path(self):

        return self._lock_path

    def _open_fd(self):

        try:

            return os.open(
                str(self._lock_path),
                os.O_RDWR,
            )

        except OSError as exc:

            raise EventStoreBusyError(
                f"Could not open the event-store lock file "
                f"({self._lock_path}): {exc}"
            )

    def _try_lock(self, fd):

        if _HAS_MSVCRT:

            os.lseek(fd, 0, os.SEEK_SET)

            msvcrt.locking(
                fd,
                msvcrt.LK_NBLCK,
                1,
            )

        elif _HAS_FCNTL:

            fcntl.flock(
                fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

        else:

            return False

        return True

    def _try_unlock(self, fd):

        if _HAS_MSVCRT:

            os.lseek(fd, 0, os.SEEK_SET)

            msvcrt.locking(
                fd,
                msvcrt.LK_UNLCK,
                1,
            )

        elif _HAS_FCNTL:

            fcntl.flock(
                fd,
                fcntl.LOCK_UN,
            )

    def acquire(self):

        """Acquire the lock with bounded retry, or fail closed."""

        with self._guard:

            if self._acquired:

                return

            fd = self._open_fd()

            deadline = time.monotonic() + self.timeout

            while True:

                try:

                    if self._try_lock(fd):

                        self._fd = fd

                        self._acquired = True

                        return

                except OSError:

                    pass

                if time.monotonic() >= deadline:

                    os.close(fd)

                    raise EventStoreBusyError(
                        "Another process is writing this event store; "
                        "single-writer required (lock timeout exceeded)."
                    )

                time.sleep(self.RETRY_SLEEP)

    def release(self):

        if not self._acquired:

            return

        with self._guard:

            if not self._acquired:

                return

            try:

                self._try_unlock(self._fd)

            except OSError:

                pass

            finally:

                try:

                    os.close(self._fd)

                except OSError:

                    pass

                self._fd = None

                self._acquired = False

    def __enter__(self):

        self.acquire()

        return self

    def __exit__(self, exc_type, exc, tb):

        self.release()

        return False
