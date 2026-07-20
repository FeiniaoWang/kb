# Development Brief: PRD v0.5 — What Changed and How to Get There

**Audience:** the `kb` CLI development team
**Date:** 2026-07-18
**Upstream:** [docs/prd.md](prd.md) v0.5 — the root and single source of truth. This brief is a derived document; if it disagrees with the PRD, the PRD wins and this brief is wrong.

---

## 1. Why there was a change

A vision-refinement session on 2026-07-18 revisited the product's foundations against three ideas: the KB must make *all* project context AI-accessible (humans stop being copy-paste machines), knowledge must be a *network* rather than a pile of files, and a KB is *purpose-built* the way a data warehouse is — raw evidence is the lake, and human-led sessions distill it into purpose-specific documents. Working through those ideas surfaced real gaps in the model (no in-place revision path, no non-provenance links, no way to record "we know this is outdated and deferred it"), and the resolutions are now normative in PRD v0.5.

The PRD itself was also restructured: the changelog is gone, the decision rationale that used to live in `docs/adr/` and the glossary that lived in `CONTEXT.md` are folded into the PRD body and Appendix C, and both files were **deleted**. Do not recreate them; new decisions go into the PRD directly. The PRD no longer references repo-internal documents — references flow strictly downstream (specs cite the PRD, never the reverse).

## 2. The changes that affect the implementation

Ordered roughly by how much work each implies.

### 2.1 New command: `kb revise` (CLI-14) — the biggest new surface

In-place revision of a synthetic document. This resolves what was OQ6: the old model expressed *every* change as supersession (`kb create --supersedes`), which mints a new id each time. Since consolidation of new evidence is routine, that would churn ids and destroy the external-citation stability that justifies frontmatter ids (PRD §6.5). The decision (PRD §6.7, "decision and rationale"):

- **Revision preserves the id.** Body/frontmatter mutation, parent appends (`--add-parent`), associative-link appends (`--link TYPE=REF`), `pending_upstream` set/clear (`--pending REF` / `--clear-pending REF`), and a `revised` log entry.
- **Revision owns explicit status transitions** (`--status draft|current|retired`) — the lifecycle previously had no legal write path for `draft → current`. Status never changes *implicitly*, and `superseded` remains exclusively set by `kb create --supersedes` (PRD LS5).
- **Supersession is reserved for genuine replacement or rescoping.**

**Guidance the team must not miss:**

- `--add-parent` can create a derivation cycle. The pre-write validation must include the DG2 acyclicity check, not just reference resolution. This is the one genuinely new failure mode revision introduces.
- The lossless frontmatter editor built for supersession (`core/frontmatter.py`) is the right foundation — revise must preserve unknown keys, key order, and YAML style exactly as supersession already does. Do not build a second editing path.
- `timestamp` advances on every revision; `last_human_touch` advances only on human-confirmed revisions. The CLI cannot know who confirmed — expect the spec to make this an explicit flag rather than a guess. This flag carries real weight now: instruction-authorized *automatic* consolidations (§2.6) must advance `timestamp` only, so the drift report can catch every unconfirmed automatic update.

Like every command, `kb revise` goes through the spec → plan → code pipeline. Questions the spec pass must settle (flagged here so nobody improvises answers in code): whether `title`/`description` are revisable; exact `--clear-pending` semantics when propagation turns out to be a no-op; whether `pending_upstream` entries must be members of `derived_from`; behavior when revising a `superseded`/`retired` document (expected: refuse).

### 2.2 Associative links (`links:` frontmatter) — PRD §6.9

A typed, non-provenance relationship layer: `links:` maps a link type to a list of ids. The rules with implementation consequences:

- Links live on **synthetic documents only**; targets may be any class. Raw files stay byte-immutable — that decision was deliberate (rejected alternatives: "body-immutable" raw, standalone edge records).
- The **link-type vocabulary is governance-declared in `kb-config.json`** (like `types` and `tags`), with shipped defaults `references`, `contradicts`, `constrains`. Config model and schema version are affected.
- `kb validate` gains findings: undeclared link type, unresolvable link target, and `links`/`pending_upstream` appearing on a non-synthetic class (the existing known-key-on-wrong-class family).
- Associative links are **exempt from acyclicity** — mutual `references` is legal. The cycle detector must run on `derived_from` only. They also never satisfy DG1/DG5 and never create propagation obligations ("notify, never obligate" — they surface in impact reports as *aware of change* only).
- The future `kb links` command traverses them on request, provenance by default.

