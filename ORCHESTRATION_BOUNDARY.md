# TANUQ — ORCHESTRATION BOUNDARY

> **Amaç:** FAZ 2/2b tamamlandıktan sonra, `OperationCoordinator` katmanının
> tam olarak nereye oturacağını, mevcut authority/evidence sınırlarını bozmadan
> belirlemek. Bu doküman **diagnosis + mapping** çıktısıdır; production
> koduna dokunulmamıştır.

---

## 1. Executive Summary

TANUQ'ta orchestration üç giriş yüzeyinden (CLI, Web UI, Agent Adapter) aynı
governed pipeline'a akar. **Authority tamamen `simulation/security/` +
`simulation/agent/approval/` katmanlarındadır;** CLI/Web/Coordinator yalnızca
delegation yapar. Fingerprint üretimi `simulation/agent/worker/`'dedir.
Evidence, dört hash-chained journal + EventStore'dadır.

FAZ 2/2b ile CLI ve Web execute yolları `OperationCoordinator.execute()`
üzerinden geçer. Agent Adapter hâlâ `agent_adapter.py` üzerinden doğrudan
governed pipeline'a gider (Coordinator katmanı henüz agent_adapter'da
bağlanmadı — `Phase 3 / Faz 2b sonrası` için net başlangıç noktasıdır).

---

## 2. Repository-Verified Current Flow

```text
[GERÇEK REPOSITORY AKIŞI — birebir, dosya+fonksiyon kanıtlı]

ENTRY POINTS
  ├── tanuq/cli.py :: cmd_execute → OperationCoordinator.execute
  ├── tanuq/web.py :: _execute → OperationCoordinator.execute
  └── tanuq/claude_code_adapter.py :: handle_pretooluse (vendor adapter)
        ↓
tanuq/agent_adapter.py :: agent_adapter.execute
        ↓
OperationCoordinator.execute (tanuq/coordinator.py)
        ↓
GovernanceEvaluator.evaluate (simulation/security/governance_evaluator.py)
  ├── RiskEngine.classify (simulation/security/risk_engine.py)
  └── RiskPolicy.decide (simulation/security/risk_policy.py)
        ↓
WorkerActionPipeline.execute (simulation/agent/pipeline/worker_action_pipeline.py)
  ├── PatchValidator.validate (simulation/agent/worker/patch_validator.py)
  ├── [Governance decision → requires_human?]
  │     └── ApprovalStore.find_valid (simulation/agent/approval/approval_store.py)
  ├── Controller.approve (simulation/agent/controller/controller.py)
  ├── ApplyAuthorization.authorize (simulation/agent/apply/apply_authorization.py)
  │     └── ApplyExecutor.apply (simulation/agent/apply/apply_executor.py)
  │           ├── ApplyOutcomeJournal.record_intent (simulation/agent/apply/apply_outcome_journal.py)
  │           ├── FileApplier.apply (simulation/agent/apply/file_applier.py)
  │           └── ApplyOutcomeJournal.record_applied
  ├── VerificationExecutor.verify (simulation/agent/verify/verification_executor.py)
  │     ├── compileall subprocess (CommandRunner.run, simulation/agent/verify/command_runner.py)
  │     └── pytest subprocess (CommandRunner.run)
  ├── [verification FAIL → FileApplier.restore → ROLLED_BACK]
  └── ApplyOutcomeJournal.record_verified / record_rolled_back
        ↓
Evidence layer:
  ├── EventStore.append (simulation/persistence/event_store.py) — hash chain + ChainAnchor
  ├── ApplyOutcomeJournal (simulation/agent/apply/apply_outcome_journal.py) — hash chain
  ├── ApprovalLedger (simulation/agent/approval/approval_ledger.py) — hash chain + anchor
  └── ExternalOutcomeJournal (simulation/agent/apply/external_outcome_journal.py) — hash chain
```

---

## 3. Entry Points

