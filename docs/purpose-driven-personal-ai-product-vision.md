# Product Vision: Purpose-Driven Personal AI

**Working title:** Purpose-Driven Personal AI
**Document type:** Product Vision
**Status:** Early concept / foundation for product discovery
**Version:** v6.3 — minimal required human decisions: defaults over approvals, reversibility as the licence
**Revised:** September 2, 2026

---

## 1. Vision

Build a personal AI system that stays meaningfully synchronized with a human — not by trying to remember everything equally, but by organizing knowledge around the outcomes the human is trying to achieve.

The long-term vision is a **human–AI working relationship** in which:

- AI performs most of the information processing, drafting, analysis, and coordination;
- humans remain responsible for intent, judgment, priorities, values, and important decisions;
- the AI continuously understands enough of the human's goals, work, and context to act as an effective extension of that person;
- keeping the AI informed requires relatively little effort from the human.

The knowledge base underneath that relationship is **consumer-agnostic**. It is shared working knowledge usable by a human, an AI agent, another software system, or any combination. It should not couple itself to who ultimately consumes an outcome.

The central product problem of the AI era follows:

> **How do we keep the human mind and the AI's working context sufficiently synchronized so that they can operate as one effective system?**

---

## 2. The Problem

An AI can only be useful when it has the right context, and most of the context that matters lives outside it: in the human's head, in conversations and meetings, in documents, in decisions made months ago, in changing priorities, in accumulated experience.

So people repeatedly explain themselves to AI systems — what they are working on, what happened earlier, what constraints exist, what was already decided, what changed, what they want next.

### The personalization paradox

The more an AI knows about a person, the more useful it can be. But collecting, organizing, and maintaining that information takes time, and most people will not become full-time curators of their own data. **A useful personal AI cannot depend on the user doing the curation.**

### Why "collect more" is not the answer

Most AI memory and "second brain" systems focus on collecting: record every meeting, save every document, index everything, put RAG over the corpus. This improves recall without solving the problem. If everything is stored with equal importance, relevant information competes with irrelevant information, old information conflicts with current information, decisions are buried among low-value details, and the user still has to reconstruct context. A better retrieval algorithm does not fix that.

The problem is not that a data lake is bad. The problem is expecting the data lake to *be* the personalized intelligence layer.

---

## 3. Core Insight: Purpose Comes Before Useful Memory

The missing organizing principle is **purpose**:

> **What is this knowledge supposed to help the human accomplish?**

Purpose tells the system what matters, what can be ignored, what should be tracked over time, which contradictions must be resolved, and which changes are significant.

The unit of that organization is a **Knowledge Space**: a bounded body of knowledge serving one goal, or a very small number of closely related goals. Examples:

- Launch my product and get the first 20 paying customers.
- Help me successfully lead Project X.
- Help me manage and improve my personal finances.
- Help me prepare my child for school.

> **Capture can be broad. Retention is demand-informed. Assembly must be purpose-driven.**

**Purpose is not descriptive metadata.** It actively governs both what knowledge the system learns and retains, and which relevant claims it assembles for a particular outcome.

---

## 4. The Two-Layer Model

- **Layer 1 — Raw Information Lake.** One per system. Immutable, append-only, permissive.
- **Layer 2 — Knowledge.** One or more Knowledge Spaces. Each has one purpose, maintains claims, and produces outcomes.

**v1 has exactly one space.** A person eventually has several purposes, and the model's answer to that is a network of spaces — but that is a growth path, not a v1 feature (Appendix A). What v1 must do is stay cheap to grow into.

### 4.1 Layer 1 — Raw Information Lake

Intentionally permissive. The user should be able to put information in without deciding where it belongs.

Inputs may include conversations, voice notes, transcripts, emails, documents, screenshots, web pages, notes, calendar events, messages, photos, imported application data, and — importantly — **corrections, decisions, and real-world results produced anywhere else in the system**.

> **If the user thinks something might matter, make it easy to capture it.**

Some of it will never become useful. That is acceptable.

Immutability is not a stylistic preference: it preserves the original evidence so extraction and reconciliation logic can improve later without rewriting what actually entered the system.

There is exactly **one** lake. Multiple lakes would reintroduce a routing decision at capture time, which is the friction the lake exists to remove.

The lake is the one place where content lives as bytes in object storage. Every source is still registered in the database so that evidence links resolve to an identity and a locator rather than to a file path (§9.2).

### 4.2 Layer 2 — Knowledge

Raw information is filtered, extracted, reconciled, and maintained as knowledge **inside a space**. A space has:

- **one purpose**;
- **claims** — named, typed, versioned, evidence-linked units of knowledge, organized by topic and owned exclusively by that space;
- **outcomes** — persisted views assembled from claims for a specific purpose;
- **a published interface** — the small subset of outcomes and claims that anything outside the space may bind to;
- **one owner** (in v1, always the user).

