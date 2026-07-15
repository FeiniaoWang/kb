# Spec: `kb init`

**Implementation context:** this file + [00-shared.md](00-shared.md).
**Traceability:** PRD CLI-11, INIT-1 (scaffold portion), Appendix A layout. The steward interview (INIT-2) and adoption (INIT-3) belong to the `kb-init` skill, not this command.

## 1. Purpose

Scaffold a new knowledge base — or repair the scaffold of an existing one — so that every other `kb` command has a root to discover and a valid empty structure to operate on. `kb init` is the only command that runs without an existing `kb-config.json` root marker.

## 2. CLI surface

```
kb init [--root PATH] [--force] [--json]
```

Run `kb init` from the folder you want to become the KB root; it scaffolds the current directory by default. Use `--root` only when scaffolding a different folder.

The command is **Git-agnostic**: it creates files and never runs `git` (no `git init`, no detection, no commit). Placing the KB under version control is the user's or a skill's job (§9).

| Param | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `--root` | option | directory path | current directory | Folder to become the KB root; resolved to an absolute path, created (with parents) if missing |
| `--force` | option | flag | off | Re-write scaffold files that already exist with pristine versions |
| `--json` | option | flag | off | Structured output (§6) |

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Scaffold a new knowledge base, or repair an existing one.
>
> Run this from the folder you want to become the KB root; it scaffolds the current directory by default (pass --root to target a different folder). Creates the standard KB layout (raw/, synthetic/, governance/), the root index.md and log.md, and kb-config.json — the file at the KB root that holds project configuration and marks the root for every other command. Safe to re-run: existing files are never touched unless --force is given. Does not touch Git — putting the KB under version control is up to you.

**Option help strings:**

| Param | Help string |
|---|---|
| `--root` | Folder to become the KB root. Resolved to an absolute path and created if it does not exist. [default: current directory] |
| `--force` | Overwrite existing scaffold files with pristine versions. Documents are never touched. |
| `--json` | Emit results as JSON. |

**Examples section:**

```
Examples:
  kb init                       Scaffold a KB in the current directory (the KB root)
  kb init --root ~/team-kb      Scaffold a KB at the given path
  kb init --force               Restore pristine scaffold files (documents untouched)
  kb init --json                Machine-readable scaffold output
```

## 4. Behavior (normative algorithm)

1. Determine the root: `--root` if given, else the current directory. Resolve it to an absolute path (call it `ROOT`). If it exists and is not a directory → `E_INIT_NOT_DIR`, exit 2. If missing, create it with parents.
2. For each scaffold entry in §5, classify and act:
   - absent → **create** with the pinned content;
   - present, `--force` given → **overwrite** with the pinned content (scaffold files only — nothing under `raw/sources/`, `raw/chats/`, `raw/feedback/`, or `synthetic/` other than the listed `index.md` files is ever written);
   - present, no `--force` → **skip**, no write.
3. **Log.** Append an `initialized` entry to `log.md` (format: 00-shared §8, actor `kb-cli`, note `KB scaffolded by kb init`) — but only if `log.md` does not already contain an `initialized` entry. Re-runs never add duplicate entries.
4. Report per §6. Exit 0 for every outcome that reaches this step.

`kb init` does **not** check whether `ROOT` is already inside another KB; running it inside an existing KB simply creates a nested root, and the closest ancestor `kb-config.json` wins during discovery (00-shared §1). No Git operation occurs at any step.

## 5. Filesystem effects — scaffold manifest (contents verbatim)

```
ROOT/
├── kb-config.json           # root marker + project configuration (machine-read)
├── index.md                 # every directory has one (DocClass INDEX)
├── log.md
├── governance/
│   ├── index.md
│   ├── conventions.md       # GOVERNANCE-CONVENTIONS
│   ├── kb-config.md         # GOVERNANCE-KB-CONFIG — human-readable field reference for kb-config.json
│   └── templates/
│       └── index.md
├── raw/
│   ├── index.md
│   ├── sources/
│   │   └── index.md
│   ├── chats/
│   │   └── index.md
│   └── feedback/
│       └── index.md
└── synthetic/
    └── index.md
```

