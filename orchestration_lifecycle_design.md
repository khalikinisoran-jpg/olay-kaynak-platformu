# TANUQ — OPERATION MODEL + LIFECYCLE DESIGN FREEZE

> **Amaç:** FAZ 2/2b tamamlandıktan sonra, TANUQ orchestration lifecycle'ının
> kesin state modelini, authority sınırlarını ve Coordinator sorumluluk
> dağılımını **mevcut repository kanıtına dayalı olarak** dondurmak.
>
> Bu doküman **architecture decision** çıktısıdır — implementation görevi değil.

---

## 1. Executive Decision

**Operation modeli mevcut journal/pending/evidence projection'larından türetilir.
Yeni bir kalıcı state store, database veya audit sistemi oluşturulmaz.**

`OperationCoordinator` **coordination + observation** sorumluluğu taşır;
governance/approval/apply authority'si mevcut core katmanlarında kalır.

**Propose, Coordinator'a alınmalıdır** — çünkü:
1. Tek orchestration yüzeyi prensibi (CLI/Web/adapter → Coordinator → core)
2. Gelecekteki WAIT/RESUME için operation registration gereklidir
3. Authority değişmez — propose yine ApprovalStore'a authority vermez

---

## 2. Current Operation Model (repository kanıtlı)

### 2.1 Existing data sources

| Veri | Dosya | Sınıf/Fonksiyon | Persistence |
|---|---|---|---|
| event chain | `events.jsonl` | `EventStore.append` | hash-chain + anchor |
| apply lifecycle | `apply_journal.jsonl` | `ApplyOutcomeJournal` | hash-chain |
| approval state | `approval_ledger.jsonl` | `ApprovalLedger` | hash-chain + anchor |
| external journal | `external_outcome_journal.jsonl` | `ExternalOutcomeJournal` | hash-chain (spike) |
| pending proposals | `pending_proposals.json` | `tanuq/pending.py` | plain JSON (RAM+disk) |
| session labels | pending record `.session` alanı | `tanuq/pending.py:_record` | RAM+disk |
| fingerprint | `PatchProposal.fingerprint()` | patch_proposal.py:16 | hesaplanan (depolanmaz) |
| verification result | `VerificationResult` | verification_result.py | EventStore'ta |

### 2.2 Mevcut projection fonksiyonları

| Projection | Dosya | Girdi | Çıktı |
|---|---|---|---|
| `operations()` | tanuq/evidence.py:341 | journal + pending + events | state/fingerprint/session/approval/incident per operation |
| `lineage()` | tanuq/evidence.py:216 | journal + events + ledger | proposal→risk→approval→execution→verification chain |
| `incidents()` | tanuq/incidents.py | journal + events | orphan/crash/rollback_failed/chain_invalid |
| `export_evidence()` | tanuq/evidence.py:145 | tümü | audit bundle (JSON) |
| `chain_status()` | tanuq/evidence.py:30 | events + anchor | VALID/INVALID + ACTIVE/FAILED |
| `terminal_state()` | tanuq/evidence.py:185 | pipeline result | product-facing label |

---

## 3. Proposed Operation Projection

OperationCoordinator'ın **operations()** projection'ı mevcut kaynaklardan
şu Operation object'ini üretir:

```text
Operation
─────────────────────────────────────
operation_id       = journal intent_id (uuid4, apply_executor.py:180)
                     veya "fp-" + fingerprint[:12] (journal intent yoksa)
workspace          = load_environment(ws) workspace path
session            = pending record .session veya evidence task_id
                     ("tanuq-session:XXX" prefix'i)
fingerprint        = PatchProposal.fingerprint() (SHA-256, reason dahil)
proposal           = {path, action, reason, task_id, event_seq}
risk               = {risk_level, reason, allowed, approval_required, signals, seq}
approvals          = [{approval_id, status(grant/consumed/applied/revoked),
                      authorizer, created_at, expires_at}]
execution          = {intent_id, lifecycle[], terminal, approval_id}
verification       = {pass/fail, exit_code, evidence[]}
outcome            = journal terminal (VERIFIED/ROLLED_BACK/DENIED/FAILED/...)
denied_reason      = scope/risk denial message
incidents          = [crashed_during_apply, orphaned_apply, rollback_failed, ...]
in_pending         = bool (pending store'da bekliyor mu)
evidence_refs      = {first_seq, last_seq, event_count}
```

**Önemli:** Bu projection, EventStore/ApprovalLedger/ApplyOutcomeJournal'ın
**yerine geçmez** — üzerine **salt-okunur correlation view**'dur.

---

## 4. Lifecycle State Machine

Aşağıdaki state modeli, mevcut journal/event/approval/pending gerçekliğinden
türetilen **product-facing projection**'dır. Core state machine'in
yerine geçmez — core davranışı değişmez.