```
┌─ Knowledge Space ────────────────────────────┐
│  Purpose (one goal, or a few related ones)   │
│        ↓                                     │
│  Claims      canonical: named, typed,        │
│              versioned, evidence-linked,     │
│              organized by topic              │
│        ↓                                     │
│  Outcomes    derived views: immutable        │
│              versions with build manifests   │
│        ↓                                     │
│  Published   the subset others may bind to   │
└──────────────────────────────────────────────┘
```

The knowledge layer answers: *what is currently true, and currently believed, in service of this purpose?* It is deliberately **not** a summary of the raw layer. New information can confirm, update, supersede, contradict, or add nuance to what is already held.

> **Claims are canonical. Outcomes are derived views over claims.**

### 4.3 Topic decides where; purpose decides whether

Within a space, claims are organized **by topic**. Subject-oriented organization gives reconciliation a single home and lets internal representation evolve without breaking bindings. Every claim has exactly one owning topic.

The cost of topic organization is that topic relevance is broad — left alone, a space drifts into being a second, smaller data lake. Purpose is the counterweight: a claim earns its place because it serves the space's purpose, and **demonstrated use is the evidence that it does**.

- **Topic decides where a claim lives.**
- **Purpose decides whether it should exist at all.**
- **Outcome bindings are the running record of which claims have proven necessary.**

> **Design decision (resolves a contradiction in v5).** Retention is *demand-informed*, not strictly demand-gated. Extraction may run on capture; a claim does not require a pre-existing outcome to be created. But claims that no outcome has ever needed are prunable, and the binding record is what tells the system which those are. The strict version — "an active claim with no outcome dependency is a model violation" — is unimplementable alongside a capture-time extraction loop, and forcing the two to agree was adding machinery without adding value.

When a new outcome requires knowledge the space does not have, the space consults raw sources, derives the needed claims, persists them with lineage, and binds the outcome to them as one operation (§6.4).

### 4.4 Outcomes: snapshot or maintained

Every outcome version is persisted as an immutable artifact with a build manifest. The only difference between the two kinds is **maintenance policy**:

- **Snapshot** — one stored version; later signals do not refresh it. An ad-hoc request is therefore not disposable; it becomes a durable record of what was needed and what was produced.
- **Maintained** — a logical outcome with a version history. When a bound claim changes materially, regeneration creates a new version and designates it current; older versions remain.

There is no promotion lifecycle. Changing the policy is a property change, not a migration — which is what allows the choice to be **defaulted rather than asked**. Every outcome starts as a snapshot. It becomes maintained when the system observes demand for currency: the same outcome is requested again, another outcome binds to it, or the user acts on it repeatedly. The user may override at any time and never has to decide up front.

Persisting outcomes also gives **pre-computed context packing** for reasoners under a context budget, which is a real consumer of this system.

---

## 5. Contracts: Names Are the Interface

A space exposes **named, typed, addressable** claims and outcomes. Consumers bind to those names.

> **Anything outside a space binds only to its published interface, never directly to its internal claims.**

An outcome does not say "read the Project X topic." It says "I depend on `project-x.current-scope`, `project-x.committed-date`, `people.sponsor.identity`."

This buys three things:

1. **Targeted invalidation.** When a claim changes, exactly the maintained outcomes bound to it can become stale.
2. **Computable blast radius.** The number of affected maintained outcomes is known, which makes it possible to rank what a change touches and to express any change in outcome terms rather than graph terms (§8).
3. **Representation freedom.** Internal representation can change without breaking consumers, as long as the named claims still resolve.

### 5.1 Claim versions are superseded, never overwritten

A named claim may have multiple immutable versions, with one designated current. Each version records the evidence it derives from, when it became current, when it stopped being current, and what replaced it on what evidence.

This is a slowly changing dimension in the classical sense. The property that matters: **"why did this outcome change?" is answerable**, and any historical outcome can be reproduced from the claim versions it was built from.

### 5.2 Every outcome version carries a build manifest

The manifest is the exact set of claim versions the outcome was assembled from. It makes regeneration a diff between two explicit builds rather than a mystery, and makes *what did this say before, what changed, and why?* directly answerable.

---

## 6. Propagation and Maintenance

Both outcome modes use the same knowledge path — assemble from claims, persist an immutable version and manifest. The difference is only whether the outcome participates in future maintenance.

### 6.1 Lineage in every hop

The system records which raw items support which claim, and which claims feed which outcome. Without lineage, every new input forces broad recomputation — expensive, and worse, **nondeterministic**: re-derivation drifts, so an unchanged source can produce a changed result and trust erodes.

### 6.2 Materiality, not immediate recompute

The sequence is: claim changes → find bound **maintained** outcomes → mark potentially stale → let something cheap decide whether the change is **material** to each one → regenerate only where it is. Regeneration produces a new version with a diff and the triggering evidence attached.

Snapshot outcomes never enter this path.

Whether regeneration is automatic or gated on review is a **per-outcome property**, not a system-wide policy. That property is **set by the system, not by the user**: regeneration is automatic by default, and an outcome escalates to gated when its own correction history says it should (§8). The user can pin either value; they are not asked to choose one.

