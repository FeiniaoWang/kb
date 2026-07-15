# Spec: `kb ingest`

**Implementation context:** this file + [00-shared.md](00-shared.md).
**Traceability:** PRD CLI-8, ING-1 (the deterministic normalize-and-file portion), ING-6 (feedback intake mechanics), FM0/FM1 (raw reduced schema), LS4 (append-only evidence, log entry). The overlap survey, conflict resolution, and propagation (ING-2…ING-5) belong to the `kb-ingest` skill, not this command.

## 1. Purpose

Normalize incoming material into the knowledge base as immutable raw evidence: read from a file, stdin, or the clipboard, and file exactly one Markdown document into `raw/sources/`, `raw/chats/`, or `raw/feedback/` with the next sequential id and the reduced raw frontmatter. The body is copied **verbatim** — ingest normalizes and files; it never synthesizes (CLI-8). A non-text original is copied unchanged alongside a generated Markdown stub, which becomes the citable form. Ingest is the only v1 command that allocates ids.

## 2. CLI surface

```
kb ingest --class source|chat|feedback --from file|stdin|clipboard [SOURCE]
          [--dest SUBDIR] [--about REF] [--title TEXT] [--origin TEXT]
          [--actor NAME] [--kb PATH] [--json]
```

| Param | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `SOURCE` | positional | file path | — | Path to the source file. **Required iff `--from file`; forbidden otherwise** |
| `--class` | required option | `source\|chat\|feedback` | — | Raw subclass: sets `type` (`raw-source\|chat\|feedback`), the class directory (`raw/sources\|chats\|feedback/`), and the id prefix (`kb-config.json` `id_prefixes`, key `source\|chat\|feedback`) |
| `--from` | required option | `file\|stdin\|clipboard` | — | Adapter to read the material with. Always explicit — never inferred from other arguments |
| `--dest` | option | relative path | class directory | Subdirectory **relative to the class directory** (`--dest api` → `raw/sources/api/`). Created (with parents) if missing, each new directory with its `index.md`. Must not be absolute or contain `.`/`..` segments |
| `--about` | option | `REF` | — | Document the feedback concerns. **Required for `--class feedback`, forbidden otherwise.** Resolved per 00-shared §4; must resolve to a document carrying an id; the canonical id is stored |
| `--title` | option | text | derived (§4 step 9) | Frontmatter `title`; also drives the target filename (slugified) |
| `--origin` | option | text | adapter default (§4 step 4) | Provenance recorded in the `origin` frontmatter field |
| `--actor` | option | text | `kb-cli` | Actor recorded in the log entry (00-shared §8) |
| `--kb` | option | directory path | upward discovery | KB root (00-shared §1) |
| `--json` | option | flag | off | Structured output (§6) |

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Ingest material into the knowledge base as immutable raw evidence.
>
> Reads from a file, stdin, or the clipboard and files one normalized Markdown document into raw/sources/, raw/chats/, or raw/feedback/, with the next sequential id and the reduced raw frontmatter. The body is copied verbatim — ingest normalizes and files, it never synthesizes. A non-text file is copied unchanged alongside a generated Markdown stub, which becomes the citable form. Feedback requires --about: the document the feedback concerns. Updates the affected index.md listings and appends an ingested entry to log.md. Does not touch Git.

**Option help strings:**

| Param | Help string |
|---|---|
| `SOURCE` | Path to the source file (required with --from file, forbidden otherwise). |
| `--class` | Raw subclass to file under: source, chat, or feedback. |
| `--from` | Where to read the material from: file, stdin, or clipboard. |
| `--dest` | Subdirectory under the class directory (e.g. api → raw/sources/api/). Created with its index.md if missing. |
| `--about` | Document the feedback concerns (id or KB-relative path). Required for --class feedback. |
| `--title` | Document title; also drives the target filename. [default: derived from the source filename or the id] |
| `--origin` | Provenance recorded in the frontmatter. [default: the source path, "stdin", or "clipboard"] |
| `--actor` | Actor recorded in the log entry. [default: kb-cli] |
| `--kb` | KB root. [default: discovered upward from the current directory] |
| `--json` | Emit results as JSON. |

