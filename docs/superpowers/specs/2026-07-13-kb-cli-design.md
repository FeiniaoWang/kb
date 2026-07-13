# Design: `kb` CLI — deterministic toolset for the KB Skill Suite

**Date:** 2026-07-13
**Source:** [docs/prd.md](../../prd.md) §7.1 (CLI-1…CLI-12), §6 information model
**Status:** Approved design, pre-implementation

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Scope of first build | Full CLI including ingest (all of PRD §7.1), not just PRD Phase 1 groups. The whole deterministic layer ships before skill work begins. |
| Id allocation | Sequential per prefix (`KB-0042` style), assigned max+1 at creation. Merge collisions from parallel branches are caught by `kb validate` in CI; fix-up happens before merge. |
| Id↔path index | No stored index. Every invocation scans the KB and reads frontmatter; ids live in the files. Zero staleness, zero merge conflicts, honors NFR-1. A gitignored cache may be added later only if scanning ever becomes slow. |
| Output rendering | Compact plain text by default (YAML-ish frontmatter blocks, path lists); `--json` on every command for structured output with stable schemas. |
| Architecture | Layered: pure core library + thin Typer CLI shell (Approach A below). |

### Approaches considered

- **A — Core library + thin CLI (chosen).** `kb/core/` holds pure functions over a per-invocation `KB` object; `kb/cli/` only parses args and renders. Unit tests target core directly; best fit for CLI-12's quality bar.
- **B — Command-centric modules.** Each command walks/parses files itself. Rejected: duplicated scanning logic, CLI-only testability.
- **C — Persistent index (SQLite/daemon).** Rejected: contradicts scan-on-demand and NFR-1; solves a performance problem that doesn't exist at KB scale.

## Package layout

```
kb/                       (this repo; package name `kb`, console script `kb`)
├── pyproject.toml        entry point: kb = "kb.cli.app:app"
├── src/kb/
│   ├── core/
│   │   ├── model.py      Document, Frontmatter, KB dataclasses; id patterns
│   │   ├── scan.py       repo discovery + frontmatter scan → KB object
│   │   ├── query.py      filter / search / frontmatter extraction
│   │   ├── graph.py      links, transitive closure, depth, cycle detection
│   │   ├── validate.py   all FM/DG/LS mechanical checks → list of Findings
│   │   ├── ids.py        id allocation (max+1 per prefix), id↔path resolution
│   │   ├── ingest.py     adapters (file/stdin/clipboard) → raw/ documents
│   │   ├── housekeeping.py  index.md generation, log.md append, scaffold
│   │   └── mv.py         move/rename + body-link rewriting
│   └── cli/
│       ├── app.py        Typer app; one thin command module per group
│       └── render.py     text and JSON renderers for core's return types
└── tests/                pytest; fixtures build throwaway KBs in tmp_path
```

## Shared foundations (all commands)

- **Root discovery.** Walk up from cwd for a `.kb` marker file (written by `kb init`; contains schema version). Overrides: `--kb PATH` flag, `KB_ROOT` env var. No marker found → clear error, exit 2.
- **The scan.** One pass per invocation builds the `KB` object: every `*.md` under `raw/`, `synthetic/`, `governance/` is parsed for frontmatter. Bodies are lazily loaded only when a command needs them (`search`, `mv`). Frontmatter parse failures do not crash query commands; the document is excluded from results, noted on stderr, and fully reported by `validate`.
- **Output modes.** `--output paths|frontmatter|full` (default `frontmatter`) on commands that return documents; `--json` on every command. JSON schemas are stable within a major version (NFR-9).
- **Exit codes.** `0` success / checks pass; `1` findings or verification failures (CI-friendly); `2` usage or environment errors.
- **Document references.** Every command accepts an id (`KB-0042`) or a path wherever a document is named (spelled `REF` below).
- **Pipelines.** Commands that accept `REF...` (`filter`, `frontmatter`, `resolve`, `validate`) also read newline-separated ids/paths from stdin when stdin is piped and no refs are given on the command line. Combined with `--output paths`, commands compose Unix-style: `kb search "user feedback" --output paths | kb filter --class raw`, or `kb links KB-0007 --reverse --transitive --output paths | kb validate`. When a command receives a candidate set this way, it operates within that set instead of the whole KB.
- **Dependencies.** `typer`, `PyYAML` only. Frontmatter is parsed with a small wrapper that preserves key order and unknown keys (FM2). Pure-Python search; no ripgrep or other external binaries.
- **Errors.** Human message on stderr + documented exit code; under `--json`, errors are structured: `{"error": {"code": ..., "message": ...}}`.