Twelve files: `kb-config.json`, `log.md`, the two governance documents, and **eight `index.md` files — one per directory** (root, `governance/`, `governance/templates/`, `raw/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, `synthetic/`). There are no `.gitkeep` files — every directory is kept non-empty by its `index.md`. `kb-config.json` at the root is both the discovery marker and the config. `governance/health.md` is deliberately absent — it is `kb-lint` output, created when lint first runs.

### 5.1 `kb-config.json` (root — marker + configuration)

Clean, strict JSON (stdlib `json`-parseable — no trailing commas, no comments, no annotation keys). Field-by-field documentation lives in `governance/kb-config.md` (id `GOVERNANCE-KB-CONFIG`, §5.5), not inside the data file. Pinned content:

```json
{
  "schema": 1,
  "types": [],
  "tags": [],
  "id_prefixes": {
    "synthetic": "KB",
    "source": "RAW",
    "chat": "CHAT",
    "feedback": "FEED"
  },
  "propagation_auto_safe": []
}
```

The pinned file is byte-for-byte fixed (it contains no timestamp). Indentation is two spaces; keys appear in the order above. `schema` is the reserved, tooling-owned layout version (00-shared §1).

### 5.2 `index.md` (every directory — `DocClass INDEX`, CLI-maintained)

Every directory carries an `index.md` with frontmatter (`type: index` → `DocClass INDEX`, plus `description`) and **no `id`** — index documents are addressed by path (00-shared §5, §6). `index.md` files are **maintained only by the CLI and are read-only** for humans and agents: `kb init` writes them, `kb index` regenerates their listing, `kb ingest`/`kb mv` refresh them; nobody edits them by hand. The whole file is machine-owned. Pinned template:

```markdown
---
type: index
description: <DESCRIPTION>
---
# <TITLE>

<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->

## Subdirectories
* [<child-index-title>](<dir-name>/index.md) - <subdirectory description>

## Files
* [<file-id>][<file-title>](<file-name>.md) - <file description>
```

- The body has up to two sections, **each omitted when it has no entries**:
  - `## Subdirectories` — one `* [<title>](<dir-name>/index.md) - <description>` line per immediate child directory, alphabetical by directory name. `<title>` is the child directory's index.md `# <TITLE>`; `<description>` is its frontmatter `description`. Each link targets the child's `index.md`, so navigation walks down the index tree.
  - `## Files` — one `* [<id>][<title>](<file-name>.md) - <description>` line per immediate child document, alphabetical by filename. `<id>`, `<title>`, and `<description>` come from the document's frontmatter (documents always carry an `id`; a subdirectory's `index.md` appears under Subdirectories, never here).
  - Operational files (`log.md`, `kb-config.json`) and the directory's own `index.md` are never listed. When **both** sections are empty the body is just the generated-header comment; when only one is empty, only that header is omitted.
- Blank-line layout: one blank line after `# <TITLE>`, then the generated-header comment, one blank line, then the section(s) — with one blank line between `## Subdirectories` and `## Files`.
- `<DESCRIPTION>` (frontmatter) is set at directory creation (pinned below for the scaffold; a default is generated for directories created later by `kb ingest`) and is CLI-owned.

Per-directory pinned frontmatter and title:

| Path | `<TITLE>` | `<DESCRIPTION>` |
|---|---|---|
| `index.md` | `Knowledge Base` | `Root of the knowledge base — raw evidence, synthetic documents, and governance.` |
| `governance/index.md` | `Governance` | `Project governance — configuration, conventions, and templates.` |
| `governance/templates/index.md` | `Templates` | `Optional per-type document templates.` |
| `raw/index.md` | `Raw Evidence` | `Immutable evidence — sources, session records, and feedback.` |
| `raw/sources/index.md` | `Sources` | `Normalized external evidence (immutable).` |
| `raw/chats/index.md` | `Session Records` | `Session records from kb-author and kb-ingest sessions (immutable).` |
| `raw/feedback/index.md` | `Feedback` | `Consumer feedback about synthetic documents (immutable).` |
| `synthetic/index.md` | `Synthetic Documents` | `Human-created, agent-maintained documents (the derivation graph).` |

Five of the eight are leaf directories with no children, so their body is the generated-header comment and nothing else: `governance/templates/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, and `synthetic/`. The other three ship these pinned bodies (the block that follows the generated-header comment). Because every listing line's `<description>` is sourced from the child's own `description`, these are identical to the `<DESCRIPTION>` values in the table above.

`index.md` (root) — three subdirectories, no files:

```markdown
## Subdirectories
* [Governance](governance/index.md) - Project governance — configuration, conventions, and templates.
* [Raw Evidence](raw/index.md) - Immutable evidence — sources, session records, and feedback.
* [Synthetic Documents](synthetic/index.md) - Human-created, agent-maintained documents (the derivation graph).
```

`governance/index.md` — one subdirectory and two documents:

```markdown
## Subdirectories
* [Templates](templates/index.md) - Optional per-type document templates.

