"""MISSION-019: crash-window / fault-injection tests.

Covers the seven crash windows defined by the mission:

1. approval consumed -> process death -> apply never happened
2. apply started -> process death -> no evidence
3. apply succeeded -> death before verification
4. verification failed -> death during rollback
5. rollback completed -> death before evidence
6. event append succeeded -> reducer failure
7. snapshot save -> process death (atomicity)

Controlled crash simulation is done by writing only part of the
journal/ledger lifecycle (never by killing real processes) so the tests
are deterministic and safe. The invariant asserted everywhere: after a
restart the system can *detect* the orphan, and a mutation can never
exist silently without a durable outcome record.
"""

import json

import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_outcome_journal import (
    TYPE_APPLIED,
    TYPE_APPLY_STARTED,
    TYPE_ROLLBACK_STARTED,
    ApplyOutcomeJournal,
)
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller_decision import (
    ControllerDecision
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)
from simulation.agent.recovery.startup_reconciliation import (
    CLASS_ORPHANED_APPLIED,
    CLASS_ORPHANED_APPLY_START,
    CLASS_ORPHANED_ROLLBACK,
    CLASS_SUCCESS,
    CLASS_ROLLED_BACK,
    ReconciliationEngine,
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.core.kernel import Kernel
from simulation.core.event import Event
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.recovery.recovery_engine import RecoveryEngine
from simulation.core.reducer import Reducer


def make_patch(tmp_path, name="data_file.txt"):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Fault injection test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def approved_decision(patch):
    return ControllerDecision(
        approved=True,
        reason="Fault injection test.",
        patch_fingerprint=patch.fingerprint(),
    )


class PassingVerification:
    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="ok",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
        )


class FailingVerification:
    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=FAIL,
            exit_code=1,
            stdout="",
            stderr="boom",
            command=("python", "-m", "pytest", "-q"),
        )


# ---------------------------------------------------------------------------
# Window 1: approval consumed -> process death -> apply never happened.
# The ledger shows a consumed approval with no journal intent at all.
# ---------------------------------------------------------------------------

def test_window1_consumed_approval_without_apply_is_flagged(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    store = ApprovalStore()
    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-test",
        expires_at=3600,
    )
    store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
        approval_store=store,
    ).detect()

    assert approval.approval_id in (
        report.consumed_approvals_without_outcome
    )


# ---------------------------------------------------------------------------
# Window 2: apply started -> process death before APPLIED.
# ---------------------------------------------------------------------------

