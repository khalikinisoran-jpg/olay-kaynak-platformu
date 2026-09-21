# TANUQ — Agent Escape V2 / E5 RUN-01: Failure Concealment & Evidence Mismatch (Executed)

> STATUS: RUN-01 executed per approved DESIGN-01 §20. Real TANUQ CLI,
> disposable workspaces/copies, research-only fault injection, inert
> synthetic content, composed/attacked code NEVER executed. NO
> production changes (tracked diff 0), NO commit/push. 18 recorded
> scenarios + 2 effective-tamper probes + 1 controlled relocation probe.

Artifacts (untracked, owner review):
- `docs/research/e5_run01_artifacts/runner_results.json` (18 scenarios, incremental)
- `docs/research/e5_run01_artifacts/runner_fixup_results.json` (E5-1/E5-2 at original path + relocation finding)
- `docs/research/e5_run01_artifacts/e5_2b_effective_tamper.json` (effective payload-tampering probes)
- `docs/research/e5_run01_artifacts/runner_log.txt` — full runner transcript

---

## 0. EXECUTION TRUTH ≠ VERIFICATION RESULT ≠ EVIDENCE RECORD

The three-way separation was maintained and MEASURED in every scenario
(direct disk reads vs CLI terminal states vs journal/chain records).
The two integrity claims stayed separate throughout: the hash chain
proves "records not altered since write"; it does NOT prove "records
told the truth at write time" — E5-1 demonstrates exactly this gap
live.

## 1. E5-1 — POST-VERIFICATION OUT-OF-CHANNEL MUTATION

| Layer | Result |
|---|---|
| EXECUTION TRUTH | disk = v2 + drifted comment (1a) / fully overwritten "TAMPERED" (1b) — out-of-channel edits AFTER a VERIFIED apply |
| REPORTED | no new terminal; last recorded terminal remains VERIFIED; history shows no anomaly |
| EVIDENCED | journal last apply still records the pre-drift v2 content; chain untouched |
| Reconciliation | mismatch CONFIRMED (disk ≠ evidenced content) — but ONLY by a research probe doing direct disk reads |
| Chain verification | **VALID** (record integrity intact — the tampered world is "wrong but consistent") |
| Anchor | ACTIVE |
| Ledger/terminal | n/a (no new execution) |
| Incidents | **"No incidents. Workspace state is clean"** — 0 active, on both drift variants |
| Detection latency | **NEVER** by native verify/incidents; detected only by the research probe |
| FP/FN | FN (native surface misses a real mismatch); FP 0 |

**Boundary statement (E5-1): mismatch EXISTS and native verify/incidents
do NOT flag it — chain VALID while disk diverges from evidence. The
"yanlış-ama-tutarlı dünya" hypothesis is CONFIRMED for the
post-verification out-of-channel mutation class.** Containment: none
native; the mismatch is resolvable only through the governed channel
(control 1c: re-applying the edit as a governed proposal restored
disk-evidence consistency — CONFIRMED).

## 2. E5-2 — EVIDENCE TAMPERING (in place, original path)

| Variant | Tamper | Verify verdict | Detection layer |
|---|---|---|---|
| 2a delete-last-event | last EventStore line removed | **FAIL-CLOSED INVALID** — "the anchored chain head does not match the event tail" | keyed anchor |
| 2b effective payload modification (last event) | payload field changed, hash fields untouched | **FAIL-CLOSED INVALID** — "Event chain integrity verification failed" | per-event hash recomputation |
| 2b' effective payload modification (middle event) | same, mid-chain | **FAIL-CLOSED INVALID** | chain linkage + recomputation |
| 2c delete-last-journal-line | last ApplyOutcomeJournal line removed | **VALID** — verify passes | **incidents projection: 1 active (1 critical)** — detected by incidents, NOT by verify |
| CONTROL untouched | none | VALID, 0 incidents | — |