| Entry Point | Dosya | Fonksiyon | Coordinator üzerinden mi? |
|---|---|---|---|
| CLI `tanuq execute` | `tanuq/cli.py` | `cmd_execute` | **Evet** — `OperationCoordinator.execute(fingerprint, run_all, session)` (Faz 2b) |
| CLI `tanuq propose` | `tanuq/cli.py` | `cmd_propose` | **Evet** — `OperationCoordinator.propose` (Faz 2c; cli.py:129) |
| Web `POST /api/execute` | `tanuq/web.py` | `_execute` | **Evet** — `OperationCoordinator.execute(fingerprint, run_all, session)` (Faz 2b) |
| Web `POST /api/propose` | `tanuq/web.py` | `_propose` | **Evet** — `OperationCoordinator.propose` (Faz 2c; web.py:335-343) |
| Claude Code PreToolUse | `tanuq/claude_code_adapter.py` (untracked kod) | `handle_pretooluse` | **Kısmen** — propose doğrudan `agent_adapter.propose`; execute `OperationCoordinator.execute(fingerprint)` (adapter kodu mevcut, henüz commit edilmedi) |
| CLI `tanuq approve` | `tanuq/cli.py` | `cmd_approve` | **Hayır** — doğrudan `agent_adapter.approve` (governance kararını yeniden değerlendirir, authority hâlâ ApprovalStore'da) |
| Web approve | `tanuq/web.py` | `_approve` | **Hayır** — doğrudan `agent_adapter.approve` (approve act = insan yetkilendirmesi; authority ApprovalStore'da) |
| p5 demo UI `/api/propose` `/api/approve` `/api/execute` | `p5/server.py` | `_handle_propose/_approve/_execute` | **Hayır — AYRI assembly** (aşağıda) |
| `agent_run.py --governed` / `apply` | `agent_run.py` | governed runtime | **Hayır — AYRI assembly** (aşağıda) |

**Ayrı mevcut assembly'ler (hata veya bypass DEĞİL — mimari kararı bekleyen mevcut gerçeklik):**

```text
# Tanuq product orchestration path (Coordinator üzerinden):
CLI / tanuq web / (claude adapter) → OperationCoordinator → agent_adapter
                                    → WorkerActionPipeline (tanuq/runtime stores)

# p5 / agent_run — aynı simulation primitive'lerini kullanan BAĞIMSIZ
# assembly'ler; kendi EventStore/Journal/pending/dummy'leri var,
# OperationCoordinator ve agent_adapter KULLANMAZLAR:
p5/server.py     → _build_pipeline → kendi WorkerActionPipeline'ı
                   (kendi pending'i, kendi test_p5_dummy.py verification'ı)
agent_run.py     → kendi governed WorkerActionPipeline assembly'si
                   (--governed; kendi data dir: <ws>/.cli_platform)
```

Bu iki assembly'nin product orchestration path'ine bağlanacağı, dışarıda
ayrı runtime olarak kalacağı veya emekli edileceği bir **mimari karardır**
ve bu dokümanda KARAR VERİLMEMİŞTİR. Güvenlik sınırları her assembly
içinde ayrı ayrı korunur (aynı primitive'ler: GovernanceEvaluator,
ApprovalStore, ApplyAuthorization, VerificationExecutor, hash-chained
journal'lar); ancak "tek orchestration giriş noktası" iddiası bugün
yalnızca Tanuq product path için doğrudur.

**Sonuç:** Execute VE Propose yolları Faz 2b/2c ile Coordinator'a bağlandı.
Approve bilinçli olarak dışarıdadır (insan yetkilendirme act'ı; authority
ApprovalStore'da). p5 ve agent_run ayrı assembly'lerdir (yukarıda).

---

## 4. Governance Boundary

```text
tanuq/agent_adapter.py :: agent_adapter.propose / execute
        ↓
GovernanceEvaluator.evaluate (simulation/security/governance_evaluator.py:152)
  ├── RiskEngine.classify (simulation/security/risk_engine.py:368)
  └── RiskPolicy.decide (simulation/security/risk_policy.py:64)
        ↓
GovernanceDecision → {allowed, requires_human, max_attempts, verification_depth}
        ↓
WorkerActionPipeline.execute (simulation/agent/pipeline/worker_action_pipeline.py:355)
  → stage VALIDATION → PatchValidator (simulation/agent/worker/patch_validator.py)
  → stage RISK → GovernanceEvaluator (yeniden değerlendirme YOK; aynı decision)
  → stage APPROVAL → ApprovalStore.find_valid (simulation/agent/approval/approval_store.py:289)
  → stage CONTROLLER → Controller.approve (simulation/agent/controller/controller.py:18)
  → stage APPLY_VERIFY → ApplyVerifyPipeline (simulation/agent/pipeline/apply_verify_pipeline.py)
```

**Authority:**
- `GovernanceEvaluator.evaluate` → governance kararını ÜRETEN tek otorite
- `ApprovalStore.find_valid/grant/revoke` → approval authority
- `ApplyAuthorization.authorize` → apply-boundary authority (yeniden kontrol)
- CLI/Web/Coordinator/AgentAdapter → **authority YOK** — sadece delegation

---

## 5. Execution Boundary

| Fonksiyon | Dosya | Roll |
|---|---|---|
| `WorkerActionPipeline.execute` | `simulation/agent/pipeline/worker_action_pipeline.py:355` | 5-stage governed funnel |
| `ApplyExecutor.apply` | `simulation/agent/apply/apply_executor.py:69` | journal + authorization + FileApplier |
| `FileApplier.apply` | `simulation/agent/apply/file_applier.py` | mkstemp+fsync+os.replace+read-back |
| `FileApplier.restore` | `simulation/agent/apply/file_applier.py` | rollback (authorized=True gate) |
| `VerificationExecutor.verify` | `simulation/agent/verify/verification_executor.py:122` | compileall -f + pytest subprocess |
| `ApplyVerifyPipeline.execute` | `simulation/agent/pipeline/apply_verify_pipeline.py` | apply→verify→rollback binding |

**Authority:** `ApplyAuthorization.authorize` (apply-boundary); `VerificationExecutor`
fail-closed (timeout/non-zero → FAIL → ROLLED_BACK).

### 5a. Verification Reality per Assembly (related-tests-v1)

Doğrulama semantic'i assembly'ye göre farklıdır — bu bir dokümante edilmiş
gerçektir:

```text
Tanuq product path (7525c66 sonrası):
  agent_adapter.execute → tanuq/verification_profile.py
  → related-tests-v1 (gerçek workspace testleri, symlink-contained,
    dummy_floor fallback) → VerificationExecutor (pass/fail authority)

p5/server.py:
  kendi verification assembly'si — dd/test_p5_dummy.py (p5/server.py:568)
  → kendi VerificationExecutor örneği

agent_run.py:
  kendi verification assembly'si — kendi dummy/target seçimi
```

`related-tests-v1` YALNIZCA Tanuq product path'te kullanılır. p5 ve
agent_run kendi dummy tabanlı verification'larıyla çalışmaya devam eder.
VerificationExecutor her üç assembly'de de tek pass/fail authority'dir;
`-p no:cacheprovider` ve timeout semantiği ortaktır. Herhangi bir assembly'nin
profile'a geçirilmesi ayrı bir görevdir — bu dokümanda karar/kapsam YOK.

RT-1 integrity katmanı (7525c66 sonrası, product path): (R1) aynı
execution'ın patch hedefi olan aday dosyalar verification target'ı
olamaz; (G1) MEVCUT bir test modülünü değiştiren patch, Governance
Core içindeki bir risk sinyaliyle HIGH'e yükseltilir ve insan onayı
gerektirir (Human=AUTHORIZATION; verification layer'a authority
TAŞINMAZ). Authority haritası değişmemiştir.

---

## 6. Evidence Boundary

| Store | Dosya | Format | Hash-chain | Anchor |
|---|---|---|---|---|
| EventStore | `simulation/persistence/event_store.py` | JSONL | ✓ SHA-256 | ✓ ChainAnchor (HMAC, opt-in) |
| ApplyOutcomeJournal | `simulation/agent/apply/apply_outcome_journal.py` | JSONL | ✓ SHA-256 | yok (EventStore'ta) |
| ApprovalLedger | `simulation/agent/approval/approval_ledger.py` | JSONL | ✓ SHA-256 | ✓ ChainAnchor (opt-in) |
| ExternalOutcomeJournal | `simulation/agent/apply/external_outcome_journal.py` | JSONL | ✓ | — (spike) |
| ChainAnchor | `simulation/persistence/chain_anchor.py` | JSONL | — | HMAC-SHA256 |

---

## 7. Approval Boundary

- **State:** `ApprovalStore` (in-memory + ApprovalLedger persistence)
- **Pending:** `tanuq/pending.py` — `pending_proposals.json` (RAM + workspace dosyası)
- **Grant:** `ApprovalStore.grant` — tek kullanımlık, fingerprint-bound, TTL 3600s
- **Consume:** `ApprovalStore.find_valid` + `authorize_apply` — cross-process lock
- **Approve eden:** insan (CLI `tanuq approve` veya Web UI) — **Agent/LLM'in approval authority'si yok**
- **In-flight:** `OperationCoordinator._in_flight` (RAM-only, Faz 2) — kalıcı değil

---

## 8. Fingerprint Boundary

- **Üretim:** `PatchProposal.fingerprint()` (simulation/agent/worker/patch_proposal.py:16) — SHA-256(canonical JSON, reason dahil)
- **Doğrulama:** `PatchValidator.validate` (scope); `ApprovalStore.find_valid` (5-tuple match); `ApplyAuthorization.authorize` (apply-boundary re-check)
- **Coordinator kullanımı:** sadece reference — fingerprint üretimi/değişimi Coordinator'da YOK

---

## 9. Authority Map

```text
Agent / LLM (UNTRUSTED)
    │ proposal (content, not authority)
    ▼
CLI / Web / AgentAdapter (TRANSLATION ONLY — authority YOK)
    │ delegation
    ▼
OperationCoordinator (COORDINATION — authority YOK)
    │ delegation
    ▼
GovernanceEvaluator (AUTHORITY — governance decision)
    │
    ▼
ApprovalStore (AUTHORITY — approval grant/consume/revoke)
    │
    ▼
ApplyAuthorization + ApplyExecutor + FileApplier (AUTHORITY — apply-boundary)
    │
    ▼
VerificationExecutor (AUTHORITY — pass/fail)
    │
    ▼
Evidence: EventStore + ApplyOutcomeJournal + ApprovalLedger + ChainAnchor
    (TRUTH — tamper-evident, fail-closed)
```

**Kural:** Coordinator hiçbir authority method'u çağırmaz (`grant`, `consume`,
`revoke`, `apply`) — yalnızca `agent_adapter.execute`'i delege eder.

---

## 10. Side-Effect Map

| Bileşen | FS yan etkisi | Subprocess | Journal/Event |
|---|---|---|---|
| `FileApplier.apply` | ✓ os.replace + fsync + read-back | — | ✓ journal APPLIED |
| `VerificationExecutor.verify` | ✓ (ws __pycache__ yazımı) | ✓ compileall + pytest | — (EventStore'ta) |
| `ApplyExecutor.apply` | ✓ (FileApplier) | — | ✓ INTENT/APPLIED |
| `ApplyExecutor.rollback` | ✓ (FileApplier.restore) | — | ✓ ROLLBACK_* |
| `EventStore.append` | ✓ events.jsonl + fsync | — | ✓ hash-chain |
| `OperationCoordinator` | — (FS yazımı YOK) | — (subprocess YOK) | — |
| `claude_code_adapter` | — (FS yazımı YOK) | — | ✓ propose evidence |

---

## 11. Current Responsibility Distribution

| Sorumluluk | Mevcut Bileşen | Dosya/Fonksiyon | Authority sahibi | Coordinator'a taşınabilir mi? |
|---|---|---|---|---|
| Proposal registration | `agent_adapter.propose` | tanuq/agent_adapter.py | Hayır (pending kaydı) | Kısmen — `coordinator.propose()` wrapper olabilir (opsiyonel) |
| Governance delegation | `GovernanceEvaluator.evaluate` | simulation/security/governance_evaluator.py | **Evet** — GovernanceEvaluator | Hayır — core authority |
| Approval waiting | `ApprovalStore.find_valid` | simulation/agent/approval/approval_store.py | **Evet** — ApprovalStore | Hayır — core authority |
| Execution orchestration | `OperationCoordinator.execute` | tanuq/coordinator.py | Hayır — delegation | **Zaten burada** (Faz 2) |
| Verification observation | `VerificationExecutor.verify` | simulation/agent/verify/verification_executor.py | **Evet** — fail-closed | Hayır — core authority |
| Failure handling | `ApplyVerifyPipeline.execute` + `FileApplier.restore` | simulation/agent/pipeline/apply_verify_pipeline.py | Hayır — pipeline davranışı | Hayır — core authority |
| Lifecycle exposure | `tanuq/evidence.py::operations` + `lineage` | tanuq/evidence.py | Hayır — salt-okunur projection | **Evet** — zaten coordinator üzerinden erişilebilir |

---

## 12. OperationCoordinator Boundary Recommendation

**Coordinator YALNIZCA şu katmanda olmalı:**

1. **Execute orchestration:** `OperationCoordinator.execute` → `agent_adapter.execute`
   (governed pipeline'ı delege eder, in-flight RAM slot yönetir) — **ZATEN MEVCUT**
2. **Projection facade:** `operations()`, `lineage()`, `incidents()`, `export()`,
   `status()` — salt-okunur, authority YOK — **ZATEN MEVCUT**
3. **Propose delegation:** `coordinator.propose()` →
   `agent_adapter.propose()` — pending kaydı zaten delegate edilir
   — **ZATEN MEVCUT (Faz 2c; coordinator.py:112-120, cli.py:129,
   web.py:335-343)**

**Coordinator AŞAĞIDAKİLERE ASLA DOKUNMAMALI:**
- `ApprovalStore.grant/consume/revoke` (governance authority)
- `ApplyAuthorization.authorize` (apply-boundary)
- `FileApplier.apply/restore` (execution authority)
- `GovernanceEvaluator.evaluate` (governance decision)
- `PatchProposal.fingerprint()` (canonical identity)

**Nerede başlamamalı:** `simulation/**`, `p5/**`, core pipeline'ların içinde.
`tanuq/coordinator.py` mevcut sınırla (tanuq/ kabuğu) doğru yerdedir.

---

## 13. Operation Model Readiness

| Kavram | Mevcut karşılık | Dosya/Object | Durum |
|---|---|---|---|
| `operation_id` | `ApplyOutcomeJournal` intent_id | apply_outcome_journal.py | ✓ VAR (journal'da üretilir) |
| `session_id` | pending record `session` + evidence `task_id` | tanuq/pending.py + worker_evidence_recorder | ✓ VAR (RAM + workspace dosyası) |
| `fingerprint` | `PatchProposal.fingerprint()` | patch_proposal.py:16 | ✓ VAR (canonical SHA-256) |
| `proposal metadata` | `pending_proposals.json` + journal intent payload | tanuq/pending.py | ✓ VAR |
| `approval reference` | `ApprovalLedger` approval_id + journal `approval_id` | approval_ledger.py | ✓ VAR |
| `created sequence` | `EventStore.sequence` | event_store.py | ✓ VAR |
| `current lifecycle state` | `tanuq/evidence.py::operations[].state` | tanuq/evidence.py | ✓ VAR (PROPOSED/PENDING_APPROVAL/VERIFIED/ROLLED_BACK/DENIED/INCIDENT) |
| `rollup/exposure` | `tanuq/coordinator.py::operations()` + `status()` | tanuq/coordinator.py | ✓ VAR (Faz 2/2b) |
| `in-flight state` | `OperationCoordinator._in_flight` (RAM) | tanuq/coordinator.py | ✓ VAR (Faz 2; kalıcı değil, tasarımla) |

**Eksik kavram: YOK** — mevcut projection'lar Operation model için yeterli.
Yeni bir audit store/database gerekmemektedir.

---

## 14. Windows Verification Reliability Note

```text
KNOWN RELIABILITY ISSUE
Platform: Windows (lokal)
Context:  TANUQ runtime parent + execute flow + verification pytest child
Symptom:  child exit intermittent delay (bazı koşumlarda >120s timeout)
State:    child yaşlıyor (WaitForSingleObject → WAIT_TIMEOUT),
          CPU ≈ 0, Wait/UserRequest, HandleCount ~130–137 sabit
Mechanism: UNCONFIRMED (py-spy DLL hatası; CIM aralıklı arızalı)
Security:  fail-closed korunuyor — timeout → FAIL → ROLLED_BACK
           yanlış VERIFIED: 0 koşum
Production fix: uygulanmadı (root cause UNCONFIRMED)
Trigger hypothesis: TANUQ execute akışı + chdir(ws) + PIPE'lı child
           (bileşen matrisi çelişkili; izole koşum EXITED)
Status:    FAZ 1 boundary mapping'i BLOKE ETMEZ
```

---

## 15. Unconfirmed / Ambiguous Areas

1. **Windows child-hang mekanizması** — UNCONFIRMED (bkz. §14); fail-closed korunduğu için güvenlik etkisi sınırlı
2. **~~Propose'un Coordinator'a bağlanması~~** — **ÇÖZÜLDÜ (Faz 2c):** CLI ve web propose artık `Coordinator.propose` üzerinden geçiyor (cli.py:129, web.py:335-343); approve bilinçli olarak ApprovalStore authority'sinde kalıyor
3. **`ExternalOutcomeJournal`** — spike durumunda (production deployment yok)
4. **`ExternalActionPipeline`** — governed spike; gerçek external provider mevcut değil
5. **Ubuntu hosted-CI'da P8/P96** — compileall `-f` fix @9e646fb sonrası yeşil; Windows lokal child-hang ile ilişkisi UNCONFIRMED
6. **Claude Code adapter** — kod mevcut (untracked); propose doğrudan `agent_adapter`, execute `Coordinator.execute`; commit kararı operatöre ait — Operation Model IMPLEMENTED DEĞİL, WAIT/RESUME IMPLEMENTED DEĞİL, `operation_id` kalıcı bağımsız identity olarak IMPLEMENTED DEĞİL (mevcut: `intent_id` reuse + fingerprint join)

---

## 16. Recommended Next Step → FAZ 2 (güncel durum: 2536af0 sonrası)

```text
P0 — checkpoint commit (TANUQ identity + product shell + packaging gate
     + adapter)                                  → DONE (7525c66, CI GREEN)
     + RT-1/RT-2 security remediation checkpoint → DONE (2536af0, CI GREEN:
       pytest ubuntu+windows / packaging-gate ubuntu+windows, run 34440460146)
P1 — CI: packaging-gate Ubuntu + Windows matrisi → DONE (run 34358984274:
     4/4 job SUCCESS)
P1 — Windows child-hang: ayrı teşhis görevi      → AÇIK (NEEDS HUMAN TOOL
     — py-spy/ETW); Faz 2 blocker değil
P2 — Coordinator Faz 2c: propose delegation      → DONE (cli.py:129,
     web.py:335-343)
P2 — Claude Code adapter execute wiring          → KODDA MEVCUT (untracked);
     commit kararı operatöre ait
P2 — Boundary documentation refresh              → DONE (bu doküman revizyonu)
P3 — Operation Model Design / Lifecycle Freeze   → SIRADAKİ (bkz. §17 tasarım
     girdisi; IMPLEMENTASYON DEĞİL)
P4 — ExternalOutcomeJournal production entegrasyonu (spike → gerçek)
```

---

## 17. Operation Model Design Input (HAZIRLIK — KARAR İÇERMEZ)

Bu bölüm FAZ 3 (Operation Model Design / Lifecycle Freeze) için kod
gerçekliğinden türetilen MINIMUM tasarım girdisidir. Burada HİÇBİR mimari
karar verilmemiştir; sadece cevaplanması gereken sorular ve mevcut kod
gerçekleri kaydedilmiştir.

**Q1 — Operation neden gerekli olabilir?**
Mevcut projection (`tanuq/evidence.py::operations/lineage`) fingerprint
başına kanıt zincirini yeniden kurar; kalıcı bir koordinasyon nesnesi
yoktur. WAIT/RESUME, cross-process in-flight ve çok-adımlı operation
ihtiyaçları doğduğunda projection'ın RAM/geçici doğası yeterli
olmayabilir. Şu an böyle bir ihtiyaç KODLA KANITLANMAMIŞTIR.

**Q2 — operation_id'nin sorumluluğu ne olurdu?**
Tek bir governed değişikliğinin propose→approve→execute→terminal tam
yaşam döngüsünü adlandırmak. Mevcut kodda bu rolü parça parça üstlenen
şeyler: `intent_id` (apply/rollback journal chain), `fingerprint`
(proposal/approval/kanıt join), `session` (agent oturu etiketi).

**Q3 — fingerprint vs operation_id farkı?**
Fingerprint = PATCH İÇERİĞİNİN canonical identity'si (değişmez; aynı
patch = aynı fingerprint = dedupe). operation_id (tasarlanırsa) = SÜRECİN
identity'si olurdu (aynı patch'in ikinci, yeni bir operation'ı ayrı
operation_id alabilir). Bu ayrım mevcut kodda henüz modellenmemiştir.

**Q4 — Operation projection'ı ne taşımalı?**
Mevcut `operations()` projection alanları (state, terminal, fingerprints,
sessions, approval_id, intent_id, timestamps) — bkz. tanuq/evidence.py.
Yeni alan eklenmesi ihtiyacı KANITLANMAMIŞTIR.

**Q5 — EventStore/Journal vs Operation sınırı?**
EventStore/ApplyOutcomeJournal/ApprovalLedger = EVIDENCE (append-only,
hash-chained, fail-closed). Operation (tasarlanırsa) = türetilmiş
coordination görünümü olmalıdır; evidence'ın yerini almamalıdır. Anayasa:
Journal/EventStore = EVIDENCE — değişmez.

**Q6 — intent_id yeterli mi, yoksa bağımsız operation_id mi?**
İKİ HİPOTEZ DE AÇIKTIR, ikisi de kanıtsızdır:
  (a) "intent_id + fingerprint join yeterli" — WAIT/RESUME ancak
      approve-pending anında askıya almayı gerektiriyorsa (mevcut pending
      dosyası zaten kalıcı) yeni identity gerekmeyebilir.
  (b) "kalıcı operation_id gerekir" — ancak operation'ın execute'tan
      ÖNCE, propose anında kalıcı olarak adlandırılması gerekiyorsa.
Karar, use-case kanıtıyla (hangi Faz 6 akışının hangi identity'ye
ihtiyaç duyduğu) verilmelidir. Bu dokümanda KARAR YOK.

**Q7 — Minimum lifecycle state seti?**
Mevcut projection state'leri: PROPOSED / PENDING_APPROVAL / VERIFIED /
ROLLED_BACK / DENIED / INCIDENT (tanuq/evidence.py). Yeni state'e kodla
kanıtlanan ihtiyaç: YOK. WAITING/RESUMED gibi state'ler yalnızca
WAIT/RESUME implementasyonunun gerektireceği durumlarda tasarlanmalıdır.

**Q8 — Hangi state'ler evidence'tan türetilmeli?**
Tümü. Mevcut gerçekte lifecycle tamamen journal/event türevlidir
(fail-closed replay). Yeni kalıcı coordination state'i eklenmesi ancak
evidence'ta türetilemeyen bir ihtiyaç kanıtlanırsa gündeme gelir.

**Q9 — Coordinator hangi geçişleri yönetebilir?**
Yalnızca coordination geçişleri: in-flight rezervasyon (RAM), execute
delegasyonu, propose delegasyonu, projection okuma. Authority geçişleri
(grant/consume/apply/verify/rollback) Coordinator DIŞINDA kalır — anayasa
değişmez.

**Q10 — Hangi kararlar kesinlikle Coordinator DIŞINDA kalmalı?**
`ApprovalStore.grant/consume/revoke`, `ApplyAuthorization.authorize`,
`FileApplier.apply/restore`, `GovernanceEvaluator.evaluate`,
`PatchProposal.fingerprint()`, `VerificationExecutor` pass/fail.
(ORCHESTRATION_BOUNDARY §12 listesiyle birebir aynı — değişmez.)

**Design freeze durumu:** Operation Model ve WAIT/RESUME
**IMPLEMENTED DEĞİLDİR**; bu bölüm bir sonraki tasarım görevine girdi
sağlar ve hiçbir implementasyon taahhüdü içermez.

---

## Kanıt dosyaları listesi (bizzat doğrulanan)

| İddia | Kanıt dosya:satır |
|---|---|
| GovernanceEvaluator.evaluate | simulation/security/governance_evaluator.py:152 |
| RiskEngine.classify | simulation/security/risk_engine.py:368 |
| RiskPolicy.decide | simulation/security/risk_policy.py:64 |
| WorkerActionPipeline.execute | simulation/agent/pipeline/worker_action_pipeline.py:355 |
| PatchValidator.validate | simulation/agent/worker/patch_validator.py:18 |
| ApplyExecutor.apply | simulation/agent/apply/apply_executor.py:69 |
| FileApplier.apply | simulation/agent/apply/file_applier.py |
| VerificationExecutor.verify | simulation/agent/verify/verification_executor.py:122 |
| ApprovalStore.grant | simulation/agent/approval/approval_store.py:147 |
| ApprovalStore.find_valid | simulation/agent/approval/approval_store.py:289 |
| ApprovalStore.authorize_apply | simulation/agent/approval/approval_store.py:462 |
| PatchProposal.fingerprint | simulation/agent/worker/patch_proposal.py:16 |
| EventStore.append | simulation/persistence/event_store.py:157 |
| ChainAnchor | simulation/persistence/chain_anchor.py:145 |
| _ProcessFileLock | simulation/persistence/process_lock.py:73 |
| ApplyOutcomeJournal | simulation/agent/apply/apply_outcome_journal.py |
| OperationCoordinator.execute | tanuq/coordinator.py (Faz 2) |
| agent_adapter.propose/execute | tanuq/agent_adapter.py |
| Claude Code adapter | tanuq/claude_code_adapter.py |
| CLI execute → Coordinator | tanuq/cli.py::cmd_execute |
| Web execute → Coordinator | tanuq/web.py::_execute |
