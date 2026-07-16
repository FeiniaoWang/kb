# Handover: `kb` CLI specification work

**Purpose of this document.** Bootstrap a new working session to continue authoring per-command specification documents for the `kb` CLI. Attach this file and say, e.g., *"Please start drafting the specification document for the kb create command."* Everything normative lives in the repo files referenced below — **always read the current files; they win over anything summarized here** (the human edits documents between sessions).

**Next up: `kb create` (CLI-13).** The immediate task is the contract spec for `kb create`, the deterministic write path for **synthetic** documents (the counterpart to `kb ingest` for raw).

> **The `kb create` design is NOT set in stone.** The `kb create` details in the [master design](superpowers/specs/2026-07-13-kb-cli-design.md) (CLI-13 section) and [PRD](prd.md) (CLI-13, the 2026-07-16 consistency note, AUT-6/7/8, OQ6) are a **starting proposal, not settled decisions**. Before writing the spec, the author should step back and reason from first principles about the **purpose of this knowledge base project** — its central idea (humans drive creation, agents maintain; evidence-to-artifact traceability; deterministic mechanical truth in the CLI, judgment in the skills) — and design the command that best serves it. The command surface, flags, frontmatter emission, id/lifecycle handling, error model, and split of responsibility between `kb create` and the `kb-author` skill are all open to reconsideration. Prefer the existing proposal where it genuinely fits, but do not treat it as a constraint. **If the spec author changes any of this, the master design and the PRD must be updated in the same change so all three documents stay in sync** (§4 step 6, §9 step 3 already require this) — the human cares a lot about cross-document consistency. The rest of this handover summarizes the *current* proposal so you know where it stands; read it as the material to challenge and refine, not as fixed requirements.

The session's job is to turn a well-reasoned design into a full contract spec mirroring the existing ones (`kb-init.md`, `kb-ingest.md`).

## 1. What this project is

We are building the **KB Skill Suite**: a shared project knowledge base (Markdown + YAML in Git, OKF-conformant) where humans of all roles and AI agents work in one context. Humans create documents in co-authoring sessions; agents maintain them; everything traces back to immutable raw evidence through a derivation graph. See [docs/prd.md](prd.md) for the full product definition.

Delivery is split in two layers:
- **`kb` CLI** (this phase) — the deterministic layer: query, graph, integrity, ingest, **synthetic authoring (`kb create`)**, housekeeping. Python, Typer, tested, independently versioned.
- **`kb-*` Agent Skills** (later) — the judgment layer. Explicitly out of scope until the CLI is done.

**Strategy decided:** build the full CLI first (all command groups incl. ingest and `kb create`), each command specified by a self-contained contract spec before implementation. Specs are written to be refined into detailed behavior specifications that drive development.

## 2. Authoritative documents (read in this order)

| File | Role |
|---|---|
| [docs/specs/commands/00-shared.md](specs/commands/00-shared.md) | **Normative cross-command contracts**: root discovery, exit codes, output/JSON envelopes, REF definition, pipelines, the scan, id grammar & allocation, **core data models** (Pydantic, with growth policy), log format, help-text and testing conventions, Git-agnostic + directory invariants |
| [docs/specs/commands/kb-init.md](specs/commands/kb-init.md) | The **first command spec and the original template** — its section structure, level of detail, and AC style are the pattern for every subsequent spec |
| [docs/specs/commands/kb-ingest.md](specs/commands/kb-ingest.md) | **The closest template for `kb create`** — the other write-path command: id allocation, pre-flight-then-write atomicity, `--dest` + directory invariant, index/log refresh, slug/collision rules, `AdapterPayload`-style internal contracts, AC1–AC50. Reuse its shape and machinery wholesale |
| [docs/superpowers/specs/2026-07-13-kb-cli-design.md](superpowers/specs/2026-07-13-kb-cli-design.md) | Master design & decision record: per-command design bullets for ALL commands (the starting material for each new spec), architecture, package layout. It has a detailed `kb create` (CLI-13) section — treat it as a **proposal to challenge and refine** (see the callout in §Next up), not a fixed spec; update it if the design changes |
| [docs/prd.md](prd.md) | Product requirements; requirement ids (CLI-1…CLI-13, FM0–FM3, DG1–DG5, CS1–CS5, LS1–LS4, ING/AUT/LINT/INIT, NFR-1…9, OQ1–OQ6) cited throughout |
| [AGENTS.md](../AGENTS.md) | Per-session coding-agent rules: package layout, invariants, working conventions |