### 2.3 `pending_upstream` marker — PRD §6.8

When a parent is revised and the human defers propagating into a child, the child gets `pending_upstream: [<revised parent id>]`. It is a **marker, not a status** — the document stays `current` (a fifth status was rejected because `--status current` filters would silently drop the only existing spec). Consumers reading a marked document are **warned, never blocked**. The marker is set/cleared via `kb revise`. Validate needs shape/reference checks for it; `kb show`/query output should eventually surface the warning.

### 2.4 KB charter — third governance document

`governance/charter.md`, reserved slug id `GOVERNANCE-CHARTER`, reserved type `charter`. It records intent (who the KB serves, architectural rationale); `conventions.md` remains the binding rules; machine-checkable settings stay in config. `kb init` must scaffold it alongside the existing two governance documents, and validate's governance-type table gains `charter`.

### 2.5 Semantics tightened elsewhere

- **CS3 propagation now triggers on revision as well as supersession.**
- **DG5's "revised by" clause is mechanically maintained:** at session close, the session record's id is appended to the `derived_from` of every document consolidated or revised in that session (skill-level behavior, but it depends on `kb revise --add-parent`).
- **Terminology is normative** (PRD Appendix C, with *Avoid* columns). Code identifiers, CLI help text, and JSON field names for new work should use the canonical terms: *revision* (not version), *consolidation* (not merge/auto-update), *purpose document*, *building block*, *charter*. Existing identifiers don't need renaming sweeps; apply on touch.
- **Old OQ7 was renumbered to OQ6** when the resolved OQ6 was removed. Any spec that cites OQ numbers needs its citations checked when next touched.
- **Do not hardcode finding-code counts anywhere.** The old "20 codes: 16 errors, 4 warnings" enumeration was deliberately dropped from the PRD because the v0.5 additions extend it.
- **The command surface was made MECE** (PRD §7.1, "Command-surface MECE — decision and rationale"): reading is one command per selection mode — `kb filter` (predicates), `kb search` (text), `kb show` (refs) — with output shape as a projection, so the formerly separate `kb frontmatter` (CLI-3) and `kb resolve` (CLI-5) are **retired** into `kb show --output frontmatter|path` / `--field` (a `resolve` alias may remain); `filter` lost `--derived-from` (graph selection belongs exclusively to `kb links`) and returns paths/frontmatter by default, bodies only on explicit `--output full`; `kb mv` is regrouped as a Write command; validate is scoped as the *document*-integrity checker (index invariants delegated to `kb index --check`); and a new **`kb report drift|impact|orphans` (CLI-15)** gives lint's deterministic reports a CLI surface, as NFR-3 requires. Retired CLI numbers are never reused.

### 2.6 Division of labor, automatic consolidation, and CLI-exclusive access

A final vision correction sharpened three things (PRD §1, G2, G10, §5.2, §6.6):

- **Authoring mode is free; the invariants are not.** Synthetic documents are *human-directed*, no longer described as "human-authored": live co-authoring, agent-drafted-and-human-approved, or other human-driven modes are all legitimate. What the KB mandates is human initiation, derivation from existing KB documents, and the CLI write path. **No CLI change follows** — `kb create` was already the sole birth path and stays it — but use *human-directed* in help text and comments, not *human-authored*, and note that the `kb-author` skill is now "the standard path," not "the only path."
- **`instructions` may define automatic consolidation rules** (PRD §6.6): how to update the document when a new parent joins its `derived_from`. Changes covered by such a rule (or by governance auto-safe classes, CS3) are applied **without per-change confirmation** — logged, advancing `timestamp` but not `last_human_touch`, drift-visible until a human confirms; anything not clearly covered falls back to a recommendation for human approval. Interpreting the rule is skill-level judgment; the CLI's job is the mechanics: the revise flag split in §2.1 (confirmed vs. automatic), full validation on every automatic write (schema + DG2 — an instruction can never smuggle in a cycle), and log entries that make the drift grouping possible. This also raises the stakes on `kb report drift`: it is the audit backstop for everything applied automatically.
- **CLI-exclusive access is now a hard rule** (PRD §5.2, NFR-3): every agent read goes through `kb show` and every agent write through the write *and housekeeping* commands (CLI-7/8/13/14 and 9/10/11) — agents never open or edit KB files directly; only humans may hand-edit governance documents. For the CLI this means the command surface must stay sufficient for everything a skill legitimately needs — if a skill is ever tempted to touch a file directly, that is a missing CLI capability to raise, not a workaround to take.
- **New G10** names the point of all this: agents do most of the heavy lifting — drafting, analysis, consolidation, propagation, recommendations — and human attention is reserved for direction, review, and judgment. When an implementation trade-off arises between "make the agent's job easier" and "make the human review load lighter," G10 says both matter and the drift/impact machinery is what keeps the second honest.

