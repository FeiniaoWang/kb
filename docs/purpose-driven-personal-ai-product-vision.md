# Product Vision: Purpose-Driven Personal AI

**Working title:** Purpose-Driven Personal AI
**Document type:** Product Vision
**Status:** Early concept / foundation for product discovery
**Version:** v5 — two layers and a network of Knowledge Spaces
**Original:** August 28, 2026
**Revised:** September 2, 2026

---

## Changelog — what changed in v5

The core thesis is unchanged: purpose, not volume, is the organizing principle. v5 changes the shape of the knowledge layer. Instead of one flat knowledge layer with a separate outcome tier above it, the knowledge layer becomes a **network of Knowledge Spaces**, each with a single purpose, composing into a directed acyclic graph.

| Change | Section |
|---|---|
| Collapsed the three-layer model into **two layers**: Raw Information Lake and Knowledge. Outcomes are no longer an architectural tier | §6, §17, §22, §34 |
| The Knowledge layer is composed of many **Knowledge Spaces**. Each space has one primary purpose, or a very small number of closely related ones. All spaces together are the Knowledge layer | §6 |
| Outcomes remain a first-class object type with unchanged semantics, but they live **inside a space** as its published sub-layer | §6.1, §21 |
| Introduced **base spaces** (subject-oriented, long-lived) and **goal spaces** (goal-oriented, finite), which resolves the topic-vs-goal tension left open in v4 | §6.2 |
| Spaces **compose**: a higher-level space consumes the published outputs of lower-level spaces. The reference graph must remain a **DAG** | §6.4 |
| Added **published names / output ports**. Cross-space consumption goes through published names — never a direct read of another space's internal claims | §6.5, §7.4 |
| Spaces can be **split** when they grow too large or their purposes diverge; splitting is a contract change with redirects, not a silent re-homing | §6.6, §13.2, §36 |
| Added deliberate borrowings from **Medallion architecture, star-schema conformed dimensions, dbt's model DAG, and the data-product shape from Data Mesh**; kept the rejection of Data Mesh's organizational layer | §9.1, §9.3 |
| Corrections now **route to the owning space** rather than being patched in the consuming space | §8.4, §16.24 |
| Retained from v4: object storage + database substrate, Change Records, claim and outcome version semantics, demand-driven retention, support count, review tiering by blast radius | throughout |

---

## 1. Vision

Build a personal AI system that stays meaningfully synchronized with a human—not by trying to remember everything equally, but by organizing knowledge around the outcomes the human is trying to achieve.

The long-term vision is a **human–AI working relationship** in which:

- AI performs most of the information processing, drafting, analysis, coordination, and other heavy lifting.
- Humans remain responsible for intent, judgment, priorities, values, and important decisions.
- The AI continuously understands enough of the human's goals, work, experiences, and context to act as an effective extension of that person.
- Keeping the AI informed requires relatively little effort from the human.

The knowledge base underneath that relationship should be **consumer-agnostic**. It is shared working knowledge that can be used by a human, one or more AI agents, another software system, or any combination of them. The knowledge base should maintain what is useful and trustworthy without coupling itself to who ultimately consumes an outcome.

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

Instead of building one undifferentiated memory of everything, the system should organize knowledge around a small number of explicit purposes.

The unit of that organization is a **Knowledge Space**.

Ideally, a knowledge space has:

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

### One lake, many spaces

A person does not have one purpose. They have several, at different scales and with different lifetimes.

The system therefore has:

- **one Raw Information Lake**, shared by everything;
- **many Knowledge Spaces** on top of it, each with a single purpose.

**All of the spaces together are the Knowledge layer.** There is no separate architectural tier above them. A space is not a folder, a tag, or a view — it is a bounded unit of knowledge with one purpose, one owner, its own internal schema, and an explicit published interface.

### Key principle

> **Capture can be broad. Understanding must be purpose-driven.**

This principle is refined in §6.3: capture is broad, *retention* is demand-driven, and *assembly* is purpose-driven.

---

## 6. The Two-Layer Model and the Space Network

Earlier versions of this vision moved from two layers to three: a raw lake, a knowledge layer, and an outcome layer above it.

The three-layer split was solving a real problem — *what is known about a subject* and *what must be assembled for a particular purpose* behave differently — but it solved it in the wrong place. It made "outcome" a global architectural tier, which implied that outcomes are somehow above and outside knowledge. They are not. An outcome is something a purpose-bounded unit of knowledge **produces**.

v5 therefore returns to two layers and puts the structure where it belongs: inside and between **Knowledge Spaces**.

- **Layer 1 — Raw Information Lake.** One per system. Immutable, append-only, permissive.
- **Layer 2 — Knowledge.** A network of Knowledge Spaces. Each space has one purpose. Each space internally maintains claims and publishes outcomes. Spaces consume the raw lake, and may consume the published outputs of other spaces.

Outcomes did not disappear. They lost their tier and kept their semantics.

---

### Layer 1 — Raw Information Lake

Intentionally permissive, immutable, append-only.

The user should be able to put information into the system without deciding where it belongs, how it should be organized, or which space it serves.

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
- **corrections, decisions, and evidence produced anywhere else in the human–AI system**.

The philosophy is:

> **If the user thinks something might matter, make it easy to capture it.**

Some information in this layer will never become useful. That is acceptable.

Immutability is not a stylistic preference. It preserves the original evidence so extraction and reconciliation logic can improve later without losing or rewriting what actually entered the system.

There is exactly **one** lake. Multiple lakes would reintroduce the routing decision at capture time, which is precisely the friction the lake exists to remove.

---

### Layer 2 — Knowledge: a network of Spaces

Raw information is filtered, extracted, reconciled, and maintained as knowledge **inside a space**.

A **Knowledge Space** is a bounded unit of knowledge with:

- **one purpose** — one primary goal, or a very small number of closely related goals;
- **its own claims**, organized by topic and owned exclusively by that space;
- **its own outcomes**, which are the artifacts it produces;
- **an explicit published interface** — the names other spaces and external consumers are allowed to depend on;
- **its own internal schema**, which may differ from every other space's;
- **one owner** (in v1, always the user).

The knowledge layer answers: *what is currently true, and currently believed, in service of this purpose?*

It is deliberately **not** a summary of the raw layer. Each space maintains a continuously updated current-best-understanding in which new information can confirm, update, supersede, contradict, or add nuance to what is already held.

The knowledge layer remains a **shared substrate**. A space does not need to know whether the next consumer of its output is a human, an AI agent, another application, another space, or a human–AI team.

---

### 6.1 Anatomy of a space

Every space has the same internal shape, regardless of where it sits in the network.

```
┌─ Knowledge Space ────────────────────────────┐
│  Purpose (one goal, or a few related ones)   │
│                                              │
│  Inputs      raw sources, and/or published   │
│              names from upstream spaces      │
│        ↓                                     │
│  Claims      named, typed, versioned,        │
│              evidence-linked; organized by   │
│              topic; owned by this space      │
│        ↓                                     │
│  Outcomes    immutable materialized versions │
│              with build manifests            │
│        ↓                                     │
│  Published   the subset of outcomes and      │
│  interface   claims other spaces may bind to │
└──────────────────────────────────────────────┘
```

**Claims and outcomes are sub-layers within a space, not system layers.** All of the v4 machinery applies unchanged inside every space: named claims, immutable claim versions with supersession, outcome bindings, build manifests, snapshot versus maintained maintenance policy, lineage, change records, materiality checks, and the reverse edge for corrections.

This is the main simplification. There is one mechanism, described once, instantiated many times.

