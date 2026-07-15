# Handover: `kb` CLI specification work

**Purpose of this document.** Bootstrap a new working session to continue authoring per-command specification documents for the `kb` CLI. Attach this file and say, e.g., *"Please start drafting the specification document for the kb ingest command."* Everything normative lives in the repo files referenced below — **always read the current files; they win over anything summarized here** (the human edits documents between sessions).

## 1. What this project is

We are building the **KB Skill Suite**: a shared project knowledge base (Markdown + YAML in Git, OKF-conformant) where humans of all roles and AI agents work in one context. Humans create documents in co-authoring sessions; agents maintain them; everything traces back to immutable raw evidence through a derivation graph. See [docs/prd.md](prd.md) for the full product definition.

Delivery is split in two layers:
- **`kb` CLI** (this phase) — the deterministic layer: query, graph, integrity, ingest, housekeeping. Python, Typer, tested, independently versioned.
- **`kb-*` Agent Skills** (later) — the judgment layer. Explicitly out of scope until the CLI is done.

**Strategy decided:** build the full CLI first (all command groups incl. ingest), each command specified by a self-contained contract spec before implementation. Specs are written to be refined into detailed behavior specifications that drive development.

## 2. Authoritative documents (read in this order)

| File | Role |
|---|---|
| [docs/specs/commands/00-shared.md](specs/commands/00-shared.md) | **Normative cross-command contracts**: root discovery, exit codes, output/JSON envelopes, REF definition, pipelines, the scan, id grammar & allocation, **core data models** (Pydantic, with growth policy), log format, help-text and testing conventions, Git-agnostic + directory invariants |
| [docs/specs/commands/kb-init.md](specs/commands/kb-init.md) | The **first command spec and the template to follow** — its section structure, level of detail, and AC style are the pattern for every subsequent spec |
| [docs/superpowers/specs/2026-07-13-kb-cli-design.md](superpowers/specs/2026-07-13-kb-cli-design.md) | Master design & decision record: per-command design bullets for ALL commands (the starting material for each new spec), architecture, package layout |
| [docs/prd.md](prd.md) | Product requirements; requirement ids (CLI-1…CLI-12, FM0–FM3, DG1–DG5, CS1–CS5, LS1–LS4, ING/AUT/LINT/INIT, NFR-1…9) cited throughout |
| [AGENTS.md](../AGENTS.md) | Per-session coding-agent rules: package layout, invariants, working conventions |

**Precedence when documents disagree:** command spec > 00-shared.md > master design > PRD. Deviating from a spec means updating the spec in the same change.

## 3. Status

**Done:**
- Master design for the whole CLI (all commands), committed.
- `00-shared.md` — shared foundations + core model table (models are added by the first command spec that needs them; the *Introduced by* column tracks this).
- `kb-init.md` — complete contract spec, user-reviewed through several revision rounds, with comprehensive acceptance criteria **AC1–AC30** and a coverage map.
- PRD kept consistent with every design decision (it has a dated "Consistency updates" note in its header).
- No implementation code exists yet. `pyproject.toml` has `typer`, `pyyaml`, `pydantic` (2.x), pytest via uv; Python ≥ 3.14; `src/` layout planned per AGENTS.md.

**Next (agreed order):** `kb ingest` → `kb validate` → then the rest (show, filter, search, frontmatter, resolve, links, mv, index, log). Rationale: ingest forces most core models into existence (scan, DocId allocation, RawFrontmatter, Document, KB, LogEntry); validate completes them (Finding, full synthetic schema); the query/graph commands then become thin.

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

## 5. The spec template (contract style — mirror kb-init.md exactly)

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
                        to implement from; edge decisions inline
5. Filesystem effects — exact tree + file contents pinned VERBATIM (byte-for-
                        byte where possible; pattern-match only timestamps)
6. Output             — text form + exact JSON shape; deterministic ordering
7. Errors & edge cases— table: # | condition | behavior/code | exit
8. Acceptance criteria— AC1..ACn contiguous, one pytest test per AC
                        (test_ac<NN>_<slug>), coverage map paragraph mapping
                        AC groups → spec sections; each AC independently
                        testable with an unambiguous pass condition
