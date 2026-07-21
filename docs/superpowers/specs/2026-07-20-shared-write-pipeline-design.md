# Shared Create/Ingest Write Pipeline Design

**Date:** 2026-07-20

**Status:** Approved

## Human-Approved Containment Amendment

This amendment supersedes every path-based safe-I/O snippet below where the
snippet conflicts with containment. Filesystem persistence is anchored to the
KB root selected during preparation: the implementation captures that root's
identity without retaining an open descriptor, reopens and verifies the root
for each later operation, traverses every relative directory component with
no-follow directory descriptors, and holds the verified parent descriptor
through the final `mkdir`, create, inspect, read, overwrite, or append syscall.
Final components are also no-follow. A platform that cannot provide the
required stdlib descriptor-relative and no-follow operations fails safely with
an `OSError` before mutation instead of falling back to an unanchored path.
All descriptors close on success and failure; abandoned preparations retain no
live filesystem handles.

Preparation rejects collisions between explicit birth, companion, or mutation
paths and implicit pipeline paths: every born `index.md`, the affected existing
`index.md`, and root `log.md`. These knowable conflicts are programmer misuse
reported as `ValueError` before any write, including a document birth at a
would-be born `index.md`.

After a preparation is consumed, environmental or late-link failures at a
companion or document path are neutral write failures, not raw path-validation
errors: `phase="write"`, `operation="create"`, the exact role (`companion` or
`document`), and the normalized root-relative path. Directory, index, mutation,
and log failures retain their respective `mkdir`/`create`/`overwrite`/`append`
operation and role attribution. The fixed partial-write order and no-rollback
contract remain unchanged.

### Root-bound context acquisition

The same containment guarantee applies before preparation. A short-lived,
internal rooted snapshot session opens the discovered KB root with no-follow
directory semantics and captures its `FileIdentity` before any config or scan
input is consumed. Configuration bytes, directory traversal, and every
Markdown file read used for allocation are performed relative to descriptors
descending from that captured root. Each directory component and final file is
opened no-follow and checked for the required kind. The root pathname is
reopened and matched against the captured identity throughout acquisition and
once more before the snapshot is returned. A platform that cannot provide
these operations fails before mutation; there is no path-based fallback.

The rooted session remains an internal seam rather than a public filesystem
adapter. It returns owned bytes and root-relative metadata, then closes every
descriptor on success and failure. Existing config and frontmatter parsers are
refactored to accept those bytes, and the ordinary path-based loaders delegate
to the same parsers; the pipeline does not create a second schema or parser.
For Markdown, the owned bytes are only the incrementally acquired frontmatter
prefix: acquisition reads through the closing `---` delimiter and stops. A
valid document body is neither read nor retained by the scan or by
`WriteContext`; `Document.body` remains a lazy path read under the normative
`00-shared.md` contract. A malformed document may be read to EOF when that is
necessary to prove that no closing delimiter exists. Both the ordinary
path-based scan and the rooted scan use the same frontmatter-prefix reader and
the same byte parser, so ordering, YAML behavior, and malformed diagnostics do
not diverge. The scan is still rebuilt once per invocation and is not
persisted or cached.

Full identity-checked bytes are acquired only later, during `prepare_write()`,
for a mutation source that actually needs a lossless transformation (currently
the supersession target). Those bytes live in `PreparedWrite.sources`; the
allocation snapshot never retains them.

`WriteContext` remains a Pydantic model and privately stores the captured root
identity. It stores no descriptor. `prepare_write()` reopens the root before
using the context and rejects an identity mismatch as a neutral typed preflight
failure. Consequently a root replaced between staged public calls cannot
receive ids or reference intent derived from the previously scanned KB. A
rename-away-and-back during acquisition cannot introduce bytes from the
temporary pathname: all acquisition remains anchored to the original root
descriptor, and any observable root-identity mismatch fails the acquisition.

### Rooted projected-index snapshot

Projected index preparation collects the affected directory's complete
listing input through the same descriptor discipline: verified directory
descriptors enumerate child names and kinds, subdirectory `index.md` files and
Markdown children are opened no-follow, and their bytes are parsed through the
existing frontmatter parser. Symlinks, junctions, unexpected child kinds, and
root identity changes are refused before rendering. The collected metadata
contains every existing subdirectory listing field (name, heading, and
description) and Markdown file listing field (filename, id, title,
description, and type), so later formatting needs no pathname access.