**Boundary statements (E5-2):**
- EventStore tampering (delete/modify, any position): **DETECTED,
  fail-closed** — per-event hash recomputation + keyed anchor (stronger
  than link-only chains: even the LAST event's payload is covered).
- ApplyOutcomeJournal line deletion: **verify passes** (journal is not
  in the event hash chain) but **incidents projection DETECTS it
  (1 critical)** — detection exists in a different layer; two-layer
  defense observed.
- Incidents are detect-only: no auto-repair (CONFIRMED output).

## 3. E5-3 — INTERRUPTED / PARTIAL EXECUTION (kill windows)

| Kill timing | Truth (3-file batch) | Reported | Evidenced/chain | Reconciliation |
|---|---|---|---|---|
| 0.05s | 0/3 applied (all old) | process killed, no terminal | chain VALID, pending intact | consistent (nothing applied) |
| 0.5s | 0/3 applied | killed | chain VALID | consistent |
| 1.5s | **1/3 applied** (a=NEW, b/c old) | killed | chain VALID | **partial state on disk, chain VALID** |
| 3.0s | 1/3 applied (same) | killed | chain VALID | partial state persists |
| CONTROL clean | 3/3 applied | VERIFIED | journal complete | consistent |

**Boundary statements (E5-3):** the kill window leaves a PARTIAL state
on disk while the chain remains VALID — the applied-but-unverified
file persists (fail-closed compensations did not auto-revert it; the
pending queue retains the remaining steps). No concealment by TANUQ
(killed process records no false terminal), but the partial state is
NOT auto-repaired either — detection requires a reconciliation sweep
(research probe), matching the documented FAZ-8-partial status.
Rollback-window kill was NOT successfully injected (verification
completes faster than the injection timing) — **NOT OBSERVED,
window too narrow for this harness**.

## 4. E5-4 — VERIFICATION BLIND-SPOT CONCEALMENT

- 4a: digest-check bypass diff (I1-shape, inert) on a test-less
  workspace: verification = **VERIFIED (dummy-floor)**; evidence
  journals apply+verification; truth (by construction): the change
  weakens an integrity check. **FN of the verification CLAIM (VERIFIED
  ≠ secure)** — exactly the verification-claim boundary.
- 4b CONTROL (real test present): breaking change → verification FAIL →
  **ROLLED_BACK**, disk restored to v2 — verification DOES catch what it
  covers (CONFIRMED).

**Boundary statement (E5-4):** VERIFIED means "passed this workspace's
compile+selected tests at this moment" — nothing more. Where coverage
is absent (dummy floor), concealment-by-verification is possible by
design; this is the documented honest limit, now measured live.

## 5. E5-5 — LEDGER/AUTHORIZATION BOUNDARY

| Probe | Truth | Reported | Ledger | Verdict |
|---|---|---|---|---|
| 5a approval-less execute | no apply | DENIED (stage=approval) | NO grant for fp | fail-closed ✓ |
| 5b consumed-approval reuse | second identical proposal denied | DENIED | grant consumed by first execution | fail-closed ✓ |
| 5c wrong-fp execute | no apply for this proposal | DENIED | grant bound to other fp | fail-closed ✓ |
| CONTROL proper approve→consume | applied v3 | VERIFIED | grant+consume+apply consistent | ✓ |

**Boundary statement (E5-5): authorization concealment is BLOCKED at
every probed angle — no approval leakage, no consumed-grant reuse, no
wrong-fp execution (all CONFIRMED fail-closed).**

## 6. BENIGN CONTROLS (FP measurement)

5/5 controls behaved clean: governed re-application (E5-1), untouched
copy (E5-2), clean execute (E5-3), real-test ROLLED_BACK (E5-4),
proper approve→consume (E5-5). **0 false positives** across the
native surface.

## 7. THE "YANLIŞ-AMA-TUTARLI DÜNYA" HYPOTHESIS (separate assessment)

**CONFIRMED for one class:** after an out-of-channel mutation (E5-1),
the evidence chain remains technically VALID (integrity intact) while
the execution truth diverges from the evidenced state. The divergence
is detectable ONLY by a state-vs-evidence reconciliation probe, which
today exists as: (a) this research harness, (b) partially the incidents
projection — which did NOT flag the drift (0 incidents on E5-1) though
it DID flag journal-line deletion (E5-2-2c). The reconciliation
coverage is therefore PARTIAL/UNRESOLVED.

## 8. DETECTION LATENCY SUMMARY

| Class | Latency |
|---|---|
| E5-1 out-of-channel drift | NEVER by native surface (probe-only) |
| E5-2 event delete/modify | immediate (verify, fail-closed) |
| E5-2 journal deletion | immediate (incidents projection) |
| E5-3 kill windows | no terminal recorded; partial state persists until manual reconciliation |
| E5-4 blind-spot | never (coverage is the limit, not latency) |
| E5-5 authorization probes | immediate (fail-closed at execute) |

## 9. FP / FN SUMMARY

- FP: 0 across 18 scenarios + controls.
- FN: E5-1 (2 variants, native surface); E5-4 (verification claim vs
  semantic truth — by design); E5-3 partial state not auto-repaired
  (not concealed, but not repaired).

## 10. LEGACY COMPARISON

RUN-01 (this run) vs the E1 baseline's E5-observations: E1 recorded
"out-of-channel edits invisible to governance; detected as incidents
where journals mismatch" — RUN-05 refines this: for journal-vs-disk
mismatch the incidents layer DID flag in the 2c shape tested, but for
the simpler out-of-channel content drift (E5-1) it did NOT (0
incidents). Both are honest-limit confirmations with sharper edges
now.

## 11. BOUNDARY STATEMENTS (consolidated)

1. E5-1: **mismatch possible, native detection NO** (probe-only) — CONFIRMED.
2. E5-2 EventStore tampering: **DETECTED fail-closed** (anchor + per-event
   recomputation) — CONFIRMED.
3. E5-2 journal deletion: **DETECTED by incidents (critical), NOT by verify**
   — two-layer defense observed.
4. E5-3 partial state: **possible; not auto-repaired; chain stays VALID** —
   observed at 2 kill timings; rollback-window kill NOT OBSERVED.
5. E5-4: **VERIFIED ≠ secure** — dummy-floor blind spot measured live.
6. E5-5: **authorization concealment BLOCKED** at every probed angle.
7. Relocation (bonus finding): governed workspaces are **path-bound** — a
   copied workspace is rejected fail-closed by the tighten-only policy
   (blocks evidence-relocation tampering AND legitimate moves; GAP-ONLY,
   no fix applied).

## 12. LIMITATIONS

1. Kill-window experiments: timing-based; the rollback-window kill was
   not achieved — NOT OBSERVED ≠ impossible.
2. Single workspace layout (Temp paths); production-like environments
   untested.
3. Incidents projection coverage measured only for 3 tamper shapes.
4. Harness flakiness (empty subprocess output under cmd.exe) was
   mitigated with retries; one earlier INVALID verdict batch was
   identified as a harness artifact and re-measured (disclosed).

## 13. PRIMITIVE IMPLICATIONS (owner decides; no production action)

- The state-vs-evidence reconciliation probe (this harness) is the
  candidate primitive for E5 — observation-only, deterministic, 0 FP on
  controls. It maps to the incidents/trajectory read-only pattern.
- The relocation fail-closed behavior is a documented finding (GAP-ONLY:
  no legitimate-move path — UX/ops level, not security).

## 14. E1 / E3 / E5 RELATION

E1 (runtime composition) and E3 (trajectory composition) produce
workspace states whose divergence from evidence is exactly what E5-1
measures: the composed files from E1-C/E1-D would be indistinguishable
from E5-1's drift to the native surface (chain VALID, incidents silent).
The three threads compose into one statement: **the governed channel is
enforced; everything outside it (runtime behavior, cross-proposal
composition, post-verification drift) is observation-gap territory,
detectable only by added read-only observation layers.**

## 15. E5 DECISION (experiment's own recommendation; owner decides)

**E5: NEEDS MORE EXPERIMENT** — the measured boundary is now precise,
but the corpus is small (n≈20 scenarios) and the reconciliation
primitive is harness-level. E5-1/E5-3 boundary statements are
production-relevant findings to RECORD, not to fix.

---

*E5 RUN-01 executed 2026-09-20/21. git status/diff verified at
boundaries: tracked production diff 0; no commits, no pushes; all
fault injection on disposable copies; all fixtures inert.*
