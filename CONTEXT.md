# KB Skill Suite

A shared project knowledge base where every human role and every AI agent works in the same context: raw evidence flows in, human-governed synthetic documents are derived from it, and a deterministic `kb` CLI plus judgment-layer agent skills keep the graph consistent.

## Language

### Document classes

**Raw document**:
Immutable evidence — the KB's ground truth. Never edited; corrections arrive as new raw documents.
_Avoid_: source file, input, upload

**Synthetic document**:
A human-created, agent-maintained document derived from parents in the derivation graph.
_Avoid_: refined document, output, artifact

**Session record**:
The archived chat of a human-led authoring or ingest session, headed by a human-confirmed decision summary. The citable form of a human decision.
_Avoid_: decision record, transcript, chat log

**Feedback record**:
Evidence produced by a consumer of a synthetic document (errors, test failures, review comments), linked to the document it concerns via `about`.
_Avoid_: bug report, review

**Governance document**:
A steward-controlled document defining vocabularies, conventions, and readiness checklists.

**Purpose document**:
A leaf synthetic document distilled from a small sub-network of the KB, carrying complete and *only* the context needed for one specific outcome (e.g., an execution plan for one API). The clean-context unit handed to a consuming agent.
_Avoid_: context dump, spec bundle

**Building block**:
An intermediate synthetic document with no consumer-facing purpose of its own — a reusable node in the knowledge network from which purpose documents are distilled.
_Avoid_: draft, partial doc

### Structure

**Derivation graph**:
The acyclic, multi-parent structure formed by `derived_from` links. The KB's structure is this graph, not the directory tree.
_Avoid_: hierarchy, layer structure, tree

**Supersession**:
Replacement or rescoping of a document by a new one, preserving lineage via `supersedes` and history. Reserved for genuine replacement — routine maintenance is a Revision instead. Nothing is deleted.
_Avoid_: overwrite, update-in-place, delete

**Revision**:
An in-place update to a synthetic document that preserves its ID — the write path for consolidation and editorial change, performed in a human-led session.
_Avoid_: version, new edition

**Associative link**:
A typed, non-provenance relationship (references, contradicts, constrains, …) recorded in synthetic frontmatter. Navigational and analytical; never satisfies parentage rules.
_Avoid_: derived_from, backlink

**Propagation**:
The human-confirmed updating of the transitive downstream set after a supersession.
_Avoid_: cascade, sync

**Consolidation**:
Folding newly ingested evidence into an existing synthetic document that it concerns — triggered by new information arriving, not by supersession.
_Avoid_: auto-update, merge

**Co-authoring**:
The human-initiated, human-led session in which a synthetic document is created or revised with an agent. The only way synthetic content comes into existence.
_Avoid_: compile, generate, ETL, pipeline

**KB purpose**:
The high-level mission a knowledge base serves, which drives its structural decisions — directory architecture, type vocabulary, granularity conventions.
_Avoid_: theme, topic

### Actors and lifecycle

**KB steward**:
The human who owns governance: vocabularies, conventions, readiness checklists, tool versions.

**Consuming agent**:
An executor (coding agent, test-generation agent, …) that reads current documents and their ancestry as working context. Reads; never maintains.

**Readiness checklist**:
Governance-defined, per-type criteria for whether a document is complete enough for its consumers.
_Avoid_: definition of done, completeness contract

**Drift report**:
The lint listing of `current` documents changed since their `last_human_touch` — the standing answer to "what have agents touched that no human confirmed?"

**Uncertainty register**:
The document holding questions a human explicitly deferred. Ask first, register second.
_Avoid_: open questions list, backlog

**Stale**:
The condition of a `current` document whose parent was revised with propagation consciously deferred — recorded by a `pending_upstream` marker naming the unpropagated parent(s), never by a status change.
_Avoid_: outdated status, expired

**KB charter**:
The governance document stating the KB's purpose: who it serves, its consumers, and the architectural rationale behind its structure and vocabularies. Intent, not rules — consulted when structure is proposed.
_Avoid_: mission statement, README

**Conventions**:
The governance document holding the binding rules for how documents are written and maintained — the top of the instruction-precedence chain, consulted in every session. Rationale belongs in the charter; machine-checkable settings in config.
_Avoid_: style guide, guidelines, charter