**Examples section:**

```
Examples:
  kb ingest --class source --from file notes.md                 File a document into raw/sources/
  kb ingest --class source --from file report.pdf --dest q3     Non-text original + citable stub into raw/sources/q3/
  kb ingest --class feedback --from stdin --about KB-000007     Pipe feedback about KB-000007
  kb ingest --class chat --from clipboard --title "Planning session"   Clipboard into raw/chats/
```

## 4. Behavior (normative algorithm)

The run is **pre-flight, then write**: steps 1–10 complete before the first byte is written, so any failure among them leaves the KB byte-for-byte untouched. Only an OS error inside the write phase (steps 11–14) can leave partial state (documented in E12, not rolled back — same stance as kb init E2).

**Pre-flight:**

1. Resolve the KB root (00-shared §1: `--kb`, else upward discovery). No root → `E_NO_KB`, exit 2. Load `kb-config.json` (`E_CONFIG_INVALID` / `E_SCHEMA_UNSUPPORTED`, exit 2).
2. Scan (00-shared §5). If `KB.malformed` is non-empty → `E_INGEST_MALFORMED`, exit 2, naming the malformed paths and directing to `kb validate` — the id-allocation guard of 00-shared §6.
3. Validate the surface: `SOURCE` present iff `--from file`, `--about` present iff `--class feedback` (violations → `E_INGEST_USAGE`, exit 2); `--dest`, when given, must be a relative path containing no `.` or `..` segments (a trailing `/` is stripped) → else `E_INGEST_DEST_INVALID`, exit 2. The **target directory** is the class directory joined with `--dest`.
4. Acquire the input as **bytes** through the adapter registry (§4.1):
   - `file` — read `SOURCE`; missing, unreadable, or not a regular file → `E_INGEST_SOURCE_NOT_FOUND`, exit 2. Default origin: the absolute resolved `SOURCE` path. Source filename: the `SOURCE` basename.
   - `stdin` — read to EOF. On a TTY this reads interactively until Ctrl-D (documented, not an error). Default origin: `stdin`. No source filename.
   - `clipboard` — run the platform tool and capture its stdout: macOS `pbpaste`; Linux `wl-paste`, else `xclip -selection clipboard -o` (first found on `PATH`); Windows `powershell -NoProfile -Command Get-Clipboard`. No tool found, or the tool exits non-zero → `E_INGEST_CLIPBOARD`, exit 2. Default origin: `clipboard`. No source filename.
5. Classify: strict UTF-8 decode. Decodes → **text**. Fails to decode: `--from file` → the **non-text** path (§5.2); `--from stdin|clipboard` → `E_INGEST_NOT_TEXT`, exit 1.
6. Text normalization: CRLF and lone CR become LF; the body ends with exactly one trailing newline; every other byte is verbatim. If the decoded text is empty or whitespace-only → `E_INGEST_EMPTY`, exit 1.
7. Resolve `--about` (feedback only) per 00-shared §4 (id first, then path). It must resolve to a document that carries an `id`; the canonical id is what gets stored. Unresolvable, or the target has no id (e.g. an `index.md`) → `E_INGEST_ABOUT_UNRESOLVED`, exit 1.
8. Allocate the id: prefix = `id_prefixes[<class>]`, number = `next_id` over the scan (00-shared §6).
9. Compute names:
   - **Slug base:** `--title` if given; else the source filename stem (basename minus its final extension; `file` only); else the lowercased id.
   - **slug():** NFKD-normalize, drop non-ASCII, lowercase, collapse every run of characters outside `[a-z0-9]` into a single `-`, trim leading/trailing `-`. An empty result falls back to the lowercased id.
   - **Document filename:** `<slug>.md`. **Non-text original filename:** `<slug>.<ext>` with the original extension lowercased (bare `<slug>` if the original has none).
   - **Collision:** if the document path — or, non-text, the original path — already exists in the target directory, append `-<lowercased id>` to **both** stems (`meeting-notes.md` → `meeting-notes-raw-000042.md`). The id is unique, so suffixed names never collide. Nothing existing is ever overwritten (raw is append-only, LS4).
   - **Title field (always written):** `--title` if given; else the source filename stem with `-`/`_` replaced by spaces, whitespace runs collapsed, no case change; else the id string.
