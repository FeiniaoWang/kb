# `kb revise` — synthetic mutation (CLI-14)

**Status:** Normative. Assumes [00-shared.md](00-shared.md).
**Source:** [PRD §7.1 CLI-14, §6.6–6.9, LS5, CS6](../../prd.md).

## 1. Purpose

The single in-place mutation path for synthetic documents: consolidation
(append parents, CS6), associative links (§6.9), body replacement, explicit
human-directed status transitions (LS5, never `superseded`), and
`pending_upstream` marker management. Preserves the id (revision, not
supersession). Advances `timestamp` always and `last_human_touch` only when
the change is human-confirmed (`--human`). Appends a `revised` log entry.
Never touches `index.md` (revise cannot change `title` or `description`).

## 2. CLI surface

`kb revise REF [--add-parent REF]... [--link TYPE=REF]... [--body-file FILE|-]
[--status draft|current|retired] [--pending REF]... [--clear-pending REF]...
[--human] [--actor NAME] [--kb PATH] [--json]`

| Surface | Kind | Value | Default | Meaning |
|---|---|---|---|---|
| `REF` | positional | id or KB-relative path | — | The synthetic document to revise (00-shared §4.1; single ref, no stdin batch) |
| `--add-parent` | option, repeatable | REF | — | Append a parent to `derived_from` (consolidation, CS6); stored as canonical id, argument order preserved |
| `--link` | option, repeatable | `TYPE=REF` | — | Append an associative link target under link type `TYPE` (§6.9); undeclared `TYPE` warns, never blocks |
| `--body-file` | option | path or `-` | absent | Replace the body from a file or stdin. Absent = body unchanged; empty/whitespace content = the empty body |
| `--status` | option | `draft`, `current`, `retired` | absent | Explicit human-directed status transition (LS5). `superseded` is not accepted — only `kb create --supersedes` sets it |
| `--pending` | option, repeatable | REF | — | Add a `pending_upstream` marker naming a parent whose revision awaits propagation (CS6) |
| `--clear-pending` | option, repeatable | REF | — | Remove a `pending_upstream` marker (the revision that performs the propagation) |
| `--human` | flag | — | off | The revision is human-confirmed: `last_human_touch` advances to the same instant as `timestamp` |
| `--actor` | option | text | `kb-cli` | Actor recorded in the log entry |
| `--kb` | option | path | discovered | KB root override (00-shared §1) |
| `--json` | flag | — | off | JSON envelope (00-shared §3) |

At least one change option is required: `--add-parent`, `--link`,
`--body-file`, `--status`, `--pending`, or `--clear-pending`. `--human` and
`--actor` alone are not a change.

## 3. Execution

Pre-flight then write: steps 1–13 complete before the first byte is written;
any failure among them leaves the KB untouched. Only an OS error inside the
write phase (steps 14–15) can leave partial state (documented, not rolled
back — same stance as kb create E14).

1. Discover root, load config (00-shared §1): `E_NO_KB` / `E_CONFIG_INVALID`
   / `E_SCHEMA_UNSUPPORTED`, exit 2.
2. Scan. `KB.malformed` non-empty → `E_REVISE_MALFORMED`, exit 2, naming the
   malformed paths and directing to `kb validate`.
3. Validate the surface: no change option at all → `E_REVISE_NO_CHANGES`,
   exit 2. Each `--link` token must be `TYPE=REF` with non-empty halves →
   else `E_REVISE_LINK_INVALID`, exit 2.
4. Resolve `REF` (00-shared §4.1). Unresolvable → `E_REVISE_TARGET_UNRESOLVED`,
   exit 1. The target must be `DocClass SYNTHETIC` with an id, and its
   `status` must not be `superseded` (a superseded document is frozen
   lineage; revise its live successor) → else `E_REVISE_TARGET_INVALID`,
   exit 1.
5. The target's existing `derived_from` must be a list of non-empty strings,
   its `links` (when present) a mapping of non-empty string to list of
   non-empty strings, and its `pending_upstream` (when present) a list of
   non-empty strings — else the document cannot be edited losslessly:
   `E_REVISE_NOT_EDITABLE`, exit 1, directing to `kb validate`.
6. Resolve each `--add-parent` to a canonical id (unresolvable or no id →
   `E_REVISE_PARENT_UNRESOLVED`, exit 1). An id already in `derived_from`,
   or repeated among the arguments → `E_REVISE_PARENT_DUPLICATE`, exit 1.
7. DG2 pre-flight: for each added parent that is itself synthetic, walk the
   current derivation graph (`derived_from` edges only — associative links
   are exempt, AL3) from that parent; if the target is reachable, the append
   would close a cycle → `E_REVISE_CYCLE`, exit 1, message naming the cycle
   path (`KB-A -> KB-B -> ... -> KB-A`).