#### Outcomes are derived views, not canonical knowledge

Within a space:

> **Claims are canonical. Outcomes are derived views over claims.**

All outcome versions are persisted as artifacts, but only maintained outcomes participate in incremental refresh. A maintained logical outcome may have many immutable materialized versions, with one designated current.

- **Snapshot outcome** — one stored immutable version, with its build manifest; later signals do not refresh it.
- **Maintained outcome** — a logical outcome with an immutable version history. When a bound claim changes materially, regeneration creates a **new outcome version** and that version becomes current; older versions remain preserved.

An ad-hoc request is therefore not disposable. It becomes a durable snapshot of what was needed and what the system produced at that moment.

There is no promotion lifecycle. Snapshots and maintained outcomes are produced by the same mechanism; the only difference is the **maintenance policy**, and changing that policy is a property change, not a migration.

Persisting outcome views also provides **pre-computed context-window packing** for reasoners with limited context budgets.

---

### 6.2 Two flavours of space: base and goal

A space is defined by having one purpose. But purposes have very different lifetimes, and pretending otherwise creates a real problem.

v4 argued that knowledge should be organized by **topic, not goal**, because goal-scoped knowledge does not survive goal completion. Making every space goal-scoped would contradict that. Facts about a person, an organization, or a project are needed by several goals at once and outlive all of them; if each goal space owned its own copy, single ownership breaks and reconciliation has no home.

The network resolves this by admitting that spaces come in two flavours.

| | **Base space** | **Goal space** |
|---|---|---|
| Purpose | *Maintain the current truth about X* | *Achieve Y* |
| Orientation | Subject | Goal |
| Lifetime | Long-lived, often permanent | Finite; ends when the goal ends |
| Typical inputs | Raw lake, mostly | Base spaces, plus raw lake |
| Typical consumers | Other spaces | Humans, agents, other systems |
| Examples | People and relationships; Finances; Health; Employer and industry | Launch the product and get 20 paying customers; Prepare my child for school; Publish the book |

Both are spaces. Both have one purpose, claims, outcomes, and a published interface. The distinction is descriptive, not a separate object type — it describes where a space tends to sit in the network and how long it tends to live.

The general shape that follows:

> **Lower in the network, spaces tend to be subject-oriented and durable. Higher in the network, spaces tend to be goal-oriented and finite.**

This is what makes goal completion safe. When a goal space is archived, the durable knowledge it depended on is not deleted with it, because that knowledge was never owned by the goal space — it lives in the base spaces the goal space consumed. What is archived is the goal-specific interpretation, which is exactly what should not outlive the goal.

---

### 6.3 Subject-oriented storage, demand-driven inclusion

Within a space, claims are still organized **by topic**, and inclusion is still **demand-driven**.

**Why topic inside a space:** even within one purpose, subject-oriented organization gives reconciliation a single home and lets internal representation evolve without breaking bindings.

**What that costs:** topic relevance is broad. Left alone, a space could drift into being a small second data lake.

**The fix:** a claim earns a place in a space because at least one stored outcome — of that space, or of a downstream space consuming its published names — actually depends on it.

- **Topic decides where a claim lives inside a space.**
- **Purpose decides which space it belongs to.**
- **Outcomes demonstrate why the claim needs to exist at all.**

A stable active claim with no outcome dependency remains a contradiction in the model. When a new outcome requires knowledge that is missing, the space may consult raw sources or upstream published names, derive the needed claim, persist the claim and its lineage, and bind the outcome to it as part of the same operation.

> **Capture can be broad. Retention must be demonstrated by use. Assembly must be purpose-driven.**

---

### 6.4 Composition: spaces form a DAG

Spaces are not a flat list. They compose.

**Splitting.** When a space grows too large, or its purposes begin to diverge, it is split into smaller spaces with tighter purposes. Divergence of purpose is the signal — not size alone. A space that is large but coherently serving one goal is fine; a space that is small but serving two unrelated goals should be split.

**Composing.** When an outcome requires knowledge from several spaces, the answer is **not** to widen an existing space or to let one space reach into another's internals. It is to create a **new higher-level space** whose purpose is that cross-cutting outcome, and which consumes the published outputs of the lower-level spaces.

```mermaid
flowchart BT
    RAW["Raw Information Lake"]

    P["People &amp; relationships<br/><i>base space</i>"]
    F["Finances<br/><i>base space</i>"]
    W["Employer &amp; industry<br/><i>base space</i>"]

    L["Launch the product<br/><i>goal space</i>"]
    S["Prepare my child for school<br/><i>goal space</i>"]

    B["Quarterly life review<br/><i>higher-level goal space</i>"]

    RAW --> P
    RAW --> F
    RAW --> W
    P --> L
    W --> L
    P --> S
    F --> S
    L --> B
    F --> B
    S --> B
```

**The one hard constraint: the reference graph must be a DAG.**

Cycles are prohibited because they destroy the three properties the whole design rests on:

- **termination** — propagation of a claim change must halt;
- **reproducibility** — a build manifest must resolve to a finite, well-defined set of versions;
- **an honest answer to "why did this change?"** — a cycle makes causality circular and unexplainable.

A cycle attempt is a signal, not an error to route around. If space A needs something from B and B needs something from A, either they are one space, or the shared part belongs in a third space below both. The system should detect the attempted cycle at binding time and propose one of those two resolutions.

**Evolution.** Because splitting and composing are both ordinary operations, the network is expected to change shape over time. It is not designed up front. It accretes from demonstrated demand in exactly the way claims do (§24): a new space is created when a new purpose demonstrably needs one, not in anticipation.

---

### 6.5 Published names: how spaces consume each other

A consuming space binds to a **published name** on the producing space, never to its internal claims.

Two kinds of name may be published:

- **A published outcome.** The normal case. A stable, purpose-shaped artifact the producing space maintains — for example, `people/current-relationship-summary` or `finances/monthly-position`.
- **A published claim.** A single named, typed claim exposed directly — for example, `people.sponsor.identity`. Useful when a consumer needs one precise fact and routing it through a whole outcome would be wasteful.

Both are contracts. Everything not published is private to the space, and internal representation may change freely as long as published names still resolve (§7.1).

**Why this granularity matters: blast radius.**

If cross-space consumption could only happen through one big published outcome per space, then any material change anywhere in the producing space would regenerate that outcome and stale every consumer, including consumers that did not care about the changed fact. Targeted invalidation — the property §7.1 exists to buy — would be lost at every space boundary.

The rule that keeps it is therefore not "outcomes only." It is:

> **Ownership is single. Cross-space reads go through published names. The reference graph is acyclic.**

Two practices follow:

1. **Publish several small, well-named outputs rather than one large one.** Think output ports, not a single export.
2. **Allow published-claim binding where a consumer genuinely needs one fact**, so that fine-grained invalidation survives the boundary.

The published interface should be deliberately smaller than the space's internal surface. A space that publishes everything it knows has no encapsulation and will be impossible to refactor.

---

### 6.6 Structural relationships

Ownership and dependency must stay separate.

**Ownership is strict.**

- One raw lake supports many spaces.
- Every claim has **exactly one owning topic**, inside **exactly one owning space**.
- A claim is never co-owned or duplicated across spaces. If two spaces need the same fact, one owns it and the other consumes it by published name.

Single ownership means reconciliation has exactly one home. Without it, the same fact drifts independently in several places and there is no authoritative current version.

**Dependency is many-to-many.**

- One outcome may bind to claims from its own space and to published names from any number of upstream spaces.
- One published name may be consumed by any number of downstream spaces and external consumers.

