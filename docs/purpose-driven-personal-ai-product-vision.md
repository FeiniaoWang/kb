# Product Vision: Purpose-Driven Personal AI

**Working title:** Purpose-Driven Personal AI
**Document type:** Product Vision
**Status:** Early concept / foundation for product discovery
**Version:** v2 — three-layer knowledge model
**Original:** August 28, 2026
**Revised:** September 1, 2026

---

## Changelog — what changed in v2

The core thesis is unchanged: purpose, not volume, is the organizing principle for a personal AI's memory. The architecture around that thesis has been reworked.

| Change | Section |
|---|---|
| Two-layer model replaced with **three layers**: raw / knowledge / outcome | §6 |
| Outcomes reframed as a **view layer** — materialized or ad hoc — rather than a third store | §6.1 |
| Knowledge layer made **subject-oriented**, with inclusion kept **demand-driven** | §6.2 |
| **Ownership separated from consumption**: one owning topic per claim, many-to-many outcome binding | §6.3 |
| New: **layer contracts** — outcomes bind to named facts, claims are superseded not overwritten | §7 |
| New: **propagation machinery** — lineage, materiality, write-back, gap logging, escape hatch | §8 |
| Data-engineering analogy expanded into an explicit **borrow / invert / do-not-borrow** analysis | §9 |
| New: **storage substrate** — files for content, Git for history, database for relationships | §10 |
| New: human review **tiered by blast radius** rather than applied uniformly | §13 |
| New: **bootstrap from an outcome**, not from a goal declaration | §24 |
| New: **metrics** that would falsify the central bet | §25 |
| New: decisions that keep the **multi-writer** path open | §29 |
| New: **open design questions** | §36 |

---

## 1. Vision

Build a personal AI system that stays meaningfully synchronized with a human—not by trying to remember everything equally, but by organizing knowledge around the outcomes the human is trying to achieve.

The long-term vision is a **human–AI working relationship** in which:

- AI performs most of the information processing, drafting, analysis, coordination, and other heavy lifting.
- Humans remain responsible for intent, judgment, priorities, values, and important decisions.
- The AI continuously understands enough of the human's goals, work, experiences, and context to act as an effective extension of that person.
- Keeping the AI informed requires relatively little effort from the human.

The product should feel less like repeatedly giving instructions to a generic chatbot and more like working with a trusted collaborator that understands **what you are trying to accomplish, what has happened so far, what matters, and what it should do next**.

---

## 2. Core Thesis

The future of knowledge work will be based on **human–AI collaboration**.

AI will increasingly perform the majority of the mechanical and cognitive heavy lifting, but complete automation is neither necessary nor desirable for many important forms of work.

Humans will continue to contribute the parts that matter most:

- defining what they want;
- choosing goals and priorities;
- supplying real-world context;
- applying judgment;
- resolving ambiguity;
- making important decisions;
- accepting responsibility for outcomes.

This changes the role of the human.

Instead of doing 100% of the work, a person may eventually perform only a small portion of the total effort while AI performs the rest. But that remaining human contribution may be the most important part because it determines **direction and judgment**.

Therefore, one of the central product problems of the AI era is:

> **How do we keep the human mind and the AI's working context sufficiently synchronized so that they can operate as one effective system?**

---

## 3. The Problem

Today's AI is already highly capable, but capability alone is not enough.

An AI can only be useful when it has the right context.

Much of the context that matters lives outside the AI:

- in the human's head;
- in conversations;
- in meetings;
- in documents;
- in decisions made weeks or months ago;
- in observations from the physical world;
- in unfinished thoughts;
- in changing priorities;
- in accumulated experience.

As a result, people repeatedly have to explain themselves to AI systems.

They must keep telling the AI:

- what they are working on;
- what happened earlier;
- what they care about;
- what constraints exist;
- what decisions were already made;
- what changed;
- what they want next.

This creates a fundamental bottleneck.

### The personalization paradox

The more an AI knows about a person, the more useful it can become.

But collecting, organizing, and maintaining that information takes time.

Most people do not have the time or desire to continuously curate a perfect personal knowledge system. They have jobs, families, projects, meetings, and lives.

A useful personal AI therefore cannot depend on the user becoming a full-time curator of their own data.

---

## 4. Why Existing Approaches Are Incomplete

Many current approaches to AI memory and "second brain" systems focus primarily on **collecting more information**.

Examples include:

- saving every document;
- recording every meeting;
- storing every conversation;
- capturing notes throughout the day;
- continuously recording audio;
- maintaining large collections of Markdown files;
- indexing everything with embeddings;
- putting a RAG layer over the resulting corpus.

These approaches can improve recall, but they do not solve the whole problem.

### More memory is not automatically more intelligence

A giant collection of information can become a **data lake**:

> a large repository containing potentially useful information without a strong guarantee that the information has been organized for a particular outcome.

The problem is not that the data lake is bad.

The problem is expecting the data lake itself to be the personalized intelligence layer.

If everything is stored with equal importance, then:

- relevant information competes with irrelevant information;
- retrieval depends heavily on search quality;
- old information may conflict with current information;
- important decisions are buried among low-value details;
- the user still needs to reconstruct context;
- the AI may retrieve something semantically similar but operationally irrelevant.

A better retrieval algorithm alone does not fully solve this problem.

---

## 5. Core Insight: Purpose Comes Before Useful Memory

The missing organizing principle is **purpose**.

A personal knowledge system becomes dramatically more useful when it knows:

> **What is this knowledge supposed to help the human accomplish?**

