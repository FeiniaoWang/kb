# `kb` CLI — Shared Foundations (normative)

**Status:** Living reference. Every command spec in this directory assumes this document.
**Implementation context rule:** to implement or validate any `kb` command, an agent reads exactly two files — this one and the command's own spec (`kb-<command>.md`).
**Sources:** [PRD §7.1](../../prd.md), [master design 2026-07-13](../../superpowers/specs/2026-07-13-kb-cli-design.md). Where this document is more specific, this document wins.

## 1. Root discovery

Every command except `kb init` locates the KB root before doing anything:

1. `--kb PATH` flag, if given.
2. Else `KB_ROOT` environment variable, if set.
3. Else walk up from cwd (inclusive) to the filesystem root, looking for a directory containing a `.kb` marker file. First hit wins.

Failure: message `not inside a knowledge base (no .kb marker found); run 'kb init' or pass --kb` on stderr, exit 2.

The `.kb` marker is a YAML file. Current content:

```yaml
schema: 1
```

`schema` is the KB layout schema version. Commands MUST refuse (exit 2, `E_SCHEMA_UNSUPPORTED`) a schema newer than they know.

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

## 4. Pipelines

- Commands accepting `REF...` (`show`, `filter`, `frontmatter`, `resolve`, `validate`) read newline-separated ids/paths from stdin when stdin is piped and no refs were passed as arguments.
- A command that receives a candidate set this way operates within that set instead of the whole KB.
- `--output paths` is the producing end of a pipeline. Example: `kb search "user feedback" --output paths | kb filter --class raw`.

## 5. The scan

- One scan per invocation builds the in-memory `KB`: every `*.md` file under `raw/`, `synthetic/`, and `governance/` is parsed for frontmatter. `index.md` and `log.md` files are excluded from the document set.
- Bodies are loaded lazily — only by commands that need them (`search`, `mv`).
- Frontmatter parsing preserves key order and unknown keys (FM2). Unknown keys are never an error.
- A file whose frontmatter fails to parse never crashes a query command: it is excluded from results, one warning line per file goes to stderr, and `kb validate` reports it fully.
- No stored index. Ids live in the files; the id→path map is rebuilt by each scan.
- **CLI-only access discipline.** The CLI is the sole KB data interface for skills: document content is read through `kb show` (and `search` snippets), never by opening KB files directly. This keeps the NFR-8 access-control hooks in the query layer effective. Skills carry the corresponding mandate (PRD §5.2).

## 6. Id grammar and allocation

- Id pattern: `<PREFIX>-<NNNN>` — an uppercase prefix, a hyphen, a zero-padded integer of at least 4 digits (`KB-0042`, `RAW-0113`, `KB-10001` is legal).
- Default prefixes: `KB` (synthetic), `RAW` (raw sources), `CHAT` (session records), `FEED` (feedback). Projects may override in `governance/kb-config.md`.
- Allocation: next id for a prefix = max existing number for that prefix + 1, computed over the in-memory `KB` built by the scan (no extra I/O — the scan already parses every document's frontmatter). Monotonic: gaps are never refilled (nothing is deleted, LS4). First id of a prefix is `<PREFIX>-0001`.
- **Malformed-file guard.** A document whose frontmatter fails to parse has an invisible id. Commands that allocate ids MUST refuse to run while `KB.malformed` is non-empty (exit 2), directing the user to `kb validate` — otherwise an invisible id could be reallocated as a duplicate.
- Merge collisions (two branches allocating the same id) are detected by `kb validate` as duplicate-id errors; repair is manual.

## 7. Core data models

Pinned so that independently implemented commands land on the same names. **Growth policy:** a model is added here by the first command spec that needs it; the *Introduced by* column records that spec. Later specs may add fields but not change existing ones.

| Model | Module | Fields / contract | Introduced by |
|---|---|---|---|
| `DocClass` | `core/model.py` | enum: `RAW`, `SYNTHETIC`, `GOVERNANCE` | kb-init |
| `RawClass` | `core/model.py` | enum: `SOURCE`, `CHAT`, `FEEDBACK`; maps to `raw/sources`, `raw/chats`, `raw/feedback` and types `raw-source`, `chat`, `feedback` | kb-init |
| `DocId` | `core/ids.py` | `prefix: str`, `number: int`; `parse(s)`, `format()` (zero-pad to 4), ordering by (prefix, number); `next_id(kb, prefix) -> DocId` | kb-init (grammar), kb-ingest (allocation) |
| `Frontmatter` | `core/model.py` | ordered mapping preserving unknown keys; round-trips YAML without reordering | kb-init |
| `RawFrontmatter` | `core/model.py` | `id`, `type` (raw-source\|chat\|feedback), `ingested_at` (ISO-8601 UTC), `origin: str`, `about: str \| None` (feedback only) | kb-ingest |
| `SyntheticFrontmatter` | `core/model.py` | `id`, `type`, `title`, `description`, `status` (draft\|current\|superseded\|retired), `derived_from: list`, `timestamp`, `last_human_touch`; optional `tags`, `supersedes`, `instructions`. Shape pinned now; enforcement specced in kb-validate | kb-validate (enforcement) |
| `Document` | `core/model.py` | `id: DocId \| None`, `path` (KB-root-relative), `doc_class: DocClass`, `frontmatter: Frontmatter`, `body` (lazy property) | kb-ingest |
| `KB` | `core/scan.py` | `root: Path`, `documents: list[Document]`, `by_id: dict[str, Document]`, `malformed: list[(path, error)]`; built by `scan(root)` | kb-ingest |
| `Config` | `core/model.py` | `types: list[str]`, `tags: list[str]`, `id_prefixes: dict[str, str]`, `propagation_auto_safe: list[str]`; parsed by `load_config(root)` from the first ` ```yaml ` block in `governance/kb-config.md` body; every field has the documented default when file or key is absent | kb-init |
| `LogEntry` | `core/housekeeping.py` | `at` (ISO-8601 UTC), `action`, `actor`, `doc_ids: list[str]`, `note`; line format §8 | kb-init |

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