**Splitting a space is a contract change, not a rename.** Because published names may already have downstream bindings, a split must preserve resolution of every published name — either by keeping the name resolving in one of the resulting spaces, or by leaving an explicit redirect. Silent re-homing of a published name is a breaking change and is treated as one (§13.2).

In database terms: **space is the ownership and encapsulation boundary; topic is the partition inside it; bindings to published names are the dependency edges.**

---

### 6.7 Support count: demonstrated reuse without promotion

Every named claim has a derived **support count**:

> **support_count = number of distinct stored outcomes that depend on the claim**

This now counts outcomes **across the whole network**, not just within the owning space. An outcome in a downstream space that depends on a published name contributes to the support count of the claims behind that name. That is the point: a base-space claim earns its keep by being useful to goal spaces, and the count should show it.

Snapshot and maintained outcomes contribute equally. The count is derived from persisted bindings, so it can be recalculated when needed or cached as database metadata rather than treated as an independent fact.

Support count measures demonstrated reuse without introducing candidate claims, promotion thresholds, or separate claim lifecycles.

However, support count must **not** become the primary retrieval rule. A popular claim can still be irrelevant to a new problem.

The ordering principle is:

1. **Relevance to the desired outcome first.**
2. **Support count as a secondary priority signal** among otherwise relevant claims.

A higher support count means a claim has proven useful across more outcomes and is therefore worth considering earlier, not that it is automatically relevant.

### 6.8 A note on the name

Several names were considered for this unit. The criteria were that it should not sound like a storage tier, should not imply a fixed hierarchy, and should carry the connotation of a bounded thing with a purpose.

| Candidate | Why not / why |
|---|---|
| Zone | Reads as a storage or availability tier; suggests partitioning by policy rather than by purpose |
| Domain | Strong precedent in Domain-Driven Design's bounded context, which is a genuinely good analogy, but "domain" is overloaded and implies subject rather than purpose |
| Context | Collides with "context window" and "working context" (§22), both already used with different meanings |
| **Space** | Chosen. Already in use in §5 as "knowledge space", carries boundedness without implying tier or hierarchy, and reads naturally in both flavours: *base space*, *goal space* |

The DDD comparison is worth keeping in mind even though the name was not taken from it. A bounded context has one owner, one internal model, an explicit published language at its edge, and translation rather than sharing across boundaries. That is the same set of commitments a space makes, arrived at from a different direction.

---

## 7. Contracts

There are now two seams that need contracts, and they are the same contract applied twice:

- **Inside a space**, between claims and the outcomes assembled from them.
- **Between spaces**, between a producing space's published names and the downstream spaces that bind to them.

If an outcome re-reads a whole topic representation, or a downstream space re-reads another space wholesale, then any change to how knowledge is represented invalidates everything downstream. Named interfaces prevent that.

### 7.1 Names are the interface

A space exposes **named, typed, addressable** claims and outcomes. Consumers bind to those names.

An outcome does not say "read the Project X topic." It says "I depend on facts `project-x.current-scope`, `project-x.committed-date`, `people.sponsor.identity`."

This buys three things:

1. **Targeted invalidation.** When a fact changes, exactly the maintained outcomes bound to that fact can become stale. Snapshot outcomes remain unchanged historical artifacts.
2. **Computable blast radius.** The number of maintained outcomes affected by a fact change is known, which makes review tiering possible (§13).
3. **Representation freedom.** How a topic is internally represented can change without breaking downstream views, as long as the named facts still resolve. Across a space boundary this is stronger: a space can be reorganized internally, and even split, without downstream spaces noticing, provided its published names keep resolving.

This is the same pattern as a data contract between a producer and downstream dependency, applied to knowledge rather than tables.

### 7.2 Claim versions are superseded, never overwritten

A named logical claim may have multiple immutable versions. The database designates the current version and preserves the supersession chain. Each claim version records:

- the evidence it derives from;
- when it became current;
- when it stopped being current;
- what replaced it, and on what evidence.

This is a slowly changing dimension in the classical sense, and the decades of practice around that pattern apply directly.

The property it buys is the one that matters most for trust: **"why did this outcome change?" is answerable**, and any historical outcome can be reproduced exactly from the claim versions it was built from.

### 7.3 Outcomes are versioned and every version carries a build manifest

Every materialized outcome version — snapshot or maintained — records the specific claim versions it was assembled from.

A **snapshot outcome** normally has one immutable version. Its manifest makes the historical result reproducible and explains what the system knew at that moment.

A **maintained outcome** is a logical outcome with a version history. Each material regeneration creates a new immutable outcome version with its own build manifest. The database records which version is current and how each version supersedes the previous one. Older versions are never overwritten.

This makes regeneration a diff between two explicit builds rather than a mystery and makes questions such as *what did this outcome say before, what changed, and why?* directly answerable.

Because bindings are persisted in the database, claim support counts can be calculated from them without introducing a second independent source of truth.

### 7.4 The space contract

A space's contract with the rest of the network is small and explicit:

| The space promises | The consumer promises |
|---|---|
| Every published name resolves, or resolves through a recorded redirect | It binds only to published names |
| A published name keeps its meaning and type; a meaning change is a new name | It does not reach into the space's internal claims |
| Changes to a published name are recorded as change records with causality | It records its bindings so invalidation can be targeted |
| The space is the sole owner and reconciler of the claims behind its published names | Corrections travel back to the owning space, not applied locally (§8.4) |

Everything else in a space is private. The published interface should stay deliberately narrow; it is the only part of a space that is expensive to change.

## 8. Propagation and Incremental Maintenance

Both outcome modes use the same knowledge path.

**Path A — maintained outcome.** Assemble from claims, persist an immutable outcome version and manifest, designate it current, then monitor its bound claims. New raw information may update those claims; material changes can mark the outcome stale and trigger regeneration into a new immutable version.

**Path B — snapshot outcome.** Assemble from claims and persist one immutable outcome version and manifest, but do not refresh it when later signals arrive.

The difference is therefore not how an outcome obtains knowledge. The difference is only whether it participates in future maintenance.

---

### 8.1 Lineage in every hop

The system must record:

- which raw items support which claim;
- which claims feed which outcome;
- which published names a downstream space binds to, and which of its claims or outcomes depend on them.

Lineage is therefore continuous across the whole network, not just within a space. Without it, every new input forces broad recomputation. That is expensive, and worse, it is **nondeterministic**: re-derivation can drift, so an unchanged source may produce a changed result and trust erodes.

---

### 8.2 Propagation across spaces

A claim change propagates transitively, but only along recorded bindings, and only through published names.

1. A claim in space A changes materially.
2. Maintained outcomes in A bound to that claim are marked potentially stale.
3. If a **published name** of A is affected, downstream spaces bound to that name are notified.
4. Each downstream space applies its own materiality test. A change that is material to A is not automatically material to B.
5. Propagation continues downstream only where materiality is confirmed.

Two properties make this safe:

- **The DAG guarantees termination.** Propagation cannot loop.
- **Materiality is evaluated locally at every hop.** Each space decides for itself, so a noisy upstream space does not force regeneration across the whole network.

Unpublished changes stop at the space boundary by construction, which is the main practical benefit of keeping the published interface narrow.

---

### 8.3 Materiality, not immediate recompute

Not every claim update should trigger a new maintained-outcome version.

The sequence should be: claim changes → find bound **maintained** outcomes → mark potentially stale → let something cheap decide whether the change is **material** to each outcome → generate a new version only when needed.

Regeneration should create a **new immutable outcome version** and surface a diff with the triggering evidence attached. The previous current version remains preserved in history.

