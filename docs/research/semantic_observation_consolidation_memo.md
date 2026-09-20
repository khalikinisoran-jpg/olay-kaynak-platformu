# TANUQ — Semantic Observation & Agent Escape Research Consolidation Memorandum

### STATUS

Owner review sonrası consolidation checkpoint ONAYLANDI.

Bu çalışma yeni experiment değildir.

Amaç:

RUN-01…RUN-06 semantic observation koşumlarını ve E1 + iki correlation probe varyantını tek araştırma memorandumu altında konsolide etmek.

Production implementation kararı bu memorandumun konusu değildir.

---

# 1. KAPSAM

Konsolide edilecek:

* Semantic Observation RUN-01
* Semantic Observation RUN-02
* Semantic Observation RUN-03
* Semantic Observation RUN-04
* Semantic Observation RUN-05
* Semantic Observation RUN-06
* Agent Escape E1 baseline
* E1-C/E1-D correlation probe
* E1-C correlation probe RUN-02

Aşağıdaki production alanları değiştirilmemiştir:

* risk engine
* policy
* authorization
* fingerprint
* approval
* execution
* evidence
* trajectory implementation

Tracked production diff:

**0**

---

# 2. ANA SONUÇ

Araştırma iki ayrı bilgi sınıfı üretti:

## A — Semantic observation primitives

KEEP:

* P1 — Atomic Security Questions
* P6 — Intent ↔ Actual Change
* P7 — Semantic Dangerousness

Bu primitive'ler deterministic governance'ın yerine geçmez.

Observer/raise-only katmanında araştırılmıştır.

## B — Agent Escape detection

E1 enforcement baseline:

* E1-A BLOCKED
* E1-B BLOCKED / fail-closed
* E1-C detection GAP
* E1-D composition GAP

Mevcut enforcement bypass'ı ölçülmemiştir.

Gap esas olarak:

* intent correlation
* cross-proposal lineage
* composition awareness

alanındadır.

---

# 3. P1 — ATOMIC SECURITY QUESTIONS

Karar:

**KEEP**

Bulgular:

* 6 initial dangerous class
* RUN-05 expanded classes
* RUN-06 integrity classes
* V/M paired tests
* 0 FP gözlenen corpus içinde
* dangerous cases'te consistent raise

RUN-04:

Q1–Q8:

**144/144 identical**

RUN-05 ve RUN-06'da expanded corpus ile semantic detection devam etti.

Sınır:

Observer independence:

**PARTIAL**

Aynı observer ile yapılan self-pass koşumları bağımsız external replication değildir.

---

# 4. P6 — INTENT ↔ ACTUAL CHANGE

Karar:

**KEEP**

En robust semantic instrument olarak kaydedilecek.

Ölçülen sonuçlar:

* RUN-01: 5/5 mismatch
* RUN-02: 5/5
* RUN-03: 6/6
* RUN-05: 3/3
* RUN-06: 6/6

Toplam:

**25/25**

Reason visibility masked olduğunda P6'nın information-access abstain üretmesi:

**failure olarak değil, input dependency olarak sınıflandırıldı.**

P6'nın bilgi kaynağı:

**claimed intent/reason**

olarak karakterize edildi.

---

# 5. P7 — SEMANTIC DANGEROUSNESS

Karar:

**KEEP**

Ana araştırma sinyali:

Deterministic baseline bazı semantic dangerous changes'i MEDIUM/auto-apply bandında bırakırken semantic observer bunları yakaladı.

RUN-01:

6/6

RUN-05:

9/9

RUN-06:

18/18

V/M visibility değişimi P7'yi değiştirmedi.

Bu sonuç:

> Semantic dangerousness observation'ın reason-independent olabileceğine dair güçlü araştırma sinyali.

Ancak:

**production capability claim yapılmayacak.**

Observer independence PARTIAL olduğu için bu primitive implementation öncesi bağımsız observer validation beklemektedir.

---

# 6. E8 — GOVERNANCE-INPUT MANIPULATION

Karar:

**KEEP / UNRESOLVED**

Tarihsel gözlemler:

* RUN-01 T4-B
* RUN-05 N3-B

