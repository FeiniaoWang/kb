# Product Requirements Document: Shared Project Knowledge Base — Skills & CLI

| Field | Value |
|---|---|
| **Status** | Draft v0.3 (supersedes v0.2) |
| **Owner** | Pengfei (Director of AI Engineering) |
| **Last updated** | 2026-07-14 |
| **Product name** | KB Skill Suite (working name; skills prefixed `kb-`, CLI named `kb`) |
| **Delivery form** | A set of [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) + an independently versioned `kb` CLI toolset |

**Changes from v0.1:** Human-driven authoring replaces autonomous generation; document creation is always initiated and steered by a human, agents maintain. Fixed refinement layers (L1–L4) replaced by an emergent derivation graph. Coding-spec focus generalized to a multi-role shared knowledge base (PM, UX, engineering, infra, QA). `kb-review` and `kb-pack` removed from v1. Deterministic operations moved into a shared `kb` CLI. New: optional per-document maintenance `instructions` frontmatter; clarification-first conflict handling; supersession-with-propagation on ingest.

**Changes from v0.2:** Session records (`raw/chats/`) — the archived history of human-led sessions — replace `raw/decisions/` as the captured form of human decisions, and every synthetic document must carry at least one session record among its parents (DG5). Consumer feedback (e.g., a coding agent's errors executing a spec) added as a raw document subclass (`raw/feedback/`). DG3 coverage discipline scoped to explicit decomposition only; extraction/reference documents make no claims about children. Optional `tags` frontmatter with a governance-declared vocabulary. `description` extended to two sentences and copied into `index.md` for progressive disclosure.

**Consistency updates (2026-07-14), from the CLI design pass ([docs/superpowers/specs/2026-07-13-kb-cli-design.md](superpowers/specs/2026-07-13-kb-cli-design.md), [docs/specs/commands/](specs/commands/)):** Project config is `kb-config.json` — strict JSON at the **KB root**, which also serves as the root-discovery marker (no separate `.kb` file); it moved out of `governance/`. Document ids zero-pad to **6 digits** (`KB-000042`). Added **`kb show`** (CLI-3a) as the sole sanctioned document-read path for skills, and `kb frontmatter --field` for single-field retrieval. Id↔path resolution is by per-invocation scan, with no stored index.

---

## 1. Executive Summary

This product is a **shared project knowledge base** in which every human role — product manager, UX designer, software engineer, infrastructure engineer, QA engineer — and every AI agent works in the **same context**. The knowledge base holds two classes of documents: **raw sources** (immutable evidence: vision documents, meeting notes, chat histories, research, compliance rules) and **synthetic documents** (human-authored, agent-maintained refinements: outcomes, design documents, specifications, test plans, runbooks, context packages — any document type a project needs). Synthetic documents form a derivation graph that progressively breaks large intent into granular, self-contained working documents; a coding specification is one possible leaf, not the privileged one.

The division of labor is the product's central idea: **humans drive creation, agents perform maintenance.** Software engineers and their peers spend their time co-authoring the documents that direct AI agents, rather than producing the downstream artifacts directly. A document is born in a human-led session and is considered accepted at creation; from then on, agents keep it consistent with new evidence — propagating updates when raw information changes, superseding stale content with newer, and **asking a human whenever anything is unclear or conflicting rather than assuming**.

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
- **G5 — Freshness with propagation.** Newer information supersedes older by default; superseding a document triggers identification and human-confirmed update of everything derived from it.
- **G6 — Any document type, any granularity.** The type vocabulary is project-defined. Coding specs, UX flows, test plans, ADRs, infra runbooks, and context packages are all just types with optional per-type readiness criteria.
- **G7 — Plain-text substrate, deterministic tooling.** Markdown + YAML in Git; all mechanical operations (search, filter, validate, graph queries) provided by a tested, independently versioned CLI that skills share.
- **G8 — Token-economical operation.** Progressive disclosure by construction: agents survey via indexes and frontmatter (CLI-served) before reading bodies.

### 3.2 Non-Goals

- **NG1.** Orchestrating downstream execution agents (coding harnesses, CI/CD, design tools). The KB directs them; it does not run them.
- **NG2.** Prescribing a methodology, document taxonomy, or fixed layer structure. Structure is emergent (derivation graph) and vocabulary is project configuration.
- **NG3.** Autonomous document generation pipelines. Explicitly rejected, not merely deferred.
- **NG4.** An approval/review workflow product. Acceptance happens at creation, with the human present; there is no separate review queue in v1.
- **NG5.** Purpose-specific context packaging (`kb-pack`) in v1. A context package is an ordinary document type a human can author when needed.
- **NG6.** Retrieval infrastructure (embeddings, vector stores). The CLI's text/frontmatter search is the baseline; external indexes may be added later as accelerators, never as sources of truth.
- **NG7.** Multi-repository knowledge federation in v1 (reserved; see OQ4).

## 4. Users and Personas

**P1 — Document authors (humans, all roles).** PM, UX designer, software engineer, infrastructure engineer, QA engineer. Each authors the document types natural to their role, derived from shared upstream documents and evidence. Their working mode shifts from producing downstream artifacts to co-authoring and curating directing documents.

**P2 — Maintenance agent (AI).** An LLM agent with this skill suite loaded, operating inside a human's session: ingesting sources, co-drafting under direction, propagating updates, asking questions.

**P3 — Consuming agents (AI).** Coding agents, test-generation agents, design-to-code agents, document-generation agents — any executor that reads current documents (and their parents) as its working context.

**P4 — KB steward (human).** Configures governance (type vocabulary, conventions, readiness checklists), monitors lint reports, owns the CLI/skill versions in use. Typically the AI engineering lead.

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
                     │  governance/  (types, conventions, readiness)      │
                     │  kb-config.json (config + root marker)             │
                     │  index.md, log.md                                  │
                     └────────────────────────────────────────────────────┘
                                    ▲                      ▲
                          kb-* Agent Skills          kb CLI (deterministic:
                          (judgment: ingest,         search, filter, graph,
                          co-author, maintain)       validate, frontmatter)
```

Humans of every role and their agents converge on one repository. Creation flows top-down through human-led sessions; evidence flows in through ingestion; freshness flows downstream through supersession and propagation; questions flow back to humans whenever judgment is required.

### 5.2 Architecture: Skills + CLI

The capability is deliberately split into two independently evolving components:

| Component | Nature | Contains | Evolves by |
|---|---|---|---|
| **`kb` CLI** | Deterministic, tested Python toolset | Search, filter, frontmatter extraction, document read (`kb show`), graph queries, validation, ingest adapters, index/log maintenance | Its own release cycle, unit-tested, semver |
| **`kb-*` skills** | Instructions + judgment (SKILL.md + templates) | When and how to ingest, co-author, resolve conflicts, ask humans, maintain | Prompt-level iteration, thin and stable |

Rationale: mechanical correctness (does this frontmatter parse? which documents derive from X?) must not depend on model judgment; shared tooling avoids per-skill reimplementation; adapters (file, clipboard, Slack, …) can be added to the CLI without touching any skill; and CLI output modes designed for progressive disclosure (paths-only, frontmatter-only) directly serve token economics. Skills MUST call the CLI for every operation the CLI provides and MUST NOT reimplement it.

## 6. Information Model

### 6.1 Document Classes

| Class | Location | Mutability | Created by | Maintained by |
|---|---|---|---|---|
| **Raw** | `raw/` | Immutable, append-only | Ingestion, session records, feedback intake (all human-initiated) | Nobody (corrections arrive as new raw docs) |
| **Synthetic** | `synthetic/` | Living | Humans (co-authoring sessions) | Agents, under §6.7 rules |
| **Governance** | `governance/` | Human-controlled | KB steward | Steward, with agent assistance |
| **Operational** | `index.md`, `log.md` | Regenerated / appended | CLI | CLI |

Raw documents come in three subclasses. **Sources** (`raw/sources/`) are ingested external material. **Session records** (`raw/chats/`) are the archived history of every human-led `kb-author` or `kb-ingest` session, headed by an agent-written, human-confirmed decision summary; they are the captured form of human decisions — "the PM decided on 2026-07-08" cites the session record — and replace the earlier separate decisions class. **Feedback** (`raw/feedback/`) is evidence produced by consumers of synthetic documents — a coding agent's errors while executing a spec, failing tests, structured review comments — filed with an `about:` reference to the document it concerns.

### 6.2 Structure: an emergent derivation graph, not fixed layers

There is **no predefined layer taxonomy**. Structure emerges from `derived_from` links, subject to four rules:

- **DG1.** Every synthetic document declares one or more parents in `derived_from`. Parents may be raw documents, decisions, governance documents, or other synthetic documents — from any depth, in any combination. (A test plan citing a coding spec, an outcome document, *and* a raw compliance PDF is normal.)
- **DG2.** The graph is acyclic, and every chain terminates at raw or governance documents.
- **DG3.** Granularity is a human choice made during authoring. Coverage discipline applies only to **decomposition**: where a document explicitly commits scope to be fulfilled by child documents, uncovered committed scope is made explicit (in the parent or the uncertainty register), never silently dropped. Documents that are extractions or reference material (concepts, facts, constraints distilled from raw sources) make no claims about their children — future documents may derive from them freely, and they owe those children no coverage statement.
- **DG4.** "Depth" is a derived property (distance from evidence), computable by the CLI for reporting — never a field an author must manage.
- **DG5.** Every synthetic document has at least one session record (`raw/chats/`) among its `derived_from` parents — the record of the human-led session that created it, joined over time by the sessions that revised it. Human involvement in every document's existence is thereby a mechanically checkable property (`kb validate`), not a policy assertion.

### 6.3 Document Types and Readiness

`kb-config.json` (at the KB root; also the root marker) defines the project's **type vocabulary** — an open, project-owned list (illustrative: `domain-note`, `outcome`, `ux-flow`, `capability`, `coding-spec`, `test-plan`, `adr`, `runbook`, `context-package`). For any type, governance MAY define a **readiness checklist**: the conditions under which a document of that type is complete enough for its consumers. During co-authoring, the agent checks the draft against the applicable checklist and reports gaps to the human; unresolved gaps are grounds for the human to leave the document in `draft`.

Readiness checklists generalize v0.1's coding-only "Completeness Contract": a `coding-spec` checklist (objective, verifiable acceptance criteria, interfaces, constraints, dependencies, scope boundary, self-containment, zero open questions) ships as an *example profile* in Appendix B; a `test-plan` or `ux-flow` type would define different criteria. The suite mandates the mechanism, not any particular checklist.

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
instructions: |                  # OPTIONAL maintenance directives (§6.6)
  Keep the interface table consistent with KB-000012.
  Do not change retry semantics without asking the author.
timestamp: 2026-07-10T14:30:00Z        # last modification (any actor)
last_human_touch: 2026-07-10T14:30:00Z # last human-confirmed revision (§6.8)
---
```

- **FM1.** `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch` are mandatory for synthetic documents. Raw documents carry a reduced schema (`id`, `type: raw-source | chat | feedback`, `ingested_at`, `origin`, plus `about` for feedback records).
- **FM1a.** `description` is at most two sentences and is copied verbatim into the owning directory's `index.md` by `kb index`, so survey-level reading can proceed on indexes alone.
- **FM1b.** `tags` is an optional list; when present, every value must appear in the tag vocabulary declared in `kb-config.json` (`kb validate` flags undeclared tags for the steward to add to the vocabulary or correct).
- **FM2.** Unknown additional keys are permitted and preserved (forward compatibility; OKF extension-key behavior).
- **FM3.** Mechanical validity of all of the above is checkable by `kb validate` without an LLM.

### 6.5 Identity: `id` field and OKF path-IDs — decision and rationale

OKF defines a concept's ID as its bundle-relative file path. This PRD **keeps a stable frontmatter `id` in addition**, and uses the two for different jobs: **the path is the address; the `id` is the identity.**

Why a path alone is insufficient here:

1. **Reorganization is expected.** A multi-role KB will be restructured as the project grows (directories split by role, by epic, by quarter). Path-IDs turn every reorganization into a link-breaking event across the whole graph; stable `id`s make moves free (the CLI re-resolves).
2. **Supersession needs identity across files.** `supersedes: KB-000031` must keep meaning after the old file is archived or the new one is renamed. A path-based chain rots.
3. **External references must not rot.** Commit messages, code comments, tickets, and audit findings will cite documents. `KB-000042` survives ten years of refactoring; `synthetic/specs/webhook.md` will not.
4. **Merge safety.** Concurrent branches renaming or moving files merge cleanly when links are id-based.

Reconciliation with OKF: `derived_from`/`supersedes` use `id`s (the machine layer); links *within document bodies* remain OKF-style relative paths (the human layer); `id` rides as an OKF extension key, so bundles stay OKF-conformant. The CLI resolves id↔path by scanning frontmatter on each invocation (no stored index — see the CLI design), and `kb mv` updates body links on moves. Net cost of keeping `id`: one frontmatter line and a per-invocation scan — cheap insurance for properties 1–4.

### 6.6 Per-Document Maintenance `instructions` — decision and rationale

**Adopted, as an optional frontmatter field.** A document may carry natural-language directives telling maintenance agents how to keep it: what to update on what triggers, what to preserve, what requires asking a specific human, style and length constraints. This makes each document a self-describing maintenance contract — the instruction lives exactly where it applies, travels with the document, and is versioned with it. It is, in effect, a per-document micro-skill.

Guardrails (mandatory):

- **IN1 — Precedence.** Governance conventions > document `instructions` > session-level requests. An instruction cannot relax a governance rule (e.g., cannot exempt a document from provenance or validation).
- **IN2 — Scope of authority.** Instructions may direct *how this document is maintained*. They may not direct agents to create documents, modify other documents, contact external systems, or alter statuses — those remain governed by the skills' own rules. Agents treat out-of-scope instructions as inert and flag them in lint.
- **IN3 — Conflict handling.** If an instruction conflicts with governance, with another applicable instruction, or with a human's in-session request, the agent surfaces the conflict to the human rather than choosing silently (per G3).
- **IN4 — Lint coverage.** `kb-lint` reports unparseable, out-of-scope, or mutually contradictory instructions.

### 6.7 Conflict, Supersession, and Propagation Semantics

- **CS1 — Latest wins, by default.** When newly ingested information conflicts with existing knowledge, the newer information takes precedence. The prior content is superseded, never silently edited away: raw stays immutable; affected synthetic content is updated with the superseded version preserved in Git history and, where document-level, via `supersedes` chains.
- **CS2 — Ask before deciding.** Where "which is newer/authoritative" or "what should change downstream" requires judgment — ambiguous scope, partial contradiction, doubtful source authority — the agent asks the human **first**. Only if the human defers ("park it") does the item enter the uncertainty register as an open question with its citations.
- **CS3 — Propagation.** Superseding any document (raw or synthetic) triggers computation of the affected downstream set (`kb links --reverse --transitive`). The agent presents the propagation plan (which documents, what kind of change each needs), then applies updates — respecting each document's `instructions` — with human confirmation for every change that involves judgment, and mechanical application (with logging) for changes governance marks as safe (e.g., updating a cited figure).
- **CS4 — No fabrication.** At no point may an agent fill a gap with invented content. Missing information is a question (CS2) or an explicit gap notation — never a plausible guess. Fabrication is the suite's severity-1 defect class.
- **CS5 — Skill-encoded permission to ask.** Every skill's SKILL.md must state, prominently, that asking the human is a *preferred, first-class action* — including concrete question-framing guidance (what is known, what is missing/conflicting, why it matters, what options exist). This counters agents' default bias toward self-sufficient completion.

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
- **LS4.** Superseded and retired documents are preserved with updated status; nothing is deleted. `log.md` records every creation, ingestion, supersession, propagation, and human answer, with date and actor.

## 7. Component Requirements

### 7.1 The `kb` CLI (deterministic toolset)

Independently versioned Python package (pip-installable); skills declare a minimum compatible version. Commands that return document sets support `--output paths|frontmatter|full` (default `frontmatter`) for progressive disclosure; `kb show` reads document content (body by default); and every command supports machine-readable JSON (`--json`) for agent consumption.

| Command group | Requirements |
|---|---|
| **Query** | **CLI-1.** `kb filter` — select documents by any frontmatter field (`--type`, `--status`, `--tag`, `--derived-from`, arbitrary `--where key=value`), returning paths or frontmatter without bodies. **CLI-2.** `kb search` — full-text search across bodies with per-hit context snippets. **CLI-3.** `kb frontmatter <refs…>` — bulk frontmatter extraction (`--field` retrieves specific fields). **CLI-3a.** `kb show <refs…>` — read document content (body by default; the sole sanctioned read path for skills, so the CLI's access-control layer stays authoritative). |
| **Graph** | **CLI-4.** `kb links <id|path>` — parents; `--reverse` — children; `--transitive` — full ancestry/impact set; `--depth` — derived depth-from-evidence. **CLI-5.** `kb resolve <id>` / reverse — id↔path resolution computed by the per-invocation scan (no stored index; §6.5). |
| **Integrity** | **CLI-6.** `kb validate` — frontmatter schema (FM1–FM3, including tag-vocabulary conformance), status-transition legality, acyclicity (DG2), session-record parentage (DG5), link/id integrity, uniqueness of ids; exit codes suitable for CI. **CLI-7.** `kb mv` — move/rename preserving id, updating body links. |
| **Ingest adapters** | **CLI-8.** `kb ingest --from file|stdin|clipboard --class source|chat|feedback [--about <id>] <target>` — normalize incoming material into the matching `raw/` subclass with correct frontmatter and assigned ids (`--about` links a feedback record to the document it concerns). Adapter architecture is extensible (Slack, mail, ticketing later) without skill changes. Adapters normalize and file; they never synthesize. |
| **Housekeeping** | **CLI-9.** `kb index` — regenerate `index.md` files from frontmatter, copying each document's `description` (≤2 sentences, FM1a) so an index alone supports survey-level reading. **CLI-10.** `kb log` — append structured entries. **CLI-11.** `kb init` — scaffold repository structure (invoked by the `kb-init` skill). |

**CLI-12 (quality bar).** The CLI is developed with unit tests and CI, released independently of the skills, and treated as the single source of mechanical truth: any correctness property that *can* be checked deterministically *must* be checked by the CLI, not entrusted to model judgment.

### 7.2 Skill: `kb-init` — Scaffold and configure

*Trigger: user asks to create or adopt a knowledge base.*

- **INIT-1.** Runs `kb init` to scaffold `raw/` (with `sources/`, `chats/`, `feedback/`), `synthetic/`, `governance/`, root `index.md`, `log.md`, and root `kb-config.json` (the config file that also marks the KB root), in a new or existing Git repository; verifies/installs the compatible CLI version.
- **INIT-2.** Interviews the KB steward to draft `kb-config.json` (at the KB root): type vocabulary (optional at start — types can be added as the project discovers them), tag vocabulary, optional per-type readiness checklists and templates, conventions, propagation-safety rules (CS3), id prefixes.
- **INIT-3.** For adoption of an existing document collection: runs `kb validate`, reports gaps, and assists the human in bringing existing documents into conformance (assigning ids, adding frontmatter) — under human direction, per G2. The adoption session itself is archived as a session record, which becomes the adopted documents' chat parent so DG5 holds from day one.

### 7.3 Skill: `kb-ingest` — Evidence intake with clarification-first reconciliation

*Trigger: a human provides new source material (file, pasted text, clipboard; adapter-extensible).*

- **ING-1.** Invokes the appropriate `kb ingest` adapter to normalize the material into `raw/` (append-only; ids assigned; original binaries may be stored alongside the normalized Markdown, which is the citable form).
- **ING-2.** Surveys existing knowledge for overlap using CLI queries (frontmatter first, bodies only where needed) and identifies agreements, additions, and conflicts with current synthetic documents and prior raw evidence.
- **ING-3.** For each conflict: applies CS1–CS2 — presents the conflict to the human in-session (what the new source says, what the KB currently says, provenance of both, recommended resolution) and asks before acting. Clear-cut recency updates are proposed for one-tap confirmation; judgment calls are genuine questions. Only if the human defers does the item enter the uncertainty register (revised from v0.1: **ask first, register second**).
- **ING-4.** Executes the resulting supersession and propagation plan per CS3, updating affected downstream documents in dependency order, respecting per-document `instructions`, and pausing for human confirmation wherever a change involves judgment.
- **ING-5.** Never creates new synthetic documents on its own initiative. If ingestion reveals that a *new* document is warranted (a new outcome, a new constraint document), it recommends this to the human, who may start a `kb-author` session.
- **ING-6.** Feedback intake: results produced by consumers of synthetic documents (a coding agent's errors executing a spec, failing tests, structured review comments) are ingested as `raw/feedback/` records with an `about:` link to the document concerned. Feedback is evidence like any other: it flows through the same conflict analysis (ING-2/ING-3), and when it warrants changing the document it concerns, the agent recommends a `kb-author` revision session rather than editing on its own initiative.
- **ING-7.** Closes by running `kb index`, `kb log`, and `kb validate`, reporting the session summary (new evidence, resolutions applied, questions parked, documents updated), and — when decisions were made in the session — archiving the session's chat as a session record.

### 7.4 Skill: `kb-author` — Human-led co-authoring (create and revise)

*Trigger: a human asks to create a new document of any type, or to revise an existing one. This is the **only** path by which synthetic documents come into existence.*

- **AUT-1.** Establishes the document's intent with the human: type (from the vocabulary, or a new type the human names), purpose, intended consumers (human roles and/or agent types), and parents. Proposes candidate parents via CLI graph/search queries; the human confirms the `derived_from` set (multiple parents, any class, any depth — DG1).
- **AUT-2.** Assembles working context from the confirmed parents and their relevant ancestry (frontmatter-first, progressive disclosure) and surfaces to the human anything already in the KB that overlaps or conflicts with the intended document *before* drafting.
- **AUT-3.** Drafts *with* the human, not for them: the human directs structure, decisions, and level of detail at every step; the agent contributes synthesis of the parent context, candidate text, and consistency checking. The human can inject guidance, constraints, and detail at any point ("co-authoring", not "generate then edit").
- **AUT-4.** Applies clarification-first (CS2/CS4) during drafting: every ambiguity, gap, or conflict encountered is raised with the human in-session. Per the human's choice, each is (a) resolved now — the resolution is captured in the session record (AUT-8), making it citable evidence, (b) left open with the document kept in `draft`, or (c) parked in the uncertainty register with citations.
- **AUT-5.** Checks the draft against the type's readiness checklist (if defined) and reports the result; the human decides `draft` vs `current` (LS1).
- **AUT-6.** On completion: writes frontmatter (including optional `instructions` the human wishes to attach), sets `last_human_touch`, updates parents' coverage notes where applicable (DG3), and runs index/log/validate.
- **AUT-7.** Revision mode: the same session pattern applied to an existing document at the human's request, including human-confirmed supersession (FM/CS rules) when the change is semantic rather than editorial.
- **AUT-8.** Session record: before closing, the agent summarizes the decisions made in the session and confirms the summary with the human, then archives the session to `raw/chats/` — the human-confirmed decision summary first, followed by the substantive exchange. The record's id is added to the created or revised document's `derived_from` (DG5). Verbatim completeness of the transcript is best-effort and platform-dependent; the decision summary is the mandatory, citable part.

### 7.5 Skill: `kb-lint` — Health, drift, and impact reporting

*Trigger: on demand, or scheduled; also invoked at the end of ingest/author sessions.*

- **LINT-1.** Runs `kb validate` for all mechanical checks (schema, graph acyclicity, link/id integrity, status legality) and reports failures with proposed mechanical fixes; applies only those fixes governance marks auto-safe (e.g., index regeneration).
- **LINT-2.** Semantic review (LLM-level): contradictions between `current` documents, coverage gaps (DG3), orphans (no consumers and no children), stale documents (an ancestor's `timestamp` newer than the document's), and `instructions` problems (IN4).
- **LINT-3.** **Drift report** (LS2): all `current` documents modified since `last_human_touch`, grouped by the operation that changed them — the standing answer to "what have the agents touched that no human has looked at?"
- **LINT-4.** **Impact view:** for any recently superseded or changed document, the transitive downstream set and its update status — surfacing propagation work that was deferred or missed.
- **LINT-5.** Never applies semantic fixes autonomously. Findings become a prioritized report (`governance/health.md`); where confident, the agent attaches candidate fixes for a human to accept in a `kb-author` revision session.

## 8. End-to-End Workflow (multi-role scenario)

1. **Setup.** The steward runs `kb-init`; defines an initial type vocabulary (`outcome`, `ux-flow`, `coding-spec`, `test-plan`) with a readiness checklist for `coding-spec` only; commits.
2. **Evidence.** The PM runs `kb-ingest` on the product vision document and two meeting-note exports. The agent finds no conflicts (empty KB), files three raw documents, and recommends — but does not create — an outcomes document.
3. **PM authoring.** The PM starts `kb-author` for an `outcome` document derived from all three raw sources. Two ambiguities surface; the PM resolves one and parks one in the uncertainty register; the document ships `current`, with the session archived to `raw/chats/` and linked as a parent (DG5).
4. **UX authoring.** The designer authors a `ux-flow` derived from the outcome document *and* a raw user-research note — cross-role, multi-parent, mixed-class derivation (DG1).
5. **Engineering authoring.** An engineer authors a `coding-spec` derived from the outcome, the ux-flow, and a raw compliance source. The readiness checklist flags a missing interface contract; the engineer supplies it in-session; `current`.
6. **QA authoring.** A QA engineer authors a `test-plan` derived from the coding-spec and the outcome. Consuming agents (a coding agent, a test-generation agent) now work from the same connected context.
7. **Feedback.** A coding agent implementing the spec hits a contradiction between the interface table and the actual upstream API; its error report is ingested as a `raw/feedback/` record about the spec (ING-6). The engineer opens a `kb-author` revision session; the feedback record and the revision's session record both join the spec's lineage.
8. **Change.** A new meeting note revises the outcome's scope. `kb-ingest` detects the conflict, asks the PM, and on confirmation supersedes the relevant outcome content; the propagation plan lists the ux-flow, coding-spec, and test-plan. The agent updates each — respecting the coding-spec's `instructions` line about retry semantics, which routes one change back to the engineer as a question — with each role's human confirming their document's judgment calls.
9. **Steward review.** Weekly `kb-lint`: drift report is empty (all agent changes were human-confirmed in-session), one stale orphan is flagged and retired.

Humans spent their time exactly where the product intends: supplying evidence, answering well-framed questions, and co-authoring the documents that direct the agents.

## 9. Non-Functional Requirements

- **NFR-1 — Substrate portability.** Plain UTF-8 Markdown + YAML in Git; fully readable and navigable by a human with a text editor. No database, server, or index required for correctness.
- **NFR-2 — OKF compatibility.** Bundles conform to OKF v0.1's required surface (parseable frontmatter with `type`; `index.md`/`log.md` conventions; body links as relative paths). KBDD-specific fields (`id`, `instructions`, `last_human_touch`, …) ride as extension keys per FM2/§6.5.
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
| **Propagation completeness** | % of superseded documents whose transitive downstream set was updated or explicitly deferred within one lint cycle | 100% |
| **Consumer zero-clarification rate** | % of consuming-agent tasks (e.g., coding from a spec) completed without KB-related clarification | ≥ 70% (Phase 3 pilot) |
| **Traceability coverage** | % of `current` documents whose chains terminate at evidence/decisions (`kb validate`) | 100% (hard gate) |

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Graph spaghetti** without fixed layers: inconsistent granularity, tangled derivations | KB becomes hard to navigate and reason about | Type vocabulary + readiness checklists as soft structure; DG3 coverage discipline; `kb links --depth` and lint orphan/shape reporting; steward curation |
| **Acceptance-at-creation complacency**: `current` read as "reviewed" when the human co-authored hastily | Quality theater | Drift report + `last_human_touch` visibility; readiness checklists at authoring time; audit metrics |
| **Instruction-field misuse**: directives that conflict with governance or attempt out-of-scope authority | Inconsistent or unsafe maintenance | IN1–IN4: precedence, scope limits, surface-don't-choose, lint coverage |
| **Question fatigue**: clarification-first degenerating into interrogation | Humans disengage; agents get pressured back into assuming | CS5 framing standards; batch questions per session; clarification-conversion metric as quality signal |
| **Propagation fatigue**: every upstream change fanning out into many confirmations | Change becomes expensive; updates get deferred | Governance-defined auto-safe change classes (CS3); dependency-ordered batching; impact view (LINT-4) keeps deferrals visible instead of lost |
| **CLI/skill version skew** | Skills invoke commands that behave differently | NFR-9 version declaration; CLI output-schema stability; validate-on-session-start |
| **Provenance-washing**: synthetic citing synthetic until claims float free of evidence | Audit chain becomes decorative | DG2 termination rule enforced by `kb validate`; session records (§6.1) make human answers citable |

## 12. Release Phasing

- **Phase 1 — CLI core + scaffold.** `kb` CLI (query, graph, integrity, housekeeping groups) with tests and CI; `kb-init`. Exit: a KB can be scaffolded and an existing document set validated and adopted.
- **Phase 2 — Evidence pipeline.** `kb-ingest` (file/stdin/clipboard adapters) + `kb-lint`. Exit: raw material flows in with clarification-first conflict resolution, supersession, and propagation; drift and impact reporting live.
- **Phase 3 — Co-authoring.** `kb-author` (create + revise), readiness checklists, session-record capture. Exit: the §8 multi-role scenario executes end-to-end with a real project team; metrics instrumented; a consuming agent completes a task from KB context.
- **Phase 4 (post-v1) — Extensions.** Additional ingest adapters (Slack, mail, ticketing); optional context-package tooling if manual authoring of packages proves repetitive; retrieval-index accelerators behind the CLI; reconciliation of consuming-agent outcomes back into evidence; multi-KB references (OQ4).

## 13. Open Questions

1. **OQ1 — Auto-safe propagation classes.** Which change classes should governance ship as auto-safe defaults (CS3) vs always-confirm? Proposal: start with "cited-figure/date refresh" only; expand from Phase 2 field data.
2. **OQ2 — Draft visibility to consumers.** Should consuming agents be permitted to read `draft` documents with a warning, or be hard-blocked? Proposal: hard-block by default, governance-relaxable per type.
3. **OQ3 — Uncertainty register shape.** Single register document vs per-document open-question sections with a CLI-aggregated view. Proposal: single register with backlinks (simpler propagation of answers); revisit if it becomes a merge hotspot.
4. **OQ4 — Cross-KB references.** Reserve a URI scheme now for citing documents in other bundles (e.g., an org-wide compliance KB)? Recommendation: reserve the syntax in v1 (`kb://<bundle>/<id>`), implement post-v1.
5. **OQ5 — Session-record fidelity.** Full verbatim transcripts vs decision summary plus key excerpts: affects repository size, privacy exposure, and citation precision. Proposal: summary mandatory, transcript best-effort (AUT-8), with a governance switch for verbatim retention; revisit with Phase 3 field data.

## Appendix A — Repository Layout

```
kb/
├── kb-config.json                # config + KB root marker: type vocabulary, readiness checklists, propagation rules, id prefixes, schema version
├── index.md                      # root navigation (CLI-generated)
├── log.md                        # KB-wide history (CLI-appended)
├── governance/
│   ├── templates/                # optional per-type document templates
│   ├── conventions.md            # standing project conventions
│   └── health.md                 # latest lint report
├── raw/
│   ├── index.md
│   ├── sources/                  # normalized external evidence (immutable)
│   ├── chats/                    # session records from kb-author / kb-ingest (immutable)
│   └── feedback/                 # consumer feedback about synthetic documents (immutable)
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

## Appendix C — Glossary

| Term | Definition |
|---|---|
| **Raw document** | Immutable evidence; the KB's ground truth (sources, session records, feedback) |
| **Session record** | Archived chat of a human-led session, headed by a human-confirmed decision summary (`raw/chats/`) |
| **Feedback record** | Evidence from a consumer of a synthetic document (errors, test failures, review comments), linked via `about` (`raw/feedback/`) |
| **Synthetic document** | Human-created, agent-maintained document derived from parents in the graph |
| **Derivation graph** | The acyclic multi-parent structure formed by `derived_from` links; replaces fixed layers |
| **Readiness checklist** | Governance-defined, per-type completeness criteria checked during authoring |
| **Supersession** | Replacement of older content/documents by newer, preserving lineage via `supersedes` and Git history |
| **Propagation** | Human-confirmed updating of the downstream set after a supersession |
| **Drift report** | Lint listing of `current` documents changed since their `last_human_touch` |
| **Uncertainty register** | The document holding questions humans chose to defer (ask-first, register-second) |
| **`kb` CLI** | The deterministic, independently versioned toolset all skills share |