Snapshot outcomes never enter this maintenance path. Their single stored version remains exactly as produced, even when the underlying knowledge later changes.

Whether regeneration is automatic or gated on review remains a **per-outcome property**, not a system-wide policy.

---

### 8.4 The reverse edge

The most valuable learning signal is an authoritative correction, decision, or real-world result produced at the outcome boundary — often from a human, but potentially supplied through another trusted participant in the system.

If a correction lives only in the outcome, the same error can recur next time.

Corrections must therefore flow **upward**:

1. The correction lands in the raw layer as a source — it is new evidence about the world or about the user's intent.
2. It updates or supersedes the claim that produced the error, **in the space that owns that claim**.
3. Bound maintained outcomes are reconsidered, in the owning space and transitively downstream; snapshot outcomes remain historical records.

**Corrections route to the owning space.** This is the network's version of the rule, and it is the one most easily got wrong. If a goal space notices that a fact it consumed from a base space is wrong, it must not fix the fact locally. A local fix creates a second, divergent belief with no reconciliation home, and it will be silently overwritten the next time the published name refreshes. The correction goes to the raw layer, is attributed to the owning space, and supersedes the claim there — which then benefits every other consumer of that fact.

Lineage is what makes this routing possible: the binding records which space the consumed name came from.

An architecture with only downward arrows cannot learn from outcomes.

---

### 8.5 Every outcome is a demand signal

Because every outcome is persisted, the system has a durable record of what knowledge was actually needed.

Each outcome contributes bindings to the claims that supported it. Those bindings naturally update each claim's **support count**.

This replaces promotion logic with something simpler:

- there is only one kind of claim;
- snapshot and maintained outcomes both demonstrate demand;
- reuse emerges from the binding graph rather than a hard threshold;
- frequently reused claims become easier to prioritize for future relevant outcomes.

No global promotion threshold is required.

---

### 8.6 The escape hatch becomes a gap-filling path

Raw→knowledge is lossy. The current knowledge layer will eventually be insufficient for some desired outcome.

The system therefore needs an escape hatch to raw information, but that escape hatch should preserve the rule that **outcomes ultimately depend on claims**.

When outcome construction cannot find enough relevant knowledge:

1. search or inspect raw sources;
2. derive the missing information;
3. create or reconcile normal claims in the knowledge layer;
4. record source→claim lineage;
5. bind the outcome to those claims;
6. persist the outcome and its manifest.

This is a **knowledge gap resolution path**, not a parallel path that bypasses the knowledge layer forever.

The result is important: snapshot and maintained outcomes use the same internal mechanism. New problems can enrich the shared knowledge base even when the resulting outcome will never be maintained.

---

### 8.7 Idempotency has to live in storage

In a deterministic pipeline, idempotency comes from transform purity: the same input produces the same output, so re-running is safe.

That guarantee does not exist here.

Idempotency must be enforced at the **storage layer** instead — content-addressed keys, stable claim slots, or equivalent controls so that the same source producing the same fact does not create a second competing current claim.

## 9. Relationship to Data Engineering

This system and a data platform both collect, store, and process information in order to serve goals. Decades of data engineering practice are therefore relevant, and the project should borrow deliberately rather than by accident.

But the differences have to be **load-bearing**. A statement that "our data is unstructured and our process is nondeterministic" is philosophy; it constrains nothing. Each difference below ends in a design decision it forces.

---

### 9.1 Borrow directly

**Immutable raw plus reprocessing optionality.** Most AI memory systems treat memory as one mutable store, which means an improved extractor can no longer inspect the original evidence. Keeping raw immutable preserves the option to revisit extraction or reconciliation later without making reprocessing a normal operating requirement.

**Medallion architecture.** The space network maps onto bronze/silver/gold more cleanly than the earlier three-layer model did:

| Medallion | This system |
|---|---|
| Bronze — raw, immutable, as-landed | Raw Information Lake |
| Silver — cleaned, conformed, reusable, subject-oriented | **Base spaces** |
| Gold — business-shaped marts serving specific questions | **Goal spaces** |

The borrowing that matters is not the three names. It is the underlying discipline: **reusable conformed knowledge is built once and consumed many times; purpose-shaped artifacts are built on top of it and are allowed to be numerous, opinionated, and disposable.** That discipline is exactly what stops every goal space from re-deriving the same facts from raw.

The difference to keep in mind: Medallion tiers are usually a fixed three, and refinement is the only axis. Here the network is arbitrarily deep and the axis is **purpose**, so a goal space can consume another goal space (§6.4) without that being a layering violation.

**Slowly changing dimensions.** The supersession requirement in §7.2 is exactly SCD Type 2.

**Conformed dimensions as a shared entity registry.** People, organizations, and projects appear across many spaces. Resolving them once, centrally, stops the same person existing as three entities in three spaces. In the network this becomes concrete: **the shared entity registry is itself a base space** — likely the first one — that nearly everything else consumes. The entity-resolution problem is identical.

**Star schema's fact/dimension split, as an analogy for space design.** Dimensions are shared, slowly changing, and reused across many facts; facts are numerous and question-specific. That is the base-space/goal-space distinction. The useful design heuristic that follows: *if several goals would each need their own copy of it, it is dimensional and belongs in a base space.* The formal star schema itself should not be adopted — see §9.3.

**The model DAG.** dbt's central idea is that transformations are named, versioned models that reference each other by name, forming a DAG that the tool validates and traverses. §6.4 and §6.5 are that idea applied to knowledge: `ref()` becomes a binding to a published name, sources are the raw lake, and cycle detection is a first-class feature rather than an afterthought.

**The data-product shape.** One owner, explicit input ports, explicit output ports, its own internal model, composable with other data products. This is precisely what a space is, and the vocabulary is worth borrowing even though the organizational half of Data Mesh is not (§9.3).

**Data contracts.** §7.1 and §7.4 are data contracts applied to knowledge.

**Freshness as an explicit per-view property.** Maps onto per-outcome regeneration policy.

---

### 9.2 Borrow, but invert

**The ETL/ELT instinct.** In a data platform the pipeline is the asset and tables are derived, so "just re-run it" is always available. Here the transform costs money and can produce a different answer each time. That inverts the relationship: **the derived knowledge artifact is an asset to preserve and version, not a cache to recompute**. Large-scale reprocessing of knowledge is therefore a deliberate migration event with human review, closer to a schema change than a nightly job.

**Data quality testing.** You cannot assert that an extracted claim is correct. You can assert **structural invariants**: every claim resolves to evidence; every evidence pointer is live; no two current claims occupy the same slot with contradictory values; every fact an outcome binds to exists. Correctness testing moves to sampling and human review — which is precisely what the AI-suggests / human-approves pattern is for.

---

### 9.3 Do not borrow

**A global schema or ontology defined up front.** Warehouses can conform globally because the question set is bounded and stable. Here, schema should emerge per space and be allowed to differ across spaces, with conformance only at the published-name and shared-entity boundaries. The space model exists partly to make heterogeneous internal schemas safe.

**Star schema as an actual physical model.** Its dimensional split is a good design heuristic (§9.1), but its machinery — fixed grain, surrogate keys, denormalized fact tables, conformed dimension tables designed up front — exists to make large-scale analytical joins fast. There is no join-performance problem at this volume, and imposing a fixed grain on knowledge would force exactly the up-front ontology the previous point rejects. Borrow the intuition, not the model.

**A prescribed number of tiers.** Medallion's bronze/silver/gold is a useful mental model, not a constraint to enforce. The network's depth should follow purpose, not a naming convention. Rejecting a legitimate space because it would be "a fourth tier" would be cargo-culting.