### 6.3 The reverse edge

The most valuable learning signal is an authoritative correction, decision, or real-world result arriving at the outcome boundary — usually from the human.

If a correction lives only in the outcome, the same error recurs next time, and the fix is silently overwritten on the next regeneration. Corrections therefore flow **upward**:

1. The correction lands in the raw layer as a source — it is new evidence about the world or about the user's intent.
2. It updates or supersedes the claim that produced the error.
3. Bound maintained outcomes are reconsidered; snapshot outcomes remain historical records.

**An architecture with only downward arrows cannot learn from outcomes.**

### 6.4 Gap filling

Raw→knowledge is lossy, so the knowledge layer will eventually be insufficient for some outcome. The escape hatch to raw information must preserve the rule that outcomes depend on claims:

1. search or inspect raw sources;
2. derive the missing information;
3. create or reconcile normal claims, recording source→claim lineage;
4. bind the outcome to them and persist the outcome with its manifest.

This is a **gap-resolution path**, not a parallel path that bypasses the knowledge layer. New problems enrich the shared knowledge base even when the resulting outcome will never be maintained.

### 6.5 Idempotency lives in storage

In a deterministic pipeline, idempotency comes from transform purity. That guarantee does not exist here, so it must be enforced at the **storage layer** — content-addressed keys, stable claim slots, or equivalent — so the same source producing the same fact does not create a second competing current claim.

---

## 7. What This Is Not: Differences from Data Engineering

Decades of data engineering practice are relevant, and the project should borrow deliberately. Three borrowings are load-bearing:

- **Immutable raw with reprocessing optionality.** Most AI memory systems treat memory as one mutable store, which means an improved extractor can no longer inspect the original evidence.
- **Slowly changing dimensions.** §5.1 is SCD Type 2.
- **Structural-invariant testing.** You cannot assert that an extracted claim is correct. You can assert that every claim resolves to live evidence, that no two current claims occupy the same slot with contradictory values, and that every claim an outcome binds to exists. Correctness moves to sampling and human review.

Four differences force design decisions:

**One important consumer is a reasoner under a context budget, not a query engine.** A warehouse answers "can this question be answered." Here the system must also answer "does the right subset fit." Selection and compression are first-class concerns, and persisted outcome views are part of the answer.

**Truth is contested, not merely late-arriving.** Sources can legitimately disagree and the user can change their mind. **Contradiction is a representable state**, not an error condition.

**The human is an input channel.** No warehouse can ask a question. The cheapest way to resolve ambiguity is to ask the user, which means a **question queue prioritized by value of information**, designed deliberately rather than left to emerge as ad hoc chat.

**Volume is tiny.** Thousands of claims, not billions of rows. Full traversal, expensive per-item processing, and per-item human review are all affordable. **Small-N is a design advantage to spend, not a limitation to work around.**

Three things explicitly not borrowed: a **global schema or ontology defined up front** (schema should emerge); **pipeline-centric architecture and scheduling** (the knowledge artifact is primary, processing is opportunistic and event-driven); and **completeness** (§14 — completeness thinking is the gravitational pull that drags the knowledge layer back into being a second data lake).

> Data engineering treats the **pipeline** as the asset, reprocessing as **cheap**, and **completeness** as the goal.
>
> This system treats the **knowledge artifact** as the asset, reprocessing as **expensive and lossy**, and **sufficiency** as the goal.

---

## 8. Human Review: Minimal, Earned, and Reversible

The pattern is **AI does the work, human reviews what matters** — it substitutes for deterministic data-quality gates where judgment is required. Applied uniformly it fails, because review requests scale with input volume and the queue becomes the new job. A system that asks for a decision every time it is unsure has moved the work, not removed it.

> **Decisions are defaulted, not asked. Structure is applied, not approved. The human corrects rather than pre-approves.**

### 8.1 Reversibility is what licenses the default

Pre-approval buys protection against changes that cannot be undone. Inside this knowledge layer, almost nothing qualifies. Claim versions are superseded, never overwritten (§5.1); outcome versions are immutable and additive (§4.4); change records make every mutation causally traceable and revertible as one operation (§9.5); and consumers bind to names, so internal reorganization cannot break them (§5).

So the question for any change is not "how big is it?" but **"can it be undone?"** Reversible changes are applied. Only these require approval before the fact:

- **deletion from the raw layer** — the one genuinely irreversible act in the system (§19 Q4);
- **actions with effects outside the knowledge base** — sending, publishing, purchasing, committing on the user's behalf;
- **sharing or exposing knowledge to another party** (a multi-writer concern, Appendix B).

Everything else — new claims, supersessions, contradictions, topic boundary changes, space splits, bulk migrations, outcome regeneration — is applied and made visible.

### 8.2 Escalation is learned, not configured

A blanket "apply everything" would be reckless in areas where the system is demonstrably wrong. Rather than asking the user to configure strictness, the system derives it per outcome and per topic from its own correction history:

| State | Behaviour | Entry condition |
|---|---|---|
| **Silent** | Applied; visible only in the inspection view | Default |
| **Flagged** | Applied; surfaced in the Inbox as "this changed, and why" | Wide blast radius, weak evidence, or a recent correction nearby |
| **Gated** | Queued for approval before taking effect | Sustained correction rate in this outcome or topic |

Escalation and relaxation are automatic. The system gets stricter exactly where it has been wrong and quieter where it has been right, so the review burden tracks **demonstrated unreliability** rather than input volume. Blast radius still matters — it ranks what to show first — but it no longer decides *whether* to ask.

### 8.3 Ask at the point of use, not the point of ingestion

Most ambiguity never matters. A contradiction is a representable state (§7), not an error demanding immediate resolution: the system carries both readings with uncertainty visible (Principle 7) and asks only when an outcome actually depends on the resolution. Clarification questions are ranked by value of information, batched, budgeted to a small number per period, and allowed to expire. **No outcome ever blocks on an unanswered question** — the system proceeds with its best current understanding and marks the uncertainty in the result.

### 8.4 Three cheap substitutes for exhaustive review

Approval never made claims correct; §7 already concedes that correctness moves to sampling and human review. Three mechanisms deliver that more cheaply than a queue:

**Use is review.** Every use of an outcome is an implicit check, and every correction is an explicit one that already routes upward to the owning claim (§6.3). Correcting the outcome in front of you costs nothing extra; approving a change you have no context for costs attention.

**Sampling audit.** A small random sample of recent claim changes is offered for verification on a periodic pass. Small-N (§7) makes this affordable, and its cost is fixed by the sample size rather than by how much information entered the system.

**Undo as a first-class action.** Because every applied change has a change record, "revert this" is a supported operation on anything the user disagrees with — which is what makes applying-by-default honest rather than merely convenient.

### 8.5 The budget

Required decisions per week should be **a small constant**, not a function of input volume. §17 tracks this. If it climbs with capture volume, the review model has failed regardless of how good the knowledge is, and the correct response is to convert the most frequent decision back into a default.

---

## 9. Storage Substrate

> **Design decision (v6.2).** Object storage holds **source bytes**. The **database is the system of record for the entire knowledge layer** — claims, claim versions, outcomes, manifests, bindings, lineage, and change history, including their content and not merely their structure. Earlier versions placed claim-version and outcome-version content in object storage; that split has been withdrawn.

### 9.1 Why the knowledge layer is not files

Nearly every load-bearing operation in this model is a join or a small graph traversal over many small records:

- **targeted invalidation** (§5) — a claim version changes, find the maintained outcomes bound to it;
- **blast radius** (§8) — count and rank those outcomes to tier review;
- **"why did this change?"** (§5.2) — manifest → claim versions → supersession chain → evidence;
- **structural invariants** (§7) — every claim resolves to live evidence, no two current claims occupy the same slot with contradictory values, every bound claim exists;
- **idempotency** (§6.5) — stable slots, exactly one current version per slot;
- **gap filling** (§6.4) — create claims, record lineage, and bind an outcome **as one operation**.

Over a blob store, each of these requires a hand-built index that must be kept consistent with the blobs — which is a database, written badly and without transactions. In a relational database they are foreign keys, a partial unique index on `(space_id, topic_id, claim_name) WHERE is_current`, a transaction, and a recursive query.

Scale does not argue the other way. At 1000+ spaces with thousands of claims each and several versions per claim, the knowledge layer is single-digit millions of rows — unremarkable for a single relational instance. The §7 observation that volume is tiny still holds; it argues for affordable per-item processing, not for file-based storage.

### 9.2 The split

- **Object storage — source bytes only.** Transcripts, documents, screenshots, audio, photos, imported exports. An abstraction, not a vendor commitment: local files first is fine.
- **Database — everything else.** Every Source also has a **row**: identity, content hash, captured-at, channel, media type, and the blob URI. Lineage and evidence links point at source identities and locators, never at URIs. Extracted text and segment locators live in the database too, because evidence should resolve to "paragraph 14 of this transcript," not to a 40 MB file.
- **Claim versions live entirely in the database.** Payload as a document/JSON column so claim types stay open (§12), with structured columns only for what the invariants and queries need: identity, space, topic, name, type, version, validity window, supersedes, author, timestamp.
- **Outcome versions are the one hybrid.** Manifest and metadata are always rows. The rendered body is normally a few kilobytes of text and belongs in the database as well. Spill to object storage only when an outcome genuinely *is* a file — a generated deck, a PDF — via a size threshold and a pointer column.

### 9.3 What the database must now enforce that a blob store gave for free

Append-only storage made immutability structural. A database makes it a discipline, so it has to be enforced deliberately:

- version tables are **insert-only**; the only mutation is advancing a current-version pointer, ideally held in its own table rather than as a flag;
- change records are an **append-only ledger**;
- `UPDATE`/`DELETE` on version and change tables is denied at the database level (trigger or role permission), not merely avoided in application code.

