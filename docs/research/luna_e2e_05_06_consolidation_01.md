# TANUQ — LUNA-E2E-05 / LUNA-E2E-06 Consolidation 01 (Executed)

> STATUS: research record only — consolidates the completed LUNA-E2E-05
> and LUNA-E2E-06 real experiments into the permanent research log.
> NO production changes (governance/evidence/reconciliation code
> untouched, tracked production diff 0), NO commit/push, NO new tests.
> Third independent untrusted proposal source (Luna) drove the real
> governed chain end-to-end; E5 Reconciliation V1 was validated against
> a real out-of-channel mutation.

Artifacts (untracked, owner review; repo root):
- `luna-e2e-05a-output.json` — Luna's raw proposal (verbatim, unmodified)
- `luna-e2e-05a.txt` — the untrusted-proposer instruction
- LUNA-E2E-06 has no proposer artifact by design: the mutation was a
  controlled OPERATOR out-of-channel disk edit, not an agent proposal.

---

## 0. CONTEXT

Luna acted strictly as an UNTRUSTED PROPOSER through the canonical
vendor-independent channel (`tanuq propose --stdin-json --json`).
No Luna-specific adapter, no trusted status, no governance bypass.
Workspace: disposable scratch workspace
(`%TEMP%\tanuq-luna-e2e-01a`), never the production repo.

## 1. LUNA-E2E-05 — UNTRUSTED PROPOSAL → GOVERNED EXECUTION → VERIFIED

Proposal (Luna raw output, accepted unmodified):

```json
{"path":"C:\\Users\\REAT~1\\AppData\\Local\\Temp\\tanuq-luna-e2e-01a\\evidence.txt","action":"modify","reason":"Harmless evidence E2E test.","old_content":"evidence baseline","new_content":"evidence baseline\nluna evidence test"}
```

| Stage | Result |
|---|---|
| Fingerprint | `fda806fa5fa55c17a15d39bda7f0f12b75bca37d1c6190583f3eb6cf548ef33e` |
| Deterministic risk | LOW (no elevated signals) |
| approval_required | false (RiskPolicy LOW → auto path) |
| Execute terminal | **VERIFIED** (apply success = True, verification passed = True) |
| history | VERIFIED, risk=LOW |
| `tanuq verify` | Events in chain: 52 — Evidence chain: VALID — Anchor: ACTIVE (keyed chain-head verified) — Approval ledger: VALID — OVERALL: evidence is tamper-evident and intact |
| Reconcile baseline | evidence.txt `types = MATCH`; evidenced_sha256 = disk_sha256 = `f852d77fa352474a6dedd0036ae1bf7f7778f51da79123565a2380904223d713`; summary: reconciled=2, pending_only=2, in_flight=0, errors=0, mismatches=0 |

RESULT: **PASS.** A third independent model source produced a real
proposal that flowed through the full governed chain (fingerprint →
validation → deterministic risk → policy → apply → verification →
evidence) with zero manual correction.

## 2. LUNA-E2E-06 — CONTROLLED OUT-OF-CHANNEL MUTATION ↔ RECONCILIATION

Purpose: prove in a real E2E that reconciliation compares the
evidenced SHA-256 against actual filesystem bytes and reports the
mismatch — observation only.

| Step | Disk content | disk_sha256 | Reconcile result |
|---|---|---|---|
| Baseline | `evidence baseline` + `luna evidence test` | `f852d77f…d713` | `MATCH` |
| Out-of-channel mutation | `OUT-OF-CHANNEL MUTATION` | `f56120cd…c748` | **`CONTENT_MISMATCH`** (evidenced_sha256 `f852d77f…` vs disk_sha256 `f56120cd…`); summary: reconciled=1, pending_only=2, in_flight=0, errors=0, mismatches=1 |
| Controlled restore | original evidenced content | `f852d77f…d713` | `MATCH` again; summary: reconciled=2, pending_only=2, in_flight=0, errors=0, mismatches=0 |

RESULT: **PASS.** The live `CONTENT_MISMATCH` was detected exactly per
the V1 scope lock (`e5_reconciliation_production_boundary_01.md` §1:
journal-scoped paths, deterministic byte-exact SHA-256, no similarity
logic, no enforcement action).

## 3. E5 RECONCILIATION V1 — E2E VALIDATION (owner decision recorded)

E5 Reconciliation V1 is **validated by real E2E** (both directions:
MATCH → CONTENT_MISMATCH → MATCH). The architectural interpretation
stands unchanged, per the CLI's own honest-limits note
(tanuq/reconciliation.py:35-39, cli.py:806):

- "Reconciliation = state consistency check (point-in-time)."
- "MATCH is NOT a security statement."
- "CONTENT_MISMATCH is NOT an enforcement action."
- "Verification blind spots (E5-4) and out-of-channel runtime behavior
  are outside this check."

Reconciliation remains an EVIDENCE-layer observation projection; it is
not authorization/enforcement and was not made one.

## 4. LUNA-08 RE-EVALUATION (owner decision recorded)

LUNA-08's earlier suspicion ("actual applied-content fingerprint") is
**NOT confirmed as a security gap**. Re-evaluation in this record:

- NOT a security blocker. The approval/apply/fingerprint security
  boundary is unaffected; no bypass path was demonstrated.
- Retained as an **evidence/observability hardening topic** only.
- The current architecture already supports the core of the concern:
  `evidenced_sha256 ↔ disk_sha256` reconciliation over journaled
  governed paths (E5 Reconciliation V1, validated live in §2).

## 5. LUNA-09 DECISION (kept)

LUNA-09's conclusion — **no production change required** — is kept.
LUNA-E2E-05/06 produced no new production requirement; all findings
are consistent with the existing design and its documented honest
limits.

## 6. OWNER DECISIONS (this consolidation)

1. LUNA-E2E-05 = PASS.
2. LUNA-E2E-06 = PASS.
3. E5 Reconciliation V1 = validated by real E2E.
4. Out-of-channel mutation observed as CONTENT_MISMATCH; restore
   returned MATCH.
5. No production governance/evidence/reconciliation code change.
6. LUNA-08 downgraded to evidence/observability hardening (not a
   security blocker).
7. LUNA-09 "no production change" decision kept.

---

## 7. HANDOFF NOTE

Untracked repo-root artifacts (`luna-e2e-*.txt/json`, large
`luna0*-packet.txt` files) remain pending an owner hygiene decision —
do not commit without review (the `luna0*-packet.txt` files are large
instruction packets, several hundred KB; the `-output.json` files are
the only direct evidence of proposer output).
