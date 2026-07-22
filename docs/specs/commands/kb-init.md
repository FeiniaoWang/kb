# Spec: `kb init`

**Implementation context:** [PRD](../../prd.md) + [00-shared.md](00-shared.md) + this file. Precedence: PRD > this command spec > shared contract.
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
| `--force` | option | flag | off | Re-write **CLI-owned** scaffold files (`kb-config.json` and the eight `index.md`) with pristine versions; never touches `log.md`, the governance documents, or any KB document |
| `--json` | option | flag | off | Structured output (§6) |

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Scaffold a new knowledge base, or repair an existing one.
>
> Run this from the folder you want to become the KB root; it scaffolds the current directory by default (pass --root to target a different folder). Creates the standard KB layout (raw/, synthetic/, governance/), the root index.md and log.md, and kb-config.json — the file at the KB root that holds project configuration and marks the root for every other command. Safe to re-run: existing files are never touched; --force restores pristine kb-config.json and index.md files, but documents and log.md are never overwritten. Does not touch Git — putting the KB under version control is up to you.

**Option help strings:**

| Param | Help string |
|---|---|
| `--root` | Folder to become the KB root. Resolved to an absolute path and created if it does not exist. [default: current directory] |
| `--force` | Restore pristine kb-config.json and index.md files. Documents and log.md are never touched. |
| `--json` | Emit results as JSON. |

**Examples section:**

```
Examples:
  kb init                       Scaffold a KB in the current directory (the KB root)
  kb init --root ~/team-kb      Scaffold a KB at the given path
  kb init --force               Restore pristine kb-config.json and index.md files
  kb init --json                Machine-readable scaffold output
```

## 4. Behavior (normative algorithm)

1. Determine the root: `--root` if given, else the current directory. Resolve it to an absolute path (call it `ROOT`). If it exists and is not a directory → `E_INIT_NOT_DIR`, exit 2. If missing, create it with parents.
2. The manifest divides into **CLI-owned** entries (`kb-config.json` and the eight `index.md`) and **protected** entries (`log.md`, `governance/charter.md`, `governance/conventions.md`, `governance/kb-config.md` — append-only history and human-maintained documents). For each scaffold entry in §5, classify and act:
   - absent → **create** with the pinned content;
   - present, CLI-owned, `--force` given → **overwrite** with the pinned content;
   - present otherwise → **skip**, no write. Protected entries are never overwritten, with or without `--force`; nothing outside the manifest is ever written (no file under `raw/sources/`, `raw/chats/`, `raw/feedback/`, or `synthetic/` other than the listed `index.md` files).
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
│   ├── charter.md           # GOVERNANCE-CHARTER — KB purpose: who it serves, consumers, architectural intent
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