The KB's history remains represented explicitly in its own data model. The architecture does not depend on Git, on blob-store versioning, or on any storage-engine feature to represent supersession.

### 9.4 Supporting commitments

**One database, not several.** A relational engine with document columns, vector search, and recursive queries covers the open claim types, embedding retrieval, and the space DAG. The network in Appendix A is shallow and small; it does not justify a separate graph store.

**Space identity is on every row.** `space_id` is already required from the first write (§16). Carrying it on every row makes it the natural key for row-level access control — the seam the multi-writer path in Appendix B will need.

**Periodic export to object storage.** Once the database is the system of record for the asset this thesis says matters most, a plain portable snapshot of the knowledge layer (line-delimited JSON per table, written to object storage on a schedule) covers disaster recovery and user data portability. It is a complement, never on the hot path.

### 9.5 Change Records carry causality

Version history says *what* changed; trust also requires *why*. A change record captures the change, the previous and new versions, the triggering source or decision, who or what made or approved it, and when. One change record may group several mutations from the same causal event — a new source superseding one claim and regenerating three outcomes shares one change ID. This lets the database answer *what did I believe on this date?*, *what changed since then?*, and *why did this outcome change?*

---

## 10. The Core Loop

1. **Establish the purpose.** What the space is for — desired outcome, why it matters, success criteria, constraints, time horizon. The human is not asked to author this before doing anything useful: the system drafts it from the first outcomes requested (§15) and keeps it current as a versioned claim like any other. The human edits it when the draft is wrong, which is a correction, not a setup step.
2. **Capture.** Very low friction; capture must be easier than organization. Connect to existing sources with permission to reduce manual entry.
3. **Interpret and extract.** AI evaluates incoming information against the purpose and identifies durable knowledge: facts, decisions, constraints, preferences, commitments, risks, open questions.
4. **Reconcile.** New information confirms, updates, supersedes, contradicts, or adds nuance. The system maintains a current best understanding rather than appending statements forever.
5. **Assemble outcomes.** Purpose decides which relevant claims are included now. The outcome is persisted with its bindings and manifest.
6. **Act.** The AI answers questions, drafts work, prepares decisions, identifies missing information, suggests next steps, monitors progress, and prepares the human for judgment calls.
7. **Learn.** Corrections and real-world results enter as raw evidence, supersede claims, and stale the maintained outcomes bound to them (§6.3).

---

## 11. Core Principles

1. **Purpose before organization.** Do not ask the user to design folders, ontologies, or taxonomies before the system is useful.
2. **Capture first, structure later.** Input friction extremely low; AI does the organizing.
3. **Raw memory and useful knowledge are different things.** Never treat the archive as the AI's working memory.
4. **Relevance is purpose-dependent.** The same fact can be essential for one purpose and irrelevant for another.
5. **Memory evolves.** Maintain current understanding; supersede rather than accumulate.
6. **Minimize synchronization cost.** The system fails if keeping it informed becomes another job.
7. **Preserve provenance and make uncertainty visible.** Knowledge retains a link to its evidence; conflicts, gaps, and low confidence are explicit rather than smoothed over. Source information stays distinguishable from AI-generated conclusions.
8. **Derived knowledge is an asset, not a cache.** Re-derivation is expensive and nondeterministic, so knowledge is preserved and versioned rather than regenerated on a whim.
9. **Corrections travel upward.** A fix applied only to an outcome will be undone the next time it regenerates.
10. **Review scales with consequence, not volume.** Human attention is reserved for what is irreversible or externally consequential, and for areas the system has demonstrably got wrong; everything else is applied, recorded, and revertible.
11. **Knowledge is consumer-agnostic.** The knowledge layer does not encode whether the next consumer is a human, an agent, or another system.
12. **The knowledge base is grown, not designed.** Claims — and later, spaces — accrete from demonstrated demand, not in anticipation.
13. **Default rather than ask.** Any decision the system can make and later reverse, it makes. Pre-approval is reserved for the irreversible and the externally consequential. A feature that adds a required human decision must justify why it cannot be a default with an undo.
14. **Outcome-first, structure-on-demand.** The human works with outcomes and their purpose. Topics, claims, bindings, and the space network are always inspectable and never required knowledge; structural changes are expressed in terms of the outcomes they affect, not the graph they alter.

---

## 12. Core Objects

The first implementation does not need a complex ontology. Seven objects carry the model:

| Object | Definition |
|---|---|
| **Source** | Raw information entering the system. Immutable. |
| **Space** | A bounded body of knowledge serving one purpose. Owns topics, claims, and outcomes; exposes a published interface. v1 has one. |
| **Topic** | The subject that owns a set of claims inside a space. Emergent rather than pre-designed and **fully AI-managed**: because outcomes bind to claim names, re-homing a claim cannot break a consumer, so boundary changes are applied with a redirect and a change record rather than queued for approval (§8.1). Every claim belongs to exactly one topic. |
| **Claim** | A named, typed logical unit of knowledge owned by one topic. May have many immutable **versions**, one designated current, each evidence-linked with its validity period and supersession record. Types are open: fact, decision, preference, constraint, observation, hypothesis, risk, question, lesson, and others as needed. |
| **Outcome** | A persisted view over claims serving one specific purpose. Has a maintenance mode (snapshot or maintained) and one or more immutable **versions**, each with a build manifest. |
| **Binding** | The declared dependency from an outcome version to the claim versions it used. The unit of provenance, targeted invalidation, and correction routing. A build manifest is the binding set of one outcome version. |
| **Change Record** | A durable record explaining a meaningful KB change: what, why, when, by or approved by whom, on what triggering evidence, affecting which versions. |

Entities — people, organizations, projects — are resolved once so the same person does not exist three times. In v1 that registry is a **topic inside the single space**, not separate infrastructure.

---

## 13. Conceptual Architecture

```mermaid
flowchart LR
    subgraph L1["Layer 1 — Raw Information Lake"]
        R["Everything captured<br/>Immutable • Append-only"]
    end

    subgraph L2["Layer 2 — Knowledge Space"]
        CL["Claims — canonical<br/>topic-owned • versioned • evidence-linked"]
        OU["Outcomes — derived views<br/>immutable versions • build manifests"]
        CL --> OU
    end

    C["Humans • AI agents • Other systems"]
    P["Purpose"]

    R -->|"learn / gap filling"| CL
    OU -->|"use"| C
    C -->|"corrections / new evidence"| R
    P -.->|"defines the space"| L2
```

The important separations:

- **Raw information** preserves what entered the system. There is exactly one lake.
- **The space** maintains the current best understanding needed for one purpose.
- **Claims are canonical; outcomes are derived from them** and bound to the exact versions used.
- **Consumers are outside the architecture.** The same knowledge serves humans, agents, and other software without changing the model.

Substrate: **object storage for source bytes; the database for the whole knowledge layer** — claim and outcome content as well as identity, versions, lineage, bindings, and change history (§9).

---

## 14. Sync Should Be Selective, Not Exhaustive

The system does not need to know everything about a person or project. It needs **enough of the right things for the outcomes that matter**.

The objective is not `Human Brain = AI Memory`, nor `Raw Data = Knowledge Base`. It is closer to:

> Goal-relevant shared context ≈ what the human–AI system needs to work effectively

Optimize for **sufficient** synchronization, not complete synchronization. Cold starts at the edges are acceptable; the important property is that resolving one leaves reusable knowledge behind.

---

## 15. Bootstrapping: Start from the Outcome

Cold start is not only a new-knowledge-base problem. It occurs whenever the knowledge layer is insufficient for a desired outcome — both when the KB is new and when a mature KB meets a new problem. Both use the same mechanism:

1. Ask what needs to be produced or decided **now**.
2. Attempt to assemble it from existing claims.
3. Where knowledge is insufficient, consult raw sources and/or request the minimum additional context.
4. Create or reconcile the missing claims and record lineage.
5. Produce and persist the outcome with its bindings.

The knowledge layer therefore accretes **backwards from demonstrated demand**. The first interaction on a new problem still delivers value instead of requiring weeks of setup, and the same area becomes progressively warmer.

The purpose model is elicited **through** actual outcomes rather than demanded before any useful work is done.

---

## 16. MVP

### Hypothesis

> **A purpose-driven knowledge layer can make a personal AI meaningfully more useful than an AI operating directly over a large unstructured memory store.**

The MVP does not need to ingest a person's digital life. One purpose, one space, a few input channels.

**Keep the later network cheap without building it:**

- every claim records its owning space from the first write;
- outcomes are addressable by name, so publishing one later is a property change, not a migration;
- bindings are stored explicitly, so a cross-space binding is the same mechanism with a different endpoint;
- every claim has an author and a timestamp, so multi-writer attribution is not a backfill.

The second space appears when the first one's purposes visibly diverge (Appendix A).

### Experience

1. The user names something that needs to be produced now — the first outcome.
2. The system checks existing claims.
3. Where knowledge is insufficient, the system consults raw sources and proceeds with its best understanding, marking what it is unsure of rather than stopping to ask.
4. The system creates or reconciles the claims the outcome requires, with evidence and lineage.
5. The outcome is persisted as an immutable version bound to the exact claim versions used, and delivered.
6. Maintenance mode is defaulted, not asked: snapshot at first, promoted to maintained when demand for currency appears (§4.4).
7. The user reacts to the outcome. Corrections and decisions flow upward as new raw evidence and may supersede claims — this is the primary review channel (§8.4).
8. New signals stale only maintained outcomes; a material refresh creates a new version and advances the current pointer, applied silently or surfaced in the Inbox according to §8.2.
9. Clarification questions are budgeted, batched, and expirable; nothing blocks on them.

