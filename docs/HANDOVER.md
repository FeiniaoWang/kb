# Handover: `kb` CLI specification work

**Purpose of this document.** Bootstrap a new working session to continue authoring per-command specification documents for the `kb` CLI. Attach this file and say, e.g., *"Please start drafting the specification document for the kb validate command."* Everything normative lives in the repo files referenced below — **always read the current files; they win over anything summarized here** (the human edits documents, and parallel implementation agents change code, between sessions).

**Next up: `kb validate` (CLI-6).** The immediate task is the contract spec for `kb validate` — the KB's **single authoritative integrity checker** and the enforcement point for every mechanical rule the write-path commands deliberately deferred (DG5 session parentage, full synthetic-schema conformance, tag-vocabulary conformance, type↔location agreement, id uniqueness, supersedes/status coupling, graph acyclicity). It is the CI gate (NFR-3, CLI-12): every property checkable without an LLM is checked here.

> **The `kb validate` design is NOT set in stone.** The `kb validate` details in the [master design](superpowers/specs/2026-07-13-kb-cli-design.md) (CLI-6 section, the check-group table) and [PRD](prd.md) (CLI-6, FM0–FM3, DG1/DG2/DG5, LS1–LS4, tag/id rules) are a **starting proposal, not settled decisions**. Before writing the spec, the author should step back and reason from first principles about the **purpose of this knowledge base project** — its central idea (humans drive creation, agents maintain; evidence-to-artifact traceability; deterministic mechanical truth in the CLI, judgment in the skills) — and design the checker that best serves it. The finding-code taxonomy, severity model, `--strict` semantics, scoping-vs-global-checks behavior, output/JSON shape, exit-code mapping, and the split of responsibility between `kb validate` and the `kb-lint` skill are all open to reconsideration. Prefer the existing proposal where it genuinely fits, but do not treat it as a constraint. **If the spec author changes any of this, the master design and the PRD must be updated in the same change so all three documents stay in sync** — the human cares a lot about cross-document consistency. The rest of this handover summarizes the *current* proposal so you know where it stands; read it as the material to challenge and refine, not as fixed requirements.

**The single most important quality bar for this spec: comprehensive, unambiguous acceptance criteria.** The ACs are the direct input to the detailed behavior specification that drives implementation. For `kb validate` this matters more than for any command so far, because the spec **is** essentially its finding-code table: every distinct check the checker performs, its severity, its exact trigger condition, and its message must be pinned, and **every finding code must map to at least one AC that provokes it (a positive/violating case) and, where meaningful, one that confirms a clean document does not trip it (a negative case).** Aim past the kb-ingest AC1–AC50 bar. Be exhaustive about edge cases: empty KB, a document that violates several rules at once, malformed frontmatter, scoping interactions, the reserved-slug id forms, `log.md`/`index.md` special handling, and every boundary in the severity/`--strict`/exit-code logic. If a behavior or a finding code is not covered by an AC with an unambiguous pass condition, the spec is not done.

The session's job is to turn a well-reasoned design into a full contract spec mirroring the existing ones (`kb-init.md`, `kb-ingest.md`, `kb-create.md`).

## 1. What this project is

We are building the **KB Skill Suite**: a shared project knowledge base (Markdown + YAML in Git, OKF-conformant) where humans of all roles and AI agents work in one context. Humans create documents in co-authoring sessions; agents maintain them; everything traces back to immutable raw evidence through a derivation graph. See [docs/prd.md](prd.md) for the full product definition.

Delivery is split in two layers:
- **`kb` CLI** (this phase) — the deterministic layer: query, graph, **integrity (`kb validate`)**, ingest, synthetic authoring, housekeeping. Python, Typer, tested, independently versioned.
- **`kb-*` Agent Skills** (later) — the judgment layer. Explicitly out of scope until the CLI is done. `kb validate`'s sibling is the `kb-lint` skill, which layers *semantic* review (contradictions, staleness, orphan detection, drift) on top of `kb validate`'s mechanical findings — keep semantic judgment out of the command.

**Strategy decided:** build the full CLI first (all command groups), each command specified by a self-contained contract spec, then an implementation plan, then the code. Specs are written to be refined into detailed behavior specifications that drive development.

## 2. Authoritative documents (read in this order)

