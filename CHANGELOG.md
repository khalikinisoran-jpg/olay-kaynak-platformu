# CHANGELOG

All notable changes to this project will be documented here.

---

# v0.6.0 (UNRELEASED — release candidate)

Status

TANUQ Release Foundation

Highlights

- Product identity migration: the product is now **TANUQ** (package
  import name `tanuq`, CLI `tanuq`, runtime dirs `.tanuq` / `~/.tanuq`,
  auth header `X-TANUQ-Token`). Distribution name stays
  `event-sourced-ai-runtime`. Controlled, secret-safe legacy migration
  from `.hermes` layouts is included (rename-only, fail-closed).
- Product shell over the proven governance core: `tanuq init / status /
  workspace / propose / approve / execute / history / lineage /
  incidents / verify / token / ui / export`.
- Governed-by-default runtime with anchored (HMAC) evidence chains by
  default; single-use, fingerprint-bound human approvals (TTL 3600s).
- Session labels, explainable governance (deterministic risk signals),
  multi-process safe pending store, incident center (detect-only,
  recovery ≠ authorization), evidence export bundle.
- Packaging regression gate: wheel → clean venv → product smoke
  (Ubuntu + Windows) as a CI job.

### Recent additions (unreleased)

- Governed `create` action: new-file creation through the same
  proposal/governance/approval/verification chain (always HIGH risk,
  human approval required; no directory-creation authority).
- Claude Code adapter: Edit is governed as `modify`, Write as
  `create` (translation-only vendor adapter, documented contract).
- UX fixes: propose-time stale `old_content` warning; DENY guidance
  now carries the real validator reason; history shows
  `denied_reason`.
- Version metadata fix: `tanuq --version` reports the packaging
  version (0.6.0) instead of a hard-coded value.
- Agent working procedure: `AGENTS.md` + `docs/TANUQ_SKILL.md`.
- Docs: honest-limitations section in the user guide; docs
  entry-point chain consolidated to the current truth-source.
- Cross-model dogfood: the generic proposal channel verified with an
  independent non-Claude model source.

Known gaps

- No OS sandbox and no network enforcement (by design; documented).
- Vendor integrations are verified per agent: Claude Code Edit/Write
  is governed and shipped; other agents use the generic hook
  protocol (runtime payload observation for Claude Write pending).
- Verification is Python-focused (compileall + pytest).

---

# v0.1.0-alpha

Release Date

2026-08-05

Status

Stable Core

## Added

- Event Store
- Replay Engine
- Snapshot Support
- Context Builder
- AI Runtime
- Timeline Inspector
- Global Sequence Engine
- Hash Chain
- Verify Chain
- Loop Engine Foundation

## Documentation

- README
- PROJECT_CONTEXT
- IDEAS
- MILESTONE

## Git

Tag

v0.1.0-alpha

---

# v0.2.0-alpha

In Development

Planned

- Loop Lifecycle Events
- Event Query Engine
- Decision Trace
- Worker Runtime