## Command group: Query

**Why `filter` and `search` are separate commands.** They answer different questions with different result types: `filter` answers "which documents have these properties?" from frontmatter alone (guaranteed zero body-reading cost — the survey tool) and returns a document set; `search` answers "where does this text appear?" by reading bodies and returns locations within documents (path + line + snippet). Keeping them separate keeps each command's `--json` schema stable (NFR-9) and encodes the survey-before-reading discipline structurally — the same reason Unix separates `find` and `grep`, composed via pipes.

Both commands accept one **shared selection-flag set** — `--type`, `--status`, `--tag`, `--class`, `--where` — implemented once in `core/query.py` and documented once. `filter` is selection; `search` is selection + body scan.

### `kb filter` (CLI-1)

```
kb filter [--type T]... [--status S]... [--tag G]... [--derived-from REF]
          [--class raw|synthetic|governance] [--where key=value]...
          [--output paths|frontmatter|full] [--json]
```

- Repeated flags of the same kind OR together; different kinds AND together.
- `--where` matches any frontmatter key, including extension keys: scalar equality, or containment when the field is a list.
- `--derived-from REF` matches **direct** parents only; transitive impact belongs to `kb links --reverse --transitive`.
- Results sorted by id for stable, diffable output.

### `kb search` (CLI-2)

```
kb search QUERY [--type T]... [--status S]... [--tag G]... [--class C] [--where key=value]...
          [--regex] [--context N] [--limit N] [--output snippets|paths] [--json]
```

- Default: case-insensitive substring match over body + `title` + `description`; `--regex` opts into regex matching.
- The shared selection flags narrow the searched set on frontmatter **before** bodies are read — the single-command form of "search within a slice" (`kb search "user feedback" --class raw`), preferred over piping when one command can express it.
- Each hit prints path, id, and ±`N` lines of context (default 2). Snippets only, never whole documents — this is the survey tool (G8/NFR-4).
- `--output paths` emits matching paths one per line for pipelines (see Pipelines under shared foundations); snippet output is not intended to be piped.
- A candidate set on stdin restricts the search to those documents (`kb filter --class raw --output paths | kb search "user feedback"`).

### `kb frontmatter` (CLI-3)

```
kb frontmatter REF... [--json]
```

- Prints each document's full frontmatter, nothing else. Any number of ids/paths.
- Companion to `filter --output paths`: cheap bulk metadata for skills.

## Command group: Graph

### `kb links` (CLI-4)

```
kb links REF [--reverse] [--transitive] [--depth] [--output ...] [--json]
```

- Default: direct parents (the `derived_from` set).
- `--reverse`: direct children (documents whose `derived_from` includes REF).
- `--transitive`: full ancestry; with `--reverse`, the full downstream impact set (the CS3 propagation input).
- `--depth`: annotate each listed document with distance-from-evidence (DG4), computed as the longest path to a raw/governance ancestor.
- Text output for transitive queries is indented by level; JSON includes explicit edge lists so agents can reconstruct the tree.

### `kb resolve` (CLI-5)

```
kb resolve REF... [--json]
```

- Id → path and path → id, one line per input.
- Unknown ref: error on stderr, exit 1, but remaining inputs still resolve (batch-friendly).

## Command group: Integrity

### `kb validate` (CLI-6)

```
kb validate [REF...] [--json] [--strict]
```

No args → whole KB. With refs → scoped to those documents, plus graph checks that are inherently global. Every finding carries a stable code, severity (`error`/`warning`), document, and message.

| Check group | Checks |
|---|---|
| Schema (FM1–FM3) | frontmatter parses; mandatory fields per class (synthetic full schema; raw reduced schema: `id`, `type`, `ingested_at`, `origin`, `about` for feedback); legal `status` values; `description` ≤ 2 sentences (heuristic sentence count → severity `warning`, never an error); timestamps parse as ISO-8601; unknown keys preserved and never flagged |
| Tags (FM1b) | every `tags` value appears in the governance tag vocabulary |
| Ids | globally unique; format matches governance-configured prefixes; duplicate detection catches sequential-allocation collisions after merges |
| Links | every `derived_from`, `supersedes`, `about` value resolves to an existing id |
| Graph (DG2) | acyclic; every chain terminates at raw or governance documents |
| Session parentage (DG5) | every synthetic document has ≥1 `raw/chats/` record among its parents |
| Lifecycle (LS) | any document named in another's `supersedes` has status `superseded`; `supersedes` targets exist; `last_human_touch` ≤ `timestamp` (warning) |