Instead of building one undifferentiated memory of everything, the system should organize knowledge around a small number of explicit goals.

Ideally, a goal-oriented knowledge space has:

- **one primary goal**, or
- at most a very small number of closely related goals.

Examples:

- Launch my product and get the first 20 paying customers.
- Help me successfully lead Project X.
- Help me manage and improve my personal finances.
- Help me learn enough about a professional field to become highly competent.
- Help me prepare my child for school.
- Help me write and publish a book.

The goal becomes the organizing function for memory.

It tells the AI:

- what information matters;
- what can be ignored;
- what should be summarized;
- what should be tracked over time;
- what relationships should be extracted;
- what contradictions should be resolved;
- what changes are significant;
- what the AI should proactively help with.

### Key principle

> **Capture can be broad. Understanding must be purpose-driven.**

This principle is refined in §6.2 once the knowledge and outcome layers are separated: capture is broad, *retention* is demand-driven, and *assembly* is purpose-driven.

---

## 6. The Three-Layer Knowledge Model

Earlier versions of this vision described two layers: a raw information lake and a purpose-driven knowledge layer.

That model conflates two things that behave differently:

- **what I know about a subject**, and
- **what I need in order to produce a specific deliverable**.

These have different lifetimes, different granularity, and different correctness criteria. Knowledge about a subject should outlive any particular use of it. A deliverable is disposable and is judged by whether it is currently correct and currently useful.

The model is therefore split into three layers.

---

### Layer 1 — Raw Information Lake

Intentionally permissive, immutable, append-only.

The user should be able to put information into the system without deciding where it belongs or how it should be organized.

Possible inputs include:

- conversations with the AI;
- voice notes;
- meeting transcripts;
- emails;
- documents;
- screenshots;
- web pages;
- notes;
- calendar events;
- messages;
- observations;
- photos;
- tasks;
- decisions;
- imported application data;
- automatically captured information;
- **human corrections made anywhere else in the system**.

The philosophy is:

> **If the user thinks something might matter, make it easy to capture it.**

Some information in this layer will never become useful. That is acceptable.

Immutability is not a stylistic preference. It is what makes the rest of the system improvable: when extraction logic gets better, knowledge can be rebuilt from sources that were never overwritten.

---

### Layer 2 — Knowledge

Raw information is filtered, extracted, reconciled, and maintained as **knowledge organized by subject or topic**.

Each knowledge item is a **claim**: typed, named, versioned, and linked to the evidence that supports it.

The knowledge layer answers: *what is currently true, and currently believed, about this subject?*

It is deliberately **not** a summary of the raw layer. It is a continuously maintained current-best-understanding, in which new information can confirm, update, supersede, contradict, or add nuance to what is already held.

---

### Layer 3 — Outcomes

Knowledge is further processed to serve a **very specific outcome**.

An outcome is a deliverable, an answer, a decision package, a monitored state, a draft, a plan. It is the thing the human actually reads, ships, or acts on.

Outcomes come in two forms, distinguished only by whether they are stored:

- **Long-term outcomes** exist as a node or file in the knowledge base and are maintained as new information arrives.
- **One-off outcomes** are produced on demand through a chat interface and are not automatically maintained.

A one-off outcome can be **promoted** to a long-term outcome at any time.

---

### 6.1 Outcomes are views, not a third store

The cleanest way to understand the model is:

> **Two storage layers and one view layer.**

Raw and Knowledge are storage. Outcomes are views over Knowledge. Some views are materialized; some are computed on demand.

This framing does useful work:

- The two propagation modes stop being two different kinds of thing. A long-term outcome is a **materialized view with incremental maintenance**. A one-off outcome is an **ad hoc query**.
- "Promoting a one-off to long-term" becomes a one-line operation — materialize this view — instead of a migration path that has to be separately designed.
- Materializing an outcome has a clear technical justification beyond convenience: it is **pre-computed context-window packing** for a reasoner that has a limited budget.

---

### 6.2 Subject-oriented storage, purpose-driven filtering

Organizing the knowledge layer by topic rather than by goal is a deliberate change from earlier drafts, and the reason should be stated explicitly.

**Why topic, not goal:** goal-scoped knowledge does not survive goal completion. If everything learned is scoped to "launch the product," it dies when the product launches, taking with it everything that was reusable. Subject-oriented knowledge outlives the outcomes it served. This is the same reason a data warehouse conforms dimensions at the subject level and puts purpose in the mart.

**What that costs:** the filter gets blunt. "Is this relevant to my goal?" is a sharp test. "Is this relevant to the topic of my finances?" is not — almost everything is. Left alone, the knowledge layer drifts back into being a data lake one level up.

**The fix:** make inclusion **demand-driven**. A claim earns a place in the knowledge layer because at least one outcome — existing, or plausibly anticipated — needs it.

- **Topic decides where a claim lives.**
- **The outcome set decides whether it lives at all.**

Purpose is therefore not a layer. It is the parameter that configures both transforms: the raw→knowledge extraction filter, and the knowledge→outcome specification.

> **Capture can be broad. Retention must be demand-driven. Assembly must be purpose-driven.**

---

### 6.3 Structural relationships

The layers form one-to-many relationships, but ownership and consumption must be separated.

**Ownership is one-to-many and strict.**

- One raw layer supports many topics in the knowledge layer.
- Every knowledge claim has **exactly one owning topic**.

Single ownership means reconciliation has exactly one home. Without it, the same claim exists in three topics, drifts independently, and there is no answer to which copy is current.

**Consumption is many-to-many and loose.**

- An outcome may subscribe to claims from **any number of topics**.