**The first session should require zero setup decisions.** No purpose statement, no maintenance policy, no topic structure, no review preferences — only a request and a result.

### Initial views

- **Goal** — what are we trying to accomplish?
- **Inbox** — what entered the system, what did it change, what is now stale, and what — rarely — needs a decision?
- **Collaborate** — what should the human and AI think about, decide, or do next?
- **Knowledge** — read-only inspection of what the system currently understands, how it is organized, and why anything changed.

The first three are the working surface. **Knowledge is inspection, not operation** (Principle 14): it is always available, never required to get value, and read-only — a correction made from it enters as new evidence rather than editing a claim in place, because a fix applied directly to knowledge has no reconciliation record (§6.3). It also serves as the builder's debugging and evaluation surface for a process that is nondeterministic by construction.

The user should be *able* to see the evolving shared working model rather than interacting only through a chat window — and should never be *obliged* to.

### What the MVP should not try to be

A universal life-logging platform; a replacement for every note-taking app; a document management system; an enterprise knowledge graph; an unbounded autonomous agent; a perfect memory of a life; an ontology-design product; a generic RAG platform; a workflow orchestration platform; a complete data warehouse for a person's life; a system that asks approval for everything; a system with a settings page for review policy; or a network of thin spaces built before one space has demonstrated value.

---

## 17. Measuring Whether the Bet Is Working

### Primary metric — knowledge layer sufficiency rate

> What fraction of desired outcomes can be produced from the knowledge layer without dropping to raw sources or requesting new context?

If this does not climb within recurring problem areas, the core bet is wrong or the knowledge layer is retaining the wrong things.

### Supporting metrics

- **Correction rate on regenerated maintained outcomes** — does propagation produce trustworthy results?
- **Required decisions per week** — a **constraint, not an observation**. The target is a small constant, flat with respect to capture volume. If it correlates with how much information entered the system, §8 has failed and the most frequent decision must be converted back into a default with an undo.
- **Correction rate by topic and outcome** — the control signal that drives escalation and relaxation in §8.2, not merely a quality report.
- **Sampling audit agreement rate** — of the sampled claim changes a user checks, what fraction do they accept? This is the evidence that applying-by-default is safe.
- **Gap-to-claim latency** — how long from discovering missing knowledge to having the claim available?
- **Knowledge reuse rate** — how often do new outcomes reuse existing claims rather than creating new ones?
- **Synchronization time per day** — human effort to keep real-world context current. The aspiration is tens of minutes per day or less, yielding many hours of leveraged assistance.
- **Stale maintained-outcome ratio** — how much is currently out of date relative to its bound claims?

---

## 18. Differentiation and the Bet

The product is not differentiated by having a chatbot, storing documents, vector search, RAG, transcription, note taking, a large context window, or long-term memory by itself. Those may all be components.

The differentiation is the ability to maintain a **purpose-shaped model of the user's world**:

> Memory-centric: *"Remember as much about me as possible."*
>
> Purpose-driven: *"Understand what I am trying to accomplish, then continuously determine what you need to know in order to help me accomplish it."*

That is a fundamentally different optimization target.

**The bet:**

> **The bottleneck to highly useful personalized AI is not model intelligence or access to more data. It is the absence of a purpose-driven system that continuously converts messy context into useful, current, reusable shared knowledge.**

**The vision statement:**

> **Create a purpose-driven personal AI that continuously transforms a person's messy stream of information into a small, evolving, shared body of knowledge that humans and AI agents can use together to achieve important outcomes — so AI can do more of the cognitive heavy lifting while humans remain focused on intent, judgment, and responsibility.**

**In one sentence:**

> **Don't try to make AI remember everything about a person; maintain the shared knowledge that humans and AI agents actually need for the outcomes they are trying to achieve.**

**The question the project is built around:**

> **What is the minimum synchronization effort needed to maintain enough shared context for humans and AI agents to operate as one effective system over time?**

---

## 19. Open Design Questions

