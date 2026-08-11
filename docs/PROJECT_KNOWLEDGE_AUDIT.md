# PROJECT_KNOWLEDGE_AUDIT.md

Knowledge audit of the Event-Sourced AI Runtime repository, produced
2026-08-11 at HEAD `96ed72d` (branch `worker-action-pipeline`).
MISSION-011 findings were refreshed by the MISSION-011 close-out on
2026-08-12 (risk engine tested + documented; see sections 3/5/6).

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
| Numbered missions VERIFIED (post-009) | 2 | MISSION-010, MISSION-011 |
| **Total completed/verified** | **19** | 8 + 3 + 8 |

Notes (VERIFIED): MISSION-005..008, MISSION-010 and MISSION-011 each carry
dedicated test files that pass today; MISSION-003 additionally executed a live
real-LLM smoke test (proposal-only) on 2026-08-11. MISSION-011 was closed on
2026-08-12 with 83 risk tests + a fail-closed bug fix.

---

## 3. Open / Active Missions

MISSION-011 (Risk/Policy Engine) is **CLOSED / VERIFIED (2026-08-12)**:
83 deterministic tests pass (`tests/risk_*.py`); fail-closed bug in
`risk_engine.py` fixed; `build_recovery_agent` accepts explicit
`risk_engine`/`risk_policy` opt-in (gate stays off by default, D-021);
MISSION_LOG + docs updated. Implementation commit: `96ed72d`. It is
counted in Section 2 and is NOT an open mission. Remaining open missions:

| Mission | Status | Evidence |
|---------|--------|----------|
| MISSION-012 Human Approval Boundary | **PARTIAL SCAFFOLD** — pipeline consumes `approval_store.find_valid(fingerprint)`; no implementation exists; HIGH/CRITICAL risk fails closed at the approval stage until implemented | `worker_action_pipeline.py:321-347`; grep finds no ApprovalStore class |
| MISSION-013 Advanced adversarial benchmark | **PLANNED** | MISSION-010 remaining work (MISSION_LOG.md:931) |
| MISSION-014 Agent-independent enforcement | **PLANNED** | MISSION_LOG.md:932 |
| MISSION-015 Productization readiness assessment | **PLANNED** | MISSION_LOG.md:933 |

Also OPEN (ROADMAP.md phases, no code): event query engine, runtime
console, secret scanning, benchmarks, multi-agent/concurrency tests, full
recovery scenario suite, external/commercial validation, CI, plugin
architecture, persistent decision trace.

---

## 4. UNKNOWN Missions / Unknowns

- Next mission number after MISSION-015 (inferred MISSION-016, not
  verified). **INFERRED.**
- Scope of MISSION-013/014/015 (no design docs). **UNKNOWN.**
- Live-LLM end-to-end apply/verify/recovery behavior. **UNKNOWN**
  (only proposal-only live path tested).
- Whether the risk gate becomes default-on in the shipped assembly after
  MISSION-012 provides an approval store. **UNKNOWN** (deferred, D-021).
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
1. **Human-approval boundary unimplemented (MISSION-012):** HIGH/CRITICAL
   risk policy depends on an `ApprovalStore` that does not exist; the risk
   gate is therefore default-off and explicit opt-in only (D-021). **HIGH**
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
6. **Human-approval boundary unimplemented** (MISSION-012 scaffold only);
   HIGH/CRITICAL risk policy depends on it; enforced by fail-closed
   blocking until then. **HIGH**
7. **Risk policy fail-closed behavior now proven by tests**
   (UNKNOWN->DENY, HIGH/CRITICAL->human approval, per-level max_attempts,
   depth propagation) — `tests/risk_policy_test.py` + `tests/risk_pipeline_test.py`
   (MISSION-011). **CLOSED**
8. **No secret scanning / supply-chain protection** (ROADMAP Phase 7).
   **MEDIUM** (mitigated: .env gitignored, ProviderError secret-safe).
9. **Repository hygiene:** tracked `.pyc` files
   (`simulation/domain/__pycache__/`, `simulation/security/__pycache__/`),
   junk files (`git` 0 bytes, `kernel.txt`), stray Turkish-named empty
   directories under simulation/. **LOW**

### Product
10. **No external validation** — no market research, no competitor
    comparison, no compliance work (ROADMAP Phase 14). **HIGH** for any
    product claim.
11. **Docs drift** — README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
    docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md describe
    older versions/sprints. **LOW-MEDIUM**

---

## 6. Recommended Next 5 Actions

Ranked by risk reduction vs. effort (MISSION-011 is closed and NOT re-listed):

1. **Implement MISSION-012 Human Approval Boundary:** build a minimal
   `ApprovalStore` (persisted authorization events, fingerprint-keyed) with
   a `find_valid(fingerprint)` implementation, wire it to the pipeline's
   STAGE_APPROVAL, and define how HIGH/CRITICAL risk flows to a human. This
   unblocks re-evaluating whether the risk gate becomes default-on (D-021).
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

## 7. Repository Facts Summary (all VERIFIED; refreshed at MISSION-011 close-out 2026-08-12)

- Branch `worker-action-pipeline` @ `96ed72d`; 14 commits ahead of `main`.
- Working tree: MISSION-011 close-out changes uncommitted (risk tests,
  `recovery_assembly.py` opt-in params, docs).
- Test suite: MISSION-011 close-out **334 passed, 9 skipped**
  (MISSION-011 öncesi baseline: 251 passed / 9 skipped; +83 risk tests).
- 22 test modules (MISSION-011 öncesi baseline: 18).
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