- Errors → exit 1 (the CI gate). Warnings → exit 0 unless `--strict`.
- Strictly LLM-free (NFR-3). Semantic review (contradictions, staleness judgment, instruction conflicts) belongs to the `kb-lint` skill, not this command.

### `kb mv` (CLI-7)

```
kb mv SRC DEST [--json]
```

- Moves/renames a document or directory. Identity is untouched — ids live in the files.
- Rewrites relative body links in the moved document **and** in every document that links to it.
- Regenerates affected `index.md` files and appends a `moved` entry to `log.md`.

## Command group: Ingest

### `kb ingest` (CLI-8)

```
kb ingest --from file|stdin|clipboard --class source|chat|feedback
          [--about REF] [--title T] [--origin O] [PATH_OR_INPUT]
```

- Assigns the next sequential id with the class's prefix (`RAW-` / `CHAT-` / `FEED-` by default; prefixes configurable in `governance/kb-config.md`).
- Writes a normalized Markdown file into `raw/sources/`, `raw/chats/`, or `raw/feedback/` with the reduced frontmatter (`id`, `type: raw-source|chat|feedback`, `ingested_at`, `origin`, plus `about` for feedback).
- Body is copied **verbatim** — adapters normalize and file; they never synthesize (per CLI-8).
- `--about` is mandatory for `--class feedback` and is validated against existing ids.
- Non-text input: the original file is copied alongside; a generated `.md` stub with the frontmatter becomes the citable form.
- Target filename: slugified `--title`, else the source filename.
- Appends an `ingested` entry to `log.md`.
- Adapters register in a small registry (name → callable returning normalized text + origin metadata) so later adapters (Slack, mail, ticketing) are additive and require no skill changes.

## Command group: Housekeeping

### `kb init` (CLI-11)

```
kb init [PATH] [--force]
```

- Scaffolds the Appendix A layout: `raw/{sources,chats,feedback}/`, `synthetic/`, `governance/` (starter `kb-config.md` with commented examples of type vocabulary, tag vocabulary, id prefixes), root `index.md`, `log.md`, and the `.kb` marker containing the schema version.
- Idempotent: on an existing KB it creates only what's missing; never overwrites without `--force`.
- Runs `git init` if the target is not already inside a Git repository.
- Prints a summary of what was created. The steward interview (INIT-2) is the `kb-init` skill's job; this command only scaffolds.

### `kb index` (CLI-9)

```
kb index [--check] [--json]
```

- Regenerates every directory's `index.md` from frontmatter: per document — id, title, status, and the verbatim ≤2-sentence `description` (FM1a), grouped by subdirectory.
- Generated files carry a "generated by `kb index` — do not edit" header.
- `--check`: exit 1 if any index is stale, writing nothing (for CI).

### `kb log` (CLI-10)

```
kb log ACTION [--doc REF]... [--actor NAME] [--note TEXT]
kb log --show [--limit N] [--json]
```

- Append mode writes one structured line to `log.md`: ISO date, action (`created`, `ingested`, `superseded`, `propagated`, `answered`, `moved`, …), actor, affected ids, note. Append-only.
- `ingest` and `mv` call it internally; skills invoke it for their own events.
- `--show` reads the log back, filtered and limited.

## Testing and quality (CLI-12)

- `pytest`. Fixtures build throwaway KBs in `tmp_path` via concise helpers (e.g. `make_doc(id, type, derived_from=[...])`).
- Core functions tested directly, without process spawning. Priority edge cases: graph cycles, diamond derivation, deep chains, dangling links; one test per `validate` finding code; ingest adapters with text/non-text/stdin inputs; `mv` link rewriting.
- CLI layer smoke-tested through Typer's `CliRunner`, including `--json` output schema stability.
- CI: `pytest` plus `kb validate` against a fixture KB.
- Versioning: semver starting at `0.x`; `kb --version` lets skills verify the minimum compatible version (NFR-9).

## Out of scope (this build)

- The `kb-*` skills themselves (next effort, after the CLI).
- Retrieval indexes, embeddings (NG6); access-control enforcement hooks (NFR-8) — the query layer will grow these later.
- Additional ingest adapters (Slack, mail, ticketing) — Phase 4.
- `kb renumber` or automated id-collision repair: v1 detects collisions via `validate`; repair is manual.