Real outcomes cut across subjects. Preparing for a board review on Project X needs project knowledge, financial knowledge, and knowledge about the people in the room. Forcing an outcome to live under a single parent topic leads to either duplicating knowledge across topics — which guarantees divergence — or widening topics until they mean nothing.

In database terms: **topic is a partition key; outcome subscriptions are foreign keys.**

---

## 7. Layer Contracts

If outcomes re-read whole topic files, then any change to how knowledge is represented invalidates every outcome downstream. The seam between Layer 2 and Layer 3 needs a contract.

### 7.1 Facts are the interface

The knowledge layer exposes **named, typed, addressable claims**. Outcomes bind to those names.

An outcome does not say "read the Project X topic." It says "I depend on facts `project-x.current-scope`, `project-x.committed-date`, `people.sponsor.identity`."

This buys three things:

1. **Targeted invalidation.** When a fact changes, exactly the outcomes bound to that fact become stale. Everything else is untouched. No full recomputation.
2. **Computable blast radius.** The number of outcomes bound to a fact is a number the system knows, which is what makes review tiering possible (§13).
3. **Representation freedom.** How a topic file is internally organized can change without breaking consumers, as long as the named facts still resolve.

This is the same pattern as a data contract between a producing and consuming team, applied to knowledge rather than to tables.

### 7.2 Claims are superseded, never overwritten

Every claim carries:

- the evidence it derives from;
- when it became current;
- when it stopped being current;
- what replaced it, and on what evidence.

This is a slowly changing dimension in the classical sense, and the decades of practice around that pattern apply directly.

The property it buys is the one that matters most for trust: **"why did this outcome change?" is answerable**, and any historical outcome can be reproduced exactly from the fact versions it was built from.

### 7.3 Outcomes carry a build manifest

A materialized outcome records the specific fact versions it was assembled from. Regeneration is then a diff between two manifests, not a mystery.

---

## 8. Propagation and Incremental Maintenance

Two paths carry information from raw data into outcomes.

**Path A — maintained outcomes.** New raw information updates the knowledge layer; changed facts mark bound outcomes stale; stale outcomes regenerate.

**Path B — ad hoc outcomes.** The user asks a question through chat. The answer is assembled from the knowledge layer at that moment and is not maintained.

The dataflow is easy to describe. The machinery underneath it is where this becomes hard.

---

### 8.1 Lineage in both hops

The system must record which raw items support which claim, and which claims feed which outcome.

Without lineage, every new input forces recomputation of everything downstream. That is expensive, and worse, it is **nondeterministic**: re-derivation drifts, so an unchanged input produces a changed outcome, and the user stops trusting the system.

---

### 8.2 Materiality, not immediate recompute

Not every knowledge update should trigger an outcome rewrite.

The sequence should be: mark the outcome stale → let something cheap decide whether the change is **material** to that outcome → regenerate only then.

Regeneration should surface as a **diff with the triggering evidence attached**, not a silent overwrite. If a long-term outcome quietly rewrites itself because a trivial fact moved, the user loses confidence in every outcome the system maintains.

Whether regeneration is automatic or gated on review is a **per-outcome property**, not a system-wide policy.

---

### 8.3 The reverse edge

The most valuable signal the system will ever receive is **the human editing an outcome**.

If that correction lives only in the outcome, the same error regenerates next time.

Corrections must therefore flow **upward**:

1. The correction lands in the raw layer as a source — it is real information about the world.
2. It updates or supersedes the claim in the knowledge layer that produced the error.
3. Every other outcome bound to that claim becomes stale.

An architecture with only downward arrows cannot learn from outcomes, no matter what the loop description says.

---

### 8.4 One-off outcomes are demand signals

A chat question is not disposable. It is the highest-quality available evidence about what the knowledge layer should contain.

Even when the answer is never materialized:

- **log the query**;
- if answering it required dropping to the raw layer because the knowledge layer lacked what was needed, **record that as a gap**.

Repeated similar one-offs should **automatically trigger a promotion suggestion**, rather than waiting for the user to think of it.

---

### 8.5 The escape hatch, and why it must exist

Raw→knowledge is lossy. Knowledge→outcome is lossy again.

Double compression means an outcome will eventually need something the extractor discarded, even though it is sitting intact in the raw layer.

The knowledge layer must therefore not be a hard wall:

- an outcome may read raw sources **through lineage** when the knowledge layer is insufficient;
- every use of that escape hatch is logged as a **knowledge gap**.

The escape hatch prevents dead ends. The gap log is how the knowledge layer learns what it should have kept.

---

### 8.6 Idempotency has to live in storage

In a deterministic pipeline, idempotency comes from transform purity: the same input produces the same output, so re-running is safe.

That guarantee does not exist here.

Idempotency must be enforced at the **storage layer** instead — content-addressed keys, so that the same source producing the same fact slot does not create a second competing claim.

---

## 9. Relationship to Data Engineering

This system and a data platform both collect, store, and process information in order to serve goals. Decades of data engineering practice are therefore relevant, and the project should borrow deliberately rather than by accident.

But the differences have to be **load-bearing**. A statement that "our data is unstructured and our process is nondeterministic" is philosophy; it constrains nothing. Each difference below ends in a design decision it forces.

---

### 9.1 Borrow directly

**Immutable raw plus rebuildability.** Most AI memory systems treat memory as one mutable store, which means an improved extractor gives no retroactive benefit. Keeping raw immutable means knowledge can be rebuilt.

**Slowly changing dimensions.** The supersession requirement in §7.2 is exactly SCD Type 2.

