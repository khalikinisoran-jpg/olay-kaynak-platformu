# PROJECT_KNOWLEDGE_AUDIT.md

Knowledge audit of the Event-Sourced AI Runtime repository, produced
2026-08-11 at HEAD `96ed72d` (branch `worker-action-pipeline`).
MISSION-011 findings were refreshed by the MISSION-011 close-out on
2026-08-12, MISSION-012/013 findings were added by the MISSION-012/013
close-out on 2026-08-12 (human approval boundary + adversarial corpus
extension), MISSION-014 findings were added by the MISSION-014
close-out on 2026-08-12 (authorization boundary hardening; see sections
3/5/6/7), MISSION-016 findings were added by the Chief-Engineer
Gap-Closure sprint on 2026-08-12 (base HEAD `d347f43`; governed runtime,
rollback, approval ledger, event-store/snapshot hardening, verification
hardening, secret/prompt-injection boundary, lazy provider, risk
refinement, corpus A21-A30, CI/packaging), and MISSION-017 findings were
added by the Productization & Human Approval sprint on 2026-08-13 (base
HEAD `a8de82e`; interactive CLI approval console, runtime-mode tests,
corpus A31-A36, CI packaging smoke, approval-lookup benchmark).

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
| MISSION-016 (committed) | 1 | Chief-Engineer Gap-Closure Sprint (`d347f43`, `a8de82e`) |
| MISSION-017 (working tree) | 1 | Productization & Human Approval Sprint |
| MISSION-018A (working tree) | 1 | Risk Boundary Hardening |
| MISSION-018B (working tree) | 1 | Recovery Approval Boundary |
| **Total completed/verified** | **26** | 8 + 3 + 6 + 5 + 1 + 1 + 1 + 1 |

Notes (VERIFIED): MISSION-016 closed 2026-08-12 and was committed
(`d347f43`, `a8de82e`) with **465 passed / 10 skipped**, corpus A01-A30,
and a gated live-LLM E2E pass (real provider). MISSION-017 closed
2026-08-13 in the working tree with **521 passed / 10 skipped**, corpus
A01-A36 (**40 passed / 1 skipped**), and a CI packaging smoke step (not
yet hosted-exercised). MISSION-018A closed 2026-08-13 in the working tree
with **579 passed / 10 skipped** and corpus A01-A50 (**54 passed /
1 skipped**): the risk layer now fails closed on credential-like /
opaque content (`not detected` is never `safe`), closing the MISSION-018
audit evasion classes.

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
| MISSION-017 Productization & Human Approval Sprint | **IMPLEMENTED / VERIFIED-by-suite** (working tree, no commit/push) | full suite 521/10; corpus A01-A36; approval_console.py; runtime_mode_test.py; MISSION_LOG.md |
| MISSION-018A Risk Boundary Hardening | **IMPLEMENTED / VERIFIED-by-suite** (working tree, no commit/push) | full suite 579/10; corpus A01-A50; risk_engine.py SAFE/SUSPICIOUS/OPAQUE; risk_regression_test.py; risk_pipeline_test.py; MISSION_LOG.md; D-029 |
| MISSION-018B Recovery Approval Boundary | **IMPLEMENTED / VERIFIED-by-suite** (working tree, no commit/push) | full suite 594/10; corpus A01-A65; apply_authorization.py fail-closed (store-less HIGH/CRITICAL/UNKNOWN => DENY); agent_run --recovery wired to risk+store; MISSION_LOG.md; D-030 |

Also OPEN (ROADMAP.md phases, no code): event query engine, runtime
console, secret scanning, multi-agent/concurrency tests, full recovery
scenario suite, external/commercial validation, plugin architecture,
persistent decision trace.

---

## 4. UNKNOWN Missions / Unknowns

- Next mission number after MISSION-016/017 (inferred MISSION-018, not
  verified). **INFERRED.**
- Scope of MISSION-015 (no design docs). **UNKNOWN.**
- Live-LLM end-to-end apply/verify/recovery behavior for HIGH/CRITICAL
  with the interactive approval console. **UNKNOWN** (the gated live E2E
  harness exercises the MEDIUM-risk path only; the console path is covered
  deterministically with fake analyzers).
