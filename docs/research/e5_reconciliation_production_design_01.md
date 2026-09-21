# TANUQ — E5 Reconciliation: Production Design-01
## (Observation-only execution↔evidence reconciliation — technical design, NOT an implementation decision)

> STATUS: DESIGN ONLY. No code, no tests, no commit/push. This document
> designs how the validated research probe (E5 Reconciliation RUN-01)
> could be incorporated into TANUQ production architecture, under the
> frozen-core constraints. An implementation decision is EXPLICITLY NOT
> made here (§31 GO/NO-GO criteria define the decision inputs).
>
> Standing constraint: **a CONTENT_MISMATCH finding does NOT imply
> execution blocking.** Reconciliation produces OBSERVATION ONLY.
>
> Research evidence base: E5 RUN-01 + Reconciliation RUN-01
> (agent_escape_e5_run_01.md, agent_escape_e5_reconciliation_run_01.md)
> — deterministic hash-based rule validated with 0 FP on benign/FP
> corpora and 2/2 CONTENT_MISMATCH detection on E5-1 drift.

---

## 1. MEVCUT MİMARİDE DOĞRU INSERTION POINT

**Selected: new standalone read-only module `tanuq/reconciliation.py`,
exposed as a new CLI subcommand (`tanuq reconcile --workspace`), built
strictly on the `trajectory.py` precedent** (read-only projection over
existing artifacts; no authority; no evidence writes; no pipeline
coupling).

Considered and REJECTED:
- **Pipeline post-execute hook** — touches WorkerActionPipeline (frozen
  core family), adds latency to the governed path, and creates
  enforcement-adjacent coupling. REJECTED.
- **Incidents projection extension** — incidents already detects journal
  deletion (E5-2-2c) and is detect-only; extending its FIELDS is viable
  but changes an existing module and couples reconciliation semantics to
  incident classification. DEFERRED as an optional integration (§12),
  not the core insertion point.
- **EventStore new event types** — evidence schema change = frozen-area
  change. REJECTED.
- **UI/server coupling** — view layer only; the reconciliation must be
  invocable without the UI. REJECTED as primary path.

The trajectory.py precedent is the only insertion pattern that
satisfies every constraint in this design with ZERO core diff.

## 2. DATA SOURCE

1. **ApplyOutcomeJournal** (`<ws>/.tanuq/data/apply_journal.jsonl`):
   - `intent` records: path, patch_fingerprint, old_content_hash,
     new_content_hash (SHA-256 of exact LF bytes — convention
     CONFIRMED empirically in E5 Reconciliation RUN-01).
   - Terminal records per intent: `applied` / `rolled_back` /
     `apply_started` (without terminal = interrupted).
   - Journal is ITSELF hash-chained (previous_hash/current_hash per
     record) — the probe can verify journal-internal integrity before
     trusting it (secondary check; primary integrity = `tanuq verify`).
2. **Governed path set:** derived ONLY from journal intent paths (plus
   pending paths from `pending_proposals.json`). NO directory scanning
   by default (§7).
3. **Actual disk state:** direct byte read + SHA-256 per governed path,
   read at reconciliation time.

Nothing else is read. No EventStore content, no verification logs, no
config beyond the workspace location already implied by the journal
paths.

## 3. CANONICAL HASH CONVENTION

- `content_hash = SHA-256(content.encode("utf-8"))` over the EXACT
  stored bytes (LF; no CRLF translation) — CONFIRMED: journal-recorded
  hashes matched sha256 of fixture contents (E5 Reconciliation RUN-01).
- The convention is READ from the journal records, not redefined: the
  probe never computes "its own" hash variant.
- Edge cases declared: binary/undecodable files — hashes operate on
  bytes, so encoding is irrelevant; only exact-byte equality matters.

## 4. DETERMINISTIC COMPARISON RULE

Per governed path P with last intent I (terminal state T):