Index formatting is pure over the identity-checked index source bytes, this
complete existing-listing metadata, and the planned file/subdirectory
overlays. The pipeline path does not call `Path.iterdir`, `Path.glob`,
path-based `read_frontmatter`, or path-based heading reads. Existing
non-pipeline callers may keep their path-acquiring convenience entry point,
but it delegates to the same pure renderer after collecting equivalent
metadata. Successful listing grammar, filename-key ordering, born-current
indexes, and nearest-existing-index behavior remain byte-for-byte unchanged.

No live descriptor crosses `load_write_context()`, `prepare_write()`, or
`apply_write()`. Each stage independently opens, verifies, uses, and closes
the descriptors it needs while carrying only immutable identities, bytes, and
typed metadata between stages.

### Born-directory identity binding

`create_rooted_directory()` creates a high-entropy private staging directory
under the verified immediate parent, opens and holds that staging directory,
and captures its identity before publication. It then publishes the held
directory to the final name with a kernel atomic no-replace primitive
(`renameatx_np(..., RENAME_EXCL)` on Darwin or
`renameat2(..., RENAME_NOREPLACE)` on Linux), verifies that the final entry is
the held identity, and only then returns it. Ordinary rename is forbidden
because it may overwrite an empty late occupant. A platform without a reliable
descriptor-relative atomic no-replace publication primitive fails safely; a
failed publication preserves the late occupant. It never path-deletes the
staging name after a separate identity check: no portable directory removal
primitive binds deletion to the held descriptor, so `stat` followed by
`rmdir` would recreate the same replacement race.

Consequently a failed operation after staging creation may leave a randomized
`.kb-born-<high-entropy>` directory as documented no-rollback partial state.
The prefix identifies it for operational inspection; it is not excluded from
normal KB traversal or granted a hidden namespace. An owned empty staging
directory can therefore make the directory invariant fail (`kb index --check`
reports the missing `index.md`) until a steward, after confirming no concurrent
write owns it and inspecting its contents/identity, deliberately removes or
repairs it. Successful exclusive publication renames the staging entry away and
leaves no staging pathname.

During `apply_write()`, every returned born directory identity is retained as
immutable local state and is required as the expected immediate-parent
identity for its own `index.md`, the next child directory, and every companion
or citable document born beneath it. A replacement installed before, during,
or after publication is therefore never trusted for a later pipeline write.
Every born directory is identity-verified again before success is returned.

Only identities cross individual rooted operations. Parent and staging
descriptors remain operation-local and are closed before the next pipeline
effect, including on success, publication failure, and verification failure.
A born-directory identity mismatch is a typed write-phase
`WriteFailure`; prior published effects remain as documented because the
pipeline does not roll back.

### Command-contract reconciliation

Command policy reserves every target directory's CLI-maintained `index.md`
pathname during collision naming, regardless of whether the index exists,
would be born, or is missing from a damaged existing directory. The latter
case therefore selects the deterministic suffixed document name before
pipeline preparation reports the missing required index as a typed preflight
I/O failure; command-owned naming never submits a document birth at
`index.md`, while the pipeline retains its `ValueError` as a programmer-misuse
guard.

Ingest destination preflight rejects every existing symlink or junction
component from the raw-class directory through the requested destination,
including links whose resolved targets remain within that class directory.
This user-facing check runs before external acquisition and maps exactly to
`E_INGEST_DEST_INVALID`; the shared pipeline's later no-follow validation
remains defense in depth.

The rooted context scan remains earlier than surface and destination
validation. When that existing scan fails at an unsafe path, ingest may map it
to `E_INGEST_DEST_INVALID` only when the path exactly equals a member of the
lexical root-relative component chain from the selected raw-class directory
through the requested destination. Destination parsing on this exception path
is comparison-only and non-raising; invalid syntax proves no match. No adapter
or independent earlier filesystem traversal is added. Context failures not
proven to come from that chain remain generic/config/malformed according to
the existing validation order.

