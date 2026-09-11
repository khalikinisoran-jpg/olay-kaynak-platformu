# AGENTS.md — TANUQ

Instructions for AI coding agents working on this repository.

**Start here: read `docs/TANUQ_SKILL.md` (project skill) and
`docs/TANUQ_PROJECT_STATE.md` (current position) before any task.**

Critical rules (full list in the skill — violating any of these is a
stop-and-report event, not a judgment call):

1. `docs/TANUQ_PROJECT_STATE.md` is the current position: read it,
   then verify git HEAD/origin/CI against it. Contradiction → stop.
2. Frozen boundaries: fingerprint semantics, approval semantics,
   risk engine/policy, canonical action set (`modify`, `create` only),
   operation_id (never add), FAZ 7/9, Unified Runtime, `p5/` +
   `agent_run.py` legacy assemblies. Do not touch; reopening any
   requires evidence + a human gate.
3. Vendor adapters are translation-only: never return "allow", never
   write files, never decide risk, never grant approvals. New vendor =
   new adapter module; canonical core diff must be zero.
4. Never invent vendor payloads or evidence. Label every claim:
   CONFIRMED / VENDOR DOCUMENTED / INFERRED / UNKNOWN / BLOCKED.
5. Never commit `child_*.dmp` (real secrets), `_dbg_*`, `_diag*`,
   `dist/`, `t`, `request.json`, or any debug/temp artifact.
6. G1: do not modify existing test modules — add NEW test modules.
7. No speculative abstraction. No new authority. No new mutation
   writer. Fail-closed everywhere.

Full working procedure (resync, change discipline, stop rules,
evidence discipline, report format, BDP): `docs/TANUQ_SKILL.md`.

Skill instructs the agent; TANUQ governance controls mutations.
