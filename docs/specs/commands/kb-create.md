# Spec: `kb create`

**Implementation context:** this file + [00-shared.md](00-shared.md).
**Traceability:** PRD CLI-13, FM0/FM1 (synthetic frontmatter emission), DG1 (≥1 parent at birth), LS1 (`draft`/`current` at creation), LS2 (`timestamp` = `last_human_touch` at the creation instant), LS4 (append-only log). Invoked by the `kb-author` skill (AUT-6, AUT-7). DG5 (session-record parentage) is deliberately **not** enforced here — it stays a `kb validate` check, the single authoritative enforcement point.

## 1. Purpose

Create a synthetic document deterministically: allocate the next sequential synthetic id, emit the full FM1 frontmatter, and file exactly one Markdown document under `synthetic/` — the write path for synthetic documents, the counterpart to `kb ingest` for raw. At least one parent is required (DG1): every synthetic document derives from prior evidence. `--supersedes` records a replacement and, in the same atomic write, flips the replaced document's `status` to `superseded`, so the KB never holds a `supersedes` link whose target is not marked `superseded`. Judgment — what to write, which parents, `draft` vs `current` — belongs to the human and the `kb-author` skill; this command only makes the mechanical act correct. Agents never hand-write synthetic files: id allocation and the frontmatter schema stay CLI-authoritative (00-shared §5).

## 2. CLI surface

```
kb create --type T --title TITLE --description DESC
          [--derived-from REF]... [--supersedes REF]
          [--status draft|current] [--tag TAG]... [--instructions TEXT]
          [--body-file FILE|-] [--dest SUBDIR]
          [--actor NAME] [--kb PATH] [--json]
```

| Param | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `--type` | required option | text | — | Synthetic document type. Reserved types (`index`, `log`, `raw-source`, `chat`, `feedback`, `conventions`, `kb-config`, `health`) are rejected (`E_CREATE_TYPE_RESERVED`). A type absent from `kb-config.json` `types` is allowed with a stderr warning — the vocabulary is open (INIT-2, AUT-1) |
| `--title` | required option | text | — | Frontmatter `title`; also drives the target filename (slugified) |
| `--description` | required option | text | — | Frontmatter `description` (FM1a: at most two sentences; longer warns, never blocks) |
| `--derived-from` | repeatable option | `REF` | — | A parent document (DG1). Resolved per 00-shared §4; must resolve to a document carrying an id; the canonical id is stored. Argument order is preserved; duplicates are dropped keeping the first occurrence |
| `--supersedes` | option | `REF` | — | The document this one replaces. Must resolve to a **synthetic** document with `status` `draft` or `current`; it is flipped to `superseded` in the same write. Implicitly appended to `derived_from` when not explicitly listed, and satisfies the ≥1-parent rule by itself |
| `--status` | option | `draft\|current` | `draft` | Lifecycle status at birth (LS1). `superseded`/`retired` are lifecycle transitions, not creation values |
| `--tag` | repeatable option | text | — | Frontmatter `tags` entry. Argument order preserved, duplicates dropped keeping the first occurrence; a tag absent from the `kb-config.json` `tags` vocabulary warns on stderr (FM1b enforcement stays with `kb validate`) |
| `--instructions` | option | text | — | Optional `instructions` frontmatter field: standing guidance for the document's consumers |
| `--body-file` | option | file path or `-` | — | Body source: a file, or `-` for stdin. Omitted → empty body (a legitimate `draft` stub). Normalized like ingest: LF line endings, exactly one trailing newline |
| `--dest` | option | relative path | `synthetic/` | Subdirectory **relative to `synthetic/`** (`--dest specs` → `synthetic/specs/`). Created (with parents) if missing, each new directory with its `index.md`. Must not be absolute or contain `.`/`..` segments |
| `--actor` | option | text | `kb-cli` | Actor recorded in the log entry (00-shared §8) |
| `--kb` | option | directory path | upward discovery | KB root (00-shared §1) |
| `--json` | option | flag | off | Structured output (§6) |

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Create a synthetic document in the knowledge base.
>
> The deterministic write path for synthetic/ — the counterpart to kb ingest for raw evidence. Allocates the next sequential id, emits the full synthetic frontmatter, and files one Markdown document under synthetic/. At least one parent is required: every synthetic document derives from prior evidence, named via --derived-from (--supersedes also counts as a parent). --supersedes marks the replaced document superseded in the same atomic write. Updates the affected index.md listings and appends a created entry to log.md. Agents never hand-write synthetic files — id allocation and frontmatter stay CLI-authoritative. Does not touch Git.