## 3. Where the implementation stands relative to v0.5

Current state (per the code and tests, 276 passing): `kb init`, `kb create`, `kb validate` are complete against their specs; **`kb ingest` is implemented only through AC23 of 50** (binary files and `--dest` missing, even though help text advertises them); query/graph commands are designed but not built. None of the v0.5 additions exist in code, and all four command specs now lag the PRD to some degree — most sharply `kb-validate.md` (finding table) and `kb-init.md` (charter scaffold).

## 4. Suggested execution plan

The ordering principle: **finish what's half-done, then refactor the shared ground, then extend schemas, then build the new command** — so `kb revise` lands on a clean foundation instead of becoming the third copy of a duplicated write pipeline.

**Step 1 — Finish `kb ingest` (AC24–AC50).** Pre-existing debt, independent of v0.5, and the advertised-but-missing behaviors (binary originals, `--dest`) are exactly the ones the PRD's CLI-8 now states normatively. Nothing in v0.5 changes the ingest contract, so this can start immediately.

**Step 2 — Extract the shared write pipeline.** `create` and `ingest` already duplicate the root/config/scan/malformed-check/destination/index/log workflow, and their safety hardening has drifted apart; `revise` would be the third copy. Consolidate the shared workflow (and move `slug()` out of `ingest.py` into a neutral naming module) *before* writing revise. How to structure this inside `src/kb/core` is the team's call — the requirement is only that the three write commands share one preflight/write/index/log path with uniform safety behavior.

**Step 3 — Schema extensions, spec-first.** Update `kb-config` (link-type vocabulary; schema version), the frontmatter models (`links`, `pending_upstream` as known optional synthetic keys), the governance type table (`charter`), and `kb-init` (charter scaffold). Then extend `kb-validate`: new finding codes for link vocabulary/resolution, marker shape, wrong-class placement — one AC per code, per the established pattern. Keep the cycle check scoped to `derived_from` only.

**Step 4 — `kb revise`: spec → plan → implementation.** The full contract pass, settling the questions in §2.1. Implementation should be thin over the Step 2 pipeline plus the existing lossless editor. This is the gate for Phase 2 of the release plan (consolidation is part of the evidence-pipeline exit criteria).

**Step 5 — Read/graph/report commands.** `filter`, `search`, `show`, `links`, and the new `kb report` were already next on the roadmap; they are greenfield, so build them to the MECE surface directly — `show` carries the frontmatter/path/field projections (there is no separate `frontmatter` or `resolve` command to implement), `filter` has no derivation predicates, and associative-link traversal plus `pending_upstream` warnings go in from the start rather than being retrofitted. `kb index --check` (now explicitly in CLI-9) belongs in this wave too — it completes the CI gate `kb validate && kb index --check`.

Steps 1 and 3 are independent and can run in parallel; Step 4 depends on 2 and 3; Step 5 depends only on 3.

## 5. What has *not* changed

The foundations the current code is built on are all reaffirmed: Markdown + YAML as the only source of truth, per-invocation scan with no stored index, `type` as the authoritative classifier, max+1 sequential ids (now with the canonical six-digit form stated in the PRD), CLI-owned indexes and log, no Git operations in the CLI, validate-fully-before-write, unknown-key preservation, and the CLI/skill split with mechanical truth on the CLI side. No rewrite is implied anywhere — v0.5 is additive plus one refactor the codebase was already asking for.
