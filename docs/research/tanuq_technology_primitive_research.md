# TANUQ — Technology Primitive Research (JEV-Inspired)

> Research/design document. NO production implementation, NO dependency,
> NO adapter, NO API key, NO commit. Read-only analysis with a
> technology-independent conclusion per primitive.
>
> Origin: Jev/TypeSafe pre-research (2026-09-20, see
> TANUQ-PARALLEL-PROGRESS-REPORT.md §2). Working principle: **TANUQ does
> not adapt to technology. It extracts ideas/primitives from new
> technologies and adapts them to its own governance architecture.**
> Jev is not a dependency or an integration target.

## 0. STANDING RULE — THE OBSERVER IS NOT AUTHORITY

Any semantic/behavioral observer, from any technology:

- may NOT grant authorization
- may NOT own policy
- may NOT change fingerprints
- may NOT create approvals
- may NOT start execution
- may NOT be evidence authority

Governance authority stays in TANUQ exactly as it is
(`simulation/security/*`: RiskEngine/RiskPolicy/GovernanceEvaluator,
ApprovalStore, ApplyAuthorization). Every primitive below is classified
against this rule. If a primitive cannot be expressed as OBSERVATION or
RAISE-ONLY SIGNAL, it is out of scope for TANUQ regardless of value.

Existing anchor points (all CONFIRMED, repo reads 2026-09-20):

- `RiskAssessment.advisory_risk / advisory_confidence` — tested
  raise-only advisory channel; `advisory` can only raise the level
  (max_level), is recorded as signal `advisory_llm_risk`, malformed
  input is silently ignored (= advisory absent = deterministic baseline)
  — `risk_engine.py:343-346,601-627`, `tests/risk_engine_test.py:345-375`.
  **No production caller passes advisory today.**
- `tanuq/trajectory.py` — read-only observation projection over existing
  evidence events; "Observation only — never enforces" discipline
  documented in-module.
- Connect registry — metadata-only, never governance (`tanuq/web.py:474-506`).

## 1. Atomic Security Questions

- **TANUQ sees today:** deterministic signals — path fragments, action
  type, content class (SAFE/SUSPICIOUS/OPAQUE via fragment/regex),
  change size, location (risk_engine.py — CONFIRMED).
- **Cannot see:** meaning. E.g. a config file edited with non-credential
  content but security-relevant intent; code that deletes a user's data
  without matching any destructive token.
- **Gap targeted:** semantic coverage gaps of fragment matching without
  replacing determinism.
- **Layer fit:** RAISE-ONLY RISK SIGNAL (advisory channel), composed from
  several narrow atomic questions answered by an external semantic
  service, weighted/combined in TANUQ code.
- **Boundary:** result enters only via `advisory_risk` (max_level, never
  lowers). Low-confidence/parse-failure = no advisory. Never policy.
- **Architecture risk:** LOW by construction (raise-only, tested
  invariant). Real risk is FP-DoS (agent inflates advisory to exhaust
  human attention) — needs rate/weight design before any implementation.
- **Measurable experiment:** corpus of proposals labeled by operator
  (risky/safe) that deterministic engine classifies LOW/MEDIUM; measure
  raise-value (true raises) vs FP-rate (raises on genuinely safe);
  injection-shift (see §8).
- **Technology-independent?** YES. The decomposition "one narrow judgment
  per question, weights in code" is provider-agnostic; any semantic
  evaluator (LLM, rule service, human triage queue) can fill the slot.

## 2. Structured Semantic Observations

- **Sees today:** evidence events are governance-shaped (proposal, risk,
  approval, apply, verify) — CONFIRMED (trajectory.py projection reads
  exactly these).
