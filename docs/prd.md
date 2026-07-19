# Product Requirements Document: Shared Project Knowledge Base — Skills & CLI

| Field | Value |
|---|---|
| **Status** | Draft v0.5 (supersedes v0.4) |
| **Owner** | Pengfei (Director of AI Engineering) |
| **Last updated** | 2026-07-18 |
| **Product name** | KB Skill Suite (working name; skills prefixed `kb-`, CLI named `kb`) |
| **Delivery form** | A set of [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) + an independently versioned `kb` CLI toolset |

This document is the **root and source of truth** for the product. All detailed design documents (command specifications, implementation plans) and all code derive from it. Decisions and their rationale are recorded here directly — in the *decision and rationale* passages of §6 — and the normative vocabulary is Appendix C.

---

## 1. Executive Summary

This product is a **shared project knowledge base** in which every human role — product manager, UX designer, software engineer, infrastructure engineer, QA engineer — and every AI agent works in the **same context**. The knowledge base holds two classes of documents: **raw sources** (immutable evidence: vision documents, meeting notes, chat histories, research, compliance rules) and **synthetic documents** (human-authored, agent-maintained refinements: outcomes, design documents, specifications, test plans, runbooks, context packages — any document type a project needs). Synthetic documents form a derivation graph that progressively breaks large intent into granular, self-contained working documents; a coding specification is one possible leaf, not the privileged one.

The division of labor is the product's central idea: **humans drive creation, agents perform maintenance.** Software engineers and their peers spend their time co-authoring the documents that direct AI agents, rather than producing the downstream artifacts directly. A document is born in a human-led session and is considered accepted at creation; from then on, agents keep it consistent with new evidence — consolidating new evidence into the documents it concerns (CS6), propagating updates downstream when upstream information changes, and **asking a human whenever anything is unclear or conflicting rather than assuming**.

The knowledge base is **purpose-built**, the way a data warehouse is. Raw documents are the lake — un-purposed evidence, not directly useful on its own — and human-led co-authoring progressively distills them, through intermediate **building blocks**, into **purpose documents**: leaf documents assembled from a small sub-network of the KB that carry complete, and *only*, the context a consuming agent needs for one specific outcome (an execution plan for a single API, a test plan for one feature). The KB-level purpose, recorded in the governance **charter**, shapes the architecture itself: directory structure, type vocabulary, granularity. The warehouse analogy is explanatory, not mechanical — distillation is always human-led (G2), never an automated ETL pipeline (NG3). Documents are also never silos: beyond provenance, governance-declared **associative links** (§6.9) make the KB a navigable network of knowledge.

The capability ships in two parts: a small set of **Agent Skills** (the judgment layer: how to ingest, co-author, and maintain) and a **`kb` CLI** (the deterministic layer: search, filtering, frontmatter extraction, graph queries, validation), developed and versioned independently so tooling can improve without touching the skills.

## 2. Problem Statement

Project knowledge today is fragmented by role: product intent lives in PM tools, design rationale in design tools, engineering decisions in wikis and pull requests, test intent in QA suites. Each role's AI agents see only that role's fragment. The consequences:

1. **No shared context.** An engineer's coding agent cannot see the UX rationale; a QA agent cannot see the outcome a feature serves. Every agent operates on partial, role-siloed information, and every human pays an integration tax reconciling the fragments.
2. **Re-derivation waste.** Agents re-read and re-interpret the same raw material on every task instead of consuming knowledge compiled once and maintained.
3. **Assumption fabrication.** When context is missing or contradictory, agents guess. In regulated environments, an unsourced guess embedded in a delivered artifact is a compliance defect, not a nuisance.
4. **Knowledge rot.** Intent changes across meetings and messages; nothing systematically supersedes stale documents or propagates the change to everything derived from them.
5. **The wrong human bottleneck.** Humans are pulled into low-value clarification loops during execution, instead of investing their time where it compounds: authoring and curating the documents that direct the agents.

No existing solution provides a role-neutral, agent-operable, human-governed knowledge substrate with evidence-to-artifact traceability. RAG pipelines retrieve but never compile; agent memory products personalize but don't specify; PM and wiki tools hold documents in forms agents cannot reliably maintain.

## 3. Goals and Non-Goals

### 3.1 Goals

- **G1 — One shared context.** All project roles, human and AI, read and write the same knowledge base. Cross-role derivation (a test plan derived from a UX flow and an outcome document) is a first-class, expected pattern. *This is the goal the product must achieve above all others.*
- **G2 — Human-driven creation, agent-driven maintenance.** New synthetic documents are created only in human-initiated, human-steered sessions. Agents update, propagate, reconcile, and repair — never originate content autonomously.
- **G3 — Clarification-first agents.** Skills must make it structurally normal for agents to ask humans questions. When information is missing, ambiguous, or conflicting, the agent's default action is to ask — falling back to draft status or the uncertainty register only when the human defers.
- **G4 — Evidence and traceability.** Raw sources are immutable; every synthetic document declares its parents (raw and/or synthetic, from any depth); derivation chains are acyclic and terminate at evidence or recorded human decisions.
- **G5 — Freshness with propagation.** Newer information supersedes older by default; revising or superseding a document triggers identification and human-confirmed update of everything derived from it, with deliberate deferrals kept visible (`pending_upstream`, CS6).
- **G6 — Any document type, any granularity.** The type vocabulary is project-defined. Coding specs, UX flows, test plans, ADRs, infra runbooks, and context packages are all just types with optional per-type readiness criteria.
- **G7 — Plain-text substrate, deterministic tooling.** Markdown + YAML in Git; all mechanical operations (search, filter, validate, graph queries) provided by a tested, independently versioned CLI that skills share.
- **G8 — Token-economical operation.** Progressive disclosure by construction: agents survey via indexes and frontmatter (CLI-served) before reading bodies.
- **G9 — Purpose-built, network-shaped.** The KB serves a declared purpose (the governance charter) at every scale: the KB-level purpose shapes architecture and vocabularies, and the end product is the **purpose document** — clean, self-contained context for one specific outcome. Documents form a navigable network: provenance (`derived_from`) plus governance-declared associative links (§6.9), never a pile of unrelated files.

### 3.2 Non-Goals

- **NG1.** Orchestrating downstream execution agents (coding harnesses, CI/CD, design tools). The KB directs them; it does not run them.
- **NG2.** Prescribing a methodology, document taxonomy, or fixed layer structure. Structure is emergent (derivation graph) and vocabulary is project configuration.
- **NG3.** Autonomous document generation pipelines. Explicitly rejected, not merely deferred.
- **NG4.** An approval/review workflow product. Acceptance happens at creation, with the human present; there is no separate review queue in v1.
- **NG5.** Purpose-specific context packaging (`kb-pack`) in v1. A context package is an ordinary document type a human can author when needed — purpose documents (G9) are exactly such human-authored packages; what v1 excludes is dedicated packaging *tooling*, not the documents.
- **NG6.** Retrieval infrastructure (embeddings, vector stores). The CLI's text/frontmatter search is the baseline; external indexes may be added later as accelerators, never as sources of truth.
- **NG7.** Multi-repository knowledge federation in v1 (reserved; see OQ4).

## 4. Users and Personas

**P1 — Document authors (humans, all roles).** PM, UX designer, software engineer, infrastructure engineer, QA engineer. Each authors the document types natural to their role, derived from shared upstream documents and evidence. Their working mode shifts from producing downstream artifacts to co-authoring and curating directing documents.

**P2 — Maintenance agent (AI).** An LLM agent with this skill suite loaded, operating inside a human's session: ingesting sources, co-drafting under direction, consolidating new evidence, propagating updates, asking questions.