| Journal terminal | Expected disk hash | Comparison |
|---|---|---|
| `applied` (no rollback) | `new_content_hash(I)` | equal → MATCH; different → CONTENT_MISMATCH |
| `rolled_back` | `old_content_hash(I)` | equal → MATCH; different → CONTENT_MISMATCH |
| `apply_started`, no terminal | none | **INDETERMINATE — skipped** (in-flight/interrupted; §19) |
| intent only, no apply | `old_content_hash` if file exists | informational (intent recorded, never applied) |

Additional non-mismatch observations:
- pending proposal referencing P → PENDING_NOTES; if P already has an
  `applied` journal record → **STALE_PENDING → PARTIAL_EXECUTION_
  CANDIDATE** (E5-3 signature, CONFIRMED in research run).
- disk file missing but journal expects content → FILE_MISSING.
- probe read error → PROBE_ERROR (never a mismatch claim; §17/§19).

Determinism: same journal + same disk bytes at read time → identical
output. No thresholds, no similarity, no scoring (E1-C lesson applied).

## 5. RESULT CLASSES

MATCH · CONTENT_MISMATCH · FILE_MISSING · PARTIAL_EXECUTION_CANDIDATE ·
INDETERMINATE (in-flight/interrupted) · STALE_PENDING · PENDING_NOTES ·
NO_JOURNAL_RECORD (coverage note only) · PROBE_ERROR.

Exactly the classes validated in the research probe, plus
INDETERMINATE (production requires explicit in-flight handling; the
research harness could ignore it because it controlled execution
timing).

## 6. COVERAGE BOUNDARY

- Reconciliation scope = journal-covered paths ONLY (the path set of
  intent records + pending paths). Bounded by governed-file count, not
  workspace size.
- Coverage report (mandatory output section): reconciled count,
  pending-only count, skipped-in-flight count, ungoverned-file count
  (files in governed directories without journal records — counted,
  listed by path only, NEVER treated as mismatches).
- Declared limit: out-of-channel CREATION of never-governed files is
  invisible (E5 Reconciliation RUN-01 finding). Extending coverage to
  ungoverned files is an OPEN QUESTION (§30) requiring an owner
  decision because it expands the probe's read scope = authority
  expansion.

## 7. UNGOVERNED FILES SINIRI

- Ungoverned files (no journal record, no pending): counted in the
  coverage report (path list optional behind a flag), classified
  NO_JOURNAL_RECORD — explicitly NOT mismatches.
- Rationale: treating their existence as a finding would make every
  legitimate new file a "detection" (FP explosion) and would silently
  convert the probe into a workspace-wide scanner (authority creep).
- Future extension path: owner-approved scope widening, e.g. reconcile
  only files inside `allowed_paths` config (config-derived scope) —
  still deterministic, still observation-only. NOT part of this design.

## 8. RELOCATION / PATH-BOUND DAVRANIŞI

- CONFIRMED (E5 RUN-01): governed workspaces are path-bound;
  `allowed_paths` in `.tanuq/config.json` references the original
  location; a copied workspace is rejected fail-closed by the
  tighten-only policy (verify/incidents/propose refuse to run).
- Production reconciliation INHERITS this: it runs on the workspace at
  its original path. A relocated copy → the CLI-level policy error
  surfaces (fail-closed) and reconciliation reports it as
  RELOCATION_BLOCKED rather than pretending to reconcile.
- GAP-ONLY (no fix in this design): legitimate workspace moves have no
  supported path; that is an operator/UX matter outside E5 scope.
- Security note: path-binding also blocks an evidence-relocation
  tampering pattern (copy → tamper → present elsewhere), which is a
  feature retained as-is.

## 9. E5-3 PARTIAL EXECUTION İLİŞKİSİ

- `apply_started` without a terminal record → INDETERMINATE (the crash
  window between disk-write and journal-write, or in-flight execution).