8. Resolve each `--link` REF to a canonical id (unresolvable or no id →
   `E_REVISE_LINK_UNRESOLVED`, exit 1). A target already present under the
   same link type, or repeated for the same type among the arguments →
   `E_REVISE_LINK_DUPLICATE`, exit 1. A `TYPE` absent from config
   `link_types` proceeds with one stderr warning naming the type (mirrors
   create's tag warning; empty `link_types` = none declared, every type
   warns). Targets append in argument order after existing targets; a new
   type key appends after existing keys.
9. Resolve each `--pending` and `--clear-pending` to a canonical id
   (unresolvable or no id → `E_REVISE_PENDING_UNRESOLVED`, exit 1). Then
   `E_REVISE_PENDING_INVALID`, exit 1, when: the same id appears in both
   `--pending` and `--clear-pending`; a `--pending` id is not among the
   final `derived_from` (existing plus this run's appends — the marker names
   a parent, CS6); a `--pending` id is already marked or repeated; a
   `--clear-pending` id is not currently marked. Adds append in argument
   order; when every marker is cleared the `pending_upstream` key is
   removed entirely.
10. Read the body when `--body-file` was given: file path → read it
    (missing, unreadable, not a regular file → `E_REVISE_BODY_NOT_FOUND`,
    exit 2); `-` → read stdin to EOF. Bytes must decode as strict UTF-8 →
    else `E_REVISE_BODY_NOT_TEXT`, exit 1. Normalize CRLF/CR to LF, ensure
    exactly one trailing newline; empty or whitespace-only input yields the
    empty body.
11. Compute the revision instant `T` (UTC, second precision, `Z` suffix),
    strictly later than the target's existing valid `timestamp` even when
    the wall clock has not advanced.
    New frontmatter: `timestamp: T`; `last_human_touch: T` iff `--human`;
    `derived_from`/`links`/`pending_upstream`/`status` per steps 6–9 (only
    keys actually changed are rewritten; untouched keys — including unknown
    extension keys, FM2 — are preserved byte-for-byte).
12. Validate the complete proposed target state with the document-integrity
    rules enforced by `kb validate`, including schema validity, existing and
    proposed references, and all `derived_from` graph effects (DG2). Any
    error finding anchored to the proposed target or introduced by its new
    graph edges → `E_REVISE_VALIDATION`, exit 1, listing stable finding codes;
    unrelated pre-existing findings elsewhere do not block. Warnings do not
    block and are reported once.
13. Format the `revised` log row (actor, target id, note = target path plus
    a change summary such as `+parent CHAT-000031, +link references=KB-000012,
    status current, body, +pending KB-000007, -pending KB-000003`). Encoding
    failure here is pre-flight `E_REVISE_IO`, exit 2.
14. Before the write phase, verify the identity and bytes captured for the
    target and every resolved final parent/link/pending document. A deletion
    or replacement during body acquisition is `E_REVISE_IO`, with no write.
    Then overwrite the target document (identity-checked, symlink-resistant
    — 00-shared safeio conventions) and append the log row.
15. Report.

## 4. Errors

| # | Condition | Code | Exit |
|---|---|---|---|
| E1 | No KB root | `E_NO_KB` | 2 |
| E2 | Config invalid / schema unsupported | `E_CONFIG_INVALID` / `E_SCHEMA_UNSUPPORTED` | 2 |
| E3 | Malformed documents in scan | `E_REVISE_MALFORMED` | 2 |
| E4 | No change option given | `E_REVISE_NO_CHANGES` | 2 |
| E5 | `--link` token not `TYPE=REF` | `E_REVISE_LINK_INVALID` | 2 |
| E6 | Target unresolvable | `E_REVISE_TARGET_UNRESOLVED` | 1 |
| E7 | Target not synthetic, no id, or `superseded` | `E_REVISE_TARGET_INVALID` | 1 |
| E8 | Target frontmatter not losslessly editable | `E_REVISE_NOT_EDITABLE` | 1 |
| E9 | `--add-parent` unresolvable / no id | `E_REVISE_PARENT_UNRESOLVED` | 1 |
| E10 | Parent already present or repeated | `E_REVISE_PARENT_DUPLICATE` | 1 |
| E11 | Append would close a derivation cycle | `E_REVISE_CYCLE` | 1 |
| E12 | `--link` REF unresolvable / no id | `E_REVISE_LINK_UNRESOLVED` | 1 |
| E13 | Link target duplicate within its type | `E_REVISE_LINK_DUPLICATE` | 1 |
| E14 | `--pending`/`--clear-pending` unresolvable / no id | `E_REVISE_PENDING_UNRESOLVED` | 1 |
| E15 | Pending marker conflict (both-add-and-clear, not-a-parent, already marked, repeated, clearing absent) | `E_REVISE_PENDING_INVALID` | 1 |
| E16 | `--body-file` path missing/unreadable/not regular | `E_REVISE_BODY_NOT_FOUND` | 2 |
| E17 | Body bytes not UTF-8 | `E_REVISE_BODY_NOT_TEXT` | 1 |
| E18 | OS error in context acquisition, preparation, or write | `E_REVISE_IO` | 2 |
| E19 | Proposed revised document fails document-integrity validation | `E_REVISE_VALIDATION` | 1 |