**P3 — Consuming agents (AI).** Coding agents, test-generation agents, design-to-code agents, document-generation agents — any executor that reads current documents (and their parents) as its working context.

**P4 — KB steward (human).** Configures governance (charter, vocabularies, conventions, readiness checklists), monitors lint reports, owns the CLI/skill versions in use. Typically the AI engineering lead.

**P5 — Auditor (human, read-only).** Traverses any artifact's derivation chain back to evidence and recorded decisions.

## 5. Product Overview

### 5.1 Concept

```
                     ┌────────────────────────────────────────────────────┐
                     │            SHARED KNOWLEDGE BASE (Git repo)        │
                     │                                                    │
 vision docs  ─────► │  raw/                    synthetic/                │
 meeting notes─────► │  (immutable            (human-created,             │
 chat exports ─────► │   evidence +            agent-maintained           │
 compliance   ─────► │   recorded              derivation graph:          │
 human answers─────► │   decisions)            outcomes, UX flows,        │──► consuming
                     │        ▲                specs, test plans,         │    agents &
                     │        │ derived_from   runbooks, packages …)      │    humans
                     │        └────────────────────┘                      │
                     │  governance/  (charter, conventions, readiness)    │
                     │  kb-config.json (config + root marker)             │
                     │  index.md, log.md                                  │
                     └────────────────────────────────────────────────────┘
                                    ▲                      ▲
                          kb-* Agent Skills          kb CLI (deterministic:
                          (judgment: ingest,         search, filter, graph,
                          co-author, maintain)       validate, frontmatter)
```

Humans of every role and their agents converge on one repository. Creation flows top-down through human-led sessions; evidence flows in through ingestion; freshness flows downstream through revision, supersession, and propagation; questions flow back to humans whenever judgment is required.

### 5.2 Architecture: Skills + CLI

The capability is deliberately split into two independently evolving components:

| Component | Nature | Contains | Evolves by |
|---|---|---|---|
| **`kb` CLI** | Deterministic, tested Python toolset | Search, filter, document read with frontmatter/path projections (`kb show`), graph queries, validation, deterministic reports, ingest adapters, index/log maintenance | Its own release cycle, unit-tested, semver |
| **`kb-*` skills** | Instructions + judgment (SKILL.md + templates) | When and how to ingest, co-author, resolve conflicts, ask humans, maintain | Prompt-level iteration, thin and stable |

Rationale: mechanical correctness (does this frontmatter parse? which documents derive from X?) must not depend on model judgment; shared tooling avoids per-skill reimplementation; adapters (file, clipboard, Slack, …) can be added to the CLI without touching any skill; and CLI output modes designed for progressive disclosure (paths-only, frontmatter-only) directly serve token economics. Skills MUST call the CLI for every operation the CLI provides and MUST NOT reimplement it.

## 6. Information Model

### 6.1 Document Classes

| Class | Location | Mutability | Created by | Maintained by |
|---|---|---|---|---|
| **Raw** | `raw/` | Immutable, append-only | Ingestion, session records, feedback intake (all human-initiated) | Nobody (corrections arrive as new raw docs) |
| **Synthetic** | `synthetic/` | Living | Humans (co-authoring sessions), via `kb create` | Agents, under §6.7 rules |
| **Governance** | `governance/` | Human-controlled | KB steward | Steward, with agent assistance |
| **Index** | `<dir>/index.md` (one per directory) | Regenerated | CLI | CLI (read-only for humans/agents) |
| **Operational** | `log.md` (`type: log`) | Appended | CLI | CLI |