**Option help strings:**

| Param | Help string |
|---|---|
| `--type` | Synthetic document type (open vocabulary; reserved types rejected). |
| `--title` | Document title; also drives the target filename. |
| `--description` | One-to-two-sentence summary, shown in index.md listings. |
| `--derived-from` | Parent document (id or KB-relative path); repeatable. At least one parent is required. |
| `--supersedes` | Document this one replaces; marked superseded in the same write and counted as a parent. |
| `--status` | Lifecycle status at birth: draft or current. [default: draft] |
| `--tag` | Tag for the tags frontmatter list; repeatable (a tag missing from the vocabulary warns). |
| `--instructions` | Standing guidance for the document's consumers, stored in the instructions field. |
| `--body-file` | File to read the body from, or - for stdin. [default: empty body] |
| `--dest` | Subdirectory under synthetic/ (e.g. specs → synthetic/specs/). Created with its index.md if missing. |
| `--actor` | Actor recorded in the log entry. [default: kb-cli] |
| `--kb` | KB root. [default: discovered upward from the current directory] |
| `--json` | Emit results as JSON. |

**Examples section:**

```
Examples:
  kb create --type spec --title "Retry Policy" --description "Retry rules." --derived-from CHAT-000027 --body-file draft.md    Draft from a body file
  kb create --type outcome --title "Q3 Outcomes" --description "Q3 results." --derived-from CHAT-000012 --derived-from RAW-000004 --status current    Accepted at creation
  kb create --type spec --title "Retry Policy" --description "Retry rules." --supersedes KB-000031 --derived-from CHAT-000040 --body-file -    Replace KB-000031, body from stdin
  kb create --type note --title "Cache Sizing" --description "Sizing note." --derived-from RAW-000004 --dest notes    File under synthetic/notes/
```

## 4. Behavior (normative algorithm)

The run is **pre-flight, then write**: steps 1–11 complete before the first byte is written, so any failure among them leaves the KB byte-for-byte untouched. Only an OS error inside the write phase (steps 12–15) can leave partial state (documented in E14, not rolled back — same stance as kb ingest E12).

**Pre-flight:**

