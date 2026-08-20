import json
import os
import threading

from pathlib import Path

from simulation.persistence.chain_anchor import (
    ChainAnchor,
)
from simulation.persistence.process_lock import (
    EventStoreBusyError,
    _ProcessFileLock,
)
from simulation.security.hash_chain import HashChain


class ApprovalLedger:

    """Durable, append-only ledger for approval authorization state.

    The ledger records three lifecycle transitions: ``grant``,
    ``consumed`` (released by ``ApprovalStore.find_valid``) and
    ``applied`` (authorized at the apply boundary by
    ``ApprovalStore.authorize_apply``). Records are hash-chained with
    the same SHA-256 primitive used by the event store so that
    corruption or naive tampering is detected on reload.

    Design note (D-012 / MISSION-014 test_m): the worker evidence
    events remain *evidence only* and are never an authorization
    input. This ledger is a separate, minimal persistence file owned by
    the approval authority itself, so durability is achieved without
    turning evidence events into authorization state.

    Load is fail-closed: a missing, malformed, or hash-broken ledger
    raises ``RuntimeError`` so the store refuses to operate on
    corruption.

    MISSION-N1 trust anchor (optional): when ``anchor_path`` is
    provided, the ledger chain head is additionally anchored by the
    same external keyed ``ChainAnchor`` used for the event store. The
    unkeyed SHA-256 chain alone is forgeable/truncatable by any actor
    who can rewrite the ledger file (GAP-N-01 / AP-P13): removing a
    consumed record yields a consistent prefix that reloads as if the
    approval were still available. The keyed anchor closes that for the
    anchored ledger:

    - every ``_append`` (grant / consumed / applied) also anchors the
      new ledger head (record count + current hash) AFTER the record is
      durably fsynced, mirroring the event store's fsync-before-anchor
      ordering;
    - ``load()`` verifies the unkeyed chain AND, when anchored, the
      anchor: any truncated / modified / forged / reordered ledger whose
      tail no longer matches the anchored head fails closed
      (``RuntimeError``);
    - a missing or wrong key fails closed (``ChainAnchorError``).

    With no ``anchor_path`` the ledger behaves exactly as before
    (legacy unanchored mode): consistent tail truncation / rewind of
    the ledger is not detectable (documented limitation; security-
    sensitive deployments must enable the anchor).

    Freshness limitation (documented, same as the event store O.5): a
    consistent rewind of BOTH the ledger and the anchor file to a state
    that was genuinely legitimately anchored is accepted. The anchor
    authenticates a ledger head; it does not prove the head is the
    newest authorized head.
    """

    TYPE_GRANT = "grant"
    TYPE_CONSUMED = "consumed"
    TYPE_APPLIED = "applied"
    TYPE_ANCHORED = "anchored"

    def __init__(
        self,
        path="data/approval_ledger.jsonl",
        anchor_path=None,
        anchor_key=None,
        anchor_key_path=None
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.path.touch(
            exist_ok=True
        )

        self._lock = threading.Lock()

        self._process_lock = _ProcessFileLock(
            self.path,
            timeout=_ProcessFileLock.DEFAULT_TIMEOUT,
        )

        self._file_size = 0

        self.anchor = None

        if anchor_path is not None:

            self.anchor = ChainAnchor(
                path=anchor_path,
                anchor_key=anchor_key,
                anchor_key_path=anchor_key_path,
            )

        with self._process_lock:

            self._tail_hash, self._record_count, has_marker = (
                self._read_tail_hash()
            )

            self._file_size = self._snapshot_file_size()

            if (
                self.anchor is not None
                and self._record_count == 0
            ):

                # MISSION-N2: a fresh anchored ledger records its anchoring
                # intent with a marker record so that a later START WITHOUT
                # the anchor option fails closed (configuration-downgrade
                # protection). The marker is part of the chain and is
                # itself anchored. An unanchored load of a ledger carrying
                # this marker is refused (see ``load``).
                self._append_locked({
                    "record_type": self.TYPE_ANCHORED,
                    "reason": "ledger created anchored",
                })

    def _read_tail_hash(self):

        last_hash = "GENESIS"

        count = 0

        has_marker = False

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line_number, line in enumerate(
                f,
                start=1,
            ):

                if not line.strip():

                    continue

                try:

                    record = json.loads(line)

                except ValueError as exc:

                    raise RuntimeError(
                        "Approval ledger is corrupted at "
                        f"line {line_number}: {exc}"
                    ) from exc

                last_hash = record.get(
                    "current_hash",
                    last_hash,
                )

                count += 1

                if record.get(
                    "record_type"
                ) == self.TYPE_ANCHORED:

                    has_marker = True

        return last_hash, count, has_marker

    def append_grant(self, approval):

        body = {
            "record_type": self.TYPE_GRANT,
            "approval_id": approval.approval_id,
            "patch_fingerprint": approval.patch_fingerprint,
            "path": approval.path,
            "action": approval.action,
            "risk_level": approval.risk_level,
            "attempt": approval.attempt,
            "authorizer": approval.authorizer,
            "created_at": approval.created_at,
            "expires_at": approval.expires_at,
        }

        self._append(body)

    def append_consumed(
        self,
        approval_id,
        patch_fingerprint
    ):

        self._append({
            "record_type": self.TYPE_CONSUMED,
            "approval_id": approval_id,
            "patch_fingerprint": patch_fingerprint,
        })

    def append_applied(
        self,
        approval_id,
        patch_fingerprint
    ):

        self._append({
            "record_type": self.TYPE_APPLIED,
            "approval_id": approval_id,
            "patch_fingerprint": patch_fingerprint,
        })

    def _snapshot_file_size(self):

        try:

            return os.path.getsize(self.path)

        except OSError:

            return 0

    def _sync_if_stale(self):

        """Re-read the ledger tail when another writer grew the file.

        Called UNDER the process lock, so check-and-resync is atomic
        with respect to cooperating ApprovalLedger writers. Single-writer
        fast path is getsize no-op.
        """

        current_size = self._snapshot_file_size()

        if current_size == self._file_size:

            return

        self._tail_hash, self._record_count, _ = (
            self._read_tail_hash()
        )

        self._file_size = current_size

    def _append_locked(self, body):

        """Inner append without acquiring locks (caller holds both)."""

        body["previous_hash"] = self._tail_hash

        body["current_hash"] = HashChain.calculate(
            body
        )

        line = (
            json.dumps(
                body,
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

            try:

                os.fsync(f.fileno())

            except OSError:

                pass

        self._tail_hash = body["current_hash"]

        self._record_count += 1

        self._file_size = self._snapshot_file_size()

        if self.anchor is not None:

            self.anchor.anchor(
                self._record_count,
                body["current_hash"],
            )

    def _append(self, body):

        with self._lock:

            with self._process_lock:

                self._sync_if_stale()

                self._append_locked(body)

    def _read_verified(self):

        """Parse the ledger file and verify the unkeyed hash chain.

        Returns the records in append order. Any parse error, broken
        link or recomputed hash mismatch raises ``RuntimeError``. This
        is the pre-anchor integrity check; ``load`` additionally
        verifies the keyed anchor when one is configured.
        """

        records = []

        previous_hash = "GENESIS"

        if not self.path.exists():

            return records

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line_number, line in enumerate(
                f,
                start=1,
            ):

                if not line.strip():

                    continue

                try:

                    record = json.loads(line)

                except ValueError as exc:

                    raise RuntimeError(
                        "Approval ledger is corrupted at "
                        f"line {line_number}: {exc}"
                    ) from exc

                if not isinstance(record, dict):

                    raise RuntimeError(
                        "Approval ledger record at line "
                        f"{line_number} is not an object."
                    )

                if record.get(
                    "previous_hash"
                ) != previous_hash:

                    raise RuntimeError(
                        "Approval ledger chain link broken "
                        f"at line {line_number}."
                    )

                body = {
                    key: value
                    for key, value in record.items()
                    if key != "current_hash"
                }

                if HashChain.calculate(
                    body
                ) != record.get("current_hash"):

                    raise RuntimeError(
                        "Approval ledger hash mismatch at "
                        f"line {line_number}."
                    )

                previous_hash = record["current_hash"]

                records.append(record)

        return records

    def load(self):

        """Fail-closed reload of all ledger records.

        Returns the records in append order after verifying the hash
        chain from GENESIS. Any parse error, broken link or recomputed
        hash mismatch raises ``RuntimeError``.

        When a keyed anchor is configured, the anchored ledger head must
        exactly match the current ledger tail (sequence and hash); any
        truncation, modification, forgery, reordering or anchor rollback
        raises ``RuntimeError`` so the store refuses to operate on
        tampered authorization state.

        When NO anchor is configured, a ledger that carries an
        ``anchored`` marker is refused: the ledger was previously
        created or re-anchored under a keyed anchor, so an unanchored
        start is a configuration downgrade and fails closed instead of
        silently weakening the approval boundary.
        """

        # MISSION-N6: load under process lock to avoid torn read during
        # concurrent append (ledger+anchor not yet both fsynced).
        with self._process_lock:

            self._sync_if_stale()

            records = self._read_verified()

            if self.anchor is None:

                if any(
                    record.get("record_type") == self.TYPE_ANCHORED
                    for record in records
                ):

                    raise RuntimeError(
                        "Approval ledger was previously anchored; "
                        "refusing to load it without the anchor "
                        "(configuration downgrade). Construct the "
                        "ledger with anchor_path= and the matching "
                        "key."
                    )

            else:

                tail_sequence = len(records)

                tail_hash = (
                    records[-1]["current_hash"]
                    if records
                    else "GENESIS"
                )

                if not self.anchor.verify(
                    tail_sequence,
                    tail_hash,
                ):

                    raise RuntimeError(
                        "Approval ledger anchor verification failed: "
                        "the anchored ledger head does not match the "
                        "ledger tail (truncation, forgery or anchor "
                        "rollback detected)."
                    )

            return records

    def reanchor_from_ledger(self):

        """Operator procedure to bring the ledger under the anchor.

        Rebuilds the anchor file from scratch to match the current
        (chain-verified) ledger head. Use once when enabling an anchor
        on an existing unanchored ledger, or after key rotation. This
        is an explicit, non-destructive operator step; the mission never
        performs it automatically.

        Trust boundary: reanchor requires possession of the anchor key
        (the ``ChainAnchor`` refuses to construct without it). It is a
        key-gated operator recovery operation, NOT an authorization
        operation: it re-keys whatever the current ledger chain states.
        It must only be run on a ledger the operator trusts.
        """

        if self.anchor is None:

            raise RuntimeError(
                "Approval ledger reanchor requires an anchor; "
                "construct the ledger with anchor_path=."
            )

        records = self._read_verified()

        if not any(
            record.get("record_type") == self.TYPE_ANCHORED
            for record in records
        ):

            self._append({
                "record_type": self.TYPE_ANCHORED,
                "reason": "operator reanchor",
            })

            records = self._read_verified()

        tail_sequence = len(records)

        tail_hash = (
            records[-1]["current_hash"]
            if records
            else "GENESIS"
        )

        self.anchor.reanchor(
            tail_sequence,
            tail_hash,
        )

        self._record_count = tail_sequence

        self._tail_hash = tail_hash

        return tail_sequence