Her ikisinde de Q8 ile ilişkili deceptive-intent anomaly gözlendi.

Ancak:

RUN-02/03/04/06 blind/self-pass koşumlarında aynı pattern sistematik biçimde tekrarlanmadı.

RUN-06:

6 yeni integrity diff:

**0/6 Q8 suppression**

Bu nedenle:

**Q8 deceptive-intent manipulation PROVEN değildir.**

Mevcut en doğru sınıflandırma:

**context-dependent / unresolved**

Self-pass saturation nedeniyle yeni aynı-observer experiment önerilmeyecek.

---

# 7. REASON VISIBILITY

Ana sonuç:

P1/P7 güvenlik observations için:

**Visibility invariant**

RUN-04:

Q1–Q8:

**144/144 identical**

RUN-05 expanded corpus:

tek exception:

**N3-B Q8**

Ancak RUN-06 yeni integrity corpus'ta:

**0/6**

tekrar.

P6 ayrı tutulmalıdır:

P6 reason'ın kendisini bilgi kaynağı olarak kullandığı için reason masking altında abstain üretmesi by-design information dependency'dir.

---

# 8. E1 ENFORCEMENT BASELINE

### E1-A

Direct rejected path:

**BLOCKED**

### E1-B

Equivalent representation:

**BLOCKED / fail-closed**

Fingerprint değişimi:

**ayrı authorization gerekir**

Approval leakage:

**yok**

Single-use:

**CONFIRMED**

Evidence:

* chain VALID
* anchor ACTIVE
* ledger VALID

### E1-C

Alternate allowed path:

**GAP**

Reddedilmiş intent ile sonraki allowed proposal arasında cross-proposal correlation yok.

### E1-D

Multi-step composition:

**GAP**

Birden fazla benign proposal'ın composed effect'i mevcut governed mutation channel dışında gözlenebilir hale gelebildi.

Ancak composed code çalıştırılmadı.

Dolayısıyla bu:

**runtime execution escape proof değildir.**

---

# 9. E1-C CORRELATION PROBE

Baseline similarity:

```text
strict:
0 TP / 8 FP

medium:
0 TP / 8 FP

permissive:
2 TP / 18 FP
```

Permissive:

**detection 0.67**

**precision 0.10**

Ana false-positive:

**legitimate same-path retry**

Sonuç:

> Naive similarity-based correlation güvenilir intent correlation değildir.

---

# 10. SHARED-TARGET-TOKEN PROBE

`shared_target_token` eklenince:

```text
strict:
1 TP / 11 FP

medium:
2 TP / 18 FP

permissive:
3 TP / 18 FP
```

Detection:

**3/3**

Precision:

**0.14**

A3→D1:

baseline 0.131

→ v2 0.431

ve permissive threshold'da yakalandı.

Ancak strict'te yeni false positives oluştu.

Bu nedenle:

> shared-target-token useful observation signal olabilir fakat tek başına intent correlation çözümü değildir.

Production implementation yok.

---

# 11. TWO MEASURED TRADE-OFFS

## Trade-off A — Reason Visibility

P1/P7:

**visible ≈ masked**

P6:

**masked → information-access abstain**

Sonuç:

Reason visibility genel semantic security observation'ı bozmadı.

P6 dependency ayrı tasarım özelliğidir.

---

## Trade-off B — Similarity Detection

Naive similarity:

**detection kazanıyor fakat FP baskın.**

Shared-target-token:

**detection artıyor fakat FP problemi çözülmüyor.**

Özellikle legitimate same-path retry:

**ana false-link mode**

olarak kaldı.

---

# 12. INSTRUMENT INVENTORY

## KEEP

### P1

Atomic Security Questions

### P6

Intent ↔ Actual Change

### P7

Semantic Dangerousness

---

## KEEP / UNRESOLVED

### E8

Governance-Input Manipulation

### Q8 deceptive-intent sensitivity

Historical observation mevcut fakat systematic mechanism unresolved.

---

## RESEARCH GAP

### E1-C

Cross-proposal intent correlation

### E1-D

Composition awareness

---

# 13. AUTHORITY BOUNDARY

