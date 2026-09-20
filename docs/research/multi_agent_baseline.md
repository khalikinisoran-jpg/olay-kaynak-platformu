# TANUQ — Multi-Agent Future Baseline (Research/Design)

> Implementation NONE. This document defines WHAT will be measured when
> multi-agent scale work ever starts, so that the baseline is designed
> before scale arrives. Research principle — **"One agent proves the
> control loop. Many agents prove the platform."** — is a measurement
> principle, NOT a product claim.

Current reality (all CONFIRMED, repo reads 2026-09-20, HEAD 5504d36):

- TANUQ governs proposals per workspace; `session` is an agent-supplied
  label used for correlation (FAZ 6-lite B: tool-aware, fail-closed on
  ambiguity) — not an authenticated identity.
- In-flight execution guard is RAM-only in the coordinator; cross-process
  in-flight serialization is ABSENT (documented residual,
  PROJECT_STATE) with fail-closed compensations.
- FAZ 7 (concurrency) is OPEN; FAZ 2 (operation identity) is
  FROZEN-BLOCKED (OPERATION_ID: NOT REQUIRED — FROZEN); multi-patch
  bundle identity (FAZ 9) FROZEN-BLOCKED.
- ApprovalStore: single-use, fingerprint-bound, TTL — human-only.
- Evidence: hash-chained, anchored, append-only.

Scale ladder: **1 → 10 → 50 → 100 agents**, where "1" is today's
single-agent reality (the control loop, already proven). Each rung
gates the next; no rung starts without the previous rung's numbers.

## Measurement areas

### 1. Identity isolation

- **Definition:** agent i cannot read, forge, or reuse agent j's
  session/pending artifacts; session label forgery must not alter
  governance behavior (today CONFIRMED: risk/approval ignore session).
- **Measurement:** forge/reuse test matrix per rung (label collision,
  label spoofing, cross-session pending reads); count governance
  behavior changes caused by identity artifacts (target: 0).
- **1-agent baseline:** trivially isolated (single operator session).
- **Open design question:** whether identity becomes authenticated
  (keyed sessions) — that is a NEW authority primitive, requires a
  human gate and a frozen-decision review; NOT assumed.

### 2. Authorization isolation

- **Definition:** one approval authorizes exactly one fingerprint for
  exactly one proposal; no cross-agent approval reuse.
- **Measurement:** concurrent approve/execute interleavings by distinct
  sessions against the same pending set; single-use violations (target:
  0); approval-consumed-under-race behavior (fail-closed DENY expected).
- **1-agent baseline:** single-use + TTL parity tests exist (P10.6
  approval expiry parity — RECORDED).
- **Scale risk:** approval-grant UX contention at 100 agents (human is
  the bottleneck — measure approval queue latency, not just correctness).

### 3. Evidence attribution

- **Definition:** every event attributable to the right agent/session
  with integrity (anchor intact); attribution is labeling, never
  authority.
- **Measurement:** interleaved multi-session runs → reconstruct
  per-session chains from evidence alone; misattribution count (target:
  0); anchor validation after N interleaved sessions.
- **Open gap:** evidence currently lacks event timestamps and content —
  attribution relies on sequence + fingerprint + session labels
  (trajectory.py documents absent fields honestly). Any schema change =
  protected area = human gate.

### 4. Policy isolation

- **Definition:** agent i's behavior cannot alter agent j's risk
  classification (no shared mutable state in the engine — CONFIRMED
  stateless RiskEngine/GovernanceEvaluator).
- **Measurement:** differential classification: same patch evaluated
  before/during/after other agents' activity; verdict deltas (target: 0).
- **1-agent baseline:** holds by construction (stateless evaluator).

### 5. Concurrency

- **Definition:** simultaneous propose/approve/execute across agents
  never corrupts pending store, journals, or workspace state.
- **Measurement:** N-agent harness driving the real CLI/API against one
  workspace: race-window probes (double-execute of one fingerprint,
  propose-vs-execute stale races — fail-closed DENY expected),
  file-lock behavior (`_ProcessFileLock` primitive exists, tested —
  RECORDED), cross-process in-flight window (documented UNKNOWN — this
  is the primary measurement target; FAZ 7 scope).
- **Metrics:** corruption count (target 0), fail-closed correctness rate
  under race, p50/p95 execute latency vs N.

### 6. Recovery

- **Definition:** crash/kill of any agent mid-cycle leaves the system
  consistent and recoverable without authority violations.
- **Measurement:** fault injection (kill during apply/verify/rollback)
  at each rung; recovery reconciliation correctness; no approval bypass
  during recovery (MISSION-018B invariant under concurrent recovery —
  must be re-verified at scale).

### 7. Throughput

- **Definition:** governed proposals/minute at each rung on reference
  hardware, including human-approval-free (LOW) path end-to-end.
- **Measurement:** soak runs; decompose latency: propose / approve wait
  / execute / verify / evidence write. Identify the first human-free
  bottleneck (expected: verification subprocess contention).
- **Note:** verification runs real pytest in a subprocess with a 120s
  timeout — concurrent verifications across 100 agents is the likely
  scaling wall; measure before designing anything.

## Rung gates (research gates, not product gates)

| Rung | Gate to pass before next rung |
|---|---|
| 1 | control loop proven (DONE — CI + dogfood) |
| 10 | identity/attribution/policy isolation = 0 violations under interleaving |
| 50 | concurrency: zero corruption, fail-closed race correctness ≥ design target |
| 100 | throughput wall characterized; human-approval queue model defined |

## Explicit non-goals of this baseline

- No product claim of multi-agent governance today (landing page/test
  contract forbids "çoklu-ajan yönetimi" — CONFIRMED).
- No new authority primitives (authenticated identity, operation_id,
  bundle identity) proposed by this document; each is FROZEN-gated.
- No Unified Runtime merge (FAZ 5 OPEN, deferred).

## BDP

- ASSUMPTIONS: scale experiments would use the real CLI/API surface only;
  "agents" are distinct processes/sessions, not new code paths.
- EVIDENCE: ARAÇ — repo reads (CONFIRMED facts above); KULLANICI —
  operator's scale ladder request; FINDINGS — measurement design only.
- GAPS: cross-process in-flight serialization UNKNOWN; evidence schema
  lacks timestamps/content (limits attribution); authenticated identity
  does not exist.
- SECURITY IMPACT: none (document only). Future scale work must preserve
  fail-closed behavior under every race — that is the measurable core.
- RECOMMENDATION: if scale work ever starts, rung "10" first, harness
  via existing CLI, zero core changes, results recorded in
  PROJECT_STATE.
- CONFIDENCE: [GÜVEN: YÜKSEK] on current-state facts; [GÜVEN: ORTA] on
  projected bottlenecks (unmeasured).
