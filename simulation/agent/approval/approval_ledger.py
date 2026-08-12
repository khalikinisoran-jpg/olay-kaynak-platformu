import json
import os
import threading

from pathlib import Path

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
    """

    TYPE_GRANT = "grant"
    TYPE_CONSUMED = "consumed"
    TYPE_APPLIED = "applied"

    def __init__(self, path="data/approval_ledger.jsonl"):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.path.touch(
            exist_ok=True
        )

        self._lock = threading.Lock()

        self._tail_hash = self._read_tail_hash()

    def _read_tail_hash(self):

        last_hash = "GENESIS"

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

        return last_hash

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

    def _append(self, body):

        with self._lock:

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

    def load(self):

        """Fail-closed reload of all ledger records.

        Returns the records in append order after verifying the hash
        chain from GENESIS. Any parse error, broken link or recomputed
        hash mismatch raises ``RuntimeError``.
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
