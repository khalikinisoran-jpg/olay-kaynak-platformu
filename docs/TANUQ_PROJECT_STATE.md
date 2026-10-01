# TANUQ PROJECT STATE — META / HANDOFF / CURRENT POSITION

> **ROLE OF THIS FILE (READ FIRST):** This is the *current-position and
> handoff* layer. It is **NOT** a second truth source. Canonical sources:
> `docs/SECURITY_MODEL.md` (security decisions), `ORCHESTRATION_BOUNDARY.md`
> (architecture map), `ORCHESTRATION_LIFECYCLE_DESIGN.md` (lifecycle freeze),
> `docs/ROADMAP.md` (historical roadmap), the code itself. If this file
> contradicts a canonical source, **the canonical source wins** and the
> contradiction must be reported and fixed here.
>
> **UPDATE PROTOCOL:** After every meaningful session, update
> `LAST UPDATED`, `CURRENT PHASE`, `RECENT COMMITS`, `CI STATUS`,
> `NEXT VALID ACTION`, `DAILY HANDOFF` (latest entry only — do not
> accumulate old entries), and any changed `FROZEN DECISIONS`.
>
> **NEW SESSION PROTOCOL:** Do not start coding. Read this file, check
> git HEAD/worktree vs the recorded state, check CI, report a
> `TANUQ — SESSION RESYNC` (format at the bottom), then pick the next
> valid action.

LAST UPDATED: 2026-09-28

---

## CURRENT PHASE

FAZ 1 (Boundary Mapping) **COMPLETE**.
FAZ 2 (Operation Identity) **BLOCKED** by frozen decision — see
FROZEN DECISIONS. Roadmap phases 3-4 depend on FAZ 2; phases 5-10 are
sequential behind them. FAZ 6-lite A/B (resume + cross-source correlation) are **SHIPPED**
(7de6a55 / 3b8e259); productization phases 1-4 are **COMPLETE**
(fresh-install path, status --json, docs entry chain, honest limits,
ADR). Current phase: **early-adopter productization** —
awaiting real-usage evidence and operator decisions (Claude access).

REPOSITORY CHECKPOINT (2026-09-28): **HEAD == origin/main ==
45e3072e67feb027b1ae9ab10e89680811dddcfb** —
`docs(quickstart): use action=create in the new-file example`
(pushed, fast-forward, hosted CI GREEN 4/4 = run 36476641745).
FREE release chain (2026-09-27..28): `b5841f9` (FREE distribution
strategy) → `7d7ee8a`/`e7c1174` (feedback prompts + real mailto
channel) → `ed1c6c5` (FAZ 1 local usage signal) → `c48e786`
(FAZ 2.1 opt-out + FAZ 2.2 anonymous remote transport) → `cf638b1`
(test isolation) → `9e133a2` (FREE roadmap/state sync) → `45e3072`
(QUICKSTART `action=create` fix — F1 follow-up).
**CURRENT STRATEGY: FREE distribution → real usage → real feedback →
product signals → evidence-based commercialization decision later.**
(Orchestration release chain `508382b → 45b2296 → 2222b07` is history;
see PUBLIC SITE CHECKPOINT for live state.)

## CURRENT OBJECTIVE

FAZ 6-lite A/B, the Claude Code Edit/Write adapter, UX fixes and
productization phases 1-4 are **SHIPPED** (latest: `3f7182b`). Per the
productization-first working model (below), the current objective is
**real-usage evidence**: run real daily-driver work through the
governed chain (self-hosted repo governance, UI dogfood done),
collect CONFIRMED friction/needs, and keep the core stable — no
speculative architecture (operation_id stays FROZEN).

## ROADMAP POSITION

```text
FAZ 1  Boundary Mapping          COMPLETE  (ORCHESTRATION_BOUNDARY.md, committed 69f8d39)
FAZ 2  Operation Identity        BLOCKED   (OPERATION_ID: NOT REQUIRED — FROZEN)
FAZ 3  Lifecycle                 BLOCKED   (depends on FAZ 2; projection already exists)
FAZ 4  OperationCoordinator      BLOCKED   (depends on FAZ 2/3; coordinator REUSE confirmed)
FAZ 5  Unified Runtime           OPEN      (requires reorder decision; runtime duplication CONFIRMED)
FAZ 6  Wait / Resume             OPEN — RECOMMENDED NEXT (6-lite; identity prerequisites proven)
FAZ 7  Concurrency               OPEN      (_ProcessFileLock primitive exists + tested)
FAZ 8  Recovery                  PARTIAL   (detection/reconciliation exist; orchestration is design)
FAZ 9  Multi-Patch               BLOCKED   (bundle identity = frozen-decision revisit condition)
FAZ 10 Product layers            NOT STARTED (no proven need)
```

## FREE PRODUCT ROADMAP (CURRENT — AUTHORITATIVE)

> Authoritative FREE product roadmap as of 2026-09-28 (F1 closed). The orchestration
> table above (FAZ 1..10) is ARCHITECTURE history and stays frozen.
> **NAMING WARNING:** "**FAZ 2 (Operation Identity)**" = architecture
> freeze (historical, BLOCKED-by-decision); "**FAZ 2.1 / 2.2**" =
> usage-telemetry phases (2026-09-27). Different numbering — never
> conflate the two.

| Gate | State | Evidence / prerequisite |
|---|---|---|
| **F0 — Release Gate** | **CLOSED (PASS)** | FAZ 2.1 + FAZ 2.2 + test-isolation committed (`c48e786`, `cf638b1`); CI 4/4 (run 36371113909) |
| **F1 — FREE E2E Local Validation** | **CLOSED (PASS)** | PASS recorded 2026-09-28 from an **in-session validation only** (fresh clone → `pip install -e .` → init → HIGH create approve → execute VERIFIED → verify/lineage/export → cleanup); **no in-repo artifact exists — do not cite repo evidence for F1**. Blocker found (QUICKSTART example missing `action`) fixed in `45e3072` |
| **F2 — Distribution / Installation** | **NEXT (decision gate — no implementation/publish approval yet)** | LICENSE file (**YOK**), NOTICE scope, ownership/identity confirmation, package naming (`event-sourced-ai-runtime` ≠ `tanuq`), PyPI account/publish (**YOK**), version policy = owner decisions; read-only audits delivered in-session, repo untouched |
| F3 — Public FREE Acquisition Path Validation | afterwards | live site: acquisition → install path end-to-end |
| F4 — First User / Feedback Validation | afterwards | first external users + `feedback@tanuq.net` intake |
| F5 — Usage / Telemetry Decision Gate | afterwards | local signals exist → decide remote default/endpoint with real data |
| FAZ 2.3 — Remote Endpoint Integration | CONDITIONAL | only with a real endpoint + owner decision; **real endpoint/backend: YOK today** |

**Active FREE strategy:** free distribution → real usage → real feedback →
product signals → evidence-based commercialization decision later.

**Commercial facts (as released):** `$19 one-time` = **SUPERSEDED** ·
`$49/month` = **SUPERSEDED for the current FREE strategy** ·
"free forever" = **NOT USED (no such promise)** · future pricing =
**UNKNOWN / undecided** · commercial signal ≠ WTP ·
positioning = **no account / no payment / no subscription** ·
feedback channel = `mailto:feedback@tanuq.net` ·
public GitHub acquisition claim = **removed**.

**Out of FREE scope:** Enterprise / Autonomous roadmap items live in
`docs/roadmap.md` and are **HISTORICAL** (banner added there).

## COMPLETED

- Verification Reality V1: real workspace tests + dummy-floor fallback,
  journaled profile (7525c66).
- RT-2 CLOSED: verification subprocess isolation (Tanuq-owned pytest
  config, confcutdir, PYTEST_ADDOPTS/PYTEST_PLUGINS scrub) (2536af0).
- RT-1 CLOSED: R1 selection integrity (same-run patch targets can never
  be verifiers) + G1 governance gate (modifying an EXISTING test module
  → HIGH → human approval) (2536af0).
- FAZ 1 boundary map committed (69f8d39).
- Claude Code adapter: PreToolUse governed entry, committed (b061d03).
- FAZ 6-lite A: resume-after-approval + pending fingerprint dedupe —
  **IMPLEMENTED, COMMITTED (7de6a55), hosted CI SUCCESS (4/4 jobs).**
- FAZ 6-lite B: cross-source resume via adapter content correlation —
  **FINALIZED (3b8e259, hosted CI SUCCESS 4/4). F1 (cross-source
  fingerprint mismatch) CLOSED — CONFIRMED via real CLI + real Claude
  hook dogfood.**
- NEW-FILE CREATE: governed `create` action (old_content=""
  convention) through the existing chain — **FINALIZED (654bf56,
  hosted CI SUCCESS 4/4). No new identity/authority; fingerprint,
  ApprovalStore, RiskEngine/PathPolicy untouched. Controller.py
  action-gate extension CONFIRMED REQUIRED (single whitelist line).
   Evidence: 29 create tests + full suite 1438/15/0 + real CLI
   dogfood PASS (propose→HIGH→approve→execute→VERIFIED→evidence
   VALID).**