- Whether the risk gate becomes default-on in the shipped assembly now that
  a human-approval UX exists. **UNKNOWN** (D-021/D-022/D-028: gate stays
  explicit opt-in; default-on is a productization decision).
- Whether the MISSION-017 CI packaging smoke step passes on a hosted
  runner. **UNKNOWN** (verified locally only).
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
1. **Interactive human-approval UX now exists** (MISSION-017): CLI
   `ConsoleApprovalGateway`/`approval_console.py` routes explicit human
   decisions into `ApprovalStore.grant`; synchronous (blocks the governed
   run until the operator decides; EOF fails closed). An async/web channel
   remains out of scope. **RESOLVED (CLI).**
2. **No production benchmarks:** the local append benchmark exists
   (`benchmarks/event_store_benchmark.py`, linear ~660-740 appends/s) and
   an approval-lookup benchmark was added (MISSION-017, ~86-89k lookups/s
   in-memory); neither is a production measurement. **LOW-MEDIUM**
3. **Duplicate snapshot implementations** (`persistence/snapshot.py` vs
   `snapshot/snapshot_manager.py` vs `persistence/snapshot_manager.py`),
   legacy `persistence/recovery.py`/`event_store_backup.py`, and
   `simulation/services/` overlap with `agent/executors/`. **LOW-MEDIUM**
4. **No concurrency/multi-agent tests beyond same-store threads** (the
   event store is lock-safe for threads; multi-process writers unsupported).
   **MEDIUM**

### Security
5. **Human-approval UX is CLI/synchronous only** (safe; blocks the
   governed run until the operator decides; EOF fails closed). **LOW**
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

Ranked by risk reduction vs. effort (MISSION-016 committed; MISSION-017
implemented but uncommitted; MISSION-011..014 are closed and NOT re-listed):

1. **Commit / push the MISSION-017 sprint** and run the new CI (incl.
   packaging smoke) on a hosted runner to close the symlink and
   Linux/macOS coverage gap.
2. **Decide the default-on gate** now that a human-approval UX exists
   (MISSION-017): the gate stays explicit opt-in by design (D-021/D-022);
   default-on is an open productization decision.
3. **Synchronize stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
4. **MISSION-015 Productization Readiness Assessment.**
5. **Finish repository hygiene** (legacy `persistence/recovery.py`,
   `event_store_backup.py`, duplicate snapshots, `services/` overlap) with
   dead-code evidence per component.

---

## 7. Repository Facts Summary (all VERIFIED; refreshed at MISSION-017 close-out 2026-08-13)

- Branch `worker-action-pipeline` @ `a8de82e`; 17 commits ahead of `main`.
- Working tree: MISSION-017 sprint changes uncommitted (interactive approval
  console, runtime-mode tests, corpus A31-A36, CI packaging smoke,
  approval-lookup benchmark, doc sync).
- Test suite: MISSION-017 close-out **521 passed, 10 skipped** (MISSION-016
  baseline: 465/10; +56).
- Adversarial corpus: **40 passed / 1 skipped** (A01-A36).
- Gated live-LLM E2E: **1 passed** (real provider, run on 2026-08-12).
- 4 tags: v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0.
- Remote: github.com/khalikinisoran-jpg/olay-kaynak-platformu.git.
- requirements.txt: pytest==9.1.1, requests, python-dotenv; pyproject.toml
  (setuptools packaging metadata; `pip install -e .` verified locally
  2026-08-13).
- .env present locally (OPENROUTER_API_KEY, untracked/gitignored).
- CI workflow: `.github/workflows/ci.yml` (ubuntu + windows; pytest +
  compileall + corpus + diff-check + packaging smoke step added
  MISSION-017). Empty `tests/{chaos,integration,property,unit}` dirs remain.

---

## 8. Classification Legend Used

- **VERIFIED** — confirmed by code, passing tests, and/or commit history.
- **INFERRED** — reasoned from available evidence; not directly tested.
- **UNKNOWN** — cannot be determined from repository evidence.