**Pipeline-centric architecture.** In data engineering the pipeline is the primary artifact and data flows through it. Here the **knowledge artifact is primary** and processing is opportunistic. Building an orchestration and scheduling layer would import complexity this system does not need.

**Completeness.** Warehouses aim for exhaustive coverage where the totals tie out. This system explicitly does not (§28). Completeness thinking is the gravitational pull that drags the knowledge layer back into being a second data lake.

**Data Mesh's organizational layer.** Domain teams, federated governance, and self-serve platform infrastructure solve an organizational problem that does not exist at single-user scale. Revisit only if the system becomes multi-writer.

Note the split from §9.1: the **data-product shape** — one owner, input and output ports, internal autonomy, composability — is borrowed and is in fact what a space is. The organizational apparatus around it is not. Keeping these separate matters, because the shape is cheap and the apparatus is expensive.

**Pipeline orchestration and scheduling.** Even though the network is now a DAG, it should not acquire a scheduler. Propagation is event-driven along recorded bindings (§8.2), not a nightly run over the graph. A DAG of knowledge artifacts is not a DAG of jobs.

---

### 9.4 The differences that force design decisions

**One important downstream consumer is a reasoner under a context budget, not a query engine.** A warehouse answers "can this question be answered." When an outcome is assembled for an AI reasoner, the system must also answer "does the right subset fit." Selection and compression therefore become first-class architectural concerns. This is one justification for keeping compact, persisted outcome views rather than repeatedly reconstructing context from scratch; human and software consumers can use the same views without changing the knowledge model.

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

## 10. Storage and History Substrate

The system uses two durable storage responsibilities:

- **Object storage** holds content: raw source objects, immutable claim-version content, immutable outcome-version content, and other large or format-specific artifacts. "Object storage" is an abstraction, not a commitment to one vendor or filesystem. An implementation may begin with local files and later use S3, Azure Blob, Google Cloud Storage, or an equivalent store without changing the knowledge model.
- **A database** is a first-class durable system of record for metadata and relationships: logical object identities, version relationships, current-version pointers, source→claim lineage, claim→outcome bindings, **cross-space bindings to published names**, **space membership, space purpose, and the space reference graph**, topic ownership, authorship, timestamps, approvals, change history, support counts or caches, retrieval metadata, and other structured state.

The space graph is database state, not a folder convention. Acyclicity must be **enforced at binding time** by the database or the application writing to it, because a cycle admitted once is expensive to unwind later.

The object store and database are both canonical, but for different responsibilities. The design does **not** require the database to be reconstructable from object storage. Production reliability comes from normal database backup, restore, migration, replication, and disaster-recovery practices.

Object-store metadata may be used for small infrastructure hints such as content type, schema version, object ID, or checksum, but it is not expected to carry the complete knowledge graph or audit history. Rich metadata and relationships belong in the database.

### 10.1 Immutable content, durable structured state

Historical content versions are preserved rather than overwritten:

- raw sources are append-only;
- claim updates create new claim versions and preserve superseded versions;
- maintained-outcome refreshes create new outcome versions and preserve prior versions;
- snapshot outcomes remain fixed as produced.

The database records which claim and maintained-outcome versions are current. It also records validity and supersession relationships so the system can answer historical questions without relying on storage-system versioning semantics.

This means the architecture does not depend on Git, S3 Versioning, or any specific blob-store history mechanism for domain history. Storage-provider versioning may still be enabled operationally, but the KB's history is represented explicitly in its own data model.

### 10.2 Change Records carry causality

Version history alone says **what** changed. Trust also requires knowing **why** it changed.

The database therefore stores a first-class **Change Record** for meaningful KB mutations. A change record should capture enough information to explain the causal event, including:

- what changed;
- previous and new version references where applicable;
- why the change was made;
- the triggering source, correction, decision, or process;
- who or what made or approved the change;
- when it happened;
- which claims, outcomes, topics, spaces, or other objects were affected.

One change record may group multiple related version changes produced by the same causal event. For example, a new source may supersede one claim and cause three maintained outcomes to generate new versions; those mutations can share one change ID.

This replaces the useful semantic role previously assigned to Git commits without making Git a technology dependency. The database can directly answer questions such as *what did I believe on this date?*, *what changed since then?*, and *why did this outcome change?* by combining version history, lineage, and change records.

## 11. The Product's Core Loop

The product should operate as a continuous loop.

### 1. Define the goal

The human establishes the purpose of a knowledge space — either by creating one, or by working within one that already exists.

The system helps clarify:

- the desired outcome;
- why it matters;
- success criteria;
- major constraints;
- time horizon;
- current state.

The user should not need to perfectly define the goal on day one. The goal can evolve, and if it evolves far enough that the space is serving two purposes, that is the signal to split (§6.4).

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

Corrections do not stop at the outcome. A correction enters the raw layer as a source, supersedes the claim that produced the error **in the space that owns it**, and marks every other outcome bound to that claim — including outcomes in downstream spaces — as stale (§8.4).

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

The system should apply the pattern of **AI does the work, human reviews the important decisions** wherever it applies. That pattern substitutes for deterministic data-quality gates where judgment is required.

But applied uniformly, it fails.

Review requests scale with input volume. At any real ingestion rate, the review queue becomes the new job — exactly the failure mode named in *minimize synchronization cost*.

### 13.1 Reuse and blast radius are different numbers

A claim's **support count** measures how many stored outcomes have used it. It is a reuse signal.

A claim change's **blast radius** measures how many **maintained outcomes** may need reconsideration if that claim changes. Snapshot outcomes do not regenerate, so they contribute to support count but not to maintenance blast radius.

Keeping those concepts separate prevents a heavily reused historical fact from automatically creating a large review burden.

### 13.2 Tiering

| Change | Handling |
|---|---|
| New claim introduced for a new outcome; narrow and reversible | Apply, optionally flag for later review |
| Change to a claim with no maintained outcomes depending on it | Apply, preserve provenance; snapshots remain unchanged |
| Change affecting a small number of maintained outcomes, reversible | Apply, flag for later review |
| Change affecting many maintained outcomes | Queue for approval before applying |
| Topic boundary creation or merge inside a space | Queue for approval |
| Change to a claim behind a **published name** with downstream space bindings | Queue for approval; blast radius crosses a contract |
| **Creating a new space** | Queue for approval — cheap to do, but proliferation is the main failure mode (§36) |
| **Splitting or merging a space** | Always reviewed. Published names must keep resolving or carry explicit redirects |
| **Adding or removing a published name** | Adding: apply, flag. Removing or changing meaning: queue for approval — it is a contract break |
| Knowledge-layer bulk migration or schema change | Explicit migration, always reviewed |
| Contradiction the system cannot resolve | Queue as a question, prioritized by value of information |

There should not normally be an active **new claim with zero outcome dependencies**. Claims are created because an outcome demonstrated the need for them (§6.3).

### 13.3 Two distinct modes

**Approve before applying** and **apply, then flag for review** are different modes.

Because immutable versions and database change records make most KB changes traceable and reversible, the second mode is available far more often than instinct suggests and preserves flow. Reserve pre-approval for changes that are hard to reverse, uncertain in a consequential way, or wide in blast radius.

### 13.4 Batch, don't interrupt

Review should be a periodic pass over a queue, not an interruption of the user's work. The queue itself should be ordered by consequence, so that if the user only reads the top of it, they still see the decisions that matter most.

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