1. Resolve the KB root (00-shared §1: `--kb`, else upward discovery). No root → `E_NO_KB`, exit 2. Load `kb-config.json` (`E_CONFIG_INVALID` / `E_SCHEMA_UNSUPPORTED`, exit 2).
2. Scan (00-shared §5). If `KB.malformed` is non-empty → `E_CREATE_MALFORMED`, exit 2, naming the malformed paths and directing to `kb validate` — the id-allocation guard of 00-shared §6.
3. Validate the surface: `--dest`, when given, must be a relative path containing no `.` or `..` segments (a trailing `/` is stripped) → else `E_CREATE_DEST_INVALID`, exit 2. The **target directory** is `synthetic/` joined with `--dest`. Missing required options, a bad `--status` value, and unknown options are Typer-rendered usage errors (exit 2); `kb create` has no flag pairings beyond what Typer enforces natively, so it defines no usage error code of its own.
4. Check `--type` (matched verbatim, case-sensitively): a reserved type (`index`, `log`, `raw-source`, `chat`, `feedback`, `conventions`, `kb-config`, `health`) → `E_CREATE_TYPE_RESERVED`, exit 2. A type absent from the config `types` list proceeds with one stderr warning naming the type. Each `--tag` absent from the config `tags` list proceeds with one stderr warning naming the tag. A `--description` of more than two sentences proceeds with one stderr warning (heuristic: a sentence ends at `.`, `!`, or `?` followed by whitespace or end-of-string; matches `kb validate`'s severity — warn, never block).
5. Read the body, if `--body-file` was given: a file path → read it (missing, unreadable, or not a regular file → `E_CREATE_BODY_NOT_FOUND`, exit 2); `-` → read stdin to EOF (on a TTY this reads interactively until Ctrl-D — documented, not an error). The bytes must decode as strict UTF-8 → else `E_CREATE_BODY_NOT_TEXT`, exit 1. Normalize: CRLF and lone CR become LF; the body ends with exactly one trailing newline. Empty or whitespace-only input — like an omitted `--body-file` — yields the **empty body**: the document ends immediately after the closing `---` line. Unlike ingest, an empty body is legal: a `draft` stub the author fills later.
6. Resolve each `--derived-from` per 00-shared §4 (id first, then path). Each must resolve to a document that carries an `id` (numeric or reserved slug); the canonical id is what gets stored. Unresolvable, or the target has no id (e.g. an `index.md`) → `E_CREATE_PARENT_UNRESOLVED`, exit 1. The stored list preserves argument order; duplicates are dropped keeping the first occurrence.
7. Resolve `--supersedes`, if given, the same way (unresolvable or no id → `E_CREATE_SUPERSEDES_UNRESOLVED`, exit 1). The target must be a **synthetic** document (`DocClass SYNTHETIC`) whose frontmatter `status` is literally `draft` or `current` → else `E_CREATE_SUPERSEDES_INVALID`, exit 1 (superseding an already-`superseded`/`retired` document almost always means the wrong target — supersede its live successor instead). Append the target's id to `derived_from` if not already present: the new version derives from the one it replaces.
8. If `derived_from` is empty (no `--derived-from` and no `--supersedes`) → `E_CREATE_NO_PARENTS`, exit 2 (DG1).
9. Allocate the id: prefix = `id_prefixes["synthetic"]` (default `KB`), number = `next_id` over the scan (00-shared §6).
10. Compute the filename: slug(`--title`) + `.md`, with ingest's slug(): NFKD-normalize, drop non-ASCII, lowercase, collapse every run of characters outside `[a-z0-9]` into a single `-`, trim leading/trailing `-`; an empty result falls back to the lowercased id. **Collision:** treat the candidate path as occupied when it already exists in the target directory **or** when the target directory will be created and the candidate is its implicit CLI-maintained `index.md`; append `-<lowercased id>` to the stem (`retry-policy.md` → `retry-policy-kb-000042.md`, `index.md` → `index-kb-000042.md`). This reservation keeps the document birth distinct from step 12's born-current directory index. Nothing existing or implicit is ever overwritten.
11. Construct and validate the `SyntheticFrontmatter` (00-shared §7): `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`, plus `tags` / `supersedes` / `instructions` when supplied. `timestamp` = `last_human_touch` = the invocation instant as ISO-8601 UTC with seconds precision (`YYYY-MM-DDTHH:MM:SSZ`) — creation is a human-confirmed act, so the two coincide at birth (LS2). When superseding, prepare the target's edit in memory: its `status` value becomes `superseded` and its `timestamp` and `last_human_touch` values become the same instant; **every other byte of the file is preserved** — key order, unknown keys, YAML styles, body. (A conforming target carries all three keys — `status` was just checked; a nonconforming target missing `timestamp` or `last_human_touch` gets the missing key(s) appended at the end of its frontmatter block, in that order.)

**Write phase:**

12. Create missing directories along the target path. Each newly created directory gets its `index.md` in the same operation (directory invariant, 00-shared) — born current per the §5.3 template, already listing its child.
13. Write the new document: the frontmatter block in the pinned key order (§5.1), then `---`, then the body with **no inserted heading or blank line** (nothing at all when the body is empty). Then rewrite the superseded document, if any, per step 11.
14. Regenerate `index.md` listing bodies (grammar: kb-init §5.2): the target directory's (unless it was just created — then it is already current) and, when step 12 created directories, the **nearest pre-existing ancestor's** (its `## Subdirectories` gains the new child). The superseded document's directory index is **not** regenerated for the status flip — its listing line (id, title, description) is unaffected. No other `index.md` is touched; global freshness is `kb index`'s job.
15. Append the log entry (00-shared §8): action `created`, actor `--actor` (default `kb-cli`), ids = the new id, followed by the superseded id when `--supersedes` was used (`KB-000042,KB-000031`), note = `<document relpath>`, with ` supersedes <old id>` appended when superseding. A missing `log.md` is first recreated with the kb-init §5.3 scaffold (frontmatter + header comment + heading, no `initialized` line) and then appended.
16. Report per §6, exit 0.

There is **no de-duplication or content validation**: creating a second document with the same title yields a new document with a new id and a collision-suffixed filename; whether the content is any good is the human's and the skill's concern. Full schema enforcement across the KB (including DG5) is `kb validate`'s job. No step runs `git` or inspects Git state.

## 5. Filesystem effects

### 5.1 The created document (pinned key order)

`kb create --type spec --title "Webhook Retry Policy" --description "Defines retry and backoff behavior for outbound webhooks." --derived-from CHAT-000027 --body-file draft.md` into a KB whose only chat record is `CHAT-000027` writes `synthetic/webhook-retry-policy.md`:

```markdown
---
id: KB-000001
type: spec
title: Webhook Retry Policy
description: Defines retry and backoff behavior for outbound webhooks.
status: draft
derived_from:
  - CHAT-000027
timestamp: 2026-07-16T10:00:00Z
last_human_touch: 2026-07-16T10:00:00Z
---
<body: the --body-file text, line endings normalized to LF, one trailing newline>
```

Key order is pinned as shown: `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`, then — only when supplied — `tags`, `supersedes`, `instructions`, in that order, last. `derived_from` (and `tags`) are always emitted as YAML block sequences with two-space-indented `- ` items, even with a single entry — deterministic, diff-friendly. `timestamp`/`last_human_touch` are the only non-deterministic values (tests pattern-match them, everything else exact). YAML values are emitted in plain style, quoted only when YAML requires it. With an empty body the file ends immediately after the closing `---` line.

### 5.2 Supersession

Given `synthetic/webhook-retry-policy.md` (`KB-000031`, `status: current`) in a KB whose highest synthetic id is `KB-000041`, the run

```
kb create --type spec --title "Webhook Retry Policy" \
  --description "Defines retry and backoff behavior for outbound webhooks." \
  --derived-from CHAT-000040 --supersedes KB-000031 --status current \
  --tag api --tag reliability --instructions "Keep the examples runnable." \
  --body-file draft.md
```

writes the new document as `synthetic/webhook-retry-policy-kb-000042.md` (the slug collides with the superseded document's filename, so the stem takes the `-<lowercased id>` suffix):

```markdown
---
id: KB-000042
type: spec
title: Webhook Retry Policy
description: Defines retry and backoff behavior for outbound webhooks.
status: current
derived_from:
  - CHAT-000040
  - KB-000031
timestamp: 2026-07-16T10:00:00Z
last_human_touch: 2026-07-16T10:00:00Z
tags:
  - api
  - reliability
supersedes: KB-000031
instructions: Keep the examples runnable.
---
<body>
```

`KB-000031` was not listed via `--derived-from`, so it is appended last to `derived_from`. In the same write, `synthetic/webhook-retry-policy.md` changes in exactly three values and nothing else:

```diff
-status: current
+status: superseded
-timestamp: 2026-06-02T14:11:08Z
+timestamp: 2026-07-16T10:00:00Z
-last_human_touch: 2026-06-02T14:11:08Z
+last_human_touch: 2026-07-16T10:00:00Z
```

Its key order, unknown keys, YAML styles, and body are byte-identical before and after.

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
* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md) - Defines retry and backoff behavior for outbound webhooks.
```

Frontmatter `description` is `Documents under <kb-relative dir path>/.` (e.g. `Documents under synthetic/specs/.`); the title is the directory basename verbatim. Body grammar and blank-line layout follow kb-init §5.2 (empty sections omitted; an intermediate directory whose only child is another new directory has a `## Subdirectories` section instead).

### 5.4 Index listing updates

After the §5.1 run, the regenerated `synthetic/index.md` body is:

```markdown
## Files
* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md) - Defines retry and backoff behavior for outbound webhooks.
```

Synthetic documents always carry a `description`, so their listing lines always have the ` - <description>` tail (kb-init §5.2). Regeneration rebuilds the body listing from the directory's current children; the index's own frontmatter `description` is preserved, never regenerated.

### 5.5 `log.md`

One line appended per run (00-shared §8). For the §5.1 run:

```
- 2026-07-16T10:00:00Z | created | kb-cli | KB-000001 | synthetic/webhook-retry-policy.md
```

For the §5.2 supersession run:

```
- 2026-07-16T10:00:00Z | created | kb-cli | KB-000042,KB-000031 | synthetic/webhook-retry-policy-kb-000042.md supersedes KB-000031
```

## 6. Output

**Text (stdout):** one `<created|updated>  <relative path>` line per document or `index.md` written or regenerated — including the superseded document — ordered alphabetically by relative path, then the result line. The `log.md` append is implicit (recorded in the log itself) and not listed. For the §5.2 run:

```
updated  synthetic/index.md
created  synthetic/webhook-retry-policy-kb-000042.md
updated  synthetic/webhook-retry-policy.md
created KB-000042 as synthetic/webhook-retry-policy-kb-000042.md
```

**JSON (`--json`):**

```json
{
  "ok": true,
  "id": "KB-000042",
  "path": "synthetic/webhook-retry-policy-kb-000042.md",
  "superseded": "KB-000031",
  "created": ["synthetic/webhook-retry-policy-kb-000042.md"],
  "updated": ["synthetic/index.md", "synthetic/webhook-retry-policy.md"]
}
```

`path` is the new document, KB-root-relative. `superseded` is the replaced document's id, or `null` when `--supersedes` was not used (the flipped document's path also appears in `updated`). `created`/`updated` are sorted alphabetically and, like the text lines, exclude `log.md`. Errors use the shared envelope `{"error": {"code": "E_...", "message": "..."}}` (00-shared §3).

