# TANUQ — PARALLEL PROGRESS REPORT

Date: 2026-09-20 · HEAD: `5504d36` == origin/main · working tree at
analysis start: clean · CI: GREEN 4/4 (run 35508373388) ·
Commit/push this round: NONE (per task rules).

New files produced (untracked, awaiting owner review):
- `docs/research/tanuq_technology_primitive_research.md` (Track A)
- `docs/research/agent_escape_v2_baseline.md` (Track D)
- `docs/research/multi_agent_baseline.md` (Track E)
- this report

---

## 1. EXECUTIVE SUMMARY

- End-User V1 exit criteria hold at 10/10 (G-02/03/04/05 released,
  CI-verified). The product surface claims only proven capabilities.
- Governance core integrity verified: protected-file diff vs
  origin/main EMPTY; vendor-blind core confirmed by scan.
- Research tracks (A/D/E) completed as design-only documents. Central
  finding: TANUQ's architecture already contains the two extension
  shapes any future technology needs — a tested RAISE-ONLY advisory
  channel (`RiskAssessment.advisory_risk/confidence`, no production
  caller yet) and an observation-only projection pattern
  (`trajectory.py`). Nothing observed in Jev/TypeSafe requires touching
  frozen semantics.
- Blocking items are decisions/external inputs, not code: operator
  corpora (24-action / H1-H7 — absent from repo, INSUFFICIENT
  EVIDENCE), Jev API key/credit, tanuq.net deployment (transport error
  — CONFIRMED unreachable), Claude Write runtime dogfood (credit-gated).

## 2. TRACK A — JEV-INSPIRED PRIMITIVE RESEARCH

Full map in `docs/research/tanuq_technology_primitive_research.md`.
12 primitives mapped (atomic questions, semantic observations,
confidence→escalation, UNKNOWN-first-class, parallel observations,
intent↔change mismatch, semantic dangerousness, surface-syntax
manipulation, governance-input manipulation, behavioral drift,
trajectory anomalies, multi-agent attribution).

- **ASSUMPTIONS:** future semantic evaluators are optional and
  provider-swappable; Jev findings remain VENDOR DOCUMENTED (no runtime
  verification performed; no key used).
- **EVIDENCE:** ARAÇ — repo reads/rg/git (CONFIRMED); VENDOR DOCUMENTED
  — docs.typesafe.ai (2026-09-20); the 12-primitive list from operator.
