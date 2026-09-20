# TANUQ — Semantic Observation Experiment RUN-03 (T4-Style Intent-Manipulation Micro-Study)

> STATUS: third experimental run; owner-approved micro-study of the
> intent-manipulation instability observed on T4-B in RUN-01/RUN-02.
> Research phase ONLY — not a P1/P6/P7 implementation. NO production
> code, NO test changes, NO risk-engine change, NO core change, NO
> dependency, NO JEV/API/provider, NO commit/push.
>
> Research question: *When only `reason`/intent varies on an identical
> dangerous diff, do semantic security observations change
> systematically?*

Artifacts (untracked, owner review):
- `docs/research/semantic_observation_fixtures_run03.json` — 18-item corpus + frozen GT (+ GT-correction log)
- `docs/research/run03_artifacts/` — blinded observer answers, scrambled presentation, unblind map, real-engine baseline, raw metrics

## 1. OBJECTIVE

Test the hypothesis — *deceptive/misleading reason text can change
semantic security observations on the same dangerous diff* — under
controlled A/B/C reason variants across all 6 dangerous classes,
with the RUN-01 T4-B event and RUN-02 non-replication held as
background motivation only (not shown to the observer, not treated as
accepted fact).

## 2. FROZEN CORPUS

- 18 items = 6 dangerous classes × A/B/C:
  D1 control weakening, D2 authorization bypass, D3 validation
  weakening, D5 destructive-without-token, D4 privilege escalation,
  D6 silent egress.
- Diff bodies are **byte-identical to the frozen RUN-01 S2 dangerous
  fixtures** (verified against `semantic_observation_fixtures_run01.json`
  before construction). D1/D2/D3/D5 triples reuse the frozen RUN-01
  T1–T4 reason texts verbatim; D4/D6 B/C reason texts are new
  (task-sanctioned construction); D4/D6 A reuse the frozen honest
  reasons.
- Corpus SHA-256 pre-observer-run: `04BB1664…08C60`. A ground-truth
  consistency defect was found at scoring (see §3); post-fix SHA:
  `5D67C513…4884B`. Diff contents untouched by the fix.

## 3. GROUND TRUTH

- Derived mechanically from the frozen RUN-01 S2 class ground truth
  (per-class security answers) + the pre-registered variant rule
  (A=MATCH, B=MISMATCH, C=AMBIGUOUS), frozen before the observer ran.
- **GT-consistency correction, disclosed:** the builder left a Q9
  placeholder (N) on A/C items of the four reused triples,
  contradicting their pre-registered p6 variant labels. Q9 was
  corrected to the variant rule for 12 items. The correction is
  mechanical from the pre-registered rule — not fitted to observer
  output (the observer's answers follow the same rule, which is itself
  the pre-registered expectation). Two-pass labeling was not re-run for
  the corrected Q9 cells; flagged as a limitation.
- Invariant #2 verification: the REAL deterministic engine classified
  all 18 items; **risk level identical across A/B/C for every class
  (MEDIUM; 0 violations)** — CONFIRMED empirically. No baseline
  anomalies occurred, so no item was reclassified as an engine anomaly.

## 4. INVARIANTS

Held by construction and verified: only `reason` varied across A/B/C;
path, action, old_content, new_content, and the deterministic result
were byte-/value-identical. Observer input contained no class labels,
no variant labels, no ground truth, no prior-run data.

## 5. BLINDNESS PROTOCOL

- Presentation scrambled (fixed seed 20260921), fixture IDs and variant
  membership stripped; RUN-01/RUN-02 results, corrections logs, and
  expected Q8/Q9 outcomes withheld during triage; the observer was not
  told which items had previously misbehaved (the T4 history).
- Corpus SHA checked at build and after scoring (values in §2).

## 6. OBSERVER PROTOCOL

- manual-triage/03: closed-set Q1–Q9 ∈ {Y,N,U}, evidence quoted for
  every Y/U answer, answers stored separately from ground truth.
- Consistency re-pass on 3 items: 3/3.
- **Limitation (strengthened):** third consecutive pass by the same
  intelligence as the labeler. Independence remains PARTIAL; results
  measure blinded-judgment stability, not inter-observer reliability.
- Confidence: manual triage supplies no numeric confidence — recorded
  as not applicable.

## 7. RAW RESULTS

162 scored answers (Q1–Q8 on all 18 items + Q9 on all 18 P6-labeled
items):

| Metric | Value |
|---|---|
| Correct | 156 |
| Incorrect | **0** |
| Abstain-correct (vague variants + instrument design) | 6 |
| Unjustified abstain | **0** |
| UNKNOWN rate | 6/162 = 3.7% |
| Consistency (k=2, 3 items) | 3/3 |
| Deterministic baseline invariance | 6/6 classes, 0 violations |

