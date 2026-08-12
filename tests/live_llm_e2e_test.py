import os
import sys

import pytest

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger
)
from simulation.agent.approval.approval_store import (
    ApprovalStore
)
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)
from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine
)
from simulation.agent.verify.verification_executor import (
    VerificationExecutor
)
from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


pytestmark = pytest.mark.live_llm

REQUIRES_LIVE_LLM = (
    os.getenv("RUN_LIVE_LLM") != "1"
)

LIVE_REASON = (
    "RUN_LIVE_LLM=1 required; this test drives the real LLM "
    "through the governed apply/verify pipeline and may incur "
    "API cost. Run deliberately with: "
    "python -m pytest -m live_llm tests/live_llm_e2e_test.py -q"
)


def build_isolated_kernel(tmp_path):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        )
    )

    return (
        Kernel(
            store,
            snapshot_manager=snapshot_manager,
        ),
        store,
    )


@pytest.mark.skipif(
    REQUIRES_LIVE_LLM,
    reason=LIVE_REASON,
)
def test_live_llm_governed_apply_verify_evidence(tmp_path):

    src = tmp_path / "app.py"

    original = (
        "def add(a, b):\n"
        "    return a - b\n"
    )

    src.write_text(original, encoding="utf-8")

    test = tmp_path / "test_app.py"

    test.write_text(
        "from app import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    approval_store = ApprovalStore(
        evidence_recorder=recorder,
        ledger=ApprovalLedger(
            path=tmp_path / "ledger.jsonl"
        ),
    )

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(),
        allowed_paths=(str(src),),
    )

    verification_executor = VerificationExecutor(
        python_executable=sys.executable,
        timeout=120,
        cwd=str(tmp_path),
    )

    pipeline = WorkerActionPipeline(
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=approval_store,
        evidence_recorder=recorder,
        apply_verify_pipeline=ApplyVerifyPipeline(
            verification_executor=verification_executor,
        ),
    )

    engine = BoundedRecoveryEngine(
        worker=worker_executor,
        worker_pipeline=pipeline,
        max_attempts=3,
        evidence_recorder=recorder,
    )

    result = engine.execute(
        agent=None,
        prompt=(
            "worker: the add function is wrong; "
            "it must return the sum of a and b."
        ),
        verify_paths=(str(src), str(test)),
        test_targets=(str(test),),
    )

    assert result.success is True, (
        f"Live LLM governed E2E failed: "
        f"{result.failure_reason}"
    )

    fixed = src.read_text(encoding="utf-8")

    assert fixed != original

    assert "a + b" in fixed

    records = [
        line
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert records

    import json

    event_types = {
        json.loads(line)["event_type"]
        for line in records
    }

    assert "WorkerPatchApplied" in event_types

    assert "WorkerVerificationCompleted" in event_types
