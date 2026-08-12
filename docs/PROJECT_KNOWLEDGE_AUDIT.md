# PROJECT_KNOWLEDGE_AUDIT.md

Knowledge audit of the Event-Sourced AI Runtime repository, produced
2026-08-11 at HEAD `96ed72d` (branch `worker-action-pipeline`).
MISSION-011 findings were refreshed by the MISSION-011 close-out on
2026-08-12, MISSION-012/013 findings were added by the MISSION-012/013
close-out on 2026-08-12 (human approval boundary + adversarial corpus
extension), MISSION-014 findings were added by the MISSION-014
close-out on 2026-08-12 (authorization boundary hardening; see sections
3/5/6/7), and MISSION-016 findings were added by the Chief-Engineer
Gap-Closure sprint on 2026-08-12 (base HEAD `d347f43`; governed runtime,
rollback, approval ledger, event-store/snapshot hardening, verification
hardening, secret/prompt-injection boundary, lazy provider, risk
refinement, corpus A21-A30, CI/packaging).

Method: full repository inspection (README, ROADMAP, VISION, CHANGELOG,
docs/*, docs/MISSION_LOG.md, docs/SECURITY_BASELINE.md, all simulation/
source, all tests/, adversarial corpus, Git history: 72 commits, 4 tags).
Evidence hierarchy: Git history > code behavior > test results >
documentation. Classification vocabulary: VERIFIED / INFERRED / UNKNOWN.

---

## 1. Repository Maturity Level

**INFERRED: proof-of-concept with a hardened, reachable governed path.**

Evidence:
- Working, tested event-sourcing + worker action pipeline with a strong
  executable security model (VERIFIED: MISSION-016 close-out suite
  `465 passed / 10 skipped`, adversarial corpus A01-A30).
- The risk/approval/authorization boundary is now reachable from a real
  opt-in runtime path (`agent_run.py --governed`) and single-use approval
  state is durable via an approval ledger (MISSION-016).
- But: no production configuration, no hosted deployment, no multi-user
  story, no externally exercised CI run, no external validation
  (VERIFIED: `.github/workflows/ci.yml` added but not run on a hosted
  runner).
- Latest release tag v0.5.0 predates the worker-action-pipeline work;
  everything since is unreleased (VERIFIED: `git tag`).

---

## 2. Completed Mission Count

From docs/MISSION_LOG.md + commit evidence (see docs/MISSION_STATUS.md):

| Category | Count | Detail |
|----------|-------|--------|
| Historic (pre-numbering) IMPLEMENTED missions | 8 | 4809b2b, b9ddb74, 9ef829a, 9df8390, 5c475b6, 609b89c, f40ceab, 90400c9 |
| Documentation/sync missions (DONE) | 3 | 3966e18, 19c6e85/3966e18, 9b5c21e (MISSION-009) |
| Numbered missions VERIFIED | 6 | MISSION-003, 004, 005, 006, 007, 008 |
| Numbered missions VERIFIED (post-009) | 5 | MISSION-010, MISSION-011, MISSION-012, MISSION-013, MISSION-014 |
| MISSION-016 (working tree, no commit) | 1 | Chief-Engineer Gap-Closure Sprint |
| **Total completed/verified** | **23** | 8 + 3 + 11 + 1 |

Notes (VERIFIED): MISSION-016 closed 2026-08-12 in the working tree with
**465 passed / 10 skipped**, corpus A01-A30 (**34 passed / 1 skipped**),
and a gated live-LLM E2E pass (real provider).

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
| MISSION-016 Chief Engineer Gap-Closure Sprint | **IMPLEMENTED / VERIFIED-by-suite** (working tree, no commit/push) | full suite 465/10; corpus A01-A30; live-LLM E2E 1 passed; MISSION_LOG.md |

Also OPEN (ROADMAP.md phases, no code): event query engine, runtime
console, secret scanning, multi-agent/concurrency tests, full recovery
scenario suite, external/commercial validation, plugin architecture,
persistent decision trace.

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
1. **No interactive human-approval UX (MISSION-012/014/016 implemented):**
   the `Approval`/`ApprovalStore`/`ApprovalLedger` boundary is implemented,
   tested and durable, but granting an approval still requires a
   programmatic call. **MEDIUM**
2. **No production benchmarks:** the local append benchmark exists
   (`benchmarks/event_store_benchmark.py`, linear ~800-815 appends/s) but is
   not a production measurement. **LOW-MEDIUM**
3. **Duplicate snapshot implementations** (`persistence/snapshot.py` vs
   `snapshot/snapshot_manager.py` vs `persistence/snapshot_manager.py`),
   legacy `persistence/recovery.py`/`event_store_backup.py`, and
   `simulation/services/` overlap with `agent/executors/`. **LOW-MEDIUM**
4. **No concurrency/multi-agent tests beyond same-store threads** (the
   event store is lock-safe for threads; multi-process writers unsupported).
   **MEDIUM**

### Security
5. **Human-approval UX missing** (safe, not interactive). **MEDIUM**
6. **Secret redaction / prompt-injection are heuristics, not guarantees**
   (documented; secret files skipped wholesale, inline redaction
   best-effort). **MEDIUM** (mitigated)
7. **Approval durability requires a wired `ApprovalLedger`.** Without a
   ledger the store is in-memory. **LOW-MEDIUM** (governed CLI wires it)
8. **No secret scanning / supply-chain protection** (ROADMAP Phase 7).
   **MEDIUM** (mitigated: .env gitignored, ProviderError secret-safe,
   secret files skipped on the read path)
9. **Repository hygiene:** tracked junk staged for removal (`git`,
   `kernel.txt`, `.pyc`); stray dirs removed; docs drift in README/
   CHANGELOG/PROJECT_CONTEXT. **LOW**

### Product
10. **No external validation** — no market research, no competitor
    comparison, no compliance work (ROADMAP Phase 14). **HIGH** for any
    product claim.
11. **CI exists but not exercised on a hosted runner.** **LOW-MEDIUM**
12. **Docs drift** — README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
    docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md describe
    older versions/sprints. **LOW-MEDIUM**

---

## 6. Recommended Next 5 Actions

Ranked by risk reduction vs. effort (MISSION-016 is implemented but
uncommitted; MISSION-011..014 are closed and NOT re-listed):

1. **Build the human-approval UX:** the boundary + ledger are implemented,
   tested and durable (MISSION-012/014/016); add the interaction that
   routes a HIGH/CRITICAL request to a human and back into `grant` (CLI
   prompt or approval-file intake). Last piece before default-on can be
   re-evaluated (D-022).
2. **Commit / push the MISSION-016 sprint**, then run the new CI on
   Linux/macOS to close the symlink coverage gap.
3. **Synchronize stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
4. **MISSION-015 Productization Readiness Assessment.**
5. **Finish repository hygiene** (legacy `persistence/recovery.py`,
   `event_store_backup.py`, duplicate snapshots, `services/` overlap) with
   dead-code evidence per component.

---

## 7. Repository Facts Summary (all VERIFIED; refreshed at MISSION-016 close-out 2026-08-12)

- Branch `worker-action-pipeline` @ `d347f43`; 16 commits ahead of `main`.
- Working tree: MISSION-016 sprint changes uncommitted (governed CLI,
  rollback, approval ledger, event-store/snapshot hardening, verification
  hardening, secret boundary, lazy provider, risk refinement, corpus
  A21-A30, CI, pyproject, new tests; tracked junk staged for removal).
- Test suite: MISSION-016 close-out **465 passed, 10 skipped** (MISSION-014
  baseline: 390/9; +75).
- Adversarial corpus: **34 passed / 1 skipped** (A01-A30).
- Gated live-LLM E2E: **1 passed** (real provider, run on 2026-08-12).
- 4 tags: v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0.
- Remote: github.com/khalikinisoran-jpg/olay-kaynak-platformu.git.
- requirements.txt: pytest==9.1.1, requests, python-dotenv; pyproject.toml
  added (setuptools packaging metadata).
- .env present locally (OPENROUTER_API_KEY, untracked/gitignored).
- CI workflow added: `.github/workflows/ci.yml` (ubuntu + windows; pytest +
  compileall + corpus + diff-check). Empty `tests/{chaos,integration,
  property,unit}` dirs remain.

---

## 8. Classification Legend Used

- **VERIFIED** — confirmed by code, passing tests, and/or commit history.
- **INFERRED** — reasoned from available evidence; not directly tested.
- **UNKNOWN** — cannot be determined from repository evidence.