- CLAUDE WRITE → GOVERNED CREATE: vendor Write tool translated to the
  canonical create action (old_content="" convention) in the
  translation layer only — **FINALIZED (ebd52b1, hosted CI SUCCESS
  4/4, run 34589680409). Core diff = 0 (vendor-blind governance
  confirmed); Write existing file → fail-closed DENY; create
  correlation tool-aware. Evidence: 19 Write tests (vendor-doc
  fixtures) + 30 adapter tests + full suite 1457/15/0. Runtime
  vendor dogfood BLOCKED (Claude API credit balance).**
- VENDOR-NEUTRALITY AUDIT (read-only, ebd52b1): vendor-specific code
  confined to `tanuq/claude_code_adapter.py`; canonical chain
  (agent_adapter/pending/coordinator/fingerprint/risk/approval/
  validation/pipeline/verification/evidence) vendor-blind (rg scan:
  zero vendor references outside secret-redaction regex). Generic
  normalizer NOT REQUIRED (1 vendor module, zero core-diff expansion
  proven twice).
- PRODUCTIZATION PHASES 1-4 (0a9bd45): P1 fresh-install proof —
  packaging correct (`tanuq` console script + packages.find); the
  stale global editable install was an operator-env issue, not a
  product bug. P2 fresh clone + venv + governed cycle + README
  demo_cli OVERALL PASS (approval/replay/evidence invariants). P3
  version metadata fix — `tanuq --version` hard-coded 0.1.0 →
  packaging metadata 0.6.0 via importlib.metadata (0a9bd45, hosted
  CI SUCCESS 4/4, run 34610594860; 3 new version tests; full suite
  1464/15/0). P4 audit: release readiness = early-adopter (Windows,
  n=1 user).
- CROSS-MODEL REAL DOGFOOD (CONFIRMED): a non-Claude model (GLM) as
  the proposal source drove the generic `--stdin-json` channel
  end-to-end in a real workspace — modify (incl. one real
  verification failure → auto-rollback → resubmit → VERIFIED),
  create (HIGH → approval → VERIFIED), create-on-existing DENY,
  traversal DENY, evidence chain VALID, history denied_reason
  visible. "GLM" appears only in proposal free-text reason, never in
  risk/approval/execution payloads (JSON scan). SECOND INDEPENDENT
  MODEL/PROPOSAL SOURCE — CONFIRMED.
- SKILL RELEASE (a67069d): AGENTS.md (pointer + critical rules) and
  docs/TANUQ_SKILL.md (working procedure: resync, frozen boundaries,
  stop rules, evidence discipline, report format, BDP v1.5, hard-no)
  — "Skill instructs the agent; TANUQ governance controls mutations."
- UX RELEASES (2f842ac, 738a158, 4302409): hook interpreter note in
  AGENT_INTEGRATION.md; QUICKSTART create example now shows the
  approval step before execute; propose-time stale old_content warning
  (read-only UX, fingerprint-external; 5 tests; full suite 1469/15/0).

## IN PROGRESS

- Tracked working tree: **only this state file** is modified
  (this state-sync commit); all other tracked files are clean at
  `2222b07` (verified `git status --short`). Untracked release-outside
  artifacts (`.venv-validation/`, 31 × `docs/research/*`,
  `site/assets/tanuq-logo-header.png`) are **OUT OF RELEASE SCOPE** and
  deliberately untouched.
- Next candidate work is designed but not started: real Claude Write
  runtime dogfood (blocked on API credit); Sol/Codex review resume
  (artifact manifest ready).

## NEXT VALID ACTION

**CURRENT (2026-09-28) — single next task/gate:** **F2 —
Distribution / Installation DECISIONS** (LICENSE/NOTICE, ownership
confirmation, package naming, PyPI account & version policy; see FREE
PRODUCT ROADMAP above). **F1 is CLOSED (PASS)** — in-session
validation only (2026-09-28), no in-repo artifact; its QUICKSTART
blocker was fixed in `45e3072`. **F2 implementation/publish is NOT
yet approved.**

**Commercial state as released (FREE strategy):** TANUQ is distributed
**FREE** — no account / no payment / no subscription. `$49/month` and
`START ACQUISITION` are **SUPERSEDED** (removed from the site in
`b5841f9`); "free forever" is **not promised**; future pricing =
**UNKNOWN / undecided**; WTP, real payment, first external user and
conversion all remain **UNKNOWN** until measured; commercial signal ≠ WTP.
Feedback intake: `mailto:feedback@tanuq.net`.

Historical (RESOLVED 2026-09-26): "deploy `site/` to tanuq.net" gate —
owner executed the manual upload; agent-side deploy was BLOCKED once
(no hosting credentials/channel available) and is no longer pending.

Standing items (unchanged):
1. Real Claude Code Write runtime dogfood (BLOCKED on API credit):
   scratch workspace + stdin-capture PreToolUse hook (method proven)
   → observe REAL Write tool_input vs vendor-documented contract →
   full chain Write→create→approval→execute→VERIFIED→evidence.
2. Hygiene: `.gitignore` already extended (dist/, child_*.dmp,
   _dbg_*, _diag*, _run_obs*, _verify_postfix*, request.json, t);
   remaining operator items — quarantine `child_*.dmp` (secrets),
   `ORCHESTRATION_LIFECYCLE_DESIGN.md` is committed (567f5f5); analyse/delete quarantined dumps (operator).
3. Then: product dogfooding with create+modify flows on a scratch
   workspace (multi-file behavior, pending UX) or FAZ 2 gate
   discussion (only with proven-need evidence).

## BLOCKED ITEMS

- FAZ 2/3/4: frozen-decision gate (`OPERATION_ID: NOT REQUIRED —
  FROZEN`). Reopen condition: a PROVEN coordination requirement that
  fingerprint + intent_id + pending + evidence cannot express
  (e.g. multi-patch bundle identity). "Might be useful later" is NOT
  a trigger.
- FAZ 9 Multi-Patch: bundle identity is exactly that revisit condition.
- Claude adapter follow-ups: none blocking; adapter is committed and
  CI-verified.

## FROZEN DECISIONS

1. `OPERATION_ID: NOT REQUIRED — FROZEN` — operation_id must NOT be
   added; reopen only via the condition above (human decision).
2. FAZ 6-lite was chosen WITHOUT operation_id — any implementation
   that needs one violates this freeze.
3. Governance policy G1: modifying an EXISTING verification test
   module (`test_*.py` / `*_test.py` / `conftest.py`) requires human
   approval (RiskEngine signal `modifies_existing_test_module` →
   HIGH). Do not weaken.
4. Verification selection integrity R1: same-execution patch targets
   can never be verification targets. Do not weaken.
5. RT-2 subprocess isolation: Tanuq-owned pytest config, confcutdir,
   env scrub. Do not weaken.
6. Assembly policy: p5/ and agent_run.py are separate legacy
   assemblies; do not touch them without an explicit architecture
   decision.

## OPERATOR DECISIONS REQUIRED

1. Commit/push the FAZ 6-lite A working-tree changes (above).
2. Roadmap reorder: approve FAZ 6-lite ahead of FAZ 2-5 (or keep the
   sequential order and accept that nothing can start until the FAZ 2
   gate opens).
3. `child_*.dmp` files in the repo root contain REAL API tokens
   (secret_guard findings) — delete/quarantine them (human action).
4. `ORCHESTRATION_LIFECYCLE_DESIGN.md` is still untracked — decide
   whether to commit it as a design-freeze record.
5. `docs/PROJECT_STATE.md` / `PROJECT_MASTER.md` are stale (P10-era,
   reference 9df6953) — decide whether to archive or synchronize them
   (this file does not replace them).

## ARCHITECTURAL INVARIANTS

```text
Governance Core      = AUTHORITY   (RiskEngine/RiskPolicy/ApprovalStore/ApplyAuthorization/VerificationExecutor)
OperationCoordinator = COORDINATION (delegation + RAM in-flight only)
Journal/EventStore   = EVIDENCE    (hash-chained, append-only, fail-closed)
Human Approval       = AUTHORIZATION (single-use, fingerprint-bound, TTL)
Agent/LLM            = UNTRUSTED ACTOR
WorkerActionPipeline = MUTATION    (only component family writing workspace files)
```

Fingerprint semantics: canonical SHA-256 over path/action/reason/
old/new/allowed_paths (patch_proposal.py:16) — never changed.
OperationCoordinator: no grant/consume/apply/verify authority
(coordinator.py + contract tests).

## SECURITY INVARIANTS