10. Construct and validate the `RawFrontmatter` (00-shared §7): `id`, `type` (`raw-source|chat|feedback`), `ingested_at` = invocation time as ISO-8601 UTC with seconds precision (`YYYY-MM-DDTHH:MM:SSZ`), `origin` (`--origin` else the adapter default), `title`, and `about` (feedback only).

**Write phase:**

11. Create missing directories along the target path. Each newly created directory gets its `index.md` in the same operation (directory invariant, 00-shared) — born current per the §5.3 template, already listing its child.
12. Write the files: non-text → the original, byte-for-byte; then the document — the frontmatter block in the pinned key order (`id`, `type`, `ingested_at`, `origin`, `title`, `about`), then `---`, then the body with **no inserted heading or blank line**: the normalized text (text case) or the pinned one-line stub (non-text case, §5.2).
13. Regenerate `index.md` listing bodies (grammar: kb-init §5.2): the target directory's (unless it was just created — then it is already current) and, when step 11 created directories, the **nearest pre-existing ancestor's** (its `## Subdirectories` gains the new child). No other `index.md` is touched; global freshness is `kb index`'s job.
14. Append the log entry (00-shared §8): action `ingested`, actor `--actor` (default `kb-cli`), ids = the new id, note = `<document relpath> from <origin>`. A missing `log.md` is first recreated with the kb-init §5.3 scaffold (frontmatter + header comment + heading, no `initialized` line) and then appended.
15. Report per §6, exit 0.

There is **no de-duplication**: re-ingesting identical content yields a new document with a new id (raw is append-only; sameness is a judgment call that belongs to the `kb-ingest` skill). No step runs `git` or inspects Git state.

### 4.1 Adapter registry (internal contract)

Adapters live in `core/ingest.py` and register in a small table so later adapters (Slack, mail, ticketing — Phase 4) are additive:

```python
class AdapterPayload(BaseModel):
    data: bytes                    # raw input, undecoded
    default_origin: str            # used when --origin is absent
    source_filename: str | None    # basename for slug/title derivation, when the adapter has one

Adapter = Callable[[str | None], AdapterPayload]   # receives SOURCE (None for stdin/clipboard)
ADAPTERS: dict[str, Adapter]                       # "file" | "stdin" | "clipboard" | ...
```

Adapters only acquire bytes and provenance; text detection, normalization, naming, and filing are uniform and live outside the adapters. `AdapterPayload` is ingest-internal — it is **not** a 00-shared §7 core model.

## 5. Filesystem effects

### 5.1 The ingested document

`kb ingest --class source --from file /work/meeting_notes.md` into a fresh KB writes `raw/sources/meeting-notes.md`:

```markdown
---
id: RAW-000001
type: raw-source
ingested_at: 2026-07-15T09:30:00Z
origin: /work/meeting_notes.md
title: meeting notes
---
<body: the source text, verbatim, line endings normalized to LF, one trailing newline>
```

Key order is pinned as shown; `ingested_at` is the only non-deterministic value (tests pattern-match it, everything else exact). YAML values are emitted in plain style, quoted only when YAML requires it. `about` appears **only** on feedback records, as the last key:

```markdown
---
id: FEED-000001
type: feedback
ingested_at: 2026-07-15T09:30:00Z
origin: stdin
title: FEED-000001
about: KB-000007
---
```

Raw documents never carry a `description` — a description would be synthesis, and adapters never synthesize.

### 5.2 Non-text originals

A `--from file` input that does not decode as UTF-8 produces **two** files in the target directory: the original, copied byte-for-byte, and a generated `.md` stub with the same frontmatter — the stub is the citable form. `kb ingest --class source --from file "/work/Q3 Report.pdf" --dest q3 --title "Q3 Report"`:

```
raw/sources/q3/q3-report.pdf     # original, byte-identical copy
raw/sources/q3/q3-report.md      # citable stub
```

The stub's body is exactly one pinned line:

```markdown
---
id: RAW-000002
type: raw-source
ingested_at: 2026-07-15T09:31:00Z
origin: /work/Q3 Report.pdf
title: Q3 Report
---
Non-text original stored alongside this stub: [q3-report.pdf](q3-report.pdf)
```

Only `.md` documents appear in `index.md` `## Files` listings — the original is reachable through the stub's link, never listed directly. On a name collision both stems take the `-<lowercased id>` suffix together, so the pair stays visibly paired.

### 5.3 New-directory `index.md` (pinned template)

Every directory created by `--dest` gets this `index.md` in the same operation (directory invariant), born current — its listing already includes the child written by this run:

```markdown
---
type: index
description: Documents under <kb-relative dir path>/.
---
# <directory basename>

<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->

## Files
* [RAW-000002][Q3 Report](q3-report.md)
```

Frontmatter `description` is `Documents under <kb-relative dir path>/.` (e.g. `Documents under raw/sources/q3/.`); the title is the directory basename verbatim. Body grammar and blank-line layout follow kb-init §5.2 (empty sections omitted; an intermediate directory whose only child is another new directory has a `## Subdirectories` section instead).

### 5.4 Index listing updates

After scenario 5.2 on a KB that already held `raw/sources/meeting-notes.md`, the regenerated `raw/sources/index.md` body is:

```markdown
## Subdirectories
* [q3](q3/index.md) - Documents under raw/sources/q3/.

## Files
* [RAW-000001][meeting notes](meeting-notes.md)
```

A document without a `description` renders without the ` - <description>` tail: `* [<id>][<title>](<file>.md)`. Regeneration rebuilds the body listing from the directory's current children per the kb-init §5.2 grammar; the index's own frontmatter `description` is preserved, never regenerated.

### 5.5 `log.md`

One line appended per run (00-shared §8):

```
- 2026-07-15T09:31:00Z | ingested | kb-cli | RAW-000002 | raw/sources/q3/q3-report.md from /work/Q3 Report.pdf
```

## 6. Output

**Text (stdout):** one `<created|updated>  <relative path>` line per document, original, or `index.md` written or regenerated, ordered alphabetically by relative path, then the result line. The `log.md` append is implicit (recorded in the log itself) and not listed:

```
created  raw/sources/q3/index.md
created  raw/sources/q3/q3-report.md
created  raw/sources/q3/q3-report.pdf
updated  raw/sources/index.md
ingested RAW-000002 as raw/sources/q3/q3-report.md
```

**JSON (`--json`):**

```json
{
  "ok": true,
  "id": "RAW-000002",
  "path": "raw/sources/q3/q3-report.md",
  "original": "raw/sources/q3/q3-report.pdf",
  "created": ["raw/sources/q3/index.md", "raw/sources/q3/q3-report.md", "raw/sources/q3/q3-report.pdf"],
  "updated": ["raw/sources/index.md"]
}
```

`path` is the citable document, KB-root-relative. `original` is the copied non-text original's relative path, or `null` for text ingests. `created`/`updated` are sorted alphabetically and, like the text lines, exclude `log.md`. Errors use the shared envelope `{"error": {"code": "E_...", "message": "..."}}` (00-shared §3).

