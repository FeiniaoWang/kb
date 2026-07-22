# AGENTS.md — guide for coding agents

This repo builds the **`kb` CLI**: the deterministic toolset of the KB Skill Suite (shared project knowledge base, Markdown + YAML in Git). Skills (the judgment layer) come later and live outside this codebase's current scope.

## Authoritative documents (read in this order)

| Document | Role |
|---|---|
| [docs/prd.md](docs/prd.md) | **The root and single source of truth** (v0.5). All specs, plans, and code derive from it; decisions and their rationale live in its §6 "decision and rationale" passages, and Appendix C is the normative vocabulary. Requirement ids like CLI-6, DG5, FM1 come from here |
| [docs/dev-brief-prd-v0.5.md](docs/dev-brief-prd-v0.5.md) | What changed in PRD v0.5, the implementation impact, and the suggested execution order |
| [docs/specs/commands/00-shared.md](docs/specs/commands/00-shared.md) | Normative cross-command contracts: root discovery, exit codes, output/JSON, pipelines, scan, id grammar, **core data models**, log format, help-text and testing conventions |
| [docs/specs/commands/kb-<command>.md](docs/specs/commands/) | Per-command contract specs. **Implementation context for a command = its spec + 00-shared.md + the PRD requirements it cites** |
| [docs/superpowers/specs/2026-07-13-kb-cli-design.md](docs/superpowers/specs/2026-07-13-kb-cli-design.md) | Master design and decision record for all commands (historical; predates v0.5) |

Precedence when documents disagree: **PRD > command spec > 00-shared.md > master design.** The specs are the detailed contracts you implement against, but they *derive from* the PRD — where a spec contradicts PRD v0.5 (the existing specs predate it; the dev brief lists the known deltas), the PRD wins and the spec must be corrected in the same change. If you must deviate from a spec for any other reason, update the spec in the same change and say so — specs are normative, not descriptive. Do **not** recreate `CONTEXT.md`, `docs/adr/`, or `docs/HANDOVER.md` — they were deliberately consolidated into the PRD and deleted; new decisions are recorded in the PRD directly.

## Package layout

The top-level layout is fixed — do not restructure:

```
kb/                       (this repo; package name `kb`, console script `kb`)
├── pyproject.toml        entry point: kb = "kb.cli.app:app"
├── src/kb/
│   ├── core/             deterministic KB application logic: scan, query, graph, validate, ids, ingest, models, …
│   └── cli/              Typer commands, renderers, and process-environment input adapters
└── tests/                pytest; fixtures build throwaway KBs in tmp_path
```

The internal file/folder structure **within** `src/kb/core/` and `src/kb/cli/` is **not fixed** — organize modules however makes the most sense as the implementation grows (split, merge, or rename files freely).

Layering rule: `core/` is delivery-independent application logic. It may read and write the discovered KB filesystem, but it contains no Typer, printing, process exit, process-global standard-stream access, or process-launching calls. Concrete acquisition of user-supplied external files, stdin, and clipboard contents belongs to adapters in `cli/`; those adapters pass explicit bytes and provenance metadata through core-owned Pydantic models. Typer callbacks parse arguments, orchestrate prepare → acquire → execute, render output, and map failures to exit codes. This layering rule is normative; the module breakdown inside each layer is a developer decision.

## Invariants (never violate)