**Precedence when documents disagree:** command spec > 00-shared.md > master design > PRD. Deviating from a spec means updating the spec in the same change.

## 3. Status

**Done (committed):**
- Master design for the whole CLI (all commands), including a **detailed `kb create` (CLI-13)** section.
- `00-shared.md` — shared foundations + core model table (models are added by the first command spec that needs them; the *Introduced by* column tracks this). Includes `SyntheticFrontmatter` (shape pinned; full enforcement deferred to `kb validate`), which `kb create` will emit.
- `kb-init.md` — complete contract spec, user-reviewed through several rounds, **AC1–AC30** + coverage map.
- `kb-ingest.md` — complete contract spec, iterated through the review gate and an AC-comprehensiveness pass, **AC1–AC50** + coverage map. Treat as settled unless the human reopens it. Decisions that landed: `SOURCE` positional + `--dest` subdir; clipboard via platform tools; collisions auto-suffixed with the new id; index refresh = target dir + nearest pre-existing ancestor; full pre-flight before any write; `--about` resolves to any doc carrying an id (canonical id stored); `--origin` is free-form provenance (path, **URL**, or label), stored verbatim; `RawFrontmatter` gained an always-written `title`.
- PRD kept consistent with every design decision (dated "Consistency updates" notes in its header; the **2026-07-16** note introduces `kb create`).