**Conformed dimensions as a shared entity registry.** People, organizations, and projects appear across many topics. Resolving them once, centrally, stops the same person existing as three entities in three topic files. The entity-resolution problem is identical.

**Data contracts.** §7.1 is a data contract applied to knowledge.

**Freshness as an explicit per-view property.** Maps onto per-outcome regeneration policy.

---

### 9.2 Borrow, but invert

**The ETL/ELT instinct.** In a data platform the pipeline is the asset and tables are derived, so "just re-run it" is always available. Here the transform costs money and produces a different answer each time. That inverts the relationship: **the derived knowledge artifact is an asset to preserve and version, not a cache to recompute**. Rebuilding the knowledge layer is a deliberate migration event with human review, closer to a schema change than a nightly job.

**Data quality testing.** You cannot assert that an extracted claim is correct. You can assert **structural invariants**: every claim resolves to evidence; every evidence pointer is live; no two current claims occupy the same slot with contradictory values; every fact an outcome binds to exists. Correctness testing moves to sampling and human review — which is precisely what the AI-suggests / human-approves pattern is for.

---

### 9.3 Do not borrow

**A global schema or ontology defined up front.** Warehouses can conform globally because the question set is bounded and stable. Here, schema should emerge per topic and be allowed to differ across topics, with conformance only at the shared-entity boundary.

**Pipeline-centric architecture.** In data engineering the pipeline is the primary artifact and data flows through it. Here the **knowledge artifact is primary** and processing is opportunistic. Building an orchestration and scheduling layer would import complexity this system does not need.

**Completeness.** Warehouses aim for exhaustive coverage where the totals tie out. This system explicitly does not (§28). Completeness thinking is the gravitational pull that drags the knowledge layer back into being a second data lake.

**Data Mesh.** It solves an organizational problem that does not exist at single-user scale. Revisit only if the system becomes multi-writer.

---

### 9.4 The differences that force design decisions

**The consumer is a reasoner under a context budget, not a query engine.** A warehouse answers "can this question be answered." This system must answer "does the right subset fit." Selection and compression become first-class architectural concerns with no clean analogue in data engineering. This is the real justification for materializing outcomes.

**Truth is contested, not merely late-arriving.** In a warehouse, disagreement between sources is a data quality bug. Here, two sources can legitimately disagree and the user can change their mind. **Contradiction is a representable state**, not an error condition.

**The human is an input channel.** No warehouse can ask a question. The cheapest way to resolve ambiguity here is to ask the user, which means the system needs a **question queue prioritized by value of information** — designed deliberately, not left to emerge as ad hoc chat.

**Volume is tiny.** Thousands of claims, not billions of rows. A large share of data engineering technique exists purely to survive scale and is pure overhead here. Full graph traversal, expensive per-item processing, and per-item human review are all affordable. **Small-N is a design advantage to spend, not a limitation to work around.**

**The process is nondeterministic.** Re-running the same extraction on the same input does not reproduce the same output, which is why lineage, caching, and storage-level idempotency carry the weight that transform purity carries elsewhere.

---

### 9.5 The inversion, in one line

> Data engineering treats the **pipeline** as the asset, reprocessing as **cheap**, and **completeness** as the goal.
>
> This system treats the **knowledge artifact** as the asset, reprocessing as **expensive and lossy**, and **sufficiency** as the goal.

---

## 10. Storage Substrate

The system stores content in **files**, history in **Git**, and relationships in a **database**.

- **Files** hold knowledge content. Files support multiple formats and can sit on different storage infrastructure. They are portable and human-readable.
- **Git** holds history. The change history is itself important knowledge-base information — it records not only what is believed but when belief changed.
- **A database** connects files across layers into a usable knowledge base: file metadata, relationships between files, the list of core concepts each file is responsible for tracking, short summaries, vector embeddings, and whatever else makes retrieval work.

### 10.1 The rule that makes this work

> **The database must be fully rebuildable from files and Git history. Nothing lives only in the database.**

This makes schema migration a drop-and-rebuild, makes index drift impossible to sustain, and keeps the portable artifact portable.

Two consequences follow:

- **Embeddings** are rebuildable at cost, so they may live in the database alone.
- **Human decisions and approvals** are not derivable from anything. They must land in files, which means **an approval is a commit, not a database row**.

### 10.2 Commits must carry causality

If an AI update touches thirty files in one commit, the reason for the change is lost.

Structured commit trailers linking a commit to its triggering raw source and to the decision made would give queryable causality for almost no effort. The database indexes those trailers.

Git then provides time-travel for free. Files carry current state, Git carries history, and the database carries an index of that history — which is what makes questions like *what did I believe on this date* and *what changed since then* cheap to answer.

---

## 11. The Product's Core Loop

The product should operate as a continuous loop.

### 1. Define the goal

The human establishes the purpose of the knowledge space.

The system helps clarify:

- the desired outcome;
- why it matters;
- success criteria;
- major constraints;
- time horizon;
- current state.

The user should not need to perfectly define the goal on day one. The goal can evolve.

### 2. Capture information

The user provides information with very low friction.

Capture should be easier than organization.

The system may also connect to existing sources—with user permission—to reduce manual entry.

### 3. Interpret

AI evaluates incoming information in the context of the goal.

### 4. Extract knowledge

The system identifies durable, useful knowledge such as:

- facts;
- people;
- entities;
- decisions;
- constraints;
- preferences;
- commitments;
- plans;
- milestones;
- risks;
- lessons;
- unresolved questions;
- hypotheses;
- dependencies.

### 5. Reconcile with existing knowledge

