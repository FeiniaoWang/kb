# Spec: `kb revise`

**Implementation context:** [PRD](../../prd.md) + [00-shared.md](00-shared.md) + this file. Precedence: PRD > this command spec > shared contract.
**Traceability:** PRD CLI-14, §6.6 (instruction-authorized automatic consolidation), DG2 (acyclic provenance), CS3/CS6 (consolidation and propagation), AL1–AL3 (associative links), LS2/LS5 (`timestamp`, `last_human_touch`, and explicit lifecycle transitions). Invoked by `kb-author`, `kb-ingest`, and instruction-authorized maintenance workflows.

## 1. Purpose

Revise one synthetic document in place while preserving its id. This is the sole synthetic-mutation path for consolidation (append parents), body replacement, associative links, explicit lifecycle transitions other than supersession, and `pending_upstream` marker management. Every revision advances `timestamp`; `last_human_touch` advances only when `--human` explicitly marks the revision human-confirmed. The command appends one `revised` log entry and never refreshes `index.md`, because it cannot change the `title` or `description` fields used by index listings.

Revision is not supersession: only `kb create --supersedes` creates a replacement and sets `status: superseded` (LS5).

## 2. CLI surface

```
kb revise REF [--add-parent REF]... [--link TYPE=REF]...
              [--body-file FILE|-] [--status draft|current|retired]
              [--pending REF]... [--clear-pending REF]...
              [--human] [--actor NAME] [--kb PATH] [--json]
```

| Param | Kind | Type | Default | Meaning |
|---|---|---|---|---|
| `REF` | positional | `REF` | — | Synthetic document to revise. Resolved per 00-shared §4.1; this is one target, not a stdin batch |
| `--add-parent` | repeatable option | `REF` | — | Append a parent to `derived_from` (consolidation, CS6). Stored as its canonical id in argument order; DG2 is checked before writing |
| `--link` | repeatable option | `TYPE=REF` | — | Append an associative-link target under `TYPE` (AL1). Stored as a canonical id; undeclared types warn but do not block |
| `--body-file` | option | file path or `-` | unchanged | Replace the body from a file or stdin. Empty/whitespace-only content means an empty body |
| `--status` | option | `draft\|current\|retired` | unchanged | Explicit human-directed lifecycle transition (LS5). Requires `--human`; `superseded` is not accepted |
| `--pending` | repeatable option | `REF` | — | Record a human-directed deferral by adding a `pending_upstream` marker naming a parent whose revision awaits propagation (CS6). Requires `--human` |
| `--clear-pending` | repeatable option | `REF` | — | Remove a `pending_upstream` marker when propagation is performed |
| `--human` | option | flag | off | Mark the revision human-confirmed; advance `last_human_touch` to the revision instant |
| `--actor` | option | text | `kb-cli` | Actor recorded in the log entry (00-shared §8) |
| `--kb` | option | directory path | upward discovery | KB root (00-shared §1) |
| `--json` | option | flag | off | Structured output (§6) |

At least one change option is required: `--add-parent`, `--link`, `--body-file`, `--status`, `--pending`, or `--clear-pending`. `--human`, `--actor`, `--kb`, and `--json` do not constitute changes by themselves.

## 3. Help text (wording normative, layout Typer's)

**Description:**

> Revise a synthetic document in place while preserving its id.
>
> The single synthetic-mutation path for consolidation, associative links, body replacement, explicit draft/current/retired transitions, and pending_upstream marker management. Appended parents are checked for derivation cycles before writing. Every revision advances timestamp; --human additionally advances last_human_touch. Appends a revised entry to log.md and never changes index.md. Supersession is not revision: only kb create --supersedes sets status superseded. Does not touch Git.

**Option help strings:**

