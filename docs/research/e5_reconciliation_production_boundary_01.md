# TANUQ — E5 Reconciliation Production Boundary 01 (V1 Scope Lock)

> STATUS: implementation-boundary addendum to
> `e5_reconciliation_production_design_01.md` (owner CONDITIONAL GO →
> minimal V1 scope locked). DESIGN/BOUNDARY ONLY — no code, no commit,
> no push. This document LOCKS the V1 scope; implementation may start
> only against THIS boundary, nothing more.

---

## 1. V1 SCOPE (kesinleştirildi)

1. **Yeni standalone modül:** `tanuq/reconciliation.py` — read-only
   projection; trajectory.py pattern'i (no authority, no evidence
   writes, no pipeline coupling).
2. **CLI subcommand:** `tanuq reconcile --workspace` (+ opsiyonel
   `--json` machine-readable output). Tek mevcut-dosya dokunuşu:
   `tanuq/cli.py` subcommand registrasyonu (trajectory pattern,
   mekanik).
3. **Journal-scoped governed paths only:** scope = apply_journal
   intent path'leri + pending path'leri. Full workspace scan YOK.
4. **Deterministic byte-exact SHA-256 comparison:** disk bytes vs
   journal-recorded hash. Similarity/threshold/scoring YOK.
5. **Terminal-state-aware expected hash:**
   - `applied` (terminal mevcut, rolled_back yok) → new_content_hash
   - `rolled_back` → old_content_hash
   - `apply_started` without terminal → **INDETERMINATE**
     (mismatch iddiası YOK; PARTIAL_EXECUTION_CANDIDATE observation'ı
     mümkün — STALE_PENDING ile)
6. **Output:**
   - Human-readable CLI (per-path satırları + özet + coverage report +
     standing note)
   - Machine-readable JSON (`--json`)
   - Output içerik sınırı: path + fingerprint + hash'ler + terminal
     durumları + standing note. **Dosya içeriği/diff asla yazılmaz**
     (privacy, Design-01 §21).

## 2. V1'DE OLMAYACAK (explicit exclusions — her biri ayrı owner gate konusudur)

- incidents EventStore integration / incidents-field surfacing
- evidence chain write (yeni event tipi, journal entry, anchor dokunuşu)
- automatic scheduling (daemon/cron/managed task)
- post-execute hook (pipeline coupling)
- execution blocking (mismatch'e dayalı herhangi bir engelleme)
- risk modification (yukarı/aşağı)
- approval creation
- authorization changes
- policy changes
- fingerprint changes
- full workspace scan (ungoverned-directory taraması)
- ungoverned-file authority (kapsama alma kararı/capture)
- relocation authority/change (path-bound davranışın değiştirilmesi)
- similarity/threshold logic (E1-C dersi: FP-baskın; determinant kural
  dışına çıkılmaz)

## 3. AÇIK KARARLAR (DEFERRED / OUT OF SCOPE)

| Karar | Durum |
|---|---|
| incidents surfacing | **DEFERRED** — ayrı owner gate (schema Design-01'de öneri olarak mevcut) |
| scheduling | **DEFERRED** — manuel CLI V1 default'u |
| ungoverned coverage | **DEFERRED** — allowed_paths-scoped genişleme ayrı security review ister |
| relocation flow | **DEFERRED** — path-bound fail-closed davranış aynen korunur |
| automatic execution blocking | **OUT OF SCOPE** — reconciliation'ın enforcement yolu mimari olarak mevcut değildir ve V1'de oluşturulmaz |

## 4. INVARIANTS (V1 implementation'ında birebir korunacak)

```text
reconciliation result != authorization
reconciliation result != security verdict
MATCH               != secure
CONTENT_MISMATCH    != automatic block
```

Ek olarak (Design-01 §0'dan devreden):

```text
EXECUTION TRUTH ≠ VERIFICATION RESULT ≠ EVIDENCE RECORD
evidence integrity ≠ evidence truth
```

Uygulama düzeyinde koruma mekanizmaları:
- Modül, governed pipeline/approval/risk modüllerinden HİÇBİRİNİ
  import etmez (import-boundary test ile zorlanır).
- Probe çıktısı `.tanuq/` altına YAZMAZ; yalnızca stdout (scratch
  dosya istenirse araştırma modunda).
- Herhangi bir mismatch kaydı hiçbir yerde enforcement girdisi olarak
  kullanılamaz (kod yolu yok).

## 5. STANDING NOTE (her output'un zorunlu parçası)

```text
Reconciliation = state consistency check (point-in-time).
MATCH means: at read time T, disk bytes matched the last evidenced hash.
MATCH is NOT a security statement. CONTENT_MISMATCH is NOT an
enforcement action — it is an observation for the human operator.
Verification blind spots (E5-4) and out-of-channel runtime behavior
are outside this check.
```

## 6. IMPLEMENTATION-READY DEĞERLENDİRMESİ

**Hazır.** Gerekçeler:

1. Kural, research probe'ta canlı doğrulandı (E5 Reconciliation
   RUN-01: E5-1 drift 2/2 CONTENT_MISMATCH; benign/FP corpus 0 FP;
   rolled_back kuralı canlı teyitli).
2. Hash konvansiyonu empirik CONFIRMED (journal hash'leri == sha256 of
   exact LF bytes).
3. Kapsam journal-scoped → performans ve authority sınırları net.
4. Tek mevcut-dosya dokunuşu: cli.py registrasyonu (mekanik, trajectory
   subcommand pattern'iyle aynı).
5. Test stratejisi Design-01 §24'te tanımlı (8 kategori; yeni test
   modülleri — G1 uyumlu).
6. Rollback/disable = koşumama + tek dosya revert; migration yok.

Bilinen sınırlar (V1'de kabul edilen): in-flight INDETERMINATE
skip'i; ungoverned coverage yok; relocation path-bound; E5-4 semantic
blind spot kapsamı dışı. Hepsinin V1'de bilinçli olarak KABUL
edildiği bu addendumla kayıt altında.

## 7. V1 ACCEPTANCE (implementation task'ının bitiş kriterleri — özet)

- `tanuq reconcile --workspace` ve `--json` çalışır; Design-01 §4
  kuralına birebir uyar.
- Frozen E5-1 drift corpus → CONTENT_MISMATCH; benign/FP corpus →
  0 mismatch (regression).
- Import-boundary test: modül pipeline/approval/risk'i import etmez.
- Output privacy test: çıktıda dosya içeriği yok.
- Full test suite GREEN; CI 4/4.
- Tracked production diff: yalnızca `tanuq/reconciliation.py` (yeni) +
  `tanuq/cli.py` (registrasyon) + yeni test modülü.

## 8. ONE NEXT SINGLE TASK (owner review sonrası)

**V1 implementation task'ı (owner review + GO sonrası):**
`tanuq/reconciliation.py` + `tanuq reconcile` CLI registrasyonu +
`tests/e5_reconciliation_test.py` (yeni modül, G1 uyumlu) — Design-01
§24 test stratejisi ve bu boundary ile sınırlı tek bounded task.

---

*DUR. Bu addendum owner review'siz implementation'a geçilmez.*