- **FINDINGS:** all 12 fit inside OBSERVATION / RAISE-ONLY-SIGNAL /
  TRAJECTORY-READ-ONLY classifications without touching the frozen
  core. The raise-only advisory invariant ("advisory can only raise,
  never lower, never authority") is already tested
  (risk_engine_test.py:345-375) and idle. UNKNOWN-as-first-class
  (OPAQUE→UNKNOWN→DENY) is already native.
- **GAPS:** no semantic corpus in repo; benchmark not run; no production
  advisory caller; the observer-side FP-DoS (agent inflating advisory)
  has no design yet.
- **SECURITY IMPACT:** none (research only). Hard rule recorded: the
  observer is never authority — no authorization, no policy, no
  fingerprint, no approval, no execute, no evidence authority.
- **RECOMMENDATION:** keep as reference map; no primitive implemented
  without a proven-need corpus + human gate.
- CONFIDENCE: [GÜVEN: YÜKSEK] repo facts; [GÜVEN: ORTA] primitive value
  (unbenchmarked).

## 3. TRACK B — END-USER V1 STATUS

| Stage | Status | Evidence |
|---|---|---|
| Setup | CONFIRMED | first-run setup mode fail-closed (web.py:53-63), setup UI + tests; refuses uninitialized workspaces |
| Connect AI | install CONFIRMED; runtime Edit CONFIRMED; runtime Write VENDOR DOCUMENTED (BLOCKED) | connect registry + hook-install tests (CI); real Edit-hook dogfood closed F1 (PROJECT_STATE, RECORDED); Write→create vendor-documented contract, runtime dogfood BLOCKED on API credit |
| AI Action (generic contract) | CONFIRMED | `tanuq propose --stdin-json --json` + `/api/propose`; real CLI runs this session; cross-model (GLM) dogfood RECORDED in PROJECT_STATE |
| Review / Approve | CONFIRMED | real demo APPROVAL_REQUIRED→APPROVED (this session); UI pending/approve/reject; single-use/TTL tested |
| Execute | CONFIRMED | real demo terminal VERIFIED, apply success True (Windows + CI Ubuntu) |
| Verify | CONFIRMED | Evidence chain VALID + Anchor ACTIVE (real runs) |
| Evidence | CONFIRMED | history/lineage/verify + UI evidence tabs; tamper-evident |

- **Vendor-independent contract preserved: YES (CONFIRMED)** — vendor
  scan shows `claude`/`anthropic` references only in
  `tanuq/claude_code_adapter.py` (translation layer, by design) and
  `tanuq/web.py` (connect-install strings, view layer). Core is
  vendor-blind.
- **Remaining gap:** Claude Write runtime dogfood (BLOCKED on operator
  API credit — not a code task). Until run, the honest wording is
  "Write governed per vendor-documented contract" (tracked as G-07
  label since the release gate).
- **Protected/frozen exposure if closed:** none — dogfood is runtime
  evidence, zero code.
- CONFIDENCE: [GÜVEN: YÜKSEK].

## 4. TRACK C — PRODUCT READINESS (tanuq.net / public surface)

- **TRY flow:** correct and repo-internal (clone → `pip install -e .` →
  script inside repo) — G-04 clarification released; real demo OVERALL
  PASS Windows + CI Ubuntu (CONFIRMED).
- **CONNECT explanation:** landing card + dashboard card; concrete
  starting path shown (G-02) — CONFIRMED.
- **GENERIC integration path:** `tanuq propose --stdin-json --json` on
  landing; no vendor lock-in claims — CONFIRMED.
- **Demo → product bridge:** present (landing + demo next-steps, G-03)
  — CONFIRMED.
- **Repo dependency:** conscious V1 boundary, stated on the page — CONFIRMED.
- **GitHub links:** repo public and reachable via gh API (CONFIRMED);
  discussions URL not fetched this round (UNKNOWN, low risk).
- **tanuq.net: NOT REACHABLE (CONFIRMED — transport error).** Deployment/
  DNS is operator scope (explicit red line for this round). Until
  deployed, the public surface lives in the repo; no code action
  available to me.
- **No speculative claims:** CI-enforced (`test_no_future_roadmap`,
  landing content contract); README identity synced (G-05); forbidden
  capability phrases (universal agent governance, rogue-agent detection,
  prompt-injection prevention, trajectory governance as a feature,
  multi-agent governance, OS/network enforcement) absent from the
  public surface — CONFIRMED via existing tests.
- **GAPS:** only tanuq.net deployment itself. **SECURITY IMPACT:** none.
  **RECOMMENDATION:** operator deploys static site per site/DEPLOY.md.
- CONFIDENCE: [GÜVEN: YÜKSEK].

## 5. TRACK D — AGENT ESCAPE V2

Full baseline in `docs/research/agent_escape_v2_baseline.md` — 8 classes,
each with threat model, minimal scenario, what TANUQ sees/misses,
detection, containment, verification, evidence, bypass, metric.
ACTION-ONLY vs TRAJECTORY-AWARE kept apart; trajectory items are
DETECTION DESIGNS only, no feature development.

- **FINDINGS:** authority layer robust today against laundering (4) and
  concealment-at-authority (5) — verified invariants. Real gaps are
  trajectory-space (1/3/6/7: cross-proposal correlation, composition,
  trend, cross-agent) — none has an enforcement path proposed; class 2
  residual is runtime observation (credit-blocked); class 8 motivates
  the raise-only advisory shape already in the core.
- **GAPS:** no authenticated agent identity; no cross-workspace
  correlation; operator escape corpora absent (INSUFFICIENT EVIDENCE).
- **SECURITY IMPACT:** none (no code). Future detections must reuse
  trajectory/incidents read-only pattern or raise-only advisory — each
  gated.
- CONFIDENCE: [GÜVEN: YÜKSEK] on current-state facts; [GÜVEN: ORTA] on
  detection-design value.

## 6. TRACK E — MULTI-AGENT BASELINE

`docs/research/multi_agent_baseline.md` — 1→10→50→100 ladder with
rung gates over 7 areas (identity isolation, authorization isolation,
evidence attribution, policy isolation, concurrency, recovery,
throughput).

- **FINDINGS:** policy isolation holds by construction (stateless
  evaluator); authorization isolation holds per current invariants;
  primary measured-unknowns: cross-process in-flight window (FAZ 7
  candidate, documented), evidence schema lacking timestamps/content,
  unauthenticated session identity. "One agent proves the control loop;
  many agents prove the platform" is recorded as a measurement
  principle, not a product claim.
- **SECURITY IMPACT:** none. **RECOMMENDATION:** rung-10 interleaving
  harness via existing CLI only, zero core changes, if scale evidence
  ever justifies it.
- CONFIDENCE: [GÜVEN: YÜKSEK] current state; [GÜVEN: ORTA] projections.

## 7. TRACK F — ARCHITECTURE INTEGRITY

- HEAD `5504d36` == origin/main; working tree clean at round start;
  CI GREEN 4/4 at HEAD (run 35508373388) — CONFIRMED.
- Protected-file diff vs origin/main (`simulation/security/`,
  `simulation/agent/approval/`, patch_proposal/validator/applier,
  tanuq/agent_adapter|pending|coordinator|evidence): **EMPTY** — CONFIRMED.
- Deterministic governance authority, PathPolicy/RiskEngine/RiskPolicy/
  GovernanceEvaluator, ApprovalStore, fingerprint semantics, single-use
  authorization, bounded attempts, pipeline, EventStore/journals/ledger,
  hash-chain anchor, fail-closed, operation_id freeze, Unified Runtime,
  FAZ 7/9 semantics: **UNCHANGED**.
- JEV (or any semantic technology) substitutes for none of these; the
  research explicitly maps every primitive to observer/advisory roles.

## 8. CROSS-TRACK FINDINGS

1. The architecture's two extension shapes (raise-only advisory;
   read-only projection) are sufficient to absorb all 12 researched
   primitives and all 8 escape-class detections without core changes.
