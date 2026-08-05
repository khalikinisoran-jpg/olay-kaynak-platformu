# Event-Sourced AI Runtime
# IDEA BACKLOG

Bu dosya, projeye yön verebilecek fikirleri içerir.

Kural:

Bir fikir doğrudan koda dönüşmez.

Her fikir şu aşamalardan geçer:

Fikir

↓

Mimari değerlendirme

↓

Roadmap

↓

Sprint

↓

Kod

↓

Test

↓

Timeline

↓

Verify Chain

↓

Release

------------------------------------------------------------

# IDEA-001

Ad

Loop Engineering

Kaynak

Poyraz - Loop Engineering videosu

Özet

AI yalnızca cevap vermemeli.

Bir hedefe ulaşana kadar;

Plan oluşturmalı,
çalışmalı,
doğrulamalı,
gerekirse tekrar denemeli.

Temel Döngü

Trigger

↓

Goal

↓

Plan

↓

Execute

↓

Verify

↓

Retry

↓

Completed

Bizdeki Karşılığı

UserQuestionReceived

↓

Kernel

↓

Agent

↓

Event Store

↓

Timeline

↓

Verify Chain

↓

Loop Engine

Mevcut Durum

Altyapı hazır.

Eksik bileşen:

Loop Engine

Planlanan Sprint

Sprint-7A

Öncelik

★★★★★

------------------------------------------------------------

# IDEA-002

Ad

Decision Trace

Amaç

AI neden bu kararı verdi?

Timeline sadece

"Ne oldu?"

değil,

"Neden oldu?"

sorusunu da cevaplayacak.

Örnek

PlanCreated

↓

ReasonGenerated

↓

DecisionAccepted

Durum

Planned

------------------------------------------------------------

# IDEA-003

Ad

Event Query Engine

Amaç

AI kendi geçmişini okuyabilmeli.

Örnek Sorular

Son 10 event nedir?

Kaç AI cevabı üretildi?

İlk kullanıcı sorusu neydi?

En çok oluşan event tipi hangisi?

Durum

Planned

------------------------------------------------------------

# IDEA-004

Ad

Worker Runtime

Yeni Eventler

WorkerRegistered

WorkerRemoved

WorkerBusy

WorkerIdle

TaskAssigned

TaskCompleted

Durum

Planned

------------------------------------------------------------

# IDEA-005

Ad

Multi-Agent Runtime

Planner

↓

Coordinator

↓

Worker

↓

Verifier

↓

Reviewer

Her ajan Event Store üzerinden haberleşecek.

Durum

Future

------------------------------------------------------------

# Mühendislik İlkesi

Kutup yıldızları yön gösterir.

Yolu ise çalışan kod belirler.

Yeni fikirler ilham verir.

Kararı;

Replay,

Timeline,

Verify Chain,

ve çalışan sistem verir.