**Class is derived from the authoritative `type` field, not from location** (FM0): `index` → Index; `raw-source`/`chat`/`feedback` → Raw; the reserved governance types (`charter`, `conventions`, `kb-config`, `health`) → Governance; `log` → Operational; any other type → Synthetic. The *Location* column is therefore an **invariant that `kb validate` enforces** (a document's directory must agree with its `type`), not the definition of its class — a misplaced file is a validation error, fixed with `kb mv`, never silently reclassified.

Governance documents divide by **binding force**. The **charter** (`GOVERNANCE-CHARTER`) records intent: who the KB serves, its consumers, and the architectural rationale behind structure, vocabularies, and granularity — judgment context, consulted when structure is proposed, rarely changed. **Conventions** (`GOVERNANCE-CONVENTIONS`) are the binding rules for how documents are written and maintained — the top of IN1's precedence chain, consulted in every authoring and maintenance session, accreting as the project learns. Anything machine-checkable belongs in neither: it goes in `kb-config.json` (with `governance/kb-config.md` as its human-readable reference). Rule of thumb: rationale → charter; rules → conventions; vocabularies and switches → config.

Raw documents come in three subclasses. **Sources** (`raw/sources/`) are ingested external material. **Session records** (`raw/chats/`) are the archived history of every human-led `kb-author` or `kb-ingest` session, headed by an agent-written, human-confirmed decision summary; they are the captured form of human decisions — "the PM decided on 2026-07-08" cites the session record. **Feedback** (`raw/feedback/`) is evidence produced by consumers of synthetic documents — a coding agent's errors while executing a spec, failing tests, structured review comments — filed with an `about:` reference to the document it concerns.

### 6.2 Structure: an emergent derivation graph, not fixed layers

There is **no predefined layer taxonomy**. Structure emerges from `derived_from` links, subject to five rules:

- **DG1.** Every synthetic document declares one or more parents in `derived_from`. Parents may be raw documents (sources, session records, feedback), governance documents, or other synthetic documents — from any depth, in any combination. (A test plan citing a coding spec, an outcome document, *and* a raw compliance PDF is normal.)
- **DG2.** The graph is acyclic, and every chain terminates at raw or governance documents. (Termination follows from DG1, link resolution, and acyclicity — a theorem, not a separate check.)
- **DG3.** Granularity is a human choice made during authoring. Coverage discipline applies only to **decomposition**: where a document explicitly commits scope to be fulfilled by child documents, uncovered committed scope is made explicit (in the parent or the uncertainty register), never silently dropped. Documents that are extractions or reference material (concepts, facts, constraints distilled from raw sources) make no claims about their children — future documents may derive from them freely, and they owe those children no coverage statement.
- **DG4.** "Depth" is a derived property (distance from evidence), computable by the CLI for reporting — never a field an author must manage.
- **DG5.** Every synthetic document has at least one session record (`raw/chats/`) among its `derived_from` parents — the record of the human-led session that created it, joined over time by the sessions that revised it. Human involvement in every document's existence is thereby a mechanically checkable property (`kb validate`), not a policy assertion.

### 6.3 Document Types and Readiness

`kb-config.json` (strict JSON at the KB root; also the root marker) defines the project's **type vocabulary** — an open, project-owned list (illustrative: `domain-note`, `outcome`, `ux-flow`, `capability`, `coding-spec`, `test-plan`, `adr`, `runbook`, `context-package`). For any type, governance MAY define a **readiness checklist**: the conditions under which a document of that type is complete enough for its consumers. During co-authoring, the agent checks the draft against the applicable checklist and reports gaps to the human; unresolved gaps are grounds for the human to leave the document in `draft`.

Readiness checklists are per-type: a `coding-spec` checklist (objective, verifiable acceptance criteria, interfaces, constraints, dependencies, scope boundary, self-containment, zero open questions) ships as an *example profile* in Appendix B; a `test-plan` or `ux-flow` type would define different criteria. The suite mandates the mechanism, not any particular checklist.

### 6.4 Frontmatter Schema

```yaml
---
id: KB-000042                    # stable identity; never changes (§6.5)
type: coding-spec                # from the project vocabulary
title: Rate-limit alert webhook
description: Webhook contract and behavior for rate-limit alerts. Covers retry and auth semantics.  # ≤2 sentences; copied into index.md
tags: [alerting, api, compliance]  # optional; values from the governance tag vocabulary
status: current                  # draft | current | superseded | retired
derived_from:                    # parents: any class, any depth, one or more
  - KB-000007                    # an outcome document
  - KB-000019                    # a ux-flow document
  - RAW-000113                   # a raw compliance source
  - CHAT-000027                  # the authoring session record (DG5)
supersedes: KB-000031            # present only when replacing a prior document
links:                           # OPTIONAL associative links (§6.9); types from the governance vocabulary
  references: [KB-000012]
pending_upstream: [KB-000007]    # present only while a parent's revision awaits propagation (CS6)
instructions: |                  # OPTIONAL maintenance directives (§6.6)
  Keep the interface table consistent with KB-000012.
  Do not change retry semantics without asking the author.
timestamp: 2026-07-10T14:30:00Z        # last modification (any actor)
last_human_touch: 2026-07-10T14:30:00Z # last human-confirmed revision (§6.8)
---
```

- **FM0 — universal `type` (OKF).** Per the Open Knowledge Format, **every markdown file in the KB carries a mandatory `type` frontmatter field** — no exception, including `index.md` (`type: index`) and `log.md` (`type: log`). `type` is the **authoritative classifier**: a document's class (raw/synthetic/governance/index) is *derived from `type`*, and `kb validate` (a) enforces that every `*.md` has a `type` and (b) flags any file whose location disagrees with its `type` (see §6.1). `type` wins over path.
- **FM1.** Beyond the universal `type`: synthetic documents additionally require `id`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`. Raw documents carry a reduced schema (`id`, `type: raw-source | chat | feedback`, `ingested_at`, `origin`, plus `about` for feedback records; ingest also always writes a `title`, used in `index.md` listings but not part of the mandatory set). Governance system documents carry `id` (reserved slug), `type`, `title`, `description`; index documents carry `type: index` + `description` (no `id`). The optional synthetic keys are `tags` (FM1b), `supersedes`, `instructions` (§6.6), `links` (§6.9), and `pending_upstream` (CS6); anything else falls under FM2.
- **FM1a.** `description` is at most two sentences. Every directory has an `index.md` (a first-class document, `DocClass INDEX`, with its own `type: index` and folder-level `description`) whose CLI-generated body enumerates each child's `description` verbatim, so survey-level reading can proceed on indexes alone. `index.md` files are maintained only by the CLI (`kb index`) and are read-only for humans and agents.
- **FM1b.** `tags` is an optional list; when present, every value must appear in the tag vocabulary declared in `kb-config.json` (`kb validate` flags undeclared tags for the steward to add to the vocabulary or correct).
- **FM2.** Unknown additional keys are permitted and preserved (forward compatibility; OKF extension-key behavior). Known schema keys appearing on the wrong class are validation findings, not extension keys — FM2 openness covers only genuinely unknown keys.
- **FM3.** Mechanical validity of all of the above is checkable by `kb validate` without an LLM.

### 6.5 Identity: `id` field and OKF path-IDs — decision and rationale

OKF defines a concept's ID as its bundle-relative file path. This PRD **keeps a stable frontmatter `id` in addition**, and uses the two for different jobs: **the path is the address; the `id` is the identity.**

Why a path alone is insufficient here:

1. **Reorganization is expected.** A multi-role KB will be restructured as the project grows (directories split by role, by epic, by quarter). Path-IDs turn every reorganization into a link-breaking event across the whole graph; stable `id`s make moves free (the CLI re-resolves).
2. **Supersession needs identity across files.** `supersedes: KB-000031` must keep meaning after the old file is archived or the new one is renamed. A path-based chain rots.
3. **External references must not rot.** Commit messages, code comments, tickets, and audit findings will cite documents. `KB-000042` survives ten years of refactoring; `synthetic/specs/webhook.md` will not.
4. **Merge safety.** Concurrent branches renaming or moving files merge cleanly when links are id-based.

Numeric ids zero-pad to **six digits** and must be written in canonical form — `KB-000042` is valid, `KB-0000042` is not — so every citation of a document is byte-comparable and `kb validate` can flag non-canonical forms.

Reconciliation with OKF: `derived_from`/`supersedes` use `id`s (the machine layer); links *within document bodies* remain OKF-style relative paths (the human layer); `id` rides as an OKF extension key, so bundles stay OKF-conformant. The CLI resolves id↔path by scanning frontmatter on each invocation (no stored index; the `kb show --output path` projection, CLI-3a), and `kb mv` updates body links on moves. Net cost of keeping `id`: one frontmatter line and a per-invocation scan — cheap insurance for properties 1–4.

System governance documents are an exception to the numeric id scheme: `governance/charter.md`, `governance/conventions.md`, and `governance/kb-config.md` carry **reserved fixed slug ids** (`GOVERNANCE-CHARTER`, `GOVERNANCE-CONVENTIONS`, `GOVERNANCE-KB-CONFIG`) assigned by `kb init`, so agents can address these system files by a stable, well-known id.

### 6.6 Per-Document Maintenance `instructions` — decision and rationale

**Adopted, as an optional frontmatter field.** A document may carry natural-language directives telling maintenance agents how to keep it: what to update on what triggers, what to preserve, what requires asking a specific human, style and length constraints. This makes each document a self-describing maintenance contract — the instruction lives exactly where it applies, travels with the document, and is versioned with it. It is, in effect, a per-document micro-skill.

Guardrails (mandatory):

- **IN1 — Precedence.** Governance conventions > document `instructions` > session-level requests. An instruction cannot relax a governance rule (e.g., cannot exempt a document from provenance or validation).
- **IN2 — Scope of authority.** Instructions may direct *how this document is maintained*. They may not direct agents to create documents, modify other documents, contact external systems, or alter statuses — those remain governed by the skills' own rules. Agents treat out-of-scope instructions as inert and flag them in lint.
- **IN3 — Conflict handling.** If an instruction conflicts with governance, with another applicable instruction, or with a human's in-session request, the agent surfaces the conflict to the human rather than choosing silently (per G3).
- **IN4 — Lint coverage.** `kb-lint` reports unparseable, out-of-scope, or mutually contradictory instructions.

### 6.7 Conflict, Supersession, Revision, and Propagation Semantics

- **CS1 — Latest wins, by default.** When newly ingested information conflicts with existing knowledge, the newer information takes precedence. The prior content is superseded, never silently edited away: raw stays immutable; affected synthetic content is updated with the superseded version preserved in Git history and, where document-level, via `supersedes` chains.
- **CS2 — Ask before deciding.** Where "which is newer/authoritative" or "what should change downstream" requires judgment — ambiguous scope, partial contradiction, doubtful source authority — the agent asks the human **first**. Only if the human defers ("park it") does the item enter the uncertainty register as an open question with its citations.
- **CS3 — Propagation.** Superseding **or revising** any document (raw or synthetic) triggers computation of the affected downstream set (`kb links --reverse --transitive`). The agent presents the propagation plan (which documents, what kind of change each needs), then applies updates — respecting each document's `instructions` — with human confirmation for every change that involves judgment, and mechanical application (with logging) for changes governance marks as safe (e.g., updating a cited figure).
- **CS4 — No fabrication.** At no point may an agent fill a gap with invented content. Missing information is a question (CS2) or an explicit gap notation — never a plausible guess. Fabrication is the suite's severity-1 defect class.
- **CS5 — Skill-encoded permission to ask.** Every skill's SKILL.md must state, prominently, that asking the human is a *preferred, first-class action* — including concrete question-framing guidance (what is known, what is missing/conflicting, why it matters, what options exist). This counters agents' default bias toward self-sufficient completion.
- **CS6 — Consolidation and deferred propagation.** New evidence concerning an existing synthetic document — the human declares which documents it concerns at ingest (the agent may suggest candidates from its overlap survey; attachment is human-confirmed) — is **consolidated** by in-place revision (`kb revise`, CLI-14): the id is preserved, the new raw document joins `derived_from`, and the agent proposes each change for in-session human confirmation. Supersession is reserved for genuine replacement or rescoping. After a revision, the agent analyzes the downstream consequence (CS3) and presents it; the human either has the agent propose the downstream changes for approval now, or **defers** — each affected child is then marked `pending_upstream: [<revised parent id>]` with status unchanged. The marker is cleared by the revision that performs the propagation; consuming agents reading a marked document are **warned, not blocked** (§6.8).

**Why in-place revision preserves the id — decision and rationale.** Consolidation is routine: a maintained document absorbs new evidence many times over its life. If every consolidation minted a new document (supersession), ids would churn (`KB-000042` → `KB-000051` → `KB-000063` …) and the external-reference stability that justifies frontmatter ids (§6.5, property 3) would collapse — every commit message and ticket citing the document would rot within months. Two alternatives were rejected: *supersession-for-every-change* (maximally explicit lineage, but citation rot), and a *hybrid* that superseded only "semantic" changes while editing "small" ones in place (requires an arbitrary, contestable boundary with no defensible judge). Hence: **revision for maintenance, supersession only for genuine replacement or rescoping**; Git history and `log.md` record the revision trail.

### 6.8 Status and Lifecycle

```
draft ──────► current ──────► superseded
  ▲              │                 
  └── (human ────┘            retired (scope dropped)
       reopens)
```

- **LS1.** A document created in a human-led session becomes `current` at creation — acceptance is implicit in co-authorship. The human may instead leave it `draft` (open questions pending), returning later to complete it.
- **LS2.** There is no separate approval workflow. The accountability mechanism is visibility: `last_human_touch` records the last human-confirmed revision; `timestamp` records the last change by any actor. `kb-lint` reports every `current` document whose content changed since its `last_human_touch` (the **drift report**), so agent maintenance is always auditable and never invisible.
- **LS3.** Agent edits to `current` documents occur only within the operations defined in §7's skills (ingestion propagation, human-directed revision, lint-proposed fixes accepted by a human) — never as free-standing autonomous edits.
- **LS4.** Superseded and retired documents are preserved with updated status; nothing is deleted. `log.md` records every creation, ingestion, revision, supersession, propagation, and human answer, with date and actor.
- **LS5.** Revision (`kb revise`) advances `timestamp` (and `last_human_touch` on human confirmation); the id never changes, and status never changes *implicitly*. Explicit, human-directed status transitions — `draft` → `current` on completion, `current` → `draft` on reopening (LS1), retirement — ride the same command; only `kb create --supersedes` sets `superseded` (its status coupling stays atomic). A document carrying `pending_upstream` remains `current`: knowingly awaiting propagation is visible state on the document, not a lifecycle transition.

**Why `pending_upstream` is a marker, not a status — decision and rationale.** "A human consciously deferred this propagation" and "nobody has looked yet" are different audit states and must be mechanically distinguishable. A fifth `stale` status was rejected: every `--status current` filter would silently drop the only spec that exists, and lifecycle semantics would overload. Lint-computed staleness with no marker was rejected: timestamps alone cannot tell deliberate deferral from neglect. A separate marker keeps status clean, names exactly which parent revision is pending, and is cleared by the revision that performs the propagation. Consumers of a marked document are **warned, not blocked** — unlike a `draft` (incomplete by declaration), a marked document is complete, merely possibly outdated, and it remains the best available context.

### 6.9 Associative Links: the knowledge network beyond provenance

`derived_from` records where a document *came from*; a network of knowledge also has relationships that are not parentage — a spec references an ADR it must not violate, two documents constrain each other, new evidence contradicts old.

- **AL1.** Synthetic documents MAY declare typed **associative links** (`links:` frontmatter, mapping link type → list of ids). Targets may be documents of any class. The link-type vocabulary is declared in `kb-config.json` like types and tags; the suite ships defaults (`references`, `contradicts`, `constrains`). `kb validate` flags undeclared link types and unresolvable targets.
- **AL2.** Associative links live on **synthetic documents only**; raw immutability is fully preserved. A raw↔raw relationship (a new note contradicting last month's) is expressed where it matters — in the downstream synthetic documents, where the later evidence overrides the earlier on conflict (CS1).
- **AL3.** Associative links never satisfy DG1/DG5 parentage and never create propagation obligations. When a link target is revised or superseded, linking documents surface in the impact report as *aware of change* — notified, never obligated; no `pending_upstream` marking. They are likewise exempt from DG2: cycles among associative links (mutual `references`) are legal, and they never count toward derivation-chain termination.
- **AL4.** `kb links` traverses associative links alongside provenance (flag-selected), so the network is machine-navigable end to end.

**Why links live on synthetic documents only — decision and rationale.** A relationship discovered *after* ingest (new note-B contradicts old note-A) cannot be written onto either raw file without breaking raw immutability. Two alternatives were rejected: redefining raw as "body-immutable" with appendable link frontmatter (weakens the immutability guarantee auditors rely on), and standalone edge-record documents (a new document class and file sprawl for marginal benefit).

**Why links notify but never obligate — decision and rationale.** If associative links carried propagation obligations, every link would become a subscription: propagation fatigue (§11) would multiply with network density, and authors would stop declaring links to avoid the maintenance cost. Only `derived_from` provenance creates maintenance obligations; associative links buy awareness for free.

## 7. Component Requirements

### 7.1 The `kb` CLI (deterministic toolset)

Independently versioned Python package (pip-installable); skills declare a minimum compatible version. Commands that return document sets support `--output paths|frontmatter|full` (default `frontmatter`) for progressive disclosure; `kb show` additionally offers `path` and single-`--field` projections; and every command supports machine-readable JSON (`--json`) for agent consumption.

The command surface is organized into five mutually exclusive groups — **Read** (retrieve documents), **Graph** (traverse relationships), **Write** (mutate the KB), **Integrity** (check and report), **Housekeeping** (maintain CLI-owned files) — and each capability lives in exactly one command. (CLI numbers are stable external identifiers; CLI-3 and CLI-5 are retired — see the decision below — and their numbers are never reused.)

| Command group | Requirements |
|---|---|
| **Read** | **CLI-1.** `kb filter` — select documents by frontmatter predicates (`--type`, `--status`, `--tag`, arbitrary `--where key=value`), returning paths or frontmatter without bodies. Filter has no derivation predicates — graph selection belongs exclusively to `kb links` (CLI-4). **CLI-2.** `kb search` — full-text search across bodies with per-hit context snippets. **CLI-3a.** `kb show <refs…>` — the single ref-retrieval command and the sole sanctioned read path for skills (so the CLI's access-control layer stays authoritative): body by default; `--output frontmatter|full|path` selects the projection, `--field F` extracts single frontmatter fields. Absorbs the formerly separate bulk-frontmatter extraction (retired CLI-3) and id↔path resolution (retired CLI-5); `kb resolve` may ship as a thin alias for `kb show --output path`. Resolution is computed by the per-invocation scan (no stored index; §6.5). Reading a document carrying `pending_upstream` emits the warning defined in §6.8. |
| **Graph** | **CLI-4.** `kb links <id|path>` — parents; `--reverse` — children; `--transitive` — full ancestry/impact set; `--depth` — derived depth-from-evidence; traverses `derived_from` by default and associative links (§6.9) on request (AL4). The sole owner of relationship queries. |
| **Write** | **CLI-8.** `kb ingest --class source|chat|feedback --from file|stdin|clipboard [SOURCE] [--dest <subdir>] [--about <ref>]` — **raw birth**: normalize incoming material into the matching `raw/` subclass with correct frontmatter and assigned ids (`SOURCE` is the input file, required with `--from file`; `--about` links a feedback record to the document it concerns); a `--dest` subdirectory that does not yet exist is created together with its `index.md`. Ingest validates fully before writing — a failed run leaves the KB untouched; filename collisions are auto-suffixed with the new id; non-text originals are stored byte-identical alongside a normalized Markdown stub, which is the citable form; the clipboard adapter shells out to platform tools. Adapter architecture is extensible (Slack, mail, ticketing later) without skill changes. Adapters normalize and file; they never synthesize. **CLI-13.** `kb create --type T --title TITLE --description DESC [--dest <subdir>] [--derived-from REF]… [--status draft|current] [--tag G]… [--supersedes REF] [--instructions TEXT] [--body-file FILE|-]` — **synthetic birth** (including birth-by-replacement): allocates the next `KB-` id, emits schema-valid synthetic frontmatter, files the document under `synthetic/` (creating `--dest` subdirectories with their `index.md`), sets `timestamp` and `last_human_touch` to the creation instant, refreshes the target `index.md`, and appends a `created` log entry. Requires ≥1 parent (DG1): `--derived-from` refs stored as canonical ids in argument order, and/or `--supersedes`, whose target — a live (`draft`/`current`) synthetic document — is implicitly added to `derived_from`; `--supersedes` atomically marks the prior document `superseded` (a documented atomicity coupling, not an overlap with revise — LS5 carves `superseded` out). Validates fully before writing — a failed run leaves the KB untouched. Agents never hand-write synthetic files; id allocation and frontmatter schema stay CLI-authoritative. Session-record parentage (DG5) is enforced by `kb validate`, not by this command. **CLI-14.** `kb revise REF [--add-parent REF]… [--link TYPE=REF]… [--body-file FILE|-] [--status draft|current|retired] [--clear-pending REF]…` — **synthetic mutation**: preserves the id; updates body/frontmatter; appends parents (consolidation, CS6) and associative links (§6.9); performs explicit human-directed status transitions (LS5; never `superseded`); sets or clears `pending_upstream` markers on deferral/propagation; advances `timestamp` (and `last_human_touch` on human confirmation); appends a `revised` log entry. Validates fully before writing. **CLI-7.** `kb mv` — **relocation**: move/rename preserving id, updating body links; changes a document's address, never its content. |
| **Integrity** | **CLI-6.** `kb validate [REF…] [--strict]` — the single authoritative **document-integrity** checker: universal `type` and type↔location agreement (FM0/NFR-2), per-class frontmatter schema (FM1–FM3), type/tag/link-type vocabularies (FM1b, §6.9), id format and uniqueness (canonical zero-padded form, merge collisions; §6.5), resolution of provenance and associative links, graph acyclicity (DG2), parentage (DG1/DG5), and supersedes/status coupling. Read-only and total (reports every finding in one pass). Every violation is a **finding** with a stable, family-prefixed code, a severity, an anchoring path, and a normative message — a namespace separate from `E_*` command errors, and the machine contract for CI and skills (NFR-9). `error` findings drive exit 1 (the CI gate); `warning` findings exit 0 unless `--strict` promotes them into the exit-1 signal. Vocabulary semantics: an empty `types` list means the type vocabulary is unconstrained (no finding), while an empty `tags` or link-type list means none are declared (every use flags). Scoping (`kb validate REF…`) filters which findings are *reported*, never which checks *run*; multi-document defects (duplicate ids, cycles) emit one finding per participant. Directory-invariant presence and index freshness are explicitly delegated to `kb index --check`; the CI gate composes `kb validate && kb index --check`. **CLI-15.** `kb report drift|impact|orphans` — read-only deterministic reports: **drift** — every `current` document whose `timestamp` is later than its `last_human_touch` (LS2); **impact** — for recently revised or superseded documents, the transitive downstream set with each member's update state (`pending_upstream`-marked = deliberate deferral; unmarked and older than the change = unexamined; connected only by associative links = notified, never obligated, AL3); **orphans** — documents nothing derives from and nothing links to. Exists because these properties are deterministically computable and NFR-3 therefore assigns them to the CLI; lint's judgment starts where these reports end. |
| **Housekeeping** | **CLI-9.** `kb index` — create any missing directory `index.md` and regenerate each one's listing body (one `- <child> — <description>` line per child, FM1a); `kb index --check` verifies directory-invariant presence and index freshness for CI. `index.md` is CLI-owned and read-only for humans/agents. **CLI-10.** `kb log` — append structured entries. Standalone appends are reserved for events no other command records (human answers, propagation decisions, session outcomes); every write command logs its own operation itself. **CLI-11.** `kb init` — scaffold repository structure (invoked by the `kb-init` skill). |

**Command-surface MECE — decision and rationale.** The surface is kept mutually exclusive and collectively exhaustive along two axes. *Reading* is one command per selection mode — predicate (`kb filter`), text (`kb search`), ref (`kb show`) — with output shape a projection option, never a separate command: the formerly separate `kb frontmatter` (CLI-3) and `kb resolve` (CLI-5) were retired into `kb show` projections because they were projections wearing command names, and `filter`'s former `--derived-from` selector was removed because graph selection already belonged to `kb links`. *Writing* is one command per operation class — raw birth (`ingest`), synthetic birth including replacement (`create`), synthetic mutation (`revise`), relocation (`mv`) — with exactly one documented coupling: `kb create --supersedes` flips the old document's status because the two changes must be atomic. `kb report` (CLI-15) closes the one exhaustiveness gap: drift, impact, and orphan detection are deterministic, so under NFR-3 they must be CLI-computed — without a report surface they would have silently fallen to model judgment inside `kb-lint`.

**CLI-12 (quality bar).** The CLI is developed with unit tests and CI, released independently of the skills, and treated as the single source of mechanical truth: any correctness property that *can* be checked deterministically *must* be checked by the CLI, not entrusted to model judgment. The CLI performs **no Git operations** — Git is the responsibility of the user and the skills.

### 7.2 Skill: `kb-init` — Scaffold and configure

*Trigger: user asks to create or adopt a knowledge base.*

- **INIT-1.** Runs `kb init` to scaffold `raw/` (with `sources/`, `chats/`, `feedback/`), `synthetic/`, `governance/`, root `index.md`, `log.md`, and root `kb-config.json` (the config file that also marks the KB root); verifies/installs the compatible CLI version. The `kb` CLI itself performs no Git operations; the skill (or the user) initializes the Git repository the KB lives in.
- **INIT-2.** Interviews the KB steward to draft the **KB charter** (`governance/charter.md`, id `GOVERNANCE-CHARTER`) — the KB-level purpose: who the KB serves, its consumers, and the architectural intent that shapes directory structure, vocabularies, and granularity choices (G9); rationale only — binding authoring rules go to `conventions.md` (§6.1) — and `kb-config.json` (at the KB root): type vocabulary (optional at start — types can be added as the project discovers them), tag vocabulary, associative link-type vocabulary (§6.9), optional per-type readiness checklists and templates, conventions, propagation-safety rules (CS3), id prefixes. Skills consult the charter whenever they propose structure.
- **INIT-3.** For adoption of an existing document collection: runs `kb validate`, reports gaps, and assists the human in bringing existing documents into conformance (assigning ids, adding frontmatter) — under human direction, per G2. The adoption session itself is archived as a session record, which becomes the adopted documents' chat parent so DG5 holds from day one.

### 7.3 Skill: `kb-ingest` — Evidence intake with clarification-first reconciliation

*Trigger: a human provides new source material (file, pasted text, clipboard; adapter-extensible).*

- **ING-1.** Invokes the appropriate `kb ingest` adapter to normalize the material into `raw/` (append-only; ids assigned; original binaries stored alongside the normalized Markdown, which is the citable form). The human declares which existing synthetic documents the new material concerns; the agent may suggest candidates from its overlap survey (ING-2), but attachment as a parent is always human-confirmed (CS6).
- **ING-2.** Surveys existing knowledge for overlap using CLI queries (frontmatter first, bodies only where needed) and identifies agreements, additions, and conflicts with current synthetic documents and prior raw evidence.
- **ING-3.** For each conflict: applies CS1–CS2 — presents the conflict to the human in-session (what the new source says, what the KB currently says, provenance of both, recommended resolution) and asks before acting. Clear-cut recency updates are proposed for one-tap confirmation; judgment calls are genuine questions. Only if the human defers does the item enter the uncertainty register (**ask first, register second**).
- **ING-4.** Executes the resulting consolidation (CS6, via `kb revise`), supersession, and propagation plan per CS3, updating affected downstream documents in dependency order, respecting per-document `instructions`, and pausing for human confirmation wherever a change involves judgment. Where the human defers downstream propagation, the affected children are marked `pending_upstream` so the deferral stays visible to lint and consumers.
- **ING-5.** Never creates new synthetic documents on its own initiative. If ingestion reveals that a *new* document is warranted (a new outcome, a new constraint document), it recommends this to the human, who may start a `kb-author` session.
- **ING-6.** Feedback intake: results produced by consumers of synthetic documents (a coding agent's errors executing a spec, failing tests, structured review comments) are ingested as `raw/feedback/` records with an `about:` link to the document concerned. Feedback is evidence like any other: it flows through the same conflict analysis (ING-2/ING-3), and when it warrants changing the document it concerns, the agent recommends a `kb-author` revision session rather than editing on its own initiative.
- **ING-7.** Closes by running `kb index`, `kb log`, and `kb validate`, reporting the session summary (new evidence, resolutions applied, questions parked, documents updated), and — when decisions were made in the session — archiving the session's chat as a session record, whose id is then appended (`kb revise --add-parent`) to the `derived_from` of every document consolidated or revised in the session, keeping DG5's revised-by clause mechanically true.

### 7.4 Skill: `kb-author` — Human-led co-authoring (create and revise)

*Trigger: a human asks to create a new document of any type, or to revise an existing one. This is the **only** path by which synthetic documents come into existence.*

- **AUT-1.** Establishes the document's intent with the human: type (from the vocabulary, or a new type the human names), purpose, intended consumers (human roles and/or agent types), and parents. Proposes candidate parents via CLI graph/search queries; the human confirms the `derived_from` set (multiple parents, any class, any depth — DG1).
- **AUT-2.** Assembles working context from the confirmed parents and their relevant ancestry (frontmatter-first, progressive disclosure) and surfaces to the human anything already in the KB that overlaps or conflicts with the intended document *before* drafting.
- **AUT-3.** Drafts *with* the human, not for them: the human directs structure, decisions, and level of detail at every step; the agent contributes synthesis of the parent context, candidate text, and consistency checking. The human can inject guidance, constraints, and detail at any point ("co-authoring", not "generate then edit").
- **AUT-4.** Applies clarification-first (CS2/CS4) during drafting: every ambiguity, gap, or conflict encountered is raised with the human in-session. Per the human's choice, each is (a) resolved now — the resolution is captured in the session record (AUT-8), making it citable evidence, (b) left open with the document kept in `draft`, or (c) parked in the uncertainty register with citations.
- **AUT-5.** Checks the draft against the type's readiness checklist (if defined) and reports the result; the human decides `draft` vs `current` (LS1).
- **AUT-6.** On completion: invokes **`kb create`** to allocate the id and write schema-valid frontmatter (including any optional `instructions` the human attached and the human's `draft`/`current` choice), which sets `last_human_touch` and `timestamp` to the creation instant; updates parents' coverage notes where applicable (DG3); the command refreshes index/log, and the skill runs `kb validate`. The agent never hand-writes the synthetic file — id allocation and frontmatter schema stay CLI-authoritative (§5.2, NFR-3).
- **AUT-7.** Revision mode: the same session pattern applied to an existing document at the human's request. In-place revision — consolidation, editorial change, adding parents or associative links — uses `kb revise` (CLI-14) and preserves the id. Genuine replacement or rescoping is human-confirmed **supersession** — a new `kb create --supersedes <old>` that atomically marks the prior document `superseded` (FM/CS rules).
- **AUT-8.** Session record: before closing, the agent summarizes the decisions made in the session and confirms the summary with the human, then archives the session to `raw/chats/` (via `kb ingest --class chat`) — the human-confirmed decision summary first, followed by the substantive exchange. Its id is supplied among the document's `--derived-from` at `kb create` (AUT-6), so session parentage (DG5) holds from creation; for a document created earlier in the session, the parent is added afterward via `kb revise` (CLI-14), and in revision mode the session record is likewise appended to the revised document's `derived_from` (DG5's revised-by clause). Verbatim completeness of the transcript is best-effort and platform-dependent; the decision summary is the mandatory, citable part.

### 7.5 Skill: `kb-lint` — Health, drift, and impact reporting

*Trigger: on demand, or scheduled; also invoked at the end of ingest/author sessions.*

- **LINT-1.** Runs `kb validate` for all mechanical checks (schema, graph acyclicity, link/id integrity, status legality) and reports failures with proposed mechanical fixes; applies only those fixes governance marks auto-safe (e.g., index regeneration).
- **LINT-2.** Semantic review (LLM-level): contradictions between `current` documents, coverage gaps (DG3), and `instructions` problems (IN4). Orphan and unexamined-change candidates come from `kb report orphans` and `kb report impact` (CLI-15) — lint assesses them for retirement or follow-up, which is judgment; it never re-derives the underlying facts (NFR-3).
- **LINT-3.** **Drift report** (LS2): `kb report drift` — all `current` documents modified since `last_human_touch` — grouped by the operation that changed them (from `log.md`): the standing answer to "what have the agents touched that no human has looked at?"
- **LINT-4.** **Impact view:** `kb report impact` — for any recently superseded or revised document, the transitive downstream set and its update state: `pending_upstream`-marked members are deliberate deferrals, unmarked-but-older members are unexamined changes, and documents connected only by associative links appear as *notified*, never obligated (AL3). Lint surfaces the propagation work that was deferred or missed.
- **LINT-5.** Never applies semantic fixes autonomously. Findings become a prioritized report (`governance/health.md`); where confident, the agent attaches candidate fixes for a human to accept in a `kb-author` revision session.

## 8. End-to-End Workflow (multi-role scenario)

1. **Setup.** The steward runs `kb-init`; defines an initial type vocabulary (`outcome`, `ux-flow`, `coding-spec`, `test-plan`) with a readiness checklist for `coding-spec` only; commits.
2. **Evidence.** The PM runs `kb-ingest` on the product vision document and two meeting-note exports. The agent finds no conflicts (empty KB), files three raw documents, and recommends — but does not create — an outcomes document.
3. **PM authoring.** The PM starts `kb-author` for an `outcome` document derived from all three raw sources. Two ambiguities surface; the PM resolves one and parks one in the uncertainty register; the document ships `current`, with the session archived to `raw/chats/` and linked as a parent (DG5).
4. **UX authoring.** The designer authors a `ux-flow` derived from the outcome document *and* a raw user-research note — cross-role, multi-parent, mixed-class derivation (DG1).
5. **Engineering authoring.** An engineer authors a `coding-spec` derived from the outcome, the ux-flow, and a raw compliance source. The readiness checklist flags a missing interface contract; the engineer supplies it in-session; `current`.
6. **QA authoring.** A QA engineer authors a `test-plan` derived from the coding-spec and the outcome. Consuming agents (a coding agent, a test-generation agent) now work from the same connected context.
7. **Feedback.** A coding agent implementing the spec hits a contradiction between the interface table and the actual upstream API; its error report is ingested as a `raw/feedback/` record about the spec (ING-6). The engineer opens a `kb-author` revision session; the feedback record and the revision's session record both join the spec's lineage.
8. **Change.** A new meeting note revises the outcome's scope. `kb-ingest` detects the conflict, asks the PM, and on confirmation consolidates the change into the outcome via `kb revise` (CS6) — the meeting note joins its `derived_from`, its id unchanged; the propagation plan lists the ux-flow, coding-spec, and test-plan. The agent updates the ux-flow and coding-spec — respecting the coding-spec's `instructions` line about retry semantics, which routes one change back to the engineer as a question — with each role's human confirming their document's judgment calls. The QA engineer is unavailable, so the test-plan update is deferred: it is marked `pending_upstream` (the outcome's id), stays `current`, and consuming agents reading it are warned until the QA engineer's next session clears the marker.
9. **Steward review.** Weekly `kb-lint`: drift report is empty (all agent changes were human-confirmed in-session); the deferred test-plan shows in the impact view as a deliberate deferral; one outdated orphan is flagged and retired.

Humans spent their time exactly where the product intends: supplying evidence, answering well-framed questions, and co-authoring the documents that direct the agents.

## 9. Non-Functional Requirements

- **NFR-1 — Substrate portability.** Plain UTF-8 Markdown + YAML in Git; fully readable and navigable by a human with a text editor. No database, server, or index required for correctness.
- **NFR-2 — OKF compatibility.** Bundles conform to OKF v0.1's required surface: **every markdown file carries a mandatory `type` frontmatter field** (FM0), and `type` is the authoritative classifier; `index.md`/`log.md` follow OKF conventions (`log.md` carries `type: log`); body links are relative paths. `kb validate` enforces universal `type` presence and `type`/location agreement. KBDD-specific fields (`id`, `instructions`, `last_human_touch`, …) ride as extension keys per FM2/§6.5.
- **NFR-3 — Deterministic mechanical truth.** Every property checkable without an LLM is checked by the CLI (CLI-12); governance rules about status, schema, and graph shape never depend on model judgment.
- **NFR-4 — Token economics.** Frontmatter-first CLI defaults, mandatory one-line `description`, index-before-body discipline in every skill.
- **NFR-5 — Auditability.** Any document's derivation chain, decision history, supersession lineage, and human-vs-agent modification record are reconstructible from the repository and its Git history alone. Suitable for regulated environments.
- **NFR-6 — Agent/vendor neutrality.** Skills follow the open Agent Skills format; the CLI is plain Python; nothing assumes a specific model or agent product.
- **NFR-7 — Concurrency.** Multi-human, multi-agent concurrency via ordinary Git branching; id-based references (§6.5) keep links merge-safe; `kb validate` in CI guards integrity at merge.
- **NFR-8 — Access control.** Governance may mark documents/directories restricted; skills must exclude restricted content from any context they assemble unless the session's human is entitled (entitlement rules in governance). Enforcement hooks live in the CLI query layer.
- **NFR-9 — Version compatibility.** Skills declare the minimum `kb` CLI version; the CLI maintains backward-compatible output schemas within a major version.

## 10. Success Metrics

| Metric | Definition | v1 target |
|---|---|---|
| **Cross-role derivation rate** | % of `current` synthetic documents with ≥1 parent authored by a different role (proxy for G1) | ≥ 50% after 90 days |
| **Fabrication defects** | Unsourced assertions found in `current` documents at audit (CS4 violations) | 0 (severity-1) |
| **Clarification conversion** | % of agent-raised questions resolved in-session (vs parked) — measures question quality and framing | ≥ 70% |
| **Drift confirmation lag** | Median time a `current` document sits agent-modified without human confirmation (LINT-3) | ≤ 7 days |
| **Propagation completeness** | % of revised or superseded documents whose transitive downstream set was updated or explicitly deferred (`pending_upstream`) within one lint cycle | 100% |
| **Consumer zero-clarification rate** | % of consuming-agent tasks (e.g., coding from a spec) completed without KB-related clarification | ≥ 70% (Phase 3 pilot) |
| **Traceability coverage** | % of `current` documents whose chains terminate at evidence/decisions (`kb validate`) | 100% (hard gate) |

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Graph spaghetti** without fixed layers: inconsistent granularity, tangled derivations | KB becomes hard to navigate and reason about | Type vocabulary + readiness checklists as soft structure; DG3 coverage discipline; `kb links --depth` and `kb report orphans`; steward curation |
| **Acceptance-at-creation complacency**: `current` read as "reviewed" when the human co-authored hastily | Quality theater | Drift report + `last_human_touch` visibility; readiness checklists at authoring time; audit metrics |
| **Instruction-field misuse**: directives that conflict with governance or attempt out-of-scope authority | Inconsistent or unsafe maintenance | IN1–IN4: precedence, scope limits, surface-don't-choose, lint coverage |
| **Question fatigue**: clarification-first degenerating into interrogation | Humans disengage; agents get pressured back into assuming | CS5 framing standards; batch questions per session; clarification-conversion metric as quality signal |
| **Propagation fatigue**: every upstream change fanning out into many confirmations | Change becomes expensive; updates get deferred | Governance-defined auto-safe change classes (CS3); dependency-ordered batching; `pending_upstream` markers and the impact view (LINT-4) keep deferrals visible instead of lost; associative links notify without obligating (AL3) |
| **CLI/skill version skew** | Skills invoke commands that behave differently | NFR-9 version declaration; CLI output-schema stability; validate-on-session-start |
| **Provenance-washing**: synthetic citing synthetic until claims float free of evidence | Audit chain becomes decorative | DG2 termination rule enforced by `kb validate`; session records (§6.1) make human answers citable |

## 12. Release Phasing

- **Phase 1 — CLI core + scaffold.** `kb` CLI (read, graph, integrity, housekeeping groups) with tests and CI; `kb-init`. Exit: a KB can be scaffolded and an existing document set validated and adopted.
- **Phase 2 — Evidence pipeline.** `kb-ingest` (file/stdin/clipboard adapters) + `kb-lint`. Exit: raw material flows in with clarification-first conflict resolution, consolidation (`kb revise`), supersession, and propagation; drift and impact reporting live.
- **Phase 3 — Co-authoring.** `kb-author` (create + revise), readiness checklists, session-record capture. Exit: the §8 multi-role scenario executes end-to-end with a real project team; metrics instrumented; a consuming agent completes a task from KB context.
- **Phase 4 (post-v1) — Extensions.** Additional ingest adapters (Slack, mail, ticketing); optional context-package tooling if manual authoring of packages proves repetitive; retrieval-index accelerators behind the CLI; reconciliation of consuming-agent outcomes back into evidence; multi-KB references (OQ4).

## 13. Open Questions

1. **OQ1 — Auto-safe propagation classes.** Which change classes should governance ship as auto-safe defaults (CS3) vs always-confirm? Proposal: start with "cited-figure/date refresh" only; expand from Phase 2 field data.
2. **OQ2 — Draft visibility to consumers.** Should consuming agents be permitted to read `draft` documents with a warning, or be hard-blocked? Proposal: hard-block by default, governance-relaxable per type. (Distinct and already decided (§6.8): a `current` document carrying `pending_upstream` is served with a **warning** naming the unpropagated parent revision, never blocked — it is complete, merely possibly outdated.)
3. **OQ3 — Uncertainty register shape.** Single register document vs per-document open-question sections with a CLI-aggregated view. Proposal: single register with backlinks (simpler propagation of answers); revisit if it becomes a merge hotspot.
4. **OQ4 — Cross-KB references.** Reserve a URI scheme now for citing documents in other bundles (e.g., an org-wide compliance KB)? Recommendation: reserve the syntax in v1 (`kb://<bundle>/<id>`), implement post-v1.
5. **OQ5 — Session-record fidelity.** Full verbatim transcripts vs decision summary plus key excerpts: affects repository size, privacy exposure, and citation precision. Proposal: summary mandatory, transcript best-effort (AUT-8), with a governance switch for verbatim retention; revisit with Phase 3 field data.
6. **OQ6 — Purpose-document marking.** Should purpose documents be mechanically distinguishable from building blocks (e.g., an optional `consumers:` frontmatter field naming the intended agent or human consumers), so lint can check purpose-document self-containment and `kb filter` can list an agent's entry points? Proposal: start with type conventions only (an `execution-plan` type is self-evidently a purpose document); add a `consumers` field if Phase 3 shows the distinction needs to be queryable.

## Appendix A — Repository Layout

```
kb/                               # every directory has an index.md (DocClass INDEX); no .gitkeep files
├── kb-config.json                # config + KB root marker: type/tag/link-type vocabularies, readiness checklists, propagation rules, id prefixes, schema version
├── index.md                      # root navigation (CLI-maintained, read-only for humans/agents)
├── log.md                        # KB-wide history (CLI-appended)
├── governance/
│   ├── index.md
│   ├── templates/                # optional per-type document templates
│   │   └── index.md
│   ├── charter.md                # KB purpose: who it serves, consumers, architectural intent (id GOVERNANCE-CHARTER)
│   ├── conventions.md            # binding authoring/maintenance rules (id GOVERNANCE-CONVENTIONS)
│   ├── kb-config.md              # human-readable field reference for kb-config.json (id GOVERNANCE-KB-CONFIG)
│   └── health.md                 # latest lint report
├── raw/
│   ├── index.md
│   ├── sources/                  # normalized external evidence (immutable)
│   │   └── index.md
│   ├── chats/                    # session records from kb-author / kb-ingest (immutable)
│   │   └── index.md
│   └── feedback/                 # consumer feedback about synthetic documents (immutable)
│       └── index.md
└── synthetic/                    # human-created, agent-maintained; organization is
    ├── index.md                  # project-chosen (by role, epic, …) — structure is
    └── …                         # the derivation graph, not the directory tree
```

## Appendix B — Example Readiness Checklist (type: `coding-spec`)

Illustrative only; a project defines its own per-type checklists in governance.

| # | Criterion |
|---|---|
| 1 | One unambiguous objective with observable done-behavior |
| 2 | Verifiable acceptance criteria (notation per project convention) |
| 3 | Every touched interface/schema specified inline or by link |
| 4 | Applicable constraints (security, compliance, non-functional) linked to their sources |
| 5 | Dependencies linked, with status visible |
| 6 | Explicit out-of-scope statements for nearest ambiguities |
| 7 | Self-contained: the document plus its ancestry suffices; no other KB content or human clarification needed |
| 8 | Zero unresolved open questions attached to this document |

## Appendix C — Glossary (normative language)

This glossary is the product's **ubiquitous language** and is normative: use the canonical term everywhere — documents, specs, code, and conversation. The *Avoid* column lists near-synonyms that must not be used for the concept, because each blurs a distinction the model depends on.

| Term | Definition | Avoid |
|---|---|---|
| **Raw document** | Immutable evidence; the KB's ground truth (sources, session records, feedback). Never edited — corrections arrive as new raw documents | source file, input, upload |
| **Session record** | Archived chat of a human-led session, headed by a human-confirmed decision summary (`raw/chats/`); the citable form of a human decision | decision record, transcript, chat log |
| **Feedback record** | Evidence from a consumer of a synthetic document (errors, test failures, review comments), linked via `about` (`raw/feedback/`) | bug report, review |
| **Synthetic document** | Human-created, agent-maintained document derived from parents in the graph | refined document, output, artifact |
| **Governance document** | Steward-controlled document carrying the KB's intent, rules, and reference material (charter, conventions, config reference, health) | — |
| **Purpose document** | A leaf synthetic document distilled from a small sub-network, carrying complete and only the context needed for one specific outcome; the clean-context unit handed to a consuming agent | context dump, spec bundle |
| **Building block** | An intermediate synthetic document with no consumer-facing purpose of its own — a reusable node from which purpose documents are distilled | draft, partial doc |
| **Derivation graph** | The acyclic multi-parent structure formed by `derived_from` links; replaces fixed layers | hierarchy, layer structure, tree |
| **Associative link** | A typed, non-provenance relationship (`references`, `contradicts`, `constrains`, …) in synthetic frontmatter; navigational, never parentage (§6.9) | backlink |
| **Supersession** | Replacement or rescoping of a document by a new one, preserving lineage via `supersedes` and Git history; reserved for genuine replacement | overwrite, update-in-place, delete |
| **Revision** | An in-place update to a synthetic document preserving its id (`kb revise`) — the write path for consolidation and editorial change, performed in a human-led session | version, new edition |
| **Consolidation** | Folding newly ingested evidence into an existing synthetic document it concerns, by revision (CS6) | auto-update, merge |
| **Propagation** | Human-confirmed updating of the downstream set after a supersession or revision | cascade, sync |
| **Co-authoring** | The human-initiated, human-led session in which a synthetic document is created or revised with an agent; the only way synthetic content comes into existence | compile, generate, ETL, pipeline |
| **KB purpose** | The high-level mission a KB serves, driving its structural decisions: directory architecture, type vocabulary, granularity | theme, topic |
| **KB charter** | The governance document stating the KB's purpose: who it serves, its consumers, and the architectural rationale behind structure and vocabularies — intent, not rules | mission statement, README |
| **Conventions** | The governance document of binding authoring/maintenance rules; the top of IN1's precedence chain (rationale → charter; rules → conventions; settings → config) | style guide, guidelines |
| **Readiness checklist** | Governance-defined, per-type completeness criteria checked during authoring | definition of done, completeness contract |
| **KB steward** | The human who owns governance: charter, vocabularies, conventions, readiness checklists, tool versions | admin |
| **Consuming agent** | An executor (coding agent, test-generation agent, …) that reads current documents and their ancestry as working context; reads, never maintains | — |
| **Stale** | The condition of a `current` document whose parent's revision awaits propagation, recorded by the `pending_upstream` marker — never by a status change (§6.8) | outdated status, expired |
| **Drift report** | Lint listing of `current` documents changed since their `last_human_touch` | — |
| **Uncertainty register** | The document holding questions a human explicitly deferred (ask-first, register-second) | open questions list, backlog |
| **`kb` CLI** | The deterministic, independently versioned toolset all skills share | — |