- RT-2: verification subprocess uses a Tanuq-owned pytest config
  (`-c`), `--confcutdir` bounds conftest loading, `PYTEST_ADDOPTS` /
  `PYTEST_PLUGINS` scrubbed. Workspace pytest config and inherited
  environment cannot steer verification.
- RT-1 R1: same-execution patch targets are never verification
  targets; excluded selections fall back to the dummy floor.
- RT-1 G1: existing test module modifications require human approval.
- Fail-closed: missing/expired/mismatched approval → DENIED;
  exit code 5 ("no tests collected") → FAIL; timeout → FAIL;
  verification failure → ROLLED_BACK.
- Known residuals (documented, accepted): helper-module weakening
  outside the test naming convention; pre-existing weak tests;
  cross-assembly workspace collision UNKNOWN; cross-process
  in-flight serialization absent (fail-closed compensations).

## RECENT COMMITS

```text
45e3072 docs(quickstart): use action=create in the new-file example   <- CURRENT CHECKPOINT (HEAD == origin/main)
9e133a2 docs(state): sync FREE roadmap and project state
cf638b1 test(usage): isolate CLI usage tests from real home
c48e786 feat(usage): add anonymous remote usage transport
ed1c6c5 feat(usage): add local usage signal derivation
e7c1174 feat(site): connect free user feedback email channel
7d7ee8a feat(site): add real feedback channel for free users
b5841f9 feat(site): launch TANUQ free distribution strategy
e4d9b72 docs(state): sync project state after public site release
2222b07 feat(site): add English default and Turkish /tr public site
45b2296 feat(site): finalize public TANUQ product experience
508382b feat(site): polish public TANUQ experience
5d90ff9 feat(site): add interactive TANUQ demo experience
98da708 chore(research): archive Luna and Sol raw artifacts
ecf00fd Harden approval TTL and pending API auth
f0d09b6 feat(observation): add read-only post-hoc observation projection (E5/Semantic V1)
ebd52b1 feat(adapter): govern Claude Code Write as create
```

## CI STATUS

**LATEST: SUCCESS on `45e3072`** — GitHub Actions run **36476641745**
(workflow `CI`, status `completed`, conclusion `success`, branch
`main`, headSha `45e3072e67feb027b1ae9ab10e89680811dddcfb`).
**4/4 jobs green:** pytest (ubuntu/windows) success, packaging-gate
(ubuntu/windows) success; failure = NONE (verified via `gh run view
36476641745`). Push covered exactly one commit: `45e3072` (QUICKSTART
`action=create` docs fix — F1 follow-up).

Also green (4/4): `9e133a2` (FREE roadmap/state sync) = run
36375363049; `cf638b1` (test isolation) = run 36371113909 — that push
covered `c48e786` + `cf638b1` (GitHub runs CI for the pushed HEAD).

Recent releases (also green, 4/4): `2222b07` = run 36234640245;
`45b2296` = run 36212828174; `508382b` = run 36099397583
(headSha verified 2026-09-25).

History (unchanged): hosted CI (Ubuntu+Windows pytest, packaging-gate
×2): SUCCESS on
`7525c66`, `2536af0`, `69f8d39`, `b061d03`, `7de6a55`, `3b8e259`,
`654bf56`, `ebd52b1`, `2e2bf55`, `003fe9b`, `a67069d`, `0a9bd45`, `738a158`, `2f842ac`, and `4302409`
(latest run 34642040793 — 4/4 jobs, propose-stale warning included);
plus run 35927652074 (4/4 GREEN) for `ecf00fd`.
**Known red:** run 35951091911 = FAILURE on `98da708`
(packaging-gate "Whitespace check" only — both pytest jobs green);
hygiene/process follow-up, not a product failure.

Latest local suites (recorded): site + i18n **89 passed / 0 failed**;
usage telemetry **26 (opt-out) + 43 (transport) passed / 0 failed**;
full suite **1762 passed / 15 skipped / 1 known-perf-flake**
(`usage_signal` cold-scan threshold, load-dependent; CI full suite is
authoritative and green on both OSes).

## RELEASE CHECKPOINT (LAST KNOWN GOOD)

- **`cf638b1bce6200f6f911ed8d0ff9aa8a5bf8f2a3`** —
  `test(usage): isolate CLI usage tests from real home`, pushed
  fast-forward, **hosted CI GREEN 4/4 (run 36371113909)**.
- Carries the telemetry work: `c48e786` (FAZ 2.1 opt-out/config +
  FAZ 2.2 `tanuq/usage_transport.py` + 2 new test modules) and
  `cf638b1` (test-isolation fix, +13). Site content: **unchanged since
  `e7c1174`** (`git diff e7c1174..cf638b1 -- site/` = empty).
- Core diff for this checkpoint: **`simulation/`, `p5/`,
  `agent_run.py`, `tanuq/usage_signal.py` = 0**; only
  `tanuq/{cli,config,usage_transport}.py` +3 tests are new.
- History (previous release checkpoints):
  - `2222b07` `feat(site): add English default and Turkish /tr public
    site` (7 files, +836/−137) — CI 4/4 (36234640245), deployed 2026-09-26.
  - `45b2296` `feat(site): finalize public TANUQ product experience`
    (7 files, +692/−75) — CI 4/4 (36212828174).
  - `508382b` `feat(site): polish public TANUQ experience`
    (4 files, +157/−10) — CI 4/4 (36099397583).

## PUBLIC SITE CHECKPOINT

- **CURRENT (last verified 2026-09-27): LIVE = `e7c1174`** — LAST-KNOWN
  CHECKPOINT, measured in the earlier 2026-09-27 session by blob identity
  (live `index.html` == `e7c1174:site/index.html`; live
  `tr/index.html` == `e7c1174:site/tr/index.html`; feedback mailto live
  EN=1 / TR=1). **NOT re-measured over the network during this
  roadmap-sync task — not a fresh confirmation.** Repo HEAD = `cf638b1`,
  and **site content is identical** (`git diff e7c1174..cf638b1 -- site/`
  = empty) — the telemetry commits (`ed1c6c5`, `c48e786`, `cf638b1`)
  are code/test-only — **no site redeploy pending** for them.
  **HISTORY — 2026-09-26 verification of the `2222b07` deploy:**
  - English `/`: HTTP 200, 24343 B, `Last-Modified: 26-Sep-2026
    10:28:21 GMT`, `<html lang="en">`.
  - Turkish `/tr/` (and `/tr/index.html`): HTTP 200, 25202 B,
    `<html lang="tr">`; EN↔TR language switch working both ways;
    `../`-relative assets resolve (`../style.css`, `../demo.js`,
    `data-fixture="../demo_fixtures.json"`).
  - **Byte-level identity:** live `index.html` git-blob
    `972e02112bdb7976fba3650a6c1e1e85e6429c26` ==
    `2222b07:site/index.html` (**EQUAL**); SHA-256
    `1bfe6f0714670e76545f86d06cd20449a8a8ff9a057c3b9f1b29eb2b1e38e4e2`;
    size 24343 B. Live TR index blob `1f9623e347c7f5a77ef86b7af1a9715ad3e9c2ec`
    == `2222b07:site/tr/index.html` (**EQUAL**).
    Release assets **7/7 EQUAL**: `index.html`, `tr/index.html`,
    `style.css`, `demo.js`, `demo_fixtures.json`, favicon, header logo.
  - Walkthrough on live (headless render): **STEP 1/8 · PROPOSAL**
    with real capture values (HIGH, fingerprint `06d0ba48d949…`,
    approval `864c6050`), **no error box**.
- **HISTORY (resolved):** through the morning of 2026-09-26, LIVE was
  the `508382b` build (blob `6d119622338ad48d0da5bacb122970d6ea2db315`,
  served since 25-Sep 07:28 GMT); before that the 22-Sep-2026 manual
  upload (byte-identical to `107d764`/`5504d36` blobs). **LIVE == old
  `508382b` → NO (verified)**; old build no longer served.
  Deploy path: agent-side upload was once BLOCKED (no hosting
  credentials/channel in the agent environment, document-root path
  unverifiable from outside) → **owner executed the manual upload**.
- Deploy mechanics (unchanged): no CI deploy (only `ci.yml`); hosting =
  Güzel Hosting (NS guzelhosting.com, A 104.247.168.115, PTR
  `115gtgwfg.guzel.net.tr`); manual upload; `style.css`
  `Cache-Control: max-age=604800` (7-day cache may serve stale CSS
  after future deploys — re-verify by hash after any deploy).
- Commercial truth on the live site (**FREE strategy**, `b5841f9` onward):
  **TANUQ is free to use** — no account / no payment / no subscription;
  pricing card = **FREE**; primary CTA = `START USING TANUQ` /
  `TANUQ'U KULLAN`; **`$49/month` and `START ACQUISITION` are SUPERSEDED**
  (removed from the site; earlier notes below recorded them only as
  history); "free forever" is NOT promised; future pricing =
  **UNKNOWN** (stated as not decided yet); feedback = `mailto:feedback@tanuq.net`;
  GitHub surface = 0; DEMO TALEP = 0; trajectory / multi-agent / anomaly
  research NOT presented as product capability; limits stated (not
  OS-level, not network enforcement, not sandbox).