Bütün semantic/correlation araştırmalarında:

Observer:

* authorization yapmadı
* approval oluşturmadı
* policy değiştirmedi
* fingerprint değiştirmedi
* execute etmedi
* evidence authority kullanmadı

Bu ayrım korunmuştur:

```text
Observation
     ≠
Governance
     ≠
Authorization
     ≠
Execution
```

---

# 14. EN ÖNEMLİ METODOLOJİK SINIR

Observer independence:

**PARTIAL**

İkinci insan veya bağımsız local model mevcut değil.

RUN-02'den itibaren environment taraması bunu doğruladı.

Ayrıca RUN-06 itibarıyla observer instrument'e primed durumdadır.

Bu nedenle:

> Aynı observer ile yeni self-pass experiment yapmak mevcut unresolved independence problemini çözmez.

---

# 15. TEK RESEARCH GATE

Semantic observation thread için yeni experiment üretme.

Thread şu durumda:

**SATURATED / WAITING FOR INDEPENDENT OBSERVER**

Gelecekte bağımsız observer erişildiğinde:

### Fresh Observer Replication Probe

Frozen corpus:

* T4-B
* N3-B
* I1–I6
* expanded semantic corpus

aynı blindness protocolüyle çalıştırılacak.

Amaç:

* historical Q8 anomalies
* P1
* P6
* P7

sonuçlarını labeler-dışı observer ile test etmek.

Bu gate aşılmadan semantic observation production implementation'a geçirilmemeli.

---

# 16. JEV / PROVIDER SONUCU

Bu araştırma boyunca:

* JEV entegrasyonu yapılmadı.
* provider dependency eklenmedi.
* API dependency eklenmedi.

Araştırma sonucu technology-first değil:

```text
technology
   ↓
primitive hypothesis
   ↓
controlled experiment
   ↓
measurement
   ↓
architecture candidate
```

şeklinde ilerledi.

Bu nedenle JEV:

**research inspiration / optional implementation candidate**

olarak kalır.

Primitive dependency değildir.

---

# 17. PRODUCTION KARARI

Bu memorandumdan:

**P1/P6/P7 production-ready**

sonucu çıkarılmayacak.

Mevcut doğru durum:

```text
P1 KEEP
P6 KEEP
P7 KEEP

       ↓

Independent Observer Gate

       ↓

Implementation Decision
```

E8:

```text
KEEP / UNRESOLVED
```

E1-C:

```text
NEEDS MORE EXPERIMENT
```

E1-D:

```text
NEEDS MORE EXPERIMENT
```

---

# 18. RESEARCH THREAD STATUS

Semantic Observation:

**SATURATED — WAITING FOR INDEPENDENT OBSERVER**

E1 correlation:

**NEEDS MORE EXPERIMENT — current similarity approach insufficient**

E1 composition:

**NEEDS MORE EXPERIMENT — negative corpus insufficient**

Production core:

**FROZEN**

---

# 19. ONE NEXT SINGLE TASK

Semantic thread açısından:

**Fresh independent observer replication probe**

Ancak bu task yalnızca bağımsız observer erişilebilir olduğunda yapılacak.

Observer erişilebilir değilse yeni self-pass experiment oluşturulmayacak.

Bu noktada yeni araştırma hattına geçilebilir.

---

# GT CORRECTION LOG (consolidation edit)

Tek düzeltme: §4 P6 toplam istatistiği "15/15" → **25/25**
(5+5+6+3+6; RUN-01…RUN-06 mismatch detection toplamı, 0 missed, 0 false).
Başka hiçbir deney sonucu değiştirilmedi.

---

# FINAL OWNER REVIEW

* P1: **KEEP**
* P6: **KEEP**
* P7: **KEEP**
* E8: **KEEP / UNRESOLVED**
* E1-C: **NEEDS MORE EXPERIMENT**
* E1-D: **NEEDS MORE EXPERIMENT**
* Reason visibility: **P1/P7 invariant; P6 information-dependent**
* Similarity detection: **FP-dominated**
* Observer gate: **INDEPENDENT OBSERVER REQUIRED**
* Production implementation: **NOT YET**

**DUR. Owner review bekle.**
