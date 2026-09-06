"""Tanuq runtime assembly — governed-by-default, anchored-by-default.

This module ONLY composes existing, tested core primitives:

- ``EventStore`` with a keyed ``ChainAnchor`` (anchor always ACTIVE in
  the product; key from ``~/.tanuq/keys/``, generated at init via the
  existing ``generate_key_bytes``).
- ``Kernel`` + ``WorkerEvidenceRecorder`` (evidence into the
  hash-chained event store).
- ``GovernanceEvaluator`` (single deterministic risk authority).
- ``ApprovalLedger`` (keyed anchored) + ``ApprovalStore``.
- ``ApplyOutcomeJournal`` (secret-safe apply evidence).
- ``WorkerActionPipeline`` with a non-empty authoritative scope
  (fail-closed; the pipeline is apply-capable only within the
  configured allowed paths).

No security primitive is reimplemented here.
"""
from pathlib import Path

from simulation.agent.apply.apply_outcome_journal import ApplyOutcomeJournal
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
)
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.security.governance_evaluator import GovernanceEvaluator

from tanuq.config import (
    ANCHOR_FILE_NAME,
    APPLY_JOURNAL_FILE_NAME,
    DUMMY_TEST_FILE_NAME,
    EVENTS_FILE_NAME,
    LEDGER_ANCHOR_FILE_NAME,
    LEDGER_FILE_NAME,
    TanuqNotInitialized,
    tanuq_data_dir,
    load_config,
    read_anchor_key,
    resolve_workspace,
)

DUMMY_TEST_CONTENT = "def test_tanuq_dummy():\n    assert True\n"


class WorkspaceEnvironment:

    def __init__(self, workspace: Path, config, store, kernel, recorder,
                 governance, approval_store, apply_journal, pipeline):
        self.workspace = workspace
        self.config = config
        self.store = store
        self.kernel = kernel
        self.recorder = recorder
        self.governance = governance
        self.approval_store = approval_store
        self.apply_journal = apply_journal
        self.pipeline = pipeline

    @property
    def data_dir(self) -> Path:
        return tanuq_data_dir(self.workspace)

    def ensure_dummy_test(self) -> Path:
        dummy = self.data_dir / DUMMY_TEST_FILE_NAME
        if not dummy.exists():
            dummy.parent.mkdir(parents=True, exist_ok=True)
            dummy.write_text(DUMMY_TEST_CONTENT, encoding="utf-8")
        return dummy


def load_environment(workspace=None) -> WorkspaceEnvironment:
    from tanuq.config import migrate_legacy_device_home
    migrate_legacy_device_home()
    ws = resolve_workspace(workspace)
    config = load_config(ws)
    key = read_anchor_key(ws)
    data_dir = tanuq_data_dir(ws)
    data_dir.mkdir(parents=True, exist_ok=True)

    store = EventStore(
        path=str(data_dir / EVENTS_FILE_NAME),
        anchor_path=str(data_dir / ANCHOR_FILE_NAME),
        anchor_key=key,
    )
    kernel = Kernel(store)
    recorder = WorkerEvidenceRecorder(kernel)
    governance = GovernanceEvaluator()
    ledger = ApprovalLedger(
        path=str(data_dir / LEDGER_FILE_NAME),
        anchor_path=str(data_dir / LEDGER_ANCHOR_FILE_NAME),
        anchor_key=key,
    )
    approval_store = ApprovalStore(
        evidence_recorder=recorder,
        ledger=ledger,
    )
    apply_journal = ApplyOutcomeJournal(
        path=str(data_dir / APPLY_JOURNAL_FILE_NAME)
    )
    pipeline = WorkerActionPipeline(
        evidence_recorder=recorder,
        governance=governance,
        approval_store=approval_store,
        apply_journal=apply_journal,
        scope=config.allowed_paths,
    )
    return WorkspaceEnvironment(
        workspace=ws,
        config=config,
        store=store,
        kernel=kernel,
        recorder=recorder,
        governance=governance,
        approval_store=approval_store,
        apply_journal=apply_journal,
        pipeline=pipeline,
    )


def environment_or_error(workspace=None):
    try:
        return load_environment(workspace)
    except TanuqNotInitialized as exc:
        raise SystemExit(f"Tanuq: {exc}")