## Files
* [GOVERNANCE-CONVENTIONS][Project Conventions](conventions.md) - Standing conventions for this knowledge base. Human-maintained.
* [GOVERNANCE-KB-CONFIG][KB Configuration Reference](kb-config.md) - Explains each field in the root kb-config.json. Human-readable companion to the machine-read config.
```

`raw/index.md` — three subdirectories, no files:

```markdown
## Subdirectories
* [Session Records](chats/index.md) - Session records from kb-author and kb-ingest sessions (immutable).
* [Feedback](feedback/index.md) - Consumer feedback about synthetic documents (immutable).
* [Sources](sources/index.md) - Normalized external evidence (immutable).
```

Every scaffolded `index.md` is byte-for-byte fixed (no timestamps).

### 5.3 `log.md`

Operational file (CLI-appended by `kb log`, excluded from the document set), but it still carries a `type: log` frontmatter field so it satisfies OKF's every-markdown-file `type` requirement (00-shared §5). `type: log` maps to the operational classification, not a `DocClass`.

```markdown
---
type: log
---
<!-- KB history — append-only; written by `kb log`. Format: - <UTC ISO> | <action> | <actor> | <ids or -> | <note> -->
# Knowledge Base Log

- <ISO-8601 UTC now> | initialized | kb-cli | - | KB scaffolded by kb init
```

(The timestamp is the only non-literal byte in the scaffold; everything else is byte-pinned.)

### 5.4 `governance/conventions.md`

A governance document (`DocClass GOVERNANCE`) with the reserved fixed id `GOVERNANCE-CONVENTIONS` (00-shared §6), so agents can read it by a known id without discovery.

```markdown
---
id: GOVERNANCE-CONVENTIONS
type: conventions
title: Project Conventions
description: Standing conventions for this knowledge base. Human-maintained.
---
# Project Conventions

Standing conventions for this knowledge base. Human-maintained.

## Writing
(none yet)

## Structure
(none yet)
```

### 5.5 `governance/kb-config.md`

A governance document (`DocClass GOVERNANCE`) with the reserved fixed id `GOVERNANCE-KB-CONFIG` — the human-readable field reference for the machine-read `kb-config.json` (§5.1). Agents read this to understand the config; the CLI reads `kb-config.json`.

```markdown
---
id: GOVERNANCE-KB-CONFIG
type: kb-config
title: KB Configuration Reference
description: Explains each field in the root kb-config.json. Human-readable companion to the machine-read config.
---
# KB Configuration Reference

The project's configuration and root marker is `kb-config.json` at the KB root.
It is strict JSON, read directly by `kb` commands. Edit the fields below to suit
the project; `schema` is managed by `kb` — do not edit it.

## Fields

- **`schema`** — KB layout schema version. Reserved and tooling-owned; `kb`
  refuses a KB whose schema is newer than the CLI understands.
- **`types`** — document type vocabulary (open list). Examples: `outcome`,
  `ux-flow`, `coding-spec`, `test-plan`, `adr`, `runbook`, `context-package`.
  An empty list means types are not yet constrained.
- **`tags`** — tag vocabulary. `kb validate` flags any document tag not listed
  here. An empty list means no tags are declared.
- **`id_prefixes`** — the id prefix used per document class: `synthetic` (`KB`),
  `source` (`RAW`), `chat` (`CHAT`), `feedback` (`FEED`). Ids are `<PREFIX>-<6+ digits>`.
- **`propagation_auto_safe`** — change classes governance considers auto-safe
  during propagation (CS3). Start empty; expand from field data (PRD OQ1).
```

(All eight `index.md` files are specified in §5.2; there are no `.gitkeep` files.)

## 6. Output

**Text (stdout):** one line per manifest entry, `<created|overwritten|skipped>  <relative path>` (skips annotated `(exists)`), then a summary line:

```
KB ready at /abs/path — 12 created, 0 overwritten, 0 skipped
```

**JSON (`--json`):**

```json
{
  "ok": true,
  "root": "/abs/path",
  "created": ["<relative paths>"],
  "overwritten": [],
  "skipped": []
}
```

## 7. Errors and edge cases

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E1 | `ROOT` exists and is a file | `E_INIT_NOT_DIR` — `target exists and is not a directory: <path>` | 2 |
| E2 | Target unwritable / OS error mid-scaffold | `E_INIT_IO` with the OS message; partial files may remain (documented, not rolled back) | 2 |
| E3 | Healthy KB, re-run, no flags | all entries skipped, zero writes, no new log entry | 0 |
| E4 | Re-run with `--force` | scaffold files rewritten pristine; documents and non-manifest files untouched | 0 |
| E5 | Partial scaffold (some files deleted) | missing entries recreated, present ones skipped (repair) | 0 |
| E6 | `ROOT` is inside an existing KB | allowed — a nested KB root is created (no nesting check); closest ancestor `kb-config.json` wins during discovery | 0 |

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`.