- Out of release scope (unchanged): `site/assets/tanuq-logo-header.png`
  (untracked, referenced nowhere, never tracked).

## OPEN RISKS

1. `child_*.dmp` in repo root: REAL API tokens on disk (secret_guard
   findings) — must never be committed; cleanup pending human action.
2. Helper-module weakening is outside the G1 naming gate (medium
   residual).
3. Cross-assembly (p5/agent_run vs tanuq) workspace collision: no
   guard, no test (UNKNOWN).
4. Cross-process in-flight serialization absent (RAM-only guard;
   fail-closed compensations exist).
5. Windows child-hang root cause UNCONFIRMED — mitigation in place;
   no speculative fixes.

## UNKNOWN / UNCONFIRMED

- Hosted CI for the uncommitted FAZ 6-lite A tree.
- Cross-process simultaneous resume window behavior.
- Whether any operator workflow points p5/agent_run at a tanuq
  workspace (collision preconditions).
- Exact Windows child-hang native mechanism.

## DO NOT DO

- Do not add operation_id or reopen FAZ 2 without the freeze condition.
- Do not touch `simulation/` security files or `WorkerActionPipeline`
  semantics without an explicit human-approved task.
- Do not commit `child_*.dmp`, `_dbg_*`, `_diag*`, `_run_obs.py`,
  `_verify_postfix*.py`, `dist/`, `t`, `request.json`.
- Do not treat VERIFIED as APPROVED or as a governance decision.
- Do not introduce Kafka/Redis/RabbitMQ/daemon/second database.
- Do not rewrite Governance Core / approval / fingerprint /
  journal semantics.

## CURRENT WORKING MODEL

- NORMAL CODING TASK: bounded single task — goal + limits + invariants
  → implement → test → drift check → report. Small review folded in.
- MECHANICAL GIT/CI: full delegation (stage → validate → commit →
  push → CI → report) — proven safe.
- ARCHITECTURAL/SECURITY DECISION: separate analysis task → evidence →
  options → HUMAN GATE → decision recorded (here or in the canonical
  doc) → only then implementation.
- CONTEXT LOSS: run a re-sync (SESSION RESYNC format below) — but only
  on session breaks, conflicting instructions, or unexpected repo
  state; not every task.
- EVIDENCE BEFORE PHASES: no phase starts on assumption; MEVCUT DURUM
  → KANIT → GEREKSİNİM → TASARIM → IMPLEMENTASYON → TEST → CHECKPOINT.

- EVIDENCE BEFORE PHASES: no phase starts on assumption; MEVCUT DURUM
  → KANIT → GEREKSİNİM → TASARIM → IMPLEMENTASYON → TEST → CHECKPOINT.

## OPERATOR DECISION — PRODUCTIZATION-FIRST WORKING MODEL (2026-09-10, FROZEN PRINCIPLE)

> **KARAR KAYDI (operatör):** Bundan sonra öncelik "mükemmel mimariyi
> sürekli genişletmek" değil, **çalışan çekirdeği gerçek ürün
> kullanımına mümkün olduğunca hızlı taşımaktır**. Bu karar güvenlik ve
> mimari prensipleri DEĞİŞTİRMEZ; yalnızca geliştirme önceliklendirme
> ve çalışma yöntemini tanımlar. Anayasa (yukarıdaki INVARIANTS)
> aynen geçerlidir.

1. **RESYNC** — her yeni oturumda önce PROJECT STATE, roadmap, git
   durumu ve son checkpoint okunur.
2. **CURRENT PRODUCT BLOCKER** — ürünleşmenin önündeki EN ÖNEMLİ gerçek
   engel önce belirlenir (varsayım değil, kanıt).
3. **TEK ÖNCELİKLİ GÖREV** — birden fazla speculative iş yerine, ürün
   değerini en fazla artıran TEK uygulanabilir görev seçilir.
4. **IMPLEMENT → TEST → DOGFOOD** — değişiklik varsa sırayla:
   implementasyon → gerçek test → mümkünse gerçek/dogfooding kullanım
   senaryosu.
5. **PRODUCT CHECK** — görev sonu sorusu yalnızca "testler geçti mi?"
   değil; "bu değişiklik TANUQ'u gerçek kullanıcı için daha hazır hale
   getirdi mi?" olur.
6. **EVIDENCE FIRST** — yeni faz/abstraction yalnızca gerçek ihtiyaç ve
   kanıt ortaya çıktığında açılır; UNKNOWN / INFERRED / CONFIRMED
   ayrımı korunur.
7. **ARCHITECTURAL DISCIPLINE** — anayasa korunur: Governance Core =
   AUTHORITY, Coordinator = COORDINATION, Evidence = EVIDENCE, Human =
   AUTHORIZATION, Agent/LLM = UNTRUSTED PROPOSER, Pipeline = MUTATION.
8. **AVOID SPECULATIVE WORK** — kanıtlanmamış ihtiyaçlar için yeni
   infrastructure, gereksiz abstraction, büyük refactor, yeni state,
   yeni identity mekanizması OLUŞTURULMAZ.
9. **SESSION-END CHECKPOINT** — her anlamlı görev sonunda DAILY HANDOFF
   güncellenir: ne yapıldı, dosyalar, commit/CI, test sonuçları,
   kararlar, kalan riskler, UNKNOWN/UNCONFIRMED, NEXT VALID ACTION,
   HUMAN GATE.
10. **NEXT-DAY CONTINUITY** — bilgisayar kapandıktan sonra ertesi gün
    insan ve GLM "nerede kaldık, neden oradayız, sıradaki iş ne?"
    sorularını konuşma geçmişine ihtiyaç duymadan yanıtlamalı.

**ANA YÖNETİM İLKESİ:** Önce çalışan TANUQ → sonra gerçek kullanım →
sonra ölçüm/kanıt → sonra büyütme.

## VISION

TANUQ: an event-sourced, deterministic, human-governed file-editing
agent runtime — "AI works. You stay in control." Every AI-proposed
change flows through deterministic governance, single-use human
authorization when risky, atomic apply, real verification, automatic
rollback and tamper-evident evidence. The orchestration roadmap
(FAZ 1-10) adds coordination, lifecycle, unified runtime, wait/resume,
concurrency, recovery and multi-patch ON TOP of that core — never
replacing it. End state per the roadmap: one governed entry surface
(runtime → coordinator → governance core → pipeline), with the agent
permanently an untrusted proposer and the human the only authorizer.
(Vision sources: README, docs/PRODUCT_VISION.md, ORCHESTRATION
docs, this session's decisions. Anything beyond this: NEEDS OPERATOR
CONFIRMATION.)

## DAILY HANDOFF

### 2026-09-27 (FREE strategy → feedback channel → usage telemetry FAZ 1/2.1/2.2 → F0 close → roadmap sync)

- SESSION OBJECTIVE: switch TANUQ to FREE distribution, wire a real
  feedback channel, build the usage-signal/telemetry stack (local +
  opt-out + transport), close the F0 release gate, then sync this file.
- WORK COMPLETED (chronological, all pushed):
  1. **FREE strategy live** — `b5841f9` `feat(site): launch TANUQ free
     distribution strategy`: pricing card = FREE, CTAs →
     `START USING TANUQ` / `TANUQ'U KULLAN`, `$49 / month` + demo/purchase
     copy removed, tests relocked; CI SUCCESS.
  2. **Feedback prompts** — `7d7ee8a` (5 short signals, EN+TR; honest
     "no form/no channel yet" state; GitHub=0 preserved).
  3. **Real feedback channel** — `e7c1174` `mailto:feedback@tanuq.net`
     (owner-created mail account), exact-encoded subject/body (EN
     `TANUQ Feedback` / TR `TANUQ Geri Bildirim`, 5 prompts, UTF-8 safe),
     old "no channel" copy removed; tests 91 green. **Owner deployed →
     LIVE verified: mailto EN=1 / TR=1, blob == `e7c1174`.**
  4. **FAZ 1 local usage signal** — `ed1c6c5` (NEW `tanuq/usage_signal.py`
     570 satır + 14 tests): 12 event şeması, HMAC install_id, run_id
     UUID4, fail-silent, privacy deny-list; full suite **1694/15/0**.
  5. **FAZ 2.1 opt-out/config** + **FAZ 2.2 remote transport** — `c48e786`
     (5 files: config/cli + `tanuq/usage_transport.py` + 2 test modules;
     26 + 43 tests): ENV>config>default ON, HTTPS-only, allow-list,
     1KB/64/32KB limits, no retry, fail-silent, OFF guard, zero network
     in tests; **real endpoint/backend = YOK (FAZ 2.3 not started)**.
  6. **Test isolation fix** — `cf638b1` (CLI usage tests → isolated HOME);
     **CI run 36371113909 = SUCCESS 4/4** (pytest + packaging-gate ×2 OS).
  7. **F0 Release Gate = CLOSED/PASS** (read-only audit: scope 5/5,
     governance core CLEAN, distribution audit: package 0.6.0, PyPI YOK,
     LICENSE file YOK, publish workflow YOK).
  8. **This task:** roadmap/project-state sync (FREE PRODUCT ROADMAP block,
     superseded commercial notes, historical banners on stale roadmap docs).
