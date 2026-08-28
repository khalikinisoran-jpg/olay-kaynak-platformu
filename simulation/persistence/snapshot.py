import hashlib
import json
import os
import tempfile

from pathlib import Path
from datetime import datetime, timezone


class SnapshotStore:

    """Snapshot persistence with crash-atomic writes (MISSION-019).

    A snapshot is written to a temporary file in the same directory,
    flushed + fsynced, then ``os.replace``-d over the target so a crash
    mid-write leaves either the old snapshot or the fully-written new
    one — never a truncated mix. This preserves the existing
    "unverifiable snapshot is ignored and recovery falls back to a full
    replay" semantics (``simulation/recovery/recovery_engine.py``):
    the atomic write only removes the corruption window, it does not
    change the trust model.
    """

    def __init__(
        self,
        path="data/snapshot.json"
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def save(
        self,
        state,
        last_sequence=None
    ):

        if hasattr(state, "to_dict"):

            state_data = state.to_dict()

        else:

            state_data = state

        content_hash = hashlib.sha256(
            json.dumps(
                state_data,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        snapshot = {

            "version": 2,

            "last_sequence": last_sequence,

            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "content_hash": content_hash,

            "state": state_data

        }

        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=".esp-snapshot-",
        )

        try:

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
                newline="",
            ) as f:

                json.dump(
                    snapshot,
                    f,
                    ensure_ascii=False,
                    indent=4,
                )

                f.flush()

                os.fsync(f.fileno())

            os.replace(tmp, self.path)

        except Exception:

            try:

                os.unlink(tmp)

            except OSError:

                pass

            raise

    def load(self):

        if not self.path.exists():

            return None

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)
