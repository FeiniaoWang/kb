# Spec: `kb validate`

**Implementation context:** [PRD](../../prd.md) + [00-shared.md](00-shared.md) + this file. Precedence: PRD > this command spec > shared contract.
**Traceability:** PRD CLI-6, CLI-12/NFR-3 (deterministic mechanical truth — every property checkable without an LLM is checked here), FM0 (universal `type`), FM1/FM1a/FM1b (per-class schema and vocabularies), FM2 (unknown keys never flagged), FM3 (mechanical checkability), DG1 (≥1 parent), DG2 (acyclicity/termination), DG5 (session parentage), AL1–AL3 (associative-link schema, vocabulary, resolution, and graph exemption), CS6 (`pending_upstream`), LS1 (legal status values), LS2 (timestamp ordering), LS4/LS5 (supersedes/status coupling), NFR-2 (OKF conformance), NFR-7 (merge-collision detection), NFR-9 (stable finding codes as a machine contract). The `kb-lint` skill's semantic review and `kb report`'s deterministic operational reports are out of scope (§9).

## 1. Purpose

Check the knowledge base's mechanical integrity: `kb validate` is the KB's **single authoritative integrity checker** and the CI gate (NFR-3, CLI-12) — the enforcement point for every rule the write paths deliberately deferred (full per-class schema; type, tag, and link-type vocabularies; type↔location agreement; id uniqueness; provenance, associative-link, and pending-marker resolution; graph acyclicity; DG5 session parentage; supersedes/status coupling). It is **total**: it never stops at the first problem — every check runs over every in-scope file and all findings are reported in one pass. It is **read-only**: the KB is byte-for-byte unchanged, and no log entry is written. Every finding carries a **stable code** (the machine contract CI and skills key off, NFR-9), a severity (`error`/`warning`), the anchoring file, and a message. Errors are the CI gate (exit 1); warnings advise (exit 0 unless `--strict`). Deterministic drift, impact, and orphan computation belongs to `kb report` (CLI-15); semantic interpretation and recommendations belong to `kb-lint`.

## 2. CLI surface

```
kb validate [REF...] [--strict] [--kb PATH] [--json]
```

| Param | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `REF...` | positional, repeatable | `REF` | whole KB | Documents to report findings for (00-shared §4). Also read newline-separated from stdin when stdin is piped and no refs were passed as arguments (00-shared §4.2). Scoping **filters which findings are reported, never which checks run** (§4 step 5); for validate only, a path `REF` additionally resolves against malformed `*.md` files (§4 step 3) |
| `--strict` | option | flag | off | Treat warnings as errors for the exit code. Promotes only the exit signal — the findings reported are identical with and without it |
| `--kb` | option | directory path | upward discovery | KB root (00-shared §1) |
| `--json` | option | flag | off | Structured output (§6) |

`kb validate` defines **no command-specific `E_VALIDATE_*` error codes**: the only command-level errors are the shared environment codes (`E_NO_KB`, `E_CONFIG_INVALID`, `E_SCHEMA_UNSUPPORTED`, exit 2) and Typer-rendered usage errors (exit 2). Everything else the command has to say about the KB is a **finding** (§7.1) — a separate namespace from `E_*` codes. An unreadable or undecodable file is a finding (`FM0_UNPARSEABLE`), not an I/O abort; an unresolvable `REF` argument follows the 00-shared §4.1 batch rule (stderr note, remaining refs processed, exit ≥ 1 — reported in `--json` as `unresolved_refs`, never as a finding).

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Check the knowledge base's mechanical integrity.
>
> The single authoritative integrity checker and CI gate: verifies every rule checkable without judgment — universal type and type/location agreement, per-class frontmatter schemas, type/tag/link-type vocabularies, id format and uniqueness, provenance/associative-link/pending-marker resolution, derivation-graph acyclicity, session parentage, and supersedes/status coupling. Reports every finding with a stable code and severity; errors exit 1, warnings exit 0 unless --strict. Reads everything, writes nothing. With REF arguments (or refs piped on stdin), only findings for the named documents are reported. Does not touch Git.

**Option help strings:**

| Param | Help string |
|---|---|
| `REF...` | Documents to report findings for (id or KB-relative path). Also read from stdin when piped. [default: the whole KB] |
| `--strict` | Treat warnings as errors for the exit code. |
| `--kb` | KB root. [default: discovered upward from the current directory] |
| `--json` | Emit findings as JSON. |

**Examples section:**

```
Examples:
  kb validate                                  Check the whole KB (the CI gate)
  kb validate --strict                         Warnings fail the run too
  kb validate KB-000042 synthetic/notes.md     Only findings for the named documents
  kb search "retry" --output paths | kb validate    Validate a piped candidate set
  kb validate --json                           Machine-readable findings
```

## 4. Behavior (normative algorithm)