```text
                    ┌──────────┐
     propose()      │ PROPOSED │  pending kaydı + governance değerlendirme
    ───────────────►└────┬─────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
  ┌─────────────┐ ┌───────────┐ ┌──────────┐
  │RISK_ASSESSED│ │PENDING_   │ │  DENIED  │ (terminal)
  │             │ │APPROVAL   │ └──────────┘
  └──────┬──────┘ └─────┬─────┘
         │              │
         │       approve()   reject()
         │              │
         ▼              ▼
  ┌─────────────┐ ┌───────────┐
  │  APPROVED   │ │EXPIRED/   │ (terminal)
  │             │ │REVOKED    │ └──────────┘
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ EXECUTING   │  apply başladı (journal: apply_started)
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ VERIFYING   │  compileall + pytest çalışıyor
  └──────┬──────┘
         │
    ┌────┴────┐
    ▼         ▼
VERIFIED   FAILED → ROLLBACK → ROLLED_BACK
(terminal)              │
                        ▼ (rollback başarısız)
                   ROLLBACK_FAILED → INCIDENT
```

### Alternative states

```text
INCIDENT            — orphaned apply / crashed_during_apply / chain_invalid
                      (startup_reconciliation detect-only)
EXPIRED             — approval TTL doldu, approve edilmemiş gibi davranır
REVOKED             — ApprovalStore.revoke çağrıldı
RECOVERY_PENDING    — mevcut kodda üretilmüyor (bounded recovery engine var
                      ama product akışında çağrılmıyor) → RECOMMENDED değil
```

---

## 5. State Transition Matrix

| # | From | To | Trigger | Authorized by | Coordinator rolü | Evidence konumu |
|---|---|---|---|---|---|---|
| 1 | (başlangıç) | PROPOSED | `propose()` — pending save + governance değerlendirme | GovernanceEvaluator (core) | delegate + observe | pending_proposals.json |
| 2 | PROPOSED | RISK_ASSESSED | governance.evaluate() sonucu event'e yazılır | RiskEngine (core) | delegate | EventStore WorkerRiskAssessed |
| 3 | RISK_ASSESSED | PENDING_APPROVAL | requires_human_approval = true | RiskPolicy (core) | observe | EventStore + pending |
| 4 | RISK_ASSESSED | DENIED | UNKNOWN→DENY veya risk > eşik | RiskPolicy (core) | observe | EventStore WorkerPatchValidated(valid=false) |
| 5 | PENDING_APPROVAL | APPROVED | `approve()` — ApprovalStore.grant | **İnsan** (CLI/Web operator) | **delegate only** | ApprovalLedger TYPE_GRANT |
| 6 | PENDING_APPROVAL | EXPIRED | Approval.is_expired() TTL aşımı | ApprovalStore (core) | observe | ApprovalLedger |
| 7 | PENDING_APPROVAL | REVOKED | `ApprovalStore.revoke()` | **İnsan** | delegate | ApprovalLedger TYPE_REVOKED |
| 8 | APPROVED / PROPOSED | EXECUTING | `execute()` — pipeline apply_started | WorkerActionPipeline (core) | delegate + in-flight slot | ApplyOutcomeJournal apply_started |
| 9 | EXECUTING | VERIFYING | apply tamamlandı, verification başladı | WorkerActionPipeline (core) | observe | ApplyOutcomeJournal applied |
| 10 | VERIFYING | VERIFIED | verification PASS (compileall + pytest exit 0) | VerificationExecutor (core) | delegate | ApplyOutcomeJournal verified + EventStore |
| 11 | VERIFYING | FAILED | verification FAIL (compile/pytest exit ≠ 0) | VerificationExecutor (core) | observe | ApplyOutcomeJournal + EventStore |
| 12 | FAILED | ROLLED_BACK | FileApplier.restore (authorized=True) | ApplyExecutor (core) | observe | ApplyOutcomeJournal rolled_back |
| 13 | FAILED | ROLLBACK_FAILED | FileApplier.restore başarısız | FileApplier (core) | observe → INCIDENT | ApplyOutcomeJournal rollback_failed |
| 14 | EXECUTING | INCIDENT | process crash → startup_reconciliation | ReconciliationEngine (detect-only) | observe | ApplyOutcomeJournal orphan |

**Kural:** Coordinator hiçbir transition'ı **authorize etmez** — yalnızca
`agent_adapter.propose/execute`'i delege eder ve **projection'ları okur**.
Her transition'ın authority sahibi yukarıdaki tabloda **core bileşendir**.

---

## 6. Authority / Responsibility Matrix