- COMMERCIAL STATE: FREE strategy ACTIVE — no account / no payment /
  no subscription; **`$19 one-time` = SUPERSEDED, `$49/month` +
  `START ACQUISITION` = SUPERSEDED** (removed from site); "free forever"
  NOT promised; future pricing **UNKNOWN**; WTP/first-user/conversion
  **UNKNOWN**; commercial signal ≠ WTP; feedback = `mailto:feedback@tanuq.net`
  (live).
- TESTS: site+i18n **89**, opt-out **26**, transport **43** (all 0 failed);
  full suite recorded **1762/15/1** (1 = load-dependent perf threshold in
  FAZ 1 usage_signal; CI full suite authoritative GREEN on both OSes).
- FREEZE: `simulation/`, `p5/`, `agent_run.py`, governance primitives,
  `usage_signal.py` semantics = **0 change** across the whole day (diff empty);
  only tanuq/{cli,config,usage_transport}.py added/extended (product layer).
- NEXT ACTION: **F1 — FREE E2E Local Validation** (fresh clone → install →
  governed run → verify/evidence).
- NEXT HUMAN GATE: F2 decisions (LICENSE file, package naming, PyPI),
  FAZ 2.3 real endpoint/backend, and — only if site copy changes again —
  deploy scheduling (site content currently live == HEAD).

### 2026-09-26 (public site: finalize → i18n release → CI → owner deploy → LIVE VERIFIED → state sync)

- SESSION OBJECTIVE: move the public site from "release candidate" to
  "released + live", then align this state file with verified reality.
- WORK COMPLETED (chronological):
  1. **Finalize release committed + pushed** — `45b2296`
     `feat(site): finalize public TANUQ product experience` (7 files,
     +692/−75: GitHub fully removed from the public site incl. clone
     commands, commercial-truth copy, nav separation, silent demo
     fallback). Pre-push safety fast-forward `508382b..45b2296`;
     **CI run 36212828174 = success 4/4**.
  2. **Comprehensive Reality Map** (read-only audit): governance chain
     traced in code (fingerprint = SHA-256 over
     `{path,action,reason,old_content,new_content,allowed_paths}`);
     single mutation writer = `FileApplier` (one instantiation,
     `apply_executor.py:62`); observer ≠ authority confirmed by import
     scan; advisory LLM risk raise-only (`max_level`); docs staleness
     list recorded; tests: 1693 collected, security 337/6 skipped
     locally, CI full suite authoritative.
  3. **Global English + Turkish `/tr` release candidate** —
     `site/index.html` becomes EN default (`lang=en`), Turkish
     preserved at `site/tr/index.html` (`lang=tr`, `../` assets),
     language switch both ways; site tests updated + new
     `tests/site_i18n_test.py`; validation: **89 passed / 0 failed /
     0 skipped**, public scans (GitHub/claims/demo-errors) = 0,
     viewports 390/768/1280/1440 overflow = 0 (EN+TR).
  4. **Final release check (read-only)** — release set = 7 files,
     all anchor/asset/path checks OK, user-reported garbled strings
     ("AAjan/RRisk/EUygulamak") **not present in source** (copy-paste
     artifact of chain icon+label spans) → no code change needed.
  5. **Commit + push (PM/owner-approved)** — `2222b07`
     `feat(site): add English default and Turkish /tr public site`
     (exactly 7 files, +836/−137; state-doc/artifacts excluded) →
     `45b2296..2222b07` fast-forward; **HEAD == origin/main**.
  6. **CI verified** — run **36234640245 = success 4/4** (pytest
     ubuntu 234s / windows 441s, packaging-gate ubuntu 23s / windows
     51s; failure NONE).
  7. **Deploy** — agent-side deploy **BLOCKED** (no hosting
     credentials/channel; document root unverifiable) and reported
     with a ready upload manifest; **owner executed the manual upload**
     to Güzel Hosting.
  8. **LIVE VERIFIED (post-deploy, read-only)** — `/` EN 200 (24343 B),
     `/tr/` 200 (25202 B), static 5/5 blob-EQUAL to release, live
     index blob `972e02112b…` == `2222b07:site/index.html`
     (**LIVE == old `508382b` → NO**), walkthrough STEP 1/8 with real
     values and no error box, claims/pricing/limits live and honest
     (GitHub surface 0, DEMO TALEP 0, no future-feature claims).
- TEST RESULTS: site+i18n suite **89 passed / 0 failed / 0 skipped**
  (pre-commit); CI full suite green at HEAD.
- PUBLIC SITE: **LIVE == RELEASE == `2222b07` — DEPLOY PASS / LIVE
  VERIFIED** (details in PUBLIC SITE CHECKPOINT).
- COMMERCIAL STATUS (unchanged, not validated): launch pricing
  hypothesis `$49/month`; payment/licensing NOT YET LIVE; WTP, first
  external user, acquisition conversion = **UNKNOWN**.
- FREEZE STATUS: unchanged — `tanuq/`, `simulation/`, `p5/`,
  `agent_run.py` diff = 0 across both commits; core freeze verified
  before every commit.
- NEXT ACTION: **commercial validation / acquisition validation**
  (single next task) — first external users → install feedback →
  10-user/WTP signal → commercial decision.
- NEXT HUMAN GATE: commercial decisions (payment/licensing build,
  pricing confirmation) — all still UNKNOWN, none recorded as done.

### 2026-09-25 (site release → cleanup → chain fix → push → artifact audit → state sync)

- SESSION OBJECTIVE: land the public-site release package, remove
  public GitHub visibility, fix the Authority Chain icon/label
  gluing, then record the truth as a checkpoint.
- WORK COMPLETED (chronological):
  1. **Release package committed** — `5d90ff9`
     `feat(site): add interactive TANUQ demo experience` (11 files:
     4 logo/favicon assets, `demo.js`, `demo_fixtures.json`,
     `index.html`, `style.css`, 3 test modules; +1884/−423). Staged
     scope verified (no `tanuq/`, `simulation/`, `p5/`,
     `docs/research/`, `site/try/`, no debug artifacts).
  2. **GitHub visibility cleanup** — footer
     `<a href="https://github.com/…">GitHub</a>` removed from
     `site/index.html` (LOCAL TRY `git clone` command text kept on
     purpose); public-surface tests inverted
     (`test_footer_has_no_github_link`, `test_no_visible_github_link_anywhere`);
     HTTP smoke 200 + "NO GITHUB ANCHOR".
  3. **Authority Chain visual fix** — root cause CONFIRMED by
     simulation: icon↔label separation relied solely on flexbox
     `gap:6px` (`icon margin:0`), so gap-less engines rendered the
     icon letter flush against the label ("AAgent/RRisk/PPolicy";
     sim: touch=true on 9/9 nodes at 390/768/1280). Fix = explicit
     `margin: 0 0 6px` on `.chain-icon`/`.chain-name` + `gap`
     removed from `.chain-node` (style.css, 4 lines). Verified via
     Chrome CDP emulation: 390/768/1280 → v_gap=6, touch=0, 9
     labels exact, no overflow; before/after screenshots
     byte-identical (SHA256 equal) → zero visual regression. New
     test module `tests/site_authority_chain_test.py` (5 tests, G1
     ✔ new module).
  4. **Commit + push (owner-approved)** — `508382b`
     `feat(site): polish public TANUQ experience`, exactly 4 files
     (+157/−10); pre-push safety (local ahead 2, remote ahead 0,
     fast-forward) → `98da708..508382b`; **HEAD == origin/main**.
  5. **Exact release artifact audit (read-only)** — `site/` @508382b
     = 11 tracked files; all 6 runtime-referenced assets tracked and
     present (worktree diff empty); `tanuq-logo-header.png`
     untracked/referenced-nowhere/never-tracked → deploy-not-needed.
- CI: GitHub Actions run **36099397583 — `CI` → SUCCESS** for
  `508382b` (4-job workflow; verified via `gh run view`).
- TEST RESULTS: site-scope suite **55 passed / 0 failed** (re-run
  before the commit).
- PUBLIC SITE: live tanuq.net still serves the 22-Sep-2026 manual
  upload (= repo blobs at `107d764`/`5504d36`), NOT `508382b` —
  **deploy not performed** (no CI deploy path; manual upload on
  Güzel Hosting required).