2. The idle advisory channel is the single most valuable hook for any
   future semantic technology — but enabling it is a decision gate, not
   a coding task, and requires an injection benchmark first.
3. Every blocked item this round is external: operator corpora, API
   key/credit, tanuq.net deployment.
4. Documentation discipline held: no capability claimed beyond evidence
   anywhere in the surface.

## 9. BLOCKING ISSUES (decisions/inputs, not code)

1. Operator: provide H1-H7 / 24-action corpus definitions (or confirm
   they don't exist) — blocks benchmark design execution.
2. Operator: Jev API key decision — blocked by design until #1 + a
   benchmark need is proven.
3. Operator: tanuq.net deployment (static site is ready).
4. Operator: Claude API credit — unblocks Write runtime dogfood.
5. Owner: review/commit the three research docs (no commit made this
   round, per rules).

## 10. RECOMMENDED NEXT SINGLE TASK

**Real Claude Write runtime dogfood** (PROJECT_STATE's standing NEXT
VALID ACTION): scratch workspace + stdin-capture PreToolUse hook
(method proven) → observe the REAL Write tool_input against the
vendor-documented contract → full chain Write→create→approval→execute→
VERIFIED→evidence.

Why this one: it is the only remaining gap between the product's
confirmed capabilities and its connect-card claim ("Edit and Write
governed"); it needs zero code changes (harness already proven);
operator side is simply enabling API credit; and its outcome either
upgrades G-07's label to CONFIRMED or surfaces the first real adapter
deviation. Everything else researched this round is deliberately
gate-blocked.

---

*Report generated 2026-09-20. No commits, no pushes, no production code
changes. Research docs are untracked files awaiting owner review.*