- STALE_PENDING (pending entry remains after the intent's `applied`)
  → PARTIAL_EXECUTION_CANDIDATE (CONFIRMED signature in research run).
- The probe NEVER repairs, never re-executes, never removes pending
  entries. Recovery remains the existing FAZ-8 domain (design-freeze
  respected); reconciliation only OBSERVES the residual state.
- Open measurement item carried from research: the strict
  disk-write-before-journal-write window was NOT OBSERVED — production
  reconciliation would observe it opportunistically, not constructively.

## 10. E5-4 SEMANTIC BLIND SPOT SINIRI (korunur)

- Byte-match (MATCH) says NOTHING about behavior: a dummy-floor
  VERIFIED weakening change reconciles cleanly (disk == journal) while
  being semantically dangerous (E5-4, CONFIRMED in RUN-06 I1-shape).
- Documentation requirement: every reconciliation output carries the
  standing note "MATCH = state consistency, NOT security" — the E5-4
  blind spot is explicitly out of scope and remains gated on the
  semantic observation thread (independent observer).
- The probe must never be presented (UI/docs) as "security check" —
  it is a "state consistency check".

## 11. EVENTSTORE İLİŞKİSİ

- READ-ONLY: the probe may read events.jsonl for context (e.g., event
  sequence ranges per fingerprint in the output) but has no write path.
- The probe does NOT validate the chain itself — that is `tanuq
  verify`'s role. Reconciliation records the verify verdict as context
  (two independent layers, as observed in E5-2: chain catches EventStore
  tampering; reconciliation catches disk-vs-evidence divergence).
- No new event types. No evidence-chain writes. Zero EventStore schema
  impact.

## 12. INCIDENTS PROJECTION

- Current state: incidents detects journal-line deletion (E5-2-2c,
  1 critical) but NOT content drift (E5-1, 0 incidents) — CONFIRMED.
- Option A (default in this design): reconciliation output stands
  alone via `tanuq reconcile`; incidents untouched.
- Option B (separate owner-gated follow-up): surface reconciliation
  records through the incidents projection (detect-only, no auto-repair)
  — schema-compatible with the observation record format (§13 of the
  reconciliation design). NOT decided here.

## 13. TRAJECTORY PROJECTION

- trajectory.py answers "what did governance decide/observe per path".
- Reconciliation answers "what is on disk vs what was evidenced".
- They compose (trajectory = governance narrative; reconciliation =
  disk-truth check) but remain separate projections. No trajectory
  changes in this design.

## 14. EVIDENCE CHAIN İLE İLİŞKİ

- Reconciliation output is NOT written into the evidence chain — no
  new event types, no journal entries, no anchor involvement.
- Rationale: writing observation records into the anchored chain would
  (a) change frozen evidence semantics, (b) create authority creep
  (observations becoming evidence authority), (c) grow the chain with
  non-governance data.
- The probe RECORDS the current verify verdict as context but cannot
  alter it.

## 15. RECONCILIATION OUTPUT'UN EVIDENCE AUTHORITY OLMAMASI

- Output = scratch/CLI projection. It is not persisted into `.tanuq`,
  not signed, not anchored, not referenced by governance decisions.
- It confers NO authority: cannot authorize, cannot approve, cannot
  lower/raise risk, cannot block or unblock execution, cannot modify
  fingerprints, cannot repair.
- If a future owner decision surfaces mismatches in the UI/incidents,
  they remain DETECT-ONLY observations (incidents precedent: no
  auto-repair).

## 16. AUTHORIZATION / POLICY / FINGERPRINT'E ETKİ SIFIRI

- No code path from reconciliation results into RiskEngine, RiskPolicy,
  GovernanceEvaluator, ApprovalStore, ApplyAuthorization, Controller,
  or fingerprints.
- The module imports NOTHING from the governed pipeline; it reads
  journal/files directly (read-only), mirroring the trajectory.py
  isolation pattern.
- Confirmed by design: reconciliation cannot raise or lower any risk
  classification (the research probe's raise-only advisory channel is
  a DIFFERENT primitive and is explicitly NOT part of this design).

## 17. FAIL-OPEN OBSERVATION SEMANTICS

- Probe-internal errors (unreadable file, journal parse failure,
  permission error) → PROBE_ERROR record for that path; the run
  continues for other paths.
- PROBE_ERROR is never a mismatch claim, never blocks anything (the
  probe has no enforcement capability), never triggers retries inside
  the governed pipeline.
- The only fail-closed behaviors in the vicinity are the EXISTING ones
  (verify on tampered chains; execute authorization) — untouched.

## 18. PERFORMANCE / FREQUENCY / TIMING

- Cost model: O(#governed paths) file reads + SHA-256. Bounded by the
  journal (typically tens of paths), NOT workspace size. No full
  workspace scan (§6/§7).
- Frequency options (all on-demand by default; no daemon, no scheduler):
  1. **Manual:** `tanuq reconcile --workspace` — operator runs it when
     wanted (default; zero steady-state cost).
  2. **Post-execute optional:** could be run manually after important
     executions; automatic invocation after every execute is REJECTED
     for the default design (adds latency to the governed path and
     creates pipeline coupling).
  3. **Periodic manual/external:** an operator cron/task calling the
     CLI — outside TANUQ, no daemon inside the product.
- Timing honesty: results are POINT-IN-TIME. A MATCH means "at read
  moment T, disk bytes hashed to the evidenced value" — it says nothing
  about T+1ms (concurrency §19; E5-4 blind spot §10).

## 19. CONCURRENCY / RACE WINDOW

- Disk state may change DURING reconciliation (another process writing,
  an agent working, verification running).
- TOCTOU: the probe reads the journal, then reads files. Between the
  journal read and each file read, a governed execution could apply a
  new change → the probe would report a "mismatch" that is actually a
  legitimate newer state.
- Mitigations (all observation-side, deterministic):
  1. **In-flight detection:** if the journal shows `apply_started`
     without a terminal for an intent (execution possibly in
     flight/interrupted), the path is marked INDETERMINATE and skipped
     from mismatch claims (CONFIRMED journal signal — the E5-3
     signature).
  2. **Point-in-time honesty:** every record includes the read
     timestamp; the output states "observed at T" — never a state
     guarantee.
  3. **No verdict language:** a mismatch record says "disk differs from
     the last evidenced state observed at T" — it does NOT say "tampered"
     or "attack" (a legitimate concurrent change produces the same
     record).
- Residual race: a mutation landing between the journal read and the
  file read can produce a stale comparison. Accepted and documented:
  reconciliation is a best-effort point-in-time observation; rerunning
  it is the remedy. It cannot create false "MATCH" security assurance
  beyond the same limitation.
- "Hash eşleşti" carnın kapsamı: "okuma anında T'de, disk baytları
  evidenced hash ile eşleşti" — bu ifade dürüstçe output'a yazılır.

## 20. CRASH / RECOVERY DAVRANIŞI

- The probe crashing mid-run: no state was modified (read-only);
  partial output files are scratch; rerun is safe.
- The governed pipeline crashing mid-apply: reconciliation observes the
  residual state (E5-3: INDETERMINATE via `apply_started`-without-
  terminal, PARTIAL_EXECUTION_CANDIDATE via STALE_PENDING) — it reports
  the crash window signature instead of a false MATCH/MISMATCH.
- Recovery/reconciliation-of-record remains the existing FAZ-8 domain
  (detect/reconcile design-freeze respected); this module never
  repairs.

## 21. PRIVACY / DATA EXPOSURE

- Output records contain: paths, fingerprints (already evidence
  metadata), SHA-256 hashes, timestamps. NO file content, NO diffs, NO
  secrets.
- The probe READS file contents (to hash) but never writes them
  anywhere — content stays in memory.
- Exception: research-mode artifact output (as in E5 RUN-01) may store
  hashes/paths only; content previews are explicitly excluded from the
  production output design.
- Relocation finding: outputs reference the path-bound workspace — no
  new exposure.

## 22. BACKWARD COMPATIBILITY

- New module + new CLI subcommand only. No existing module, command,
  format, or behavior changes. Zero diff in `tanuq/` existing files
  (new file + cli.py subcommand registration — the ONLY existing-file
  touchpoint, a mechanical addition mirroring the `trajectory`
  subcommand pattern).
- Journal/pending formats are read as-is; no format migration.
- Workspaces created before this feature reconcile identically (the
  journal format is stable).
- Skipping the feature entirely (never running `reconcile`) leaves
  behavior identical to today.

## 23. PROVIDER / AGENT INDEPENDENCE

- The probe consumes only TANUQ-internal artifacts (journal, pending,
  disk). No model, no provider, no agent cooperation required.
- Agent-agnostic by construction: the journal records any proposer's
  governed changes identically (vendor-blind core, CONFIRMED).
- Works with zero agents (reconciles the operator's own governed
  changes) and with any agent stack.

## 24. TEST STRATEGY

New test module(s) only (G1: no existing test module modified):
1. **Rule unit tests:** synthetic journals + temp files → each result
   class (MATCH / CONTENT_MISMATCH / FILE_MISSING / INDETERMINATE /
   STALE_PENDING / PENDING_NOTES / NO_JOURNAL_RECORD / PROBE_ERROR),
   including the rolled_back → old_content_hash rule (the E5-4/rollback
   FP case from research).
2. **Hash convention tests:** recorded journal hashes vs sha256 of
   fixture contents (LF-exact; CRLF divergence documented).
3. **Corpus tests:** the frozen E5-1 drift fixtures (small drift, full
   overwrite) → CONTENT_MISMATCH; frozen benign/FP corpora → 0
   mismatch (0-FP regression, per the research RUN-01 results).
4. **Determinism test:** same inputs → identical records (two runs).
5. **In-flight test:** `apply_started`-without-terminal journal →
   INDETERMINATE (no mismatch claim).
6. **Integration:** real disposable workspace, governed apply, then
   out-of-channel edit → reconcile → CONTENT_MISMATCH; then governed
   re-application → MATCH (the E5-1 scenario end-to-end).
7. **Privacy test:** output contains no file content (only paths/
   hashes).
8. **Authority test:** no imports/calls into pipeline/approval/risk
   modules (import-boundary assertion).

## 25. ROLLBACK / DISABLE STRATEGY

- The feature is a standalone CLI projection: **disable = do not run
  it.** No runtime coupling exists to undo.
- Removal = delete the module + subcommand registration (single-file
  revert); no data migration to undo (no persisted probe state).
- If surfaced later through incidents (Option B, §12), removal returns
  incidents to its current fields — incidents is the only integration
  point to revert.

## 26. MIGRATION REQUIREMENTS

- None. No persisted probe state, no schema changes, no format
  changes. Journal/config/pending formats are consumed as-is.
- The only "migration" is documentation: USER_GUIDE addition describing
  the command and its observation-only semantics (docs-only commit).

## 27. SECURITY BOUNDARIES

- Probe reads: journal, pending, governed files — the same artifacts
  the CLI already reads. No new read scope (ungoverned scanning
  excluded by default, §7).
- Probe writes: scratch output only. No `.tanuq` writes. No evidence
  chain interaction.
- Probe authority: none (§15/§16). It cannot become an enforcement
  point without a new owner decision (explicitly out of scope).
- Threat honesty: a fully consistent wrong-world (attacker controls
  disk AND journals coherently) is undetectable — declared in the
  research phase, preserved here.

## 28. E5-1 / E5-3 RESEARCH EVIDENCE MAPPING

| Research finding (CONFIRMED) | Design coverage |
|---|---|
| E5-1: out-of-channel drift after VERIFIED; verify VALID; 0 incidents; mismatch only via probe | §4 rule (CONTENT_MISMATCH), §6 scope, §20 F mapping table |
| E5-1: 0 FP on benign/FP corpora | §24 test 3 (0-FP regression) |
| E5-1: rollback → old-content restoration | §4 rolled_back rule (validated live) |
| E5-3: applied + STALE_PENDING → PARTIAL_EXECUTION_CANDIDATE | §4 STALE_PENDING/PARTIAL rules; §9 |
| E5-3: chain VALID through kill; partial state persists | §9 (observation-only, no repair), §20 |
| E5-2: EventStore tampering fail-closed; journal deletion → incidents | §11/§12 (layers kept separate; no duplication) |
| Relocation fail-closed (path-bound) | §8 (inherited, documented) |
| E5-4: VERIFIED ≠ secure | §10 (standing limitation, preserved) |

## 29. PRODUCTION IMPLEMENTATION RISKLERİ

1. **FP-by-timing:** reconciliation during in-flight execution →
   mitigated by INDETERMINATE rule (§19); residual stale-read risk
   accepted and documented (point-in-time semantics).
2. **Authority creep:** future pressure to make mismatches block
   execution → structural prevention: no code path exists; the module
   has no enforcement imports (test-enforced, §24.8).
3. **Hash convention drift:** if TANUQ's internal hash convention ever
   changed (frozen-area change), the probe breaks loudly (mass
   MISMATCH) — detectable, and the convention is itself FROZEN.
4. **Performance on long journals:** bounded by governed-path count;
   pathological journals (thousands of paths) → linear cost, still
   file-read bound; no mitigation needed at current scale, noted for
   the future.
5. **Privacy of paths in output:** paths leak directory structure in
   CLI output — same exposure as existing `history`/`status` commands;
   no new exposure.
6. **False assurance risk (E5-4):** users reading MATCH as "secure" →
   mitigated by mandatory standing note in output/docs (§10).
7. **Windows specifics:** the research harness hit cmd.exe pipe flakiness
   — production implementation runs in-process (module function, not
   subprocess), eliminating that class entirely.

## 30. AÇIK SORULAR (owner decisions required before implementation)

1. Incidents integration: standalone CLI only (default) vs also
   surfacing records through incidents projection (Option B)?
2. Scheduling: manual-only (default) vs documented external-scheduling
   recipe?
3. Ungoverned-file coverage: keep excluded (default) vs owner-approved
   allowed_paths-scoped extension?
4. Output channel: CLI-only vs also UI panel (view-layer work)?
5. Relocation support: keep fail-closed path-binding (default) vs
   design a legitimate re-location flow (separate security review)?

## 31. GO / NO-GO / CONDITIONAL GO CRITERIA

**GO (all must hold):**
- Implementation is a NEW read-only module + one CLI subcommand
  registration; zero diff to existing production files beyond that
  mechanical registration.
- Rule matches §4 exactly (deterministic, hash-based, no
  similarity/thresholds).
- 0-FP on the frozen benign/FP corpora (research corpus reused).
- Authority test passes: no imports into pipeline/approval/risk
  modules; no evidence writes.
- Output carries the standing "state consistency, NOT security" note.

**CONDITIONAL GO (GO + owner decision on an option):**
- Incidents surfacing (Option B) — requires the incidents-field owner
  gate.
- allowed_paths-scoped ungoverned coverage — requires the §30.3 owner
  decision.

**NO-GO (any one):**
- Any code path that could block/alter execution, authorization, risk,
  fingerprints, or evidence based on reconciliation output.
- Full-workspace scanning as default behavior.
- Automatic post-execute reconciliation coupled to the pipeline.
- Any evidence-chain writes.
- Similarity/threshold-based classification entering the rule.

---

## SONUÇ

This design demonstrates a production path that (a) preserves every
frozen boundary, (b) requires zero changes to the governed core,
(c) inherits the validated deterministic rule and 0-FP corpus from the
research thread, and (d) leaves the enforcement question untouched by
construction. The decision remains with the owner (§31); this document
is the technical input, not the decision.

*Production Design-01 prepared 2026-09-20. Yalnızca bu dosya
oluşturuldu; tracked production diff 0; commit/push yok.*