| File | Role |
|---|---|
| [docs/specs/commands/00-shared.md](specs/commands/00-shared.md) | **Normative cross-command contracts**: root discovery, exit codes, output/JSON envelopes, REF definition, pipelines, the scan, id grammar & allocation, **core data models** (Pydantic, with growth policy), log format, help-text and testing conventions, Git-agnostic + directory invariants. `kb validate` graduates every `*Frontmatter` model here from "shape pinned" to **full enforcement**, and introduces the `Finding` model |
| [docs/specs/commands/kb-init.md](specs/commands/kb-init.md) | The **first command spec and the original template** — its section structure, level of detail, and AC style are the pattern for every subsequent spec |
| [docs/specs/commands/kb-ingest.md](specs/commands/kb-ingest.md) | A complete **write-path** spec (AC1–AC50); good reference for AC comprehensiveness and the pre-flight/error-table discipline |
| [docs/specs/commands/kb-create.md](specs/commands/kb-create.md) | The other write-path spec (AC1–AC52), written most recently; **its frontmatter emission (§5.1 pinned key order) and supersedes/status coupling are exactly what `kb validate` must enforce** — read it to know what a valid synthetic document looks like |
| [docs/superpowers/specs/2026-07-13-kb-cli-design.md](superpowers/specs/2026-07-13-kb-cli-design.md) | Master design & decision record: per-command design bullets for ALL commands. Its **`kb validate` (CLI-6) section** (the check-group table) is the starting material — treat it as a **proposal to challenge and refine**, not a fixed spec; update it if the design changes |
| [docs/prd.md](prd.md) | Product requirements; requirement ids (CLI-1…CLI-13, FM0–FM3, DG1–DG5, CS1–CS5, LS1–LS4, ING/AUT/LINT/INIT, NFR-1…9, OQ1–OQ6) cited throughout |
| [docs/superpowers/plans/](superpowers/plans/) | Implementation plans produced (by the `writing-plans` skill) after each spec: `2026-07-15-kb-init.md`, `2026-07-16-kb-ingest.md`, `2026-07-16-kb-create.md`. Not needed to write the validate spec, but they show how specs become code |
| [src/kb/](../src/kb/) | **The implementation as it stands** — the scan/model/id/housekeeping foundation `kb validate` will build on already exists (see §3). Skim `core/model.py`, `core/scan.py`, `core/ids.py` so the spec aligns with the real code contracts |
| [AGENTS.md](../AGENTS.md) | Per-session coding-agent rules: package layout, invariants, working conventions |

**Precedence when documents disagree:** command spec > 00-shared.md > master design > PRD. Deviating from a spec means updating the spec in the same change.

## 3. Status

This project is **no longer spec-only** — specs, implementation plans, and working code now co-exist. Read the tree, not just this summary.

**Specs (`docs/specs/commands/`) — done:**
- `00-shared.md` — shared foundations + core model table (models added by the first command spec that needs them; the *Introduced by* column tracks this). Already lists `RawFrontmatter`, `SyntheticFrontmatter`, `GovernanceFrontmatter`, `IndexFrontmatter` with enforcement "specced in kb-validate" — **that enforcement is this session's job**, and `kb validate` also introduces the `Finding` model here.
- `kb-init.md` — complete, user-reviewed, **AC1–AC30**.
- `kb-ingest.md` — complete, iterated through the review gate + an AC-comprehensiveness pass, **AC1–AC50**.
- `kb-create.md` — complete, **AC1–AC52**, and now **implemented and green** (see Code below). Two decide-and-flag calls in it, carried into the implementation: (a) **no `E_CREATE_USAGE` code** — `kb create` has no flag pairings beyond what Typer enforces natively, so missing/invalid options are Typer-rendered usage errors (exit 2) with no custom code; (b) a **nonconforming `--supersedes` target** missing `timestamp`/`last_human_touch` gets those keys appended at the end of its frontmatter block.

**Implementation plans (`docs/superpowers/plans/`) — done for init, ingest, create.** No plan for validate yet (that comes after this spec is approved).