1. **What is the unit of a claim?** Too fine and the namespace becomes unmanageable and binding brittle. Too coarse and targeted invalidation stops being targeted.
2. **Who specifies what an outcome needs?** If the user must specify it precisely, the system inherits the curation burden it exists to remove. If AI infers it, the binding set can drift and invalidation becomes unreliable.
3. **How are topic boundaries revised after the fact?** Splitting or merging means re-homing claims that outcomes are already bound to. Inside a space this is a rename with redirection; the question is what the redirect lifecycle looks like.
4. **What is the retention policy for the raw layer?** Immutability implies unbounded growth. At what point does that become a cost or privacy problem, and what goes first?
5. **How is a superseded claim distinguished from a contradicted one?** "I changed my mind" and "two sources disagree" have the same shape and different correct handling.
6. **How long should snapshot outcomes be retained?** They are useful as demand history and reproducibility artifacts, but indefinite retention carries privacy and storage cost.
7. **What is the concrete signal that the single space should become two?** Divergence of purpose is the stated criterion; it is not yet operational. A candidate: two clusters of outcomes that share few bound claims.
8. **Where does the single-database substrate stop being enough?** §9 asserts that millions of rows across 1000+ spaces is unremarkable. The pressure is more likely to come from embedding volume, per-space isolation requirements, or export size than from row count — which of those arrives first is unknown.
9. **What is the size threshold at which an outcome body spills to object storage,** and does an outcome that *is* a file behave differently in any other respect — diffing, review, or reproduction?
10. **What are the escalation thresholds in §8.2?** Correction rate over what window, at what level, before an outcome or topic moves from silent to flagged to gated — and what relaxes it again. Wrong thresholds either restore the queue or hide real unreliability.
11. **Does silence mean acceptance?** §8.4 treats use without correction as weak evidence of correctness. That is plausible for an outcome the user reads closely and false for one they skim, and the system cannot currently tell the difference.
12. **What is the right sampling rate for the audit?** Too low and it certifies nothing; too high and it becomes the review queue under another name.
13. **How is uncertainty rendered in an outcome** so that it prompts a correction instead of eroding trust in the result? Proceeding-with-flagged-uncertainty (§8.3) only works if the flag is legible and proportionate.

---

## Appendix A — Growth Path: A Network of Spaces

This is where the model goes when one space is no longer enough. **None of it is v1.** It is recorded here so that the v1 commitments in §16 are understood as deliberate rather than accidental.

A person has several purposes, at different scales and lifetimes. The answer is many spaces on the shared raw lake, composing into a directed acyclic graph.

**Two flavours.** The distinction is descriptive, not a separate type:

| | **Base space** | **Goal space** |
|---|---|---|
| Purpose | *Maintain the current truth about X* | *Achieve Y* |
| Lifetime | Long-lived, often permanent | Finite; ends when the goal ends |
| Typical inputs | Raw lake, mostly | Base spaces, plus raw lake |
| Examples | People and relationships; Finances; Health | Launch the product; Prepare my child for school |

Lower in the network, spaces tend to be subject-oriented and durable; higher, goal-oriented and finite. This is what makes goal completion safe: archiving a goal space does not delete the durable knowledge it consumed, because that knowledge was never owned by it.

**Composition.** When an outcome needs knowledge from several spaces, the answer is not to widen a space or let one reach into another's internals. It is a **new higher-level space** whose purpose is that cross-cutting outcome, consuming the published outputs of the others.

**The one hard constraint: the reference graph must be a DAG.** Cycles destroy termination of propagation, reproducibility of a build manifest, and any honest answer to "why did this change?" A cycle attempt is a signal: either the two spaces are one space, or the shared part belongs in a third space below both.

**Published names.** A consuming space binds to a published name — a published outcome, or a single published claim where a consumer needs one precise fact — never to internal claims. Publish several small, well-named outputs rather than one large export, or targeted invalidation is lost at every boundary. The published interface should stay deliberately narrower than what the space knows, because it is the only part that is expensive to change.

**Ownership is single; dependency is many-to-many.** Every claim has exactly one owning topic in exactly one owning space, never co-owned or duplicated. Single ownership means reconciliation has one home. Splitting a space is therefore a contract change, not a rename: every published name must keep resolving or carry an explicit redirect.

**Corrections route to the owning space.** This is the rule most easily got wrong. If a goal space notices a consumed fact is wrong, it must not fix it locally — a local fix creates a divergent belief with no reconciliation home and is silently overwritten on the next refresh.

**Splits are applied, not approved.** Because published names must keep resolving or carry an explicit redirect, a split is reversible and invisible to consumers, so it falls under §8.1: the system proposes, applies, and flags it in the Inbox in terms of the outcomes affected — never as a graph edit the user must adjudicate. Over-fragmentation is guarded by making the split criterion operational and conservative, not by asking a human every time.

**Open network questions:** what stops space proliferation (over-fragmentation is the likely failure mode); what the operational threshold for splitting is; what happens to a completed goal space that downstream spaces still bind to; whether base/goal ever becomes a real type.

## Appendix B — Growth Path: Multi-Writer

The first version is single-user and simplicity should win. A few decisions determine whether multi-writer is a later feature or a later rewrite.

**Must be true from the start** (all already required by v1 for other reasons):

- every claim has an author and a timestamp;
- every claim has exactly one owning topic, inside exactly one owning space — the space is also the natural future unit of access control and sharing;
- anything outside a space consumes its knowledge only through the published interface, never by binding directly to internal claims;
- approvals are durable change records, so there is a shared auditable record of who decided what and why;
- contradiction is a representable state — single-user contradiction is changing your mind, multi-writer contradiction is disagreement; the representation is the same and only the resolution policy differs.

**Can safely wait:** access control and visibility scoping, per-user views, conflict resolution and merge semantics, notification and subscription models, and anything resembling Data Mesh's organizational layer.

The distinction is between decisions that are cheap now and expensive later, and decisions that are simply features. Only the first list constrains v1.