## 7. Errors and edge cases

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E1 | Not inside a KB (no `kb-config.json` found; also `--kb` pointing at a config-less directory) | `E_NO_KB`, message per 00-shared §1 | 2 |
| E2 | `kb-config.json` unparseable | `E_CONFIG_INVALID` | 2 |
| E3 | Config `schema` newer than the CLI knows | `E_SCHEMA_UNSUPPORTED` | 2 |
| E4 | `KB.malformed` non-empty | `E_CREATE_MALFORMED` naming the malformed paths, directing to `kb validate`; nothing written (id-allocation guard, 00-shared §6) | 2 |
| E5 | Missing required option (`--type`/`--title`/`--description`), bad `--status` value, unknown option | usage error (Typer-rendered message on stderr); no custom code | 2 |
| E6 | `--dest` absolute, or containing `.`/`..` segments, or empty | `E_CREATE_DEST_INVALID` naming the offending value | 2 |
| E7 | `--type` is a reserved type | `E_CREATE_TYPE_RESERVED` naming the type | 2 |
| E8 | `--body-file` path missing, unreadable, or not a regular file | `E_CREATE_BODY_NOT_FOUND` | 2 |
| E9 | Body bytes (file or stdin) do not decode as UTF-8 | `E_CREATE_BODY_NOT_TEXT` | 1 |
| E10 | `derived_from` empty after the implicit `--supersedes` add (no parents at all) | `E_CREATE_NO_PARENTS` (DG1) | 2 |
| E11 | A `--derived-from` unresolvable, or resolves to a document without an id | `E_CREATE_PARENT_UNRESOLVED` naming the ref | 1 |
| E12 | `--supersedes` unresolvable, or resolves to a document without an id | `E_CREATE_SUPERSEDES_UNRESOLVED` naming the ref | 1 |
| E13 | `--supersedes` target not synthetic, or its `status` not `draft`/`current` (already `superseded`, `retired`, or missing) | `E_CREATE_SUPERSEDES_INVALID` naming the target and its status | 1 |
| E14 | OS error during the write phase (steps 12–15) | `E_CREATE_IO` with the OS message; partial files may remain (documented, not rolled back) | 2 |
| E15 | `--type` unreserved but absent from config `types` | one stderr warning naming the type; document written | 0 |
| E16 | A `--tag` absent from the config `tags` vocabulary | one stderr warning naming the tag; tags written as given | 0 |
| E17 | `--description` longer than two sentences (§4 step 4 heuristic) | one stderr warning; never blocks | 0 |
| E18 | Body empty or whitespace-only (or `--body-file` omitted) | empty body — a legitimate draft stub | 0 |
| E19 | Filename collision in the target directory, including a candidate `index.md` reserved for a target directory that will be created | stem suffixed `-<lowercased id>`; no existing file or implicit born index is overwritten | 0 |
| E20 | `log.md` missing at step 15 | recreated with the kb-init §5.3 scaffold (no `initialized` line), then appended | 0 |
| E21 | `--body-file -` on a TTY | reads interactively until EOF (Ctrl-D); not an error | — |