- WORKING TREE: tracked clean; untracked (`.venv-validation/`,
  12 × `docs/research/*`, `site/assets/tanuq-logo-header.png`)
  intentionally left untouched (release scope = `site/` tree only).
- FREEZE STATUS: unchanged — `tanuq/`, `simulation/`, `p5/` diffs =
  0 across both commits; no core/security/fingerprint/approval
  semantics touched.
- NEXT ACTION: resume Sol/Codex review on the 508382b artifact
  manifest (single next task), then owner-gated deploy.
- NEXT HUMAN GATE: deploy approval (tanuq.net); header.png
  keep/ignore/delete decision; freeze reopen condition still NOT met.

### 2026-09-24

- RELEASE: commit `ecf00fd33f80f5b5c89eb590eb27bf6a01b3e9f3`
  ("Harden approval TTL and pending API auth") pushed; **origin/main ==
  HEAD == ecf00fd** (fast-forward from f0d09b6). Scoped commit set:
  tanuq/agent_adapter.py (Q1), tanuq/web.py (A4),
  tests/approval_ttl_contract_test.py (NEW),
  tests/web_api_get_auth_test.py (NEW), docs/TANUQ_PROJECT_STATE.md,
  3 × docs/research/*consolidation_01.md.
- CI: GitHub run **35927652074 — 4/4 GREEN**: pytest (ubuntu-latest)
  PASS, pytest (windows-latest) PASS, packaging-gate (ubuntu-latest)
  PASS, packaging-gate (windows-latest) PASS. (Annotations: actions
  Node 20 deprecation + ubuntu-latest image migration notices —
  informational only.)
- Q1: Approval TTL **FIXED + VERIFIED + PUSHED** —
  `APPROVAL_TTL_SECONDS=3600` now bound at grant time
  (`expires_at` persisted, validated at find_valid/authorize_apply,
  durable across restart); regression PASS.
- A4: Sensitive API GET authentication **FIXED + VERIFIED + PUSHED** —
  tokenless `GET /api/pending` → **403** (fail-closed); valid token →
  200; `/api/health` + static shell stay public; regression PASS.
- FINAL AUTHORITY-SURFACE DISPOSITION (unchanged; research records in
  docs/research/sol_a1_a4_q1_q2_authority_surface_consolidation_01.md):
  - A1 CLI self-approval: **DEPLOYMENT-DEPENDENT / ACCEPTED CURRENT
    MODEL** (mechanism real; not a core governance gap in the
    single-user/local model).
  - A2 export --out: **ACCEPTED OPERATOR BEHAVIOR** (read-only over
    governance state; --out is documented external-audit artifact
    write).
  - A3 init --force --yes: **ACCEPTED OPERATOR BEHAVIOR** (documented
    re-init scope reconfiguration; workspace-root ceiling enforced by
    Tighten-only validation at save+load). Optional Option-2 hardening
    (force+omit keeps current scope) = **OWNER CHOICE**.
  - Q2 verifier: **RESIDUAL TRUST BOUNDARY / ACCEPTED** (no
    unauthorized agent mutation path; pre-existing/approved test code
    runs with operator privileges — no OS sandbox).
- SECURITY VALIDATION (final pre-commit audit): scoped regression
  **573 passed / 3 skipped / 0 failed**; security invariants all PASS
  (fingerprint binding, single-use, bounded attempts, risk
  recomputation, UNKNOWN→DENY, HIGH/CRITICAL→approval, advisory
  cannot lower, apply authorization, evidence chain, reconciliation,
  Q1 expiry, A4 token requirement); **simulation/ diff = 0**; no
  unexpected production-core changes (tanuq/ diff = Q1 + A4 only).
- GIT HYGIENE: scoped release files committed (above). Scoped-out
  changes remain **uncommitted and preserved**: site/index.html,
  site/style.css, tests/site_next_step_test.py,
  tests/test_public_surface.py (separate prior work stream); root
  luna-*/sol-* artifacts (luna-*, luna0*, sol-01/02*) and other
  untracked research artifacts (observer packages, site/assets/)
  remain outside the release commit. The working tree is NOT clean.
- OPEN OWNER ITEMS: (1) root luna-*/sol-* artifact hygiene — cleanup
  decision pending; (2) A1/A2/A3/Q2 optional hardening decisions
  remain owner-choice/deployment decisions — **no immediate
  production blocker**; these are NOT unresolved core security
  vulnerabilities and must not be represented as such; (3) standing
  NEXT VALID ACTION items (real Claude Write runtime dogfood — credit
  gate).
- FREEZE STATUS: unchanged. Core governance chain re-validated across
  LUNA-07..12 + Sol review: no core authority bypass found.
- NEXT ACTION: owner artifact-hygiene decision; CI already GREEN for
  the release; then standing items.
- NEXT HUMAN GATE: artifact cleanup approval; operator-surface
  hardening choices; freeze reopen condition still NOT met.

### 2026-09-23 (continuation 2 — Sol adversarial review consolidation)

- SESSION OBJECTIVE: consolidate the GPT-6 Sol adversarial review
  (A1-A4/Q1-Q2) with the independent GLM source audit + live
  disposable verification into tracked research records. Research
  scope ONLY.
- WORK COMPLETED: added
  `docs/research/sol_a1_a4_q1_q2_authority_surface_consolidation_01.md`.
  Every finding was re-verified against real source and reproduced
  LIVE in a disposable scratch workspace (production repo untouched):
  A1 CLI self-approval (mechanism real, `authorizer="human-operator"`
  is a static string — DEPLOYMENT-DEPENDENT, not a core governance
  gap in the single-user/local model); A2 `export --out` writes
  outside scope (live: directory+file created outside the workspace);
  A3 `init --force --yes` widens a narrowed scope back to the whole
  workspace (live: config before/after); A4 `GET /api/pending`
  returns proposal diff content without any token (live: HTTP 200
  with `new_preview`, localhost-bound); Q1 advertised 3600s approval
  TTL is NOT enforced (live: ledger grant `expires_at=''`) —
  fingerprint binding + single-use remain real; Q2 verifier residual
  (pre-existing test code runs at verification; RT-2/R1/G1
  mitigations intact — not an agent bypass).
- KEY DISTINCTION RECORDED: no core authority bypass in the
  proposal→risk→approval→apply→verification→evidence chain
  (consistent with LUNA-07..12); the confirmed items live on the
  SEPARATE operator surface (CLI/local API/operator commands).
  Classification: A2/A3/A4 = confirmed operator-surface hardening;
  Q1 = confirmed defense-in-depth hardening; Q2 = PARTIAL residual
  verifier trust boundary.
- FILES CHANGED:
  docs/research/sol_a1_a4_q1_q2_authority_surface_consolidation_01.md
  (NEW), docs/TANUQ_PROJECT_STATE.md (this entry).
- FREEZE STATUS: unchanged. **NO PRODUCTION CODE CHANGE** (tanuq/,
  simulation/, tests/ diff = 0). Production fixes NOT applied — six
  owner decisions pending (TTL enforcement, /api/pending GET auth,
  export --out scope-binding, init --force confirmation, CLI approval
  identity, verifier sandbox) — listed in the consolidation record §8.
- NEXT ACTION: owner decisions on the operator-surface hardening
  items; root `luna-*` artifact cleanup still deferred.
- NEXT HUMAN GATE: operator-surface hardening decisions; freeze reopen
  condition still NOT met.

### 2026-09-23 (continuation — LUNA research consolidation V2)

- SESSION OBJECTIVE: convert the remaining conversation-derived LUNA
  research verdicts into tracked records; no production scope.
- WORK COMPLETED: added
  `docs/research/luna_governance_consolidation_01.md` — LUNA-07
  (approval fingerprint binding / single-use: FALSIFIED as a security
  gap; binding demonstrable from tracked source: fingerprint schema,
  ApprovalStore single-use + ledger durability, apply-boundary
  fingerprint compare, per-fingerprint in-flight key) and LUNA-10
  (governance-input manipulation: FALSIFIED as a security gap;
  authoritative state confined to GovernanceEvaluator/RiskEngine/
  RiskPolicy/fingerprint/ApprovalStore/apply/verification — both
  historical verdicts labeled conversation-derived, corroborated by
  tracked tests). Root artifact hygiene audit COMPLETED (read-only):
  root `luna-*` files classified (raw proposer outputs = MOVE
  candidates; `luna0*-packet.txt` = reproducible repo-source
  snapshots = DELETE-CANDIDATES; no real secrets found).
- DECISIONS RECORDED: LUNA-E2E-05 PASS; LUNA-E2E-06 PASS; E5
  Reconciliation V1 E2E-validated; LUNA-08 security gap NOT confirmed
  (evidence/UX hardening only — history CLI does not expose content;
  evidenced_sha256 ↔ disk_sha256 reconciliation exists); LUNA-09
  production change not required (kept); LUNA-07 security hypothesis
  falsified; LUNA-10 security hypothesis falsified. Production core
  unchanged. Root `luna-*` cleanup intentionally DEFERRED pending
  owner approval (no delete/move/rename, no .gitignore change).
