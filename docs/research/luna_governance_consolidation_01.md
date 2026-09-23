# TANUQ — LUNA Governance Research Consolidation 01 (LUNA-07 / LUNA-10)

> STATUS: research record only — converts the previously
> conversation-derived LUNA-07 and LUNA-10 verdicts into a permanent,
> tracked research log. NO production changes (governance/evidence/
> reconciliation code untouched, tracked production diff 0), NO
> commit/push, NO new tests. Historical results are labeled as
> conversation-derived; every technical claim below is corroborated
> against the current tracked source/tests, or explicitly marked
> UNRESOLVED. No test counts or file names were invented.

Related records:
- `luna_e2e_05_06_consolidation_01.md` — LUNA-E2E-05/06, E5
  Reconciliation V1 E2E validation, LUNA-08 re-evaluation, LUNA-09
  decision.

---

## 1. LUNA-07 — APPROVAL FINGERPRINT BINDING / SINGLE-USE

HYPOTHESIS (conversation-derived):
"Approval must be bound to the exact canonical proposal fingerprint
and execution instance — this binding cannot be demonstrated."

RESULT: **FALSIFIED as a security gap.**
The binding IS demonstrable from current tracked source and tests:

- `simulation/agent/worker/patch_proposal.py:16-35` — the proposal
  fingerprint is deterministic canonical SHA-256 over
  path/action/reason/old_content/new_content/allowed_paths.
- `simulation/agent/approval/approval_store.py:14-40` (contract
  docstring) — the store binds every approval to fingerprint, path,
  action, risk level and attempt; `find_valid` is single-use
  (consume-once); with an `ApprovalLedger` every grant/consume/apply
  transition is durable and reloaded on construction, so a consumed
  approval stays consumed after restart.
- `simulation/agent/approval/approval_validation.py:24-70` — shared
  fail-closed validation re-checks type, fingerprint, path, action,
  risk context, attempt and expiry.
- `simulation/agent/apply/apply_authorization.py:89-112` — the apply
  boundary requires a typed `ControllerDecision` whose fingerprint
  exactly matches the patch, then store-backed authorization.
- `tanuq/coordinator.py:124-129` — `OperationCoordinator` reserves a
  RAM-only in-flight slot keyed per fingerprint/selector so concurrent
  executions of the same proposal cannot interleave.
- Existing tracked tests (executed in this session's analyses):
  `tests/security/approval_policy_replay_test.py`,
  `tests/security/approval_ledger_authority_test.py`,
  `tests/test_p4_llm_untrusted.py` adversarial replay scenario
  (`test_p4_adversarial_replay_single_use`), and the multiprocess
  concurrency suite — replay, concurrency and restart-recovery
  behaviors are covered.

REMAINING NON-BLOCKING RESEARCH LIMITATIONS (recorded, not claimed
as gaps):

- Canonical serialization details of the fingerprint schema should
  remain documented at their definition point (they are: the
  fingerprint dict is explicit in `patch_proposal.py:17-25`).
- Distributed / multi-host approval durability is FUTURE SCOPE — the
  ledger is per-workspace; cross-host guarantees are UNRESOLVED by
  design (single-operator product).
- Crash between approval consumption and apply remains a FUTURE
  RESEARCH edge case: the ledger records consumption and the apply
  journal records intent/outcome, and startup reconciliation flags
  consumed-approvals-without-terminal-outcome
  (`simulation/agent/recovery/startup_reconciliation.py:300-352`);
  automatic repair is intentionally out of scope (detect-only).

## 2. LUNA-10 — GOVERNANCE-INPUT MANIPULATION

HYPOTHESIS (conversation-derived):
"An untrusted agent/proposer can manipulate the inputs of the
governance decision to alter the deterministic governance outcome."

RESULT: **FALSIFIED as a security gap.**
(Historical verdict is conversation-derived; the current tracked
source and tests corroborate it directly.)

- The agent controls proposal fields, advisory labels, metadata and
  claims — and nothing else. The authoritative governance state lives
  exclusively in:
  - `GovernanceEvaluator` / `RiskEngine` / `RiskPolicy`
    (`simulation/security/`) — deterministic classification from
    path/action/content; advisory risk is raise-only and is not even
    forwarded by any production call site;
  - the proposal fingerprint (`patch_proposal.py`) — every
    agent-controlled field is inside the hash, so any manipulation
    breaks approval binding instead of bypassing it;
  - `ApprovalStore` / `ApprovalLedger` — the only authorization
    authority;
  - the apply path (`ApplyAuthorization` → `ApplyExecutor` →
    `FileApplier`) — risk is recomputed from the patch at the apply
    boundary (`governance_evaluator.py:195`), never read from
    forgeable decision objects;
  - verification and journals — evidence, never authorization input.
- Tracked corroboration:
  - authority-shaped fields are stripped from snapshots
    (`session_persistence.py:38-50` — approved, approval_id,
    verification_passed, risk_override, bypass_governance, ...);
  - the proposal boundary strips/adversarial risk claims stay
    advisory (`tests/test_p93_proposal_boundary.py:105-125`);
  - LLM untrusted adversarial scenarios (prompt injection, fake
    approval, risk hiding, structured-output manipulation) are
    covered by `tests/test_p4_llm_untrusted.py`;
  - raw `attempt` bypass is explicitly rejected in the external
    pipeline (`external_action_pipeline.py:156-170`);
  - advisory risk can never lower a deterministic level
    (`tests/risk_engine_test.py:345-361`).

## 3. CROSS-REFERENCE

- LUNA-08 ("actual applied-content fingerprint") — re-evaluated with
  real E2E evidence: SECURITY GAP = NOT CONFIRMED; retained only as an
  evidence/observability hardening topic. See
  `luna_e2e_05_06_consolidation_01.md` §4.
- LUNA-09 ("production change not required") — kept. Same record, §5.

## 4. UNRESOLVED / LABELING

- The LUNA-07 and LUNA-10 experiments themselves ran outside the repo
  (no raw transcripts tracked); their verdicts above are recorded as
  conversation-derived and are corroborated — not re-derived — by the
  tracked source/tests cited.
- Root-level `luna-*` artifacts remain untracked pending an
  owner-approved cleanup task (see the completed root artifact hygiene
  audit; no files were moved, renamed or deleted).