Inside a space, knowledge is organized by topic so that it outlives the individual outcomes it served. Purpose enters as a filter on what to keep and a specification for what to assemble.

### 16.13 Derived knowledge is an asset, not a cache

Re-derivation is expensive and nondeterministic. Knowledge is preserved and versioned, not regenerated on a whim.

### 16.14 Corrections must travel upward

A fix applied only to an outcome will be undone the next time that outcome regenerates.

### 16.15 Review scales with consequence, not with volume

Human attention is spent on decisions that are wide or hard to reverse. Everything else is applied and made reversible.

### 16.16 Knowledge is consumer-agnostic

The knowledge layer maintains reusable claims and evidence. It should not encode whether the next consumer is a human, an AI agent, or another system.

### 16.17 Outcome persistence and maintenance are separate concerns

Every materialized outcome version is retained as a snapshot of work performed. Maintenance is an explicit policy layered on top: snapshot outcomes stay fixed; maintained outcomes create new immutable versions when refreshed, with one version designated current.

### 16.18 Reuse should emerge from bindings, not promotion thresholds

Claims have one lifecycle. Their support count is derived from how many stored outcomes depend on them; relevance remains the primary criterion for future use.

### 16.19 History is explicit domain data

Version relationships, causality, approvals, and change reasons belong to the KB's own data model. They should not depend on Git commits or storage-provider version history.

### 16.20 Storage technology should remain replaceable

The knowledge model should depend on an object-storage abstraction rather than a local filesystem or a specific cloud provider. Structured metadata and relationships belong in the durable database.

### 16.21 One space, one purpose

A space exists to serve one goal, or a very small number of closely related ones. When purposes diverge, the space is split rather than widened. Size alone is not the trigger; divergence of purpose is.

### 16.22 Spaces compose; the graph stays acyclic

A cross-cutting need creates a new higher-level space that consumes existing ones. It does not create a copy, and it does not create a back-reference. Acyclicity is enforced, not merely encouraged, because termination, reproducibility, and explainable causality all depend on it.

### 16.23 Cross-space reads go through published names

Everything a space does not publish is private. Consumers bind to names, never to internals. The published interface is deliberately narrower than what the space knows, because it is the only part that is expensive to change.

### 16.24 Corrections route to the owning space

A fact is owned by exactly one space. A correction discovered anywhere in the network is applied there, so that every consumer benefits and no divergent second belief is created.

### 16.25 The network is grown, not designed

Spaces accrete from demonstrated demand exactly as claims do. A new space is created when a purpose needs one, not in anticipation of one.

---

## 17. Conceptual Architecture

The architecture is intentionally simple at the highest level:

```mermaid
flowchart LR
    subgraph L1["Layer 1 — Raw Information Lake"]
        R["Everything captured<br/>Immutable • Append-only"]
    end

    subgraph L2["Layer 2 — Knowledge (a network of Spaces)"]
        direction LR
        B1["Base space<br/><i>maintain truth about X</i>"]
        B2["Base space<br/><i>maintain truth about Y</i>"]
        G1["Goal space<br/><i>achieve A</i>"]
        G2["Higher-level goal space<br/><i>achieve B</i>"]

        B1 -->|"published names"| G1
        B2 -->|"published names"| G1
        B2 -->|"published names"| G2
        G1 -->|"published names"| G2
    end

    C["Humans • AI agents • Other systems"]
    P["Purpose"]

    R -->|"learn"| B1
    R -->|"learn"| B2
    R -->|"learn"| G1
    G1 -->|"use"| C
    G2 -->|"use"| C
    B1 -->|"use"| C
    C -->|"corrections / new evidence"| R
    P -.->|"defines each space"| L2
```

Each space, expanded, has the same internal shape (§6.1):

```mermaid
flowchart TD
    IN["Inputs: raw sources and/or<br/>upstream published names"]
    CL["Claims — canonical<br/>topic-owned • versioned • evidence-linked"]
    OU["Outcomes — derived views<br/>immutable versions • build manifests"]
    PUB["Published interface<br/>the subset others may bind to"]

    IN --> CL --> OU --> PUB
```

The important separations are:

- **Raw Information** preserves what entered the system. There is exactly one lake.
- **Each space** maintains the current best understanding needed for one purpose, and produces outcomes from it.
- **The network** lets a cross-cutting purpose be served by composing spaces rather than by widening one or copying facts.
- **Published names** are the only cross-space interface, which keeps invalidation targeted and internals refactorable.
- **Consumers are outside the knowledge architecture.** The same network can serve humans, AI agents, and other software without changing its internal model.

If a space cannot support a requested outcome, outcome construction drops to raw sources or upstream published names, derives the missing claims, records lineage, and completes the outcome through the normal claims→outcome path (§8.6).

Substrate: **object storage** for immutable/versioned content and a **durable database** for metadata, relationships, current-version pointers, lineage, the space graph, cross-space bindings, change history, and retrieval. Git is not required. Support count is derived from persisted bindings across the whole network.

## 18. The Goal as a Function

```mermaid
flowchart TD
    N["Desired outcome / purpose"]
    K["Relevant existing claims"]
    G{"Enough knowledge?"}
    R["Raw information / new input"]
    C["Create or reconcile missing claims"]
    O["Persist outcome version + build manifest"]
    D{"Maintenance mode"}
    S["Snapshot<br/>kept, not refreshed"]
    M["Maintained<br/>new version when material claims change"]

    N --> K
    K --> G
    G -->|"Yes"| O
    G -->|"No"| R
    R --> C
    C --> O
    O --> D
    D --> S
    D --> M
```

Purpose is not metadata. It enters at two distinct decisions:

- During gap filling and raw→knowledge extraction, purpose decides **what must be learned and retained because this outcome needs it**.
- During knowledge→outcome assembly, purpose decides **which relevant claims should be included now**.

After the outcome is stored, its bindings become durable evidence of demand. Those bindings contribute to claim support counts whether the outcome is a snapshot or maintained.

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

The purpose or result the human–AI system is trying to achieve.

### Knowledge Space

A bounded unit of knowledge serving one purpose. It owns a set of topics and their claims, produces outcomes from them, and exposes a published interface. It may consume raw sources and the published names of upstream spaces.

Descriptively, spaces come in two flavours (§6.2), which is a characterization rather than a separate type:

- **base space** — subject-oriented, long-lived, consumed by other spaces;
- **goal space** — goal-oriented, finite, usually consumed by humans and agents.

All spaces together are the Knowledge layer. Their reference graph must remain acyclic.

### Published Name

A stable, typed identifier that a space exposes for external binding — either a published outcome or a published claim. It is the only legitimate way for another space to consume this space's knowledge. Everything not published is private.

Published names are contracts: they must keep resolving, keep their meaning, and carry explicit redirects when a space is split.

### Source

Raw information entering the system.

### Knowledge Item

A structured piece of purpose-relevant understanding.

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

A meaningful person, organization, project, product, place, concept, or other object relevant to one or more outcomes.

### Relationship

A meaningful connection among entities or knowledge items.

### Evidence

Source material supporting a knowledge item.

### State

The system's current understanding of progress or conditions relevant to a purpose.

### Action

Something a human, AI agent, or other system may need to do.

### Topic

The subject that owns a set of knowledge claims **inside a space**. Emergent rather than pre-designed: AI may propose boundaries and humans can review consequential changes. Every active claim belongs to exactly one topic, inside exactly one space.

### Claim

A named logical unit of knowledge, typed and owned by one topic within one space. A claim may have multiple immutable versions, with one version designated current when the claim has a resolved current belief.

