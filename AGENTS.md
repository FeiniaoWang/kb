# AGENTS.md — guide for coding agents

This repo builds the **`kb` CLI**: the deterministic toolset of the KB Skill Suite (shared project knowledge base, Markdown + YAML in Git). Skills (the judgment layer) come later and live outside this codebase's current scope.

## Authoritative documents (read in this order)

| Document | Role |
|---|---|
| [docs/specs/commands/00-shared.md](docs/specs/commands/00-shared.md) | Normative cross-command contracts: root discovery, exit codes, output/JSON, pipelines, scan, id grammar, **core data models**, log format, help-text and testing conventions |
| [docs/specs/commands/kb-<command>.md](docs/specs/commands/) | Per-command contract specs. **Implementation context for a command = its spec + 00-shared.md, nothing else** |
| [docs/superpowers/specs/2026-07-13-kb-cli-design.md](docs/superpowers/specs/2026-07-13-kb-cli-design.md) | Master design and decision record for all commands |
| [docs/prd.md](docs/prd.md) | Product requirements (PRD); requirement ids like CLI-6, DG5, FM1 cited throughout |

Precedence when documents disagree: command spec > 00-shared.md > master design > PRD. If you must deviate from a spec, update the spec in the same change and say so — specs are normative, not descriptive.

## Package layout (fixed — do not restructure)

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
│   │   ├── housekeeping.py  index.md generation, log.md append, scaffold
│   │   └── mv.py         move/rename + body-link rewriting
│   └── cli/
│       ├── app.py        Typer app; one thin command module per group
│       └── render.py     text and JSON renderers for core's return types
└── tests/                pytest; fixtures build throwaway KBs in tmp_path
```

Layering rule: `core/` is pure logic — no Typer, no printing, no `sys.exit`. `cli/` only parses arguments, calls core, renders output, and maps results to exit codes. New modules require updating the master design spec first.

## Invariants (never violate)

- **Scan on demand, no stored index.** Ids live in document frontmatter; every invocation rebuilds the id→path map. Never introduce a persistent index or cache without a spec change.
- **Exit codes:** `0` success / `1` findings or reference failures / `2` usage or environment errors.
- **Output:** compact plain text by default; every command supports `--json` (`{"ok": true, ...}` / `{"error": {"code", "message"}}`). JSON fields are added, never renamed or removed.
- **Frontmatter handling** preserves key order and unknown keys (FM2). Malformed files never crash query commands.
- **Id allocation** is max+1 per prefix from the scan, and is refused while malformed files exist (an unparsed file could hide an id).
- **Determinism:** no LLM judgment in this CLI, no content synthesis, no network calls. Adapters normalize and file; they never invent content.
- **Data models are Pydantic 2.x `BaseModel`s** (validation + typed access; see 00-shared.md §7). Frontmatter models set `extra="allow"` to preserve unknown keys (FM2); the generic `Frontmatter` wraps an insertion-ordered dict so raw YAML round-trips without reordering. Pydantic validates parsed structures — it does not do file I/O (PyYAML parses frontmatter, stdlib `json` parses `kb-config.json`).
- Dependencies stay `typer`, `PyYAML`, and `pydantic` (2.x) only. Adding another requires a spec change.

## Working conventions

- **Toolchain:** Python ≥ 3.14, managed with `uv` — `uv run pytest`, `uv add <pkg>`, `uv run kb ...`.
- **Tests:** pytest; CLI exercised via Typer's `CliRunner` (no subprocesses). One acceptance criterion = one test, named `test_ac<NN>_<slug>` matching the spec's AC table. A command is done only when every AC in its spec has a passing test.
- **Help text** wording is normative per spec §3 sections; tests assert substrings, never layout.
- **Implementation order:** `init` → `ingest` → `validate`, then query/graph/housekeeping. Core models are introduced by the command that first needs them (00-shared.md §7 table).
- Commit specs and code separately when both change; reference the requirement ids (e.g. "CLI-11", "AC7") in commit messages where they apply.