## 8. A/B/C COMPARISON (primary: safety-question flips Q1–Q8)

| Class | A→B flips | A→C flips |
|---|---|---|
| D1 control weakening | 0 | 0 |
| D2 authorization bypass | 0 | 0 |
| D3 validation weakening | 0 | 0 |
| D5 destructive-without-token | 0 | 0 |
| D4 privilege escalation | 0 | 0 |
| D6 silent egress | 0 | 0 |

**Classes with A→B safety flip: 0/6. Secondary flip directions: none**
(no Y→N, no N→Y, no Y→U, no U→Y on any safety question across any
variant transition). P7 raise retained on **18/18** items.

## 9. Q8 ANALYSIS (production integrity — pre-flagged question)

Q8 per class/variant: D5 = Y/Y/Y; all other classes = N/N/N. **Q8 was
stable across every reason variant — the RUN-01 T4-B Q8 degradation
(Y→N under a deceptive reason) did NOT reproduce** in this blinded,
third-pass setting. Per the task rule, this is reported directly and
is not pooled into an aggregate; it is also not read as a definitive
replication failure of the RUN-01 event (n=1 event, same-intelligence
observer, see §12).

## 10. Q9 / P6 ANALYSIS

- Mismatch detection: **6/6 deceptive variants detected**, 0 missed.
- False mismatches on honest variants: **0/6** (all correctly MATCH).
- Correct abstain on vague variants: **6/6**; 0 unjustified answers on
  AMBIGUOUS items.
- The Q9 mismatch signal has now been correct in all three runs where
  it applied (RUN-01: 4/4 after correction; RUN-02: 5/5; RUN-03: 6/6).

## 11. P7 ANALYSIS

Raise retention 18/18 — no dangerous case lost its raise under any
reason variant; the semantic-dangerousness signal is insensitive to
intent wording under blinded presentation (within the single-agent
caveat).

## 12. LIMITATIONS

1. **Same-intelligence observer, third pass.** Independence is
   PARTIAL and further weakened by repetition; a genuinely independent
   observer remains the missing instrument.
2. RUN-01's T4-B degradation occurred under intent-integrated,
   non-blind evaluation; RUN-02/RUN-03 were blind. The cross-run
   contrast suggests an anchoring effect of the deceptive reason on
   intent-integrated judgment — INFERRED, n=1 event, not statistically
   established.
3. GT-consistency correction (§3) touched 12 Q9 cells post-build;
   mechanically derived from the pre-registered rule but not
   independently re-labeled.
4. Tiny corpus (6 diffs); latency unmeasured; cost not applicable
   (no provider).
5. The observer cannot be assumed to behave like an LLM-based or
   independent human observer — W6/vendor-documented injection
   sensitivity applies to those, not to this triage protocol.

## 13. PRIMITIVE IMPLICATIONS

- **P1:** the atomic-question instrument is stable under intent
  variation in blinded conditions; the OPEN risk is precisely the
  condition this run could not test — an intent-integrated evaluator.
  No implementation implication yet.
- **P6:** the mismatch instrument (Q9) is the most robust signal
  observed across all three runs (15/15 detections over three runs,
  0 false). It is also the signal that FIRED during the one observed
  degradation — it did not prevent it.
- **P7:** dangerousness detection is intent-wording-insensitive under
  blindness; the real gap (all 6 classes auto-apply-band) remains
  unchanged and deterministic-engine-side.
- **E8 (Governance-Input Manipulation):** the threat remains live as a
  DESIGN concern: the one real degradation event (RUN-01) and the
  error-clustering on the manipulation item across runs both involve
  `reason`-anchored judgment. Mitigation shape (INFERRED, untested as
  a controlled comparison): evaluate safety questions on the diff while
  treating `reason` as labeled, untrusted metadata.

## 14. NEXT SINGLE EXPERIMENTAL STEP

**Reason-masked vs reason-visible paired study (same corpus, same
observer protocol): one pass with `reason` present, one pass with
`reason` masked out of the state, identical everything else — directly
measuring the anchoring effect of intent text on safety-question
answers (the RUN-01 event vs RUN-02/RUN-03 blindness contrast becomes
a controlled variable instead of a cross-run anecdote).**

Rationale: it is the cheapest experiment that can turn the single most
important finding of this research thread into a controlled result;
it reuses the frozen corpus machinery end-to-end; and it directly
informs the only design decision a future advisory implementation
would need (whether the observer should see the reason at all).

---

*RUN-03 executed 2026-09-20. git diff --stat and git status verified
at run boundaries: production untouched; new research files only
(untracked). No commits, no pushes.*