- **Scan on demand, no stored index.** Ids live in document frontmatter; every invocation rebuilds the id→path map. Never introduce a persistent index or cache without a spec change.
- **Exit codes:** `0` success / `1` findings or reference failures / `2` usage or environment errors.
- **Output:** compact plain text by default; every command supports `--json` (`{"ok": true, ...}` / `{"error": {"code", "message"}}`). JSON fields are added, never renamed or removed.
- **Frontmatter handling** preserves key order and unknown keys (FM2). Malformed files never crash query commands.
- **`type` is mandatory and authoritative (OKF).** Every `*.md` (including `index.md` → `type: index` and `log.md` → `type: log`) carries a `type` field. `DocClass`/`RawClass` derive from `type`, never from path (`index`→INDEX; `raw-source|chat|feedback`→RAW; `charter|conventions|kb-config|health`→GOVERNANCE; `log`→operational; else→SYNTHETIC). Location must agree with `type`; `kb validate` enforces universal `type` presence and `type`↔location agreement. The charter (`governance/charter.md`, id `GOVERNANCE-CHARTER`) is the third scaffolded governance document (PRD §6.1).
- **Id allocation** is max+1 per prefix from the scan, and is refused while malformed files exist (an unparsed file could hide an id). Ids are canonical six-digit zero-padded (`KB-000042`; `KB-0000042` is invalid) and **never change**: `kb revise` mutates in place preserving the id; only `kb create --supersedes` replaces a document (and is the only thing that ever sets status `superseded` — `kb revise` owns every other status transition, PRD LS5).
- **Write/read surface is MECE (PRD §7.1) — respect the retirements.** Never implement `kb frontmatter` (CLI-3) or `kb resolve` (CLI-5) as separate commands: they are `kb show` projections (`--output frontmatter|full|path`, `--field`; a `resolve` alias at most). `kb filter` has no derivation predicates (graph selection is `kb links` only, and it returns paths/frontmatter by default). Deterministic reports (drift/impact/orphans) belong to `kb report` (CLI-15), not to skills. Retired CLI numbers are never reused.
- **Acyclicity is scoped to `derived_from`.** Cycle detection runs on provenance only; associative links (`links:` frontmatter, PRD §6.9) may legally form cycles, live on synthetic documents only, and their type vocabulary comes from `kb-config.json`. Every parent-appending write (`kb revise --add-parent`) must run the DG2 cycle check pre-write.
- **`timestamp` vs `last_human_touch`:** every mutation advances `timestamp`; `last_human_touch` advances only on explicitly human-confirmed writes (expect a flag — the CLI never guesses). Instruction-authorized automatic consolidations advance `timestamp` only, so `kb report drift` catches them.
- **Never hardcode validate finding-code counts** (in code, tests, or docs) — the code table grows with the schema; enumerate from the source of truth instead.
- **Use the PRD Appendix C glossary terms** in identifiers, help text, and JSON fields for new work: *revision* (not version), *consolidation* (not merge/auto-update), *human-directed* (not human-authored), *purpose document*, *building block*, *charter*. No renaming sweeps of existing code; apply on touch.
- **Determinism:** no LLM judgment in this CLI, no content synthesis, no network calls. Adapters normalize and file; they never invent content.
- **Git-agnostic:** no command runs `git` or inspects Git state — the CLI only reads and writes files. The KB lives in Git, but initializing/committing/branching is the user's or a skill's job.
- **Directory invariant:** every directory has an `index.md` (`DocClass INDEX`, path-addressed, no id); any command that creates a directory also creates its `index.md`. No `.gitkeep` files. `index.md` files are **CLI-maintained and read-only** for humans/agents — never hand-edited; `kb index` regenerates their listing bodies.
- **Data models are Pydantic 2.x `BaseModel`s** (validation + typed access; see 00-shared.md §7). Frontmatter models set `extra="allow"` to preserve unknown keys (FM2); the generic `Frontmatter` wraps an insertion-ordered dict so raw YAML round-trips without reordering. Pydantic validates parsed structures — it does not do file I/O (PyYAML parses frontmatter, stdlib `json` parses `kb-config.json`).
- Dependencies stay `typer`, `PyYAML`, and `pydantic` (2.x) only. Adding another requires a spec change.

## Working conventions

- **Toolchain:** Python ≥ 3.14, managed with `uv` — `uv run pytest`, `uv add <pkg>`, `uv run kb ...`.
- **Tests:** pytest; CLI exercised via Typer's `CliRunner` (no subprocesses). One acceptance criterion = one test, named `test_ac<NN>_<slug>` matching the spec's AC table. A command is done only when every AC in its spec has a passing test.
- **Help text** wording is normative per spec §3 sections; tests assert substrings, never layout.
- **Implementation order** (dev brief §4): `init`, `create`, and `validate` are implemented; **finish `ingest` (AC24–AC50) first**, then extract the shared write pipeline (create/ingest currently duplicate it; `revise` must not become a third copy — move `slug()` out of `ingest.py` while there), then the v0.5 schema extensions spec-first (config link-type vocabulary, `links`/`pending_upstream` model keys, `charter` scaffold, new validate findings), then `kb revise` (spec → plan → code), then the read/graph/report commands built directly to the MECE surface. Core models are introduced by the command that first needs them (00-shared.md §7 table).
- Commit specs and code separately when both change; reference the requirement ids (e.g. "CLI-11", "AC7") in commit messages where they apply.
