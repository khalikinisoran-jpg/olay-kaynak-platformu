# PROJECT_KNOWLEDGE_AUDIT.md

Knowledge audit of the Event-Sourced AI Runtime repository, produced
2026-08-11 at HEAD `96ed72d` (branch `worker-action-pipeline`).
MISSION-011 findings were refreshed by the MISSION-011 close-out on
2026-08-12, MISSION-012/013 findings were added by the MISSION-012/013
close-out on 2026-08-12 (human approval boundary + adversarial corpus
extension), and MISSION-014 findings were added by the MISSION-014
close-out on 2026-08-12 (authorization boundary hardening; see sections
3/5/6/7).

Method: full repository inspection (README, ROADMAP, VISION, CHANGELOG,
docs/*, docs/MISSION_LOG.md, docs/SECURITY_BASELINE.md, all simulation/
source, all tests/, adversarial corpus, Git history: 71 commits, 4 tags).
Evidence hierarchy: Git history > code behavior > test results >
documentation. Classification vocabulary: VERIFIED / INFERRED / UNKNOWN.

---

## 1. Repository Maturity Level

**INFERRED: Proof-of-concept (pre-alpha engineering prototype).**

Evidence:
- Working, tested event-sourcing + worker action pipeline with a strong
  executable security model (VERIFIED: MISSION-011 close-out suite
  `334 passed / 9 skipped`, adversarial corpus A01-A12).
- But: no production configuration, no CI pipeline, no packaging, no
  deployment story, no external validation (VERIFIED: `.github/workflows/`
  empty; ROADMAP.md Phase 2/3/14 all "Planned").
- Latest release tag v0.5.0 predates the worker-action-pipeline work;
  everything since is unreleased (VERIFIED: `git tag`).
- The docs themselves describe the project as "experimental"
  (VERIFIED: README.md).

---

## 2. Completed Mission Count

From docs/MISSION_LOG.md + commit evidence (see docs/MISSION_STATUS.md):

| Category | Count | Detail |
|----------|-------|--------|
| Historic (pre-numbering) IMPLEMENTED missions | 8 | 4809b2b, b9ddb74, 9ef829a, 9df8390, 5c475b6, 609b89c, f40ceab, 90400c9 |
| Documentation/sync missions (DONE) | 3 | 3966e18, 19c6e85/3966e18, 9b5c21e (MISSION-009) |
| Numbered missions VERIFIED | 6 | MISSION-003, 004, 005, 006, 007, 008 |
| Numbered missions VERIFIED (post-009) | 5 | MISSION-010, MISSION-011, MISSION-012, MISSION-013, MISSION-014 |
| **Total completed/verified** | **22** | 8 + 3 + 11 |

Notes (VERIFIED): MISSION-005..008, MISSION-010..014 each carry dedicated
test files that pass today; MISSION-003 additionally executed a live
real-LLM smoke test (proposal-only) on 2026-08-11. MISSION-011 was closed
on 2026-08-12 with 83 risk tests + a fail-closed bug fix. MISSION-012
(human approval boundary) and MISSION-013 (adversarial corpus extension)
were closed on 2026-08-12 with 31 approval tests + corpus A13-A20.
MISSION-014 (authorization boundary hardening) was closed on 2026-08-12
with 17 additional boundary tests (approval_boundary_test.py, 48 total).

---

## 3. Open / Active Missions

MISSION-011 (Risk/Policy Engine) is **CLOSED / VERIFIED (2026-08-12)**:
83 deterministic tests pass (`tests/risk_*.py`); fail-closed bug in
`risk_engine.py` fixed; `build_recovery_agent` accepts explicit
`risk_engine`/`risk_policy` opt-in (gate stays off by default, D-021);
MISSION_LOG + docs updated. Implementation commit: `96ed72d`. It is
counted in Section 2 and is NOT an open mission.

MISSION-012 (Human Approval Boundary) is **CLOSED / VERIFIED
(2026-08-12)**: `Approval` + `ApprovalStore` implemented; pipeline-level
typed + full-binding validation; single-use/fingerprint-bound/evidence-
recorded; 31 tests (`tests/approval_boundary_test.py`); corpus A13-A20.
MISSION-013 (Advanced Adversarial Benchmark) is **CLOSED / VERIFIED
(2026-08-12)**: corpus extended from A01-A12 to A01-A20 (approval replay/
substitution/expiry/forgery/boundary-bypass records), summary-gated.
MISSION-014 (Authorization Boundary Hardening) is **CLOSED / VERIFIED
(2026-08-12)**: the apply authorization boundary is now store-backed and
fail-closed — typed `ControllerDecision`, exact fingerprint, and for
HIGH/CRITICAL/UNKNOWN applies a store-verified, single-use approval
binding consumed at the apply boundary (`ApprovalStore.authorize_apply`,
patch-object identity binding); 17 new boundary tests (A–O) in
`tests/approval_boundary_test.py` (48 total).

Remaining open missions:

| Mission | Status | Evidence |
|---------|--------|----------|
| MISSION-015 Productization readiness assessment | **PLANNED** | MISSION_LOG.md (MISSION-014 remaining work) |

Also OPEN (ROADMAP.md phases, no code): event query engine, runtime
console, secret scanning, benchmarks, multi-agent/concurrency tests, full
recovery scenario suite, external/commercial validation, CI, plugin
architecture, persistent decision trace.

---

## 4. UNKNOWN Missions / Unknowns

- Next mission number after MISSION-015 (inferred MISSION-016, not
  verified). **INFERRED.**
- Scope of MISSION-015 (no design docs). **UNKNOWN.**
- Live-LLM end-to-end apply/verify/recovery behavior. **UNKNOWN**
  (only proposal-only live path tested).
- Whether the risk gate becomes default-on in the shipped assembly after a
  human-approval UX exists. **UNKNOWN** (D-021/D-022: gate stays explicit
  opt-in; default-on is a productization decision).
- Symlink-dependent security behavior outside this Windows environment.
  **UNKNOWN** (7 tests skip where symlinks are denied).
- Whether the "weather" planner strategy is intended to work.
  **UNKNOWN** (planner produces it; dispatcher cannot dispatch it).
- Historic MISSION_LOG records state "IMPLEMENTED" without current test
  re-verification; today's suite covers them, so effectively
  verified-by-suite. **INFERRED.**

---

## 5. Critical Gaps

### Technical
1. **No interactive human-approval UX (MISSION-012 implemented):** the
   `Approval`/`ApprovalStore` boundary is implemented and tested, but
   granting an approval still requires a programmatic call; the flow that
   routes a HIGH/CRITICAL request to a human and back is missing. **MEDIUM**
2. **Verification `compile`-only depth is tested but never policy-selected**
   (every non-deny policy level uses `compile+tests`). **LOW**
3. **`weather` strategy unroutable** — ValueError at runtime.
   **LOW-MEDIUM**
4. **Duplicate snapshot implementations** (`persistence/snapshot.py` vs
   `snapshot/snapshot_manager.py` vs `persistence/snapshot_manager.py`),
   legacy `persistence/recovery.py`/`event_store_backup.py`, and
   `simulation/services/` overlap with `agent/executors/`.
   **LOW-MEDIUM**
5. **No benchmarks / no concurrency tests / no full recovery scenario
   suite** (restart, snapshot+replay+hash after recovery). **MEDIUM**

### Security
6. **Human-approval UX missing** (MISSION-012/014 implemented and hardened
   the boundary; there is no interactive grant flow yet). Without a grant,
   HIGH/CRITICAL still fails closed — safe, but not usable end-to-end.
   **MEDIUM**
7. **Risk policy fail-closed behavior now proven by tests**
   (UNKNOWN->DENY, HIGH/CRITICAL->human approval, per-level max_attempts,
   depth propagation) — `tests/risk_policy_test.py` + `tests/risk_pipeline_test.py`
   (MISSION-011). **CLOSED**
8. **Authorization boundary now proven fail-closed by tests**
   (MISSION-014): typed `ControllerDecision`, store-verified single-use
   approval binding at the apply boundary, object-identity patch binding,
   replay/expiry/forgery/evidence-only/metadata-injection denial —
   `tests/approval_boundary_test.py` (48 tests) + corpus A01-A20. **CLOSED**
9. **No secret scanning / supply-chain protection** (ROADMAP Phase 7).
   **MEDIUM** (mitigated: .env gitignored, ProviderError secret-safe).
10. **Repository hygiene:** tracked `.pyc` files
    (`simulation/domain/__pycache__/`, `simulation/security/__pycache__/`),
    junk files (`git` 0 bytes, `kernel.txt`), stray Turkish-named empty
    directories under simulation/. **LOW**

### Product
11. **No external validation** — no market research, no competitor
    comparison, no compliance work (ROADMAP Phase 14). **HIGH** for any
    product claim.
12. **Docs drift** — README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
    docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md describe
    older versions/sprints. **LOW-MEDIUM**

---

## 6. Recommended Next 5 Actions

Ranked by risk reduction vs. effort (MISSION-011, MISSION-012,
MISSION-013 and MISSION-014 are closed and NOT re-listed):

1. **Build the human-approval UX:** the `ApprovalStore` boundary is
   implemented, tested and hardened at the apply boundary (MISSION-012/
   014); add the interaction that routes a HIGH/CRITICAL request to a
   human and back into `grant` (CLI prompt or approval-file intake). This
   is the last piece before default-on can be re-evaluated as a product
   decision (D-022).
2. **Synchronize stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
3. **Fix the `weather` routing gap or remove the branch** (Planner produces
   "weather" that StrategyDispatcher cannot dispatch); add a planner/dispatcher
   contract test.
4. **Clean repository hygiene** (tracked `.pyc`, junk files, stray
   directories) in a docs/hygiene commit.
5. **Close MISSION-009 documentation** (referenced as a sync task but with no
   dedicated MISSION_LOG entry).

---

## 7. Repository Facts Summary (all VERIFIED; refreshed at MISSION-014 close-out 2026-08-12)

- Branch `worker-action-pipeline` @ `f94c82b`; 14 commits ahead of `main`.
- Working tree: MISSION-012/013/014 close-out changes uncommitted
  (approval module, apply-authorization hardening, pipeline wiring,
  tests, corpus extension, docs).
- Test suite: MISSION-014 close-out **390 passed, 9 skipped**
  (MISSION-012/013 close-out baseline: 373 passed / 9 skipped; +17
  MISSION-014 authorization-boundary tests).
- 23 test modules (MISSION-011 close-out baseline: 22).
- 4 tags: v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0.
- Remote: github.com/khalikinisoran-jpg/olay-kaynak-platformu.git.
- requirements.txt: pytest==9.1.1, requests, python-dotenv.
- .env present locally (OPENROUTER_API_KEY, untracked/gitignored).
- No CI workflows; empty tests/{chaos,integration,property,unit} dirs.

---

## 8. Classification Legend Used

- **VERIFIED** — confirmed by code, passing tests, and/or commit history.
- **INFERRED** — reasoned from available evidence; not directly tested.
- **UNKNOWN** — cannot be determined from repository evidence.