New information may:

- confirm something;
- update something;
- supersede something;
- contradict something;
- add nuance;
- create uncertainty.

The system should maintain the current best understanding rather than simply accumulating statements forever.

### 6. Maintain the goal model

The purpose-driven layer continuously represents:

- where the user is now;
- where the user wants to go;
- what is known;
- what is unknown;
- what has been decided;
- what is blocked;
- what needs attention;
- what may happen next.

### 7. Help the human act

The AI uses this model to:

- answer questions;
- draft work;
- prepare decisions;
- identify missing information;
- suggest next steps;
- perform delegated tasks;
- monitor progress;
- surface risks;
- coordinate work;
- prepare the human for important judgment calls.

### 8. Learn from outcomes

Human decisions and real-world results update the knowledge model.

Corrections do not stop at the outcome. A correction enters the raw layer as a source, supersedes the claim that produced the error, and marks every other outcome bound to that claim as stale (§8.3).

The system becomes more useful over time.

---

## 12. Human–AI Division of Responsibility

The product should not be designed around the assumption that AI replaces the human.

It should be designed around **division of cognitive labour**.

### Human

The human primarily provides:

- goals;
- values;
- judgment;
- preferences;
- corrections;
- real-world observations;
- decisions;
- responsibility.

### AI

The AI primarily performs:

- information capture;
- organization;
- extraction;
- synthesis;
- recall;
- comparison;
- drafting;
- analysis;
- planning;
- tracking;
- monitoring;
- execution of delegated work.

The objective is to minimize the amount of repetitive cognitive labour required from the human while preserving human control over what matters.

---

## 13. Human Review: Tier by Blast Radius

The system should apply the pattern of **AI does the work, human reviews the important decisions** wherever it applies. That pattern is what substitutes for deterministic data quality gates.

But applied uniformly, it fails.

Review requests scale with input volume. At any real ingestion rate, the review queue becomes the new job — which is exactly the failure mode named in the principle *minimize synchronization cost*. A system that asks for approval on everything has not freed the human's time; it has changed the shape of the work.

### 13.1 Tiering

The lineage graph already computes blast radius, so this is a calculation rather than a judgment call.

| Change | Handling |
|---|---|
| New claim nothing binds to yet | Auto-apply |
| Change to a claim with small blast radius, reversible | Apply, flag for later review |
| Change to a claim many outcomes bind to | Queue for approval before applying |
| Topic boundary creation or merge | Queue for approval |
| Knowledge layer rebuild or schema change | Explicit migration, always reviewed |
| Contradiction the system cannot resolve | Queue as a question, prioritized by value of information |

### 13.2 Two distinct modes

**Approve before applying** and **applied, flagged for review** are different products.

Because Git makes almost everything reversible, the second mode is available far more often than instinct suggests, and it preserves flow. Reserve the first for changes that are hard to reverse or wide in blast radius.

### 13.3 Batch, don't interrupt

Review should be a periodic pass over a queue, not an interruption of the user's work. The queue itself should be ordered by consequence, so that if the user only ever reads the top of it, they are still reading the decisions that matter.

---

## 14. A New Definition of a "Second Brain"

Traditional second-brain systems often behave like better filing cabinets.

This product should behave more like a **goal-oriented cognitive partner**.

A useful second brain should not merely remember.

It should understand:

1. **What am I trying to accomplish?**
2. **What do I currently know that matters to that goal?**
3. **What has changed?**
4. **What have I already decided?**
5. **What remains uncertain?**
6. **What should I pay attention to now?**
7. **What can the AI do for me?**
8. **Where is human judgment required?**

The second brain therefore becomes a bridge between **memory and agency**.

---

## 15. Product Promise

The product's promise can be expressed simply:

> **Tell the AI what matters to you, keep it lightly informed about your world, and it will continuously organize what it knows around your goal so it can do more of the work for you.**

The user should not need to spend hours maintaining the system.

A reasonable aspiration is that a person could spend perhaps **tens of minutes per day—or less—synchronizing important real-world context**, while receiving many hours of leveraged AI assistance.

Over time, integrations and passive capture should reduce even that effort.

---

## 16. Core Product Principles

### 16.1 Purpose before organization

Do not ask the user to design folders, ontologies, schemas, or taxonomies before the system becomes useful.

Start with the goal.

### 16.2 Capture first, structure later

Make input friction extremely low.

Let AI do most of the organization.

### 16.3 Raw memory and useful knowledge are different things

Never treat the complete information archive as the AI's working memory.

### 16.4 Relevance is goal-dependent

The same piece of information may be essential for one goal and irrelevant for another.

### 16.5 Memory should evolve

The system should maintain current understanding, not merely append facts forever.

### 16.6 Humans remain in control

AI should know when it can act and when human judgment is required.

### 16.7 Minimize synchronization cost

The system fails if keeping it informed becomes another job.

### 16.8 Preserve provenance

Important knowledge should retain a connection to where it came from so the human can inspect evidence when needed.

### 16.9 Separate facts from interpretations

The system should distinguish source information from AI-generated conclusions.

### 16.10 Make uncertainty visible

When the AI is unsure, conflicting information exists, or critical information is missing, that uncertainty should be explicit.

### 16.11 Retention is demand-driven

Knowledge earns its place because an outcome needs it, not because it is interesting or because it was easy to extract.

### 16.12 Subject-oriented storage, purpose-driven assembly

Knowledge is organized by topic so that it outlives the goals it served. Purpose enters as a filter on what to keep and a specification for what to assemble.

### 16.13 Derived knowledge is an asset, not a cache