## 5. Output

Text (stdout; warnings to stderr):

```
updated  synthetic/specs/retry-policy.md
revised KB-000042 as synthetic/specs/retry-policy.md
```

JSON: `{"ok": true, "id": "KB-000042", "path": "synthetic/specs/retry-policy.md",
"updated": ["synthetic/specs/retry-policy.md"], "warnings": []}`.
Error envelope per 00-shared §3.

## 6. Acceptance criteria

AC01 append one parent: `derived_from` gains the canonical id at the end; all
other frontmatter bytes unchanged; `timestamp` strictly advanced; `last_human_touch`
unchanged without `--human`.
AC02 `--human` advances `last_human_touch` to equal the new `timestamp`.
AC03 path REF and id REF resolve to the same target.
AC04 parent by path stored as canonical id.
AC05 repeated `--add-parent` of the same ref → E10, nothing written.
AC06 parent already in `derived_from` → E10.
AC07 unresolvable parent → E9.
AC08 direct cycle (child as parent of its own ancestor) → E11 with the cycle
path in the message.
AC09 transitive cycle (A→B→C, revise C adding parent A... i.e. an append
whose reachability closes a longer loop) → E11.
AC10 raw and governance parents append without cycle checks beyond
resolution.
AC11 `--link references=KB-…` creates the `links` key when absent, with one
type and one target.
AC12 `--link` appends to an existing type's list, preserving prior order.
AC13 two `--link` options with different types create both keys in argument
order after any existing keys.
AC14 duplicate target within a type (existing or repeated argument) → E13.
AC15 malformed token (`--link references` / `=KB-1` / `references=`) → E5,
exit 2.
AC16 unresolvable link REF → E12.
AC17 undeclared link TYPE proceeds, one stderr warning naming it; declared
types warn nothing.
AC18 with `link_types: []` every link TYPE warns.
AC19 `--status current` rewrites only `status` (plus `timestamp`); `draft`
and `retired` likewise; the flag accepts no other value (Typer usage error
for `superseded`).
AC20 revising a `superseded` target → E7.
AC21 setting the status it already has succeeds (idempotent transition,
still a change).
AC22 `--pending P` with P a parent adds the marker; key created when
absent.
AC23 `--pending` id not among final parents → E15; adding the parent in the
same run (`--add-parent P --pending P`) succeeds.
AC24 already-marked or repeated `--pending` → E15; unresolvable → E14.
AC25 `--clear-pending` removes the marker; clearing the last marker removes
the key entirely.
AC26 clearing an absent marker → E15; same id in add and clear → E15.
AC27 `--body-file FILE` replaces the body; frontmatter block untouched
except the revised keys.
AC28 `--body-file -` reads stdin; CRLF normalized; exactly one trailing
newline.
AC29 empty/whitespace body input yields the empty body (document ends after
the closing `---`).
AC30 omitted `--body-file` leaves the body byte-identical.
AC31 non-UTF-8 body → E17, exit 1; missing body file → E16, exit 2.
AC32 no change option → E4, exit 2.
AC33 unknown extension frontmatter keys, YAML comments, and quoting styles
on untouched keys survive byte-for-byte.
AC34 target with duplicate frontmatter keys or non-list `derived_from` →
E8.
AC35 unresolvable target → E6; target without id (index.md) or non-synthetic
(raw, governance) → E7.
AC36 malformed scan → E3 naming paths.
AC37 log gains one `revised` row: timestamp `T`, actor, target id, note
starting with the target path.
AC38 no `index.md` content changes in any revise run.
AC39 every pre-flight error leaves the KB byte-for-byte untouched. A
write-phase `E_REVISE_IO` may leave partial state only as documented.
AC40 `--json` success envelope exactly as §5; error envelope carries the
typed code; exit codes as §4.
AC41 combined run (`--add-parent` + `--link` + `--status` + `--body-file` +
`--pending`) applies all changes in one write and one log row.
AC42 `--actor` value appears in the log row; default `kb-cli`.
AC43 a proposed revised document that retains or introduces a document-
integrity error (including schema invalidity or a DG2 cycle) fails
`E_REVISE_VALIDATION`, lists stable finding codes, and writes nothing;
unrelated pre-existing findings elsewhere do not block.
