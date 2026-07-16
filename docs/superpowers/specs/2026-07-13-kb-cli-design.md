# Design: `kb` CLI — deterministic toolset for the KB Skill Suite

**Date:** 2026-07-13
**Source:** [docs/prd.md](../../prd.md) §7.1 (CLI-1…CLI-13), §6 information model
**Status:** Approved design, pre-implementation

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Scope of first build | Full CLI including ingest and `kb create` (all of PRD §7.1), not just PRD Phase 1 groups. The whole deterministic layer ships before skill work begins — `kb create` is built with the core even though its driving skill (`kb-author`) is PRD Phase 3. |
| Id allocation | Sequential per prefix (`KB-000042` style, 6-digit zero-pad), assigned max+1 at creation. Merge collisions from parallel branches are caught by `kb validate` in CI; fix-up happens before merge. |
| Id↔path index | No stored index. Every invocation scans the KB and reads frontmatter; ids live in the files. Zero staleness, zero merge conflicts, honors NFR-1. A gitignored cache may be added later only if scanning ever becomes slow. |
| Output rendering | Compact plain text by default (YAML-ish frontmatter blocks, path lists); `--json` on every command for structured output with stable schemas. |
| Architecture | Layered: pure core library + thin Typer CLI shell (Approach A below). |
| Data models | Pydantic 2.x `BaseModel`s for validation and typed access; `extra="allow"` preserves unknown frontmatter keys (FM2). Pydantic validates parsed structures only — PyYAML/`json` do the file parsing. |

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
│   │   ├── model.py      Document, Frontmatter, KB, Config Pydantic models; id patterns
│   │   ├── scan.py       repo discovery + frontmatter scan → KB object
│   │   ├── query.py      filter / search / frontmatter extraction
│   │   ├── graph.py      links, transitive closure, depth, cycle detection
│   │   ├── validate.py   all FM/DG/LS mechanical checks → list of Findings
│   │   ├── ids.py        id allocation (max+1 per prefix), id↔path resolution
│   │   ├── ingest.py     adapters (file/stdin/clipboard) → raw/ documents
│   │   ├── create.py     synthetic document creation (id alloc + frontmatter emit + file)
│   │   ├── housekeeping.py  index.md listing maintenance, log.md append, scaffold
│   │   └── mv.py         move/rename + body-link rewriting
│   └── cli/
│       ├── app.py        Typer app; one thin command module per group
│       └── render.py     text and JSON renderers for core's return types
└── tests/                pytest; fixtures build throwaway KBs in tmp_path
```

## Shared foundations (all commands)

- **Root discovery.** Walk up from cwd for a `kb-config.json` file (written by `kb init`; holds project config and the schema version, and doubles as the root marker). Discovery is existence-based; a malformed config is a separate error, not "no KB found". Override: `--kb PATH` flag. No marker found → clear error, exit 2.
- **The scan.** One pass per invocation builds the `KB` object: every `*.md` in the tree is parsed for frontmatter, except `log.md` (operational; carries `type: log` for OKF conformance but is not a document). `index.md` files are included as `DocClass INDEX` documents (one per directory, path-addressed, no id). Bodies are lazily loaded only when a command needs them (`search`, `mv`). Frontmatter parse failures do not crash query commands; the document is excluded from results, noted on stderr, and fully reported by `validate`.
- **`type` is mandatory and authoritative (OKF).** Every `*.md` carries a `type` frontmatter field. `DocClass`/`RawClass` are derived from `type` (`index`→INDEX; `raw-source|chat|feedback`→RAW; `conventions|kb-config|health`→GOVERNANCE; `log`→operational; anything else→SYNTHETIC), never from path. Location must agree with `type`; `validate` flags mismatches and universal-`type` violations. See 00-shared.md §5.
- **Output modes.** `--output paths|frontmatter|full` (default `frontmatter`) on commands that return documents; `--json` on every command. JSON schemas are stable within a major version (NFR-9).
- **Exit codes.** `0` success / checks pass; `1` findings or verification failures (CI-friendly); `2` usage or environment errors.
- **Document references.** Every command accepts an id (`KB-000042`) or a path wherever a document is named (spelled `REF`; defined normatively in 00-shared.md §4).
- **Pipelines.** Commands that accept `REF...` (`show`, `filter`, `frontmatter`, `resolve`, `validate`) also read newline-separated ids/paths from stdin when stdin is piped and no refs are given on the command line. Combined with `--output paths`, commands compose Unix-style: `kb search "user feedback" --output paths | kb filter --class raw`, or `kb links KB-000007 --reverse --transitive --output paths | kb validate`. When a command receives a candidate set this way, it operates within that set instead of the whole KB.
- **Dependencies.** `typer`, `PyYAML`, `pydantic` (2.x) only. Data models are Pydantic 2.x `BaseModel`s (validation + typed access); frontmatter models use `extra="allow"` and the generic `Frontmatter` wraps an insertion-ordered dict to preserve key order and unknown keys (FM2). Pydantic validates parsed structures, not files — PyYAML parses frontmatter, stdlib `json` parses config. Pure-Python search; no ripgrep or other external binaries.
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
kb frontmatter REF... [--field KEY]... [--json]
```

