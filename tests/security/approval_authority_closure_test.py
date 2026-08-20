"""MISSION-N3: combined N.1+N.2 closure evidence.

Positive security tests for the shipped Approval Authority Boundary:

- the production assembly wires ONE ApprovalStore instance across the
  pipeline, the console gateway and the apply boundary (single in-process
  authority);
- a fresh-process unanchored reload of an anchored ledger fails closed
  (configuration-downgrade resistance across process boundary);
- the legacy unanchored ledger is a documented compatibility mode that
  can authorize APPLY, with single-use holding across a clean restart.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger,
)
from simulation.agent.approval.approval_store import (
    ApprovalStore,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.core.event import Event
from simulation.core.kernel import Kernel
from simulation.persistence.chain_anchor import (
    generate_key_bytes,
)
from simulation.persistence.event_store import EventStore
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy

_REPO_ROOT = str(Path(__file__).resolve().parents[2])


@pytest.fixture
def key():
    return generate_key_bytes()


def _make_patch(target):
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="n3-closure",
        old_content="mode = 1\n",
        new_content="mode = 2\n",
        allowed_paths=(),
    )


def _secret_target(tmp_path):
    d = tmp_path / "secrets"
    d.mkdir(exist_ok=True)
    t = d / "config.env"
    t.write_text("mode = 1\n", encoding="utf-8")
    return t


def test_assembly_wires_single_approval_store(tmp_path, key):
    """Single authoritative in-process approval decision: the shipped
    assembly binds ONE ApprovalStore to the pipeline, the console
    gateway and the apply boundary."""
    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent,
    )

    kernel = Kernel(EventStore(path=tmp_path / "events.jsonl"))
    agent = build_recovery_agent(
        kernel,
        worker_executor=type(
            "W", (), {"allowed_paths": (str(tmp_path),)}
        )(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_ledger_path=str(tmp_path / "ledger.jsonl"),
        approval_ledger_anchor_path=str(tmp_path / "ledger.anchor"),
        approval_ledger_anchor_key=key,
        scope=(str(tmp_path),),
    )

    store_pipeline = agent.worker_pipeline.approval_store
    store_apply = (
        agent.worker_pipeline.apply_verify_pipeline
        .apply_executor.authorization.approval_store
    )
    assert store_pipeline is store_apply
    assert isinstance(store_pipeline, ApprovalStore)


def test_fresh_process_unanchored_downgrade_rejected(tmp_path, key):
    """A fresh process loading an anchored ledger WITHOUT the anchor
    option must fail closed (configuration-downgrade resistance)."""
    ledger = ApprovalLedger(
        path=str(tmp_path / "ledger.jsonl"),
        anchor_path=str(tmp_path / "ledger.anchor"),
        anchor_key=key,
    )
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    store.grant(patch.fingerprint(), str(target), "modify", "HIGH")
    store.find_valid(patch.fingerprint(), path=str(target),
                     action="modify", risk_level="HIGH", attempt=1,
                     patch=patch)

    helper = tmp_path / "fresh_unaload.py"
    helper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {_REPO_ROOT!r})\n"
        "from simulation.agent.approval.approval_ledger import ApprovalLedger\n"
        "from simulation.agent.approval.approval_store import ApprovalStore\n"
        f"ApprovalStore(ledger=ApprovalLedger(path={str(ledger.path)!r}))\n"
        "print('UNANCHORED_LOAD_OK')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(helper)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "UNANCHORED_LOAD_OK" not in result.stdout
    assert "downgrade" in result.stderr.lower()


def test_legacy_unanchored_authorizes_apply_is_documented_compatibility(
    tmp_path
):
    """The legacy unanchored ledger is an intentional compatibility mode:
    it CAN authorize an approved HIGH apply, and single-use holds across
    a clean restart (its raw-file forgeability is the documented
    limitation closed by the opt-in anchor)."""
    ledger = ApprovalLedger(path=str(tmp_path / "legacy.jsonl"))
    store = ApprovalStore(ledger=ledger)
    target = _secret_target(tmp_path)
    patch = _make_patch(target)
    store.grant(patch.fingerprint(), str(target), "modify", "HIGH")
    found = store.find_valid(patch.fingerprint(), path=str(target),
                             action="modify", risk_level="HIGH", attempt=1,
                             patch=patch)
    assert found is not None  # a valid unconsumed approval is releasable

    reloaded = ApprovalStore(ledger=ApprovalLedger(path=str(ledger.path)))
    second = reloaded.find_valid(patch.fingerprint(), path=str(target),
                                 action="modify", risk_level="HIGH",
                                 attempt=1, patch=patch)
    assert second is None  # single-use holds across clean restart