9. Out of scope       — explicit non-goals incl. what belongs to skills
```

Cross-cutting rules that every new spec must honor (details in 00-shared.md):
- Error codes `E_<CMD>_*`, unique, SCREAMING_SNAKE; exits 0/1/2 per the shared contract; `--json` error envelope `{"error":{"code","message"}}`.
- `type` is mandatory on every `*.md` and authoritative (FM0); DocClass/RawClass derive from `type`, never path; location must agree with `type`.
- Every directory has a CLI-owned read-only `index.md` (`type: index`, no id); any command creating a directory creates its `index.md`.
- Git-agnostic: no command runs `git` or inspects Git state, ever.
- Scan-on-demand, no stored index; malformed/missing-`type` files go to `KB.malformed`; **commands that allocate ids refuse while `KB.malformed` is non-empty (exit 2)**.
- CLI-only data access for skills (`kb show` is the read path); progressive disclosure (paths → frontmatter → snippets → body).
- Deterministic output ordering (alphabetical by relative path unless the spec pins otherwise).
- New core models: add to 00-shared §7 with *Introduced by* = the new spec; never change existing fields, only add.
- After writing a spec, reconcile the master design and PRD if the spec sharpened or changed anything (the human cares a lot about cross-document consistency — grep before claiming done).

## 6. Decisions log (chronological, with rationale in the master design)

- Full CLI before skills; contract specs before code.
- Layered architecture: pure core (`src/kb/core/`) + thin Typer CLI (`src/kb/cli/`); models in `core/model.py` as Pydantic 2.x BaseModels (`extra="allow"` on frontmatter; Pydantic never does file I/O).
- Ids: sequential per prefix, **6-digit** zero-pad (`KB-000042`), max+1 from the scan, gaps never refilled; merge collisions caught by `kb validate` in CI. Reserved **slug ids** for governance system docs (`GOVERNANCE-CONVENTIONS`, `GOVERNANCE-KB-CONFIG`); `GOVERNANCE` prefix never allocated numerically.
- `kb-config.json` (clean strict JSON, stdlib-parsed, no comment keys) lives at the KB root and doubles as the **root marker** — no `.kb` file. `schema` key is tooling-owned. Human-readable field docs live in `governance/kb-config.md`. Discovery: closest ancestor with `kb-config.json` wins; existence-based (malformed config ≠ "no KB").
- No nesting guard in `kb init`; nested roots allowed.
- `index.md` in **every** directory: `DocClass INDEX`, `type: index`, folder `description`, **no id** (path-addressed), **CLI-maintained and read-only** for humans/agents; body = generated-header comment + `## Subdirectories` / `## Files` listing sections (see kb-init.md §5.2 for the exact current format — the human refined it directly). No `.gitkeep` anywhere.
- `log.md`: operational, append-only, `type: log` frontmatter (FM0), pipe-format lines `- <UTC ISO> | <action> | <actor> | <ids or -> | <note>`; actor column kept deliberately (PRD LS4/NFR-5 audit trail).
- `kb show`: body-by-default read command; body rendered `# <title>` + blank line + **byte-for-byte body** + `---` terminator per document; raw stdout writes (no rich console); `--json` for strict parsing. `kb frontmatter --field` for single-field retrieval (bare value / TSV / typed JSON).
- `filter`/`search` stay separate commands sharing one selection-flag set (`--type/--status/--tag/--class/--where`); REF-accepting commands read refs from piped stdin; `--output paths` is the pipeline producer.
- Git: **no Git operations anywhere in the CLI** (user/skills own Git).
- `type` **authoritative** (FM0): every `*.md` carries `type`; class derivation `index`→INDEX, `raw-source|chat|feedback`→RAW(SOURCE|CHAT|FEEDBACK), `conventions|kb-config|health`→GOVERNANCE, `log`→operational, else→SYNTHETIC; `kb validate` enforces universal `type` + type↔location agreement. DocClass/RawClass are kept as derived enums for behavioral dispatch (challenged and re-affirmed).
- `kb init --force` overwrites **CLI-owned files only** (kb-config.json + the eight index.md); log.md and the two governance documents are create-if-missing, never overwritten.
- Output ordering: alphabetical by relative path.

## 7. Known open threads (candidates for future sessions)

- `kb ingest` spec (next): master design bullets exist — adapters registry (file/stdin/clipboard), verbatim-body normalization, `--about` mandatory+validated for feedback, non-text originals copied alongside a generated `.md` stub, filename slugification, directory invariant (create dir → create its index.md), `ingested` log entry, malformed-file guard on id allocation. Open details to settle in-session: adapter interface shape, clipboard mechanism, filename collision handling, index.md refresh scope on ingest, exact RawFrontmatter validation timing.
- `kb show`'s own spec (the `---` terminator is a convention, not a parse boundary — JSON is the strict path; needs stating in its spec with a round-trip AC).
- `kb validate` spec: finding-code table must consolidate every check accumulated in 00-shared/master design (FM0 universal type, type↔location, DG2/DG5, ids, tags, supersedes, index staleness?).
- Folder `description` customization gap: index.md is read-only, so a human currently has no way to set a folder description — deliberate; revisit with a small command if needed.
- AC22 in kb-init uses `E_INIT_IO` for wrong-kind occupied paths rather than a dedicated code — flagged as a judgment call.
- PRD open questions OQ1–OQ5 remain open product-level.
- `kb init` implementation plan (writing-plans) not yet produced.

## 8. Working conventions with this human

- They review carefully and iterate: expect several rounds of targeted change requests per spec; apply exactly, keep every document consistent, commit per logical change (imperative subject, requirement ids like "CLI-8", "AC7" in the body where relevant, `Co-Authored-By: Claude`).
- They sometimes edit the docs directly between sessions (e.g. the index.md listing format, `kb-config.json` rename) — **re-read files at session start; never assume this handover or memory is current**.
- Ask before deciding anything user-visible (flag semantics, formats, naming); decide-and-flag for internal judgment calls, stating the reversal path.
- Simplicity requests are real: when they say "don't worry about X for now," remove X cleanly and record it in Out of scope rather than leaving vestiges.
- Tests: one AC = one test, `test_ac<NN>_<slug>`, Typer `CliRunner`, tmp_path fixtures, no subprocesses in unit tests.

## 9. Kickoff instruction for a new session

Given this document, the next session should:
1. Read [00-shared.md](specs/commands/00-shared.md), [kb-init.md](specs/commands/kb-init.md) (as the template), the target command's section in the [master design](superpowers/specs/2026-07-13-kb-cli-design.md), and the relevant PRD requirements.
2. Run the §4 process: clarifying questions (one at a time) on the genuinely open details listed in §7 for that command, then sectioned design presentation, then write `docs/specs/commands/kb-<command>.md`, self-review, and hand to the human for the review gate.
3. Update 00-shared §7 (models introduced), the master design, and the PRD wherever the new spec sharpens or changes behavior — then verify consistency by grepping across all five documents before declaring done.
