# CHANGELOG

All notable changes to this project will be documented here.

---

# v0.6.0 (UNRELEASED — release candidate)

Status

TANUQ Release Foundation — release preparedness in progress: license
layer prepared in-tree (Apache-2.0 `LICENSE` + aligned metadata,
2026-09-28). Still **UNRELEASED**: no git tag, no PyPI publication,
no release date assigned yet.

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
- Usage-signal stack (FAZ 1 / 2.1 / 2.2): local anonymous usage-signal
  derivation (`tanuq/usage_signal.py`, `ed1c6c5`); opt-out preference
  plus `tanuq usage on|off|status` (ENV > config > default ON,
  `c48e786`); HTTPS-only, fail-silent remote transport
  (`tanuq/usage_transport.py`, `c48e786`) — **no remote endpoint
  ships**, so transport stays a no-op until an owner-provided endpoint
  exists.
- FREE distribution strategy + feedback channel: the site presents
  TANUQ as free-to-use (no account / no payment / no subscription;
  `b5841f9`) and intake is a real mailbox, `mailto:feedback@tanuq.net`,
  in English and Turkish (`7d7ee8a`, `e7c1174`); earlier pricing claims
  were removed.
- Quickstart fix: the new-file example now carries `"action": "create"`
  so the documented first-run flow follows the HIGH-risk create path
  (`45e3072`).
- F1 FREE E2E local validation: **PASS** (recorded 2026-09-28 in
  `docs/TANUQ_PROJECT_STATE.md` as an in-session validation result;
  no in-repo artifact by design).

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