| Sorumluluk | Mevcut Bileşen | Authority sahibi | Coordinator rolü | Coordinator'a taşınabilir mi? |
|---|---|---|---|---|
| **Fingerprint üretimi** | `PatchProposal.fingerprint()` | — (deterministik fonksiyon) | Hayır — referans only | Hayır |
| **Fingerprint doğrulama** | `PatchValidator.validate` + `ApprovalStore.find_valid` | Core (PatchValidator + ApprovalStore) | Hayır — delegate | Hayır |
| **Risk sınıflandırma** | `RiskEngine.classify` + `GovernanceEvaluator.evaluate` | **GovernanceEvaluator (core)** | Hayır — delegate | Hayır |
| **Approval grant** | `ApprovalStore.grant` | **ApprovalStore (core)** — insan onayı ile | Hayır — delegate | Hayır |
| **Approval consume** | `ApprovalStore.find_valid` + `authorize_apply` | **ApprovalStore (core)** | Hayır — delegate | Hayır |
| **Approval revoke** | `ApprovalStore.revoke` | **ApprovalStore (core)** | Hayır — delegate | Hayır |
| **Apply** | `FileApplier.apply` | **ApplyExecutor + ApplyAuthorization (core)** | Hayır — delegate | Hayır |
| **Rollback** | `FileApplier.restore` | **ApplyExecutor (core)** | Hayır — delegate | Hayır |
| **Verification** | `VerificationExecutor.verify` | **VerificationExecutor (core)** | Hayır — delegate | Hayır |
| **Evidence yazımı** | `EventStore.append` + `ApplyOutcomeJournal` | **Core persistence** | Hayır — delegate | Hayır |
| **In-flight tracking** | `OperationCoordinator._in_flight` | — (RAM-only, process-local) | **Evet** — zaten Coordinator'da | **Zaten burada** |
| **Operation projection** | `operations()`, `lineage()`, `incidents()` | — (salt-okunur view) | **Evet** — zaten Coordinator üzerinden | **Zaten burada** |
| **Evidence export** | `export_evidence()` | — (salt-okunur bundle) | **Evet** | **Zaten burada** |

**Kural:** Coordinator'a **taşınabilecek** sorumluluklar yalnızca
**salt-okunur projection** ve **RAM-only orchestration state**'tir.
Authority içeren sorumlulukların tamamı core katmanında kalır.

---

## 7. Coordinator Boundary

```text
OperationCoordinator (tanuq/coordinator.py)
──────────────────────────────────────────
YAPAR:
  ✓ operations() — journal/pending/events projection
  ✓ lineage() — cross-journal chain
  ✓ incidents() — detect-only incident projection
  ✓ export() — salt-okunur audit bundle
  ✓ status() — workspace health summary
  ✓ execute() — agent_adapter.execute delegation + in-flight slot
  ✓ in_flight() — RAM-only state snapshot
  ✓ get_operation() — selector

YAPMAZ:
  ✗ grant() / consume() / revoke() — ApprovalStore authority'si
  ✗ apply() / restore() — FileApplier authority'si
  ✗ evaluate() / classify() / decide() — GovernanceEvaluator authority'si
  ✗ fingerprint() üretimi veya değişimi — PatchProposal deterministik fonksiyonu
  ✗ fsync / os.replace / journal formatı değişikliği — core persistence
  ✗ verification semantics değişikliği — VerificationExecutor authority'si
  ✗ rollback politikası değişikliği — ApplyExecutor authority'si
```

---

## 8. Propose vs Execute Decision

### Soru: `propose()` Coordinator'a alınmalı mı?

**KARAR: EVET — Coordinator'a alınmalı (RECOMMENDED).**

### Gerekçe:

1. **Tek orchestration yüzeyi prensibi:**
   Execute zaten Coordinator üzerinden geçiyor (Faz 2/2b).
   Propose'un dışarıda kalması asimetri yaratıyor.
   CLI/Web/Adapter üçü de aynı Coordinator üzerinden propose+execute
   çağırmalı.

2. **Gelecekteki WAIT/RESUME gereksinimi:**
   WAIT/RESUME modeli için operation registration (propose anında
   operation_id assignment) gerekiyor. Propose Coordinator dışındaysa
   Coordinator operation yaşam döngüsünü tamamlayamaz.

3. **Authority değişmiyor:**
   Propose approval üretmez, apply yapmaz, governance kararı vermez.
   Sadece pending kaydı + governance değerlendirmesi yapar (delegation).
   Coordinator'a alınması authority modelini değiştirmez.

4. **Mevcut davranış bozulmuyor:**
   `agent_adapter.propose()` değişmez — Coordinator yalnızca wrapper olur.
   CLI/Web çağrıları aynı kalır.

### Uygulama önerisi:

```python
# tanuq/coordinator.py (gelecekte eklenecek)
def propose(self, payload_text, session=None):
    """Delegate to agent_adapter.propose (no authority)."""
    from tanuq import agent_adapter
    return agent_adapter.propose(self.env, payload_text, session=session)
```

**Kod değişikliği: minimal (coordinator.py +1 method, cli.py/web.py
delegation değişikliği).** Bu görevde uygulanmamıştır — sonraki onaylı
görev olarak önerilir.

> **STATUS GÜNCELLEME (boundary refresh görevi, 7525c66 sonrası):**
> Bu karar **IMPLEMENTED EDİLDİ (Faz 2c)** — `coordinator.propose()`
> mevcut (coordinator.py:112-120); CLI (cli.py:129) ve web
> (web.py:335-343) propose'u Coordinator üzerinden geçiriyor.
> Yukarıdaki "gelecekte eklenecek" ifadesi tarihseldir.
> Authority modeli DEĞİŞMEDİ: propose delegation yetkisizdir.

---

## 9. Claude Code Adapter Lifecycle Analysis

`handle_pretooluse(env, raw_text)` akışı:

