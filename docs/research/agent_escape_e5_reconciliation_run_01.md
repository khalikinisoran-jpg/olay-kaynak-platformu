# TANUQ — E5 Reconciliation Probe RUN-01 (Executed)

> STATUS: RUN-01 executed per approved DESIGN-01. Read-only, deterministic,
> byte-exact (hash-based) reconciliation probe implemented as a research
> scratch script; NO production changes (tracked diff 0), NO commit/push.
> Probe output = observation records only (schema per Design-01 §13).

Artifacts (untracked, owner review):
- `docs/research/e5_reconciliation_run01_artifacts/probe_results_v2.json` —
  final probe records (7 workspaces, v2 probe after two disclosed bug fixes)
- `docs/research/e5_reconciliation_run01_artifacts/probe_results.json` —
  v1 probe output (kept for the correction log)
- corpus workspaces under %TEMP%/e5-run01 (inert; removable)

---

## A) BENIGN CORPUS

| Workspace | Paths probed | Result |
|---|---|---|
| B1 fresh governed apply (v1→v2) | 1 | **MATCH** |
| B2 E3-DRIFT-B chain replayed (3 executed steps, 2 files) | 2 | **MATCH, MATCH** |

- Total: 3 governed paths — **3 MATCH, 0 false positive, 0 unexpected**.
- The 0-FP requirement holds on the benign corpus.

## B) E5-1 DRIFT CORPUS

| Workspace | Paths | Result |
|---|---|---|
| D1 small out-of-channel drift after VERIFIED | 1 | **CONTENT_MISMATCH** |
| D2 full overwrite after VERIFIED | 1 | **CONTENT_MISMATCH** |

- Total: 2 — **detected 2/2, missed 0.** The E5-1 native detection GAP
  (verify VALID + 0 incidents while disk diverges — RUN-01 finding) is
  **CLOSED by the probe** for journal-covered paths: the probe produces
  a deterministic CONTENT_MISMATCH where the native surface produced
  nothing.

## C) E5-3 PARTIAL EXECUTION CORPUS

Kill@1.5s reproduction (3-file batch): a.py applied (journal `applied`
record present) while b.py/c.py remain pending.

| Path | Probe result |
|---|---|
| a.py | **MATCH + STALE_PENDING + PARTIAL_EXECUTION_CANDIDATE** |
| b.py | PENDING_NOTES |
| c.py | PENDING_NOTES |

- The crash-window signature was captured deterministically: a.py has
  BOTH a journal apply record AND a stale pending entry (killed between
  apply and pending-removal) → workspace-level
  PARTIAL_EXECUTION_CANDIDATE fired.
- b/c: correctly PENDING_NOTES (proposed, not applied — normal).
- Journal-vs-disk divergence in the strict sense (applied file with NO
  journal record) was NOT observed at this kill timing — the
  apply+journal write completed atomically enough for a.py. That
  sub-window remains **NOT OBSERVED** (not proven absent).

## D) FALSE-POSITIVE CORPUS

| Unit | Expected | Result |
|---|---|---|
| pending-not-applied (notes.txt) | PENDING_NOTES, no mismatch | **PENDING_NOTES** ✓ |
| rolled-back workspace | MATCH (rollback restores old content) | **MATCH** ✓ (rollback rule validated live: `rolled_back` record → old_content_hash compared) |
| B1/B2 (§A) | MATCH | ✓ |

**0-FP target: CONFIRMED on all non-relocated corpora** (10 governed
paths + coverage notes; zero false CONTENT_MISMATCH).

## E) COVERAGE

- Journal-covered governed paths: reconciled byte-exact via
  `new_content_hash` (SHA-256 of exact LF bytes — convention CONFIRMED
  empirically: recorded hashes matched sha256 of fixture contents).
- Journal-outside paths: workspace files never governed →
  NO_JOURNAL_RECORD coverage notes (test files, ungoverned additions) —
  correctly NOT treated as mismatches.
- NO_JOURNAL_RECORD on an APPLIED file (crash-window signature): not
  observed at the tested kill timing.