- Prints each document's full frontmatter, nothing else. Any number of ids/paths.
- `--field KEY` (repeatable) retrieves specific frontmatter fields instead of the full block. Single doc + single field → the bare value alone (scripting-friendly: `kb frontmatter KB-000042 --field status` → `current`). Multiple docs and/or fields → TSV lines `<id>\t<key>\t<value>`, list values comma-joined. Missing key → empty value plus a stderr warning. `--json` returns properly typed values (`{"KB-000042": {"status": "current"}}`).
- Companion to `filter --output paths`: cheap bulk metadata for skills.

### `kb show` (new — CLI-only read path)

```
kb show REF... [--output body|full|frontmatter] [--json]
```

- Prints documents by id or path. Default `body`: first line `# <title>` (frontmatter `title`; falls back to `# <id>` for raw documents, whose reduced schema has no title), a blank line, the body verbatim, then a terminator line containing exactly `---`. The terminator follows **every** document — single-doc and pipeline output parse identically, and truncated streams stay detectable.
- **Markdown preservation.** The body between heading and terminator is byte-for-byte the file's body: no reflowing, no markup interpretation, no escaping, trailing whitespace intact. Implementation note: document content MUST be written to stdout raw (e.g. `sys.stdout.write` in the render layer), never through a rich/Typer console that could interpret `[...]` as markup or rewrap lines. Under `--json`, the body is a plain string field and round-trips exactly.
- `full` prepends the frontmatter block; `frontmatter` aliases `kb frontmatter` for symmetry.
- The **only** sanctioned way for skills to read document content — agents never open KB files directly. Routing all reads through the CLI keeps the NFR-8 access-control hooks effective and completes the CLI-served progressive-disclosure ladder: `index` → `filter`/`frontmatter` → `search` snippets → `show`.
- Accepts refs from stdin (pipelines): `kb filter --type coding-spec --output paths | kb show`.

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
| Universal `type` (FM0/OKF) | **every** `*.md` (including `index.md` and `log.md`) carries a `type` frontmatter field — missing `type` is an error |
| Type↔location agreement | a document's directory matches its authoritative `type` (`index`→`index.md`; `raw-*`→`raw/<subclass>/`; governance types→`governance/`; synthetic types→`synthetic/`) — mismatch is an error |
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
- Regenerates the affected `index.md` listings (source and destination directories) and appends a `moved` entry to `log.md`.

## Command group: Ingest

### `kb ingest` (CLI-8)

```
kb ingest --class source|chat|feedback --from file|stdin|clipboard [SOURCE]
          [--dest SUBDIR] [--about REF] [--title T] [--origin O] [--actor NAME]
```