| # | Given / When / Then |
|---|---|
| AC1 | Given an empty dir, when `kb init` runs, then every §5 manifest path exists with byte-identical pinned content (timestamp line pattern-matched) and exit is 0. |
| AC2 | Given AC1's run, then stdout lists each entry as `created` and the summary line matches the §6 form. |
| AC3 | Given a scaffolded KB, when `kb init` re-runs, then exit 0, all entries `skipped`, and no file's mtime/content changed. |
| AC4 | Given three consecutive runs, then `log.md` contains exactly one `initialized` entry. |
| AC5 | Given a KB where `kb-config.json` was edited, when `kb init --force` runs, then the file is restored byte-identical to §5.1. |
| AC6 | Given a fresh `kb init` KB, then `kb-config.json` parses with stdlib `json`, contains **exactly** the keys `schema`, `types`, `tags`, `id_prefixes`, `propagation_auto_safe` (no `_comment*` keys), with `schema == 1`, `types == []`, `tags == []`, `id_prefixes == {synthetic:KB, source:RAW, chat:CHAT, feedback:FEED}`, and `propagation_auto_safe == []`. |
| AC7 | Given a fresh `kb init` KB, then `governance/conventions.md` frontmatter has `id == GOVERNANCE-CONVENTIONS` and `governance/kb-config.md` has `id == GOVERNANCE-KB-CONFIG` (parsed from the pinned files). Resolving them by id and confirming `DocClass GOVERNANCE` is covered by the scan spec; marked `xfail` here until the scan exists. |
| AC7a | Given a fresh `kb init` KB, then exactly eight `index.md` files exist (root, `governance/`, `governance/templates/`, `raw/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, `synthetic/`), each parses with frontmatter `type: index`, carries a `description`, has **no** `id` key, and its body byte-matches the §5.2 pinned content for that path (generated-header comment plus the two-section body — `## Subdirectories` / `## Files`, with empty sections omitted). |
| AC7b | Given a fresh `kb init` KB, then no file named `.gitkeep` exists anywhere under the root. |
| AC7c | Given a fresh `kb init` KB, then **every** scaffolded `*.md` file carries a `type` frontmatter field (OKF-mandatory): the eight `index.md` have `type: index`, `governance/conventions.md` has `type: conventions`, `governance/kb-config.md` has `type: kb-config`, and `log.md` has `type: log`. |
| AC8 | Given a KB containing a document at `raw/sources/x.md`, when `kb init --force` runs, then that document is byte-identical afterwards. |
| AC9 | Given a file at path `P`, when `kb init --root P` runs, then exit 2 with `E_INIT_NOT_DIR`. |
| AC10 | Given a nonexistent nested path `x/y/z`, when `kb init --root x/y/z` runs, then the directories are created and scaffolded, exit 0. |
| AC11 | Given an empty dir as cwd with no `--root`, when `kb init` runs, then that cwd (resolved absolute) becomes the KB root and is scaffolded, exit 0. |
| AC12 | Given an existing KB at `/a`, when `kb init --root /a/b` runs, then exit 0 and a nested KB root is scaffolded at `/a/b` (no nesting guard). |
| AC13 | Given a KB with `log.md` and `raw/index.md` deleted, when `kb init` re-runs, then exactly those are recreated (`created`), the rest `skipped`. |
| AC14 | Given a plain dir that is not a Git repo, when `kb init` runs, then no `.git/` directory is created, no `git` subprocess is invoked, and the JSON output contains no `git` key (the command is Git-agnostic). |
| AC15 | Given `--json`, then output parses as JSON and contains exactly the §6 fields with correct types. |
| AC16 | When `kb init --help` runs, then output contains every normative string from §3 (description sentences, each option help string, each example line) and makes no mention of Git operations. |
| AC17 | Given a fresh `kb init` KB, when `kb validate` runs, then it exits 0 (scaffold is born valid). Marked `xfail` until `kb validate` is implemented; flips to a hard gate then. |
| AC18 | Given an unwritable target dir, when `kb init` runs, then exit 2 with `E_INIT_IO` (skipif on platforms without POSIX permissions). |

## 9. Out of scope

- Steward interview / governance authoring (INIT-2 — `kb-init` skill).
- Adopting existing documents into conformance (INIT-3 — `kb-init` skill).
- Any file generation beyond the §5 manifest; no inference, no content synthesis.
- **All Git operations.** `kb init` never runs `git init`, staging, or commits, and never inspects Git state. The KB lives in Git (NFR-1/NFR-7), but initializing and managing the repository is the user's or a skill's responsibility.
- Regenerating `index.md` listings after scaffold — that is `kb index`'s job; `kb init` only writes the initial pinned content.
- Rollback of partially written scaffolds on I/O error (documented in E2).
- Any check for whether `ROOT` is already inside a KB (no nesting guard); nested roots are permitted (E6).