- **Cannot see:** semantic characterization of a change ("this edits
  authentication logic", "this weakens input validation").
- **Gap:** evidence records WHAT happened, not WHAT-IT-MEANS.
- **Layer fit:** OBSERVATION / EVIDENCE-ADJACENT record. A separate
  observation record (model, questions, answers, confidence) attached to
  a fingerprint — display-only, journaled OUTSIDE the authority chain or
  as display metadata; never an input to allow/deny.
- **Boundary:** may never become a decision input retroactively; may
  never alter the hash chain; adding a new event type to the anchored
  EventStore touches protected evidence semantics → human gate.
- **Architecture risk:** MEDIUM — evidence schema changes are protected
  territory. Recommendation: keep observations in a separate, clearly
  non-authority store until a real need is proven.
- **Experiment:** shadow-run observations over the dogfood corpus for N
  weeks; measure whether any observation would have changed a human
  decision (value evidence) or generated noise (cost evidence).
- **Technology-independent?** YES — observation schema is provider-neutral.

## 3. Confidence → Escalation

- **Sees today:** deterministic approval gating (HIGH/CRITICAL → human,
  single-use, fingerprint-bound) — CONFIRMED.
- **Cannot see:** graded uncertainty about ITS OWN classification. A
  borderline proposal is either above or below a fragment threshold.
- **Gap:** "the system is unsure" as an explicit, routable state.
- **Layer fit:** OBSERVATION + display-only input to the human approval
  screen ("a semantic observer flagged this as uncertain"). The human
  remains the decider; confidence never selects behavior automatically.
- **Boundary (hard):** confidence must NEVER widen auto-apply. "High
  confidence → skip approval" is the unacceptable direction; only "low
  confidence → more human attention" is allowed, and even that only as
  presentation.
- **Architecture risk:** LOW if display-only; HIGH the moment confidence
  starts gating deterministic behavior (that would be new authority).
- **Experiment:** calibration study — does observer confidence correlate
  with human disagreement rates on a labeled corpus?
- **Technology-independent?** YES. Escalation-on-uncertainty is the same
  philosophy as UNKNOWN→DENY, generalized.

## 4. UNKNOWN / "I don't know" as first-class outcome

- **Already TANUQ-native:** RiskEngine SAFE/SUSPICIOUS/OPAQUE with
  OPAQUE→UNKNOWN→policy DENY; "not detected is never safe" (MISSION-018A)
  — CONFIRMED. No gap in principle.
- **Gap actually targeted:** semantic observers that CANNOT say
  "I don't know" are unsafe; any future semantic signal must carry an
  explicit unknown/abstain state that TANUQ maps to "no advisory" (never
  to "safe").
- **Layer fit:** contract requirement for every future observer.
- **Boundary:** abstain must be indistinguishable from absent advisory.
- **Architecture risk:** NONE — it strengthens the existing invariant.
- **Experiment:** contract test: observer output space must include
  abstain; abstain must map to baseline behavior (add to any future
  adapter's test module).
- **Technology-independent?** YES — already proven by the codebase.

## 5. Parallel Independent Observations

- **Sees today:** multiple deterministic signals per proposal, but from
  ONE analyzer (RiskEngine).
- **Cannot see:** independent second opinions.
- **Gap:** single point of semantic blindness.
- **Layer fit:** multiple RAISE-ONLY signals; TANUQ combines with
  max_level semantics (most restrictive wins) — the exact mechanism the
  advisory channel already implements.
- **Boundary:** each observer is a separate translation-only module;
  none is privileged; all fail independently; absence of any = baseline.
- **Architecture risk:** LOW per observer; aggregates must not become a
  shadow authority (e.g. "3 of 5 observers say HIGH" auto-logic is
  FORBIDDEN — that is policy by another name).
- **Experiment:** measure incremental raise-value of observer #2 over
  observer #1 on the same corpus (does independence add value?).
- **Technology-independent?** YES.

## 6. Intent ↔ Actual Change Mismatch

- **Sees today:** the proposal's `reason` free-text and the exact
  old→new content; validation ensures old_content matches the file —
  but nothing checks that the CHANGE matches the CLAIMED INTENT.
- **Cannot see:** "reason says 'fix typo', diff rewires auth".
- **Gap:** intent-vs-diff consistency. (CONFIRMED gap: no such check
  exists in validator/engine.)
- **Layer fit:** RAISE-ONLY SIGNAL at propose time (advisory), plus
  OBSERVATION display for the human approver ("claimed intent vs actual
  change"). Human approval remains the control point — the approval UI
  already shows the diff and what_this_authorizes.
- **Boundary:** identical to §1. Never DENY by itself (a mismatched
  advisory raises; the human decides).
- **Architecture risk:** LOW (advisory) / ZERO (display).
- **Experiment:** labeled pairs (honest reason, deceptive reason) over
  the same diffs; measure mismatch-detection rate and deceptive-reason
  manipulation resistance.
- **Technology-independent?** YES — "does the description match the
  change" is a classic, provider-neutral check.

## 7. Semantic Dangerousness

- **Sees today:** syntactic danger (credential fragments, destructive
  tokens, sensitive paths).
- **Cannot see:** semantically dangerous content with no keyword
  signature (e.g. a subtle logic change that disables a security check).
- **Gap:** the complement of the deterministic engine.
- **Layer fit:** RAISE-ONLY SIGNAL (advisory) + OBSERVATION for approvers.
- **Boundary:** §0. Note the structural safety: because the advisory can
  only raise, a blind spot causes the OLD behavior (deterministic
  baseline), never a weaker one.
- **Architecture risk:** LOW; FP fatigue is the practical risk.
- **Experiment:** red-team corpus (subtle security-weakening diffs) vs
  deterministic engine recall; measure advisory catch-rate uplift.
- **Technology-independent?** YES.

## 8. Surface-Syntax Manipulation

- **Sees today:** content classification is lexical; manipulation of
  surface syntax (padding, misleading comments, variable renaming) can
  change deterministic classification in EITHER direction.
- **Cannot see:** that surface form was engineered.
- **Gap:** manipulation-awareness of the classifier itself.
- **Layer fit:** RESEARCH/EVALUATION concern first: any future semantic
  observer must be tested for manipulation resistance. Also OBSERVATION
  (flag suspicious surface patterns for humans).
- **Boundary:** an observer's verdict on manipulation is advisory only.
- **Architecture risk:** LOW. Vendor evidence (Jev jaggedness #6:
  adversarial content "can move the answer" — VENDOR DOCUMENTED) shows
  semantic observers are themselves manipulable → must never be more
  than advisory.
- **Experiment:** adversarial pairs (same semantic change, benign vs
  engineered surface) — measure classification flip rate of any candidate
  observer.
- **Technology-independent?** YES.

## 9. Governance-Input Manipulation

- **Sees today:** proposals are untrusted input; validator/risk/approval
  all re-derive from the patch (no decision object is trusted —
  ApplyAuthorization recomputes risk; CONFIRMED). The H-experiment
  corpus referenced by the operator is NOT in the repo (UNKNOWN /
  INSUFFICIENT EVIDENCE).
- **Cannot see:** manipulation aimed at the GOVERNANCE LAYER'S inputs:
  crafting `reason` text, `path` naming, or content to steer semantic
  observers (once they exist) or to game approval presentation.
- **Gap:** preemptive hardening of future semantic inputs.
- **Layer fit:** THREAT-MODEL + test requirement for any observer
  adapter: fail-closed, raise-only, injection-benchmarked before enable.
- **Boundary:** §0 plus: observer input construction must not include
  fields the agent controls unchecked without labeling them as
  agent-controlled in the observation.
- **Architecture risk:** LOW today (no semantic observer active); MEDIUM
  if an observer is enabled without the injection benchmark.
- **Experiment:** the injection-shift benchmark (JEV research §9.3)
  generalized to any observer.
- **Technology-independent?** YES.

## 10. Behavioral Drift

- **Sees today:** per-proposal governance; trajectory projection shows
  per-path operation outcomes over time (trajectory.py — CONFIRMED,
  observation-only).
- **Cannot see:** behavior-level drift of an agent across sessions
  (shifting risk profile, probing patterns).
- **Gap:** longitudinal semantic view. Evidence today lacks event-level
  timestamps and content (by design — trajectory.py:14-17 documents
  absent fields honestly).
- **Layer fit:** TRAJECTORY (observation-only), strictly extending the
  existing read-only projection; never enforcement.
- **Boundary:** §0. A "drift score" must never auto-restrict an agent
  (that would be policy without authority).
- **Architecture risk:** MEDIUM — tempting to convert observations into
  enforcement; explicitly out of scope until proven need + human gate.
- **Experiment:** define drift metrics on the existing evidence schema;
  measure on self-hosted dogfood history whether they distinguish
  benign sessions from crafted ones.
- **Technology-independent?** YES.

## 11. Trajectory-Level Anomalies

- **Sees today:** per-fingerprint chains (proposal→risk→approval→apply→
  verify) and per-path aggregates — CONFIRMED.
- **Cannot see:** cross-operation anomalies (many denied proposals to
  sensitive paths in a short window, approval-harvesting patterns).
- **Gap:** anomaly detection over the operation stream.
- **Layer fit:** TRAJECTORY — anomaly = OBSERVATION routed to the
  Incidents-style detect-only projection (web.py incidents is already
  detect-only, never auto-repairs — CONFIRMED).
- **Boundary:** anomalies surface to humans; never auto-DENY, never
  auto-revoke.
- **Architecture risk:** LOW as detect-only; HIGH if wired into policy.
- **Experiment:** replay historical evidence + injected synthetic
  anomaly sequences; measure detection vs false-alarm rates.
- **Technology-independent?** YES.

## 12. Multi-Agent Attribution

- **Sees today:** `session` field on proposals; adapter correlation
  (tool-aware, fail-closed on ambiguity — CONFIRMED, FAZ 6-lite B).
- **Cannot see:** reliable multi-agent identity (session is
  agent-supplied, not authenticated); cross-agent correlation.
- **Gap:** attribution integrity at scale.
- **Layer fit:** MULTI-AGENT (future baseline — see
  multi_agent_baseline.md). Identity isolation is a prerequisite for any
  attribution claim.
- **Boundary:** attribution is evidence labeling, not authority; a
  forged session label must not change governance behavior (today it
  doesn't — CONFIRMED: risk/approval ignore session).
- **Architecture risk:** LOW now; grows at scale (see Track E doc).
- **Experiment:** the Track E measurement plan (§1→10→50→100).
- **Technology-independent?** YES.

## SUMMARY TABLE

| # | Primitive | TANUQ fit | Max classification allowed |
|---|---|---|---|
| 1 | Atomic security questions | advisory channel (raise-only) | RISK SIGNAL |
| 2 | Structured semantic observations | separate observation store / display | OBSERVATION |
| 3 | Confidence → escalation | display-only on approval screen | OBSERVATION |
| 4 | UNKNOWN as first-class | already native (OPAQUE/UNKNOWN) | CONTRACT RULE |
| 5 | Parallel independent observations | multiple advisory sources, max_level | RISK SIGNAL |
| 6 | Intent↔change mismatch | advisory + approver display | RISK SIGNAL / OBSERVATION |
| 7 | Semantic dangerousness | advisory + approver display | RISK SIGNAL / OBSERVATION |
| 8 | Surface-syntax manipulation | observer eval benchmark + observation | OBSERVATION / TEST |
| 9 | Governance-input manipulation | threat model + adapter test req | THREAT MODEL |
| 10 | Behavioral drift | trajectory (read-only) | TRAJECTORY |
| 11 | Trajectory-level anomalies | incidents-style detect-only projection | TRAJECTORY / OBSERVATION |
| 12 | Multi-agent attribution | future baseline (Track E) | MULTI-AGENT (future) |

None of the twelve requires touching frozen semantics. Items that would
(evidence event types, enforcement wiring) are explicitly gated.

## BDP

- ASSUMPTIONS: external semantic evaluators exist and are optional;
  operator-provided corpora (24-action / H1-H7) remain UNAVAILABLE
  (INSUFFICIENT EVIDENCE — not fabricated).
- EVIDENCE: ARAÇ — repo reads (rg/Read), git; KULLANICI — operator's
  primitive list; EĞİTİM — prior Jev/TypeSafe vendor-doc review
  (VENDOR DOCUMENTED, 2026-09-20).
- FINDINGS: all 12 primitives fit TANUQ without touching frozen core;
  safe classifications are OBSERVATION / RAISE-ONLY SIGNAL /
  TRAJECTORY-READ-ONLY.
- GAPS: no production caller of the advisory channel; no semantic
  corpus in repo; benchmark not run.
- SECURITY IMPACT: none from this document (research only). Future
  impact bounded by §0 rule.
- RECOMMENDATION: keep this as the reference map; do not implement any
  primitive without a proven-need corpus and a human gate.
- CONFIDENCE: [GÜVEN: YÜKSEK] on repo facts; [GÜVEN: ORTA] on
  technology-independent value claims (unbenchmarked).