Context-acquisition failures receive supersession-specific classification
only with exact target provenance. A path reference may be compared with the
unsafe root-relative path; an id reference requires a safely parsed document
that binds that id to the unsafe path. An unresolved id plus an unrelated
unsafe Markdown path maps to generic create I/O. The command never infers
target provenance merely from `ELOOP` or from failure to resolve a reference.

Create and ingest may persist KB bytes only through the public shared
write-pipeline interface. A semantic AST architecture gate rejects direct
mutating `Path`, built-in file, `os`, and `shutil` APIs, including aliases and
dynamic open modes that cannot be proven read-only. Until the separate input
seam lands, current external source/body acquisition remains legal only
through provably read-only operations; clipboard subprocess acquisition is
also unchanged.

## Goal

Extract the duplicated create/ingest filesystem commit orchestration into one deep core module while preserving every observable `kb create` and `kb ingest` contract. The extraction also strengthens ingest's mutable index and log handling to match create's identity-checked safety without adding rollback or changing documented partial-write semantics.

This is the prerequisite named by `AGENTS.md` and by `docs/superpowers/plans/2026-07-20-cli-core-input-seam.md`. The later CLI/core input seam must consume this module rather than recreate command-specific write, index, or log flows.

## Scope

The design covers:

- shared root/config/scan setup for allocating writes;
- the malformed-document allocation guard;
- exclusive creation of citable documents and companion files;
- creation of missing directories and born-current `index.md` files;
- regeneration of only the nearest pre-existing affected index;
- identity-checked preparation and replacement of mutable documents;
- identity-checked append or exclusive recreation of `log.md`;
- fixed write ordering and documented partial-state behavior;
- deterministic `created` and `updated` path accounting; and
- moving the shared pure `slug()` helper out of `ingest.py`.

The design changes KB context acquisition only as described above: root-bound
config acquisition plus lazy Markdown frontmatter-prefix scans. It does not
move external file, stdin, clipboard, or create-body acquisition; that work
remains in the separately approved CLI/core input-seam plan. It does not
define `kb revise`, introduce rollback, add a transaction abstraction, or
change the PRD. Command behavior changes only through the explicit
command-contract reconciliation above; all other command behavior remains
unchanged.

## Design Vocabulary and Dependency Classification

The new write pipeline is a **module** whose **interface** is the typed transition from command-prepared write intent to checked filesystem effects. Its **seam** sits after create/ingest domain policy and before KB filesystem mutation.

The filesystem dependencies are local-substitutable: production uses the real local filesystem, and tests exercise the same semantics in `tmp_path`. Inode identity, symlink behavior, `O_EXCL`, permissions, and partial writes are material behavior, so there is no public filesystem port or **adapter**. `safeio.py`, `indexing.py`, and `housekeeping.py` remain internal seams inside the implementation.

The module is deep because callers describe one domain write while the implementation hides directory/index maintenance, identity capture, safe I/O, log behavior, ordering, race detection, and result accounting. Deleting it would force that complexity back into `create.py`, `ingest.py`, and eventually `revise`.

## Alternatives Considered

### Minimal callback plan

A two-entry-point design could accept caller-provided byte-edit callbacks and perform preparation and commit in one call. Its type surface is small, but command-specific lossless transformation errors would execute inside the shared implementation. That weakens locality for error mapping and makes the pipeline responsible for callbacks it does not own.

Rejected in favor of a staged interface that returns identity-checked mutation source bytes before the write boundary.

### Command-shaped create/ingest functions

Separate `prepare_create_write`/`commit_create_write` and `prepare_ingest_write`/`commit_ingest_write` functions make each caller simple. They also duplicate the external interface and pull destination, source-shape, supersession, and raw-class policy into the persistence module.

Rejected because it couples the persistence seam to the later CLI/core acquisition seam and reduces reuse.

### Generic filesystem operation list

An operation list or fluent builder could expose `mkdir`, create, replace, refresh-index, and append-log steps. That is a shallow module: callers would still need to know the ordering and safety rules being extracted, and invalid intermediate states would remain representable.

Rejected. The chosen interface exposes typed domain intent, not filesystem instructions.

## File Responsibilities

### `src/kb/core/write_pipeline.py`

Owns the public write-pipeline interface and its implementation:

- loading the allocating-write context;
- validating intent paths and coherence;
- preparing mutable sources and identities without writes;
- planning missing directories and indexes;
- applying the fixed write sequence;
- reporting neutral write failures; and
- returning deterministic effects.

### `src/kb/core/naming.py`

Owns the pure shared `slug(value, fallback)` helper, moved without behavior changes from `ingest.py`.

### `src/kb/core/create.py`

Retains create policy:

- destination grammar and containment;
- warnings;
- body normalization until the CLI/core seam is implemented;
- parent and supersession eligibility resolution;
- id allocation and collision naming;
- frontmatter/body rendering;
- lossless supersession transformation;
- create-specific failures and result construction.

It consumes the shared write pipeline and no longer owns directory birth, index regeneration, direct safe writes, log append, or effects accounting.

### `src/kb/core/ingest.py`

Retains ingest policy:

- raw-class destination grammar and containment;
- acquisition and normalization until the CLI/core seam is implemented;
- `about` resolution;
- id allocation, title/origin derivation, collision naming, and binary classification;
- raw frontmatter/stub rendering;
- ingest-specific failures and result construction.

It consumes the shared write pipeline and no longer owns directory birth, index regeneration, direct safe writes, log append, or effects accounting.

### `src/kb/core/indexing.py`

Retains index formatting. It gains only the pure implementation support needed to render a projected post-write tree before mutation. That support is not exposed through the write pipeline's public interface.

### `tests/core/test_write_pipeline.py`

Tests behavior through the write pipeline's interface using real temporary filesystems.

### Existing command tests

`tests/cli/test_create.py` and `tests/cli/test_ingest.py` remain the normative end-to-end contract tests. Tests that specifically monkeypatch command-private orchestration should move to the pipeline interface where appropriate; acceptance tests and command error/output regressions remain.

## Stable Interface

All public data models are Pydantic 2.x `BaseModel`s.

```python
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field

from kb.core.housekeeping import LogEntry
from kb.core.model import Config
from kb.core.scan import KB


class WriteContext(BaseModel):
    root: Path
    config: Config
    kb: KB


class CompanionBirth(BaseModel):
    path: Path
    content: bytes


class DocumentBirth(BaseModel):
    path: Path
    content: bytes
    companions_before: list[CompanionBirth] = Field(default_factory=list)


class MutationTarget(BaseModel):
    key: str
    path: Path


class WriteIntent(BaseModel):
    birth: DocumentBirth
    mutations: list[MutationTarget] = Field(default_factory=list)
    log_entry: LogEntry


class MutationSource(BaseModel):
    key: str
    path: Path
    content: bytes


class PreparedWrite(BaseModel):
    sources: dict[str, MutationSource]


class WriteReceipt(BaseModel):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)


def load_write_context(kb_root: Path | None) -> WriteContext: ...


def prepare_write(
    context: WriteContext,
    intent: WriteIntent,
) -> PreparedWrite: ...


def apply_write(
    prepared: PreparedWrite,
    replacements: Mapping[str, bytes] | None = None,
) -> WriteReceipt: ...
```

`PreparedWrite` exposes only identity-checked mutation source bytes. Filesystem identities, index bytes, log identity, normalized paths, missing-directory plans, the original intent, and the one-shot state are private implementation data. `apply_write()` uses `None` rather than a mutable mapping default.

The exact complete log row, including its trailing LF, is also private
prepared state. `prepare_write()` formats the `LogEntry` and strict UTF-8
encodes it once. `apply_write()` can only consume those prepared bytes; the
public model and function interfaces do not grow.

The current scope always has one citable document birth. Mutation-only revision writes are not added until the `kb revise` specification requires them.

## Interface Invariants

### Context

`load_write_context()`:

- discovers the root;
- captures the root identity and loads config descriptor-relatively;
- scans exactly once, descriptor-relatively, reading only each Markdown
  frontmatter prefix through its closing delimiter;
- retains no document body or complete Markdown source bytes;
- blocks id allocation when `kb.malformed` is non-empty;
- performs no writes; and
- preserves the underlying shared root/config failures for callers to translate.