Re-derivation is expensive and nondeterministic. Knowledge is preserved and versioned, not regenerated on a whim.

### 16.14 Corrections must travel upward

A fix applied only to an outcome will be undone the next time that outcome regenerates.

### 16.15 Review scales with consequence, not with volume

Human attention is spent on decisions that are wide or hard to reverse. Everything else is applied and made reversible.

---

## 17. Conceptual Architecture

```text
                              HUMAN
              Goals • Judgment • Decisions • Corrections
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Goal / Purpose Model │
                    └───────────┬───────────┘
                                │ configures both transforms
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — OUTCOMES (views)                                          │
│                                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ materialized│ │ materialized│ │ materialized│ │  ad hoc query │  │
│  │  outcome A │  │  outcome B │  │  outcome C │  │  (not stored) │  │
│  └────────────┘  └────────────┘  └────────────┘  └───────────────┘  │
│         ▲  binds to named facts (many-to-many)         ▲             │
└─────────┼──────────────────────────────────────────────┼─────────────┘
          │                                              │
┌─────────┴──────────────────────────────────────────────┼─────────────┐
│  LAYER 2 — KNOWLEDGE (subject-oriented)                │             │
│                                                        │             │
│   Topic: Project X     Topic: Finances     Topic: People             │
│   claims • decisions   constraints         entities • relations      │
│                                                        │             │
│   every claim: typed • named • versioned • evidence-linked           │
│   every claim: exactly one owning topic                │             │
└──────────────────────────────┬─────────────────────────┼─────────────┘
                               ▲  extraction • reconciliation          │
                               │  lossy • nondeterministic • cached    │
┌──────────────────────────────┴─────────────────────────┴─────────────┐
│  LAYER 1 — RAW INFORMATION LAKE (immutable, append-only)             │
│                                                                      │
│  Chats • Files • Meetings • Voice • Email • Notes • Screenshots      │
│  Messages • Events • Observations • Human corrections                │
└──────────────────────────────────────────────────────────────────────┘

   ◀── write-back:   outcome corrections re-enter as raw sources
   ◀── escape hatch: an outcome may read raw via lineage; logs a gap
```

Substrate: **files** for content, **Git** for history, **database** for relationships and retrieval.

---

## 18. The Goal as a Function

```text
Raw Information
      +
Human Goal                    ← configures the extraction filter
      +
Existing Topic Knowledge
      +
AI Reasoning
      ↓
Current Subject Knowledge (claims: typed, versioned, evidence-linked)
      +
Outcome Specification         ← configures the assembly
      ↓
Outcome (materialized view, or ad hoc answer)
      ↓
Human Judgment + Real-World Result
      ↓
Correction re-enters as a raw source
      ↓
Updated Knowledge → stale outcomes → regeneration
```

The goal is not metadata. It is a central input into almost every knowledge-management decision the system makes — but it enters at **two different points**, and they are not the same decision.

- Entering the raw→knowledge transform, purpose decides **what is worth keeping**.
- Entering the knowledge→outcome transform, purpose decides **what is worth assembling now**.

---

## 19. Example

Imagine a user creates a knowledge space with the goal:

> **Launch my new SaaS product and acquire 20 paying customers within six months.**

During the next several months, the user adds:

- customer interviews;
- competitor links;
- random ideas;
- meeting recordings;
- pricing discussions;
- technical architecture notes;
- emails;
- sales conversations;
- personal observations;
- product metrics;
- investor articles;
- unrelated documents.

All of this can enter the raw information layer.

The purpose-driven layer may extract and maintain:

### Goal

20 paying customers within six months.

### Current strategy

Target small accounting firms with a specific workflow problem.

### Important hypotheses

- Customers will pay $X/month.
- Setup time must remain below Y.
- Accuracy is the primary purchasing criterion.

### Decisions

- Initial market chosen.
- Feature A postponed.
- Pricing changed after interview #8.

### Evidence

- 6 of 9 interviews mentioned the same pain point.
- Three prospects requested a demo.
- One prospect rejected the current price.

### Risks

- Onboarding remains too technical.
- Acquisition channel is unproven.

### Open questions

- Which buyer persona has budget authority?
- Does annual pricing improve conversion?

### Next actions

- Follow up with three prospects.
- Test revised pricing.
- Simplify onboarding.

A random article about an unrelated topic can remain safely in the raw layer.

It does not need to become part of the goal model.

This is the difference between **remembering everything** and **knowing what matters**.

---

## 20. Differentiation

The product is not primarily differentiated by:

- having a chatbot;
- storing documents;
- vector search;
- RAG;
- transcription;
- note taking;
- a large context window;
- long-term memory by itself.

Those capabilities may all be components.

The differentiation is the system's ability to maintain a **purpose-shaped model of the user's world**.

### Traditional memory-centric approach

> "Remember as much about me as possible."

### Purpose-driven approach

> "Understand what I am trying to accomplish, then continuously determine what you need to know in order to help me accomplish it."

That is a fundamentally different optimization target.

---

## 21. Potential Core Objects

The first implementation does not need a complex ontology, but several concepts are likely to be important.

### Goal

The outcome the human wants to achieve.

### Source

Raw information entering the system.

### Knowledge Item

A structured piece of goal-relevant understanding.

Possible types:

- fact;
- decision;
- preference;
- constraint;
- observation;
- assumption;
- hypothesis;
- task;
- risk;
- opportunity;
- milestone;
- question;
- lesson.

### Entity

A meaningful person, organization, project, product, place, concept, or other object associated with the goal.

### Relationship