| Param | Help string |
|---|---|
| `REF` | Synthetic document to revise (id or KB-relative path). |
| `--add-parent` | Parent to append to derived_from; repeatable. The append must not create a derivation cycle. |
| `--link` | Associative link to append as TYPE=REF; repeatable. |
| `--body-file` | File to replace the body from, or - for stdin. [default: body unchanged] |
| `--status` | Explicit human-directed lifecycle status: draft, current, or retired. Requires --human; superseded is never accepted. |
| `--pending` | Parent id to add to pending_upstream for a human-directed deferral; repeatable. Requires --human. |
| `--clear-pending` | Parent id to remove from pending_upstream; repeatable. |
| `--human` | Mark this revision human-confirmed and advance last_human_touch. |
| `--actor` | Actor recorded in the log entry. [default: kb-cli] |
| `--kb` | KB root. [default: discovered upward from the current directory] |
| `--json` | Emit results as JSON. |

**Examples section:**

```
Examples:
  kb revise KB-000042 --add-parent RAW-000113 --body-file revised.md       Consolidate new evidence
  kb revise KB-000042 --link references=KB-000012                          Add an associative link
  kb revise KB-000042 --status current --human                             Confirm completion
  kb revise KB-000051 --pending KB-000042 --human                          Record human-directed deferred propagation
  kb revise KB-000051 --body-file - --clear-pending KB-000042 --human      Propagate and clear the marker
```

## 4. Behavior (normative algorithm)

The run is **pre-flight, then write**: steps 1–12 complete before the first byte is written. Any failure in those steps leaves the KB byte-for-byte untouched. Only an OS error in the write phase can leave completed earlier effects; no rollback is attempted, matching the other write commands.

**Core preparation:**

1. Resolve the KB root (00-shared §1) and load `kb-config.json`. Fail with the shared `E_NO_KB`, `E_CONFIG_INVALID`, or `E_SCHEMA_UNSUPPORTED` envelope, exit 2.
2. Scan (00-shared §5). If `KB.malformed` is non-empty, fail `E_REVISE_MALFORMED`, exit 2, name the paths, and direct the user to `kb validate`. Although revise allocates no id, it refuses an unsafe partial view before graph or identity mutation.
3. Validate the surface. No change option → `E_REVISE_NO_CHANGES`, exit 2. `--status` or `--pending` without `--human` → `E_REVISE_HUMAN_REQUIRED`, exit 2: lifecycle transitions and propagation deferrals are human-directed decisions, and the CLI requires their confirmation to be explicit rather than guessing it. Split every `--link` token at its first `=`; both `TYPE` and `REF` must be non-empty → `E_REVISE_LINK_INVALID`, exit 2. Unknown options and invalid enum values (including `--status superseded`) are Typer usage errors, exit 2.
4. Resolve target `REF` per 00-shared §4.1. Unresolvable → `E_REVISE_TARGET_UNRESOLVED`, exit 1. The target must carry an id, classify as `SYNTHETIC`, and have live status `draft` or `current`; otherwise → `E_REVISE_TARGET_INVALID`, exit 1. Superseded and retired documents are preserved terminal records (LS4); revise a live successor instead.
5. Confirm the target can be edited losslessly: its frontmatter is a mapping without duplicate top-level keys; `derived_from` is a list of non-empty strings; `links`, when present, is a mapping of non-empty string keys to lists of non-empty strings; `pending_upstream`, when present, is a list of non-empty strings. Failure → `E_REVISE_NOT_EDITABLE`, exit 1, directing to `kb validate`.
6. Resolve each `--add-parent` to a document carrying an id and store the canonical id. Unresolvable/no id → `E_REVISE_PARENT_UNRESOLVED`, exit 1. An id already in `derived_from` or repeated in this invocation → `E_REVISE_PARENT_DUPLICATE`, exit 1. Otherwise append in argument order.
7. Run the DG2 pre-write check for every appended synthetic parent. The graph contains only existing and proposed `derived_from` edges; associative `links` are excluded (AL3). If the target is reachable from an added parent, the append would close a cycle → `E_REVISE_CYCLE`, exit 1, with the cycle path in the message.
8. Resolve each `--link` reference to a document carrying an id. Unresolvable/no id → `E_REVISE_LINK_UNRESOLVED`, exit 1. A target already present under that type or repeated for that type in this invocation → `E_REVISE_LINK_DUPLICATE`, exit 1. Append targets in argument order; append a new type key after existing type keys. A `TYPE` absent from config `link_types` emits one stderr warning per undeclared type—`link type '<type>' is not declared in the kb-config.json link_types vocabulary`—but proceeds; an empty vocabulary means none are declared.
9. Resolve each `--pending` and `--clear-pending` reference to a canonical id. Unresolvable/no id → `E_REVISE_PENDING_UNRESOLVED`, exit 1. Fail `E_REVISE_PENDING_INVALID`, exit 1, if an id appears in both add and clear sets; a pending id is absent from the final `derived_from` list; a pending id is already marked or repeated; or a clear id is not currently marked. Append markers in argument order. If the final list is empty, remove the `pending_upstream` key rather than emitting an empty list.
**CLI-adapter acquisition:**