**Code (`src/kb/`, `tests/`) — init, ingest, and create are implemented and green; only validate is not:**
- **`kb init` (CLI-11)**, **`kb ingest` (CLI-8)**, and **`kb create` (CLI-13, AC1–AC52)** are implemented with tests. `185 passed, 1 xfailed` at handover (`uv run pytest -q`). Implementation proceeds on parallel tracks (note `.worktrees/`, `.agents/`, and `codex/*` merge commits in the log) — writing-plans → coding agents — so **HEAD and branch lineage move between sessions; trust the working tree and `git log`, not this summary.**
- The **foundation `kb validate` needs already exists as real, tested code**: `core/model.py` (`DocClass`, `RawClass`, `Frontmatter`, `Document`, `Config`, `load_config`, and the `RawFrontmatter`/`SyntheticFrontmatter`/`GovernanceFrontmatter`/`IndexFrontmatter` models — the synthetic model landed with `kb create`), `core/scan.py` (`discover_root`, `read_frontmatter`, `scan(root) -> KB`, `resolve_ref`, and `KB.malformed` handling), `core/ids.py` (`DocId`, `next_id`), `core/create.py` + `core/ingest.py` (the write paths), `core/housekeeping.py` (`LogEntry`, `format_log_entry`, log/scaffold I/O), `core/indexing.py` (index rendering). `kb validate` reads through this layer; it does **not** allocate ids, so the malformed-file *guard* does not apply to it — validate is instead the command that *reports* malformed files fully.
- **Not yet in code:** a `Finding` model, `core/validate.py`, and any `kb validate` CLI wiring. The master-design package layout reserves `core/validate.py` ("all FM/DG/LS mechanical checks → list of Findings"). Confirm the current model/field names against `core/model.py` when specifying enforcement — the models already exist and the spec should match them.

**Next (agreed order):** `kb validate` → then the remaining query/graph/housekeeping commands (show, filter, search, frontmatter, resolve, links, mv, index, log). Rationale: with all three write paths now shipped, `kb validate` completes the model set (`Finding`, full synthetic-schema + graph enforcement) and is the integrity backbone; the query/graph commands become thin afterward because the scan and models are already solid.

## 4. The spec-authoring process we follow

Each spec is produced in a **brainstorming session** with this shape (the human insists on it — do not skip steps):

1. Read the current repo docs **and the relevant code** (both may have changed between sessions).
2. Ask clarifying questions **one at a time**, multiple-choice where possible, only about genuinely open decisions. The human answers quickly and decisively; when they say "keep it simple," believe them.
3. Propose approaches with trade-offs and a recommendation where a real design fork exists.
4. Present the design in sections, getting approval per section.
5. Write the spec file, self-review (placeholders, contradictions, ambiguity, scope), fix inline.
6. **User review gate** — the human reviews and requests changes over several rounds; apply each, keep all documents consistent (00-shared, master design, PRD, AGENTS.md), commit per logical change with requirement ids in messages.
7. Only after explicit approval: transition to implementation planning (`writing-plans` skill).