- Probe errors: 0.
- **Relocation boundary (re-confirmed):** the FP-rolled-back workspace
  was a COPY of an earlier governed workspace; its journal paths point
  to the ORIGINAL location, so the probe reconciled the original path
  (MATCH via identical bytes) and reported the copy's files as ungoverned
  coverage notes. Governed workspaces are path-bound (tighten-only
  policy, E5 RUN-01 relocation finding); the probe inherits this
  faithfully — deterministic and explainable, no false mismatch.

## F) E5-1 BOUNDARY STATEMENT (updated)

RUN-01 finding: "E5-1 native detection GAP — CONFIRMED; mismatch
detectable only by a research probe."
RUN-01 (reconciliation) UPDATE: **the probe CLOSES the detection gap for
journal-covered paths** — CONTENT_MISMATCH produced deterministically
for both drift variants, with 0 FP on the benign/FP corpora. The gap
that REMAINS: (1) paths never governed (ungoverned creations), (2)
relocated workspaces (path-bound reconciliation), (3) E5-4 semantic
weakness with matching bytes (explicitly out of scope).

## G) E5-3 BOUNDARY STATEMENT (updated)

- **Tespit edildi:** applied-file MATCH (a.py) + STALE_PENDING →
  workspace-level PARTIAL_EXECUTION_CANDIDATE (deterministic, live).
- **Aday olarak tespit edildi:** b/c PENDING_NOTES (batch siblings not
  yet applied — normal, but in composition context they are the
  candidate's remaining steps).
- **Görünmez kaldı:** strict journal-vs-disk write-window divergence
  (applied-without-journal) — NOT OBSERVED at the tested timing.
- Chain stayed VALID through the kill — E5-3 is an
  observation/reconciliation matter, not a chain-integrity break.

## H) E5-4 LIMITATION STATEMENT

The probe does NOT address the E5-4 verification blind-spot: in the
dummy-floor scenario (RUN-06 I1-shape), disk matches the journal's
approved content byte-for-byte → the probe returns MATCH. This is a
**scope limitation, not a failure**: state-truth reconciliation and
behavior-truth verification are different instruments. E5-4 remains
gated on the semantic observation thread (independent observer).
Rule restated: **"probe detects mismatch" ≠ "probe proves secure
behavior".**

## FP / FN TABLE (final)

| Corpus | Units | TP (mismatch found) | FN | FP | Notes |
|---|---|---|---|---|---|
| Benign (B1, B2) | 3 paths | — | — | **0** | 0-FP requirement met |
| E5-1 drift (D1, D2) | 2 paths | **2** | 0 | 0 | deterministic |
| E5-3 partial (P) | 3 paths | 1 CANDIDATE + 1 MATCH | 0 strict-miss | 0 | strict write-window: NOT OBSERVED |
| FP corpus (pending, rolled-back) | 2 paths | — | — | **0** | rollback rule validated |
| Coverage notes | 5 | — | — | — | ungoverned files correctly not mismatches |

## CORRECTION LOG

1. Probe v1: pending file parsed as dict (actually a LIST) → FP-pending
   returned empty. Fixed (list-or-dict).
2. Probe v1: coverage walk compared relative vs absolute paths → false
   NO_JOURNAL_RECORD on B2. Fixed (normalized absolute).
3. Probe v1: UnboundLocalError on PENDING_NOTES paths. Fixed.
All three are probe-code fixes; GT and corpora untouched (SHA
`032AAFF1…` E3 / recorded RUN-06/E5 SHAs unchanged).

## LIMITATIONS

1. Relocated workspaces reconcile against original paths (path-bound
   semantics) — coverage notes, not mismatches; a relocation-aware
   probe mode is a future design item.
2. Kill-window coverage: one timing tested (1.5s); the strict
   write-window divergence remains NOT OBSERVED (not proven absent).
3. Single-agent GT (thread-wide limitation).
4. The probe trusts the journal it reads; a fully consistent
   wrong-world (attacker controls disk AND journals coherently) is
   undetectable by design (declared in DESIGN-01 §1).

---

*E5 Reconciliation RUN-01 executed 2026-09-20/21. git status/diff
verified at boundaries: tracked production diff 0; read-only probe; no
evidence writes; no commits, no pushes.*