- FILES CHANGED: docs/research/luna_governance_consolidation_01.md
  (NEW), docs/research/luna_e2e_05_06_consolidation_01.md (from the
  first consolidation pass, unchanged this pass),
  docs/TANUQ_PROJECT_STATE.md (this entry).
- FREEZE STATUS: unchanged. Production diff (simulation/, tanuq/) = 0.
- NEXT ACTION: owner-approved root artifact cleanup (separate task);
  then the standing NEXT VALID ACTION items.
- NEXT HUMAN GATE: root artifact cleanup approval; freeze reopen
  condition still NOT met.

### 2026-09-23

- SESSION OBJECTIVE: LUNA research consolidation — permanent, auditable
  records for LUNA-E2E-05/06; E5 Reconciliation V1 E2E validation;
  LUNA-08/09 re-evaluation. Research-record scope ONLY.
- WORK COMPLETED: added
  `docs/research/luna_e2e_05_06_consolidation_01.md` — third
  independent untrusted proposer (Luna) drove the canonical
  `--stdin-json` chain end-to-end (fingerprint
  `fda806fa…ef33e`, risk LOW, no approval, terminal VERIFIED, chain
  VALID 52 events, anchor ACTIVE, ledger VALID); controlled
  out-of-channel mutation observed live as CONTENT_MISMATCH
  (evidenced_sha256 `f852d77f…` vs disk_sha256 `f56120cd…`) and
  restore returned MATCH — E5 Reconciliation V1 E2E-validated
  (observation-only semantics confirmed; MATCH/CONTENT_MISMATCH are
  NOT security/enforcement statements).
- DECISIONS RECORDED: LUNA-E2E-05 = PASS; LUNA-E2E-06 = PASS; E5
  Reconciliation V1 = validated by real E2E; LUNA-08 "actual
  applied-content fingerprint" suspicion NOT confirmed as a security
  gap — retained as evidence/observability hardening topic (the
  architecture already reconciles evidenced_sha256 ↔ disk_sha256);
  LUNA-09 "no production change required" kept. No production
  governance/evidence/reconciliation code touched.
- FILES CHANGED: docs/research/luna_e2e_05_06_consolidation_01.md
  (NEW), docs/TANUQ_PROJECT_STATE.md (this entry). Untracked raw
  artifacts (luna-e2e-*.txt/json, luna0*-packet.txt) pending owner
  hygiene decision — do not commit without review.
- FREEZE STATUS: unchanged. Core diff = 0.
- NEXT ACTION: owner hygiene decision on root luna-* artifacts; then
  the standing NEXT VALID ACTION items (real Claude Write runtime
  dogfood — credit gate).
- NEXT HUMAN GATE: none new; freeze reopen condition still NOT met.

### 2026-09-16

- SESSION OBJECTIVE: fix the confirmed `tanuq lineage --fingerprint`
  CLI crash found during real dogfood (audit-commands friction).
- WORK COMPLETED: one-line CLI fix — cmd_lineage passed `env` both
  positionally (binding to `fingerprint`) and as a keyword argument
  to OperationCoordinator.lineage() →
  TypeError: got multiple values for argument 'fingerprint'.
  Read-only view-layer fix only; coordinator/lineage semantics
  untouched (single call site, diff-verified).
- FILES CHANGED: tanuq/cli.py (1 line),
  tests/lineage_cli_test.py (NEW, 3 tests; no existing test module
  touched — G1 ✔).
- TEST RESULTS: 3 new lineage-CLI tests passed; coordinator +
  status_json regression 16 passed; full suite 1485 passed /
  15 skipped / 0 failed. Real CLI dogfood: `lineage --fingerprint
  abc` no longer crashes (human + --json paths).
- INCIDENT: first commit attempt (2698ac9) accidentally truncated
  docs/TANUQ_PROJECT_STATE.md to 25 lines (PowerShell -TotalCount
  pipe); this commit restores the full file and re-applies the
  intended updates. CLI + test changes in 2698ac9 were correct.
- FREEZE STATUS: unchanged.
- NEXT ACTION: real Claude Write runtime dogfood (BLOCKED on
  operator subscription/credit — capture harness ready); operator
  items: child_*.dmp cleanup decision.
- NEXT HUMAN GATE: none new; freeze reopen condition still NOT met.

### 2026-09-11

- SESSION OBJECTIVE: finalize the NEW-FILE CREATE product blocker —
  implementation → audit → release (commit + push + CI).
- WORK COMPLETED: governed `create` action through the existing chain
  (adapter whitelist + old_content="" convention; validator create
  branch — target-must-not-exist / parent-must-exist / no dir
  creation; applier create apply (atomic, read-back, apply-time
  re-check) + create rollback (delete ONLY if content still matches
  approved new_content, else fail-closed ROLLBACK_FAILED);
  controller.py single action-gate line (CONFIRMED REQUIRED — the
  only modify assumption in the controller layer)). NO new identity,
  authority or abstraction; fingerprint/ApprovalStore/RiskEngine/
  PathPolicy/verification untouched (diff-verified).
- FILES CHANGED (all committed in 654bf56): tanuq/agent_adapter.py,
  simulation/agent/worker/patch_validator.py,
  simulation/agent/apply/file_applier.py,
  simulation/agent/controller/controller.py,
  tests/create_action_test.py (NEW, 29 tests; no existing test
  module touched — G1 ✔).
- COMMITS: 654bf56 (pushed; HEAD == origin/main).
- TEST RESULTS: 29 create tests passed; targeted regression 174-251
  passed across sessions; full suite 1438 passed / 15 skipped /
  0 failed (re-run twice locally).
- CI RESULTS: SUCCESS for 654bf56 (run 34565021168 — 4/4 jobs).
- SECURITY VALIDATION: approval-less/consumed/expired/wrong-fp
  create → DENY; overwrite-via-create, traversal, out-of-scope →
  DENY; propose/apply race → stale fail-closed; modified-content
  rollback → fail-closed no-delete; R1 preserved (created test
  module never verifies itself → dummy floor).
- DOGFOOD (real CLI subprocesses, scratch workspaces, twice):
  propose→APPROVAL_REQUIRED(HIGH)→approve(single-use TTL)→execute→
  VERIFIED→file created byte-exact→evidence tamper-evident VALID;
  negative: out-of-scope create DENIED and not persisted. PASS.
- DECISIONS MADE: create uses old_content="" (canonical marker) —
  no fingerprint schema change; create is HIGH → always human
  approval (existing RiskEngine behavior reused); directory
  creation authority NOT granted; bundle identity NOT added.
- FREEZE STATUS: unchanged.
- REMAINING RISKS: child_*.dmp secrets (operator); helper-module G1
  gap; cross-assembly collision UNKNOWN; cross-process resume
  window UNKNOWN.
- NEXT ACTION: Claude Code vendor adapter Write-tool support
  (design-gate first; `_SUPPORTED_TOOLS` is Edit-only — code-
  CONFIRMED vendor-path flow-stopper); hygiene commits (state file
  + LIFECYCLE_DESIGN); child_*.dmp cleanup (operator).
- NEXT HUMAN GATE: vendor Write-tool task approval; hygiene commit
  approval; freeze reopen condition still NOT met.
- HANDOFF: next session = read this file → verify HEAD == origin/main
  → expect HEAD at or after 654bf56 → then vendor Write-tool design
  gate or dogfood evidence session.

- SESSION CONTINUATION (same day) — CLAUDE WRITE TOOL + VENDOR
  NEUTRALITY:
- WORK COMPLETED: Claude Code Write tool translated to the governed
  create action (translation layer only; `_SUPPORTED_TOOLS` += Write
  per the OFFICIAL vendor contract: tool_input {file_path, content};
  action="create", old_content=""; Write existing file → fail-closed
  DENY; correlation tool-aware, ambiguous→fail-closed); matcher
  documented as "Edit|Write"; AGENT_INTEGRATION.md contract updated.
  Read-only vendor-neutrality audit: canonical chain vendor-blind
  (rg scan — zero vendor refs outside secret-redaction regex);
  generic normalizer NOT REQUIRED.
- FILES CHANGED (all committed in ebd52b1): tanuq/claude_code_adapter.py,
  docs/AGENT_INTEGRATION.md, tests/claude_write_tool_test.py (NEW,
  19 tests; G1 ✔ — existing adapter test module untouched).
- COMMITS: ebd52b1 (pushed; HEAD == origin/main).
- PAYLOAD EVIDENCE BASIS: vendor-documented contract
  (code.claude.com/docs/en/hooks — tools reference), NOT yet runtime-
  observed; fixtures labeled accordingly; parser fail-closed on any
  deviation.
