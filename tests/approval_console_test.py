import json

from simulation.agent.approval.approval import Approval
from simulation.agent.approval.approval_console import (
    APPROVE_PHRASES,
    ConsoleApprovalGateway,
    PendingApprovalRequest,
    build_pending_request,
    prompt_approval_decision,
)
from simulation.agent.approval.approval_ledger import (
    ApprovalLedger
)
from simulation.agent.approval.approval_store import (
    ApprovalStore
)
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.worker_result import WorkerResult
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.security.hash_verifier import HashVerifier
from simulation.security.risk_engine import (
    RiskAssessment,
    RiskEngine,
)
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected in the approval "
            "console test."
        )

    def get_model_name(self):

        return "stub"


class ScriptedVerification:

    def __init__(self, results):

        self.results = list(results)

        self.calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)


class FixedPatchWorker:

    def __init__(self, patch):

        self.patch = patch

        self.calls = 0

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        self.calls += 1

        return WorkerResult(
            task_id="console-fixed",
            success=True,
            summary="Console fixed worker.",
            patches=(self.patch,),
        )


def make_verification_result(
    status=PASS,
    exit_code=0,
    failure_reason=""
):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout="1 passed" if status == PASS else "1 failed",
        stderr="",
        command=("venv-python", "-m", "pytest", "-q"),
        failure_reason=failure_reason,
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


def make_high_patch(tmp_path):

    target = tmp_path / "settings.secret.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    return target, PatchProposal(
        path=str(target),
        action="modify",
        reason="Console HIGH proposal.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def make_critical_patch(tmp_path):

    target = tmp_path / "secrets" / "app.pem"

    target.parent.mkdir(parents=True, exist_ok=True)

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    return target, PatchProposal(
        path=str(target),
        action="modify",
        reason="Console CRITICAL proposal.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


class OutputCapture:

    def __init__(self):

        self.lines = []

    def __call__(self, text):

        self.lines.append(str(text))


def make_scripted_input(*decisions):

    remaining = list(decisions)

    def input_fn(prompt):

        if remaining:

            return remaining.pop(0)

        raise EOFError()

    return input_fn


def make_console(
    store,
    decisions,
    risk_engine=None,
    authorizer="human-console",
):

    out = OutputCapture()

    gateway = ConsoleApprovalGateway(
        store=store,
        risk_engine=(
            risk_engine
            if risk_engine is not None
            else RiskEngine()
        ),
        input_fn=make_scripted_input(*decisions),
        print_fn=out,
        authorizer=authorizer,
        ttl_seconds=3600,
    )

    return gateway, out


# ---------------------------------------------------------------------------
# Rendering: every required field is visible and no patch content leaks
# ---------------------------------------------------------------------------

def test_request_render_shows_all_required_fields(tmp_path):

    target, patch = make_high_patch(tmp_path)

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        authorizer="human-console",
        ttl_seconds=3600,
        evidence_reference="worker-task",
    )

    rendered = request.render()

    assert patch.fingerprint() in rendered

    assert patch.path in rendered

    assert patch.action in rendered

    assert assessment.risk_level.value in rendered

    assert assessment.reason in rendered

    assert "ATTEMPT" in rendered and "1" in rendered

    assert "AUTHORIZER" in rendered and "human-console" in rendered

    assert "EXPIRES AT" in rendered

    assert "EVIDENCE REFERENCE" in rendered and "worker-task" in rendered


def test_request_render_never_contains_patch_content(tmp_path):

    target, patch = make_high_patch(tmp_path)

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        evidence_reference="worker-task",
    )

    rendered = request.render()

    assert patch.old_content not in rendered

    assert patch.new_content not in rendered

    assert "value = 2" not in rendered


def test_build_pending_request_fails_closed_on_malformed_input(tmp_path):

    _, patch = make_high_patch(tmp_path)

    assessment = RiskEngine().classify(patch)

    for bad in (
        None,
        object(),
        "not-a-patch",
        {"path": "x"},
    ):

        try:

            build_pending_request(bad, assessment)

            raised = False

        except TypeError:

            raised = True

        assert raised

    for bad in (None, object(), "not-an-assessment", {}):

        try:

            build_pending_request(patch, bad)

            raised = False

        except TypeError:

            raised = True

        assert raised

    for bad_attempt in (0, -1, True, "1", None):

        try:

            build_pending_request(
                patch,
                assessment,
                attempt=bad_attempt,
            )

            raised = False

        except ValueError:

            raised = True

        assert raised