A meaningful connection among entities or knowledge items.

### Evidence

Source material supporting a knowledge item.

### State

The system's current understanding of the goal and progress toward it.

### Action

Something the human or AI may need to do.

### Topic

The subject that owns a set of knowledge claims. Emergent rather than pre-designed: the AI proposes boundaries, the human approves. Every claim belongs to exactly one topic.

### Claim

The unit of the knowledge layer. Typed, named, versioned, evidence-linked, and owned by one topic. Superseded rather than overwritten.

### Outcome

A view over knowledge, serving one specific purpose. Either materialized and maintained, or produced ad hoc and discarded.

### Binding

The declared dependency from an outcome to the named facts it needs. The unit of invalidation, and the thing that makes blast radius computable.

### Lineage

The recorded edges from raw source to claim, and from claim to outcome. Without lineage there is no targeted invalidation, no provenance, and no honest answer to why something changed.

### Gap

A recorded instance of the knowledge layer failing to supply what an outcome needed. The primary input to deciding what the knowledge layer should contain next.

---

## 22. An Important Architectural Distinction

The system should maintain at least three different forms of information:

### 1. Source memory

What actually entered the system.

This should remain relatively immutable.

### 2. Derived knowledge

What the AI currently believes is important based on the sources and goal.

This may change.

### 3. Working context

The subset of derived knowledge needed for a specific AI task at a specific moment.

This distinction prevents the system from treating every historical statement as equally current and equally relevant.

### How this maps onto the three layers

The three forms are not the same axis as the three layers, and conflating them causes confusion.

| Form | Where it lives |
|---|---|
| Source memory | Layer 1, immutable |
| Derived knowledge | Layer 2, superseded over time |
| Working context | Assembled at Layer 3, either materialized as an outcome or built transiently for an ad hoc query |

A materialized outcome is working context that was worth keeping.

---

## 23. MVP Hypothesis

The first version should prove one central hypothesis:

> **A purpose-driven knowledge layer can make a personal AI meaningfully more useful than an AI operating directly over a large unstructured memory store.**

The MVP does not need to ingest a person's entire digital life.

It could begin with one goal and a few input channels.

### MVP experience

1. User names something they need to produce now — the first outcome.
2. User supplies whatever context they have, through chat, files, or voice.
3. AI produces the outcome, and records what it needed in order to do so.
4. AI proposes an initial topic boundary and an initial set of claims; the user reviews and approves.
5. User can inspect and correct the knowledge model at any time; corrections travel upward.
6. User marks the outcome as maintained, or lets it stay one-off.
7. New information updates claims; bound outcomes go stale and regenerate as a reviewable diff.
8. AI maintains, per topic: current state, decisions, constraints, open questions, risks, next actions.
9. The system asks only the highest-value clarification questions, batched rather than interrupting.
10. Repeated ad hoc questions surface as promotion suggestions.

The goal model is elicited **through** the first few outcomes rather than demanded before any work is done (§24).

---

## 24. Bootstrapping: Start From an Outcome, Not a Goal

The cold start is a larger risk to this product than the architecture is.

A purpose-driven knowledge base has almost no value until it has been fed. The natural MVP flow — define a goal, then supply information for several weeks before anything useful appears — describes a value curve that enterprises tolerate and individuals do not.

Inverting it fixes the problem, and it follows from the demand-driven principle anyway.

> **Make the first outcome the entry point.**

1. Ask what the person needs to produce right now.
2. Produce it.
3. Let the knowledge layer accrete **backwards** from what that outcome actually required.

Two things follow:

- The first session delivers something, so the value curve starts above zero.
- The knowledge layer is populated by **demonstrated demand** rather than by speculation about what might matter later — which is the inclusion criterion §6.2 requires.

The goal model still exists, and still shapes filtering. But it is elicited **through** the first few outcomes rather than demanded before any work is done.

---

## 25. Measuring Whether the Bet Is Working

The central bet needs a number attached to it, early.

### Primary metric — knowledge layer sufficiency rate

> What fraction of outcomes can be produced from the knowledge layer alone, without dropping through the escape hatch to raw?

If this rate does not climb over time, the core bet is wrong, and it is better to learn that in month two than in year two.

### Supporting metrics

- **Human correction rate on regenerated outcomes** — how often a maintained outcome is wrong enough to need editing after it updates itself. Measures whether propagation is trustworthy.
- **Review queue volume per unit of input** — measures whether the human-in-the-loop design is actually saving time or has become the new job (§13).
- **Gap-to-promotion latency** — how long between a repeated one-off question and the knowledge layer acquiring what it needed to answer it.
- **Synchronization time per day** — the number the product promise in §15 is making a claim about.
- **Stale-outcome ratio** — how many maintained outcomes are currently out of date relative to their bound facts.

The first metric tests the thesis. The rest test whether the implementation is honest about it.

---

## 26. What the MVP Should Not Try to Solve

Early versions should avoid becoming:

- a universal life-logging platform;
- a replacement for every note-taking application;
- a general document management system;
- a giant enterprise knowledge graph;
- an autonomous agent that acts without boundaries;
- a perfect memory of the user's entire life;
- an ontology-design product;
- a generic RAG platform;
- a workflow orchestration platform;
- a complete data warehouse for a person's life;
- a system that asks for approval on everything it does.

The early product should stay focused on proving that **purpose-driven knowledge produces better human–AI collaboration**.

---

## 27. Possible Initial Product Experience

A simple product could have four main views.

### Goal

What am I trying to accomplish?

### Knowledge

What does the AI currently understand that matters?

### Inbox