**Uncommitted at handover (the human's between-session edits introducing `kb create`):** `docs/prd.md`, `docs/specs/commands/00-shared.md`, `docs/superpowers/specs/2026-07-13-kb-cli-design.md` carry the CLI-13 additions (master-design `kb create` section, PRD CLI-13 row + OQ6 + AUT-6/7/8 updates, package layout `create.py`). Read them as current. (`main.py` is also staged for deletion — unrelated to spec work.)

- No implementation code exists yet. `pyproject.toml` has `typer`, `pyyaml`, `pydantic` (2.x), pytest via uv; Python ≥ 3.14; `src/` layout planned per AGENTS.md.

**Next (agreed order):** `kb create` → `kb validate` → then the rest (show, filter, search, frontmatter, resolve, links, mv, index, log). Rationale: `kb create` is the natural pair to `kb ingest` (the two write paths) and is cheap now — it reuses ingest's `next_id` allocator, malformed-file guard, `--dest`/directory-invariant handling, slug/collision rules, and pre-flight-then-write atomicity, and forces the `SyntheticFrontmatter` emission surface into concrete form. `kb validate` then completes the model set (Finding, full synthetic-schema enforcement, DG/LS checks); the query/graph commands become thin afterward.

**Parked:** the implementation plan for `kb init` (the writing-plans step) — spec approved, planning not started.

## 4. The spec-authoring process we follow

Each spec is produced in a **brainstorming session** with this shape (the human insists on it — do not skip steps):

1. Read the current repo docs (they may have changed between sessions).
2. Ask clarifying questions **one at a time**, multiple-choice where possible, only about genuinely open decisions. The human answers quickly and decisively; when they say "keep it simple," believe them.
3. Propose approaches with trade-offs and a recommendation where a real design fork exists.
4. Present the design in sections, getting approval per section.
5. Write the spec file, self-review (placeholders, contradictions, ambiguity, scope), fix inline.
6. **User review gate** — the human reviews and requests changes over several rounds; apply each, keep all documents consistent (00-shared, master design, PRD, AGENTS.md), commit per logical change with requirement ids in messages.
7. Only after explicit approval: transition to implementation planning (writing-plans skill).

## 5. The spec template (contract style — mirror kb-init.md / kb-ingest.md exactly)

```
# Spec: `kb <command>`
Implementation context: this file + 00-shared.md.     ← two-file closure rule
Traceability: PRD requirement ids covered.
1. Purpose            — one paragraph
2. CLI surface        — synopsis, param table (kind/type/default/meaning)
3. Help text          — NORMATIVE WORDING (layout is Typer's): description,
                        each option help string, Examples section (2–5 lines).
                        Tests assert substrings, never layout.
4. Behavior           — numbered normative algorithm, deterministic enough
                        to implement from; edge decisions inline. For write-path
                        commands: PRE-FLIGHT (all checks) THEN WRITE (atomic),
                        so a failed run leaves the KB byte-for-byte untouched.
5. Filesystem effects — exact tree + file contents pinned VERBATIM (byte-for-
                        byte where possible; pattern-match only timestamps)
6. Output             — text form + exact JSON shape; deterministic ordering
7. Errors & edge cases— table: # | condition | behavior/code | exit
8. Acceptance criteria— AC1..ACn contiguous, one pytest test per AC
                        (test_ac<NN>_<slug>), coverage map paragraph mapping
                        AC groups → spec sections; each AC independently
                        testable with an unambiguous pass condition. Aim for
                        comprehensiveness: every §4 step and every §7 error row
                        maps to ≥1 AC (note any untestable exceptions).
9. Out of scope       — explicit non-goals incl. what belongs to skills
```

Cross-cutting rules that every new spec must honor (details in 00-shared.md):
- Error codes `E_<CMD>_*`, unique, SCREAMING_SNAKE; exits 0/1/2 per the shared contract; `--json` error envelope `{"error":{"code","message"}}`. (Some shared/cross-command codes are unprefixed, e.g. `E_NO_KB`, `E_CONFIG_INVALID`, `E_SCHEMA_UNSUPPORTED`; the master design's `kb create` bullets also name shared `E_REF_UNRESOLVED` / `E_DEST_INVALID` / `E_TYPE_RESERVED` / `E_NO_PARENTS` — settle in-session whether these get a `_CREATE_` prefix, mirroring how ingest used `E_INGEST_*`.)
- `type` is mandatory on every `*.md` and authoritative (FM0); DocClass/RawClass derive from `type`, never path; location must agree with `type`.
- Every directory has a CLI-owned read-only `index.md` (`type: index`, no id); any command creating a directory creates its `index.md`.
- Git-agnostic: no command runs `git` or inspects Git state, ever.
- Scan-on-demand, no stored index; malformed/missing-`type` files go to `KB.malformed`; **commands that allocate ids refuse while `KB.malformed` is non-empty (exit 2)** — applies to `kb create` exactly as to `kb ingest`.
- CLI-only data access for skills (`kb show` is the read path); **CLI-only write discipline** for synthetic docs is precisely what `kb create` exists to enforce (agents never hand-write synthetic files).
- Deterministic output ordering (alphabetical by relative path unless the spec pins otherwise).
- New core models: add to 00-shared §7 with *Introduced by* = the new spec; never change existing fields, only add. (`kb create` likely graduates `SyntheticFrontmatter` from "shape pinned" toward emission; keep enforcement in `kb validate`.)
- After writing a spec, reconcile the master design and PRD if the spec sharpened or changed anything (the human cares a lot about cross-document consistency — grep before claiming done).

## 6. Decisions log (chronological, with rationale in the master design)

- Full CLI before skills; contract specs before code.
- Layered architecture: pure core (`src/kb/core/`) + thin Typer CLI (`src/kb/cli/`); models in `core/model.py` as Pydantic 2.x BaseModels (`extra="allow"` on frontmatter; Pydantic never does file I/O). `core/create.py` holds synthetic creation (id alloc + frontmatter emit + file), alongside `core/ingest.py`.
- Ids: sequential per prefix, **6-digit** zero-pad (`KB-000042`), max+1 from the scan, gaps never refilled; merge collisions caught by `kb validate` in CI. Reserved **slug ids** for governance system docs (`GOVERNANCE-CONVENTIONS`, `GOVERNANCE-KB-CONFIG`); `GOVERNANCE` prefix never allocated numerically.
- `kb-config.json` (clean strict JSON, stdlib-parsed, no comment keys) lives at the KB root and doubles as the **root marker** — no `.kb` file. `schema` key is tooling-owned. Human-readable field docs live in `governance/kb-config.md`. Discovery: closest ancestor with `kb-config.json` wins; existence-based (malformed config ≠ "no KB").
- No nesting guard in `kb init`; nested roots allowed.
- `index.md` in **every** directory: `DocClass INDEX`, `type: index`, folder `description`, **no id** (path-addressed), **CLI-maintained and read-only** for humans/agents; body = generated-header comment + `## Subdirectories` / `## Files` listing sections (see kb-init.md §5.2 for the exact current format — the human refined it directly). A document without a `description` renders without the ` - <description>` tail (kb-ingest introduced this; synthetic docs always have a `description`, so they keep the tail). No `.gitkeep` anywhere.
- `log.md`: operational, append-only, `type: log` frontmatter (FM0), pipe-format lines `- <UTC ISO> | <action> | <actor> | <ids or -> | <note>`; actor column kept deliberately (PRD LS4/NFR-5 audit trail). `kb create` appends a `created` entry (incl. the superseded id when `--supersedes` is used).
- **Two write paths, symmetric:** `kb ingest` writes immutable `raw/` documents; `kb create` writes `synthetic/` documents. Both allocate ids, honor the malformed guard, use `--dest` + the directory invariant, refresh the target `index.md` + nearest pre-existing ancestor, append a log entry, and validate fully **pre-flight** before an atomic write.
- **`kb create` specifics *proposed* in the master design (CLI-13) — provisional, open to redesign (see the §Next up callout), and if changed must be reconciled back into the master design + PRD:** emits the full FM1 synthetic schema; `timestamp` = `last_human_touch` = creation instant (LS2); `--status` defaults to `draft`, only `draft`/`current` legal at birth; **≥1 `--derived-from` required (DG1)**, each stored as canonical id; **DG5 (session-record parent) deliberately NOT enforced here** — it stays a `kb validate` check (single authoritative enforcement point); `--type` must be a synthetic type (reserved types rejected `E_TYPE_RESERVED`; unknown-but-unreserved types allowed with a stderr warning, open vocabulary); over-long `--description` warns, never blocks; **`--supersedes` atomically flips the prior doc to `superseded`** and updates its timestamps in the same write (never leaves the LS-invalid "supersedes target not marked superseded" state); body from `--body-file FILE|-`, empty allowed (draft stub), normalized like ingest (LF, one trailing newline); filename = slug(`--title`) else lowercased id, collision → `-<id>` suffix.
- In-place **synthetic revision** (editorial body/frontmatter edits, adding a parent after creation, status changes short of supersession) has **no command in v1** — deferred as **OQ6**; v1 expresses semantic revision as supersession via `kb create --supersedes`.
- Git: **no Git operations anywhere in the CLI** (user/skills own Git).
- Output ordering: alphabetical by relative path.

## 7. Known open threads (candidates for future sessions)

**For `kb create` (next) — the whole design is open for reconsideration (see the §Next up callout), not just these sub-details. The master design's CLI-13 bullets are extensive but provisional; below are the sub-details most obviously unsettled even if the overall shape is kept:**
- **`--supersedes` vs `--derived-from`:** does `--supersedes X` implicitly add `X` to `derived_from` (the new version derives from the one it replaces), or must the author list it explicitly? Also: must the `--supersedes` target be a **synthetic** document, and what happens if it is already `superseded`/`retired` (re-supersede? error?)?
- **`derived_from` ordering** in the emitted frontmatter: preserve `--derived-from` argument order, or sort (by id)? (Pin it for deterministic, diffable output.)
- **Error-code prefixing:** whether the master design's shared-looking codes (`E_REF_UNRESOLVED`, `E_DEST_INVALID`, `E_TYPE_RESERVED`, `E_NO_PARENTS`) become `E_CREATE_*` (mirroring `E_INGEST_*`) or are promoted to genuinely shared codes in 00-shared. Reconcile with `kb ingest`'s equivalents (`E_INGEST_DEST_INVALID`, `E_INGEST_ABOUT_UNRESOLVED`).
- **Body input surface:** master design pins `--body-file FILE|-` (no positional, unlike ingest's `SOURCE`). Confirm — and decide whether an inline `--body TEXT` is wanted (probably not; keep it simple).
- **Output/JSON shape:** mirror `kb ingest` §6 (`id`, `path`, `created`, `updated`) plus a `superseded` field when `--supersedes` is used.
- **DG3 coverage-note updates to parents** (AUT-6 mentions "updates parents' coverage notes where applicable"): confirm this is the **skill's** job, not `kb create`'s (likely Out of scope for the command).
- **`SyntheticFrontmatter` in 00-shared §7:** currently "shape pinned; enforcement specced in kb-validate." Decide how much `kb create` graduates it (construction/emission) while leaving cross-KB enforcement to `kb validate`.

**Other commands / product-level:**
- `kb validate` spec: finding-code table must consolidate every check accumulated in 00-shared/master design (FM0 universal type, type↔location, DG1/DG2/DG5, ids, tags, supersedes-status coupling, index staleness?). It is the **single authoritative enforcement point** for DG5 and full synthetic-schema checks that `kb create` deliberately defers.
- `kb show`'s own spec (the `---` terminator is a convention, not a parse boundary — JSON is the strict path; needs stating in its spec with a round-trip AC).
- Folder `description` customization gap: index.md is read-only, so a human currently has no way to set a folder description — deliberate; revisit with a small command if needed.
- AC22 in kb-init uses `E_INIT_IO` for wrong-kind occupied paths rather than a dedicated code — flagged as a judgment call.
- **OQ6 — synthetic revision/mutation write path** (the in-place counterpart to `kb create`), deferred pending Phase 3 `kb-author` field data. PRD open questions OQ1–OQ5 also remain open product-level.
- `kb init` implementation plan (writing-plans) not yet produced.

## 8. Working conventions with this human

- They review carefully and iterate: expect several rounds of targeted change requests per spec; apply exactly, keep every document consistent, commit per logical change (imperative subject, requirement ids like "CLI-13", "AC7" in the body where relevant, `Co-Authored-By: Claude`).
- They sometimes edit the docs directly between sessions (e.g. the index.md listing format, `kb-config.json` rename, **the whole `kb create` CLI-13 introduction**) — **re-read files at session start; never assume this handover or memory is current**.
- Ask before deciding anything user-visible (flag semantics, formats, naming); decide-and-flag for internal judgment calls, stating the reversal path.
- Simplicity requests are real: when they say "don't worry about X for now," remove X cleanly and record it in Out of scope rather than leaving vestiges.
- They value **comprehensive, unambiguous acceptance criteria** — the ACs are the input to detailed behavior specs that drive development. When asked, do a full pass ensuring every behavior and every error row maps to a test (kb-ingest AC1–AC50 is the bar).
- Tests: one AC = one test, `test_ac<NN>_<slug>`, Typer `CliRunner`, tmp_path fixtures, no subprocesses in unit tests.

## 9. Kickoff instruction for a new session

Given this document, the next session should:
1. Read [00-shared.md](specs/commands/00-shared.md), [kb-init.md](specs/commands/kb-init.md) and [kb-ingest.md](specs/commands/kb-ingest.md) (as templates — ingest is the closest analog for `kb create`), the **`kb create` (CLI-13) section** in the [master design](superpowers/specs/2026-07-13-kb-cli-design.md), and the relevant PRD requirements (CLI-13, FM1, DG1/DG5, LS1/LS2, AUT-6/7/8, OQ6).
2. **Reason from the project's purpose first** (see the §Next up callout): treat the master design's CLI-13 section and the PRD's `kb create` requirements as a proposal to challenge, not a fixed spec. Decide what command best serves the KB's central idea before committing to the existing surface. Then run the §4 process: clarifying questions (one at a time) on the genuinely open details listed in §7 for `kb create` **and on any part of the proposal you think should change**, then sectioned design presentation, then write `docs/specs/commands/kb-create.md`, self-review, and hand to the human for the review gate.
3. Update 00-shared §7 (models introduced/graduated), the master design (CLI-13 section), and the PRD (CLI-13 row, the 2026-07-16 consistency note, AUT-6/7/8, OQ6) wherever the new spec sharpens or **changes** behavior — then verify consistency by grepping across all documents before declaring done. This reconciliation is mandatory whenever the design diverges from the current proposal.
