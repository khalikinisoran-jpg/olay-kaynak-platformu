"""External keyed chain-head trust anchor (MISSION-N).

The unkeyed SHA-256 hash chain is tamper-*evidence* but cannot detect
deletion or in-place edit of the LAST record (the tail): the tail has no
successor to reference its hash, and an actor who can edit the event
file can recompute every ``current_hash``.

``ChainAnchor`` closes that gap with an *external, keyed* anchor:

- A separate append-only anchor file stores one record per anchored
  chain head: ``anchor_id``, ``sequence``, ``current_hash`` and an
  HMAC-SHA256 tag computed with a key that never lives in the
  repository, the event file or the snapshot.
- The MAC makes the anchor unforgeable by an actor without the key. A
  tail deletion, a tail edit (even with a recomputed hash), or a
  hash-recomputed middle deletion all produce a recomputed tail that
  does NOT match the anchored head -> FAIL CLOSED.
- The anchor file itself is validated: ``anchor_id`` must be
  contiguous (rollback / truncation / gap -> FAIL CLOSED) and every
  MAC must verify under the current key.
- Authority separation: the anchor proves only "this chain head was
  previously anchored" (integrity authority). It is NEVER an input to
  approval, apply, scope, risk or worker authorization, which remain
  the sole province of the governance / approval boundary.

Key handling:

- The key is supplied by the caller (``anchor_key=``) or read from the
  environment variable ``CHAIN_ANCHOR_KEY``.
- A missing key when an anchor is enabled is FAIL CLOSED (ValueError
  at construction): an anchored store refuses to start unkeyed.
- A wrong or rotated key makes every MAC fail -> FAIL CLOSED at
  verification.
- The key must be at least 32 bytes. A hex string is unhexlified;
  any other string is used verbatim (UTF-8). Never store the key in
  the repository, tests, docs or snapshots.

Crash consistency: the event record is fsynced BEFORE the anchor
record is appended. A crash between the two leaves events beyond the
anchored head, which the next recovery rejects (FAIL CLOSED): a
partially-anchored tail is never silently trusted.
"""

import hmac
import hashlib
import json
import os
import secrets

from pathlib import Path


KEY_ENV_VAR = "CHAIN_ANCHOR_KEY"

_MIN_KEY_BYTES = 32

_GENESIS_HASH = "GENESIS"


class ChainAnchorError(RuntimeError):
    """Base class for anchor verification / construction failures."""


def load_key(anchor_key=None, anchor_key_path=None):
    """Resolve the anchor key, fail-closed when unavailable or too short.

    Order: explicit ``anchor_key``, then ``anchor_key_path``, then the
    ``CHAIN_ANCHOR_KEY`` environment variable. A hex string of at least
    64 characters is unhexlified; any other value must be at least
    32 bytes of raw material.
    """

    material = None

    if anchor_key is not None:

        material = anchor_key

    elif anchor_key_path is not None:

        path = Path(anchor_key_path)

        try:

            material = path.read_text(
                encoding="utf-8"
            ).strip()

        except OSError as exc:

            raise ChainAnchorError(
                f"Anchor key file could not be read: {exc}"
            )

    else:

        material = os.environ.get(KEY_ENV_VAR)

    if material is None or material == "":

        raise ChainAnchorError(
            "Chain anchor key is missing. Provide anchor_key= or set "
            f"the {KEY_ENV_VAR} environment variable. Missing key "
            "fails closed."
        )

    if isinstance(material, str):

        if material.startswith("hex:"):
            material = material[4:]

        stripped = material.strip()

        if (
            len(stripped) >= 64
            and all(
                char in "0123456789abcdefABCDEF"
                for char in stripped
            )
        ):
            key_bytes = bytes.fromhex(stripped)
        else:
            key_bytes = material.encode("utf-8")

    elif isinstance(material, (bytes, bytearray)):

        key_bytes = bytes(material)

    else:

        raise ChainAnchorError(
            "Chain anchor key must be a string or bytes."
        )

    if len(key_bytes) < _MIN_KEY_BYTES:

        raise ChainAnchorError(
            "Chain anchor key must be at least 32 bytes "
            f"(got {len(key_bytes)}). Short keys fail closed."
        )

    return key_bytes