def test_request_grant_context_is_derived_from_real_objects(tmp_path):

    target, patch = make_high_patch(tmp_path)

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        authorizer="human-console",
        ttl_seconds=3600,
        evidence_reference="worker-task",
    )

    ctx = request.to_grant_context()

    assert ctx["patch_fingerprint"] == patch.fingerprint()

    assert ctx["path"] == patch.path

    assert ctx["action"] == patch.action

    assert ctx["risk_level"] == assessment.risk_level.value

    assert ctx["attempt"] == 1

    assert ctx["authorizer"] == "human-console"

    assert ctx["expires_at"] == 3600


# ---------------------------------------------------------------------------
# Decision: approve grants through the store; deny / garbage fail closed
# ---------------------------------------------------------------------------

def test_prompt_approve_grants_through_store(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        authorizer="human-console",
    )

    approval = prompt_approval_decision(
        request,
        store,
        input_fn=make_scripted_input("approve"),
        print_fn=OutputCapture(),
    )

    assert isinstance(approval, Approval)

    assert store.is_consumed(approval) is False

    assert store.is_applied(approval) is False

    found = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=assessment.risk_level.value,
        attempt=1,
        patch=patch,
    )

    assert found is approval


def test_prompt_deny_returns_none_and_does_not_grant(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
    )

    approval = prompt_approval_decision(
        request,
        store,
        input_fn=make_scripted_input("deny"),
        print_fn=OutputCapture(),
    )

    assert approval is None

    assert len(store) == 0


def test_prompt_unrecognized_input_then_deny_fails_closed(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
    )

    approval = prompt_approval_decision(
        request,
        store,
        input_fn=make_scripted_input("sure", "deny"),
        print_fn=OutputCapture(),
    )

    assert approval is None

    assert len(store) == 0


def test_prompt_eof_fails_closed(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
    )

    approval = prompt_approval_decision(
        request,
        store,
        input_fn=make_scripted_input(),
        print_fn=OutputCapture(),
    )

    assert approval is None

    assert len(store) == 0


def test_prompt_recognizes_all_approve_phrases(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
    )

    for phrase in APPROVE_PHRASES:

        approval = prompt_approval_decision(
            request,
            store,
            input_fn=make_scripted_input(phrase),
            print_fn=OutputCapture(),
        )

        assert isinstance(approval, Approval), phrase

        approval = None


def test_duplicate_approval_each_is_single_use(tmp_path):

    _, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    assessment = RiskEngine().classify(patch)

    first = grant_via_console(store, patch, assessment)

    second = grant_via_console(store, patch, assessment)

    assert first.approval_id != second.approval_id

    assert len(store) == 2

    released = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=assessment.risk_level.value,
        attempt=1,
    )

    assert released is not None

    again = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=assessment.risk_level.value,
        attempt=1,
    )

    assert again is not None

    third = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=assessment.risk_level.value,
        attempt=1,
    )

    assert third is None


def test_approval_restart_with_console_grant_survives(tmp_path):

    target, patch = make_high_patch(tmp_path)

    ledger_path = tmp_path / "ledger.jsonl"

    store = ApprovalStore(
        ledger=ApprovalLedger(path=ledger_path)
    )

    approval = grant_via_console(
        store,
        patch,
        RiskEngine().classify(patch),
    )

    restarted = ApprovalStore(
        ledger=ApprovalLedger(path=ledger_path)
    )

    found = restarted.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
    )

    assert found is not None

    assert found.approval_id == approval.approval_id

    assert restarted.is_consumed(found) is True


def test_console_gateway_rejects_non_approval_return(tmp_path):

    _, patch = make_high_patch(tmp_path)

    class HostileGateway:

        def request_approval(
            self,
            patch,
            risk_level,
            attempt,
            evidence_reference="",
        ):

            return {
                "approved": True,
                "patch_fingerprint": patch.fingerprint(),
            }

    store = ApprovalStore()

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        HostileGateway(),
    )

    result = agent.chat("worker: hostile gateway")

    assert result.success is False

    assert result.failure_stage == "approval"


def test_console_approve_flows_through_governed_runtime_apply(
    tmp_path
):

    target, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    gateway, out = make_console(store, ["approve"])

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        gateway,
    )

    result = agent.chat("worker: console approve high")

    assert result.success is True

    assert result.final_apply_success is True

    assert result.final_verification_passed is True

    assert target.read_text(encoding="utf-8") == "value = 2\n"