**On acceptance criteria (the human's top priority — do not under-serve this):** the ACs are refined into the behavior spec that drives development, so they must be **comprehensive and unambiguous**. One AC = one test = one behavior. Every §4 algorithm step and every §7 error/edge row maps to ≥1 AC. For `kb validate` specifically, every finding code maps to ≥1 AC that triggers it; note any genuinely untestable exception explicitly.

## 5. The spec template (contract style — mirror kb-init.md / kb-ingest.md / kb-create.md)

```
# Spec: `kb <command>`
Implementation context: this file + 00-shared.md.     ← two-file closure rule
Traceability: PRD requirement ids covered.
1. Purpose            — one paragraph
2. CLI surface        — synopsis, param table (kind/type/default/meaning)
3. Help text          — NORMATIVE WORDING (layout is Typer's): description,
                        each option help string, Examples section (2–5 lines).
                        Tests assert substrings, never layout.
4. Behavior           — numbered normative algorithm, deterministic enough
                        to implement from; edge decisions inline.
5. Filesystem effects — exact tree + file contents pinned VERBATIM.
6. Output             — text form + exact JSON shape; deterministic ordering
7. Errors & edge cases— table: # | condition | behavior/code | exit
8. Acceptance criteria— AC1..ACn contiguous, one pytest test per AC
                        (test_ac<NN>_<slug>), coverage map paragraph mapping
                        AC groups → spec sections; each AC independently
                        testable with an unambiguous pass condition.
9. Out of scope       — explicit non-goals incl. what belongs to skills
```

**`kb validate` is the first READ-ONLY command spec, so the section weights shift.** It writes nothing — **§5 "Filesystem effects" is essentially "none (read-only); the KB is byte-for-byte unchanged"** (worth a one-line AC), and there is no pre-flight/atomicity machinery. The weight moves to **§4 (the check algorithm)**, **§7 (the finding-code table — this is the heart of the spec)**, **§6 (finding output: text + JSON + exit-code mapping)**, and **§8 (one AC per finding code, plus scoping/severity/`--strict`/output)**. Note that the §7 "Errors & edge cases" table now has two distinct kinds of rows to keep separate: **command-level errors** (`E_*`, e.g. no KB, unresolvable `REF` argument — these end the run with exit 2) versus **findings** (integrity violations the command is designed to report — these produce the exit-1 CI signal, not an `E_*` code). Decide the presentation (likely a dedicated finding-code table plus a small command-error table).

Cross-cutting rules that every new spec must honor (details in 00-shared.md):
- Command-level error codes `E_<CMD>_*`, unique, SCREAMING_SNAKE; exits 0/1/2 per the shared contract; `--json` error envelope `{"error":{"code","message"}}`. Shared/environment codes stay unprefixed (`E_NO_KB`, `E_CONFIG_INVALID`, `E_SCHEMA_UNSUPPORTED`). **Findings are a separate namespace from `E_*` command errors** — decide and pin their code scheme in-session (see §7 open threads).
- `type` is mandatory on every `*.md` and authoritative (FM0); DocClass/RawClass derive from `type`, never path; location must agree with `type`. **`kb validate` is the enforcement point for all of this.**
- Every directory has a CLI-owned read-only `index.md` (`type: index`, no id); any command creating a directory creates its `index.md`.
- Git-agnostic: no command runs `git` or inspects Git state, ever.
- Scan-on-demand, no stored index; malformed/missing-`type` files go to `KB.malformed`. The id-allocation guard is a *write-path* concern — **`kb validate` does not allocate ids**, so it runs even when malformed files exist; reporting them is its job.
- Deterministic output ordering (alphabetical by relative path unless the spec pins otherwise). Findings need a pinned, stable order (by path, then by code, is the natural choice — pin it).
- New core models: add to 00-shared §7 with *Introduced by* = the new spec; never change existing fields, only add. **`kb validate` introduces `Finding` and graduates the `*Frontmatter` models to full enforcement.**
- After writing a spec, reconcile the master design and PRD if the spec sharpened or changed anything (the human cares a lot about cross-document consistency — grep before claiming done).

## 6. Decisions log (chronological; rationale in the master design)

- Full CLI before skills; contract specs before code; each spec → implementation plan → code.
- Layered architecture: pure core (`src/kb/core/`) + thin Typer CLI (`src/kb/cli/`); models in `core/model.py` as Pydantic 2.x BaseModels (`extra="allow"` on frontmatter; Pydantic never does file I/O). `core/validate.py` will hold the mechanical checks → list of `Finding`s.
- Ids: sequential per prefix, **6-digit** zero-pad (`KB-000042`), max+1 from the scan, gaps never refilled; **merge collisions (two branches allocating the same id) are caught by `kb validate` as duplicate-id findings** — repair is manual. Reserved **slug ids** for governance system docs (`GOVERNANCE-CONVENTIONS`, `GOVERNANCE-KB-CONFIG`); `GOVERNANCE` prefix never allocated numerically. The id-format check must accept both the numeric `<PREFIX>-<NNNNNN>` and the reserved-slug `<PREFIX>-<UPPER-SLUG>` forms.
- `kb-config.json` (clean strict JSON, stdlib-parsed) lives at the KB root and doubles as the **root marker**. `schema` key is tooling-owned; commands refuse a newer schema (`E_SCHEMA_UNSUPPORTED`). Discovery: closest ancestor with `kb-config.json`; existence-based (malformed config ≠ "no KB").
- `index.md` in **every** directory: `DocClass INDEX`, `type: index`, folder `description`, **no id** (path-addressed), **CLI-maintained and read-only**. `log.md`: operational, append-only, `type: log` (FM0 still applies — it must carry `type`), pipe-format lines. Both are `*.md` files the scan sees; both are in scope for the universal-`type` check.
- **Two write paths, symmetric:** `kb ingest` writes immutable `raw/` docs; `kb create` writes `synthetic/` docs. Both allocate ids, honor the malformed guard, use `--dest` + directory invariant, refresh indexes, append a log entry, and validate fully pre-flight before an atomic write.
- **`kb create` decisions that landed this session (now in kb-create.md + master design + PRD, reconciled):** `--supersedes` implicitly appends its target to `derived_from` (last, deduplicated) and satisfies the ≥1-parent rule (DG1) alone; the target must be a **live (`draft`/`current`) synthetic** document, else `E_CREATE_SUPERSEDES_INVALID` (re-superseding a `superseded`/`retired` doc is an error); `--supersedes` atomically flips the target to `superseded` and rewrites only its `status` + `timestamp` + `last_human_touch`, every other byte preserved. `derived_from` preserves `--derived-from` argument order, duplicates dropped keeping first occurrence. Error codes are `E_CREATE_*`; resolution/content failures exit 1, usage/environment exit 2. Body via `--body-file FILE|-` only; empty/whitespace-only → empty body (legal draft stub). Undeclared `--tag` values warn (never block), like unknown `--type`; **FM1b tag-vocabulary enforcement and DG5 stay with `kb validate`**. Frontmatter key order pinned in kb-create §5.1; `SyntheticFrontmatter` in 00-shared §7 graduated to "constructed and emitted by kb-create."
- **DG5 and full synthetic-schema/tag enforcement are deliberately deferred to `kb validate`** — the single authoritative enforcement point. This is the central reason validate is the natural next command.
- Git: no Git operations anywhere in the CLI. Output ordering: alphabetical by relative path.

## 7. Known open threads for `kb validate` (the design to reason through)

**The whole design is open (see the §Next up callout). The master design's CLI-6 check-group table is the starting proposal; below are the decisions most obviously in need of a first-principles answer.** Raise these one at a time in-session, and challenge any part of the proposal you think should change.

- **Finding-code taxonomy (the biggest decision).** Every check needs a stable, unique code (used in output, in `--json`, and as the AC anchor). Decide the scheme and namespace: grouped by rule family (e.g. `FM0_MISSING_TYPE`, `DG2_CYCLE`, `LS_SUPERSEDES_NOT_MARKED`, `ID_DUPLICATE`, `LINK_UNRESOLVED`, `LOC_TYPE_MISMATCH`, `TAG_UNDECLARED`) vs a flat `V_*` scheme vs something else. Whatever you pick, it must be exhaustive and stable (skills and CI will key off these codes, NFR-9).
- **Severity model.** Which findings are `error` (→ exit 1, the CI gate) vs `warning` (→ exit 0 unless `--strict`)? The master design already marks `description` > 2 sentences and `last_human_touch > timestamp` as warnings. Pin the full error/warning split per code.
- **`--strict` semantics.** Confirm it only promotes warnings to the exit-1 signal (does it change *what* is reported, or only the exit code?). Pin exactly.
- **Scoping vs inherently-global checks.** `kb validate [REF...]` scopes to the named documents, "plus graph checks that are inherently global." Pin precisely which checks stay global regardless of scope (acyclicity, duplicate-id across the whole KB, reverse-link/`supersedes`-target existence) and how findings on out-of-scope documents surface when a scope is given. Also: does validate read `REF...` from **stdin** like the other pipeline commands (00-shared §4.2 lists `validate` among them)? Pin it.
- **Command error vs finding for an unresolvable `REF` argument.** If the user passes `kb validate KB-999999` and no such doc exists, is that a command-level error (exit 2, like other commands' ref resolution) or a finding? Decide and keep it consistent with `kb resolve`/00-shared.
- **Malformed / unparseable frontmatter as a finding.** validate is the *full* reporter of `KB.malformed` (query commands only warn, write commands refuse). Pin how a file whose YAML doesn't parse, or that has no `type`, becomes a finding (code, severity, message) — and that validate still runs to completion and reports everything else.
- **Index staleness — ownership boundary.** `kb index --check` already owns "is every `index.md` present and its listing current?". Decide whether `kb validate` *also* checks index freshness/presence or leaves it entirely to `kb index --check` (avoid double-ownership; the master design currently splits them). The old open thread flagged this explicitly.
- **`Finding` model → 00-shared §7.** Fields at least: `code`, `severity` (`error`/`warning`), `doc` (id and/or path — pin which; index/log have no id), `message`. Add it with *Introduced by* = kb-validate. Also decide the JSON success/finding envelope: `{"ok": true, "findings": [...]}`? exit code independent of `ok`?
- **Graduating the `*Frontmatter` models.** `kb validate` is where `RawFrontmatter`, `SyntheticFrontmatter`, `GovernanceFrontmatter`, `IndexFrontmatter` move from "shape pinned" to full enforcement. Spell out per-class mandatory fields, legal `status` values, timestamp ISO-8601 parsing, and that FM2 unknown keys are preserved and **never** flagged.
- **Output shape & ordering.** Text form (grouped by document? by severity? flat sorted?), the `--json` schema, and the deterministic ordering. No `--output paths|frontmatter|full` here (that's for document-returning commands) — confirm validate has its own finding-oriented output only.
- **`kb validate` vs `kb-lint` boundary.** Strictly LLM-free (NFR-3). Semantic checks (contradictions, staleness judgment, orphan/coverage analysis, instruction conflicts, the drift report) belong to the `kb-lint` skill — keep them out of the command and record them in Out of scope.
- **Does it check `log.md`?** FM0 says *every* `*.md` carries `type`; `log.md` carries `type: log`. Confirm validate checks `log.md`'s `type` presence and nothing else about it (it's operational, not a document).

**Other product-level open threads (not this session):** `kb show`'s own spec (the `---` terminator convention, round-trip AC); the folder-`description` customization gap (index.md is read-only); AC22 in kb-init's `E_INIT_IO` judgment call; OQ6 (synthetic in-place revision write path) and PRD OQ1–OQ5; the kb-create written-spec review gate is still pending the human's read.

## 8. Working conventions with this human

- They review carefully and iterate: expect several rounds of targeted change requests per spec; apply exactly, keep every document consistent, commit per logical change (imperative subject, requirement ids like "CLI-6", "AC7" in the body where relevant, `Co-Authored-By: Claude`).
- They edit docs directly between sessions, and **parallel agents change code between sessions** (worktrees, codex branches) — **re-read files and skim the current code at session start; never assume this handover, memory, or the last state is current.** The git log is the truth about what's been implemented.
- Ask before deciding anything user-visible (flag semantics, formats, naming, finding codes/severities); decide-and-flag for internal judgment calls, stating the reversal path.
- Simplicity requests are real: when they say "don't worry about X for now," remove X cleanly and record it in Out of scope rather than leaving vestiges.
- They value **comprehensive, unambiguous acceptance criteria** above almost everything — the ACs drive development. For validate, that means one AC per finding code (triggering case), plus clean-document negatives, plus scoping/severity/`--strict`/output/exit-code coverage. kb-ingest AC1–AC50 / kb-create AC1–AC52 is the floor, not the ceiling.
- Tests: one AC = one test, `test_ac<NN>_<slug>`, Typer `CliRunner`, `tmp_path` fixtures, no subprocesses in unit tests. A `make_doc(id, type, derived_from=[...])`-style helper set exists in `tests/conftest.py` — validate's tests will lean on it to build KBs that violate one rule at a time.

## 9. Kickoff instruction for a new session

Given this document, the next session should:
1. Read [00-shared.md](specs/commands/00-shared.md), [kb-init.md](specs/commands/kb-init.md), [kb-ingest.md](specs/commands/kb-ingest.md), and [kb-create.md](specs/commands/kb-create.md) (templates; kb-create shows what a valid synthetic document looks like — i.e. what validate enforces), the **`kb validate` (CLI-6) section** in the [master design](superpowers/specs/2026-07-13-kb-cli-design.md), and the relevant PRD requirements (CLI-6, FM0–FM3, DG1/DG2/DG5, LS1–LS4, id/tag rules, NFR-3). **Also skim the existing code** (`src/kb/core/model.py`, `scan.py`, `ids.py`) so the spec aligns with the real `KB`/`Document`/`Frontmatter` contracts already implemented.
2. **Reason from the project's purpose first** (see the §Next up callout): treat the master design's CLI-6 check-group table and the PRD's validate requirements as a proposal to challenge, not a fixed spec. Decide what checker best serves the KB's central idea — the deterministic integrity backbone that lets humans and CI trust the graph — before committing to the surface. Then run the §4 process: clarifying questions (one at a time) on the §7 open threads **and any part of the proposal you think should change**, then sectioned design presentation, then write `docs/specs/commands/kb-validate.md`, self-review, and hand to the human for the review gate.
3. **Be exhaustive on the finding-code table and its ACs** — this is the explicit top priority. Every mechanical rule in the KB (FM0 universal `type`; type↔location; per-class schema FM1–FM3; tag vocabulary FM1b; id format/uniqueness incl. merge collisions and reserved slugs; link integrity for `derived_from`/`supersedes`/`about`; graph acyclicity + evidence termination DG2; session parentage DG5; lifecycle/supersedes-status coupling and timestamp ordering LS) becomes one or more finding codes, each with pinned severity, trigger, and message, each covered by ≥1 AC.
4. Update 00-shared §7 (introduce `Finding`; graduate the `*Frontmatter` models to full enforcement), the master design (CLI-6 section), and the PRD (CLI-6 row + a dated consistency note) wherever the new spec sharpens or **changes** behavior — then verify consistency by grepping across all documents before declaring done. This reconciliation is mandatory whenever the design diverges from the current proposal.