class ChainAnchor:

    """Append-only, keyed anchor of the event chain head.

    Every ``anchor`` call appends one record to the anchor file. The
    anchor file is the ONLY place a valid MAC can exist, so an actor
    without the key cannot create a record that ``verify`` accepts.
    """

    def __init__(
        self,
        path="data/chain_anchor.jsonl",
        anchor_key=None,
        anchor_key_path=None
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.key = load_key(
            anchor_key=anchor_key,
            anchor_key_path=anchor_key_path,
        )

        self._tail_anchor = self._read_tail()

        self._file_size = self._snapshot_file_size()

    def _snapshot_file_size(self):

        try:

            return os.path.getsize(self.path)

        except OSError:

            return 0

    def _sync_if_stale(self):

        """Re-read the anchor tail when another writer grew the file.

        Called while the caller holds the event-store process lock, so
        check-and-resync is atomic with respect to every cooperating
        writer. Single-writer fast path is a ``getsize`` no-op.
        """

        current_size = self._snapshot_file_size()

        if current_size == self._file_size:

            return

        self._tail_anchor = self._read_tail()

        self._file_size = current_size

    def _mac(self, anchor_id, sequence, current_hash):

        message = (
            f"{anchor_id}:{sequence}:{current_hash}"
        ).encode("utf-8")

        return hmac.new(
            self.key,
            message,
            hashlib.sha256,
        ).hexdigest()

    def _read_tail(self):

        if not self.path.exists():

            return None

        last = None

        try:

            with open(
                self.path,
                "r",
                encoding="utf-8"
            ) as f:

                for line in f:

                    if not line.strip():

                        continue

                    last = json.loads(line)

        except (OSError, ValueError) as exc:

            raise ChainAnchorError(
                "Chain anchor file could not be read or parsed: "
                f"{exc}"
            )

        return last

    def anchor(
        self,
        sequence,
        current_hash
    ):

        """Append a new anchored chain head. Returns the anchor_id."""

        self._sync_if_stale()

        anchor_id = (
            self._tail_anchor.get("anchor_id", 0) + 1
            if self._tail_anchor is not None
            else 1
        )

        mac = self._mac(
            anchor_id,
            sequence,
            current_hash,
        )

        record = {
            "anchor_id": anchor_id,
            "sequence": sequence,
            "current_hash": current_hash,
            "mac": mac,
        }

        self._write_record(record)

        self._tail_anchor = record

        self._file_size = self._snapshot_file_size()

        return anchor_id

    def _write_record(self, record):

        line = (
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")

        with open(
            self.path,
            "ab"
        ) as f:

            f.write(line)

            f.flush()

            os.fsync(f.fileno())

    def _read_records(self):

        if not self.path.exists():

            return []

        records = []

        try:

            with open(
                self.path,
                "r",
                encoding="utf-8"
            ) as f:

                for line in f:

                    if not line.strip():

                        continue

                    records.append(json.loads(line))

        except (OSError, ValueError) as exc:

            raise ChainAnchorError(
                f"Chain anchor file could not be read or parsed: {exc}"
            )

        return records

    def verify(
        self,
        event_tail_sequence,
        event_tail_hash
    ):

        """Fail-closed verification of the anchored chain head.

        Returns True only when:

        - the anchor file parses and every record's MAC verifies under
          the current key,
        - ``anchor_id`` is strictly contiguous starting at 1 (no
          rollback, truncation or gap in the anchor file),
        - the LAST anchored head equals the caller-supplied event tail
          exactly (sequence AND hash).

        Any other outcome (empty store with a non-empty anchor, non-empty
        store with an empty anchor, mismatch, MAC failure, malformed
        anchor) returns False.
        """

        records = self._read_records()

        if not records:

            return (
                event_tail_sequence == 0
                and event_tail_hash == _GENESIS_HASH
            )

        for index, record in enumerate(records):

            expected_id = index + 1

            if record.get("anchor_id") != expected_id:

                return False

            sequence = record.get("sequence")

            current_hash = record.get("current_hash")

            stored_mac = record.get("mac")

            if not isinstance(sequence, int) or isinstance(
                sequence,
                bool,
            ):

                return False

            if not isinstance(current_hash, str) or not current_hash:

                return False

            if not isinstance(stored_mac, str) or not stored_mac:

                return False

            expected_mac = self._mac(
                expected_id,
                sequence,
                current_hash,
            )

            if not hmac.compare_digest(
                stored_mac,
                expected_mac,
            ):

                return False

        last = records[-1]

        return (
            last.get("sequence") == event_tail_sequence
            and last.get("current_hash") == event_tail_hash
        )

    def reanchor(
        self,
        sequence,
        current_hash
    ):

        """Rebuild the anchor file from scratch for the given head.

        Operator procedure for key rotation or for bringing an existing
        unanchored store under an anchor: clears the anchor file and
        writes one fresh anchored head under the current key.
        """

        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence < 0
        ):

            raise ChainAnchorError(
                "reanchor requires a non-negative integer sequence."
            )

        if not isinstance(current_hash, str) or not current_hash:

            raise ChainAnchorError(
                "reanchor requires a non-empty current_hash."
            )

        tmp = self.path.with_name(
            self.path.name + ".reanchor.tmp"
        )

        with open(
            tmp,
            "w",
            encoding="utf-8",
            newline="",
        ) as f:

            f.write("")

        os.replace(tmp, self.path)

        self._tail_anchor = None

        self.anchor(
            sequence,
            current_hash,
        )


def generate_key_bytes():
    """Generate a fresh 32-byte key (hex string, caller-managed).

    The caller is responsible for storing the returned key OUTSIDE the
    repository (secret store, environment, or a protected file) and for
    keeping it out of the event store, snapshots, tests and docs.
    """

    return secrets.token_hex(_MIN_KEY_BYTES)