10. Acquire body bytes through the CLI body adapter (§4.1). Omitted `--body-file` produces `None`; a file path must name a readable regular file or fails `E_REVISE_BODY_NOT_FOUND`, exit 2; `-` reads stdin to EOF. The adapter performs no decoding, normalization, or writes.

**Core execution:**

11. With supplied bytes, strict UTF-8 decode or fail `E_REVISE_BODY_NOT_TEXT`, exit 1; normalize CRLF and lone CR to LF and end non-empty content with exactly one newline. Empty/whitespace-only input yields the empty body; `None` preserves the existing body byte-for-byte. Compute revision instant `T` as UTC seconds (`YYYY-MM-DDTHH:MM:SSZ`). Set `timestamp: T` on every revision. Set `last_human_touch: T` only with `--human`; otherwise preserve it. Apply only requested `derived_from`, `links`, `pending_upstream`, `status`, and body changes. Untouched frontmatter keys—including unknown FM2 extension keys—retain their order, YAML style, comments, and bytes. A newly introduced key appends at the end of the frontmatter mapping.
12. Validate the complete proposed target state with the same document-integrity rules as `kb validate`, including all existing and proposed references and graph effects. Any error finding anchored to the proposed target (or introduced by its new graph edges) → `E_REVISE_VALIDATION`, exit 1, listing the finding codes; unrelated pre-existing findings elsewhere do not block. Warnings do not block and are reported once (deduplicated against step 8). Then format and strict-UTF-8 encode one log row before mutation: action `revised`, actor from `--actor`, ids = target id, note = target path followed by a deterministic change summary in option-family order (`+parent`, `+link`, `status`, `body`, `+pending`, `-pending`). Preparation/I/O failure → `E_REVISE_IO`, exit 2.

**Write phase:**

13. Replace the target document through the identity-checked, symlink-resistant write seam. The id and path never change. No `index.md` is read or written.
14. Append the prepared log bytes. If `log.md` is missing, recreate the kb-init §5.3 operational scaffold without an `initialized` line, then append. Report per §6 and exit 0.

No step runs `git`, inspects Git state, modifies another document, changes `title`/`description`/`tags`/`instructions`, or sets `status: superseded`.

### 4.1 Body adapter (internal contract)

Concrete body acquisition lives at the CLI seam (00-shared §5.1). Binding the
selection performs no I/O. After core preparation succeeds, the callback
acquires optional bytes and passes them explicitly to core execution:

```python
class BoundReviseBody:
    @property
    def source_kind(self) -> Literal["none", "file", "stdin"]: ...

    def acquire(self) -> bytes | None: ...
```

The core never opens the external file or reads process-global stdin. Strict
UTF-8 decoding, normalization, validation, and persistence remain core behavior.

## 5. Filesystem effects

Given `KB-000042` with parents `[CHAT-000027]`, no associative links, `status: draft`, and `last_human_touch: 2026-07-20T09:00:00Z`, this instruction-authorized revision:

```
kb revise KB-000042 --add-parent RAW-000113 \
  --link references=KB-000012 --body-file revised.md
```

changes only the target and `log.md`. The relevant frontmatter becomes:

```yaml
derived_from:
  - CHAT-000027
  - RAW-000113
timestamp: 2026-07-22T10:00:00Z
last_human_touch: 2026-07-20T09:00:00Z
links:
  references:
    - KB-000012
```

`id`, status, untouched keys, and their bytes are preserved. Adding `--human` makes `last_human_touch` equal the new `timestamp`. A marker-only revision appends or removes `pending_upstream`; clearing the final marker removes that key. No index listing changes because the command cannot change listing fields.

The log line for the example is:

```
- 2026-07-22T10:00:00Z | revised | kb-cli | KB-000042 | synthetic/specs/retry-policy.md +parent RAW-000113, +link references=KB-000012, body
```

## 6. Output

**Text (stdout):**

```
updated  synthetic/specs/retry-policy.md
revised KB-000042 as synthetic/specs/retry-policy.md
```

Warnings go to stderr. The `log.md` append is implicit and not listed.

**JSON (`--json`):**

```json
{
  "ok": true,
  "id": "KB-000042",
  "path": "synthetic/specs/retry-policy.md",
  "updated": ["synthetic/specs/retry-policy.md"],
  "warnings": []
}
```

`warnings` contains stable validation-warning strings in first-occurrence order (including undeclared link types), deduplicated. Errors use the shared envelope `{"error": {"code": "E_...", "message": "..."}}`.

## 7. Errors and edge cases

| # | Condition | Behavior | Exit |
|---|---|---|---|
| E1 | No KB root | `E_NO_KB` | 2 |
| E2 | Config invalid or schema unsupported | `E_CONFIG_INVALID` / `E_SCHEMA_UNSUPPORTED` | 2 |
| E3 | Malformed documents in scan | `E_REVISE_MALFORMED` naming paths | 2 |
| E4 | No change option | `E_REVISE_NO_CHANGES` | 2 |
| E5 | Malformed `--link` token | `E_REVISE_LINK_INVALID` | 2 |
| E6 | Target unresolvable | `E_REVISE_TARGET_UNRESOLVED` | 1 |
| E7 | Target has no id, is not synthetic, or lacks live `draft`/`current` status (`superseded`, `retired`, missing, or invalid) | `E_REVISE_TARGET_INVALID` | 1 |
| E8 | Target frontmatter is not losslessly editable | `E_REVISE_NOT_EDITABLE` | 1 |
| E9 | Parent unresolvable or has no id | `E_REVISE_PARENT_UNRESOLVED` | 1 |
| E10 | Parent already present or repeated | `E_REVISE_PARENT_DUPLICATE` | 1 |
| E11 | Parent append would close a derivation cycle | `E_REVISE_CYCLE` with cycle path | 1 |
| E12 | Associative-link target unresolvable or has no id | `E_REVISE_LINK_UNRESOLVED` | 1 |
| E13 | Associative-link target duplicated within its type | `E_REVISE_LINK_DUPLICATE` | 1 |
| E14 | Pending/clear ref unresolvable or has no id | `E_REVISE_PENDING_UNRESOLVED` | 1 |
| E15 | Pending add/clear conflict, marker not a parent, duplicate/already marked add, or absent clear | `E_REVISE_PENDING_INVALID` | 1 |
| E16 | Body path missing, unreadable, or not regular | `E_REVISE_BODY_NOT_FOUND` | 2 |
| E17 | Body bytes not UTF-8 | `E_REVISE_BODY_NOT_TEXT` | 1 |
| E18 | Complete proposed target fails document-integrity validation | `E_REVISE_VALIDATION` listing stable finding codes | 1 |
| E19 | Context, preparation, or write I/O failure | `E_REVISE_IO`; pre-flight leaves the KB untouched, write-phase failure may leave the target changed before log append | 2 |
| E20 | Undeclared associative-link type | one warning naming the type; revision proceeds. Empty `link_types` means every type warns | 0 |
| E21 | Unknown option or bad enum (including `--status superseded`) | Typer usage error | 2 |
| E22 | `log.md` missing | recreate operational scaffold, then append the revision | 0 |
| E23 | `--status` or `--pending` supplied without `--human` | `E_REVISE_HUMAN_REQUIRED`; lifecycle transitions and deferral decisions require explicit human confirmation | 2 |