Thirteen files: `kb-config.json`, `log.md`, the three governance documents, and **eight `index.md` files — one per directory** (root, `governance/`, `governance/templates/`, `raw/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, `synthetic/`). There are no `.gitkeep` files — every directory is kept non-empty by its `index.md`. `kb-config.json` at the root is both the discovery marker and the config. `governance/health.md` is deliberately absent — it is `kb-lint` output, created when lint first runs.

### 5.1 `kb-config.json` (root — marker + configuration)

Clean, strict JSON (stdlib `json`-parseable — no trailing commas, no comments, no annotation keys). Field-by-field documentation lives in `governance/kb-config.md` (id `GOVERNANCE-KB-CONFIG`, §5.6), not inside the data file. Pinned content:

```json
{
  "schema": 1,
  "types": [],
  "tags": [],
  "link_types": ["references", "contradicts", "constrains"],
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
  - `## Files` — one `* [<id>][<title>](<file-name>.md) - <description>` line per immediate listable child document, alphabetical by filename. `<id>`, `<title>`, and `<description>` come from the document's frontmatter (listable raw, synthetic, and governance documents carry an id; a subdirectory's `index.md` appears under Subdirectories, while operational files are omitted). A document without a `description` renders without the ` - <description>` tail — `* [<id>][<title>](<file-name>.md)` (raw documents carry a `title` but never a `description`; see kb-ingest).
  - The operational document `log.md`, the configuration file `kb-config.json`, and the directory's own `index.md` are never listed. When **both** sections are empty the body is just the generated-header comment; when only one is empty, only that header is omitted.
- Blank-line layout: one blank line after `# <TITLE>`, then the generated-header comment, one blank line, then the section(s) — with one blank line between `## Subdirectories` and `## Files`.
- `<DESCRIPTION>` (frontmatter) is set at directory creation (pinned below for the scaffold; a default is generated for directories created later by `kb ingest`) and is CLI-owned.

Per-directory pinned frontmatter and title:

| Path | `<TITLE>` | `<DESCRIPTION>` |
|---|---|---|
| `index.md` | `Knowledge Base` | `Root of the knowledge base — raw evidence, synthetic documents, and governance.` |
| `governance/index.md` | `Governance` | `Project governance — purpose, configuration, conventions, and templates.` |
| `governance/templates/index.md` | `Templates` | `Optional per-type document templates.` |
| `raw/index.md` | `Raw Evidence` | `Immutable evidence — sources, session records, and feedback.` |
| `raw/sources/index.md` | `Sources` | `Normalized external evidence (immutable).` |
| `raw/chats/index.md` | `Session Records` | `Session records from kb-author and kb-ingest sessions (immutable).` |
| `raw/feedback/index.md` | `Feedback` | `Consumer feedback about synthetic documents (immutable).` |
| `synthetic/index.md` | `Synthetic Documents` | `Human-directed, agent-maintained documents (the derivation graph).` |

Five of the eight are leaf directories with no children, so their body is the generated-header comment and nothing else: `governance/templates/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, and `synthetic/`. The other three ship these pinned bodies (the block that follows the generated-header comment). Because every listing line's `<description>` is sourced from the child's own `description`, these are identical to the `<DESCRIPTION>` values in the table above.

`index.md` (root) — three subdirectories, no files:

```markdown
## Subdirectories
* [Governance](governance/index.md) - Project governance — purpose, configuration, conventions, and templates.
* [Raw Evidence](raw/index.md) - Immutable evidence — sources, session records, and feedback.
* [Synthetic Documents](synthetic/index.md) - Human-directed, agent-maintained documents (the derivation graph).
```

`governance/index.md` — one subdirectory and three documents:

```markdown
## Subdirectories
* [Templates](templates/index.md) - Optional per-type document templates.

## Files
* [GOVERNANCE-CHARTER][KB Charter](charter.md) - The KB's purpose — who it serves, its consumers, and the architectural intent. Human-maintained.
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

Operational document (`DocClass OPERATIONAL`), path-addressed with no id and CLI-appended by `kb log`. Its `type: log` frontmatter both classifies it and satisfies OKF's every-markdown-file `type` requirement (00-shared §5). It is deliberately omitted from generated index listings.

```markdown
---
type: log
---
<!-- KB history — append-only; written by `kb log`. Format: - <UTC ISO> | <action> | <actor> | <ids or -> | <note> -->
# Knowledge Base Log

- <ISO-8601 UTC now> | initialized | kb-cli | - | KB scaffolded by kb init
```

(The timestamp is the only non-literal byte in the scaffold; everything else is byte-pinned.)

### 5.4 `governance/charter.md`

A governance document (`DocClass GOVERNANCE`) with the reserved fixed id `GOVERNANCE-CHARTER`. It is the scaffolded home for the KB purpose and architectural rationale that the `kb-init` skill drafts with the steward (PRD §6.1, INIT-2). It is protected from `--force` like the other human-maintained governance documents.

```markdown
---
id: GOVERNANCE-CHARTER
type: charter
title: KB Charter
description: The KB's purpose — who it serves, its consumers, and the architectural intent. Human-maintained.
---
# KB Charter

The KB's purpose: who it serves, its consumers, and the architectural intent
behind directory structure, vocabularies, and granularity (PRD G9). Drafted
with the KB steward by the kb-init skill. Rationale lives here; binding
authoring rules live in conventions.md; machine-read settings live in
kb-config.json.

## Purpose
(not yet drafted)

## Consumers
(not yet drafted)

## Architectural intent
(not yet drafted)
```

### 5.5 `governance/conventions.md`

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

### 5.6 `governance/kb-config.md`

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
- **`link_types`** — associative link-type vocabulary (PRD §6.9): the typed,
  non-provenance relationships a synthetic document may declare under `links:`.
  `kb validate` flags undeclared link types. An empty list means none are
  declared.
- **`id_prefixes`** — the id prefix used per document class: `synthetic` (`KB`),
  `source` (`RAW`), `chat` (`CHAT`), `feedback` (`FEED`). Numeric ids use six
  zero-padded digits, growing naturally beyond six without a leading zero.
- **`propagation_auto_safe`** — change classes governance considers auto-safe
  during propagation (CS3). Start empty; expand from field data (PRD OQ1).
```

(All eight `index.md` files are specified in §5.2; there are no `.gitkeep` files.)

## 6. Output

**Text (stdout):** one line per manifest entry, `<created|overwritten|skipped>  <relative path>` (skips annotated `(exists)`), then a summary line. Entries are ordered **alphabetically by relative path** — in the text lines and in each JSON array below — so output is deterministic run to run:

```
KB ready at /abs/path — 13 created, 0 overwritten, 0 skipped
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
| E4 | Re-run with `--force` | CLI-owned entries (`kb-config.json`, the eight `index.md`) rewritten pristine; protected entries (`log.md`, the three governance documents), KB documents, and non-manifest files untouched | 0 |
| E5 | Partial scaffold (some files deleted) | missing entries recreated, present ones skipped (repair) — protected entries included (a deleted `log.md` or governance doc is recreated pristine) | 0 |
| E6 | `ROOT` is inside an existing KB | allowed — a nested KB root is created (no nesting check); closest ancestor `kb-config.json` wins during discovery | 0 |
| E7 | A manifest path is occupied by the wrong kind — a directory where a file belongs (e.g. a directory named `kb-config.json/`) or a file where a directory belongs (e.g. a file named `raw`) | `E_INIT_IO` with the offending path; no silent replacement, no rollback of entries already written | 2 |
| E8 | Unknown option / bad flag value | usage error (Typer-rendered message on stderr) | 2 |

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`. These criteria are the input to the detailed behavior specifications that drive development; each is written to be independently testable with an unambiguous pass condition.

**Coverage map:** fresh scaffold & pinned content AC1–AC8 (§5) · idempotency & repair AC9–AC12 (§4 step 2, E3/E5) · `--force` semantics AC13–AC17 (§4 step 2, E4) · root resolution AC18–AC21 (§4 step 1, E1/E6) · errors & edge cases AC22–AC24 (E2/E7/E8) · output contract AC25–AC27 (§6, 00-shared §3) · help & cross-command AC28–AC30 (§3, Git-agnosticism, born-valid) · charter lifecycle AC31 (§5.4).

| # | Given / When / Then |
|---|---|
| AC1 | Given an empty directory, when `kb init` runs, then exit is 0 and exactly the 13 §5 manifest paths exist — no other file is created anywhere under `ROOT` — each byte-identical to its pinned content (the `log.md` timestamp is pattern-matched, everything else exact). |
| AC2 | Given AC1's run, then stdout contains one `created  <relative path>` line per manifest entry, ordered alphabetically by relative path, followed by the summary line `KB ready at <abs ROOT> — 13 created, 0 overwritten, 0 skipped`. |
| AC3 | Given a fresh KB, then `kb-config.json` parses with stdlib `json` and contains **exactly** the keys `schema`, `types`, `tags`, `link_types`, `id_prefixes`, `propagation_auto_safe` — no others — with `schema == 1`, `types == []`, `tags == []`, `link_types == [references, contradicts, constrains]`, `id_prefixes == {synthetic: KB, source: RAW, chat: CHAT, feedback: FEED}`, `propagation_auto_safe == []`. |
| AC4 | Given a fresh KB, then `governance/charter.md`, `governance/conventions.md`, and `governance/kb-config.md` byte-match their pinned sections and carry the reserved ids `GOVERNANCE-CHARTER`, `GOVERNANCE-CONVENTIONS`, and `GOVERNANCE-KB-CONFIG`; scanning classifies all three as `DocClass GOVERNANCE`. |
| AC5 | Given a fresh KB, then exactly eight `index.md` files exist (root, `governance/`, `governance/templates/`, `raw/`, `raw/sources/`, `raw/chats/`, `raw/feedback/`, `synthetic/`); each parses with frontmatter `type: index` plus the pinned `description`, has **no** `id` key, and its body byte-matches §5.2 for that path — generated-header comment, then `## Subdirectories` / `## Files` sections with empty sections omitted (five leaf indexes have header-comment-only bodies; root, `governance/`, `raw/` match their pinned listings). |
| AC6 | Given a fresh KB, then **every** scaffolded `*.md` carries a `type` frontmatter field (FM0/OKF): eight × `type: index`, `type: charter`, `type: conventions`, `type: kb-config`, `type: log`. |
| AC7 | Given a fresh KB, then no `.gitkeep` file exists anywhere under `ROOT`. |
| AC8 | Given a fresh KB, then `log.md` scans as a path-addressed, id-less `DocClass OPERATIONAL` document and contains exactly one log line; it matches the 00-shared §8 format `- <timestamp> | initialized | kb-cli | - | KB scaffolded by kb init`, and `<timestamp>` parses as ISO-8601 UTC. |
| AC9 | Given a scaffolded KB, when `kb init` re-runs, then exit 0, stdout lists all 13 entries as `skipped … (exists)` with the summary `— 0 created, 0 overwritten, 13 skipped`, and no file's bytes or mtime changed. |
| AC10 | Given three consecutive runs in the same directory, then `log.md` contains exactly one `initialized` entry. |
| AC11 | Given a KB with `log.md` and `raw/index.md` deleted, when `kb init` re-runs, then exactly those two are `created` (pristine — the recreated `log.md` carries a fresh `initialized` entry), the other 11 are `skipped`, and exit is 0. |
| AC12 | Given a non-empty non-KB directory containing an unrelated file `notes.txt` and an unrelated subdirectory `misc/`, when `kb init` runs, then the 13 manifest entries are created, `notes.txt` and `misc/` are byte-for-byte untouched, and **no** `index.md` is added inside `misc/` (init writes only the manifest; the directory invariant for foreign directories is `kb index`/`kb index --check` territory — kb-validate §7.4). |
| AC13 | Given an empty directory, when `kb init --force` runs, then all 13 entries classify as `created` (never `overwritten`), and the result is byte-identical to a plain `kb init`. |
| AC14 | Given a KB where `kb-config.json` was hand-edited, when `kb init --force` runs, then it is restored byte-identical to §5.1 and reported `overwritten`. |
| AC15 | Given a KB where `raw/index.md` was hand-edited, when `kb init --force` runs, then it is restored byte-identical to §5.2 and reported `overwritten`. |
| AC16 | Given a KB where `governance/charter.md`, `governance/conventions.md`, and `governance/kb-config.md` were edited and two extra lines were appended to `log.md`, when `kb init --force` runs, then all four files are byte-identical afterwards and reported `skipped` — protected entries are never overwritten — and the summary partitions as `0 created, 9 overwritten, 4 skipped`. |
| AC17 | Given a KB containing a document at `raw/sources/x.md`, when `kb init --force` runs, then that document is byte-identical afterwards (nothing outside the manifest is ever written). |
| AC18 | Given a nonexistent nested relative path `x/y/z`, when `kb init --root x/y/z` runs, then the directories are created with parents, scaffolded, exit 0, and the reported root (`--json` `root` field) is the resolved **absolute** path. |
| AC19 | Given an empty directory as cwd and no `--root`, when `kb init` runs, then that cwd (resolved absolute) becomes the KB root and is scaffolded, exit 0. |
| AC20 | Given an existing **file** at path `P`, when `kb init --root P` runs, then exit 2, error code `E_INIT_NOT_DIR`, and nothing is created. |
| AC21 | Given an existing KB at `/a`, when `kb init --root /a/b` runs, then exit 0 and a complete nested KB root is scaffolded at `/a/b` (no nesting guard, E6). |
| AC22 | Given a manifest path occupied by the wrong kind — case (a): a **directory** named `kb-config.json/`; case (b): a **file** named `raw` — when `kb init` runs, then exit 2 with `E_INIT_IO` naming the offending path, and the occupying entry is not replaced. |
| AC23 | Given an unwritable target directory, when `kb init` runs, then exit 2 with `E_INIT_IO` (skipif on platforms without POSIX permissions). |
| AC24 | When `kb init --bogus-flag` runs, then exit 2 with a usage error on stderr and no file created (E8). |
| AC25 | Given `--json` on a fresh directory, then stdout parses as JSON containing exactly the fields `ok` (true), `root` (absolute path string), `created`/`overwritten`/`skipped` (arrays of relative-path strings, each sorted alphabetically), the three arrays partition the 13-entry manifest, and nothing else is on stdout. |
| AC26 | Given `--json --root P` where `P` is a file, then stdout is exactly the error envelope `{"error": {"code": "E_INIT_NOT_DIR", "message": …}}`, exit 2. |
| AC27 | Given a text-mode (no `--json`) failing run (AC20's setup), then the error message appears on **stderr** and stdout carries no payload lines. |
| AC28 | When `kb init --help` runs, then exit 0 and output contains every normative string from §3 — each description sentence, each option help string, each example line — and mentions no Git operations. |
| AC29 | Given a fresh KB, when `kb init` ran, then no `.git/` directory exists, no `git` subprocess was invoked (asserted via a PATH shim or subprocess spy), and JSON output contains no `git` key (Git-agnostic). |
| AC30 | Given a fresh KB, when `kb validate` runs, then exit 0 (the scaffold is born valid; this is a hard gate). |
| AC31 | Given an empty directory, when `kb init` runs, then `governance/charter.md` is created with the pinned §5.4 content; when `kb init` re-runs it is skipped; when `kb init --force` runs it is never overwritten. |

## 9. Out of scope

- Steward interview / governance authoring (INIT-2 — `kb-init` skill).
- Adopting existing documents into conformance (INIT-3 — `kb-init` skill).
- Any file generation beyond the §5 manifest; no inference, no content synthesis.
- **All Git operations.** `kb init` never runs `git init`, staging, or commits, and never inspects Git state. The KB lives in Git (NFR-1/NFR-7), but initializing and managing the repository is the user's or a skill's responsibility.
- Regenerating `index.md` listings after scaffold — that is `kb index`'s job; `kb init` only writes the initial pinned content.
- Rollback of partially written scaffolds on I/O error (documented in E2).
- Any check for whether `ROOT` is already inside a KB (no nesting guard); nested roots are permitted (E6).