## 7. Errors and edge cases

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E1 | Not inside a KB (no `kb-config.json` found; also `--kb` pointing at a config-less directory) | `E_NO_KB`, message per 00-shared §1 | 2 |
| E2 | `kb-config.json` unparseable | `E_CONFIG_INVALID` | 2 |
| E3 | Config `schema` newer than the CLI knows | `E_SCHEMA_UNSUPPORTED` | 2 |
| E4 | `KB.malformed` non-empty | `E_INGEST_MALFORMED` naming the malformed paths, directing to `kb validate`; nothing written (id-allocation guard, 00-shared §6) | 2 |
| E5 | `SOURCE` missing with `--from file`, or given with `--from stdin\|clipboard`; `--about` missing with `--class feedback`, or given with another class | `E_INGEST_USAGE` with a case-specific message | 2 |
| E6 | `--dest` absolute, or containing `.`/`..` segments, or empty | `E_INGEST_DEST_INVALID` naming the offending value | 2 |
| E7 | `SOURCE` missing, unreadable, or not a regular file | `E_INGEST_SOURCE_NOT_FOUND` | 2 |
| E8 | No clipboard tool on `PATH`, or the tool exits non-zero | `E_INGEST_CLIPBOARD` | 2 |
| E9 | stdin/clipboard bytes do not decode as UTF-8 | `E_INGEST_NOT_TEXT` (a non-text **file** instead takes the §5.2 stub path) | 1 |
| E10 | Input empty or whitespace-only after decoding | `E_INGEST_EMPTY` | 1 |
| E11 | `--about` unresolvable, or resolves to a document without an id | `E_INGEST_ABOUT_UNRESOLVED` | 1 |
| E12 | OS error during the write phase (steps 11–14) | `E_INGEST_IO` with the OS message; partial files may remain (documented, not rolled back) | 2 |
| E13 | Unknown option / bad enum value for `--class`/`--from` | usage error (Typer-rendered message on stderr) | 2 |
| E14 | Re-ingesting content identical to an existing document | allowed — new id, collision-suffixed filename, no de-duplication | 0 |
| E15 | `--from stdin` on a TTY | reads interactively until EOF (Ctrl-D); not an error | — |
| E16 | `log.md` missing at step 14 | recreated with the kb-init §5.3 scaffold (no `initialized` line), then appended | 0 |

