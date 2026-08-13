from simulation.agent.approval.approval import Approval

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger,
)


class ApprovalStore:

    """Fingerprint-keyed, single-use human-approval authority.

    The store is the durable authority behind the pipeline's
    STAGE_APPROVAL. It implements the ``find_valid`` contract the
    pipeline already consumes and binds every returned approval to
    the full authorization context: patch fingerprint, path, action,
    risk level and attempt.

    Fail-closed rules:

    - Missing approval -> ``None`` (deny).
    - Expired approval -> ``None`` (deny).
    - Already-consumed approval -> ``None`` (replay denied).
    - Wrong fingerprint / path / action / risk level / attempt ->
      ``None`` (substitution denied).
    - Every granted approval is single-use: ``find_valid`` consumes it
      once, so the same approval can never authorize two executions.

    Durability: when an ``ApprovalLedger`` is supplied, every grant /
    consume / apply transition is appended to the ledger and the store
    reloads its authorization state from the ledger on construction, so
    a consumed or applied approval stays consumed after a process
    restart. The ledger is fail-closed: corrupted or hash-broken state
    raises ``RuntimeError``. The worker evidence events stay evidence
    only (D-012 / MISSION-014 test_m) and are never authorization
    input.
    """

    def __init__(
        self,
        evidence_recorder=None,
        ledger=None
    ):

        self.evidence_recorder = evidence_recorder

        self.ledger = ledger

        self._approvals = {}

        self._by_fingerprint = {}

        self._consumed = set()

        self._bindings = {}

        self._applied = set()

        if ledger is not None:

            self._reload_from_ledger()

    def _reload_from_ledger(self):

        records = self.ledger.load()

        for record in records:

            record_type = record.get(
                "record_type"
            )

            if record_type == ApprovalLedger.TYPE_GRANT:

                approval = Approval(
                    approval_id=record["approval_id"],
                    patch_fingerprint=record[
                        "patch_fingerprint"
                    ],
                    path=record["path"],
                    action=record["action"],
                    risk_level=record["risk_level"],
                    attempt=record["attempt"],
                    authorizer=record["authorizer"],
                    created_at=record["created_at"],
                    expires_at=record.get(
                        "expires_at",
                        "",
                    ),
                )

                self._approvals[
                    approval.approval_id
                ] = approval

                self._by_fingerprint.setdefault(
                    approval.patch_fingerprint,
                    [],
                ).append(approval.approval_id)

            elif record_type == (
                ApprovalLedger.TYPE_CONSUMED
            ):

                self._consumed.add(
                    record["approval_id"]
                )

            elif record_type == (
                ApprovalLedger.TYPE_APPLIED
            ):

                self._applied.add(
                    record["approval_id"]
                )

            else:

                raise RuntimeError(
                    "Approval ledger contains an unknown "
                    f"record type: {record_type!r}"
                )

    def grant(
        self,
        patch_fingerprint,
        path,
        action,
        risk_level,
        attempt=1,
        authorizer="human",
        expires_at=None,
        approval=None,
    ) -> Approval:

        """Authorize a patch and persist the authorization evidence.

        Returns the immutable ``Approval``. The approval is bound to
        the full context passed here; ``find_valid`` will only release
        it for the exact same context.
        """

        if approval is None:

            approval = Approval.create(
                patch_fingerprint=patch_fingerprint,
                path=path,
                action=action,
                risk_level=risk_level,
                attempt=attempt,
                authorizer=authorizer,
                expires_at=expires_at,
            )

        if approval.patch_fingerprint != patch_fingerprint:

            raise ValueError(
                "Approval fingerprint does not match the "
                "granted fingerprint."
            )

        self._approvals[approval.approval_id] = approval

        self._by_fingerprint.setdefault(
            approval.patch_fingerprint,
            [],
        ).append(approval.approval_id)

        if self.evidence_recorder is not None:

            self.evidence_recorder.record_approval_granted(
                approval
            )

        if self.ledger is not None:

            self.ledger.append_grant(approval)

        return approval

    def find_valid(
        self,
        fingerprint,
        path=None,
        action=None,
        risk_level=None,
        attempt=None,
        patch=None
    ):

        """Return a single-use approval matching the full context.

        ``None`` is returned (deny) unless a granted, unexpired,
        unconsumed approval matches every binding field. A human
        approval query must carry the complete authorization context:
        missing fingerprint, path, action, risk level or attempt fails
        closed. Consuming happens on a successful match: the approval
        cannot be replayed.

        When the exact ``patch`` object is supplied, the approval is
        also bound to that object; the apply authorization boundary
        later requires that same object, so an approval consumed for
        one patch object can never authorize a different object with
        identical-looking metadata.
        """

        if not fingerprint:

            return None

        if (
            path is None
            or action is None
            or risk_level is None
            or attempt is None
        ):

            return None

        for approval_id in self._by_fingerprint.get(
            fingerprint,
            (),
        ):

            if approval_id in self._consumed:

                continue

            approval = self._approvals[approval_id]

            if approval.is_expired():

                continue

            if approval.path != path:

                continue

            if approval.action != action:

                continue

            if approval.risk_level != risk_level:

                continue

            if approval.attempt != attempt:

                continue

            self._consumed.add(approval_id)

            if patch is not None:

                self._bindings[approval_id] = patch

            if self.ledger is not None:

                self.ledger.append_consumed(
                    approval_id,
                    fingerprint,
                )

            return approval

        return None

    def authorize_apply(self, approval_id, patch) -> bool:

        """Verify an approval binding at the actual apply boundary.

        This is the narrowest enforcement point for approval authority.
        An apply is authorized ONLY when the referenced approval:

        - was granted by THIS store (unknown ids fail closed),
        - was actually released by ``find_valid`` (a forged claim
          about an unconsumed grant fails closed),
        - is bound to THIS exact patch object (a different patch
          object with identical-looking metadata fails closed),
        - has not already authorized an apply (single-use at the apply
          boundary; replay fails closed),
        - is not expired, and
        - is bound to this patch fingerprint, path and action.

        On success the approval is consumed for apply, so it can never
        authorize a second execution.
        """

        if not isinstance(approval_id, str) or not approval_id:

            return False

        if approval_id not in self._approvals:

            return False

        approval = self._approvals[approval_id]

        if approval_id not in self._consumed:

            return False

        if approval_id in self._applied:

            return False

        if self._bindings.get(approval_id) is not patch:

            return False

        if approval.is_expired():

            return False

        if approval.patch_fingerprint != patch.fingerprint():

            return False

        if approval.path != patch.path:

            return False

        if approval.action != patch.action:

            return False

        self._applied.add(approval_id)

        if self.ledger is not None:

            self.ledger.append_applied(
                approval_id,
                patch.fingerprint(),
            )

        return True

    def is_consumed(self, approval) -> bool:

        if not isinstance(approval, Approval):

            return False

        return approval.approval_id in self._consumed

    def is_consumed_id(self, approval_id) -> bool:

        """Public consumed-state lookup by approval id.

        Used by startup reconciliation to flag a consumed approval whose
        apply intent never reached a terminal outcome.
        """

        if not isinstance(approval_id, str) or not approval_id:

            return False

        return approval_id in self._consumed

    def consumed_ids(self) -> frozenset:

        """All approval ids consumed (released by ``find_valid``)."""

        return frozenset(self._consumed)

    def is_applied(self, approval) -> bool:

        if not isinstance(approval, Approval):

            return False

        return approval.approval_id in self._applied

    def __len__(self):

        return len(self._approvals)
