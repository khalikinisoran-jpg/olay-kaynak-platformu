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

LAST UPDATED: 2026-09-23

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

- Nothing uncommitted (working tree clean at 0a9bd45). Next candidate
  work is designed but not started: real Claude Write runtime dogfood
  (blocked on API credit).

## NEXT VALID ACTION

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
ebd52b1 feat(adapter): govern Claude Code Write as create
654bf56 feat(governance): governed new-file creation via create action
3b8e259 feat(orchestration): cross-source resume via adapter content correlation
7de6a55 feat(orchestration): add approved retry resume and pending dedup
b061d03 feat(adapter): add Claude Code PreToolUse governed entry
69f8d39 docs(orchestration): map orchestration boundaries
2536af0 fix(security): harden verification integrity boundaries
```

## CI STATUS

Hosted CI (Ubuntu+Windows pytest, packaging-gate ×2): SUCCESS on
`7525c66`, `2536af0`, `69f8d39`, `b061d03`, `7de6a55`, `3b8e259`,
`654bf56`, `ebd52b1`, `2e2bf55`, `003fe9b`, `a67069d`, `0a9bd45`, `738a158`, `2f842ac`, and `4302409`
(latest run 34642040793 — 4/4 jobs, propose-stale warning included).
Latest local full suite: 1469 passed / 15 skipped / 0 failed.

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