- `SOURCE` (positional) is the source file path — required iff `--from file`, forbidden otherwise. `--dest` names a subdirectory relative to the class directory (`--dest api` → `raw/sources/api/`).
- Assigns the next sequential id with the class's prefix (`RAW-` / `CHAT-` / `FEED-` by default; prefixes configurable in root `kb-config.json`).
- Writes a normalized Markdown file into `raw/sources/`, `raw/chats/`, or `raw/feedback/` with the reduced frontmatter (`id`, `type: raw-source|chat|feedback`, `ingested_at`, `origin`, an always-written `title`, plus `about` for feedback).
- Body is copied **verbatim** — adapters normalize and file; they never synthesize (per CLI-8). The only normalization: line endings → LF, exactly one trailing newline.
- **Pre-flight, then write:** every check (malformed-file guard, flag pairing, `--about` resolution, input acquisition, id/filename computation) completes before the first byte is written; a failed ingest leaves the KB untouched.
- `--about` is mandatory for `--class feedback` (forbidden otherwise), accepts a REF, and must resolve to a document carrying an id; the canonical id is stored.
- Non-text input (a `--from file` input that does not decode as UTF-8): the original file is copied alongside; a generated `.md` stub with the frontmatter becomes the citable form.
- Target filename: slugified `--title`, else the source filename stem, else the lowercased id (stdin/clipboard without `--title`). Name collision → `-<lowercased id>` suffix; nothing existing is ever overwritten.
- Clipboard adapter shells out to platform tools (`pbpaste`; `wl-paste`/`xclip`; `powershell Get-Clipboard`) — no extra dependency.
- If the target subdirectory does not exist, it is created **together with its `index.md`** (`DocClass INDEX`), per the directory invariant (00-shared). Ingest refreshes the target directory's `index.md` and, when directories were created, the nearest pre-existing ancestor's — global freshness stays `kb index`'s job.
- Appends an `ingested` entry to `log.md`.
- Adapters register in a small registry (name → callable returning raw bytes + origin metadata) so later adapters (Slack, mail, ticketing) are additive and require no skill changes.

## Command group: Authoring

### `kb create` (CLI-13 — CLI-only synthetic write path)

```
kb create --type T --title TITLE --description DESC
          [--dest SUBDIR] [--derived-from REF]... [--status draft|current]
          [--tag G]... [--supersedes REF] [--instructions TEXT]
          [--body-file FILE|-] [--actor NAME] [--json]
```

`kb create` is the deterministic **write path for synthetic documents** — exactly what `kb ingest` is to `raw/`. It closes the gap where synthetic id allocation and frontmatter emission had no command and would otherwise fall to skill judgment, violating CLI-12/NFR-3 and §5.2. Agents never hand-write synthetic files; content and metadata come in as arguments, and id allocation plus the frontmatter schema stay CLI-authoritative (mirrors the CLI-only *read* discipline in 00-shared §5).

- **Id.** Assigns the next sequential id with the synthetic prefix (`KB-` by default; configurable in `kb-config.json`) via the same `next_id` allocator `kb ingest` uses. The malformed-file guard applies (00-shared §6): it refuses to allocate while `KB.malformed` is non-empty (exit 2), so an invisible id can never be reallocated.
- **Frontmatter.** Writes the full synthetic schema (FM1): `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`, plus optional `tags`, `supersedes`, `instructions`. `timestamp` and `last_human_touch` are both set to the creation instant (ISO-8601 UTC) — creation is a human-confirmed act, so the two coincide at birth (LS2).
- **`--status`** defaults to `draft`; the `kb-author` skill passes `--status current` when the human accepts at creation (LS1). Only `draft` and `current` are legal birth states; `superseded`/`retired` are lifecycle transitions, not creation values.
- **`--derived-from`** (repeatable) — **at least one is required** (DG1); each REF resolves through the scan and is stored as the canonical id. An unresolved parent aborts before any write (`E_REF_UNRESOLVED`, exit 2). **DG5 (a `raw/chats/` session-record parent) is deliberately *not* enforced here:** the session record is typically archived while finalizing the document, and the recommended flow ingests it first, then supplies its id among `--derived-from` (`kb ingest --class chat …` → `kb create … --derived-from CHAT-000027`). DG5 stays a `kb validate` check — the single authoritative enforcement point.
- **`--type`** must be a synthetic type. A reserved type (`index`, `log`, `raw-source`, `chat`, `feedback`, `conventions`, `kb-config`, `health`) is rejected (`E_TYPE_RESERVED`, exit 2). A type absent from `kb-config.json`'s `types` is **allowed** — the vocabulary is open (INIT-2) and authors may name new types (AUT-1) — but emits a stderr warning so the steward can add it.
- **`--description`** over two sentences → stderr warning only (never blocks), matching `kb validate`'s heuristic severity.
- **`--supersedes REF`** (optional) records the replacement link and, in the same atomic write, flips the superseded document's `status` to `superseded` and updates its `timestamp`/`last_human_touch` — so the KB never lands in the LS-invalid state "a `supersedes` target is not marked `superseded`". Transitive propagation to that document's descendants is a skill concern (CS3/`kb-ingest`/`kb-author`), not this command's.
- **Body.** Read from `--body-file FILE` (or `-` for stdin); omitted → an empty body, a legitimate `draft` stub the author fills. The body is written verbatim with the ingest normalization (LF line endings, exactly one trailing newline). In-place body edits after creation are a revision concern (see Out of scope).
- **Filename.** Slugified `--title`, else the lowercased id; collision → `-<lowercased id>` suffix; nothing existing is ever overwritten. `--dest SUBDIR` files under `synthetic/<subdir>/`; a missing subdirectory is created together with its `index.md` (directory invariant). A `--dest` that escapes `synthetic/` → `E_DEST_INVALID` (exit 2).
- **Pre-flight, then write** (as `kb ingest`): every check — malformed guard, flag pairing, type legality, ref resolution, id/filename computation — completes before the first byte is written; a failed `kb create` leaves the KB untouched. The write is atomic across every touched file (the new document, any superseded document, `index.md`, `log.md`).
- Refreshes the target directory's `index.md` (and any created ancestors'); global freshness stays `kb index`'s job. Appends a `created` entry to `log.md` (including the superseded id when `--supersedes` is used).

