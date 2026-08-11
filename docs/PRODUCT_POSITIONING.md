# PRODUCT_POSITIONING.md

Product positioning derived strictly from the current technical reality
(branch `worker-action-pipeline` @ `96ed72d`, 2026-08-11; limitation #1
refreshed by the MISSION-011 close-out on 2026-08-12). Marketing claims
that cannot be proven from code/tests are explicitly marked UNVERIFIED.

---

## 1. Product Definition

**What it is today (VERIFIED from code):**
An event-sourced AI runtime prototype with:
- an append-only, SHA-256 hash-chained event store and deterministic
  replay/recovery (`simulation/persistence/event_store.py`,
  `simulation/recovery/recovery_engine.py`);
- a CLI chat runtime (`agent_run.py`) that routes input through a planner
  and a dispatcher of executors (calculator, memory store/recall, LLM,
  worker);
- a worker agent that reads in-scope files and produces patch proposals,
  optionally through a real LLM (OpenRouter/DeepSeek);
- a deterministic apply/verify pipeline with bounded recovery — active
  only when explicitly enabled (`--recovery`);
- a documented security model with executable adversarial tests
  (docs/SECURITY_MODEL.md, tests/security/adversarial_corpus_test.py).

**What it is not (VERIFIED):** a productized, packaged, deployed, or
externally validated platform. There is no production configuration, no CI
pipeline, no packaging, no API service, no multi-user story.

---

## 2. Target Problem

The problem the project states it solves (docs/PRODUCT_VISION.md,
VISION.md, README.md):
- AI applications usually store only the latest output and cannot explain
  why a decision was made, which inputs influenced it, or whether it can
  be replayed/verified/audited.
- The project's answer: treat every meaningful AI action as an immutable,
  hash-chained event; constrain AI proposals with deterministic
  validation/authorization/application/verification layers; preserve
  evidence.

**Evidence the problem is real for this project:** the codebase implements
the full replay/verify/evidence machinery (VERIFIED). **Evidence the
problem exists in the market is UNVERIFIED** — no market research,
customer interviews, or external validation exists in the repository
(ROADMAP.md Phase 14 "External Validation" is future work).

---

## 3. Differentiators (what the code actually does differently)

| Differentiator | Evidence | Claim class |
|----------------|----------|-------------|
| Every decision becomes a hash-chained event; chain verified from GENESIS | EventStore + HashVerifier; adversarial A11 | VERIFIED |
| Worker proposals are constrained by deterministic gates (validator -> controller -> apply -> verify), not by the LLM | WorkerActionPipeline; MISSION-003..010 | VERIFIED |
| Apply is never active by default (proposal-only default runtime) | agent_run.py; worker_runtime_test.py | VERIFIED |
| Apply success is structurally separated from verification success | ApplyVerifyPipeline; A08/A09 | VERIFIED |
| Retry/self-modification is hard-bounded (max 3, no recursion, duplicate suppression) | BoundedRecoveryEngine; A10 | VERIFIED |
| Evidence payloads are secret-safe (fingerprints only) | WorkerEvidenceRecorder; worker_evidence_test.py | VERIFIED |
| Live-LLM integration is gated and fail-closed (timeout, ProviderError, no secret logging) | MISSION-003; llm_provider_test.py | VERIFIED |
| Adversarial security corpus as executable, summary-gated tests | tests/security/adversarial_corpus_test.py | VERIFIED |

**Untested/marketing differentiators (UNVERIFIED):**
- "Enterprise-grade" (docs/PROJECT_STATE.md) — no enterprise features exist.
- "Provider agnostic" beyond OpenRouter — only one provider implemented.
- Any performance advantage — no benchmarks exist.

---

## 4. Limitations (VERIFIED from code)

1. **Risk engine (MISSION-011) is tested but opt-in:** deterministic
   RiskEngine/RiskPolicy/RiskLevel (83 tests) but the gate activates only
   when explicitly wired; the shipped assembly stays gate-off until the
   human-approval store exists (MISSION-012, D-021).
2. **Human approval boundary missing:** `approval_store` is a contract with
   no implementation.
3. **No production/deployment story:** no CI, packaging, config system,
   logging/metrics, or deployment profiles (docs/ROADMAP.md Phase 2/3 are
   future).
4. **Single-process, single-user CLI only.**
5. **No concurrency/multi-agent testing; no benchmarks.**
6. **`weather` strategy is planned but unroutable** (no registered
   executor).
7. **Live-LLM end-to-end (apply/verify/recovery) untested.**
8. **Symlink behavior untested on OSes without symlink privileges**
   (junction variants cover Windows).
9. **Docs drift:** README/CHANGELOG/PROJECT_CONTEXT describe older versions.
10. **Repository hygiene:** tracked `.pyc` artifacts, junk files
    (`git`, `kernel.txt`), stray Turkish-named empty directories under
    simulation/.

---

## 5. Competitor Claims Requiring Verification

These are claims the project might eventually make; none are currently
substantiated by evidence in the repository. Each requires external
validation before use in any product claim (ROADMAP.md Phase 14):

| Claim to verify | Current evidence | Required validation |
|-----------------|------------------|---------------------|
| "Built-in AI audit trail" | Hash-chained event log exists | Independent audit; compare to competitor audit offerings; define what "audit-grade" means |
| "Deterministic replay of AI execution" | Replay engine + tests | Benchmarks at 1k/10k/100k events; distributed/replay semantics; adversarial scenarios |
| "Verifiable AI code modification" | Apply/verify/recovery pipeline | Real-LLM end-to-end verification evidence; restore correctness under crash |
| "Provider-agnostic" | BaseProvider ABC + OpenRouter only | Verified adapters for >=2 real providers; parity tests |
| "Enterprise ready" | None | No enterprise deployment exists |
| "Faster/safer than existing agent frameworks" | None | Comparative benchmarks against named products (CrewAI/AutoGen/LangGraph/etc. as named candidates — NOT yet compared) |
| Compliance certifications (SOC2/GDPR/etc.) | None | ROADMAP.md Phase 14 explicitly defers compliance claims to authoritative sources |

**Positioning statement that is FAIRLY SUPPORTED today (INFERRED):**
"An experimental, testable event-sourced runtime for constraining,
verifying and auditing AI code-modification proposals — currently at
proof-of-concept maturity, with its security model defined as executable
tests." Anything stronger (platform, product, enterprise) is premature.