def test_console_deny_fails_closed_no_apply(tmp_path):

    target, patch = make_high_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    store = ApprovalStore()

    gateway, out = make_console(store, ["deny"])

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        gateway,
    )

    result = agent.chat("worker: console deny high")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert target.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Display / apply integrity: console-granted approvals carry the full
# binding, so substituting any displayed field fails closed downstream
# (no interactive gateway in these runs: the approval comes only from
# the store, so the binding is what authorizes apply).
# ---------------------------------------------------------------------------

def grant_via_console(store, patch, assessment, authorizer="human-console"):

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        authorizer=authorizer,
        ttl_seconds=3600,
        evidence_reference="console-grant",
    )

    return prompt_approval_decision(
        request,
        store,
        input_fn=make_scripted_input("approve"),
        print_fn=OutputCapture(),
    )


def build_gated_agent_no_gateway(
    tmp_path,
    worker_executor,
    verification_executor,
    store,
):

    kernel, event_store = build_isolated_kernel(tmp_path)

    agent = build_recovery_agent(
        kernel,
        worker_executor=worker_executor,
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=store,
        evidence_recorder=WorkerEvidenceRecorder(kernel=kernel),
        verification_executor=verification_executor,
    )

    assert agent.worker_pipeline.risk_gate_enabled is True

    return agent, kernel, event_store


def test_console_approve_for_different_path_fails_closed(tmp_path):

    target, patch = make_high_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    other = tmp_path / "other.secret.txt"

    other.write_text("other = 1\n", encoding="utf-8")

    other_patch = PatchProposal(
        path=str(other),
        action="modify",
        reason="Approval for another path.",
        old_content="other = 1\n",
        new_content="other = 2\n",
        allowed_paths=(str(other),),
    )

    store = ApprovalStore()

    grant_via_console(
        store,
        other_patch,
        RiskEngine().classify(other_patch),
    )

    assert len(store) == 1

    agent, kernel, event_store = build_gated_agent_no_gateway(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
    )

    result = agent.chat("worker: console wrong path")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert target.read_text(encoding="utf-8") == original


def test_console_approve_for_different_patch_fails_closed(tmp_path):

    target, patch = make_high_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    other = PatchProposal(
        path=patch.path,
        action=patch.action,
        reason="Different patch.",
        old_content=patch.old_content,
        new_content="value = 9\n",
        allowed_paths=patch.allowed_paths,
    )

    store = ApprovalStore()

    grant_via_console(
        store,
        other,
        RiskEngine().classify(other),
    )

    assert len(store) == 1

    agent, kernel, event_store = build_gated_agent_no_gateway(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
    )

    result = agent.chat("worker: console wrong patch")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert target.read_text(encoding="utf-8") == original


def test_console_approve_risk_downgrade_fails_closed(tmp_path):

    target, patch = make_critical_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    real_assessment = RiskEngine().classify(patch)

    assert real_assessment.risk_level.value == "CRITICAL"

    downgraded = build_pending_request(
        patch,
        RiskAssessment(
            risk_level=RiskLevel.HIGH,
            reason="Downgraded display (attacker/console bug).",
        ),
        attempt=1,
        authorizer="human-console",
    )

    store = ApprovalStore()

    approval = prompt_approval_decision(
        downgraded,
        store,
        input_fn=make_scripted_input("approve"),
        print_fn=OutputCapture(),
    )

    assert isinstance(approval, Approval)

    assert approval.risk_level == "HIGH"

    agent, kernel, event_store = build_gated_agent_no_gateway(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
    )

    result = agent.chat("worker: console risk downgrade")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert target.read_text(encoding="utf-8") == original


def test_console_gateway_refuses_downgraded_risk_display(tmp_path):

    target, patch = make_critical_patch(tmp_path)

    store = ApprovalStore()

    gateway, out = make_console(store, ["approve"])

    request = gateway.request_approval(
        patch,
        risk_level="HIGH",
        attempt=1,
        evidence_reference="worker-task",
    )

    assert request is None

    assert len(store) == 0