Every pre-flight failure (E1–E11) leaves the KB byte-for-byte untouched (§4).

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`. Each is independently testable with an unambiguous pass condition; `ingested_at` and log timestamps are pattern-matched, everything else asserted exactly.

**Coverage map:** happy path & pinned content AC1–AC6 (§4, §5.1, §5.4, §5.5, §6) · classes & ids AC7–AC11 (§2, §4 steps 2/8, E4) · filenames, titles & collisions AC12–AC16 (§4 step 9, E14) · adapters AC17–AC21 (§4 steps 4–6, §4.1, E8–E10) · non-text originals AC22–AC24 (§5.2) · `--dest` & index effects AC25–AC28 (§4 steps 3/11/13, §5.3, §5.4, E6) · `--about` AC29–AC31 (§4 step 7, E11) · usage & environment errors AC32–AC35 (E1, E5, E7) · atomicity & log AC36–AC38 (§4 pre-flight, step 14, E16) · output, help & Git-agnosticism AC39–AC42 (§3, §6, 00-shared).

| # | Given / When / Then |
|---|---|
| AC1 | Given a fresh KB and a UTF-8 file `/work/meeting_notes.md`, when `kb ingest --class source --from file /work/meeting_notes.md` runs, then exit 0 and `raw/sources/meeting-notes.md` exists with frontmatter containing exactly the keys `id`, `type`, `ingested_at`, `origin`, `title` in that order, with `id == RAW-000001`, `type == raw-source`, `ingested_at` parsing as `YYYY-MM-DDTHH:MM:SSZ`, `origin` == the absolute source path, `title == meeting notes`. |
| AC2 | Given a source file with LF line endings, a trailing newline, and tricky content (a leading `---` line, Unicode, trailing spaces), when it is ingested, then the document's body — everything after the closing `---` of the frontmatter block — is byte-identical to the source. |
| AC3 | Given a source file with CRLF and lone-CR line endings and no trailing newline, when it is ingested, then the body contains only LF line endings and ends with exactly one newline, all other bytes verbatim. |
| AC4 | Given AC1's run, then `raw/sources/index.md` gained exactly the line `* [RAW-000001][meeting notes](meeting-notes.md)` under `## Files` (no ` - <description>` tail), its frontmatter `description` is unchanged from the kb-init pinned value, and no other `index.md` in the KB changed. |
| AC5 | Given AC1's run, then `log.md` gained exactly one line matching `- <timestamp> | ingested | kb-cli | RAW-000001 | raw/sources/meeting-notes.md from <absolute source path>` with `<timestamp>` parsing as ISO-8601 UTC. |
| AC6 | Given AC1's run, then stdout is exactly: `created  raw/sources/meeting-notes.md`, `updated  raw/sources/index.md` (alphabetical), then `ingested RAW-000001 as raw/sources/meeting-notes.md`, with no `log.md` line. |
| AC7 | Given `--class chat --from stdin` with piped text, then the document lands in `raw/chats/`, has `type: chat`, and `id == CHAT-000001`. |
| AC8 | Given a KB containing a synthetic document `KB-000007`, when `kb ingest --class feedback --from stdin --about KB-000007` runs with piped text, then the document lands in `raw/feedback/` with `type: feedback`, `id == FEED-000001`, and `about: KB-000007` as the last frontmatter key. |
| AC9 | Given a KB whose raw sources carry ids `RAW-000001` and `RAW-000005` (a gap), when a source is ingested, then the new id is `RAW-000006` — max+1, gaps never refilled. |
| AC10 | Given a `kb-config.json` with `id_prefixes.source == "SRC"`, when a source is ingested, then the new id is `SRC-000001`. |
| AC11 | Given a KB containing a `*.md` file whose frontmatter does not parse, when any `kb ingest` runs, then exit 2 with `E_INGEST_MALFORMED` naming that path, and nothing is written (no file, no index change, no log line). |
| AC12 | Given `--title "Meeting Notes!"`, then the document is `meeting-notes.md` (slugified) and frontmatter `title` is the verbatim `Meeting Notes!`. |
| AC13 | Given a source file named `q3_planning-notes.md` and no `--title`, then the filename is `q3-planning-notes.md` and the title is `q3 planning notes` (stem with `-`/`_` → spaces, no case change). |
| AC14 | Given `raw/sources/notes.md` already exists, when a source that slugs to `notes` is ingested and receives id `RAW-000002`, then the new document is `raw/sources/notes-raw-000002.md` and the pre-existing file is byte-identical afterwards. |
| AC15 | Given `--title "!!!"` (slugifies to empty), then the document filename falls back to the lowercased id (`raw-000001.md`). |
| AC16 | Given the same file ingested twice, then two documents exist with distinct ids, the second collision-suffixed, the first byte-identical afterwards, and both runs exit 0 (no de-duplication, E14). |
| AC17 | Given text piped to `--from stdin` with no `--title`, then `origin == stdin`, the filename is the lowercased id, and `title` is the id string. |
| AC18 | Given a PATH shim providing a fake clipboard tool that prints known text, when `--from clipboard` runs, then the document body is that text and `origin == clipboard`. |
| AC19 | Given a PATH with no clipboard tool, when `--from clipboard` runs, then exit 2 with `E_INGEST_CLIPBOARD` and nothing written. |
| AC20 | Given non-UTF-8 bytes piped to `--from stdin`, then exit 1 with `E_INGEST_NOT_TEXT` and nothing written. |
| AC21 | Given a file containing only whitespace, when it is ingested, then exit 1 with `E_INGEST_EMPTY` and nothing written. |
| AC22 | Given a binary file `Q3 Report.pdf` (invalid UTF-8) and `--title "Q3 Report"`, when it is ingested, then `q3-report.pdf` is a byte-identical copy, `q3-report.md` matches §5.2 exactly (frontmatter + the pinned one-line stub body linking `q3-report.pdf`), and both appear as `created` in the output. |
| AC23 | Given `q3-report.md` already exists in the target directory, when the AC22 ingest runs and receives id `RAW-000002`, then **both** new files are suffixed (`q3-report-raw-000002.md`, `q3-report-raw-000002.pdf`) and the stub links the suffixed original. |
| AC24 | Given AC22's run, then the target directory's `index.md` `## Files` lists the stub `q3-report.md` and does **not** list `q3-report.pdf`. |
| AC25 | Given `--dest api` where `raw/sources/api/` does not exist, then the directory is created with an `index.md` byte-matching §5.3 (description `Documents under raw/sources/api/.`, title `api`, listing the new document), `raw/sources/index.md` is regenerated with `* [api](api/index.md) - Documents under raw/sources/api/.` under `## Subdirectories`, and the root and `raw/` indexes are untouched. |
| AC26 | Given `--dest a/b` where neither directory exists, then both are created with born-current §5.3 indexes (`a`'s listing `b` under `## Subdirectories`, `b`'s listing the document under `## Files`), and only the nearest pre-existing ancestor's index (`raw/sources/index.md`) is regenerated. |
| AC27 | Given `--dest api` where `raw/sources/api/` already exists with its index, then only `raw/sources/api/index.md` is regenerated (`updated`); `raw/sources/index.md` is untouched. |
| AC28 | Given `--dest /abs` (case a) and `--dest ../escape` (case b), then exit 2 with `E_INGEST_DEST_INVALID` naming the value, nothing written. |
| AC29 | Given `--class feedback --about synthetic/specs/webhook.md` where that document carries id `KB-000007`, then the stored frontmatter is `about: KB-000007` (canonical id, not the path). |
| AC30 | Given `--class feedback --about KB-999999` (no such id), then exit 1 with `E_INGEST_ABOUT_UNRESOLVED` and nothing written. |
| AC31 | Given `--class feedback --about index.md` (resolves to a document without an id), then exit 1 with `E_INGEST_ABOUT_UNRESOLVED` and nothing written. |
| AC32 | Given `--class feedback` without `--about` (case a) and `--class source --about KB-000001` (case b), then exit 2 with `E_INGEST_USAGE` and a case-specific message, nothing written. |
| AC33 | Given `--from file` without `SOURCE` (case a) and `--from stdin SOURCE.md` (case b), then exit 2 with `E_INGEST_USAGE`, nothing written. |
| AC34 | Given `--from file /nonexistent` (case a) and `--from file <a directory>` (case b), then exit 2 with `E_INGEST_SOURCE_NOT_FOUND`, nothing written. |
| AC35 | Given a directory with no `kb-config.json` in it or any ancestor, when `kb ingest` runs there, then exit 2 with `E_NO_KB` and the 00-shared §1 message. |
| AC36 | Given a failing pre-flight run (AC30's setup), then afterwards every file in the KB is byte-identical to before — no document, no index change, no log line (pre-flight atomicity). |
| AC37 | Given `--actor pm-skill`, then the log line's actor column is `pm-skill`. |
| AC38 | Given a KB whose `log.md` was deleted, when an ingest runs, then `log.md` exists afterwards with the kb-init §5.3 scaffold (frontmatter `type: log`, header comment, heading), no `initialized` line, and exactly one `ingested` line. |
| AC39 | Given `--json` on a successful non-text `--dest` run (AC22+AC25 setup), then stdout parses as JSON with exactly the fields `ok` (true), `id`, `path`, `original` (string), `created`/`updated` (alphabetically sorted arrays of relative paths, excluding `log.md`), and nothing else on stdout; a text ingest yields `original: null`. |
| AC40 | Given `--json` on a failing run (AC30's setup), then stdout is exactly the envelope `{"error": {"code": "E_INGEST_ABOUT_UNRESOLVED", "message": …}}` and exit is 1. |
| AC41 | When `kb ingest --help` runs, then exit 0 and the output contains every normative string from §3 — each description sentence, each option help string, each example line. |
| AC42 | Given AC1's run, then no `git` subprocess was invoked (PATH shim or subprocess spy) and no `.git/` directory exists (Git-agnostic). |

## 9. Out of scope

- Overlap survey, conflict analysis, supersession, and propagation (ING-2…ING-5) — the `kb-ingest` skill's judgment layer, driven through query commands.
- Session-record summarization or any content synthesis — ingest files what it is given, verbatim; even the non-text stub body is a fixed pointer, not a summary.
- De-duplication of identical or near-identical content (E14) — sameness is a judgment call for the skill.
- Additional adapters (Slack, mail, ticketing) — Phase 4; the §4.1 registry is the extension point.
- Regenerating `index.md` files beyond the target directory and the nearest pre-existing ancestor — global freshness is `kb index`'s job.
- Validating the ingested document beyond its own frontmatter construction (full raw-schema enforcement across the KB is `kb validate`'s job).
- **All Git operations** (00-shared): ingest never runs `git` or inspects Git state.
