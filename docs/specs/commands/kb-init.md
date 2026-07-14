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
2. **Nesting guard.** Walk up from `ROOT`'s parent to the filesystem root. If any ancestor directory contains a `kb-config.json` file → `E_INIT_NESTED` (message names the enclosing KB root), exit 2, nothing created. `--force` does NOT override this.
3. For each scaffold entry in §5, classify and act:
   - absent → **create** with the pinned content;
   - present, `--force` given → **overwrite** with the pinned content (scaffold files only — nothing under `raw/sources/`, `raw/chats/`, `raw/feedback/`, or `synthetic/` other than the listed `index.md` files is ever written);
   - present, no `--force` → **skip**, no write.
4. **Log.** Append an `initialized` entry to `log.md` (format: 00-shared §8, actor `kb-cli`, note `KB scaffolded by kb init`) — but only if `log.md` does not already contain an `initialized` entry. Re-runs never add duplicate entries.
5. Report per §6. Exit 0 for every outcome that reaches this step.

No Git operation occurs at any step.

## 5. Filesystem effects — scaffold manifest (contents verbatim)

```
ROOT/
├── kb-config.json           # root marker + project configuration
├── index.md
├── log.md
├── governance/
│   ├── conventions.md
│   └── templates/.gitkeep
├── raw/
│   ├── index.md
│   ├── sources/.gitkeep
│   ├── chats/.gitkeep
│   └── feedback/.gitkeep
└── synthetic/
    └── index.md
```

`kb-config.json` at the root is both the discovery marker and the config — there is no separate `.kb` file (00-shared §1). `governance/health.md` is deliberately absent — it is `kb-lint` output, created when lint first runs.

### 5.1 `kb-config.json` (root — marker + configuration)

Strict JSON (stdlib `json`-parseable — no trailing commas, no comments). `_comment*` keys carry the steward guidance JSON cannot express as comments; `load_config` ignores every `_`-prefixed key (00-shared §7). Pinned content:

```json
{
  "_comment": "Project configuration and KB root marker. Edit the vocab fields below; kb commands read this file directly. 'schema' is managed by kb — do not edit.",
  "schema": 1,

  "_comment_types": "Document type vocabulary (open list). Examples: outcome, ux-flow, coding-spec, test-plan, adr, runbook, context-package. Empty means not yet constrained.",
  "types": [],

  "_comment_tags": "Tag vocabulary. kb validate flags tags not listed here. Empty means no tags declared.",
  "tags": [],

  "_comment_id_prefixes": "Id prefix per document class.",
  "id_prefixes": {
    "synthetic": "KB",
    "source": "RAW",
    "chat": "CHAT",
    "feedback": "FEED"
  },

  "_comment_propagation_auto_safe": "Change classes governance considers auto-safe during propagation (CS3). Start empty; expand from field data (PRD OQ1).",
  "propagation_auto_safe": []
}
```

The pinned file is byte-for-byte fixed (it contains no timestamp). Indentation is two spaces; keys appear in the order above.

### 5.2 `index.md` (root)

```markdown
<!-- generated by `kb index` — do not edit; run `kb index` to regenerate -->
# Knowledge Base Index

_No documents yet. Run `kb ingest` to add evidence or start a `kb-author` session._

## raw/
(empty)

## synthetic/
(empty)

## governance/
- conventions.md — Standing project conventions.
```

(The root `kb-config.json` is configuration, not a listed document, so it does not appear in the index.)

### 5.3 `log.md`

```markdown
<!-- KB history — append-only; written by `kb log`. Format: - <UTC ISO> | <action> | <actor> | <ids or -> | <note> -->
# Knowledge Base Log

- <ISO-8601 UTC now> | initialized | kb-cli | - | KB scaffolded by kb init
```

(The timestamp is the only non-literal byte in the scaffold; everything else is byte-pinned.)

### 5.4 `governance/conventions.md`

```markdown
---
type: conventions
---
# Project Conventions

Standing conventions for this knowledge base. Human-maintained.

## Writing
(none yet)

## Structure
(none yet)
```

### 5.5 `raw/index.md` and `synthetic/index.md`

Same generated header as §5.2, title `# Index — raw/` / `# Index — synthetic/`, body `(empty)`.

### 5.6 `.gitkeep` files

Zero bytes. Placed in `governance/templates/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`. These are ordinary placeholder files that let the otherwise-empty directories persist in the Git-backed repository the KB lives in (NFR-1); `kb init` writes them as plain files and runs no Git commands.

## 6. Output

**Text (stdout):** one line per manifest entry, `<created|overwritten|skipped>  <relative path>` (skips annotated `(exists)`), then a summary line:

```
KB ready at /abs/path — 10 created, 0 overwritten, 0 skipped
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
| E2 | An ancestor of `ROOT` contains `kb-config.json` | `E_INIT_NESTED` — `already inside a knowledge base rooted at <root>` | 2 |
| E3 | Target unwritable / OS error mid-scaffold | `E_INIT_IO` with the OS message; partial files may remain (documented, not rolled back) | 2 |
| E4 | Healthy KB, re-run, no flags | all entries skipped, zero writes, no new log entry | 0 |
| E5 | Re-run with `--force` | scaffold files rewritten pristine; documents and non-manifest files untouched | 0 |
| E6 | Partial scaffold (some files deleted) | missing entries recreated, present ones skipped (repair) | 0 |

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`.

| # | Given / When / Then |
|---|---|
| AC1 | Given an empty dir, when `kb init` runs, then every §5 manifest path exists with byte-identical pinned content (timestamp line pattern-matched) and exit is 0. |
| AC2 | Given AC1's run, then stdout lists each entry as `created` and the summary line matches the §6 form. |
| AC3 | Given a scaffolded KB, when `kb init` re-runs, then exit 0, all entries `skipped`, and no file's mtime/content changed. |
| AC4 | Given three consecutive runs, then `log.md` contains exactly one `initialized` entry. |
| AC5 | Given a KB where `kb-config.json` was edited, when `kb init --force` runs, then the file is restored byte-identical to §5.1. |
| AC6 | Given a fresh `kb init` KB, then `kb-config.json` parses with stdlib `json` and contains `schema == 1`, `types == []`, `tags == []`, `id_prefixes == {synthetic:KB, source:RAW, chat:CHAT, feedback:FEED}`, and `propagation_auto_safe == []`. |
| AC7 | Given a KB containing a document at `raw/sources/x.md`, when `kb init --force` runs, then that document is byte-identical afterwards. |
| AC8 | Given a KB at `/a`, when `kb init --root /a/b` runs, then exit 2, `E_INIT_NESTED` names `/a`, and `/a/b` gained no files. |
| AC9 | Given the AC8 setup, when `kb init --root /a/b --force` runs, then it is still refused identically. |
| AC10 | Given a file at path `P`, when `kb init --root P` runs, then exit 2 with `E_INIT_NOT_DIR`. |
| AC11 | Given a nonexistent nested path `x/y/z`, when `kb init --root x/y/z` runs, then the directories are created and scaffolded, exit 0. |
| AC12 | Given an empty dir as cwd with no `--root`, when `kb init` runs, then that cwd (resolved absolute) becomes the KB root and is scaffolded, exit 0. |
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
- **All Git operations.** `kb init` never runs `git init`, staging, or commits, and never inspects Git state. The KB lives in Git (NFR-1/NFR-7), but initializing and managing the repository is the user's or a skill's responsibility. (`.gitkeep` files in §5.6 are inert placeholders, not a Git operation.)
- Rollback of partially written scaffolds on I/O error (documented in E3).