1. **Root and config.** Resolve the KB root (00-shared §1: `--kb`, else upward discovery). No root → `E_NO_KB`, exit 2. Load `kb-config.json` (`E_CONFIG_INVALID` / `E_SCHEMA_UNSUPPORTED`, exit 2). Unknown options and bad flag values are Typer-rendered usage errors, exit 2.
2. **The check universe.** Scan (00-shared §5). The check universe is **every `*.md` file under the KB root**, recursively—the scan's document set (including index and operational documents) plus `KB.malformed`. No `*.md` file is exempt: a stray `README.md` without frontmatter is in the universe and fails FM0. The malformed-file guard of 00-shared §6 does **not** apply—validate allocates no ids and is precisely the command that reports malformed files fully. The query commands' one-line stderr warning for malformed files (00-shared §5) is suppressed here: in validate, a malformed file is a §7.1 finding on stdout, not a diagnostic.
3. **Scope.** If no refs were given (as arguments, or piped on stdin per 00-shared §4.2—arguments win when both are present), the scope is the whole check universe. Otherwise resolve each ref per 00-shared §4 (id first through the scan's id→path map, else as a KB-root-relative path, `.md` optional)—with one validate-specific extension: a **path** ref resolves against the whole check universe, so malformed files can be named despite not being `Document` values. Blank stdin lines are skipped; duplicate refs are deduplicated silently. Each unresolvable ref is reported on stderr (`unresolvable ref: <token>`), remembered for the exit code and `--json`, and the remaining refs are still processed (00-shared §4.1).
4. **Run every check over the whole universe** (scope never disables a check — graph and uniqueness checks are inherently global). The checks, their trigger conditions, severities, and messages are pinned in §7.1. Cross-cutting rules:
   - **Classification.** A file whose frontmatter fails to parse (missing/unclosed delimiters, YAML error, non-mapping, unreadable, or not valid UTF-8) triggers `FM0_UNPARSEABLE`; one that parses but whose `type` is absent, empty, or not a string triggers `FM0_MISSING_TYPE`. Such files receive **no other checks** (nothing else about them is knowable). Every other file classifies by its authoritative `type` (00-shared §5) and receives the checks for its class.
   - **`log.md` minimalism.** Files of `type: log` receive exactly two checks: FM0 (via the universe) and location (`LOC_TYPE_MISMATCH`: `type: log` is reserved for the root `log.md`). Their remaining frontmatter and body are operational, not schema-checked.
   - **Graceful degradation.** Checks never cascade off broken inputs: graph checks (DG1/DG2/DG5) run only where `derived_from` is a well-shaped list of strings (otherwise `FM1_FIELD_INVALID` stands alone); `DG1_NO_PARENTS` preempts `DG5_NO_SESSION_PARENT` (an empty parent list is one defect, not two); DG5 evaluates over the parents that resolve (unresolvable ones already carry `LINK_UNRESOLVED`); associative-link resolution and vocabulary checks run only for a well-shaped `links` mapping; pending-marker resolution runs only for a well-shaped `pending_upstream` list, and `PU_NOT_PARENT` additionally requires a well-shaped `derived_from` list and a resolved marker; the `ID_INVALID`/`ID_PREFIX_MISMATCH` checks evaluate only string ids on classes whose §4.1 schema includes `id` (a non-string `id` is `FM1_FIELD_INVALID` alone; an `id` on an `index.md` is `FM1_KEY_FORBIDDEN` alone); `ID_DUPLICATE` likewise compares literal string ids only on the id-bearing synthetic, raw, and governance classes; `LS_TOUCH_AFTER_TIMESTAMP` compares only timestamps that parse; `LS_SUPERSEDES_NOT_SYNTHETIC`/`LS_SUPERSEDES_NOT_MARKED` evaluate only a resolved, non-self target (`LS_SUPERSEDES_SELF` preempts both).
   - **Keys are checked only where legal.** Reference and lifecycle checks evaluate `derived_from`, `supersedes`, `links`, and `pending_upstream` on synthetic documents and `about` on feedback documents — where the §4.1 schema defines them. On any other class the same key is `FM1_KEY_FORBIDDEN` and its value is not otherwise evaluated.
   - **Graph edges.** The derivation graph's edges are the resolvable `derived_from` entries of **synthetic** documents only. Raw, governance, and index documents contribute no edges (`derived_from` on them is `FM1_KEY_FORBIDDEN`). Associative links (`links:`) are exempt from DG2 (AL3): they never enter the derivation graph, cycles among them are legal, and they do not count toward chain termination. They never satisfy DG1/DG5 or create propagation obligations. With DG1, `LINK_UNRESOLVED`, and `DG2_CYCLE` in force, DG2's termination clause — every chain terminates at raw or governance documents — is a theorem, not a separate check: every synthetic document has parents, every edge lands on an existing document, no path cycles, so every maximal chain ends at a non-synthetic document. It has no finding code.
   - **Anchor rule.** Every finding anchors to exactly one file (its `path`). Multi-document defects emit one finding **per participating document** (`ID_DUPLICATE`, `DG2_CYCLE`), each naming the other participants in its message; single-anchor defects about a relation (`LS_SUPERSEDES_NOT_MARKED`) anchor to the document carrying the link.
5. **Filter and order.** Report exactly the findings whose anchor is in scope. Sort by (path ascending, code ascending, occurrence) — *occurrence* is the order the triggering construct appears in the document (frontmatter key order; list-entry order within a key). The ordering is pinned and deterministic.
6. **Report** per §6: findings are the payload (stdout); unresolvable-ref notes are diagnostics (stderr).
7. **Exit code:** `1` if any reported finding has severity `error`, or (`--strict`) any reported finding at all, or any ref was unresolvable; else `0`. (Environment/usage failures exited `2` at step 1 and never reach here.)

No step writes a single byte — no document, no `index.md`, no `log.md` entry, no cache. No step runs `git` or inspects Git state.

### 4.1 Shared definitions

- **Sentence heuristic** (for `FM1_DESCRIPTION_LONG`, identical to kb-create §4 step 4): a sentence ends at `.`, `!`, or `?` followed by whitespace or end-of-string.
- **Timestamp validity:** the value must be a string that parses as an ISO-8601 date-time (Python 3.11+ `datetime.fromisoformat` semantics; a trailing `Z` is accepted as UTC). For the `LS_TOUCH_AFTER_TIMESTAMP` comparison, a value without a UTC offset is treated as UTC.
- **Canonical numeric id:** `<PREFIX>-<NNNNNN>` where `<PREFIX>` is one or more uppercase ASCII letters and `<NNNNNN>` is either exactly six digits, or more than six digits not starting with `0`. (`KB-000042` and `KB-1000001` are canonical; `KB-42` and `KB-0000042` are not — the latter closes the `KB-000042`≡`KB-0000042` ambiguity that would corrupt max+1 allocation.)
- **Reserved slug id:** `GOVERNANCE-<SLUG>` where `<SLUG>` is an uppercase letter followed by uppercase letters, digits, or hyphens (e.g. `GOVERNANCE-CHARTER`, `GOVERNANCE-CONVENTIONS`).
- **Reserved schema keys** (the FM1 key namespace; everything outside it is an FM2 extension key, preserved and **never flagged**): `id`, `type`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`, `tags`, `supersedes`, `instructions`, `links`, `pending_upstream`, `ingested_at`, `origin`, `about`.
- **Per-class legal reserved keys and mandatory fields** (`type` itself is legal and mandatory everywhere — FM0 owns it):

| Class | Legal reserved keys | Mandatory (`FM1_FIELD_MISSING`) |
|---|---|---|
| synthetic | `id`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch`, `tags`, `supersedes`, `instructions`, `links`, `pending_upstream` | `id`, `title`, `description`, `status`, `derived_from`, `timestamp`, `last_human_touch` |
| raw (`raw-source`, `chat`) | `id`, `ingested_at`, `origin`, `title` | `id`, `ingested_at`, `origin` (`title` is always written by ingest but **not** mandatory — PRD FM1) |
| raw (`feedback`) | `id`, `ingested_at`, `origin`, `title`, `about` | `id`, `ingested_at`, `origin`, `about` |
| governance (`charter`, `conventions`, `kb-config`, `health`) | `id`, `title`, `description` | `id`, `title`, `description` |
| index | `description`, `title` | `description` (`id` is **forbidden** — index documents are path-addressed) |
| log (operational) | exempt from FM1 checks entirely (§4 step 4) | — |

- **Field shapes** (`FM1_FIELD_INVALID`): `id`, `title`, `description`, `origin`, `instructions`, `supersedes`, `about` — non-empty strings (empty or whitespace-only is invalid); `status` — literally one of `draft`, `current`, `superseded`, `retired` (case-sensitive); `derived_from`, `tags`, `pending_upstream` — lists whose entries are all non-empty strings (empty `tags`/`pending_upstream` lists are legal; an empty `derived_from` is well-shaped but triggers `DG1_NO_PARENTS`); `links` — a mapping of link type to a list of non-empty strings (link types are non-empty strings; an empty mapping or target list is legal); `timestamp`, `last_human_touch`, `ingested_at` — valid timestamps as defined above.
- **Vocabulary checks:** `TAG_UNDECLARED` fires for every `tags` entry absent from config `tags`; `LINKTYPE_UNDECLARED` fires once for every `links` mapping key absent from config `link_types`. Both fire when the corresponding config list is empty (empty means none declared). `TYPE_UNDECLARED` fires for a synthetic `type` absent from a **non-empty** config `types` list; an empty `types` list means the type vocabulary is unconstrained and no finding fires. This asymmetry is the PRD CLI-6 contract.

## 5. Filesystem effects

**None.** `kb validate` is the CLI's first read-only command: after any run — clean, finding-laden, or scoped — every file under the KB root is byte-for-byte identical to before, including `log.md` (validation is a query of integrity, not an event; it is never logged).

## 6. Output

**Text (stdout):** one line per reported finding, in the §4 step 5 order, fields separated by two spaces:

```
<severity>  <path>  <code>  <message>
```

followed by one summary line: `no findings — checked <N> files` when nothing was reported, else `<F> findings (<E> errors, <W> warnings) — checked <N> files`. Counts use the singular noun when the count is 1 (`1 finding (1 error, 0 warnings) — checked 3 files`). `<N>` is the number of in-scope files. Findings are the payload and go to **stdout**; unresolvable-ref notes (`unresolvable ref: <token>`) go to **stderr**. Example:

```
error  synthetic/webhook.md  DG5_NO_SESSION_PARENT  no session record (type chat) among derived_from parents
warning  synthetic/webhook.md  TAG_UNDECLARED  tag 'internal' is not declared in the kb-config.json tags vocabulary
2 findings (1 error, 1 warning) — checked 42 files
```

**JSON (`--json`):**

```json
{
  "ok": false,
  "checked": 42,
  "findings": [
    {
      "code": "DG5_NO_SESSION_PARENT",
      "severity": "error",
      "path": "synthetic/webhook.md",
      "id": "KB-000042",
      "message": "no session record (type chat) among derived_from parents"
    }
  ],
  "counts": {"errors": 1, "warnings": 1},
  "unresolved_refs": []
}
```

- `ok` is `true` **iff the run exits 0** — it reflects the gate outcome including `--strict` and unresolvable refs, so CI consumers read one bit and never recompute the severity/strict logic.
- `checked` — number of in-scope files. `findings` — same order as the text lines; `id` is the class-bearing literal frontmatter id for synthetic, raw, and governance documents, else `null` (malformed, index, log). `counts` counts the reported findings by severity. `unresolved_refs` — the unresolvable ref tokens in argument (then stdin) order, `[]` when none.
- Command-level errors use the shared envelope `{"error": {"code": "E_...", "message": "..."}}` (00-shared §3), exit 2.

The document-set `--output paths|frontmatter|full` convention does not apply — validate returns findings, not documents.

## 7. Findings, errors, and edge cases

### 7.1 Finding codes (normative — the heart of this spec)

Stable across releases (NFR-9): codes are appended, never renamed or re-severitied within a major version. Message **wording** is normative (tests assert substrings); `<placeholders>` are filled per finding. Every code's severity is fixed — no flag changes what is reported (only `--strict` changes what exits 1).

| Code | Severity | Trigger | Message |
|---|---|---|---|
| `FM0_UNPARSEABLE` | error | a `*.md` file that cannot be read as UTF-8 text, or whose frontmatter is missing, unclosed, fails YAML parsing, or is not a mapping | `frontmatter cannot be parsed: <reason>` |
| `FM0_MISSING_TYPE` | error | frontmatter parses but `type` is absent, empty, or not a string (FM0/OKF — applies to **every** `*.md`, including `index.md` and `log.md`) | `missing mandatory type frontmatter field` |
| `LOC_TYPE_MISMATCH` | error | location disagrees with the authoritative `type`: `index` → the file must be named `index.md`; `raw-source`/`chat`/`feedback` → under `raw/sources/`/`raw/chats/`/`raw/feedback/` (any depth); `charter`/`conventions`/`kb-config`/`health` → under `governance/` (any depth); `log` → exactly the root `log.md`; any synthetic type → under `synthetic/` (any depth); **and conversely** a file named `index.md` must carry `type: index` | `type '<type>' does not agree with location '<path>' (expected <expectation>)` |
| `FM1_FIELD_MISSING` | error | a §4.1 mandatory field for the file's class is absent | `missing mandatory field '<field>' for <class> documents` |
| `FM1_FIELD_INVALID` | error | a reserved schema key present with the wrong §4.1 shape (illegal `status`, malformed `links`, non-list `derived_from`/`tags`/`pending_upstream`, non-string or empty string field, unparseable timestamp) | `field '<field>' is invalid: <reason>` |
| `FM1_KEY_FORBIDDEN` | error | a reserved schema key present on a class whose §4.1 legal set does not include it (e.g. `about` outside feedback, `links`/`pending_upstream` outside synthetic, `status`/`derived_from` on a raw document, `id` on an `index.md`). FM2 extension keys (outside the reserved set) are never flagged | `key '<key>' is not part of the <class> schema` |
| `FM1_DESCRIPTION_LONG` | warning | `description` exceeds two sentences (§4.1 heuristic), on any class carrying one | `description exceeds two sentences` |
| `TYPE_UNDECLARED` | warning | a synthetic document's `type` is absent from the config `types` list **and that list is non-empty** (§4.1) | `type '<type>' is not declared in the kb-config.json types vocabulary` |
| `TAG_UNDECLARED` | warning | a `tags` entry absent from the config `tags` list (one finding per undeclared entry; fires even when the list is empty, §4.1) | `tag '<tag>' is not declared in the kb-config.json tags vocabulary` |
| `LINKTYPE_UNDECLARED` | warning | a `links` mapping key absent from config `link_types` (one finding per undeclared key; fires even when the list is empty, §4.1) | `link type '<type>' is not declared in the kb-config.json link_types vocabulary` |
| `ID_INVALID` | error | the `id` string matches neither legal form **for the file's class**: synthetic and raw require a canonical numeric id; governance requires a reserved slug id (§4.1) | `id '<id>' is not a valid <class> id` |
| `ID_PREFIX_MISMATCH` | error | a canonical numeric id whose prefix differs from the configured prefix for the file's class (`id_prefixes`: synthetic→`synthetic`, `raw-source`→`source`, `chat`→`chat`, `feedback`→`feedback`) — catches cross-class ids and numeric use of reserved prefixes (`GOVERNANCE-000001` on a synthetic document) | `id prefix '<prefix>' does not match the configured <class-key> prefix '<expected>'` |
| `ID_DUPLICATE` | error | the same literal `id` string on two or more id-bearing synthetic, raw, or governance documents—one finding **per participant**, naming the others (merge collisions, NFR-7; repair is manual) | `id '<id>' is also carried by <other paths, alphabetical, comma-separated>` |
| `LINK_UNRESOLVED` | error | a `derived_from`, `links`, or `pending_upstream` entry, `supersedes` value, or `about` value that is not an existing document's id (one finding per value; references are canonical ids — a path never resolves here, and an id hidden in a malformed file does not exist) | `<field> reference '<value>' does not resolve to a document id` |
| `PU_NOT_PARENT` | error | a resolved `pending_upstream` entry is absent from the same document's well-shaped `derived_from` list (unresolved markers and malformed/missing `derived_from` do not cascade into this finding) | `pending_upstream reference '<id>' is not among derived_from parents` |
| `DG1_NO_PARENTS` | error | a synthetic document whose `derived_from` is present and well-shaped but empty (an absent key is `FM1_FIELD_MISSING` instead) | `derived_from is empty — every synthetic document declares at least one parent` |
| `DG2_CYCLE` | error | the document participates in a `derived_from` cycle (§4 step 4 graph edges; a self-reference is a cycle of length 1) — one finding per participant, the cycle rendered starting from that document's own id | `derivation cycle: <id> -> ... -> <id>` |
| `DG5_NO_SESSION_PARENT` | error | a synthetic document none of whose resolvable `derived_from` parents is a document of `type: chat` | `no session record (type chat) among derived_from parents` |
| `LS_SUPERSEDES_NOT_MARKED` | error | `supersedes` resolves to a document whose `status` is not literally `superseded` (anchored to the link holder); a target without a `status` reads `has no status` in place of `has status '<status>'` | `supersedes target <id> has status '<status>', expected 'superseded'` |
| `LS_SUPERSEDES_NOT_SYNTHETIC` | error | `supersedes` resolves to a non-synthetic document | `supersedes target <id> is not a synthetic document` |
| `LS_SUPERSEDES_SELF` | error | `supersedes` equals the document's own `id` (preempts the two checks above for that link) | `document supersedes itself` |
| `LS_TOUCH_AFTER_TIMESTAMP` | warning | both `last_human_touch` and `timestamp` parse (§4.1) and `last_human_touch` is strictly later | `last_human_touch <value> is later than timestamp <value>` |

22 stable finding codes (17 errors, 5 warnings): `FM1_DESCRIPTION_LONG`, `TYPE_UNDECLARED`, `TAG_UNDECLARED`, `LINKTYPE_UNDECLARED`, and `LS_TOUCH_AFTER_TIMESTAMP` are warnings; all others are errors.

### 7.2 Command-level errors (end the run — no findings are produced)

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E1 | Not inside a KB (no `kb-config.json` found; also `--kb` pointing at a config-less directory) | `E_NO_KB`, message per 00-shared §1 | 2 |
| E2 | `kb-config.json` unparseable | `E_CONFIG_INVALID` | 2 |
| E3 | Config `schema` newer than the CLI knows | `E_SCHEMA_UNSUPPORTED` | 2 |
| E4 | Unknown option / bad flag value | usage error (Typer-rendered message on stderr) | 2 |

### 7.3 Edge cases (not errors)

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E5 | `REF` argument (or stdin ref) unresolvable against the check universe | `unresolvable ref: <token>` on stderr; remaining refs processed; token listed in `--json` `unresolved_refs`; **not a finding** | ≥ 1 |
| E6 | `KB.malformed` non-empty | no guard — validate runs to completion and reports each malformed file as `FM0_UNPARSEABLE`/`FM0_MISSING_TYPE` alongside every other finding | per findings |
| E7 | Scoped run naming only clean documents while other documents have errors | out-of-scope findings are not reported and do not affect the exit code | 0 |
| E8 | A file with several violations at once | one finding per violated rule, all reported, sorted by (path, code, occurrence) | per findings |
| E9 | Empty KB (config plus zero `*.md` files) | `no findings — checked 0 files` | 0 |
| E10 | Fresh `kb init` scaffold | born valid: no findings (kb-init AC30's gate) | 0 |
| E11 | Warnings only, no `--strict` | findings printed, exit 0 | 0 |
| E12 | Warnings only, `--strict` | identical findings printed, exit 1 | 1 |
| E13 | Refs passed as arguments while stdin is also piped | arguments win; stdin is not read (00-shared §4.2) | — |
| E14 | `derived_from` entry duplicated in one document | not flagged (kb create deduplicates at birth; hand-introduced duplicates are harmless to the graph) | — |
| E15 | Two `supersedes` links naming the same target | not flagged — the coupling rule constrains the target's status, not its in-degree; lineage judgment is `kb-lint`'s | — |
| E16 | Numerically equal but textually distinct ids (`KB-000042` vs `KB-0000042`) | the non-canonical form is `ID_INVALID`; `ID_DUPLICATE` compares literal strings only | 1 |

### 7.4 Owned elsewhere (deliberately not findings here)

- **Missing `index.md` in a directory, or a stale index listing** — `kb index --check` (CLI-9) owns the directory invariant's presence and freshness; the CI gate is `kb validate && kb index --check`. Validate checks every *existing* `index.md` as a document (FM0, schema, forbidden `id`, location).
- **Missing root `log.md`** — not a finding; the write commands recreate it on demand (kb-ingest E16, kb-create E20).
- **`kb-config.json` content** — an unparseable or unsupported config is a command error (E2/E3), never a finding; validate cannot check a KB it cannot configure itself against.

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`. Each is independently testable with an unambiguous pass condition. Fixtures build violating KBs with the `tests/conftest.py` helpers, one rule violated at a time except where an AC states otherwise; message assertions are substring matches against §7.1 wording, ordering and counts asserted exactly. Every §7.1 finding code has at least one triggering AC and at least one clean-negative AC; every §7.2/§7.3 row and §4 step maps to at least one AC.

**Coverage map:** clean KBs & read-only AC1–AC5 (§1, §4 step 2, §5, E9/E10) · FM0 AC6–AC10 (§4 step 4, E6) · location AC11–AC15 and AC75 (§7.1 `LOC_TYPE_MISMATCH`) · schema: missing fields AC16–AC20 (§4.1 mandatory table) · schema: invalid shapes AC21–AC25 and AC77 (§4.1 field shapes) · forbidden keys & FM2 AC26–AC28 and AC76 · description & vocabularies AC29–AC33 and AC78/AC82 (§4.1 heuristics/vocabulary rules) · ids AC34–AC39 (§4.1 id forms, E16) · references AC40–AC43 and AC79–AC80 · graph AC44–AC49 and AC81 (DG1/DG2/DG5, AL3, termination theorem) · lifecycle AC50–AC54 (LS codes) · severity, `--strict` & exit codes AC55–AC57/AC82 (E11/E12) · scoping & pipelines AC58–AC64 (§4 steps 3/5, E5/E7/E13) · output & JSON AC65–AC69 (§6) · environment, usage, help & Git AC70–AC74 (E1–E4, §3, 00-shared).

| # | Given / When / Then |
|---|---|
| AC1 | Given a fresh `kb init` scaffold, when `kb validate` runs, then exit 0 and stdout is exactly `no findings — checked 12 files` (8 `index.md` + 3 governance documents + `log.md`) — the scaffold is born valid (E10; kb-init AC30 is a hard gate). |
| AC2 | Given a fully conforming populated KB — a raw source, a chat record, a feedback record with `about`, two synthetic documents (one with `tags`/`instructions`, one a supersession pair whose target is `superseded`), all types and tags declared in `kb-config.json` — when `kb validate` runs, then exit 0 and no finding is reported: no §7.1 code fires on conforming documents. |
| AC3 | Given a KB with at least one error finding, when `kb validate` runs, then afterwards every file under the KB root is byte-for-byte identical to before — including `log.md` (no entry appended) — and no new file exists (§5). |
| AC4 | Given a directory containing only a valid `kb-config.json` and no `*.md` at all, when `kb validate` runs, then exit 0 and stdout is exactly `no findings — checked 0 files` (E9). |
| AC5 | Given a KB whose only defect is one malformed file, when `kb validate` runs, then exit 1 — validate runs despite non-empty `KB.malformed` (E6), unlike the write commands' guard, and reports the file. |
| AC6 | Given case (a) a `*.md` file with no frontmatter block at all, case (b) one whose closing `---` is missing, and case (c) one whose frontmatter is invalid YAML, then each yields one `FM0_UNPARSEABLE` error with message containing `frontmatter cannot be parsed`. |
| AC7 | Given a file whose frontmatter is a YAML list (not a mapping) (case a) and a file that is not valid UTF-8 (case b), then each yields `FM0_UNPARSEABLE`. |
| AC8 | Given case (a) frontmatter with no `type` key, case (b) `type: ""`, and case (c) `type: [x]` (non-string), then each yields one `FM0_MISSING_TYPE` error — and no other finding is anchored to that file (classification stops, §4 step 4). |
| AC9 | Given a `log.md` whose frontmatter lacks `type`, then `FM0_MISSING_TYPE` anchored to `log.md` — FM0 applies to every `*.md`, operational files included. |
| AC10 | Given a stray `README.md` at the KB root with no frontmatter, then `FM0_UNPARSEABLE` anchored to `README.md` — the check universe is every `*.md` under the root (§4 step 2). |
| AC11 | Given a `type: chat` document at `raw/sources/x.md` (case a) and a `type: raw-source` document at `synthetic/x.md` (case b), then each yields one `LOC_TYPE_MISMATCH` error naming the type. |
| AC12 | Given a synthetic-typed document at the KB root (case a), a `type: conventions` document under `synthetic/` (case b), and a `type: charter` document under `synthetic/` (case c), then each yields `LOC_TYPE_MISMATCH`. |
| AC13 | Given a `type: log` file at `raw/notes.md`, then `LOC_TYPE_MISMATCH` (`type: log` is reserved for the root `log.md`) — and the root `log.md` itself yields no finding. |
| AC14 | Given case (a) a `type: index` document named `listing.md` and case (b) a file named `index.md` carrying `type: spec`, then each yields `LOC_TYPE_MISMATCH` (the index rule is bidirectional). |
| AC15 | Given a `type: raw-source` document at `raw/sources/api/deep/x.md` and a synthetic document at `synthetic/specs/x.md`, then neither yields `LOC_TYPE_MISMATCH` (class directories match at any depth). |
| AC16 | Given a synthetic document missing `title`, then one `FM1_FIELD_MISSING` error whose message names `'title'`; given one missing `id`, `description`, `status`, `derived_from`, `timestamp`, and `last_human_touch` in turn (cases), each yields `FM1_FIELD_MISSING` naming that field. |
| AC17 | Given one synthetic document missing `title`, `status`, and `timestamp` at once, then exactly three `FM1_FIELD_MISSING` findings anchor to it (E8: one finding per violated rule). |
| AC18 | Given a raw-source document missing `ingested_at` (case a) and one missing `origin` (case b), then each yields `FM1_FIELD_MISSING`; given a raw-source missing `title` (case c), then **no** finding — `title` is not part of FM1's mandatory raw set. |
| AC19 | Given a feedback document without `about`, then `FM1_FIELD_MISSING` naming `'about'`; a chat document without `about` yields nothing. |
| AC20 | Given a governance document (`type: charter` or `type: conventions`) missing `description` (case a) and an `index.md` missing `description` (case b), then each yields `FM1_FIELD_MISSING`. |
| AC21 | Given a synthetic document with `status: accepted` (case a) and `status: Current` (case b — case-sensitive), then each yields one `FM1_FIELD_INVALID` error naming `'status'`. |
| AC22 | Given `derived_from: CHAT-000001` (a plain string, not a list) (case a) and `derived_from: [CHAT-000001, 42]` (a non-string entry) (case b), then each yields `FM1_FIELD_INVALID` naming `'derived_from'` — and no DG1/DG2/DG5 finding anchors to that document (graceful degradation, §4 step 4). |
| AC23 | Given `timestamp: not-a-date` on a synthetic document (case a) and `ingested_at: 2026-13-40` on a raw document (case b), then each yields `FM1_FIELD_INVALID`; given `timestamp: 2026-07-16T10:00:00+02:00` (case c, ISO-8601 with offset), then no finding — validity is ISO-8601, not the emitters' `Z` form. |
| AC24 | Given `title: ""` (case a) and `description: "   "` (case b) on a synthetic document, then each yields `FM1_FIELD_INVALID` (non-empty string required). |
| AC25 | Given `tags: api` (a string, not a list) on a synthetic document, then `FM1_FIELD_INVALID` naming `'tags'`; given `tags: []` (case b), then no finding (an empty tags list is legal). |
| AC26 | Given `about: KB-000001` on a raw-source document (case a), `status: current` on a chat document (case b), and `derived_from: [RAW-000001]` on a governance document (case c), then each yields one `FM1_KEY_FORBIDDEN` error naming the key. |
| AC27 | Given an `index.md` carrying `id: KB-000009`, then `FM1_KEY_FORBIDDEN` naming `'id'` (index documents are path-addressed) — and no `ID_*` finding anchors to it. |
| AC28 | Given a synthetic and a raw document each carrying an unknown key `custom_field: x`, then **no** finding fires for it (FM2: extension keys are preserved and never flagged). |
| AC29 | Given a synthetic document with a three-sentence `description` (case a) and an `index.md` with a three-sentence `description` (case b), then each yields one `FM1_DESCRIPTION_LONG` **warning**; a two-sentence description (case c) yields nothing (§4.1 heuristic). |
| AC30 | Given config `types: ["spec"]` and a synthetic document of `type: retro`, then one `TYPE_UNDECLARED` warning naming `retro`; a `type: spec` document (case b) yields nothing. |
| AC31 | Given config `types: []` and a synthetic document of any type, then **no** `TYPE_UNDECLARED` finding — an empty types list means the vocabulary is not yet constrained (§4.1). |
| AC32 | Given config `tags: ["api"]` and a synthetic document with `tags: [api, internal, wip]`, then exactly two `TAG_UNDECLARED` warnings — one naming `internal`, one naming `wip`, in list order (occurrence ordering) — and none naming `api`. |
| AC33 | Given config `tags: []` and a document with `tags: [api]`, then one `TAG_UNDECLARED` warning — an empty tags list means no tags are declared (§4.1; asymmetric with AC31 by design). |
| AC34 | Given a synthetic document with `id: KB-42` (fewer than six digits) (case a), `id: kb-000042` (lowercase) (case b), and `id: KB-FOO` (slug form on a non-governance class) (case c), then each yields one `ID_INVALID` error. |
| AC35 | Given a synthetic document with `id: KB-0000042` (seven digits, leading zero), then `ID_INVALID` — non-canonical numeric forms are invalid (E16 closes the `KB-000042`≡`KB-0000042` allocation ambiguity). |
| AC36 | Given a governance document with `id: GOVERNANCE-000001` (numeric on governance) (case a) and one with `id: CONV-CONVENTIONS` (wrong slug prefix) (case b), then each yields `ID_INVALID`; `GOVERNANCE-CHARTER`/`GOVERNANCE-CONVENTIONS` (case c) and a synthetic `KB-1000001` (case d) yield nothing. |
| AC37 | Given a synthetic document with `id: RAW-000009` (case a) and a chat document with `id: FEED-000002` (case b), then each yields one `ID_PREFIX_MISMATCH` error naming the expected prefix. |
| AC38 | Given config `id_prefixes.synthetic == "SYN"` and a synthetic document with `id: KB-000001`, then `ID_PREFIX_MISMATCH` (the configured prefix wins); a `SYN-000001` document yields nothing. |
| AC39 | Given two documents both carrying `id: KB-000007`, then exactly two `ID_DUPLICATE` errors — one anchored to each file, each message naming the other's path (merge-collision detection, one finding per participant). |
| AC40 | Given a synthetic document with `derived_from: [CHAT-000001, KB-999999, RAW-999999]` where only `CHAT-000001` exists, then exactly two `LINK_UNRESOLVED` errors naming `derived_from` and the unresolvable value, in list order. |
| AC41 | Given `supersedes: KB-999999` (case a) and a feedback document with `about: KB-999999` (case b), then each yields `LINK_UNRESOLVED` naming the field. |
| AC42 | Given a synthetic document whose `derived_from` entry is the **path** `raw/chats/session.md` (the file exists and carries `CHAT-000001`), then `LINK_UNRESOLVED` — link values are canonical ids, never paths. |
| AC43 | Given a synthetic document with `derived_from: [GOVERNANCE-CHARTER, GOVERNANCE-CONVENTIONS, CHAT-000001]`, then no `LINK_UNRESOLVED` — reserved slug ids resolve like any id. |
| AC44 | Given a synthetic document with `derived_from: []`, then exactly one `DG1_NO_PARENTS` error — no `FM1_FIELD_MISSING` for `derived_from` (present-but-empty is DG1; absent is FM1, per AC16) and no `DG5_NO_SESSION_PARENT` (DG1 preempts DG5, §4 step 4). |
| AC45 | Given synthetic documents `KB-000001` and `KB-000002` each in the other's `derived_from` (plus a shared chat parent), then exactly two `DG2_CYCLE` errors, one per participant, each message starting the cycle at that document's own id. |
| AC46 | Given a synthetic document whose `derived_from` contains its own id, then one `DG2_CYCLE` error (a self-reference is a cycle of length 1). |
| AC47 | Given a diamond derivation (`KB-000004` derives from `KB-000002` and `KB-000003`, both deriving from `KB-000001`, all with chat parents), then no `DG2_CYCLE` — diamonds are legal; only cycles are findings. |
| AC48 | Given a synthetic document whose parents are one raw source and one synthetic document only, then one `DG5_NO_SESSION_PARENT` error; adding a `type: chat` parent (case b) clears it. |
| AC49 | Given a synthetic document with `derived_from: [CHAT-999999]` (unresolvable), then `LINK_UNRESOLVED` **and** `DG5_NO_SESSION_PARENT` (no resolvable chat parent); given `derived_from: [KB-999999, CHAT-000001]` (case b, resolvable chat), then `LINK_UNRESOLVED` only — DG5 evaluates over the parents that resolve (§4 step 4). |
| AC50 | Given `supersedes: KB-000031` where `KB-000031` has `status: current` (case a) and no `status` at all (case b), then each yields one `LS_SUPERSEDES_NOT_MARKED` error anchored to the **link holder** — case (a)'s message containing `has status 'current'`, case (b)'s `has no status`. |
| AC51 | Given `supersedes: RAW-000001` (a raw document, `status`-less by schema), then one `LS_SUPERSEDES_NOT_SYNTHETIC` error — and no `LS_SUPERSEDES_NOT_MARKED` for the same link. |
| AC52 | Given a synthetic document whose `supersedes` equals its own id, then exactly one `LS_SUPERSEDES_SELF` error and neither `LS_SUPERSEDES_NOT_MARKED` nor `LS_SUPERSEDES_NOT_SYNTHETIC` (preemption, §7.1). |
| AC53 | Given a conforming supersession pair (target `status: superseded`), then no `LS_*` finding (clean negative). |
| AC54 | Given `last_human_touch` one hour later than `timestamp`, then one `LS_TOUCH_AFTER_TIMESTAMP` **warning**; equal values (case b) yield nothing; an unparseable `last_human_touch` (case c) yields `FM1_FIELD_INVALID` and **no** `LS_TOUCH_AFTER_TIMESTAMP` (graceful degradation). |
| AC55 | Given a KB whose only findings are warnings, when `kb validate` runs, then the warnings are printed and exit is 0 (E11). |
| AC56 | Given AC55's KB, when `kb validate --strict` runs, then the reported findings are **identical** to AC55's (same lines, same order) and exit is 1 (E12 — `--strict` promotes only the exit code). |
| AC57 | Given a KB with one error finding, then exit 1 with and without `--strict`. |
| AC58 | Given a KB where `synthetic/a.md` is clean and `synthetic/b.md` has an error, when `kb validate synthetic/a.md` runs, then no finding is reported and exit is 0 (E7 — scope filters findings and the exit code). |
| AC59 | Given AC58's KB, when `kb validate` runs scoped to `b` by id (case a) and by path without the `.md` extension (case b), then the same `b`-anchored finding is reported both times, exit 1. |
| AC60 | Given AC58's KB and `synthetic/b.md` piped on stdin with no ref arguments, then the outcome equals AC59's (00-shared §4.2); given refs on **both** stdin and the command line, then the arguments win and stdin is not read (E13). |
| AC61 | Given two documents sharing an id, when `kb validate` runs scoped to one of them, then exactly one `ID_DUPLICATE` finding is reported (that document's), its message naming the out-of-scope partner's path (anchor rule, §4 step 4). |
| AC62 | Given a malformed file at `raw/sources/broken.md`, when `kb validate raw/sources/broken.md` runs, then its `FM0_UNPARSEABLE` finding is reported — a path ref resolves against malformed files (§4 step 3). |
| AC63 | Given `kb validate KB-999999 synthetic/a.md` where `KB-999999` resolves to nothing and `synthetic/a.md` is clean, then stderr contains `unresolvable ref: KB-999999`, stdout reports no finding, and exit is 1 (E5 — an unresolvable ref alone forces exit ≥ 1). |
| AC64 | Given one clean document named twice (`kb validate KB-000001 KB-000001`), then output equals naming it once (duplicate refs deduplicated, §4 step 3). |
| AC65 | Given a KB producing one error and one warning on the same document, then stdout's finding lines match `<severity>  <path>  <code>  <message>` (two-space separated), sorted by (path, code), followed by exactly `2 findings (1 error, 1 warning) — checked <N> files` with `<N>` the file count — and nothing is written to stderr. |
| AC66 | Given a KB with findings across several files, then finding lines are sorted by path first, then code — asserted against a fixture with interleaved paths and codes. |
| AC67 | Given `--json` on AC65's KB, then stdout parses as JSON with exactly the fields `ok` (false), `checked` (int), `findings` (array in text order, each with exactly `code`, `severity`, `path`, `id`, `message`), `counts` (`{"errors": 1, "warnings": 1}`), `unresolved_refs` (`[]`), and nothing else on stdout; the `id` field is `null` for findings anchored to files without a string frontmatter id. |
| AC68 | Given `--json` on case (a) a warnings-only KB, then `ok` is `true` and exit 0; case (b) the same KB with `--strict`, then `ok` is `false` and exit 1; case (c) a clean KB with one unresolvable ref argument, then `ok` is `false`, `unresolved_refs == ["<token>"]`, exit 1 — `ok` ⟺ exit 0 (§6). |
| AC69 | Given `--json` on a clean whole-KB run, then the envelope is `ok: true`, `checked` = the file count, `findings: []`, `counts: {"errors": 0, "warnings": 0}`, `unresolved_refs: []`. |
| AC70 | Given case (a) `kb validate` run outside any KB and case (b) `--kb` pointing at a config-less directory, then exit 2 with `E_NO_KB` and the 00-shared §1 message (E1); with `--json`, stdout is exactly the error envelope. |
| AC71 | Given a KB whose `kb-config.json` is invalid JSON, then exit 2 with `E_CONFIG_INVALID` (E2). |
| AC72 | Given a KB whose config `schema` is `999`, then exit 2 with `E_SCHEMA_UNSUPPORTED` (E3). |
| AC73 | When `kb validate --bogus-flag` runs, then exit 2 with a usage error on stderr (E4); when `kb validate --help` runs, then exit 0 and the output contains every normative string from §3 — each description sentence, each option help string, each example line. |
| AC74 | Given a whole-KB run over a finding-laden KB, then no `git` subprocess was invoked (PATH shim or subprocess spy) and no `.git/` directory exists (Git-agnostic). |
| AC75 | Given the pinned `governance/charter.md`, then it classifies as governance and produces no location, schema, or id finding; moving the same `type: charter` document under `synthetic/` produces `LOC_TYPE_MISMATCH`. |
| AC76 | Given a synthetic document with well-shaped `links` and `pending_upstream`, then neither key produces `FM1_KEY_FORBIDDEN`; placing either reserved key on a raw, governance, or index document produces one `FM1_KEY_FORBIDDEN` per key and no reference/vocabulary cascade for that key. |
| AC77 | Given synthetic `links` that is not a mapping, has an empty/non-string key, or has a value that is not a list of non-empty strings, each case produces `FM1_FIELD_INVALID` naming `links`; malformed `pending_upstream` that is not a list of non-empty strings likewise produces `FM1_FIELD_INVALID` naming `pending_upstream`, with no reference or `PU_NOT_PARENT` cascade. Empty `links: {}` and `pending_upstream: []` are well-shaped. |
| AC78 | Given config `link_types: [references]` and synthetic `links: {references: [KB-000002], custom: [KB-000003]}` with both targets resolvable, then exactly one `LINKTYPE_UNDECLARED` warning names `custom`; `references` produces none. Given `link_types: []`, both mapping keys produce warnings because none are declared. |
| AC79 | Given a synthetic document whose well-shaped `links` contains one resolvable and one unresolvable target and whose `pending_upstream` contains one unresolvable id, then one `LINK_UNRESOLVED` error is emitted per unresolvable value, using field labels `links` and `pending_upstream`; resolvable raw, governance, and synthetic associative-link targets produce no finding. |
| AC80 | Given `pending_upstream: [KB-000007]` where `KB-000007` resolves but is absent from the document's `derived_from`, then one `PU_NOT_PARENT` error is emitted; adding it to `derived_from` clears the finding. An unresolvable marker produces `LINK_UNRESOLVED` only, and a malformed/missing `derived_from` produces its FM1 finding without `PU_NOT_PARENT` (no cascade). |
| AC81 | Given two synthetic documents that mutually `references` each other through `links`, each with a valid chat parent in `derived_from`, then no `DG2_CYCLE` is emitted. Associative links neither satisfy DG1/DG5 nor participate in derivation-chain termination (AL3). |
| AC82 | Given a KB whose only finding is `LINKTYPE_UNDECLARED`, a normal run reports the warning and exits 0; `--strict` reports the identical finding and exits 1. |

## 9. Out of scope

- **Operational reports and semantic review** — deterministic drift, impact, and orphan computation belongs to `kb report` (CLI-15); `kb-lint` consumes those reports and adds judgment about contradictions, DG3 coverage, `instructions` conflicts, retirement, and recommended follow-up. `kb validate` supplies the document-integrity findings both surfaces build on.
- **Directory-invariant presence and index freshness** — `kb index --check` (CLI-9) owns both (§7.4); the CI gate composes the two commands.
- **Fixing anything** — validate writes nothing; repair belongs to the write commands, `kb mv`, `kb index`, manual edits, or lint-proposed fixes. Duplicate-id repair after merges is manual (no `kb renumber` in v1).
- **`status: superseded` with no inbound `supersedes` link** — not mechanically wrong (legitimate pre-merge and adoption states exist); lineage review is lint territory.
- **Duplicate `derived_from` entries** (E14) and link *quality* (is this the right parent?) — judgment.
- **`about` target class** — `about` must resolve (LINK_UNRESOLVED) but may name any id-carrying document, mirroring `kb ingest`'s contract.
- **Template document conventions** — `governance/templates/` holds no specified document form yet (PRD-level gap); a template carrying a synthetic `type` will flag `LOC_TYPE_MISMATCH` until templates are specified.
- **Document-set output modes** (`--output paths|frontmatter|full`) — validate returns findings, not documents.
- **All Git operations** (00-shared): validate never runs `git` or inspects Git state; CI wires it into merge checks externally (NFR-7).