Malformed allocation raises a neutral `AllocationBlocked` exception carrying deterministically sorted root-relative paths. `create.py` maps it to `E_CREATE_MALFORMED`; `ingest.py` maps it to `E_INGEST_MALFORMED` with their existing messages and exit code `2`.

### Paths and intent coherence

Every path in an intent is a normalized KB-root-relative POSIX path. Before any filesystem mutation, `prepare_write()` rejects programmer misuse with `ValueError` when:

- a path is absolute, empty, contains `.` or `..`, uses backslashes, or escapes the resolved KB root;
- birth, companion, or mutation paths overlap;
- companion paths are not siblings of the citable document;
- a companion path ends in `.md` and would enter the Markdown scan/index surface;
- mutation keys or paths are duplicated;
- the citable document is not Markdown;
- a destination component is a symlink or junction; or
- planned directory/file shapes conflict.

Existing command destination validation remains the user-facing source of destination errors. Ingest rejects all existing destination symlink/junction components before external acquisition, even when a link stays within the raw-class directory. Pipeline `ValueError`s indicate an internal caller defect rather than a second user-facing validation vocabulary.

### Preparation

`prepare_write()` performs all fallible checks and rendering possible before the first write:

1. validate intent structure and root containment;
2. determine missing directories between the nearest existing ancestor and the citable document's parent;
3. identify the nearest pre-existing affected `index.md`;
4. capture identities for mutation targets, the affected existing index, and `log.md` when present;
5. read every mutation source through its captured identity;
6. derive the new document's index listing from its rendered Markdown bytes;
7. pre-render every born-current index and the affected existing index against the projected post-write tree; and
8. format and strict UTF-8 encode the complete log row; and
9. prepare exact sorted effect paths.

Log formatting or encoding failure is wrapped as `WriteFailure` with
`phase="preflight"`, `operation="render"`, `role="log"`, `path=Path("log.md")`,
and a stable `OSError` cause (`EINVAL` for a formatting failure and `EILSEQ`
for an encoding failure). No expected formatter `TypeError`/`ValueError` or
raw `UnicodeEncodeError` crosses the pipeline interface, and the KB remains
byte-identical.

It performs no writes. Any preparation failure leaves the KB byte-identical.

### Command-specific mutation transformation

After preparation, create reads `prepared.sources["superseded"].content` and performs its lossless frontmatter transformation. A semantic `ValueError` remains outside the shared implementation and maps to `E_CREATE_SUPERSEDES_INVALID` before any write.

`apply_write()` requires replacement keys to match the prepared mutation keys exactly. Missing keys, extra keys, duplicate intent keys, or replay of a consumed preparation raise `ValueError` before an additional write.

### Application order

`apply_write()` owns this fixed order:

1. create missing directories root-to-leaf, capture each born identity, and
   exclusively create each born-current `index.md` against its captured parent;
2. exclusively create companions in declared order;
3. exclusively create the citable Markdown document;
4. identity-check and overwrite mutations in declared order;
5. identity-check and overwrite only the nearest pre-existing affected index; and
6. identity-check and append the privately prepared bytes to `log.md`, or
   exclusively create its scaffold plus those bytes, last.

Application does not call the log formatter and performs no text encoding.

Create supplies no companions. Binary ingest supplies its byte-identical original as the first companion, making original-before-stub structural. Text ingest supplies no companions.

The pipeline does not roll back. A write-phase OS failure may leave effects
from completed earlier steps. This preserves `kb create` AC46 and `kb ingest`
AC44. Late occupants are never truncated, and changed mutable identities,
symlinks, or junctions are never followed. Every child directory, born index,
companion, and document under a born directory requires that directory's
captured identity, and all born directory identities are verified once more
before the receipt is returned.

### Effects

On success, `WriteReceipt` contains alphabetically sorted, root-relative POSIX paths:

- `created`: companions, citable document, and new `index.md` files;
- `updated`: mutation targets and the nearest pre-existing affected index.

`log.md` is excluded from both lists, preserving current command JSON/text results.

## Error Model

The module defines neutral exceptions rather than command failures:

```python
WritePhase = Literal["preflight", "write"]
WriteOperation = Literal[
    "inspect",
    "read",
    "render",
    "mkdir",
    "create",
    "overwrite",
    "append",
]
WriteRole = Literal[
    "directory",
    "companion",
    "document",
    "mutation",
    "index",
    "log",
]


class AllocationBlocked(Exception):
    paths: tuple[Path, ...]


class WriteFailure(Exception):
    phase: WritePhase
    operation: WriteOperation
    role: WriteRole
    path: Path
    cause: OSError
    key: str | None
```

Command modules retain all stable codes, messages, and exit codes:

- shared root/config errors map exactly as they do today;
- `AllocationBlocked` maps to the command's malformed-allocation error;
- create preflight `operation="inspect"` failure for mutation key `superseded` maps to the existing `E_CREATE_SUPERSEDES_INVALID`, exit `1` message;
- a context-acquisition scan failure maps to that supersession-specific error only when the unsafe path is proven to be the requested target (path equality for a path reference, or a safely parsed id-to-path match); without that proof it remains `E_CREATE_IO`, exit `2`;
- an ingest context-acquisition scan failure maps to
  `E_INGEST_DEST_INVALID`, exit `2`, only when the unsafe path exactly matches
  a lexical requested class/destination component; without that proof it
  remains `E_INGEST_IO`, exit `2`;
- create preflight `operation="read"` failure for that mutation remains `E_CREATE_IO`, exit `2`;
- preflight `operation="render"`, `role="log"` failure maps to the caller's
  stable generic I/O envelope (`E_CREATE_IO` or `E_INGEST_IO`), exit `2`;
- other create pipeline failures map to `E_CREATE_IO`, exit `2`;
- ingest pipeline failures map to `E_INGEST_IO`, exit `2`; and
- semantic lossless-transformation errors remain command-owned and pre-write.

The underlying OS message remains available through `cause`, so current non-empty error details are preserved.

## Projected Index Rendering

Successful writes must create every new directory with a current index and refresh only the nearest pre-existing ancestor. Preparation therefore renders indexes against a projected post-write tree rather than requiring callers to construct index contents.

The projection contains:

- the existing directory tree;
- each planned missing directory and its `index.md` metadata;
- the planned citable Markdown document; and
- no companion files in Markdown listings, including `.md.original` evidence.

The implementation derives the new document's id, title, and optional description from its already-rendered Markdown frontmatter. Invalid rendered bytes are a programmer error before writes. Existing entries continue to use the current index reader and deterministic sort rules.

This keeps listing coherence behind the seam: callers cannot provide document bytes and contradictory index metadata.

## Caller Flows

### Create

```python
context = load_write_context(request.kb_root)

# create.py retains destination checks, warnings, body handling, refs,
# supersession eligibility, allocation, naming, timestamp, and rendering.
intent = WriteIntent(
    birth=DocumentBirth(
        path=document_relative,
        content=document_content.encode("utf-8"),
    ),
    mutations=(
        [MutationTarget(key="superseded", path=superseded_document.path)]
        if superseded_document is not None
        else []
    ),
    log_entry=created_log_entry,
)

prepared = prepare_write(context, intent)
replacements: dict[str, bytes] = {}
if superseded_document is not None:
    replacements["superseded"] = replace_frontmatter_scalars(
        prepared.sources["superseded"].content,
        {
            "status": "superseded",
            "timestamp": timestamp,
            "last_human_touch": timestamp,
        },
        append_missing=("timestamp", "last_human_touch"),
    )

receipt = apply_write(prepared, replacements)
```

### Ingest

```python
context = load_write_context(request.kb_root)

# ingest.py retains acquisition, normalization, about resolution,
# allocation, naming, classification, and rendering for now.
companions = (
    [CompanionBirth(path=original_relative, content=original_bytes)]
    if original_bytes is not None
    else []
)
intent = WriteIntent(
    birth=DocumentBirth(
        path=document_relative,
        content=document_bytes,
        companions_before=companions,
    ),
    log_entry=ingested_log_entry,
)

prepared = prepare_write(context, intent)
receipt = apply_write(prepared)
```

Each command constructs its existing result model from domain values and `receipt`. The pipeline does not know about `CreateResult`, `IngestResult`, warnings, `original`, `superseded`, or rendering.

## Compatibility with the CLI/Core Input Seam