Every E1–E18/E21/E23 failure is pre-flight and leaves the KB byte-for-byte untouched.

## 8. Acceptance criteria

One pytest test per item (00-shared §10), named `test_ac<NN>_<slug>`. Timestamps are pattern-matched; byte preservation is asserted exactly.

**Coverage map:** target/id/timestamps AC1–AC3 · parents and DG2 AC4–AC10 · associative links AC11–AC18 · lifecycle AC19–AC21/AC48 · pending markers AC22–AC26/AC48 · body AC27–AC31 · surface/schema/atomicity AC32–AC36/AC39/AC45–AC47 · log/index/output AC37–AC42 · help and Git-agnosticism AC43–AC44.

| # | Given / When / Then |
|---|---|
| AC1 | Given a valid synthetic target, `--add-parent` appends the canonical id, preserves the target id and path, advances `timestamp`, and leaves `last_human_touch` unchanged without `--human`. |
| AC2 | Given the same revision with `--human`, `last_human_touch` advances to the exact new `timestamp`. |
| AC3 | Target id and path refs resolve to the same document and produce the same revision. |
| AC4 | A parent supplied by path is stored as its canonical id. |
| AC5 | Repeating one `--add-parent` ref fails `E_REVISE_PARENT_DUPLICATE`, with nothing written. |
| AC6 | Adding a parent already present fails `E_REVISE_PARENT_DUPLICATE`. |
| AC7 | An unresolvable/id-less parent fails `E_REVISE_PARENT_UNRESOLVED`. |
| AC8 | Adding the target's descendant as a parent, closing a direct derivation cycle, fails `E_REVISE_CYCLE` and names the cycle. |
| AC9 | A transitive cycle across three or more synthetic documents likewise fails `E_REVISE_CYCLE`. |
| AC10 | Raw and governance parents append successfully and do not create graph edges of their own. |
| AC11 | `--link references=KB-…` creates `links` when absent with the requested type and canonical target. |
| AC12 | A link appends to an existing type's list after prior targets. |
| AC13 | Link options for different types preserve type first-occurrence order and target argument order. |
| AC14 | A target already linked under that type, or repeated for that type in the invocation, fails `E_REVISE_LINK_DUPLICATE`. The same target under a different type is legal. |
| AC15 | Malformed `--link` tokens (`references`, `=KB-…`, `references=`) fail `E_REVISE_LINK_INVALID`, exit 2. |
| AC16 | An unresolvable/id-less link ref fails `E_REVISE_LINK_UNRESOLVED`. |
| AC17 | An undeclared link type proceeds with exactly one warning; a declared type emits none. |
| AC18 | With `link_types: []`, every distinct used link type warns. Associative-link cycles are legal and never trigger `E_REVISE_CYCLE`. |
| AC19 | With `--human`, `--status draft`, `current`, and `retired` each write the explicit value and advance both `timestamp` and `last_human_touch`; `superseded` is rejected as a usage error. |
| AC20 | A target with `status: superseded` or `retired` fails `E_REVISE_TARGET_INVALID`; terminal documents are preserved. |
| AC21 | Explicitly setting the current status to its existing value with `--human` is legal and still records a human-confirmed revision. |
| AC22 | `--pending P --human` where P is a parent creates/appends `pending_upstream` in argument order and advances `last_human_touch` with `timestamp`. |
| AC23 | A pending id absent from final parents fails `E_REVISE_PENDING_INVALID`; adding that parent in the same invocation succeeds. |
| AC24 | An already marked or repeated pending id fails `E_REVISE_PENDING_INVALID`; an unresolvable/id-less ref fails `E_REVISE_PENDING_UNRESOLVED`. |
| AC25 | `--clear-pending` removes the named marker; clearing the last marker removes the key. |
| AC26 | Clearing an absent marker, or adding and clearing the same id in one invocation, fails `E_REVISE_PENDING_INVALID`. |
| AC27 | `--body-file FILE` replaces the body while preserving untouched frontmatter bytes. |
| AC28 | `--body-file -` reads stdin, normalizes CRLF/lone CR, and produces exactly one trailing newline. |
| AC29 | Empty/whitespace body input produces the empty body ending at the frontmatter delimiter. |
| AC30 | Without `--body-file`, the body is byte-identical. |
| AC31 | Non-UTF-8 body bytes fail `E_REVISE_BODY_NOT_TEXT`, exit 1; a missing/non-regular body path fails `E_REVISE_BODY_NOT_FOUND`, exit 2. |
| AC32 | No change option fails `E_REVISE_NO_CHANGES`, exit 2; `--human` or `--actor` alone still counts as no change. |
| AC33 | Unknown extension keys, untouched YAML comments, key order, quoting, and scalar styles survive byte-for-byte. |
| AC34 | Duplicate top-level keys or malformed editable fields fail `E_REVISE_NOT_EDITABLE`, directing to `kb validate`. |
| AC35 | An unresolvable target fails `E_REVISE_TARGET_UNRESOLVED`; raw, governance, index, id-less, missing-status, or invalid-status targets fail `E_REVISE_TARGET_INVALID`. |
| AC36 | A scan containing unparseable frontmatter or an absent/empty/non-string `type` fails `E_REVISE_MALFORMED`, names paths, and writes nothing. |
| AC37 | A successful run appends exactly one `revised` log row with timestamp, actor, target id, path, and deterministic change summary. |
| AC38 | No `index.md` file changes in any revision. |
| AC39 | Every pre-flight error leaves every KB file byte-identical. A write-phase I/O failure returns `E_REVISE_IO`; partial state is permitted only as documented. |
| AC40 | JSON success contains exactly `ok`, `id`, `path`, `updated`, and `warnings`; typed failures use the shared error envelope and §7 exit code. |
| AC41 | A combined parent/link/status/body/pending revision applies all requested changes in one target write and one log row. |
| AC42 | `--actor` appears in the log (default `kb-cli`); a missing `log.md` is recreated as operational `type: log` with exactly the new revision entry. |
| AC43 | `kb revise --help` exits 0 and contains every normative description sentence, option help string, and example from §3. |
| AC44 | No successful or failing revision invokes `git`, creates `.git/`, or inspects Git state. |
| AC45 | Running outside a KB returns `E_NO_KB`; malformed JSON returns `E_CONFIG_INVALID`; a newer schema returns `E_SCHEMA_UNSUPPORTED`; each exits 2 and writes nothing. |
| AC46 | An unknown option or invalid `--status` value exits 2 with a Typer usage error and writes nothing. |
| AC47 | If the complete proposed target would retain or introduce an error finding (for example missing DG5 session parentage, an unresolved existing link, duplicate id, or invalid supersession coupling), the run fails `E_REVISE_VALIDATION` listing the finding codes and writes nothing; an unrelated finding on another document does not block. |
| AC48 | `--status` without `--human` and `--pending` without `--human` each fail `E_REVISE_HUMAN_REQUIRED`, exit 2, and write nothing; the same operations with `--human` proceed when otherwise valid. `--clear-pending` does not require `--human`, because propagation may be instruction-authorized and then advances `timestamp` only. |

## 9. Out of scope

- Synthetic birth and genuine replacement/rescoping (`kb create`, with `--supersedes` for the latter).
- Raw-document mutation: raw evidence is immutable.
- Changes to `title`, `description`, `tags`, or `instructions`; the v1 CLI-14 surface does not expose them.
- Propagation planning or deciding which content should change. Skills use `kb links --reverse --transitive`, respect `instructions`, ask the human where judgment is needed, and then invoke this deterministic write path.
- Index regeneration: no listing field can change.
- Any direct modification of another document. A child receives its own revision when marked or propagated.
- All Git operations.