```text
Claude Code Edit tool call
  ↓
PreToolUse hook → adapter (stdin JSON)
  ↓
parse_pretooluse(raw) — fail-closed (malformed/unsupported → DENY)
  ↓
proposal_payload(parsed) — generic şemaya çeviri
  ↓
agent_adapter.propose(env, payload, session=session_id)
  ↓
┌─────────────────────────────────────────────────────────┐
│ state = DENIED           → deny "Tanuq governance DENIED│
│                            this edit: ..."              │
│ state = APPROVAL_REQUIRED→ deny "Tanuq: pending human   │
│                            approval (fingerprint ...)"  │
│ state = PROPOSED         → coordinator.execute(fp)      │
│     ↓ terminal = VERIFIED → deny "applied and verified" │
│     ↓ terminal = ROLLED_BACK → deny "verification       │
│         failed ... automatically rolled back"           │
│     ↓ terminal = DENIED → deny + denial_reason          │
└─────────────────────────────────────────────────────────┘
```

### APPROVAL_REQUIRED durumunda execute atlanması

**Doğru bir lifecycle davranışıdır:**

1. Edit tool call iptal edilir (fail-closed: Claude doğrudan yazamaz)
2. Proposal pending store'da kalır (kayıp değil — kalıcı)
3. Operatör `tanuq approve` + `tanuq execute` ile ayrı adımda yetkilendirir
4. Claude Code retry ettiğinde TANUQ propose dedupe yapar (same fingerprint)
5. Bu, gelecekteki WAIT/RESUME modelinin önünde engel **değildir**:
   - pending + approval kalıcı → restart sonrası resume mümkün
   - Claude Code retry → TANUQ same-fingerprint dedupe → çakışma yok

**Gelecekteki --wait / resume** (FAZ 6) bu pending state'i kullanır:
adapter deny yerine `"ask"` dönerek operatör onayını bekleyebilir.
Ancak bu FAZ 6 kapsamındadır — şimdi uygulanmaz.

---

## 10. WAIT / RESUME Readiness

```text
Soru: process ölürse ne olur?
Cevap: pending_proposals.json + approval_ledger.jsonl + events.jsonl
       kalıcıdır. Process ölürse pending + approval kaybolmaz.
       Yeniden başlatan kullanıcı/app:
         tanuq approve → tanuq execute  ile kaldığı yerden devam eder.
       Restart sonrası operations() projection pending'i ve incidents'ı
       doğru gösterir (EventStore hash-chain doğrulanır).

Soru: session ölürse ne olur?
Cevap: session label yalnızca observability amaçlıdır (pending record
       + evidence task_id). Session kaybolursa pending kaydı korunur;
       yeni session ile retry mümkündür.

Soru: approval kaybolur mu?
Cevap: ApprovalLedger hash-chained + anchored — process ölümü etkilemez.
       Yalnızca TTL dolduğunda (3600s) yeni approval gerekir.

Soru: Operation state nasıl tekrar gözlemlenir?
Cevap: operations() projection journal/pending/events'ten deterministik
       olarak türetilir. Restart sonrası doğru state gösterir.

Soru: EventStore/Journal source of truth olarak kalır mı?
Cevap: EVET — Coordinator hiçbir kalıcı state tutmaz. In-flight RAM-only.
       EventStore + ApprovalLedger + ApplyOutcomeJournal truth source'tur.
```

**Sonuç: WAIT/RESUME için mevcut mimari HAZIRDIR.**
Yeni state store, daemon veyainfrastructure gerektirmez.

---

## 11. Evidence Correlation

```text
Fingerprint ↔ evidence
────────────────────────
EventStore         : WorkerPatchProposed.payload.patch_fingerprint
                     WorkerRiskAssessed.payload.patch_fingerprint
                     WorkerHumanApprovalGranted.payload.patch_fingerprint
ApprovalLedger     : TYPE_GRANT.patch_fingerprint
                     TYPE_CONSUMED.patch_fingerprint
                     TYPE_APPLIED.patch_fingerprint
ApplyOutcomeJournal: TYPE_INTENT.patch_fingerprint
                     (intent_id ile correlate)
Operations projection: operations[].fingerprint (join key)

Tümüne "fingerprint" ile erişilebilir — tek join key.
```

---

## 12. Failure / Recovery Implications

```text
Process crash (parent):
  → events.jsonl + approval_ledger.jsonl + apply_journal.jsonl kalıcı
  → restart sonrası load_environment() chain doğrulaması yapar
  → startup_reconciliation orphan intent'leri tespit eder (detect-only)
  → operations() projection orphan'ları INCIDENT olarak gösterir
  → otomatik recovery YOK (recovery ≠ authorization sözleşmesi)

Process crash (child — verification):
  → TimeoutExpired → timed_out=True → verification FAIL → ROLLED_BACK
  → fail-closed korunur (Windows child-hang dahil — bkz. §13)

Process crash (launcher stub):
  → gerçek python3.12 torunu bitmiş olabilir
  → launcher stub askıda → communicate timeout
  → ROLLED_BACK (aynı fail-closed)
  → stub zinciri (Windows Store Python app-execution-alias) kaynaklı
    — mekanizma UNCONFIRMED (py-spy/ETW gerektirir)
```