Error codes: `E_TYPE_RESERVED`, `E_NO_PARENTS` (zero `--derived-from`), `E_REF_UNRESOLVED`, `E_DEST_INVALID`, plus the shared `E_NO_KB` / `E_CONFIG_INVALID` and the malformed-file guard (00-shared §6).

## Command group: Housekeeping

### `kb init` (CLI-11)

```
kb init [--root PATH] [--force]
```

- Run from the folder to become the KB root; scaffolds the current directory by default (`--root` targets a different folder, resolved to an absolute path).
- Scaffolds the Appendix A layout: `raw/{sources,chats,feedback}/`, `synthetic/`, `governance/`, root `index.md`, `log.md`, and root `kb-config.json` — clean JSON config (starter type/tag vocabulary and id prefixes) that also holds the schema version and marks the KB root. (Deviation from PRD Appendix A, which nested `kb-config` under `governance/`: moved to root so it can double as the discovery marker.) It also scaffolds two governance documents with reserved fixed ids — `governance/conventions.md` (`GOVERNANCE-CONVENTIONS`) and `governance/kb-config.md` (`GOVERNANCE-KB-CONFIG`, the human-readable field reference for `kb-config.json`) — so agents can read them by known id.
- No nesting guard: `kb init` never checks whether the target sits inside an existing KB; a nested root is allowed, and discovery takes the closest ancestor `kb-config.json`.
- Every directory gets an `index.md` (`DocClass INDEX`, CLI-maintained, read-only for humans/agents) — eight at init (root, `governance/`, `governance/templates/`, `raw/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, `synthetic/`). No `.gitkeep` files; each `index.md` keeps its directory non-empty.
- Idempotent: on an existing KB it creates only what's missing; never overwrites without `--force`.
- **Git-agnostic** (whole CLI): `kb init` and every other command only read and write files; they never run `git` or inspect Git state. The KB lives in Git (NFR-1/NFR-7), but initializing and managing the repository is the user's or a skill's job.
- Prints a summary of what was created. The steward interview (INIT-2) is the `kb-init` skill's job; this command only scaffolds.

### `kb index` (CLI-9)

```
kb index [--check] [--json]
```

- `index.md` is a first-class **INDEX document** (frontmatter `type: index` + `description`), one per directory, **maintained only by the CLI and read-only for humans/agents**. `kb index` creates a starter `index.md` in any directory that lacks one and regenerates each directory's listing body; the frontmatter `description` is set at creation and carried forward.
- The generated body holds one `- <name> — <its description>` line per immediate child (subdirectories then child documents, sorted), sourced from each child's `description` (the FM1a survey-on-index property).
- `--check`: exit 1 if any directory lacks an `index.md` or any listing is stale, writing nothing (for CI).

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
- A synthetic **mutation** command (in-place revision write path). `kb create` covers document *birth*; editorial edits to an existing synthetic document's body/frontmatter, adding a session-record parent after creation (AUT-8), and status changes short of supersession have no deterministic command yet. v1 expresses semantic revision as supersession (`kb create --supersedes`); a dedicated `kb set`/`kb revise` is deferred (PRD OQ6).