A claim exists in the active knowledge layer because at least one stored outcome — in its own space or in a downstream space — depends on it.

### Claim Version

An immutable evidence-linked materialization of a claim at a point in time. New evidence may confirm the current version or cause a new version to supersede it. Superseded versions remain preserved with their validity period, evidence, and change record.

### Support Count

A derived property of a named claim: the number of distinct stored outcomes **anywhere in the network** whose bindings depend on that claim, directly or through a published name. Snapshot and maintained outcomes both count. It is a secondary reuse/ranking signal, not a promotion threshold and not a substitute for relevance.

### Outcome

A logical persisted view over knowledge serving one specific purpose.

Every outcome has a maintenance mode:

- **snapshot** — normally has one immutable materialized version and is never automatically refreshed;
- **maintained** — may have many immutable materialized versions and is reconsidered when bound claims change. Exactly one version is designated current.

The consumer is not part of the outcome model; it may be a human, AI agent, other system, or combination.

### Binding

The declared dependency from an outcome to the names it needs: claims within its own space, and published names from upstream spaces. Bindings are the unit of provenance, support-count calculation, targeted invalidation, cross-space propagation, and correction routing.

### Outcome Version

An immutable materialization of an outcome at a particular point in time. It records the content produced, its build manifest, creation time, and supersession relationship when another version replaces it as current.

### Build Manifest

The exact claim versions used to produce an outcome version. Every materialized outcome version has one.

### Change Record

A durable database record explaining a meaningful KB change: what changed, why, when, who or what caused or approved it, the triggering evidence or decision, and the affected old/new versions. A single change record may group several related mutations under one causal event.

### Lineage

The recorded edges from raw source to claim, from claim to outcome, and from a consumed published name to the downstream claims and outcomes that depend on it. Without lineage there is no targeted invalidation, provenance, reproducibility, or honest answer to why something changed.

### Gap

A recorded instance of the current knowledge layer failing to supply what a desired outcome needed. Resolving a gap produces or updates normal claims rather than creating a separate candidate-claim lifecycle.

## 22. An Important Architectural Distinction

The system should maintain at least three different forms of information:

### 1. Source memory

What actually entered the system.

This should remain relatively immutable.

### 2. Derived knowledge

What the system currently believes is useful and true based on sources and demonstrated outcome demand.

This may change through supersession and reconciliation.

### 3. Working context

The subset of derived knowledge assembled for a specific outcome at a specific moment.

This distinction prevents the system from treating every historical statement as equally current and equally relevant.

### How this maps onto the two layers

| Form | Where it lives |
|---|---|
| Source memory | Layer 1 — the raw lake, immutable |
| Derived knowledge | Layer 2 — claims inside a space, superseded over time |
| Working context | Layer 2 — an outcome inside a space, persisted with a build manifest |

Note that the second and third forms now live in the same layer. That is deliberate: they are distinguished by **role**, not by tier. Claims are canonical, outcomes are derived from them, and both belong to the space whose purpose they serve.

A **snapshot outcome** preserves working context exactly as it was assembled. A **maintained outcome** preserves every materialized version of that working context and designates one version as current; relevant material claim changes may generate a new current version without deleting the prior one.

## 23. MVP Hypothesis

The first version should prove one central hypothesis:

> **A purpose-driven knowledge layer can make a personal AI meaningfully more useful than an AI operating directly over a large unstructured memory store.**

The MVP does not need to ingest a person's entire digital life. It can begin with one desired outcome and a few input channels.

**The MVP should also begin with one space.** The network is the model's answer to growth, not a v1 feature. Building multi-space composition before a single space has proven useful would be designing for a problem the product has not yet earned. What v1 must do is make the *later* network cheap:

- every claim records its owning space from the first write;
- outcomes are addressable by name, so publishing one later is a property change rather than a migration;
- bindings are stored explicitly, so cross-space bindings are the same mechanism with a different endpoint.

The second space should appear when the first one's purposes visibly diverge — which is itself the first real test of §6.4.

### MVP experience

1. The user names something that needs to be produced now — the first outcome.
2. The system checks the existing knowledge layer for relevant claims.
3. If knowledge is insufficient, the user supplies context and/or the system consults available raw sources.
4. The system creates or reconciles the claims the outcome actually requires, with evidence and lineage.
5. The outcome is produced as an immutable outcome version, persisted, and bound to the exact claim versions used.
6. The user chooses whether the outcome is **snapshot** or **maintained**. The knowledge and claim lifecycle does not change.
7. Corrections and decisions flow upward as new raw evidence and may supersede claims.
8. New signals can stale only maintained outcomes; a material refresh creates a new immutable outcome version and advances the current-version pointer. Snapshot outcomes remain fixed historical artifacts.
9. Every stored outcome contributes to claim support counts, so repeated use increases demonstrated reuse naturally.
10. The system asks only high-value clarification questions, preferably batched rather than interrupting.

The goal model is elicited **through** actual outcomes rather than demanded before any useful work is done (§24).

## 24. Bootstrapping and Outcome-Level Cold Start

Cold start is not only a new-knowledge-base problem.

It occurs whenever:

> **The current knowledge layer is insufficient to support a desired outcome.**

There are therefore at least two common cases:

1. **Initial cold start** — the knowledge base is new and contains little useful knowledge.
2. **Outcome-level cold start** — the knowledge base already exists, but a new problem requires knowledge that has never been needed before.

Both cases use the same mechanism.

> **Start from the desired outcome, not from speculative knowledge collection.**

1. Ask what needs to be produced or decided now.
2. Attempt to assemble it from existing claims.
3. If knowledge is insufficient, consult raw sources and/or request the minimum additional context needed.
4. Create or reconcile the missing claims and record lineage.
5. Produce and persist the outcome with bindings to those claims.

This causes the knowledge layer to accrete **backwards from demonstrated demand**.

Two things follow:

- The first interaction around a new problem can still deliver value instead of requiring weeks of setup.
- Once the gap has been resolved, future related outcomes can reuse the newly created claims, so the same area of the knowledge base becomes progressively warmer.

A mature knowledge base can therefore still experience cold starts at its edges. That is expected, not a failure of the model.

## 25. Measuring Whether the Bet Is Working

The central bet needs numbers attached to it early.

### Primary metric — knowledge layer sufficiency rate

> What fraction of desired outcomes can be produced from the knowledge layer without needing to drop to raw sources or request new context?

If this rate does not climb within recurring problem areas, the core bet is wrong or the knowledge layer is failing to retain the right things.

### Supporting metrics

- **Correction rate on regenerated maintained outcomes** — how often a maintained outcome needs meaningful correction after refresh. Measures propagation trustworthiness.
- **Review queue volume per unit of input** — whether human-in-the-loop design is saving time or becoming the new job (§13).
- **Gap-to-claim latency** — how long it takes from discovering missing knowledge for an outcome to having the necessary claim available in the knowledge layer.
- **Knowledge reuse rate** — how often new outcomes reuse claims that already existed rather than creating entirely new ones.
- **Support-count distribution** — whether a useful core of claims is being reused across many outcomes or the knowledge layer is fragmenting into one-off facts.
- **Synchronization time per day** — the human effort required to keep important real-world context current.
- **Stale maintained-outcome ratio** — how many maintained outcomes are currently out of date relative to their bound claims. Snapshot outcomes are excluded by definition.

Support count is an explanatory signal, not a target to maximize. The system should never prefer a popular but irrelevant claim over a less-used claim that better fits the desired outcome.

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
- a system that asks for approval on everything it does;
- a sprawling network of thin spaces built before a single space has demonstrated value.