---

## 13. Windows Reliability Dependency

```text
Windows verification child-exit reliability
────────────────────────────────────────────
Platform: Windows (lokal)
Context:  TANUQ runtime parent + execute flow + verification pytest child
Symptom:  child exit intermittent delay (bazı koşumlarda >120s timeout)
State:    child yaşlıyor (WaitForSingleObject → WAIT_TIMEOUT),
          CPU ≈ 0, Wait/UserRequest, HandleCount ~130–137 sabit
Mechanism: UNCONFIRMED (py-spy DLL hatası; CIM aralıklı arızalı)
Security:  fail-closed korunuyor — timeout → FAIL → ROLLED_BACK
           yanlış VERIFIED: 0 koşum
Production fix: uygulanmadı (root cause UNCONFIRMED)
Status:    FAZ 2→3 lifecycle tasarımını BLOKE ETMEZ
```

---

## 14. Open Questions

1. **App Execution Alias stub'ın çıkmama nedeni** — Windows Store Python
   launcher stub süreci, gerçek interpreter bitmesine rağmen neden yaşamaya
   devam ediyor? (Windows kernel handle davranışı — ETW/windbg gerekli)
2. **Defender/EDR minifilter** — pyc yazımı veya child process exit'i
   geciktiriyor mu? (salt-okunur ortamda kanıtlanamaz)
3. **`PYTHONPYCACHEPREFIX`'in `_env()`'den kaldırılması** — verification
   güvenliğini zayıflatmaz mı? (ws `.gitignore`'a `__pycache__/` zaten var;
   pyc yazımı repo mutasyonu sayılmaz — ama dokümantasyon güncellenmeli)
4. **Claude Code adapter `--wait`** — APPROVAL_REQUIRED durumunda deny
   yerine `ask` dönmek (operatör onayını beklemek) FAZ 6 adayı mı?

---

## 15. Design Freeze