- TEST RESULTS: 19 Write tests + 30 adapter tests + targeted 254 +
  full suite 1457 passed / 15 skipped / 0 failed.
- CI RESULTS: SUCCESS for ebd52b1 (run 34589680409 — 4/4 jobs).
- REAL VENDOR DOGFOOD: BLOCKED — Claude API "Credit balance is too
  low" (CLI 2.1.215, auth OK); capture harness proven mechanically
  (scratch ws + stdin-capture hook + venv interpreter).
- NEXT ACTION: real Write runtime dogfood (credit gate); hygiene
  commits (state file + LIFECYCLE_DESIGN); child_*.dmp cleanup.
- NEXT HUMAN GATE: API credit; hygiene commit approval; freeze reopen
  condition still NOT met.
- HANDOFF: next session = read this file → verify HEAD == origin/main
  → expect HEAD at or after ebd52b1 → then real Write runtime
  dogfood (credit) or hygiene.

- SESSION CONTINUATION (same day) — PRODUCTIZATION PHASES 1-4 +
  CROSS-MODEL DOGFOOD + SKILL RELEASE:
- WORK COMPLETED: stale-patch DENY UX fix (real validator reason in
  guidance + history denied_reason; 2e2bf55, CI GREEN 34599646364);
  AGENTS.md + docs/TANUQ_SKILL.md (a67069d); version metadata fix
  (0a9bd45, CI GREEN 34610594860); productization Phases 1-4
  (fresh-install proof, fresh-clone governed cycle + README demo
  OVERALL PASS, version consistency, early-adopter readiness audit);
  cross-model real dogfood — GLM as an independent non-Claude
  proposal source drove modify+create+approval+DENY+evidence through
  the generic `--stdin-json` channel (SECOND INDEPENDENT MODEL
  SOURCE — CONFIRMED); hygiene audit (no .gitignore gaps for dist/,
  dmp, debug scripts — fixed this checkpoint).
- FILES CHANGED (this checkpoint): .gitignore (hygiene patterns:
  dist/, child_*.dmp, _dbg_*, _diag*, _run_obs*, _verify_postfix*,
  request.json, t), docs/TANUQ_PROJECT_STATE.md. Already committed:
  tanuq/agent_adapter.py, tanuq/cli.py, tests/stale_patch_ux_test.py
  (2e2bf55), tanuq/__init__.py, tests/version_metadata_test.py
  (0a9bd45), AGENTS.md + docs/TANUQ_SKILL.md (a67069d).
- COMMITS: 2e2bf55, 003fe9b, a67069d, 0a9bd45 (all pushed, CI GREEN).
- TEST RESULTS: full suite 1464 passed / 15 skipped / 0 failed;
  version tests 3; stale-patch UX tests 4.
- CI RESULTS: SUCCESS for 2e2bf55 (34599646364), 003fe9b
  (34593048285), a67069d+0a9bd45 (34610594860) — all 4/4.
- FRICTION MAP (real CLI dogfood): stale old_content byte-match +
  misleading guidance — FIXED (2e2bf55); init non-interactive via
  --yes (documented); remaining friction low.
- FREEZE STATUS: unchanged.
- NEXT ACTION: real Write runtime dogfood (credit gate); operator
  items — child_*.dmp quarantine, ORCHESTRATION_LIFECYCLE_DESIGN
  commit decision.
- NEXT HUMAN GATE: API credit; hygiene file decisions; freeze reopen
  condition still NOT met.
- HANDOFF: next session = read this file → verify HEAD == origin/main
  → expect HEAD at or after this checkpoint → then real Write runtime
  dogfood (credit) or hygiene decisions.

- SESSION CONTINUATION (same day) — QUICKSTART UX +
  INTERPRETER NOTE + PROPOSE-STALE WARNING:
- WORK COMPLETED: QUICKSTART create example shows the approval step
  before execute (738a158); AGENT_INTEGRATION.md hook interpreter
  note (2f842ac); propose-time stale old_content warning — read-only
  UX, fingerprint-external, execute-time stale DENY unchanged
  (4302409); first real product task executed through TANUQ itself
  (repo workspace self-hosted: propose LOW —> execute VERIFIED
  —> evidence VALID).
- COMMITS: 738a158, 2f842ac, 4302409 (pushed, CI GREEN
  34636544882 / 34642040793).
- TEST RESULTS: full suite 1469 passed / 15 skipped / 0 failed;
  propose-stale-warning tests 5; version metadata tests 3.
- FRICTION MAP: stale old_content propose-stage warning IMPLEMENTED
  (2/2 dogfood friction closed); partial-edit (region old_content)
  still requires full-file proposals — frozen validation semantics,
  design gate if ever needed.
- NEXT ACTION: real Claude Write runtime dogfood (credit gate).
- HANDOFF: expect HEAD at or after 4302409 + this checkpoint.

### 2026-09-10

- SESSION OBJECTIVE: security remediation checkpoint + roadmap re-sync
  + FAZ 6-lite analysis + implementation + adapter/FAZ 6-lite commits.
- WORK COMPLETED: RT-2 subprocess isolation; RT-1 R1+G1; FAZ 1 boundary
  map committed; Claude adapter committed; FAZ 6-lite A (approved retry
  resume + pending fingerprint dedupe) committed; red-team findings
  RT-1..RT-10 with RT-2/RT-1 closed.
- FILES CHANGED (now all committed): tanuq/pending.py,
  tanuq/claude_code_adapter.py,
  tests/test_tanuq_claude_code_adapter.py,
  docs/AGENT_INTEGRATION.md. (Also untracked:
  ORCHESTRATION_LIFECYCLE_DESIGN.md — commit decision pending.)
- COMMITS: 2536af0, 69f8d39, b061d03, 7de6a55 (all pushed, CI GREEN).
- TEST RESULTS: full suite 1399 passed / 15 skipped / 0 failed
  (including 6 RT-2 + 6 RT-6 + 9 RT-1/adapter adversarial tests).
- CI RESULTS: SUCCESS for 2536af0 / 69f8d39 / b061d03 / 7de6a55
  (4/4 jobs each).
- DECISIONS MADE: OPERATION_ID NOT REQUIRED — FROZEN; G1 governance
  gate approved and implemented; R1 implemented; FAZ 6-lite A chosen
  (option A of three); runtime duplication acknowledged, unified
  runtime deferred; **PRODUCTIZATION-FIRST WORKING MODEL accepted
  (frozen principle — see OPERATOR DECISION section).**
- FREEZE STATUS: unchanged.
- DISCOVERED RISKS: helper-module weakening outside G1; cross-assembly
  collision UNKNOWN; child_*.dmp secrets on disk.
- DOGFOOD (real CLI+adapter, temp workspace): all four scenarios
  behaved per design (LOW auto-VERIFIED; HIGH approve→execute
  VERIFIED; unapproved/stale→fail-closed; failing verification→
  ROLLED_BACK; evidence VALID). CONFIRMED product finding:
  cross-source fingerprint mismatch — reason is part of the
  fingerprint, so a CLI proposal and a vendor retry of the SAME edit
  produce DIFFERENT fingerprints; the human approval binds to the
  CLI-side fingerprint and the vendor retry gets fail-closed DENY +
  a second pending record. → **RESOLVED: FAZ 6-lite B (adapter
  content correlation) committed 3b8e259; F1 CLOSED end-to-end.**
- OPEN QUESTIONS: roadmap reorder approval; stale PROJECT_STATE/MASTER
  sync; cross-process simultaneous resume window (FAZ 7 candidate).
- NEXT ACTION: product dogfooding / evidence session on a scratch
  workspace (CONFIRMED first user-stopper: new-file creation denied at
  apply validation); hygiene commits (state file + LIFECYCLE_DESIGN);
  child_*.dmp cleanup (operator).
- NEXT HUMAN GATE: new-file-creation fix design (touches validation/
  apply semantics — core mutation boundary); roadmap reorder; freeze
  reopen condition (not met).
- HANDOFF: next session = read this file → verify git HEAD/worktree →
  expect HEAD at or after the FAZ 6-lite A commit → then FAZ 6-lite B
  or the FAZ 2 gate discussion.

---

## SESSION RESYNC FORMAT (use at the start of a new session)

```text
TANUQ — SESSION RESYNC
WHERE WE ARE:        <phase + gate>
WHAT WE JUST COMPLETED: <commits/CI>
CURRENT PHASE:       <FAZ X + status>
BLOCKERS:            <frozen gates / missing evidence>
FROZEN DECISIONS:    <list from FROZEN DECISIONS>
WHAT WE MUST NOT DO: <from DO NOT DO>
NEXT VALID ACTION:   <from NEXT VALID ACTION>
HUMAN DECISION REQUIRED: <from OPERATOR DECISIONS REQUIRED>
RECOMMENDED NEXT TASK:   <one task, with scope>
```
