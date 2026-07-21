# `kb` CLI — Shared Foundations (normative)

**Status:** Living reference. Every command spec in this directory assumes this document.
**Implementation context rule:** to implement or validate any `kb` command, an agent reads exactly two files — this one and the command's own spec (`kb-<command>.md`).
**Sources:** [PRD §7.1](../../prd.md), [master design 2026-07-13](../../superpowers/specs/2026-07-13-kb-cli-design.md). Where this document is more specific, this document wins.

**Git-agnostic (applies to every command).** No `kb` command runs `git` or inspects Git state; the CLI only reads and writes files. The KB is stored in Git (NFR-1/NFR-7), but initializing, staging, committing, and branching the repository are the user's or a skill's responsibility.

**Directory invariant (applies to every command).** Every directory in the KB contains an `index.md` (`DocClass INDEX`). Any command that creates a directory MUST also create that directory's `index.md` in the same operation (e.g. `kb ingest` creating a new `raw/` subdirectory). There are no `.gitkeep` files — the `index.md` keeps each directory non-empty. `index.md` files are **maintained only by the CLI and are read-only** for humans and agents (they read them, never hand-edit them); `kb index` regenerates their bodies.

## 1. Root discovery

Every command except `kb init` locates the KB root before doing anything:

1. `--kb PATH` flag, if given.
2. Else walk up from cwd (inclusive) toward the filesystem root, looking for a directory containing a `kb-config.json` file. The **closest** such ancestor is the root (stop at the first hit); only when none is found does the walk reach the filesystem root and conclude there is no KB.

Failure: `E_NO_KB` — message `not inside a knowledge base (no kb-config.json found); run 'kb init' or pass --kb` on stderr, exit 2 (`--json`: the §3 error envelope with that code). This same failure applies when the root was supplied explicitly via `--kb PATH` but that directory contains no `kb-config.json`: an explicit path is still subject to existence-based discovery, so a config-less path falls through to this generic "no KB found" error (exit 2) rather than a path-specific message.

`kb-config.json` at the KB root is both the **root marker** and the project configuration. Discovery is **existence-based**: a directory is a KB root iff it contains a file named `kb-config.json`. Whether that file parses is a separate concern — a malformed config is reported as `E_CONFIG_INVALID` (exit 2) by the command that loads it, never as "no KB found".

The file is a JSON object. Minimum content written by `kb init`:

```json
{
  "schema": 1,
  "types": [],
  "tags": [],
  "id_prefixes": { "synthetic": "KB", "source": "RAW", "chat": "CHAT", "feedback": "FEED" },
  "propagation_auto_safe": []
}
```

`schema` is the KB layout schema version — a **reserved, tooling-owned** key, not hand-edited by stewards. Commands MUST refuse (exit 2, `E_SCHEMA_UNSUPPORTED`) a schema newer than they know. The file carries no comment/annotation keys; unknown keys are ignored by `load_config`. Field-by-field documentation for `kb-config.json` lives in the governance document `governance/kb-config.md` (id `GOVERNANCE-KB-CONFIG`), not inside the data file.

## 2. Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. For check-style commands: no findings at error severity. |
| `1` | Findings, verification failures, or unresolvable references (partial batch failures included). |
| `2` | Usage errors, environment errors (no KB root, unsupported schema, I/O failures). |

## 3. Output conventions

- Default output is compact plain text for humans and agents.
- Commands returning document sets support `--output paths|frontmatter|full` (default `frontmatter`). `paths` prints one KB-root-relative path per line.
- Every command supports `--json`. Success envelope: `{"ok": true, ...}`. Error envelope: `{"error": {"code": "E_...", "message": "..."}}`. JSON schemas are stable within a major version; fields are added, never renamed or removed.
- Error codes are SCREAMING_SNAKE with `E_` prefix, unique across the CLI, defined in each command's spec.
- Human-readable errors and warnings go to stderr; payload output goes to stdout.

## 4. Document references (`REF`) and pipelines

### 4.1 What `REF` means

Throughout the specs, `REF` denotes a **document reference**: the way a command names one document, on the command line or via stdin. A `REF` is exactly one of:

1. **An id** — matches the id grammar in §6 (e.g. `KB-000042`). Resolved to a document through the scan's id→path map.
2. **A path** — a KB-root-relative path to a `*.md` document in the KB (`synthetic/specs/webhook.md`). Accepted with or without the `.md` extension. Only KB-root-relative paths are accepted; absolute paths are not a valid `REF`.

Resolution rules:

- A token matching the id grammar is treated as an id first; if no document carries that id, it is unresolved (not retried as a path).
- Any other token is treated as a path.
- Unresolvable `REF` → reported on stderr with exit 1; in a batch (`REF...`), remaining refs are still processed (batch-friendly, per §2).
- `REF...` means one or more references as positional arguments; commands that accept `REF...` also read them from stdin (§4.2).

### 4.2 Pipelines

- Commands accepting `REF...` (`show`, `filter`, `frontmatter`, `resolve`, `validate`) read newline-separated refs from stdin when stdin is piped and no refs were passed as arguments.
- A command that receives a candidate set this way operates within that set instead of the whole KB.
- `--output paths` is the producing end of a pipeline. Example: `kb search "user feedback" --output paths | kb filter --class raw`.

## 5. The scan

- One scan per invocation builds the in-memory `KB`: every `*.md` file in the KB tree (recursively from the root) is parsed for frontmatter. `log.md` is **operational** (CLI-appended, never a document); it carries `type: log` for OKF conformance but is excluded from the document set. `index.md` files **are** documents (`DocClass INDEX`), one per directory, included. `kb-config.json` is configuration (not `*.md`); it is loaded separately by `load_config` and never appears in the document set.
- **`type` is mandatory and authoritative (OKF).** Every `*.md` file in the KB MUST carry a `type` frontmatter field; `kb validate` enforces this on **every** markdown file, including `log.md`. A file missing `type` is malformed (§ malformed-file handling below). `type` is the single source of truth for classification — `DocClass` and `RawClass` are **derived from `type`, never from path**:
    - `type: index` → `INDEX`
    - `type: raw-source | chat | feedback` → `RAW` (`RawClass` `SOURCE | CHAT | FEEDBACK`)
    - reserved governance types `conventions | kb-config | health` → `GOVERNANCE`
    - `type: log` → operational (not a `DocClass`; excluded from the document set)
    - any other `type` → `SYNTHETIC` (the open project vocabulary in `kb-config.json`)
- **Location must agree with `type`.** A document's directory is expected to match its `type`, and `kb validate` flags any mismatch (it never silently reclassifies): `index` → file named `index.md`; `raw-source|chat|feedback` → under `raw/sources|chats|feedback/`; governance types → under `governance/`; synthetic types → under `synthetic/`. `type` wins; a misplaced file is a validation error to be fixed (e.g. via `kb mv`), not a reclassification.
- Bodies are loaded lazily — only by commands that need them (`search`, `mv`, `show`).
- Frontmatter parsing preserves key order and unknown keys (FM2). Unknown keys are never an error.
- A file that is **unclassifiable** — its frontmatter fails to parse, or it parses but has no `type` (so no `DocClass` can be derived) — never crashes a query command: it goes to `KB.malformed`, is excluded from results, emits one stderr warning, and is fully reported by `kb validate` (missing `type` is an FM0 error).
- No stored index. Ids live in the files; the id→path map is rebuilt by each scan.
- **CLI-only access discipline.** The CLI is the sole KB data interface for skills: document content is read through `kb show` (and `search` snippets), never by opening KB files directly. This keeps the NFR-8 access-control hooks in the query layer effective. Skills carry the corresponding mandate (PRD §5.2). Symmetrically, documents are **created** through the CLI — `kb ingest` for raw, `kb create` for synthetic — so id allocation and the frontmatter schema stay CLI-authoritative; skills supply content and metadata as arguments rather than hand-writing document files.

### 5.1 Allocating-write persistence ownership

`core/create.py` and `core/ingest.py` own command policy and construct typed
write intents, but all KB filesystem persistence is owned by the shared
`core/write_pipeline.py` seam. The command modules MUST NOT mutate KB paths
directly through `Path`, built-in file handles, `os`, `shutil`, housekeeping,
indexing, safe-I/O, or private write-pipeline primitives. Until the separate
CLI/core input-seam work is implemented, they MAY continue to acquire external
body/source input directly with provably read-only file operations and the
documented clipboard subprocess; that temporary acquisition allowance does
not permit writes to either the KB or the external input.