What new information has entered the system, and what did the AI learn from it?

### Outcomes

What is this system currently maintaining for me, what is stale, and what changed?

### Review

What has the AI decided that I should look at, ordered by consequence?

### Collaborate

What should we think about, decide, or do next?

The user should be able to see the AI's evolving mental model rather than interacting only through a chat window.

---

## 28. Sync Should Be Selective, Not Exhaustive

The product does not need to know everything about a person.

It needs to know **enough of the right things**.

This is an important philosophical difference.

The objective is not:

> Human Brain = AI Memory

The objective is:

> Human Goal-Relevant Context ≈ AI Working Understanding

The system should therefore optimize for **sufficient synchronization**, not complete synchronization.

---

## 29. Evolution Path to Multi-Writer

The first version is single-user. Simplicity should win. But a few decisions made now determine whether multi-writer is a later feature or a later rewrite.

**What must be true from the start:**

- **Every claim has an author and a timestamp.** Adding attribution later means backfilling something that was never recorded.
- **Every claim has exactly one owning topic.** Ownership is how concurrent writers are arbitrated; retrofitting it into a knowledge layer that grew without it is a data migration.
- **Approvals are commits, not database rows.** Multi-writer needs a shared, auditable record of who decided what. Git already provides one.
- **Contradiction is a representable state.** Single-user contradiction comes from changing your mind. Multi-writer contradiction comes from disagreement. The representation is the same; only the resolution policy differs.

**What can safely wait:**

- access control and visibility scoping;
- per-user views of shared knowledge;
- conflict resolution policy and merge semantics;
- notification and subscription models;
- anything resembling Data Mesh.

The distinction is between decisions that are cheap now and expensive later, and decisions that are simply features. Only the first list constrains the first version.

---

## 30. Future Evolution

If the core model works, the product could evolve toward multiple specialized personal AIs.

A person may eventually have AI collaborators for:

- work;
- entrepreneurship;
- learning;
- parenting;
- finance;
- health;
- creative projects;
- personal administration.

Each can have its own purpose-driven knowledge model.

Some raw sources may be shared, while goal-oriented knowledge remains scoped to the relevant purpose.

Over time, a higher-level personal AI could coordinate across these goal spaces while respecting privacy and boundaries.

---

## 31. Long-Term Vision

In the long term, the AI should not merely answer when asked.

It should continuously understand:

- what the human is trying to achieve;
- the current state of that effort;
- what changed recently;
- what information is missing;
- what decisions are approaching;
- what work can be delegated;
- what should be ignored;
- when the human's judgment is required.

The human remains the source of direction and judgment.

The AI becomes the scalable cognitive infrastructure surrounding that human.

This creates a new working model:

> **Human intent + human judgment + AI memory + AI reasoning + AI execution**

The result is not "AI replacing humans."

It is a **combined human–AI system** capable of accomplishing far more than either could efficiently accomplish alone.

---

## 32. Product Vision Statement

> **Create a purpose-driven personal AI that continuously transforms a person's messy stream of information into the small, evolving body of knowledge needed to achieve an important goal—so AI can do most of the cognitive heavy lifting while the human remains focused on intent, judgment, and decisions.**

---

## 33. One-Sentence Version

**Don't try to make AI remember everything about a person; make it understand what the person is trying to accomplish, then continuously organize everything it learns around that purpose.**

---

## 34. Foundational Product Question

The project can be built around one question:

> **What is the minimum amount of effort a human must spend keeping an AI synchronized with their world for that AI to become a genuinely useful long-term collaborator?**

The three-layer model—**raw information lake + subject-oriented knowledge layer + purpose-specific outcome views**—is the proposed answer to that question.

The raw layer minimizes the cost of capture. The knowledge layer makes what was captured reusable. The outcome layer makes it useful without being asked twice.

---

## 35. The Bet

This product is ultimately making a specific bet:

> **The bottleneck to highly useful personalized AI is not primarily model intelligence or access to more data. It is the absence of a purpose-driven system that continuously converts messy human context into useful, current, goal-specific knowledge.**

If that bet is correct, the winning personal AI products will not simply have the largest memories.

They will have the best mechanisms for deciding **what matters, why it matters, and what should be done with it**.

---

## 36. Open Design Questions

These remain unresolved and are worth tracking explicitly rather than deciding by default.

1. **What is the unit of a claim?** Too fine and the fact namespace becomes unmanageable and binding becomes brittle. Too coarse and targeted invalidation stops being targeted, because every change touches every outcome.

2. **Who writes the outcome specification?** If the user must specify precisely what an outcome needs, the system inherits the curation burden it was built to remove. If the AI infers it, the binding set drifts and invalidation becomes unreliable.

3. **How are topic boundaries revised after the fact?** AI suggests and the human approves, but splitting or merging a topic later means re-homing claims that outcomes are already bound to. Is that a rename with redirection, or a breaking change?

4. **What is the retention policy for the raw layer?** Immutability and append-only are stated. Unbounded growth is implied. At what point does that become a cost or a privacy problem, and what is deleted first?

5. **How is a superseded claim distinguished from a contradicted one?** "I changed my mind" and "two sources disagree" have the same shape and different correct handling.

6. **When does the goal model itself change, and what happens downstream?** A goal shift can invalidate the filtering decisions behind a large amount of retained knowledge. Is that a rebuild, or is stale-but-retained knowledge acceptable?

7. **What does the system do with knowledge that no outcome needs any more?** Demand-driven inclusion implies demand-driven eviction. It is not obvious that eviction is safe, or that it is worth the complexity at small scale.