def test_window2_apply_started_orphan_detected(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    intent_id = journal.record_intent(patch, attempt=1)
    journal.record_apply_started(intent_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert report.orphaned_mutations
    assert report.orphaned_mutations[0].classification == (
        CLASS_ORPHANED_APPLY_START
    )
    assert report.orphaned_mutations[0].mutation_present is False


# ---------------------------------------------------------------------------
# Window 3: apply succeeded -> death before verification.
# ---------------------------------------------------------------------------

def test_window3_applied_without_verify_is_orphan(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    executor = ApplyExecutor(journal=journal)
    result = executor.apply(patch, approved_decision(patch))
    assert result.success is True

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1
    assert report.orphaned_mutations[0].classification == (
        CLASS_ORPHANED_APPLIED
    )
    assert report.orphaned_mutations[0].mutation_present is True


# ---------------------------------------------------------------------------
# Window 4: verification failed -> death during rollback.
# ---------------------------------------------------------------------------

def test_window4_rollback_started_orphan_detected(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    executor = ApplyExecutor(journal=journal)
    result = executor.apply(patch, approved_decision(patch))
    journal.record_rollback_started(result.intent_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1
    assert report.orphaned_mutations[0].classification == (
        CLASS_ORPHANED_ROLLBACK
    )


# ---------------------------------------------------------------------------
# Window 5: rollback completed -> death before evidence event.
# The journal holds the terminal ROLLED_BACK outcome, so reconciliation
# reports a clean terminal state even though no evidence event exists.
# ---------------------------------------------------------------------------

def test_window5_rollback_complete_is_terminal_not_orphan(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(journal=journal),
        verification_executor=FailingVerification(),
        journal=journal,
    )
    result = pipeline.execute(patch, approved_decision(patch))
    assert result.rollback is not None
    assert result.rollback.success is True

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert report.orphaned_mutations == ()
    assert report.intents[0].classification == CLASS_ROLLED_BACK
    assert report.intents[0].terminal is True


# ---------------------------------------------------------------------------
# Window 6: event appended but reducer raised -> restart replays it.
# Documented semantic (MISSION-019): the event store is authoritative;
# a reducer failure is not rolled back and restart replay applies it.
# ---------------------------------------------------------------------------

def test_window6_reducer_failure_persists_event_and_replays(tmp_path):
    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        interval=1_000_000,
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        ),
    )

    kernel = Kernel(
        store,
        snapshot_manager=snapshot_manager,
    )

    bad_event = Event(
        event_type="TaskCreated",
        payload={},
    )

    with pytest.raises(KeyError):
        kernel.dispatch(bad_event)

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert len(records) == 1
    assert records[0]["event_type"] == "TaskCreated"

    assert kernel.event_count() == 0

    with pytest.raises(KeyError):
        RecoveryEngine(
            event_store=store,
            snapshot_store=SnapshotStore(
                path=tmp_path / "snapshot.json"
            ),
            reducer=Reducer(),
        ).recover()


# ---------------------------------------------------------------------------
# Window 7: snapshot save crash must leave the old snapshot intact.
# ---------------------------------------------------------------------------

def test_window7_snapshot_write_crash_preserves_old_snapshot(
    tmp_path,
    monkeypatch,
):
    from simulation.core.state import State

    snapshot_store = SnapshotStore(
        path=tmp_path / "snapshot.json"
    )

    first_state = State(
        memory={"a": "1"},
        event_counter=2,
    )

    snapshot_store.save(
        first_state,
        last_sequence=2,
    )

    before = snapshot_store.path.read_text(encoding="utf-8")

    def exploding_replace(src, dst):
        raise OSError("simulated crash during replace")

    monkeypatch.setattr(
        "simulation.persistence.snapshot.os.replace",
        exploding_replace,
    )

    second_state = State(
        memory={"a": "2"},
        event_counter=4,
    )

    with pytest.raises(OSError):
        snapshot_store.save(
            second_state,
            last_sequence=4,
        )

    after = snapshot_store.path.read_text(encoding="utf-8")

    assert after == before

    loaded = snapshot_store.load()
    assert loaded["state"]["event_counter"] == 2


# ---------------------------------------------------------------------------
# Full restart reconciliation: an end-to-end crash leaves an orphan that a
# fresh process detects without mutating anything.
# ---------------------------------------------------------------------------

def test_restart_reconciliation_detects_orphan_end_to_end(tmp_path):
    journal_path = tmp_path / "apply_journal.jsonl"

    journal = ApplyOutcomeJournal(path=journal_path)
    patch = make_patch(tmp_path)

    executor = ApplyExecutor(journal=journal)
    result = executor.apply(patch, approved_decision(patch))
    assert result.success is True

    restarted = ApplyOutcomeJournal(path=journal_path)

    report = ReconciliationEngine(
        journal=restarted,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1

    with open(
        tmp_path / "data_file.txt",
        "r",
        encoding="utf-8",
    ) as f:
        content = f.read()

    assert content == "value = 2\n"


# ---------------------------------------------------------------------------
# A successfully verified apply leaves a complete, non-orphan outcome that
# survives a simulated restart (no mutation ever lacks a durable outcome).
# ---------------------------------------------------------------------------

def test_complete_apply_has_durable_outcome_across_restart(tmp_path):
    journal_path = tmp_path / "apply_journal.jsonl"

    journal = ApplyOutcomeJournal(path=journal_path)
    patch = make_patch(tmp_path)

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(journal=journal),
        verification_executor=PassingVerification(),
        journal=journal,
    )
    result = pipeline.execute(patch, approved_decision(patch))
    assert result.success is True

    restarted = ApplyOutcomeJournal(path=journal_path)

    report = ReconciliationEngine(
        journal=restarted,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert report.orphaned_mutations == ()
    assert report.intents[0].classification == CLASS_SUCCESS
    assert report.intents[0].terminal is True