The later input-seam plan splits command preparation around CLI-owned acquisition. Its prepared create/ingest models may carry `WriteContext`, or the command may relay that context privately. The ordering remains:

```text
CLI binds source/body without I/O
  → core command preparation calls load_write_context()
  → CLI acquires external bytes
  → core completes domain policy and builds WriteIntent
  → prepare_write()
  → command-specific mutation transformation
  → apply_write()
```

No external path read, stdin access, platform lookup, PATH lookup, subprocess execution, Typer call, printing, or `sys.exit` enters the write pipeline.

## Testing Strategy

Tests use real temporary directories through the module interface. No public filesystem adapter or mock repository is introduced.

Direct pipeline coverage includes:

- root/config propagation and one scan;
- incremental frontmatter-prefix acquisition for ordinary and rooted scans,
  with lazy bodies and no retained complete Markdown bytes;
- later full rooted acquisition of lossless mutation-source bytes;
- deterministic malformed allocation blocking;
- root-relative path and containment validation;
- overlapping path rejection;
- nested directory and born-current index creation;
- replacement of a just-born directory before its index/child/document birth,
  including nested chains and final born-identity verification;
- only the nearest pre-existing index refresh;
- exclusion of binary companions from Markdown indexes;
- companion-before-document ordering;
- exclusive creation and late occupants at companion, document, and new-index paths;
- stale mutation, index, and log identity rejection;
- symlink/junction refusal;
- missing-log exclusive recreation with exact scaffold and one row;
- exact successful prepared log bytes and log-last ordering, plus typed
  preflight failure for an unencodable log row;
- pre-write supersession transformation failure;
- exact replacement-key validation;
- one-shot preparation consumption;
- sorted receipts excluding `log.md`; and
- fixed partial-state order after write-phase failure.

Create AC01–AC52 and ingest AC01–AC50 remain end-to-end gates. Existing safe-I/O tests remain focused on the smaller internal module's interface. Command-private orchestration tests that become redundant move to `test_write_pipeline.py`; normative acceptance and error/output tests remain in the command suites.

Architecture tests assert that `create.py` and `ingest.py` consume `write_pipeline.py`, import `slug` from `naming.py`, and no longer directly call index regeneration, log append, safe write primitives, or mutating filesystem APIs. Semantic fixtures cover aliases and module qualification; mutating and dynamic built-in/`Path.open` modes; mutating `Path`, `os`, and `shutil` calls; and file-object writes. They continue to allow the current provably read-only external file acquisition and avoid false positives for domain/Pydantic calls.

## Migration Order

1. Freeze the current create, ingest, and repository suites.
2. Move `slug()` unchanged to `core/naming.py` and update both callers.
3. Introduce the write-pipeline models, context loading, preparation, application, and direct tests using TDD.
4. Migrate create first, preserving every command contract and using its stronger current identity safety as the baseline.
5. Migrate ingest, preserving original-first binary filing while upgrading mutable index/log operations to the shared identity-checked behavior.
6. Delete duplicated directory/index/log/write orchestration and command-specific effects bookkeeping.
7. Add architecture enforcement and run all focused and complete suites.
8. Update only stale path references in the CLI/core input-seam plan if the extraction changes any named files.

## Rejected Scope

- no rollback or transaction manager;
- no arbitrary filesystem operation DSL;
- no filesystem port or adapter;
- no injectable public I/O callbacks;
- no command-specific destination policy in the pipeline;
- no `kb revise` interface before its normative spec;
- no PRD changes and no command-surface, successful-output, or AC-number changes;
- no dependency additions; and
- no external file/stdin/clipboard/create-body acquisition changes in this
  prerequisite; the root-bound lazy allocation snapshot is part of this
  design.

## Success Criteria

The design is complete when:

- create and ingest use the same write-pipeline interface;
- the duplicated commit/index/log implementations are deleted rather than wrapped;
- `slug()` no longer lives in `ingest.py`;
- ingest index/log mutation safety matches create's identity-checked behavior;
- all create AC01–AC52 and ingest AC01–AC50 pass unchanged;
- direct pipeline tests cover its safety and ordering interface;
- architecture tests prevent regression to command-owned persistence; and
- the later CLI/core input-seam plan can consume the module without duplicating persistence logic.