def test_console_approve_records_evidence_event(tmp_path):

    target, patch = make_high_patch(tmp_path)

    kernel, event_store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    store = ApprovalStore(evidence_recorder=recorder)

    gateway, out = make_console(store, ["approve"])

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        gateway,
        kernel=kernel,
        event_store=event_store,
    )

    result = agent.chat("worker: console evidence")

    assert result.success is True

    records = [
        json.loads(line)
        for line in event_store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert HashVerifier().verify(records) is True

    event_types = {
        record["event_type"]
        for record in records
    }

    assert "WorkerHumanApprovalGranted" in event_types


# ---------------------------------------------------------------------------
# Secret boundary: the console / ledger / evidence never leak patch
# content or secret values (MISSION-017 Phase 5)
# ---------------------------------------------------------------------------

def test_console_grant_ledger_never_contains_patch_content(tmp_path):

    secret_value = "sk-super-secret-console-value-xyz"

    target = tmp_path / "settings.secret.txt"

    original = f"api_key = '{secret_value}'\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Console secret probe.",
        old_content=original,
        new_content=f"api_key = '{secret_value}-changed'\n",
        allowed_paths=(str(target),),
    )

    ledger_path = tmp_path / "ledger.jsonl"

    store = ApprovalStore(
        ledger=ApprovalLedger(path=ledger_path)
    )

    approval = grant_via_console(
        store,
        patch,
        RiskEngine().classify(patch),
    )

    ledger_text = ledger_path.read_text(encoding="utf-8")

    assert secret_value not in ledger_text

    assert patch.old_content not in ledger_text

    assert patch.new_content not in ledger_text

    assert approval.patch_fingerprint in ledger_text


def test_console_render_and_grant_never_leak_secrets(tmp_path):

    secret_value = "sk-another-console-secret-98765"

    target = tmp_path / "config.secret.txt"

    original = f"token = '{secret_value}'\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Console secret render probe.",
        old_content=original,
        new_content=f"token = '{secret_value}-v2'\n",
        allowed_paths=(str(target),),
    )

    assessment = RiskEngine().classify(patch)

    request = build_pending_request(
        patch,
        assessment,
        attempt=1,
        authorizer="human-console",
        evidence_reference="worker-task",
    )

    out = OutputCapture()

    approval = prompt_approval_decision(
        request,
        ApprovalStore(),
        input_fn=make_scripted_input("approve"),
        print_fn=out,
    )

    rendered = "\n".join(out.lines)

    assert secret_value not in rendered

    assert patch.old_content not in rendered

    assert patch.new_content not in rendered

    assert approval is not None


def test_console_evidence_never_contains_patch_content(tmp_path):

    secret_value = "sk-console-evidence-secret-111"

    target = tmp_path / "settings.secret.txt"

    original = f"password = '{secret_value}'\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Console evidence probe.",
        old_content=original,
        new_content=f"password = '{secret_value}-rotated'\n",
        allowed_paths=(str(target),),
    )

    kernel, event_store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    store = ApprovalStore(evidence_recorder=recorder)

    gateway, out = make_console(store, ["approve"])

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        gateway,
        kernel=kernel,
        event_store=event_store,
    )

    result = agent.chat("worker: console evidence secret")

    assert result.success is True

    event_text = event_store.path.read_text(encoding="utf-8")

    assert secret_value not in event_text

    assert patch.old_content not in event_text

    assert patch.new_content not in event_text

    assert patch.fingerprint() in event_text


def test_console_gateway_evidence_reference_is_not_authority(tmp_path):

    _, patch = make_high_patch(tmp_path)

    class EvidenceClaimingGateway:

        def __init__(self, store):

            self.store = store

        def request_approval(
            self,
            patch,
            risk_level,
            attempt,
            evidence_reference="",
        ):

            return self.store.find_valid(
                patch.fingerprint(),
                path=patch.path,
                action=patch.action,
                risk_level=risk_level,
                attempt=attempt,
            )

    store = ApprovalStore()

    agent, kernel, event_store, _ = build_console_agent(
        tmp_path,
        FixedPatchWorker(patch),
        ScriptedVerification(
            [make_verification_result()]
        ),
        store,
        EvidenceClaimingGateway(store),
    )

    result = agent.chat("worker: evidence claiming gateway")

    assert result.success is False

    assert result.failure_stage == "approval"


# ---------------------------------------------------------------------------
# Runtime assembly
# ---------------------------------------------------------------------------

def build_console_agent(
    tmp_path,
    worker_executor,
    verification_executor,
    store,
    gateway,
    kernel=None,
    event_store=None,
):

    if kernel is None:

        kernel, event_store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    agent = build_recovery_agent(
        kernel,
        worker_executor=worker_executor,
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=store,
        approval_gateway=gateway,
        evidence_recorder=recorder,
        verification_executor=verification_executor,
    )

    assert agent.worker_pipeline.risk_gate_enabled is True

    return agent, kernel, event_store, recorder