## 6. Id grammar and allocation

- Id pattern: `<PREFIX>-<NNNNNN>` — an uppercase prefix, a hyphen, a zero-padded integer of at least 6 digits (`KB-000042`, `RAW-000113`; numbers above 999999 keep growing — `KB-1000001` is legal).
- Default prefixes: `KB` (synthetic), `RAW` (raw sources), `CHAT` (session records), `FEED` (feedback). Projects may override in `kb-config.json`.
- **Reserved governance ids.** System governance documents carry fixed, well-known **slug ids** of the form `GOVERNANCE-<SLUG>` (e.g. `GOVERNANCE-CONVENTIONS`, `GOVERNANCE-KB-CONFIG`) instead of the numeric scheme, so agents can address them by a stable known id. These ids are assigned by `kb init` (not allocated), never change, and the `GOVERNANCE` prefix is reserved — `next_id` never allocates in it. They are matched by an alternate id form (`<PREFIX>-<UPPER-SLUG>`) and resolve through the scan like any id; only the numeric `<PREFIX>-<NNNNNN>` form participates in allocation.
- Allocation: next id for a prefix = max existing number for that prefix + 1, computed over the in-memory `KB` built by the scan (no extra I/O — the scan already parses every document's frontmatter). Monotonic: gaps are never refilled (nothing is deleted, LS4). First id of a prefix is `<PREFIX>-000001`.
- **Malformed-file guard.** A document whose frontmatter fails to parse has an invisible id. Commands that allocate ids MUST refuse to run while `KB.malformed` is non-empty (exit 2), directing the user to `kb validate` — otherwise an invisible id could be reallocated as a duplicate.
- Merge collisions (two branches allocating the same id) are detected by `kb validate` as duplicate-id errors; repair is manual.

## 7. Core data models

Pinned so that independently implemented commands land on the same names. **Growth policy:** a model is added here by the first command spec that needs it; the *Introduced by* column records that spec. Later specs may add fields but not change existing ones.

**Implementation:** every model below is a Pydantic 2.x `BaseModel` (or `RootModel`), giving validation, typed access, and structured (de)serialization. Frontmatter models set `model_config = ConfigDict(extra="allow")` to preserve unknown keys (FM2). The generic `Frontmatter` is a `RootModel` wrapping an insertion-ordered `dict[str, Any]` so raw YAML round-trips without reordering; `RawFrontmatter` / `SyntheticFrontmatter` are validated views constructed over it. Pydantic validates already-parsed structures and does **not** perform file I/O: PyYAML parses document frontmatter and stdlib `json` parses `kb-config.json`, then the result is handed to the model. `DocId` implements ordering by `(prefix, number)`.

| Model | Module | Fields / contract | Introduced by |
|---|---|---|---|
| `DocClass` | `core/model.py` | enum: `RAW`, `SYNTHETIC`, `GOVERNANCE`, `INDEX`; **derived from the authoritative `type`** (§5), not from path | kb-init |
| `RawClass` | `core/model.py` | enum: `SOURCE`, `CHAT`, `FEEDBACK`; **derived from `type`** (`raw-source`→`SOURCE`, `chat`→`CHAT`, `feedback`→`FEEDBACK`); the matching subdirectory (`raw/sources|chats|feedback/`) is required and checked by `kb validate` | kb-init |
| `DocId` | `core/ids.py` | `prefix: str`, `number: int`; models the **numeric** id form only; `parse(s)`, `format()` (zero-pad to 6), ordering by (prefix, number); `next_id(kb, prefix) -> DocId`. Reserved slug ids (`GOVERNANCE-CONVENTIONS`, …) are literal id strings, not `DocId`s | kb-init (grammar), kb-ingest (raw allocation), kb-create (synthetic allocation) |
| `Frontmatter` | `core/model.py` | ordered mapping preserving unknown keys; round-trips YAML without reordering | kb-init |
| `RawFrontmatter` | `core/model.py` | `id`, `type` (raw-source\|chat\|feedback), `ingested_at` (ISO-8601 UTC), `origin: str`, `title: str` (always written by `kb ingest`; not part of FM1's mandatory set), `about: str \| None` (feedback only). Enforced across the KB by `kb validate` (kb-validate §4.1, §7.1) | kb-ingest |
| `SyntheticFrontmatter` | `core/model.py` | `id`, `type`, `title`, `description`, `status` (draft\|current\|superseded\|retired), `derived_from: list`, `timestamp`, `last_human_touch`; optional `tags`, `supersedes`, `instructions`. **Constructed and emitted by kb-create** in exactly this key order (kb-create §5.1; optional keys last, only when present; `derived_from`/`tags` as block sequences); enforced across the KB by `kb validate` (kb-validate §4.1, §7.1) | kb-create (emission), kb-validate (enforcement) |
| `GovernanceFrontmatter` | `core/model.py` | `id` (reserved slug, e.g. `GOVERNANCE-CONVENTIONS`), `type`, `title`, `description`; the two system files scaffolded by `kb init`. Enforced across the KB by `kb validate` (kb-validate §4.1, §7.1) | kb-init |
| `IndexFrontmatter` | `core/model.py` | `type: index`, `description`; optional `title`; **no `id`** (index docs are path-addressed). One per directory (`DocClass INDEX`). CLI-maintained and read-only for humans/agents: the body is a generated child listing (`kb index` regenerates it). Enforced across the KB by `kb validate` (kb-validate §4.1, §7.1) | kb-init |
| `Document` | `core/model.py` | `id: str \| None` (the literal frontmatter id; numeric ids parse via `DocId`), `path` (KB-root-relative), `doc_class: DocClass`, `frontmatter: Frontmatter`, `body` (lazy property) | kb-ingest |
| `KB` | `core/scan.py` | `root: Path`, `documents: list[Document]`, `by_id: dict[str, Document]`, `malformed: list[(path, error)]`; built by `scan(root)` | kb-ingest |
| `Config` | `core/model.py` | `schema: int`, `types: list[str]`, `tags: list[str]`, `id_prefixes: dict[str, str]`, `propagation_auto_safe: list[str]`; parsed by `load_config(root)` as a JSON object from `kb-config.json` at the KB root (stdlib `json`); unknown keys ignored; every field has the documented default when the key is absent; unparseable file → `E_CONFIG_INVALID` | kb-init |
| `LogEntry` | `core/housekeeping.py` | `at` (ISO-8601 UTC), `action`, `actor`, `doc_ids: list[str]`, `note`; line format §8 | kb-init |
| `Finding` | `core/validate.py` | `code: str` (stable finding code, kb-validate §7.1 — a separate namespace from `E_*` command errors), `severity` (`error`\|`warning`), `path` (KB-root-relative; always present — malformed, index, and log files have no id), `id: str \| None` (the literal frontmatter id when present as a string), `message: str`. Findings sort by (path, code, occurrence); produced only by `kb validate` | kb-validate |

## 8. `log.md` line format

One bullet line per event, appended only:

```
- <ISO-8601 UTC> | <action> | <actor> | <comma-separated ids or -> | <note>
```

Example:

```
- 2026-07-13T09:30:00Z | initialized | kb-cli | - | KB scaffolded by kb init
```

Actions are an open set; each command spec declares the actions it writes. `actor` defaults to `kb-cli` when the CLI acts on its own; skills pass `--actor`.

## 9. Help-text conventions

- Every command's `--help` contains, in order: a one-to-three-sentence description, the options with help strings, and an `Examples:` section with 2–5 one-line examples.
- The **wording** of the description, each option help string, and the examples is normative (defined in each command spec). The **layout** (boxes, wrapping, color) belongs to Typer and is not asserted.
- Tests assert normative strings with substring matching against `--help` output.

## 10. Testing conventions

- `pytest`; CLI invoked through Typer's `CliRunner` (no subprocesses in unit tests).
- Fixtures build throwaway KBs in `tmp_path`; a shared `make_kb()` / `make_doc()` helper set lives in `tests/conftest.py`.
- **One acceptance criterion = one test.** Each command spec's acceptance-criteria list maps one-to-one onto test functions named `test_ac<NN>_<slug>`.
- JSON outputs are asserted against the schemas in the specs (field presence and types, not incidental ordering).
- Platform-specific criteria (e.g. permission errors) may be skipped on platforms where they don't apply, with a `skipif` marker.