The early product should stay focused on proving that **purpose-driven knowledge produces better human–AI collaboration**.

---

## 27. Possible Initial Product Experience

A simple product could have several main views.

### Goal

What are we trying to accomplish?

### Spaces

What spaces exist, what is each one's purpose, and how do they depend on each other? A view of the network itself, showing published names and their consumers, is the main new surface v5 requires.

### Knowledge

Within a space, what does the system currently understand that matters, and which claims are most reused?

### Inbox

What new information has entered the system, and what did it change?

### Outcomes

What outcomes have been produced? Which are snapshots, which are maintained, what is stale, and what changed?

### Review

Which AI-proposed changes or unresolved contradictions deserve human judgment, ordered by consequence?

### Collaborate

What should the human and AI agents think about, decide, or do next using the shared knowledge base?

The user should be able to see the evolving shared working model rather than interacting only through a chat window.

## 28. Sync Should Be Selective, Not Exhaustive

The system does not need to know everything about a person or project.

It needs to know **enough of the right things for the outcomes that matter**.

The objective is not:

> Human Brain = AI Memory

Nor is it:

> Raw Data = Knowledge Base

The objective is closer to:

> Goal-Relevant Shared Context ≈ What the human–AI system needs to work effectively

The system should therefore optimize for **sufficient synchronization**, not complete synchronization. New outcome-level cold starts are acceptable; the important property is that resolving them leaves reusable knowledge behind.

## 29. Evolution Path to Multi-Writer

The first version is single-user. Simplicity should win. But a few decisions made now determine whether multi-writer is a later feature or a later rewrite.

**What must be true from the start:**

- **Every claim has an author and a timestamp.** Adding attribution later means backfilling something that was never recorded.
- **Every claim has exactly one owning topic, inside exactly one owning space.** Ownership is how concurrent writers are arbitrated; retrofitting it into a knowledge layer that grew without it is a data migration. The space is also the natural future unit of access control and sharing, which is a second reason to establish the boundary now even though v1 has one writer.
- **Cross-space consumption goes through published names from day one.** In a multi-writer world this becomes the sharing boundary: another person can be granted a space's published interface without being granted its internals. If consumers are allowed to reach into internals in v1, that option is gone.
- **Approvals are durable change records.** Multi-writer needs a shared, auditable record of who decided what, when, and why. The database records the approval and links it to the affected versions and causal change record.
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

In the v5 model this is not a new architecture. Each of those is a space, or a small cluster of spaces, on the shared raw lake.

Two consequences worth naming:

- **Coordination across areas is a space, not a supervisor.** A "personal chief of staff" that spans work, finance, and family is a higher-level goal space consuming the published names of the others. It needs no special privileges, because it consumes them the same way any space does.
- **Privacy boundaries follow published interfaces.** A space can expose a coarse summary while keeping sensitive internals private. That is the same encapsulation mechanism used for refactoring, reused for confidentiality — which is why §29 treats published names as a prerequisite for multi-writer rather than a later feature.

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

> **Create a purpose-driven personal AI that continuously transforms a person's messy stream of information into a small, evolving, shared body of knowledge that humans and AI agents can use together to achieve important outcomes—so AI can do more of the cognitive heavy lifting while humans remain focused on intent, judgment, and responsibility.**

---

## 33. One-Sentence Version

**Don't try to make AI remember everything about a person; maintain the shared knowledge that humans and AI agents actually need for the outcomes they are trying to achieve.**

---

## 34. Foundational Product Question

The project can be built around one question:

> **What is the minimum amount of synchronization effort needed to maintain enough shared context for humans and AI agents to operate as one effective system over time?**

The two-layer model — **one permissive raw lake, plus a network of purpose-bounded knowledge spaces composing as a DAG** — is the proposed answer.

The raw layer minimizes capture cost. Each space keeps its purpose small enough that the AI can decide what matters within it. Base spaces make durable knowledge reusable across purposes. Goal spaces package that knowledge for concrete work and record what was actually needed. Composition means a new cross-cutting purpose costs a new space, not a redesign.

---

## 35. The Bet

This product is ultimately making a specific bet:

> **The bottleneck to highly useful personalized AI is not primarily model intelligence or access to more data. It is the absence of a purpose-driven system that continuously converts messy context into useful, current, reusable shared knowledge.**

If that bet is correct, winning personal AI products will not simply have the largest memories.

They will have the best mechanisms for deciding **what matters for a desired outcome, turning gaps into reusable knowledge, and keeping humans and AI agents aligned on the same current understanding**.

## 36. Open Design Questions

These remain unresolved and are worth tracking explicitly rather than deciding by default.

1. **What is the unit of a claim?** Too fine and the fact namespace becomes unmanageable and binding becomes brittle. Too coarse and targeted invalidation stops being targeted because every change touches too many outcomes.

2. **Who writes the outcome specification?** If the user must specify precisely what an outcome needs, the system inherits the curation burden it was built to remove. If AI infers it, the binding set can drift and invalidation may become unreliable.

3. **How are space and topic boundaries revised after the fact?** Splitting or merging means re-homing claims that outcomes are already bound to. Inside a space this is a rename with redirection. Across a space boundary it touches a published contract, so the working answer in §6.6 is *published names must keep resolving or carry explicit redirects*. Unresolved: how long redirects live, whether a redirect chain is ever collapsed, and what happens when a split genuinely changes a published name's meaning rather than its location.

4. **What is the retention policy for the raw layer?** Immutability and append-only are stated. Unbounded growth is implied. At what point does that become a cost or privacy problem, and what is deleted first?

5. **How is a superseded claim distinguished from a contradicted one?** "I changed my mind" and "two sources disagree" have the same shape and different correct handling.

6. **When does the goal model itself change, and what happens downstream?** A goal shift can change what future outcomes need. Because claims are now retained through demonstrated outcome use rather than goal membership, does a goal shift require any knowledge migration at all, or only new outcome assembly behavior?

7. **How long should snapshot outcomes be retained?** They are useful as demand history, reproducibility artifacts, and inputs to support count, but indefinite retention may create privacy and storage costs. If snapshots expire, should their contribution to support count expire too?

8. **What is the right granularity of a space, and what stops proliferation?** The model makes creating a space cheap, which makes over-fragmentation the most likely failure mode: dozens of thin spaces, each with a small published interface, and most of the system's real complexity pushed into the edges between them. What is the concrete signal that a space should be split, and the concrete signal that two should be merged? A candidate heuristic is *coherence of purpose per claim*, but it is not yet operational.

9. **Who decides that a new space is needed — user or AI?** Creating a space is a more consequential judgement than creating a claim, because it changes the shape of the network. The AI-proposes / human-approves pattern (§13) is the obvious answer, but the proposal needs a trigger. Repeated cross-cutting outcomes that keep binding to the same set of published names are a plausible one.

10. **What happens to a goal space when its goal completes?** Archive it, keep it queryable, or dissolve it? Its outcomes are historical artifacts worth keeping. Its claims may still be referenced by downstream spaces, which means a completed goal space cannot simply be deleted while anything still binds to its published names.

11. **Does the base/goal distinction need to be a real type, or does it stay descriptive?** It is currently descriptive. If the system ever needs to treat them differently — different retention, different review defaults, different lifecycle — it becomes a real attribute, and that decision is cheaper now than later.

12. **When is a cross-cutting need a new space rather than one more outcome in an existing one?** Both are legitimate. Creating a space is the right answer when the need is durable and has its own reconciliation logic; adding an outcome is right when it is one-off assembly. The boundary between these cases is not yet sharp.