| Karar | Durum | Kanıt |
|---|---|---|
| Operation model = mevcut journal/pending/events projection | **CONFIRMED** | tanuq/evidence.py + simulation/agent/* kod kanıtı |
| Lifecycle states = core state machine'den türetilen product projection | **CONFIRMED** | tanuq/evidence.py::operations() mevcut |
| State authority = core katmanları (GovernanceEvaluator, ApprovalStore, ApplyExecutor, VerificationExecutor) | **CONFIRMED** | simulation/** kod kanıtı |
| Coordinator = coordination + observation only | **CONFIRMED** | tanuq/coordinator.py — authority yüzeyi yok (test kanıtlı) |
| Propose → Coordinator'a alınmalı | **IMPLEMENTED (Faz 2c)** | cli.py:129 + web.py:335-343 + coordinator.py:112-120 — authority değişmedi |
| Claude Code adapter APPROVAL_REQUIRED'da execute atlaması doğru | **CONFIRMED** | Fail-closed; pending kalıcı; operatör approve ayrı adım |
| WAIT/RESUME mimari olarak hazır | **RECOMMENDED** | Pending + approval + evidence kalıcı; yeni store gereksiz |
| Windows child-hang mekanizması | **UNCONFIRMED** | py-spy çalışmıyor; CIM güvenilmez; NEEDS TOOL |
| In-flight state RAM-only, restart'ta kaybolur | **CONFIRMED (tasarım)** | tanuq/coordinator.py `_in_flight` dict |

---

## 16. Recommended Implementation Order

```text
1. Coordinator.propose() ekle (coordinator.py +1 method, cli.py/web.py
   delegation değişikliği) — tek orchestration yüzeyi tamamlanır
   → DONE (Faz 2c)
2. Pending state'i Operation modeline resmi olarak bağla
   (operations() projection pending'inden operation_id assignment)
   → AÇIK — Operation Model design input: ORCHESTRATION_BOUNDARY.md §17
     (operation_id gerekliliği kanıtlanmadan karar verilemez)
3. Claude Code adapter'ı coordinator.propose + coordinator.execute
   üzerinden geçir (şu an propose agent_adapter'a direkt)
   → EXECUTE WIRING KODDA MEVCUT (untracked adapter, Coordinator.execute
     kullanıyor); propose hâlâ doğrudan agent_adapter.propose — satır
     satır durum: adapter commit kararı operatöre ait
4. Windows child-hang: py-spy'ı çalışır hale getir (EDR teşhisi veya
   alternatif kurulum) → stack kanıtı → mekanizma CONFIRMED
   → AÇIK (NEEDS HUMAN TOOL)
5. --wait / RESUME (FAZ 6) — yukarıdaki lifecycle state machine'i
   kullanarak uygula
   → AÇIK — IMPLEMENTED DEĞİL
```

---

## 17. Git Status

```text
Branch:  main @ dccdd32
Modified: yok (bu görevde production/test/docs değişikliği YOK)
Untracked: ORCHESTRATION_LIFECYCLE_DESIGN.md (bu görev),
           ORCHESTRATION_BOUNDARY.md (önceki görev),
           tanuq/ + tests/test_tanuq_* (önceki onaylı görevler),
           docs/{USER_GUIDE,QUICKSTART,AGENT_INTEGRATION}.md,
           benchmarks/, _dbg*.py ×14, _diag*.py ×5, _run_obs.py,
           _verify_postfix.py, _diag3_run.log,
           7× child_*.dmp (⚠️ SECRET), dist/, t
simulation diff: EMPTY
p5 diff:         EMPTY
Commit:  NONE · Push: NONE · Merge: NONE
```

> **NOT (güncel durum):** Yukarıdaki blok, dokümanın yazıldığı anın
> TARİHİ snapshot'ıdır (dccdd32). Güncel gerçek: main @ **7525c66**
> (Verification Reality V1 checkpoint), origin/main ile senkron,
> hosted CI GREEN (run 34358984274, 4/4 job). Drift düzeltmeleri
> ORCHESTRATION_BOUNDARY.md §3/§5a/§15/§16/§17'de.

---

## 18. OPERATION MODEL DESIGN PROPOSAL v1 → **KARAR VERİLDİ: OPERATION_ID NOT REQUIRED — FROZEN**

> **STATUS: KARAR FROZEN (Operation ID Gereksinim Analizi görevi, 7525c66
> üzerinde).** Bu bölüm 7525c66 sonrası kod gerçekliğinden türetilmiş,
> use-case bazlı gereksinim analiziyle kesinleştirilmiştir. Anayasa
> değişmez: Operation hiçbir koşulda AUTHORITY olamaz.
>
> **KARAR KAYDI — OPERATION_ID: NOT REQUIRED — FROZEN.**
>
> Identity modeli (frozen):
> - `fingerprint` = İÇERİK identity'si (patch_proposal.py:16)
> - `intent_id` = APPLY-TIME execution intent identity'si (uuid4,
>   apply_outcome_journal.py:180)
> - pending kaydı = PRE-APPLY kalıcı bekleme identity'si (fingerprint-keyed,
>   tanuq/pending.py)
> - evidence/journal = lifecycle geçmişi ve korelasyon (fingerprint join)
> - `operation_id` = MEVCUT AŞAMADA GEREKLİ DEĞİL
>
> Senaryo bazlı freeze kararları:
> 1. Tek fingerprint / tek execution → operation_id GEREKMEZ (fingerprint
>    join yeterli; lineage mevcut).
> 2. Retry → intent_id + attempt YETERLİ (her attempt yeni intent_id +
>    attempt numarası; approval binding attempt-bound).
> 3. WAIT/RESUME → pending + fingerprint YETERLİ (pending kalıcı,
>    fingerprint-keyed; resume aynı identity yolu).
> 4. Process restart → mevcut reconciliation YETERLİ (orphaned intent
>    detection, incidents.py + fault_injection corpus; identity = intent_id).
> 5. Cross-process concurrency → problemin çözümü operation_id DEĞİL,
>    ayrı locking/coordination tasarımıdır (mevcut _ProcessFileLock
>    primitive'i üzerinde, ayrı onaylı görev).
> 6. Multi-patch bundle identity → yapısal olarak MEVCUT bir eksikliktir
>    (journal intent payload'ında ortak koordinasyon identity'si yok);
>    ancak bugün operation_id gerektiren doğrulanmış kullanıcı/use-case
>    ihtiyacı YOKTUR.
>
> **Yeniden değerlendirme koşulu (tek koşul):** Multi-patch bundling veya
> başka SOMUT bir koordinasyon gereksinimi ortaya çıkar ve mevcut
> identity modeli (fingerprint + intent_id + pending + evidence) gerçek
> bir operasyonel ihtiyacı karşılayamazsa operation_id yeniden
> değerlendirilir. "Gelecekte faydalı olabilir" tek başına gerekçe
> DEĞİLDİR.

### 18.1 Operation necessity — sınıflandırma

**SONUÇ: REQUIRED ONLY FOR SPECIFIC USE CASE.**

Kod gerçekliği:
- Aynı fingerprint altında ZAMAN İÇİNDE birden fazla execution/lifecycle
  MÜMKÜNDÜR — CONFIRMED: ROLLED_BACK ve FAILED durumlarında pending
  kaydı SİLİNMEZ (agent_adapter.py:303-304 yalnızca VERIFIED ve
  DENIED(validation/risk)'ta remove_pending çağırır); tüketilmiş approval
  sonrası yeniden grant + re-execute mümkündür (approval_boundary_test).
- `intent_id` yalnızca APPLY anında üretilir (uuid4,
  apply_outcome_journal.py:180) — propose/approval (pre-apply) fazında
  henüz yoktur — CONFIRMED.
- Pre-apply koordinasyon identity'si bugün fingerprint + pending
  kayıdıdır (pending_proposals.json kalıcıdır, fingerprint-keyed) —
  CONFIRMED (tanuq/pending.py).
- `session` advisory etikettir, identity değildir (tek session altında
  çok fingerprint olabilir) — CONFIRMED.

Neden "Operation" ancak belirli use-case'lerde gerekir:
1. **Multi-patch operation**: `run_all` tek pipeline koşusunda birden
   fazla fingerprint yürütür; bunları TEK koordinasyon varlığı olarak
   adlandıracak identity bugün YOK. — CONFIRMED (driver adayı)
2. **Cross-process in-flight**: `_in_flight` RAM-only ve process-local;
   kalıcı coordination identity'si olmadan iki process aynı
   fingerprint'i execute edebilir (eski içerik match check'i fiziksel
   çift-yazımı sınırlar ama coordination seviyesinde serialization yok).
   — CONFIRMED risk, çözüm tasarımı ayrı
3. **WAIT/RESUME'da süreç-üstü adlandırma**: bugün fingerprint ile
   correlation mümkündür; ayrı operation_id ancak aynı fingerprint'in
   birden fazla bekleme dönemini AYIRT etme gereksinimi kanıtlanırsa
   gerekir. — UNKNOWN (use-case kanıtı bekliyor)

Tek-patch propose→approve→execute akışı için: **NOT REQUIRED.**

### 18.2 Identity model (trace edilmiş gerçek)

```text
fingerprint  = "hangi İÇERİĞİN kimliği?"   → patch_proposal.py:16, SHA-256
               (değişmez; dedupe anahtarı; approval/authz/journal/evidence join)
intent_id    = "hangi EXECUTION INTENT zincirinin kimliği?" → uuid4, apply-time only
operation_id = "hangi KOORDİNASYON SÜRECİNİN kimliği?"      → BUGÜN MEVCUT DEĞİL
```

### 18.3 Minimum Operation schema (yalnızca Operation getirilirse)

| Alan | Sınıf | Gerekçe |
|---|---|---|
| fingerprint | **REQUIRED** | tüm kanıtın join anahtarı (mevcut gerçek) |
| proposal reference | **REQUIRED** | pending kaydı + propose/risk evidence event'leri |
| lifecycle projection | **REQUIRED (DERIVED)** | tamamen evidence türevi; asla ayrı truth değil |
| session_id | OPTIONAL | advisory; evidence'ta zaten var |
| approval reference | DERIVED | ApprovalLedger'dan fingerprint ile; Operation'a kopyalanmaz |
| intent reference | DERIVED | ApplyOutcomeJournal'dan fingerprint ile; birden çok olabilir |
| created sequence | OPTIONAL | EventStore sequence zaten taşıyor |
| operation_id | NOT NEEDED (bugün) | yalnızca §18.1 use-case 1-3 kanıtlanırsa REQUIRED olur |

Yeni audit history, yeni DB, yeni store: **YOK.** Operation = coordination
identity + projection; EventStore/Journal = evidence/history. Sınır değişmez.

### 18.4 Lifecycle state machine — aday değerlendirmesi

| Aday state | Karar | Anlam / üretici / authority / terminal / türev? |
|---|---|---|
| PROPOSED | **TUT (derived)** | pending'de kayıtlı, execute bekliyor; üretici: agent_adapter.propose; authority yok; terminal değil; pending+events'ten türetilir |
| RISK_ASSESSED | **RED** | governance kararı authority event'idir, coordination state değil; risk projection attribute'udur; ayrı state = authority/projection karışması |
| PENDING_APPROVAL | **TUT (derived)** | pending + geçerli approval yok; authority ApprovalStore; terminal değil; türetilir |
| APPROVED | **RED — DUPLICATION** | approval geçerliliği ApprovalStore/Ledger'in authoritysidir; execute anında find_valid/authorize_apply zaten karar verir; Operation'da APPROVED state'i tutmak ikinci bir truth kaynağı yaratır |
| EXECUTING | **TUT (coordination-only, RAM)** | yalnızca Coordinator `_in_flight` RAM slot; persist EDİLMEZ; terminal değil |
| VERIFYING | **RED** | execution'ın alt aşaması; kanıt event'lerde stage olarak var; coordination değeri yok |
| VERIFIED | **TUT (terminal, derived)** | events + journal verified outcome'tan türetilir; authority: VerificationExecutor (karar), evidence (kayıt) |
| FAILED | **TUT (terminal, derived)** | apply-stage failure; terminal_state() mapping mevcut |
| ROLLBACK (started) | **RED (kalıcı state olarak)** | journal rollback_started kaydı yeterli; orphan detection INCIDENT overlay ile; kalıcı state gereksiz |
| ROLLED_BACK | **TUT (terminal, derived)** | journal + events; pending bilinçli olarak kalır (re-execute mümkün) |
| DENIED | **TUT (terminal, derived)** | validation/risk denial; blocked evidence |
| INCIDENT | **TUT (derived overlay)** | detect-only (incidents.py); saklanan state değil, projection bayrağı |
| RECOVERY_PENDING | **RED (şimdilik)** | recovery pipeline içi bounded retry; kalıcı recovery state yok; ihtiyaç kanıtlanırsa tasarlanır |
| EXPIRED | **RED (state olarak)** | approval expiry authority tarafında (find_valid None döner); Operation PENDING_APPROVAL kalır; expiry derived annotation olabilir |

**Minimum terminal seti: VERIFIED, ROLLED_BACK, DENIED, FAILED.**
Gerekçe: terminal_state() projection bu dördü terminal olarak map eder;
EXPIRED/INCIDENT terminal değildir (biri annotation, biri overlay).

### 18.5 State vs Evidence ayrımı (kritik kural)

- Evidence'tan türetilebilir (kalıcı state YASAK): VERIFIED, ROLLED_BACK,
  DENIED, FAILED, PROPOSED, PENDING_APPROVAL, INCIDENT — mevcut
  evidence.py::operations/lineage bunları zaten türetiyor. — CONFIRMED
- Coordination-only (RAM, kalıcı yasak): EXECUTING. — CONFIRMED
  (mevcut _in_flight ile aynı)
- Kalıcı YENİ coordination state'i gerektiren kanıtlanmış use-case:
  **BUGÜN YOK.** — CONFIRMED

### 18.6 WAIT/RESUME identity analizi (implementasyonsuz)

```text
PENDING_APPROVAL → [WAIT: process ölebilir] → human approve → RESUME → execute
```

- Process kapanırsa: pending_proposals.json kalıcı (fingerprint + payload
  + session + created_at); propose/risk evidence event'leri journal'da. — CONFIRMED
- Yeniden açılışta devam identity'si: **fingerprint** (pending dosyası
  fingerprint-keyed; `tanuq execute --fingerprint` aynı yolu izler). — CONFIRMED
- intent_id bu fazda henüz YOK (apply-time uuid4). — CONFIRMED
- operation_id olmadan correlation: **MÜMKÜN** — lineage() tam olarak bunu
  yapar (fingerprint join: pending + events + ledger + journal). — CONFIRMED
- operation_id'nin ekleyeceği tek şey: aynı fingerprint'in birden fazla
  bekleme/execution döneminin ayırt edilmesi. Bu ihtiyacın gerçek
  use-case'i henüz yoktur. — UNKNOWN

### 18.7 Concurrency / Recovery / Multi-patch etkisi (analysis only)

- **Concurrent operations (aynı workspace):** process-içi: `_in_flight`
  guard; process-ler-arası: coordination-level serialization YOK —
  kalıcı coordination identity'si veya kilit tasarımı ancak bu use-case
  resmileşirse gündeme gelir. Fiziksel sınır: FileApplier exact
  old_content match. — CONFIRMED risk, INFERRED sınır etkinliği
- **Crash + startup reconciliation:** mevcut incident detection
  (orphaned apply intents, pending intents) + fault_injection corpus.
  Operation modeli bunu DEĞİŞTİRMELİ DEĞİL; projection'a orphan görünümü
  zaten var. — CONFIRMED
- **Multi-patch tek operation:** run_all bugün N fingerprint'i tek
  pipeline koşusunda yürütür; N intent oluşur. "Tek operation" bundling
  operation_id'nin EN GÜÇLÜ gerekçesidir — karar use-case onayıyla. — CONFIRMED driver
- **Retry/resume:** mevcut bounded retry pipeline içi (MAX_ATTEMPTS_CAP=3);
  kalıcı retry identity gereksinimi: YOK (kanıtlanmış). — CONFIRMED

### 18.8 p5 / agent_run

**OPEN DESIGN DECISION.** Operation kavramı bugün Tanuq product path için
tanımlanmalıdır (tek orchestration yüzeyi orada zaten var). Ortak primitive
haline getirilmesi ancak assembly'ler birleştirilme kararı alınırsa
gündeme gelir; bu görev kapsamı dışıdır.

### 18.9 Freeze önkoşulları (implementation başlamadan önce)

1. §18.1 use-case 1-3'ten en az birinin insan operatör tarafından gerçek
   gereksinim olarak onaylanması (aksi halde Operation implemente EDİLMEZ).
2. operation_id getirilirse üretim zamanı (propose-time vs execute-time)
   ve format kararı (rastgele UUID vs türetilmiş) — Q6 hipotez testiyle.
3. EXECUTING kalıcı hale getirilecekse cross-process locking tasarımı
   (mevcut _ProcessFileLock primitive'i üzerinde) — ayrı görev.
4. Hiçbir state evidence'tan türetilemeyeceği halde persist edilmeyecek
   — §18.5 kuralının test corpus'uyla sabitlenmesi.

---

## DESIGN FREEZE STATUS

**FROZEN** — Operation model, lifecycle state machine, Coordinator
boundary ve Propose/Execute kararı yukarıda dondurulmuştur.
Değişiklik ancak yeni onaylı görev ile yapılabilir.

**GÜNCELLEME (Operation ID Gereksinim Analizi, 7525c66):** §18'deki
Operation Model önerisi use-case analiziyle kesinleşti ve
**OPERATION_ID: NOT REQUIRED — FROZEN** olarak donduruldu (bkz. §18
başındaki karar kaydı). §18.3 schema'sındaki `operation_id: NOT NEEDED
(bugün)` sınıflandırması artık karardır; §18.9 önkoşullarından 1-2
kapatılmıştır. Yeniden değerlendirme yalnızca §18'deki tek koşul
(multi-patch bundling veya somut koordinasyon gereksinimi + mevcut
identity modelinin yetersizliği) gerçekleşirse açılır.