Every pre-flight failure (E1–E13) leaves the KB byte-for-byte untouched (§4).

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`. Each is independently testable with an unambiguous pass condition; `timestamp`/`last_human_touch` and log timestamps are pattern-matched (and cross-checked for equality where stated), everything else asserted exactly. Every §4 step and §7 row maps to at least one AC except E21 (interactive TTY stdin), which is not exercisable through `CliRunner` and stays documented behavior only.

**Coverage map:** happy path & pinned content AC1–AC9 (§4, §5.1, §5.4, §5.5, §6) · id allocation & guard AC10–AC12 (§4 steps 2/9, E4) · parents AC13–AC18 (§4 steps 6/8, E10, E11) · supersession AC19–AC27 (§4 steps 7/11/13/14, §5.2, E12, E13) · type, tags & description warnings AC28–AC31 (§4 step 4, E7, E15–E17) · titles, slugs & collisions AC32–AC34 (§4 step 10, E19) · `--dest` & index effects AC35–AC38 (§4 steps 3/12/14, §5.3, §5.4, E6) · body input AC39–AC40 (§4 step 5, E8, E9; empty-body cases live in AC4) · usage & environment errors AC41–AC44 (E1–E3, E5) · atomicity, I/O & log AC45–AC48 (§4 pre-flight, steps 12–15, E14, E20) · output, help & Git-agnosticism AC49–AC52 (§3, §6, 00-shared).

| # | Given / When / Then |
|---|---|
| AC1 | Given a KB containing one chat record `CHAT-000001`, when `kb create --type spec --title "Webhook Retry Policy" --description "Defines retry and backoff behavior for outbound webhooks." --derived-from CHAT-000001` runs, then exit 0 and `synthetic/webhook-retry-policy.md` exists with frontmatter containing exactly the keys `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch` in that order, with `id == KB-000001`, `type == spec`, `status == draft` (the default), `derived_from == [CHAT-000001]` as a block sequence — and the only changes anywhere under the KB root are that document, `synthetic/index.md`, and one appended `log.md` line. |
| AC2 | Given AC1's run, then `timestamp` and `last_human_touch` are byte-identical to each other and parse as `YYYY-MM-DDTHH:MM:SSZ`. |
| AC3 | Given a `--body-file` with CRLF and lone-CR line endings, no trailing newline, and tricky content (a leading `---` line, Unicode, trailing spaces), when the document is created, then the body — everything after the closing `---` of the frontmatter block — contains only LF line endings, ends with exactly one newline, all other bytes verbatim, with no inserted heading or blank line. |
| AC4 | Given case (a) no `--body-file` and case (b) a `--body-file` containing only whitespace, when the document is created, then exit 0 and the file ends immediately after the closing `---` line (empty body, E18). |
| AC5 | Given body text piped to `--body-file -`, then the document body is that text (normalized per AC3). |
| AC6 | Given AC1's run, then `synthetic/index.md` gained exactly the line `* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md) - Defines retry and backoff behavior for outbound webhooks.` under `## Files` (the description tail present), its frontmatter `description` is unchanged, and no other `index.md` in the KB changed. |
| AC7 | Given AC1's run, then `log.md` gained exactly one line matching `- <timestamp> | created | kb-cli | KB-000001 | synthetic/webhook-retry-policy.md` with `<timestamp>` parsing as ISO-8601 UTC. |
| AC8 | Given AC1's run, then stdout is exactly: `created  synthetic/webhook-retry-policy.md`, `updated  synthetic/index.md` (alphabetical), then `created KB-000001 as synthetic/webhook-retry-policy.md`, with no `log.md` line. |
| AC9 | Given `--status current`, then the frontmatter reads `status: current` (LS1: acceptance at creation). |
| AC10 | Given a KB whose synthetic documents carry ids `KB-000001` and `KB-000005` (a gap), when a document is created, then the new id is `KB-000006` — max+1, gaps never refilled. |
| AC11 | Given case (a) a `kb-config.json` with `id_prefixes.synthetic == "SYN"`, then creation allocates `SYN-000001`; case (b) a `kb-config.json` whose `id_prefixes` key is absent entirely, then the documented default applies and creation allocates `KB-000001` (00-shared §7 `Config` defaults). |
| AC12 | Given a KB containing a `*.md` file whose frontmatter does not parse, when any `kb create` runs, then exit 2 with `E_CREATE_MALFORMED` naming that path, and nothing is written (no file, no index change, no log line). |
| AC13 | Given `--derived-from RAW-000002 --derived-from CHAT-000001 --derived-from KB-000001`, then `derived_from` is emitted as a block sequence in exactly that argument order. |
| AC14 | Given `--derived-from CHAT-000001 --derived-from RAW-000002 --derived-from CHAT-000001` (a duplicate), then `derived_from == [CHAT-000001, RAW-000002]` — first occurrence kept, order preserved. |
| AC15 | Given case (a) `--derived-from raw/chats/planning.md` where that document carries id `CHAT-000001`, then `derived_from` stores `CHAT-000001` (canonical id, not the path); case (b) `--derived-from governance/conventions.md`, then it stores the reserved slug id `GOVERNANCE-CONVENTIONS`. |
| AC16 | Given `--derived-from KB-999999` (no such id), then exit 1 with `E_CREATE_PARENT_UNRESOLVED` and nothing written. |
| AC17 | Given `--derived-from index.md` (resolves to a document without an id), then exit 1 with `E_CREATE_PARENT_UNRESOLVED` and nothing written. |
| AC18 | Given neither `--derived-from` nor `--supersedes`, then exit 2 with `E_CREATE_NO_PARENTS` and nothing written (DG1). |
| AC19 | Given `--supersedes KB-000001 --derived-from CHAT-000002` where `KB-000001` is not among the `--derived-from` values, then `derived_from == [CHAT-000002, KB-000001]` — the superseded id appended last. |
| AC20 | Given `--supersedes KB-000001` and no `--derived-from`, then exit 0 and `derived_from == [KB-000001]` — the implicit parent alone satisfies the ≥1-parent rule. |
| AC21 | Given `--derived-from KB-000001 --derived-from CHAT-000002 --supersedes KB-000001`, then `derived_from == [KB-000001, CHAT-000002]` — no duplicate appended, the explicit position kept. |
| AC22 | Given a superseded target whose frontmatter carries an unknown key and a non-pinned key order, when the supersession runs, then afterwards the target file differs from before in exactly three values — `status: superseded` and its `timestamp`/`last_human_touch` equal to the new document's — and every other byte (key order, unknown key, body) is identical. |
| AC23 | Given the §5.2 supersession run, then the new document's frontmatter contains `supersedes: KB-000031`, and `log.md` gained one line whose ids column is `KB-000042,KB-000031` and whose note is `synthetic/webhook-retry-policy-kb-000042.md supersedes KB-000031`. |
| AC24 | Given `--supersedes KB-999999` (no such id), then exit 1 with `E_CREATE_SUPERSEDES_UNRESOLVED` and nothing written. |
| AC25 | Given `--supersedes RAW-000001` (a raw document), then exit 1 with `E_CREATE_SUPERSEDES_INVALID` and nothing written. |
| AC26 | Given a synthetic target whose `status` is case (a) `superseded`, case (b) `retired`, and case (c) absent, then exit 1 with `E_CREATE_SUPERSEDES_INVALID` and nothing written. |
| AC27 | Given a superseded target in `synthetic/archive/` and a new document created in `synthetic/` (no `--dest`), then the target's file appears under `updated` but `synthetic/archive/index.md` is byte-identical afterwards — the status flip does not regenerate the target's directory index. |
| AC28 | Given `--type index` (case a), `--type chat` (case b), and `--type health` (case c), then exit 2 with `E_CREATE_TYPE_RESERVED` naming the type, nothing written. |
| AC29 | Given case (a) `--type retro` where `retro` is absent from config `types`, then exit 0, the document is written with `type: retro`, and stderr contains one warning naming `retro`; case (b) `--type spec` where `spec` is declared, then no type warning on stderr. |
| AC30 | Given case (a) `--tag api --tag internal` where only `api` is in the config `tags` vocabulary, then exit 0, `tags == [api, internal]` (argument order), and stderr contains one warning naming `internal` only; case (b) all tags declared, then no tag warning. |
| AC31 | Given case (a) a three-sentence `--description`, then exit 0, the description is written verbatim, and stderr contains one length warning; case (b) a two-sentence description, then no length warning. |
| AC32 | Given `--title "Résumé Über 2026!"`, then the document filename is `resume-uber-2026.md` (NFKD → ASCII fold, lowercase, hyphen runs collapsed, trimmed) and frontmatter `title` is the verbatim `Résumé Über 2026!`. |
| AC33 | Given `--title "!!!"` (slugifies to empty), then the document filename falls back to the lowercased id (`kb-000001.md`). |
| AC34 | Given case (a) `synthetic/notes.md` already exists, when a document titled `Notes` is created and receives id `KB-000002`, then the new document is `synthetic/notes-kb-000002.md` and the pre-existing file is byte-identical afterwards; case (b) `--dest a/b` names a target directory that will be created and a document titled `Index` receives id `KB-000001`, then the new document is `synthetic/a/b/index-kb-000001.md`, the CLI-maintained born-current `synthetic/a/b/index.md` remains the directory index and lists that suffixed document, and the normal sorted `created`/`updated` receipts and text/JSON result fields name the suffixed path. |
| AC35 | Given `--dest specs` where `synthetic/specs/` does not exist, then the directory is created with an `index.md` byte-matching §5.3 (description `Documents under synthetic/specs/.`, title `specs`, listing the new document), `synthetic/index.md` is regenerated with `* [specs](specs/index.md) - Documents under synthetic/specs/.` under `## Subdirectories`, and the root index is untouched. |
| AC36 | Given `--dest a/b` where neither directory exists, then both are created with born-current §5.3 indexes (`a`'s listing `b` under `## Subdirectories`, `b`'s listing the document under `## Files`), and only the nearest pre-existing ancestor's index (`synthetic/index.md`) is regenerated. |
| AC37 | Given `--dest specs` where `synthetic/specs/` already exists with its index, then only `synthetic/specs/index.md` is regenerated (`updated`); `synthetic/index.md` is untouched. |
| AC38 | Given `--dest /abs` (case a) and `--dest ../escape` (case b), then exit 2 with `E_CREATE_DEST_INVALID` naming the value, nothing written. |
| AC39 | Given `--body-file /nonexistent` (case a) and `--body-file <a directory>` (case b), then exit 2 with `E_CREATE_BODY_NOT_FOUND`, nothing written. |
| AC40 | Given non-UTF-8 bytes from case (a) a `--body-file` file and case (b) piped `--body-file -`, then exit 1 with `E_CREATE_BODY_NOT_TEXT` and nothing written. |
| AC41 | Given case (a) `kb create` run in a directory with no `kb-config.json` in it or any ancestor, and case (b) `--kb` pointing at an existing directory that contains no `kb-config.json`, then exit 2 with `E_NO_KB` and the 00-shared §1 message; nothing written. |
| AC42 | Given a KB whose `kb-config.json` contains invalid JSON, when a create runs, then exit 2 with `E_CONFIG_INVALID` and nothing written. |
| AC43 | Given a KB whose `kb-config.json` has `schema` newer than the CLI knows (e.g. `999`), when a create runs, then exit 2 with `E_SCHEMA_UNSUPPORTED` and nothing written. |
| AC44 | Given case (a) no `--type`, case (b) `--status bogus`, and case (c) an unknown option `--bogus-flag`, then exit 2 with a usage error on stderr and nothing written (E5). |
| AC45 | Given a failing pre-flight run (AC16's setup), then afterwards every file in the KB is byte-identical to before — no document, no index change, no log line (pre-flight atomicity). |
| AC46 | Given the target directory made unwritable so that pre-flight passes but the write phase fails, when a create runs, then exit 2 with `E_CREATE_IO` and the OS message (E14; partial state permitted, not rolled back; skipif on platforms without POSIX permissions). |
| AC47 | Given `--actor kb-author`, then the log line's actor column is `kb-author`. |
| AC48 | Given a KB whose `log.md` was deleted, when a create runs, then `log.md` exists afterwards with the kb-init §5.3 scaffold (frontmatter `type: log`, header comment, heading), no `initialized` line, and exactly one `created` line. |
| AC49 | Given `--json` on the §5.2 supersession run, then stdout parses as JSON with exactly the fields `ok` (true), `id`, `path`, `superseded` (the old id), `created`/`updated` (alphabetically sorted arrays of relative paths, `updated` containing the superseded document's path, both excluding `log.md`), and nothing else on stdout; a run without `--supersedes` yields `superseded: null`. |
| AC50 | Given `--json` on a failing run (AC16's setup), then stdout is exactly the envelope `{"error": {"code": "E_CREATE_PARENT_UNRESOLVED", "message": …}}` and exit is 1. |
| AC51 | When `kb create --help` runs, then exit 0 and the output contains every normative string from §3 — each description sentence, each option help string, each example line. |
| AC52 | Given AC1's run, then no `git` subprocess was invoked (PATH shim or subprocess spy) and no `.git/` directory exists (Git-agnostic). |

## 9. Out of scope

- **Judgment about content**: what to write, which parents are right, `draft` vs `current` — the human's and the `kb-author` skill's job (AUT-1…AUT-5); this command records their decisions mechanically.
- **DG5 (session-record parentage) enforcement** — `kb validate` is the single authoritative enforcement point. The recommended flow ingests the session record first (`kb ingest --class chat`), then supplies its id among `--derived-from`.
- **DG3 coverage-note updates to parent documents** (AUT-6 "updates parents' coverage notes where applicable") — the `kb-author` skill's job; `kb create` never modifies parents (only the `--supersedes` target, and only its three lifecycle values).
- **In-place revision** of an existing synthetic document — editorial body/frontmatter edits, adding a parent after creation, status changes short of supersession — deferred (OQ6); v1 expresses semantic revision as supersession via `--supersedes`.
- **Transitive supersession propagation** to the superseded document's descendants (CS3) — skill judgment, driven through query commands.
- **Full FM1/FM1b schema and vocabulary enforcement** across the KB (including tag vocabulary and the `--description` length as an error) — `kb validate`'s job; this command only warns at the moment of creation.
- De-duplication of same-titled or similar documents — collision-suffixed filenames, never merged.
- **All Git operations** (00-shared): create never runs `git` or inspects Git state.
