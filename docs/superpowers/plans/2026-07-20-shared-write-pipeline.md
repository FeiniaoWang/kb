# Shared Create/Ingest Write Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicated `kb create` and `kb ingest` filesystem commit orchestration with one identity-checked shared core write pipeline while preserving every observable command contract.

**Architecture:** Command modules retain destination grammar, domain validation, allocation, naming, frontmatter rendering, command-specific failures, and result construction. A deep `kb.core.write_pipeline` module loads the shared allocating-write context, prepares a typed document-birth intent without writes, exposes identity-checked mutation source bytes, and applies one fixed sequence for directories, indexes, companions, documents, mutable replacements, and `log.md`. The filesystem remains a direct local dependency tested through `tmp_path`; there is no filesystem port or adapter.

**Tech Stack:** Python >=3.14, Pydantic 2.x, PyYAML, pytest, `uv`; no new runtime or development dependencies.

## Human-Approved Containment Amendment

This amendment supersedes the path-based safe-I/O code snippets in this plan.
All namespace resolution begins at the KB selected during preparation. Capture
the root directory identity without keeping descriptors in `PreparedWrite`;
for every operation, reopen and verify that root, traverse relative directory
components using descriptor-relative no-follow opens, and keep the verified
parent descriptor open through the final `mkdir`, exclusive create, inspect,
read, identity-checked overwrite, or append. Refuse the operation with
`OSError` before mutation on platforms lacking the necessary stdlib
`dir_fd`/no-follow support. Close every descriptor on every path so an
abandoned preparation cannot leak handles.

The containment guarantee is descriptor/object containment. Every descriptor
is resolved from the captured root under no-follow rules, but once open it
binds the filesystem object rather than its lexical pathname. Portable
Darwin/Linux interfaces cannot stop a non-cooperating namespace writer from
renaming that bound inode outside the lexical KB root between open and
mutation. That post-open movement is outside the threat model; no exclusive-
writer or snapshot-isolation guarantee is claimed. If a later pathname-identity
check observes the movement or a replacement at an expected pathname, it
returns the established typed failure; not every post-open movement is
necessarily observed, including movement during the final log effect after the
last available born-directory check. Bytes already written through the bound
descriptor remain documented no-rollback partial state on the moved object.
Ordinary symlink/path traversal and pre-open replacement of paths with an
established expected identity retain their documented protections. The
high-entropy born staging path is the explicit exception: before its first open
it has no expected identity and may bind a substituted real directory only when
that directory is observed empty.

Before returning from preparation, reject any explicit birth, companion, or
mutation path that collides with an implicit born index, the affected existing
index, or root `log.md`. A document born as a would-be `index.md` is one such
prewrite `ValueError` when passed directly to the pipeline: it is programmer
misuse. Create and ingest command policy must prevent that invalid intent by
reserving each implicit born `index.md` path while applying the existing
deterministic collision-suffix naming algorithm.

After consumption, late path/link/environment failures are `WriteFailure`s
with the fixed operation and role for the attempted effect. In particular,
companion and document failures are `phase="write"`, `operation="create"`, with
their exact role and normalized root-relative path; directory, index, mutation,
and log failures remain attributed to `mkdir`, `create`, `overwrite`, and
`append` respectively. The application order and partial-write/no-rollback
contract are unchanged.

Context acquisition is also root-bound. Configuration and the recursive
Markdown scan are descriptor-relative to one captured root identity. Each
valid Markdown scan reads incrementally only through the closing frontmatter
delimiter; it does not read or retain the body. Ordinary `scan()` and the
rooted allocating scan share one prefix reader and one frontmatter byte parser.
Malformed input may be read to EOF to establish a missing delimiter. Full
identity-checked bytes are acquired later only for mutation sources that need
lossless transformation. `Document.body` remains lazy, and no live descriptor
crosses `load_write_context()`, `prepare_write()`, or `apply_write()`.

Every created directory is first made under a high-entropy private staging
name beneath the verified parent. Because portable Darwin/Linux `mkdirat` does
not atomically return a descriptor, that pathname has no trusted creator
identity. The first descriptor-relative no-follow directory open and its
`fstat` bind the authoritative `FileIdentity`; a real-directory substitution
before that first open may be bound and published only if descriptor-relative
enumeration shows it is empty. A symlink, non-directory, or non-empty directory
at binding fails before publication. Emptiness is checked through the held
descriptor immediately after binding and again before publication; this
narrows the concurrent-change window without promising snapshot isolation.
A replacement inode present at an expected pathname when an available identity
check runs is detected before or after publication, during child writes, or
before the log effect. Operations already bound to an object follow that object
under the threat-model scope above. Creator-provenance authentication before
first open is not promised.

The implementation atomically publishes the bound directory to the final name
with a kernel no-replace primitive and verifies that the published entry
matches the bound identity before returning it. Darwin uses
`renameatx_np(..., RENAME_EXCL)` and Linux uses
`renameat2(..., RENAME_NOREPLACE)`; ordinary rename is never an acceptable
fallback because it may overwrite an empty late occupant. Unsupported
platforms fail safely. Failed publication preserves the final occupant and
performs no path-based staging deletion: a separate `stat`/`rmdir` pair cannot
bind deletion to the held descriptor and could delete a replacement.

Failure after staging creation may therefore leave a randomized
`.kb-born-<high-entropy>` directory as permitted no-rollback partial state.
The prefix identifies the orphan for operational inspection; it is not hidden
from normal scan/index semantics. `kb index --check` can surface its missing
`index.md`, and a steward removes or repairs it only after confirming no live
write owns it and inspecting its contents. Successful exclusive publication
renames the staging entry away, leaving no staging pathname.

`apply_write()` keeps returned identities, not descriptors, as local state and
requires the expected immediate-parent identity for every subsequent
child-directory, born-index, companion, and document birth. It verifies every
born directory identity again before success. A replacement directory
installed at the old pathname after the first no-follow binding receives no
pipeline bytes. A moved already-bound directory may receive partial bytes
as no-rollback partial state. If a subsequent pathname-identity check observes
the movement, it returns a typed failure; no such later observation is promised
for movement during the final log effect. Parent and staging descriptors close
within the one rooted directory-birth operation on every path.

## Command-Contract Reconciliation Amendment

This amendment supersedes the narrower born-directory collision and
architecture-gate wording below. Create and ingest collision
naming always reserve `<target>/index.md`, whether present, implicit for a new
directory, or missing from a damaged existing directory. A damaged directory
therefore reaches typed pipeline preparation with the deterministic suffixed
document path and never leaks the pipeline's programmer-misuse `ValueError`.

Ingest destination preflight rejects every existing symlink or junction
component from the raw-class directory through the target before external
acquisition, including in-class links. The exact command result is
`E_INGEST_DEST_INVALID`, exit 2, with no KB or target mutation.

Supersession-specific classification requires exact unsafe-target provenance:
path references may match the unsafe root-relative path, while id references
need a safely parsed matching document/path. An unresolved id plus unrelated
unsafe Markdown path remains generic `E_CREATE_IO`; an `ELOOP` plus failed
resolution is not proof.

The architecture gate is semantic over direct filesystem writes as well as
the existing helper/import graph. It rejects mutating `Path`, built-in file,
`os`, and `shutil` calls, aliases/module qualification, dynamic or write-capable
open modes, and file-object writes. Provably read-only external acquisition in
the current command modules remains allowed until the separate input-seam
plan.

## Final-Review Destination and Log-Rendering Amendment

This amendment addresses the remaining destination-provenance and log
atomicity findings without changing traversal or validation order. On ingest's
existing context-loading exception path, parse `--dest` only for a non-raising
lexical comparison. Build the root-relative prefix chain from the selected raw
class directory through the requested destination. An exact unsafe-path match
maps to the established `E_INGEST_DEST_INVALID`; no match maps to the existing
generic/config/malformed result. Do not call the adapter, inspect a path, or
move destination validation ahead of context acquisition for this mapping.

`prepare_write()` formats and strict UTF-8 encodes the complete log row before
any mutation. Encoding failure is `WriteFailure("preflight", "render", "log",
Path("log.md"), OSError(EILSEQ, ...))`; a raw `UnicodeEncodeError` never escapes.
Store the resulting row bytes in private `PreparedWrite` state. `apply_write()`
uses those bytes only and does not format or encode log text. Successful row
bytes, existing/missing-log behavior, log-last ordering, and receipts remain
unchanged.

## Release-Hardening Amendment

Rooted Markdown snapshot traversal is iterative, descriptor-relative, and
bounded in live descriptor use. It does not recurse in Python or reopen every
descendant from the root, while preserving lexicographic traversal,
no-follow semantics, directory-identity checks on descent/ascent, root
identity verification, and deterministic typed failures. A valid tree deeper
than Python's recursion limit must never leak `RecursionError`.

Projected-index acquisition reads only the frontmatter prefix of existing
Markdown child documents in both the rooted pipeline and ordinary
path-acquiring convenience path. Full subdirectory `index.md` acquisition
remains permitted because its body heading is required listing metadata.

Final born-directory verification moves to immediately before the log create
or append. It is the last fallible pathname-identity operation before the final
log effect, so a verification failure leaves `log.md` byte-identical and no
fallible pipeline operation follows a successful log write.

## Final Typed-Preflight and Acquisition-Provenance Amendment

If rooted Markdown tree acquisition fails after listing—during a no-follow
directory/file open, identity inspection, or frontmatter-prefix read—a private
safe-I/O carrier preserves the exact root-relative failing path, the original
`OSError`, and all prefixes safely acquired before failure. The pipeline builds
the read-only partial `snapshot_kb` from only those prefixes and keeps the
public staged interface unchanged.

Create path-reference supersession classification and ingest requested
destination/component classification compare the exact failing path directly.
Create id references may use the partial snapshot to prove id-to-path
provenance. Context/surface/destination/adapter order is unchanged, adapters
are not invoked after a context failure, and the KB remains byte-identical.

Born-current index formatting and strict UTF-8 encoding are preflight render
work. Wrap expected `TypeError`/`ValueError` as `WriteFailure("preflight",
"render", "index", exact_born_index_path, OSError(EINVAL, ...))` and
`UnicodeEncodeError` with `EILSEQ`. Raw formatting/Unicode exceptions never
cross the pipeline seam; create and ingest retain their stable generic I/O
envelopes and no mutation occurs.

## Global Constraints

- The root source of truth is `docs/prd.md`; command behavior remains governed by `docs/specs/commands/00-shared.md`, `docs/specs/commands/kb-create.md`, and `docs/specs/commands/kb-ingest.md` in that precedence order.
- Implement the approved design in `docs/superpowers/specs/2026-07-20-shared-write-pipeline-design.md`; do not expand it into `kb revise`, a transaction manager, rollback, or a generic filesystem operation language.
- Preserve `kb create` AC01–AC52 and `kb ingest` AC01–AC50: text/JSON output, streams, exit codes, error codes/messages, help, warnings, bytes, paths, validation order, and documented partial-write behavior remain stable.
- Strengthen ingest index/log handling to the same pre-inspected, identity-checked mutable-write behavior already used by create.
- A preparation failure performs no writes. A write-phase `OSError` may leave effects completed earlier in the fixed sequence; no rollback is added.
- Every new document, binary companion, and born `index.md` uses exclusive creation and never follows its final path when it is a symlink or junction.
- Normal and rooted scans incrementally acquire only each Markdown
  frontmatter prefix; allocation contexts retain no document body or complete
  Markdown source bytes, while full rooted mutation-source acquisition remains
  deferred to preparation.
- Every born directory identity is bound by the first no-follow directory open
  and `fstat` after staging-path creation, before atomic exclusive publication,
  required for all later
  child/index/companion/document births below it, and verified before success;
  no descriptor survives an individual rooted operation and no ordinary rename
  fallback may overwrite a late occupant. A real-directory substitution before
  that first open may become the bound identity only when descriptor-relative
  enumeration observes it empty at binding. Every descriptor is resolved from
  the captured root; a non-cooperating post-open rename of its bound object is
  outside the containment threat model and may carry documented partial bytes
  outside the lexical root. Failed staging is never path-deleted after a
  separate check and remains identifiable partial state when present.
- Every existing mutation target, existing affected index, and existing `log.md` is inspected before the write boundary and updated using the captured `FileIdentity`.
- The fixed application order is: missing directories and born indexes root-to-leaf; companions in declared order; citable document; mutations in declared order; nearest pre-existing affected index; log last.
- Binary ingest represents the byte-identical original as a companion, so the original is created before the Markdown stub.
- `WriteReceipt.created` and `WriteReceipt.updated` contain alphabetically sorted KB-root-relative POSIX paths and exclude `log.md`.
- All public core data models introduced here are Pydantic 2.x `BaseModel`s. Private implementation state may use `PrivateAttr` and ordinary private helper types.
- `src/kb/core/create.py` and `src/kb/core/ingest.py` retain their existing failure classes and map neutral pipeline failures to their stable command contracts.
- Keep destination grammar, reference resolution, id allocation, collision policy, frontmatter rendering, and result models outside the write pipeline.
- Preserve context/malformed/surface/destination/adapter ordering. Ingest may
  classify a rooted context failure as destination-invalid only by exact
  equality with the lexical requested class/destination component chain; no
  additional traversal or adapter call is permitted.
- Create and ingest command collision policy always treats the target directory's CLI-maintained `index.md` as occupied before choosing the document filename, whether it exists, would be born, or is missing from a damaged existing directory; a direct pipeline intent that still collides with an implicit path remains programmer misuse rejected by `prepare_write()`.
- Keep external file/stdin/clipboard/create-body acquisition unchanged; the
  root-bound lazy allocation snapshot is in this plan, while the later
  `2026-07-20-cli-core-input-seam.md` plan owns external command input.
- Move `slug()` unchanged to `src/kb/core/naming.py`; do not combine this with broader naming changes.
- No Typer, printing, `sys.exit`, network, Git operations, persistent cache/index, or new dependency enters `src/kb/core/`.
- Prepare and strict UTF-8 encode the full log row before mutation, keep the
  bytes private, and make application consume those bytes without rendering.
- Use `uv run pytest`; CLI tests continue to invoke Typer through `CliRunner`, not subprocesses.
- Preserve unrelated user changes. At plan-writing time `.gitignore` is modified and `docs/superpowers/plans/2026-07-20-cli-core-input-seam.md` is untracked; do not stage, edit, or remove either file while executing this plan.

---

## File Structure

- Create `src/kb/core/naming.py`: the shared deterministic `slug()` computation.
- Create `src/kb/core/write_pipeline.py`: typed write intent, context/preparation/application interface, neutral failures, and hidden safe-I/O orchestration.
- Modify `src/kb/core/indexing.py`: allow deterministic index rendering from an identity-checked index source plus projected file/subdirectory listing lines.
- Modify `src/kb/core/create.py`: consume `naming.py` and `write_pipeline.py`; delete command-owned directory/index/log/write orchestration.
- Modify `src/kb/core/ingest.py`: consume `naming.py` and `write_pipeline.py`; delete command-owned directory/index/log/write orchestration.
- Create `tests/core/test_naming.py`: pin the moved pure helper.
- Modify `tests/core/test_indexing.py`: pin projected listing order and identity-source rendering.
- Create `tests/core/test_write_pipeline.py`: test the deep module through its interface with real temporary filesystems.
- Create `tests/test_write_pipeline_architecture.py`: prevent create/ingest from regaining persistence orchestration or a private slug copy.
- Modify `tests/cli/test_ingest.py`: add stale-index/log integration coverage for the strengthened safety contract without renumbering or changing AC01–AC50.

## Stable Interfaces

```python
# src/kb/core/naming.py
def slug(value: str, fallback: str) -> str
```

```python
# src/kb/core/indexing.py
def regenerate_directory_index(
    root: Path,
    directory: Path,
    *,
    source: bytes | None = None,
    planned_files: Mapping[str, str] | None = None,
    planned_subdirectories: Mapping[str, str] | None = None,
) -> str
```

`source=None` preserves the current path-reading behavior for existing callers. The pipeline always supplies identity-checked `source` bytes. Planned mappings are keyed by filename/directory name and contain already-rendered listing lines; existing and planned entries are merged by key and emitted in deterministic key order.

```python
# src/kb/core/write_pipeline.py
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


class AllocationBlocked(Exception):
    paths: tuple[Path, ...]


class WriteFailure(Exception):
    phase: WritePhase
    operation: WriteOperation
    role: WriteRole
    path: Path
    cause: OSError
    key: str | None
    snapshot_kb: KB | None


def load_write_context(kb_root: Path | None) -> WriteContext


def prepare_write(context: WriteContext, intent: WriteIntent) -> PreparedWrite


def apply_write(
    prepared: PreparedWrite,
    replacements: Mapping[str, bytes] | None = None,
) -> WriteReceipt
```

`PreparedWrite` uses private attributes for the resolved root, original intent,
mutation identities, affected-index path/identity/bytes, log identity,
born-index plan, receipt paths, and consumed flag. `sources` is the only public
preparation detail. Born-directory identities do not enter the public model;
`apply_write()` captures and retains them locally as directories are created.
The complete rendered log row is stored as a private `bytes` attribute and
never exposed through the public Pydantic fields.

`WriteFailure.snapshot_kb` is read-only context-failure provenance. It is
populated only with the safely parsed partial snapshot available when rooted
Markdown acquisition fails, so a command can prove an exact id/path or
destination-path classification. It is not a mutable or persistent KB
cache/index and is `None` when no safely parsed partial snapshot is available.

---

### Task 1: Extract Deterministic Naming

**Historical execution record:** Complete in `7d72ce0`. The unchecked steps
below preserve the original TDD instructions; they are not pending work.

**Files:**
- Create: `src/kb/core/naming.py`
- Create: `tests/core/test_naming.py`
- Modify: `src/kb/core/create.py`
- Modify: `src/kb/core/ingest.py`

**Interfaces:**
- Consumes: the existing `slug(value: str, fallback: str) -> str` behavior in `src/kb/core/ingest.py`.
- Produces: `kb.core.naming.slug`, imported by both command modules and unchanged for every current title/collision case.

- [ ] **Step 1: Write the failing naming tests**

Create `tests/core/test_naming.py`:

```python
import pytest

from kb.core.naming import slug


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [
        ("Webhook Retry Policy", "KB-000001", "webhook-retry-policy"),
        ("Résumé / Über", "KB-000002", "resume-uber"),
        ("___", "RAW-000003", "raw-000003"),
        ("Already--Spaced", "KB-000004", "already-spaced"),
    ],
)
def test_slug_is_ascii_deterministic_and_uses_lowercase_fallback(
    value: str,
    fallback: str,
    expected: str,
) -> None:
    assert slug(value, fallback) == expected
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/core/test_naming.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'kb.core.naming'`.

- [ ] **Step 3: Move the helper without changing it**

Create `src/kb/core/naming.py`:

```python
from __future__ import annotations

import re
import unicodedata


def slug(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    candidate = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return candidate or fallback.lower()
```

In `src/kb/core/create.py`, replace:

```python
from kb.core.ingest import slug
```

with:

```python
from kb.core.naming import slug
```

In `src/kb/core/ingest.py`, remove the `unicodedata` import and local `slug()` definition, and add:

```python
from kb.core.naming import slug
```

- [ ] **Step 4: Run focused and command regression tests**

Run:

```bash
uv run pytest tests/core/test_naming.py tests/cli/test_create.py tests/cli/test_ingest.py -q
```

Expected: the naming tests pass; create AC01–AC52 and ingest AC01–AC50 remain green.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/kb/core/naming.py src/kb/core/create.py src/kb/core/ingest.py tests/core/test_naming.py
git commit -m "refactor(core): share deterministic slug naming"
```

Expected: the commit contains only the naming move and its direct test.

---

### Task 2: Add Projected Index Rendering

**Historical execution record:** Complete in `85e4b26`. The unchecked steps
below preserve the original TDD instructions; they are not pending work.

**Files:**
- Modify: `src/kb/core/indexing.py`
- Modify: `tests/core/test_indexing.py`

**Interfaces:**
- Consumes: current `regenerate_directory_index(root, directory)` behavior and listing-line helpers.
- Produces: the backward-compatible `source`, `planned_files`, and `planned_subdirectories` keyword interface used by Task 3.

- [ ] **Step 1: Add failing projected-rendering tests**

Append to `tests/core/test_indexing.py`:

```python
def test_regeneration_uses_identity_checked_source_and_merges_planned_file(
    tmp_path,
) -> None:
    init_kb(tmp_path)
    directory = tmp_path / "synthetic"
    index = directory / "index.md"
    source = index.read_bytes()
    index.write_text("not the prepared source\n", encoding="utf-8")

    rendered = regenerate_directory_index(
        tmp_path,
        directory,
        source=source,
        planned_files={
            "planned.md": "* [KB-000001][Planned](planned.md) - Planned."
        },
    )

    assert rendered.startswith("---\ntype: index\n")
    assert "not the prepared source" not in rendered
    assert "* [KB-000001][Planned](planned.md) - Planned." in rendered


def test_projected_entries_merge_by_path_key_not_rendered_label(tmp_path) -> None:
    init_kb(tmp_path)
    directory = tmp_path / "synthetic"
    (directory / "zulu.md").write_text(
        "---\nid: KB-000009\ntype: spec\ntitle: A First Label\n"
        "description: Existing.\n---\n",
        encoding="utf-8",
    )

    rendered = regenerate_directory_index(
        tmp_path,
        directory,
        planned_files={
            "alpha.md": "* [KB-000010][Z Last Label](alpha.md) - Planned."
        },
    )

    assert rendered.index("(alpha.md)") < rendered.index("(zulu.md)")
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
uv run pytest tests/core/test_indexing.py -q
```

Expected: both new tests fail because the keyword parameters do not exist.

- [ ] **Step 3: Make listing collection key-aware**

In `src/kb/core/indexing.py`, import `Mapping`:

```python
from collections.abc import Mapping
```

Replace `render_directory_listing()` with this backward-compatible implementation:

```python
def render_directory_listing(
    root: Path,
    directory: Path,
    *,
    planned_files: Mapping[str, str] | None = None,
    planned_subdirectories: Mapping[str, str] | None = None,
) -> str:
    subdirectories = dict(planned_subdirectories or {})
    files = dict(planned_files or {})
    for child in sorted(path for path in directory.iterdir() if path.is_dir()):
        index = child / "index.md"
        if not index.is_file():
            continue
        frontmatter = read_frontmatter(index).root
        subdirectories[child.name] = subdirectory_listing_line(
            child.name,
            _description(frontmatter),
            title=_heading(index),
        )
    for child in sorted(directory.glob("*.md")):
        if child.name in {"index.md", "log.md"}:
            continue
        frontmatter = read_frontmatter(child).root
        if frontmatter.get("type") == "log":
            continue
        doc_id = frontmatter.get("id")
        title = frontmatter.get("title") or child.stem
        files[child.name] = file_listing_line(
            child.name,
            str(doc_id) if doc_id is not None else None,
            str(title),
            _description(frontmatter),
        )
    sections: list[str] = []
    if subdirectories:
        sections.append(
            "## Subdirectories\n"
            + "\n".join(subdirectories[name] for name in sorted(subdirectories))
        )
    if files:
        sections.append(
            "## Files\n" + "\n".join(files[name] for name in sorted(files))
        )
    return "\n\n".join(sections)
```

- [ ] **Step 4: Add identity-source support to index regeneration**

Replace `regenerate_directory_index()` with:

```python
def regenerate_directory_index(
    root: Path,
    directory: Path,
    *,
    source: bytes | None = None,
    planned_files: Mapping[str, str] | None = None,
    planned_subdirectories: Mapping[str, str] | None = None,
) -> str:
    path = directory / "index.md"
    text = (
        path.read_text(encoding="utf-8")
        if source is None
        else source.decode("utf-8", errors="strict")
    )
    lines = text.splitlines(keepends=True)
    closing = _frontmatter_closing(lines)
    frontmatter_block = "".join(lines[: closing + 1])
    if not frontmatter_block.endswith("\n"):
        frontmatter_block += "\n"
    body = f"# {_heading_from_text(text, path.parent.name)}\n\n{INDEX_COMMENT}\n"
    listing = render_directory_listing(
        root,
        directory,
        planned_files=planned_files,
        planned_subdirectories=planned_subdirectories,
    )
    return (
        frontmatter_block + body
        if not listing
        else frontmatter_block + body + f"\n{listing}\n"
    )
```

Add the pure heading helper and make `_heading()` delegate to it:

```python
def _heading_from_text(text: str, fallback: str) -> str:
    lines = text.splitlines()
    closing = _frontmatter_closing(lines)
    for line in lines[closing + 1 :]:
        if line.startswith("# "):
            return line[2:]
    return fallback


def _heading(path: Path) -> str:
    return _heading_from_text(path.read_text(encoding="utf-8"), path.parent.name)
```

- [ ] **Step 5: Run indexing and repository regression tests**

Run:

```bash
uv run pytest tests/core/test_indexing.py tests/cli/test_create.py tests/cli/test_ingest.py -q
```

Expected: all tests pass with byte-identical existing index output.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/kb/core/indexing.py tests/core/test_indexing.py
git commit -m "refactor(index): support projected write listings"
```

---

### Task 3: Implement the Shared Write Pipeline

**Historical execution record:** Complete in `174101a` through `0c6c036`. The
unchecked steps below preserve the original TDD instructions; they are not
pending work.

**Files:**
- Create: `src/kb/core/write_pipeline.py`
- Create: `tests/core/test_write_pipeline.py`

**Interfaces:**
- Consumes: `safeio` rooted exclusive/identity-checked primitives,
  `LogEntry` formatting, Task 2 projected index rendering, root discovery,
  descriptor-relative config acquisition, and the shared incremental
  frontmatter-prefix scan parser.
- Produces: the exact `WriteContext`, `DocumentBirth`, `CompanionBirth`, `MutationTarget`, `WriteIntent`, `PreparedWrite`, `WriteReceipt`, `AllocationBlocked`, `WriteFailure`, `load_write_context()`, `prepare_write()`, and `apply_write()` interface under Stable Interfaces.

- [ ] **Step 1: Write failing context and intent tests**

Create `tests/core/test_write_pipeline.py` with these imports and helpers:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from kb.core.housekeeping import LogEntry, init_kb
from kb.core.write_pipeline import (
    AllocationBlocked,
    CompanionBirth,
    DocumentBirth,
    MutationTarget,
    WriteFailure,
    WriteIntent,
    apply_write,
    load_write_context,
    prepare_write,
)


def document_bytes(
    doc_id: str = "KB-000001",
    title: str = "Planned",
    description: str | None = "Planned document.",
) -> bytes:
    description_line = (
        "" if description is None else f"description: {description}\n"
    )
    return (
        "---\n"
        f"id: {doc_id}\n"
        "type: spec\n"
        f"title: {title}\n"
        f"{description_line}"
        "---\n"
        "Body\n"
    ).encode("utf-8")


def log_entry(doc_id: str = "KB-000001") -> LogEntry:
    return LogEntry(
        at="2026-07-20T12:00:00Z",
        action="created",
        actor="test",
        doc_ids=[doc_id],
        note="synthetic/planned.md",
    )


def initialized(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    assert init_kb(root).root == root.resolve()
    return root
```

Add the first tests:

```python
def test_load_context_blocks_malformed_documents_without_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    malformed = root / "synthetic/bad.md"
    malformed.write_text("not frontmatter\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(AllocationBlocked) as raised:
        load_write_context(root)

    assert raised.value.paths == (Path("synthetic/bad.md"),)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    "relative",
    [Path("/absolute.md"), Path("../escape.md"), Path(r"synthetic\\escape.md")],
)
def test_prepare_rejects_non_relative_posix_birth_paths_before_writes(
    tmp_path,
    relative,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    intent = WriteIntent(
        birth=DocumentBirth(path=relative, content=document_bytes()),
        log_entry=log_entry(),
    )

    with pytest.raises(ValueError):
        prepare_write(context, intent)

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_exposes_identity_checked_mutation_source_without_writes(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    context = load_write_context(root)
    intent = WriteIntent(
        birth=DocumentBirth(
            path=Path("synthetic/planned.md"),
            content=document_bytes(),
        ),
        mutations=[MutationTarget(key="superseded", path=Path("synthetic/old.md"))],
        log_entry=log_entry(),
    )

    prepared = prepare_write(context, intent)

    assert prepared.sources["superseded"].content == old.read_bytes()
    assert not (root / "synthetic/planned.md").exists()


def test_prepare_rejects_markdown_companion_before_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    intent = WriteIntent(
        birth=DocumentBirth(
            path=Path("raw/sources/evidence.md"),
            content=(
                b"---\nid: RAW-000001\ntype: raw-source\n"
                b"title: Evidence\n---\nStub\n"
            ),
            companions_before=[
                CompanionBirth(
                    path=Path("raw/sources/original.md"), content=b"binary"
                )
            ],
        ),
        log_entry=LogEntry(
            at="2026-07-20T12:00:00Z",
            action="ingested",
            actor="test",
            doc_ids=["RAW-000001"],
            note="raw/sources/evidence.md",
        ),
    )

    with pytest.raises(ValueError, match="must not be Markdown"):
        prepare_write(context, intent)
```

- [ ] **Step 2: Run the context tests to verify RED**

Run:

```bash
uv run pytest tests/core/test_write_pipeline.py -q
```

Expected: collection fails because `kb.core.write_pipeline` does not exist.

- [ ] **Step 3: Define the public models and neutral failures**

Create `src/kb/core/write_pipeline.py` with the Stable Interfaces exactly. Use these concrete exception initializers:

```python
class AllocationBlocked(Exception):
    def __init__(self, paths: tuple[Path, ...]) -> None:
        super().__init__("malformed documents block id allocation")
        self.paths = paths


class WriteFailure(Exception):
    def __init__(
        self,
        phase: WritePhase,
        operation: WriteOperation,
        role: WriteRole,
        path: Path,
        cause: OSError,
        *,
        key: str | None = None,
    ) -> None:
        super().__init__(str(cause))
        self.phase = phase
        self.operation = operation
        self.role = role
        self.path = path
        self.cause = cause
        self.key = key
```

Declare `PreparedWrite` with these private attributes:

```python
class PreparedWrite(BaseModel):
    sources: dict[str, MutationSource]
    _root: Path = PrivateAttr()
    _intent: WriteIntent = PrivateAttr()
    _mutation_identities: dict[str, FileIdentity] = PrivateAttr(default_factory=dict)
    _new_directories: list[Path] = PrivateAttr(default_factory=list)
    _new_indexes: dict[Path, bytes] = PrivateAttr(default_factory=dict)
    _refresh_index: Path = PrivateAttr()
    _refresh_identity: FileIdentity = PrivateAttr()
    _refresh_content: bytes = PrivateAttr()
    _log_identity: FileIdentity | None = PrivateAttr(default=None)
    _created: list[str] = PrivateAttr(default_factory=list)
    _updated: list[str] = PrivateAttr(default_factory=list)
    _consumed: bool = PrivateAttr(default=False)
```

Implement context loading exactly once through a short-lived rooted reader.
Configuration is acquired in full, while `_snapshot_markdown_prefixes()`
incrementally reads only through each Markdown file's closing frontmatter
delimiter. `scan_snapshot()` receives those prefixes and does not attach them
to `Document` objects:

```python
def load_write_context(kb_root: Path | None) -> WriteContext:
    root = discover_root(kb_root)
    with rooted_reader(root) as reader:
        root_identity = reader.identity
        config = parse_config_bytes(reader.read_file(Path("kb-config.json")))
        kb = scan_snapshot(root, _snapshot_markdown_prefixes(reader))
    if kb.malformed:
        paths = tuple(sorted(path for path, _ in kb.malformed))
        raise AllocationBlocked(paths)
    context = WriteContext(root=root, config=config, kb=kb)
    context._root_identity = root_identity
    return context
```

The ordinary path-based `scan()` calls the same incremental prefix-reader and
frontmatter byte parser. A no-closing-delimiter file may run to EOF; a valid
file's body must never be read or retained. Supersession continues to use the
separate full rooted `read_rooted_bytes()` acquisition during preparation.

- [ ] **Step 4: Implement private path and document-metadata validation**

Use these private helpers; all returned `Path`s are normalized root-relative paths:

```python
def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _relative_path(root: Path, value: Path) -> Path:
    shown = value.as_posix()
    candidate = PurePosixPath(shown)
    if (
        value.is_absolute()
        or not candidate.parts
        or "\\" in shown
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"write path must be KB-root-relative POSIX: {shown}")
    relative = Path(*candidate.parts)
    resolved = (root / relative).resolve(strict=False)
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(f"write path escapes KB root: {shown}")
    current = root
    for part in relative.parts:
        current /= part
        if _is_link_or_junction(current):
            raise ValueError(f"write path contains a symlink or junction: {shown}")
    return relative


def _document_listing(content: bytes, filename: str) -> str:
    text = content.decode("utf-8", errors="strict")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("planned document is missing opening frontmatter delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(
            "planned document is missing closing frontmatter delimiter"
        ) from error
    parsed = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(parsed, dict):
        raise ValueError("planned document frontmatter must be a mapping")
    doc_id = parsed.get("id")
    title = parsed.get("title")
    description = parsed.get("description")
    if not isinstance(doc_id, str) or not isinstance(title, str):
        raise ValueError("planned document requires string id and title")
    if description is not None and not isinstance(description, str):
        raise ValueError("planned document description must be a string")
    return file_listing_line(filename, doc_id, title, description)
```

Validate that the birth ends in `.md`, companion paths are distinct siblings of the birth, mutation keys/paths are unique, no paths overlap, existing path shapes are regular, and the destination directory chain contains no file where a directory is required.

- [ ] **Step 5: Implement write preparation with identity-checked sources**

`prepare_write()` must perform this exact sequence before returning:

```python
def prepare_write(context: WriteContext, intent: WriteIntent) -> PreparedWrite:
    root = context.root.resolve()
    birth_relative = _relative_path(root, intent.birth.path)
    if birth_relative.suffix != ".md":
        raise ValueError("citable document birth must end in .md")
    companion_relatives = [
        _relative_path(root, companion.path)
        for companion in intent.birth.companions_before
    ]
    mutation_relatives = [
        _relative_path(root, mutation.path) for mutation in intent.mutations
    ]
    if any(path.parent != birth_relative.parent for path in companion_relatives):
        raise ValueError("companion births must be siblings of the citable document")
    if any(path.suffix == ".md" for path in companion_relatives):
        raise ValueError("companion births must not be Markdown documents")
    all_paths = [birth_relative, *companion_relatives, *mutation_relatives]
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("write intent paths must be distinct")
    keys = [mutation.key for mutation in intent.mutations]
    if len(set(keys)) != len(keys):
        raise ValueError("mutation keys must be unique")

    target_dir = root / birth_relative.parent
    new_directories = _missing_directories(root, target_dir)
    refresh_directory = (
        new_directories[0].parent if new_directories else target_dir
    )
    refresh_index = refresh_directory / "index.md"

    sources: dict[str, MutationSource] = {}
    mutation_identities: dict[str, FileIdentity] = {}
    for mutation, relative in zip(intent.mutations, mutation_relatives, strict=True):
        absolute = root / relative
        try:
            identity = inspect_mutable_file(absolute)
        except OSError as error:
            raise WriteFailure(
                "preflight",
                "inspect",
                "mutation",
                relative,
                error,
                key=mutation.key,
            ) from error
        try:
            content = read_mutable_bytes(absolute, identity)
        except OSError as error:
            raise WriteFailure(
                "preflight",
                "read",
                "mutation",
                relative,
                error,
                key=mutation.key,
            ) from error
        mutation_identities[mutation.key] = identity
        sources[mutation.key] = MutationSource(
            key=mutation.key,
            path=relative,
            content=content,
        )

    try:
        refresh_identity = inspect_mutable_file(refresh_index)
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "index",
            refresh_index.relative_to(root),
            error,
        ) from error
    try:
        refresh_source = read_mutable_bytes(refresh_index, refresh_identity)
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "read",
            "index",
            refresh_index.relative_to(root),
            error,
        ) from error
    try:
        log_identity = inspect_mutable_file(root / "log.md", allow_missing=True)
    except OSError as error:
        raise WriteFailure(
            "preflight", "inspect", "log", Path("log.md"), error
        ) from error

    listing = _document_listing(intent.birth.content, birth_relative.name)
    new_indexes = _render_born_indexes(
        root,
        new_directories,
        birth_relative,
        listing,
    )
    planned_files = {birth_relative.name: listing} if not new_directories else None
    planned_subdirectories = (
        None
        if not new_directories
        else {
            new_directories[0].name: subdirectory_listing_line(
                new_directories[0].name,
                f"Documents under "
                f"{new_directories[0].relative_to(root).as_posix()}/.",
            )
        }
    )
    try:
        refresh_content = regenerate_directory_index(
            root,
            refresh_directory,
            source=refresh_source,
            planned_files=planned_files,
            planned_subdirectories=planned_subdirectories,
        ).encode("utf-8")
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        cause = error if isinstance(error, OSError) else OSError(str(error))
        raise WriteFailure(
            "preflight",
            "render",
            "index",
            refresh_index.relative_to(root),
            cause,
        ) from error

    prepared = PreparedWrite(sources=sources)
    prepared._root = root
    prepared._intent = intent.model_copy(deep=True)
    prepared._mutation_identities = mutation_identities
    prepared._new_directories = new_directories
    prepared._new_indexes = new_indexes
    prepared._refresh_index = refresh_index
    prepared._refresh_identity = refresh_identity
    prepared._refresh_content = refresh_content
    prepared._log_identity = log_identity
    prepared._created = sorted(
        [
            birth_relative.as_posix(),
            *(path.as_posix() for path in companion_relatives),
            *(path.relative_to(root).as_posix() for path in new_indexes),
        ]
    )
    prepared._updated = sorted(
        [
            *(path.as_posix() for path in mutation_relatives),
            refresh_index.relative_to(root).as_posix(),
        ]
    )
    return prepared
```

Implement directory discovery and born-index rendering exactly as follows:

```python
def _missing_directories(root: Path, target_dir: Path) -> list[Path]:
    missing: list[Path] = []
    current = root
    for part in target_dir.relative_to(root).parts:
        current /= part
        if _is_link_or_junction(current):
            raise ValueError(
                f"write destination contains a symlink or junction: "
                f"{current.relative_to(root).as_posix()}"
            )
        if current.exists() and not current.is_dir():
            raise ValueError(
                f"write destination component is not a directory: "
                f"{current.relative_to(root).as_posix()}"
            )
        if not current.exists():
            missing.append(current)
    return missing


def _render_born_indexes(
    root: Path,
    missing: list[Path],
    birth_relative: Path,
    document_listing: str,
) -> dict[Path, bytes]:
    if missing and birth_relative.parent != missing[-1].relative_to(root):
        raise ValueError("planned document parent does not match write destination")
    contents: dict[Path, bytes] = {}
    for offset, directory in enumerate(reversed(missing)):
        relative = directory.relative_to(root).as_posix()
        if offset == 0:
            listing = "## Files\n" + document_listing
        else:
            child = missing[len(missing) - offset]
            child_relative = child.relative_to(root).as_posix()
            listing = "## Subdirectories\n" + subdirectory_listing_line(
                child.name,
                f"Documents under {child_relative}/.",
            )
        contents[directory / "index.md"] = render_index(
            directory.name,
            f"Documents under {relative}/.",
            listing,
        ).encode("utf-8")
    return {
        directory / "index.md": contents[directory / "index.md"]
        for directory in missing
    }
```

`birth_relative` is intentionally accepted to make the helper's relationship to the planned document explicit.

- [ ] **Step 6: Add failing application-order and race tests**

Append tests that assert the public effects rather than private state:

```python
def test_apply_creates_nested_indexes_document_updates_ancestor_and_logs(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/b/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    receipt = apply_write(prepared)

    assert receipt.created == [
        "synthetic/a/b/index.md",
        "synthetic/a/b/planned.md",
        "synthetic/a/index.md",
    ]
    assert receipt.updated == ["synthetic/index.md"]
    assert "(planned.md)" in (root / "synthetic/a/b/index.md").read_text(
        encoding="utf-8"
    )
    assert "(a/index.md)" in (root / "synthetic/index.md").read_text(
        encoding="utf-8"
    )
    assert " | created | test | KB-000001 | " in (
        root / "log.md"
    ).read_text(encoding="utf-8")


def test_companion_is_created_before_document_and_excluded_from_index(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    seen: list[str] = []
    real_create = pipeline.create_file_bytes

    def record(path: Path, content: bytes) -> None:
        seen.append(path.relative_to(root).as_posix())
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", record)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
                companions_before=[
                    CompanionBirth(
                        path=Path("raw/sources/evidence.pdf"),
                        content=b"%PDF",
                    )
                ],
            ),
            log_entry=LogEntry(
                at="2026-07-20T12:00:00Z",
                action="ingested",
                actor="test",
                doc_ids=["RAW-000001"],
                note="raw/sources/evidence.md",
            ),
        ),
    )

    receipt = apply_write(prepared)

    assert seen.index("raw/sources/evidence.pdf") < seen.index(
        "raw/sources/evidence.md"
    )
    assert receipt.created == [
        "raw/sources/evidence.md",
        "raw/sources/evidence.pdf",
    ]
    assert "evidence.pdf" not in (
        root / "raw/sources/index.md"
    ).read_text(encoding="utf-8")


def test_late_document_occupant_is_preserved_and_preparation_is_consumed(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/planned.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    target.write_bytes(b"late occupant")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.role == "document"
    assert target.read_bytes() == b"late occupant"
    with pytest.raises(ValueError, match="already consumed"):
        apply_write(prepared)
```

Add these remaining safety tests:

```python
def test_stale_mutation_identity_preserves_late_replacement(tmp_path) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )
    old.rename(root / "synthetic/original-old.md")
    old.write_bytes(b"late replacement")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared, {"superseded": b"superseded"})

    assert raised.value.operation == "overwrite"
    assert raised.value.role == "mutation"
    assert old.read_bytes() == b"late replacement"


def test_stale_index_identity_is_not_overwritten_or_logged(tmp_path) -> None:
    root = initialized(tmp_path)
    index = root / "synthetic/index.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    log_before = (root / "log.md").read_bytes()
    index.rename(root / "synthetic/original-index.md")
    index.write_bytes(b"late index")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "overwrite"
    assert raised.value.role == "index"
    assert index.read_bytes() == b"late index"
    assert (root / "log.md").read_bytes() == log_before


def test_stale_log_identity_is_not_appended(tmp_path) -> None:
    root = initialized(tmp_path)
    log = root / "log.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    log.rename(root / "original-log.md")
    log.write_bytes(b"late log")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "append"
    assert raised.value.role == "log"
    assert log.read_bytes() == b"late log"


def test_missing_log_is_recreated_with_only_the_new_entry(tmp_path) -> None:
    root = initialized(tmp_path)
    (root / "log.md").unlink()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )

    apply_write(prepared)

    log = (root / "log.md").read_text(encoding="utf-8")
    assert "| initialized |" not in log
    assert log.count("| created | test | KB-000001 |") == 1


def test_replacement_keys_are_exact_and_checked_before_consumption(tmp_path) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(ValueError, match="exactly match"):
        apply_write(prepared)
    receipt = apply_write(prepared, {"superseded": b"superseded"})

    assert receipt.updated == ["synthetic/index.md", "synthetic/old.md"]


def test_prepare_rejects_symlink_birth_without_touching_target(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside")
    target = root / "synthetic/planned.md"
    try:
        target.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(ValueError, match="symlink or junction"):
        prepare_write(
            load_write_context(root),
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"), content=document_bytes()
                ),
                log_entry=log_entry(),
            ),
        )

    assert outside.read_bytes() == b"outside"


def test_document_failure_leaves_companion_but_not_index_or_log(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    index_before = (root / "raw/sources/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_create = pipeline.create_file_bytes
    document = root / "raw/sources/evidence.md"

    def fail_document(path: Path, content: bytes) -> None:
        if path == document:
            raise OSError("document failure")
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", fail_document)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
                companions_before=[
                    CompanionBirth(
                        path=Path("raw/sources/evidence.pdf"), content=b"%PDF"
                    )
                ],
            ),
            log_entry=LogEntry(
                at="2026-07-20T12:00:00Z",
                action="ingested",
                actor="test",
                doc_ids=["RAW-000001"],
                note="raw/sources/evidence.md",
            ),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.role == "document"
    assert (root / "raw/sources/evidence.pdf").read_bytes() == b"%PDF"
    assert not document.exists()
    assert (root / "raw/sources/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before


def test_late_born_index_occupant_is_preserved(tmp_path, monkeypatch) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    born_index = root / "synthetic/a/index.md"
    real_create = pipeline.create_file_bytes

    def occupy_index(path: Path, content: bytes) -> None:
        if path == born_index:
            real_create(path, b"late index")
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", occupy_index)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "create"
    assert raised.value.role == "index"
    assert born_index.read_bytes() == b"late index"
```

- [ ] **Step 7: Implement one-shot application**

`apply_write()` validates replacement keys before consuming the preparation, then marks it consumed before the first filesystem mutation:

```python
def apply_write(
    prepared: PreparedWrite,
    replacements: Mapping[str, bytes] | None = None,
) -> WriteReceipt:
    if prepared._consumed:
        raise ValueError("prepared write is already consumed")
    replacement_map = dict(replacements or {})
    expected_keys = set(prepared.sources)
    if set(replacement_map) != expected_keys:
        raise ValueError(
            "replacement keys must exactly match prepared mutation keys"
        )
    prepared._consumed = True
    root = prepared._root
    intent = prepared._intent
    try:
        for directory in prepared._new_directories:
            relative_directory = directory.relative_to(root)
            try:
                directory.mkdir()
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "mkdir",
                    "directory",
                    relative_directory,
                    error,
                ) from error
            index_path = directory / "index.md"
            try:
                create_file_bytes(index_path, prepared._new_indexes[index_path])
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "create",
                    "index",
                    index_path.relative_to(root),
                    error,
                ) from error
        for companion in intent.birth.companions_before:
            relative = _relative_path(root, companion.path)
            try:
                create_file_bytes(root / relative, companion.content)
            except OSError as error:
                raise WriteFailure(
                    "write", "create", "companion", relative, error
                ) from error
        birth_relative = _relative_path(root, intent.birth.path)
        try:
            create_file_bytes(root / birth_relative, intent.birth.content)
        except OSError as error:
            raise WriteFailure(
                "write", "create", "document", birth_relative, error
            ) from error
        for mutation in intent.mutations:
            source = prepared.sources[mutation.key]
            try:
                overwrite_mutable_bytes(
                    root / source.path,
                    replacement_map[mutation.key],
                    prepared._mutation_identities[mutation.key],
                )
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "overwrite",
                    "mutation",
                    source.path,
                    error,
                    key=mutation.key,
                ) from error
        try:
            overwrite_mutable_bytes(
                prepared._refresh_index,
                prepared._refresh_content,
                prepared._refresh_identity,
            )
        except OSError as error:
            raise WriteFailure(
                "write",
                "overwrite",
                "index",
                prepared._refresh_index.relative_to(root),
                error,
            ) from error
        try:
            append_log(
                root,
                intent.log_entry,
                expected_identity=prepared._log_identity,
            )
        except OSError as error:
            raise WriteFailure(
                "write", "append", "log", Path("log.md"), error
            ) from error
    except WriteFailure:
        raise
    except OSError as error:
        raise WriteFailure(
            "write", "mkdir", "directory", Path("."), error
        ) from error
    return WriteReceipt(created=prepared._created, updated=prepared._updated)
```

The outer fallback is only for an unexpected local `OSError`; every planned operation reports its exact root-relative path through the inner wrappers.

- [ ] **Step 8: Run direct pipeline tests and full regression**

Run:

```bash
uv run pytest tests/core/test_write_pipeline.py tests/core/test_indexing.py tests/core/test_safeio.py -q
uv run pytest -q
```

Expected: direct pipeline tests pass and the unchanged repository remains at least 306 passing tests.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/kb/core/write_pipeline.py tests/core/test_write_pipeline.py
git commit -m "feat(core): add identity-checked write pipeline"
```

---

### Task 4: Migrate `kb create` to the Pipeline

**Historical execution record:** Complete in `81bc4e5` and `236ea2c`. Commit
`81bc4e5` used `CLI-7` in its immutable historical subject by mistake; the
normative create requirement and this plan's traceability are `CLI-13`. The
unchecked steps below are not pending work.

**Files:**
- Modify: `src/kb/core/create.py`
- Create: `tests/test_write_pipeline_architecture.py`

**Interfaces:**
- Consumes: Tasks 1–3 and the existing `CreateFailure`, `CreateRequest`, `CreateResult`, supersession transformation, and destination/reference policies.
- Produces: create behavior through `load_write_context()` → `prepare_write()` → lossless supersession transformation → `apply_write()` with no command-owned persistence orchestration.

- [ ] **Step 1: Write a failing create architecture test**

Create `tests/test_write_pipeline_architecture.py`:

```python
from pathlib import Path


def source(relative: str) -> str:
    return Path(relative).read_text(encoding="utf-8")


def test_create_consumes_shared_write_pipeline() -> None:
    text = source("src/kb/core/create.py")
    assert "from kb.core.write_pipeline import" in text
    for forbidden in (
        "create_file_bytes(",
        "overwrite_mutable_bytes(",
        "append_log(",
        "regenerate_directory_index(",
        "def _new_index_contents(",
    ):
        assert forbidden not in text
```

- [ ] **Step 2: Run the architecture test to verify RED**

Run:

```bash
uv run pytest tests/test_write_pipeline_architecture.py::test_create_consumes_shared_write_pipeline -q
```

Expected: FAIL because create still owns and calls the persistence helpers.

- [ ] **Step 3: Replace create's context and malformed setup**

Import the pipeline interface:

```python
from kb.core.write_pipeline import (
    AllocationBlocked,
    DocumentBirth,
    MutationTarget,
    WriteFailure,
    WriteIntent,
    apply_write,
    load_write_context,
    prepare_write,
)
```

At the start of `create()`, replace direct root discovery/config/scan with:

```python
try:
    context = load_write_context(request.kb_root)
except RootDiscoveryError as error:
    raise CreateFailure(error.code, error.message, 2) from error
except ConfigLoadError as error:
    raise CreateFailure(error.code, error.message, 2) from error
except AllocationBlocked as error:
    paths = ", ".join(path.as_posix() for path in error.paths)
    raise CreateFailure(
        "E_CREATE_MALFORMED",
        f"malformed documents block id allocation: {paths}; run kb validate",
        2,
    ) from error
root = context.root
config = context.config
kb = context.kb
```

Keep create destination validation, warnings, body handling, parent/supersession resolution, allocation, collision naming, timestamp, frontmatter rendering, and relative path construction unchanged.

- [ ] **Step 4: Replace create's prewrite and write block**

Delete `_new_index_contents()`, `_superseded_bytes()`, direct index/log identity preparation, directory/index loops, safe writes, and manual `created`/`updated` construction.

Build the typed intent:

```python
intent = WriteIntent(
    birth=DocumentBirth(
        path=Path(relative),
        content=document_content.encode("utf-8"),
    ),
    mutations=(
        [MutationTarget(key="superseded", path=superseded_document.path)]
        if superseded_document is not None
        else []
    ),
    log_entry=LogEntry(
        at=timestamp,
        action="created",
        actor=request.actor,
        doc_ids=[doc_id]
        + ([superseded_document.id] if superseded_document is not None else []),
        note=relative
        + (
            f" supersedes {superseded_document.id}"
            if superseded_document is not None
            else ""
        ),
    ),
)
try:
    prepared_write = prepare_write(context, intent)
except WriteFailure as error:
    if (
        error.operation == "inspect"
        and error.role == "mutation"
        and error.key == "superseded"
    ):
        raise CreateFailure(
            "E_CREATE_SUPERSEDES_INVALID",
            f"supersedes target cannot be updated safely: "
            f"{request.supersedes}: {error.cause}",
            1,
        ) from error
    raise CreateFailure("E_CREATE_IO", str(error.cause), 2) from error

replacements: dict[str, bytes] = {}
if superseded_document is not None:
    try:
        replacements["superseded"] = replace_frontmatter_scalars(
            prepared_write.sources["superseded"].content,
            {
                "status": "superseded",
                "timestamp": timestamp,
                "last_human_touch": timestamp,
            },
            append_missing=("timestamp", "last_human_touch"),
        )
    except (UnicodeError, ValueError) as error:
        raise CreateFailure(
            "E_CREATE_SUPERSEDES_INVALID",
            f"supersedes target cannot be updated safely: "
            f"{request.supersedes}: {error}",
            1,
        ) from error
try:
    receipt = apply_write(prepared_write, replacements)
except WriteFailure as error:
    raise CreateFailure("E_CREATE_IO", str(error.cause), 2) from error
```

Construct `CreateResult` with `created=receipt.created` and `updated=receipt.updated`; preserve all other fields exactly.

- [ ] **Step 5: Run create-focused tests**

Run:

```bash
uv run pytest tests/test_write_pipeline_architecture.py::test_create_consumes_shared_write_pipeline tests/core/test_write_pipeline.py tests/cli/test_create.py -q
```

Expected: architecture and pipeline tests pass; all create AC01–AC52 and non-AC safety regressions pass.

- [ ] **Step 6: Run the full suite and inspect the create diff**

Run:

```bash
uv run pytest -q
git diff --check
git diff -- src/kb/core/create.py tests/test_write_pipeline_architecture.py tests/cli/test_create.py
```

Expected: the repository suite passes; create has no direct persistence orchestration and no unrelated behavior change.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/kb/core/create.py tests/test_write_pipeline_architecture.py
git commit -m "refactor(create): use shared write pipeline (CLI-13)"
```

---

### Task 5: Migrate and Strengthen `kb ingest`

**Historical execution record:** Complete in `42f8bfd`. The unchecked steps
below preserve the original TDD instructions; they are not pending work.

**Files:**
- Modify: `src/kb/core/ingest.py`
- Modify: `tests/test_write_pipeline_architecture.py`
- Modify: `tests/cli/test_ingest.py`

**Interfaces:**
- Consumes: Tasks 1–4 and existing ingest acquisition/normalization/about/allocation/naming/frontmatter behavior.
- Produces: ingest filing through the shared pipeline, with binary originals represented as ordered companions and mutable index/log updates using captured identities.

- [ ] **Step 1: Add failing ingest architecture and stale-index integration tests**

Append to `tests/test_write_pipeline_architecture.py`:

```python
def test_ingest_consumes_shared_write_pipeline() -> None:
    text = source("src/kb/core/ingest.py")
    assert "from kb.core.write_pipeline import" in text
    for forbidden in (
        "create_file_bytes(",
        "append_log(",
        "regenerate_directory_index(",
        "create_directory_index(",
        "def _new_directories(",
    ):
        assert forbidden not in text
```

Add to `tests/cli/test_ingest.py`:

```python
def test_ingest_stale_index_identity_is_typed_and_preserves_late_occupant(
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    index = initialized_kb / "raw/sources/index.md"
    late = b"late replacement index\n"
    real_overwrite = pipeline.overwrite_mutable_bytes

    def replace_before_overwrite(path, content, identity) -> None:
        if path == index:
            path.rename(path.with_name("old-index.md"))
            path.write_bytes(late)
        real_overwrite(path, content, identity)

    monkeypatch.setattr(
        pipeline,
        "overwrite_mutable_bytes",
        replace_before_overwrite,
    )
    result = ingest_file(invoke_ingest, initialized_kb, source)

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert index.read_bytes() == late
    assert " | ingested | " not in (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8")
```

In the existing
`test_append_only_file_creation_refuses_late_stub_and_original_occupants`,
replace:

```python
from kb.core import ingest as ingest_core
```

with:

```python
from kb.core import write_pipeline
```

and change its patch target from `ingest_core` to `write_pipeline`:

```python
monkeypatch.setattr(
    write_pipeline,
    "create_file_bytes",
    create_with_late_occupant,
    raising=False,
)
```

This preserves the regression at the new seam rather than leaving a patch
against deleted command-owned orchestration.

- [ ] **Step 2: Run the new tests to verify RED**

Run:

```bash
uv run pytest tests/test_write_pipeline_architecture.py::test_ingest_consumes_shared_write_pipeline tests/cli/test_ingest.py::test_ingest_stale_index_identity_is_typed_and_preserves_late_occupant -q
```

Expected: architecture fails because ingest owns persistence; the stale-index test cannot patch an ingest pipeline call.

- [ ] **Step 3: Replace ingest's context and malformed setup**

Import:

```python
from kb.core.write_pipeline import (
    AllocationBlocked,
    CompanionBirth,
    DocumentBirth,
    WriteFailure,
    WriteIntent,
    apply_write,
    load_write_context,
    prepare_write,
)
```

Replace direct root/config/scan initialization with the same shared context pattern as create, mapping `AllocationBlocked` to the existing `E_INGEST_MALFORMED` message. Preserve the current order: context loading and malformed guard precede `_surface()`, destination validation, and external acquisition.

- [ ] **Step 4: Replace ingest's write block with a typed companion intent**

After rendering the document, construct:

```python
original_relative = (
    original_path.relative_to(root).as_posix()
    if original_path is not None
    else None
)
companions = (
    [
        CompanionBirth(
            path=Path(original_relative),
            content=original_bytes,
        )
    ]
    if original_relative is not None and original_bytes is not None
    else []
)
intent = WriteIntent(
    birth=DocumentBirth(
        path=Path(relative),
        content=_document(frontmatter, body).encode("utf-8"),
        companions_before=companions,
    ),
    log_entry=LogEntry(
        at=timestamp,
        action="ingested",
        actor=request.actor,
        doc_ids=[doc_id],
        note=f"{relative} from {frontmatter.origin}",
    ),
)
try:
    prepared_write = prepare_write(context, intent)
    receipt = apply_write(prepared_write)
except WriteFailure as error:
    raise IngestFailure("E_INGEST_IO", str(error.cause), 2) from error
```

Delete `_new_directories()`, direct directory/index writes, direct `create_file_bytes`, direct `append_log`, and manual effects bookkeeping. Return `created=receipt.created`, `updated=receipt.updated`, and the unchanged `original=original_relative`.

- [ ] **Step 5: Run ingest-focused tests**

Run:

```bash
uv run pytest tests/test_write_pipeline_architecture.py tests/core/test_write_pipeline.py tests/cli/test_ingest.py -q
```

Expected: architecture and pipeline tests pass; ingest AC01–AC50 and all non-AC collision/race regressions pass, including stale-index protection.

- [ ] **Step 6: Run create plus ingest regression**

Run:

```bash
uv run pytest tests/cli/test_create.py tests/cli/test_ingest.py -q
git diff --check
```

Expected: both complete command suites pass with no whitespace errors.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/kb/core/ingest.py tests/test_write_pipeline_architecture.py tests/cli/test_ingest.py
git commit -m "refactor(ingest): use safe shared write pipeline (CLI-8)"
```

---

### Task 6: Enforce the Architecture and Complete Regression

**Historical execution record:** Complete in `944ce87`, `715b6d9`, and
`8df47e4`. The unchecked steps below preserve the original TDD instructions;
they are not pending work. The downstream input-seam inspection found a deeper
interface assumption, so its revalidation remains explicitly deferred.

**Files:**
- Modify: `tests/test_write_pipeline_architecture.py`
- Modify: `docs/superpowers/plans/2026-07-20-cli-core-input-seam.md` only if an exact file-path reference became stale; do not change its stable interfaces in this task.

**Interfaces:**
- Consumes: the completed naming and shared write-pipeline migrations.
- Produces: a durable regression guard and a verified prerequisite for the CLI/core input-seam plan.

- [ ] **Step 1: Replace string-only architecture checks with an AST integration guard**

Keep the focused tests from Tasks 4–5 and add:

```python
import ast


PERSISTENCE_CALLS = {
    "append_log",
    "create_directory_index",
    "create_file_bytes",
    "inspect_mutable_file",
    "overwrite_mutable_bytes",
    "regenerate_directory_index",
}


def imported_names(path: str) -> set[str]:
    tree = ast.parse(source(path), filename=path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def called_names(path: str) -> set[str]:
    tree = ast.parse(source(path), filename=path)
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_create_and_ingest_do_not_own_persistence_primitives() -> None:
    for path in ("src/kb/core/create.py", "src/kb/core/ingest.py"):
        assert not (imported_names(path) & PERSISTENCE_CALLS)
        assert not (called_names(path) & PERSISTENCE_CALLS)


def test_slug_has_one_definition_and_both_commands_import_it() -> None:
    definitions: list[str] = []
    for path in Path("src/kb/core").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "slug"
            for node in ast.walk(tree)
        ):
            definitions.append(path.as_posix())
    assert definitions == ["src/kb/core/naming.py"]
    for path in ("src/kb/core/create.py", "src/kb/core/ingest.py"):
        assert "from kb.core.naming import slug" in source(path)
```

- [ ] **Step 2: Run all focused prerequisite tests**

Run:

```bash
uv run pytest tests/core/test_naming.py tests/core/test_indexing.py tests/core/test_safeio.py tests/core/test_write_pipeline.py tests/test_write_pipeline_architecture.py -q
uv run pytest tests/cli/test_create.py tests/cli/test_ingest.py -q
```

Expected: all focused tests pass; create collects AC01–AC52 and ingest collects AC01–AC50 without gaps.

- [ ] **Step 3: Verify acceptance-criterion collection explicitly**

Run:

```bash
uv run pytest tests/cli/test_create.py --collect-only -q
uv run pytest tests/cli/test_ingest.py --collect-only -q
```

Expected: output includes exactly one `test_acNN_...` function for every create AC01–AC52 and ingest AC01–AC50; additional named regressions may also collect.

- [ ] **Step 4: Run full regression and static checks**

Run:

```bash
uv run pytest -q
git diff --check
rg -n "def slug|create_file_bytes\(|overwrite_mutable_bytes\(|append_log\(|regenerate_directory_index\(" src/kb/core/create.py src/kb/core/ingest.py
```

Expected: the complete repository suite passes; `git diff --check` is silent; `rg` returns no matches.

- [ ] **Step 5: Check the downstream input-seam plan for stale paths only**

Run:

```bash
rg -n "src/kb/core/(create|ingest|naming|write_pipeline)\.py|missing_directories|shared write pipeline" docs/superpowers/plans/2026-07-20-cli-core-input-seam.md
```

Expected: all referenced source paths exist after this extraction. If a path is stale, update only that path and state the reason in the commit; do not redesign the downstream plan here. Record any interface conflict for its own pre-flight review rather than silently changing it.

- [ ] **Step 6: Commit the architecture gate**

```bash
git add tests/test_write_pipeline_architecture.py
git commit -m "test(core): enforce shared write pipeline"
```

If Step 5 required a path-only correction, commit that documentation correction separately before the architecture commit:

```bash
git add docs/superpowers/plans/2026-07-20-cli-core-input-seam.md
git commit -m "docs: refresh input seam prerequisite paths"
```

- [ ] **Step 7: Inspect the completed branch**

Run:

```bash
git status --short
git log -6 --oneline
git diff --stat "$(git merge-base HEAD main)"..HEAD
```

Expected: tracked status is clean; unrelated user files remain untouched; the branch contains the naming, projected-index, pipeline, create migration, ingest migration, and architecture-test commits in that order.

---

### Task 7: Bind Context and Projected Index Reads to the Captured Root

**Executed scope:** Root configuration/scan acquisition and projected-index
metadata acquisition were moved behind short-lived rooted readers. Contexts
carry root identity without live descriptors, and every later stage reopens
and verifies the captured root.

- [x] Acquire configuration and Markdown scan inputs descriptor-relatively.
- [x] Acquire affected-index source and listing metadata without path fallback.
- [x] Reject root replacement and unsafe child kinds with typed provenance.
- [x] Verify focused and complete regressions (`bd4184b`, `b78c1e5`).

### Task 8: Reconcile Command Naming, Destination, and Architecture Contracts

**Executed scope:** Both commands reserve CLI-maintained `index.md`, ingest
rejects requested destination unsafe components before acquisition, and the
semantic architecture gate prevents command-owned persistence from returning.

- [x] Pin born-index naming and destination validation in command specs.
- [x] Preserve create supersession and ingest destination error envelopes.
- [x] Enforce direct-write and provenance restrictions with AST tests.
- [x] Verify focused and complete regressions (`5148b4a`..`b66a3be`).

### Task 9A: Make Allocation Lazy and Bind Born Directories by Identity

**Executed scope:** Ordinary and rooted scans share incremental frontmatter
prefix acquisition; born directories use held staging identity plus atomic
no-replace publication, and failed staging is retained as documented partial
state rather than removed through a racy pathname.

- [x] Keep valid Markdown bodies out of allocation snapshots.
- [x] Publish born directories exclusively and fail safely when unsupported.
- [x] Propagate each born identity to child/index/document writes and verify it
      before success.
- [x] Verify focused and complete regressions (`502b0ab`..`180cff4`).

### Task 9B: Close Command and Direct-Write Contract Gaps

**Executed scope:** Command validation ordering, raw-class destination shape,
exact supersession provenance, and the semantic direct-write gate were brought
into agreement with the normative command specs.

- [x] Reconcile create and ingest specifications before code.
- [x] Preserve exact command results for damaged or unsafe destinations.
- [x] Reject aliases, dynamic modes, file-object writes, and mutating
      filesystem calls in command modules.
- [x] Verify focused and complete regressions (`1f1cae1`..`c1e3028`).

### Task 10: Classify Destination Context Failures and Pre-render Logs

**Historical execution record:** Complete in `43063f5` and `62c6068`. The
unchecked steps below preserve the original TDD instructions; they are not
pending work.

**Files:**
- Modify: `docs/specs/commands/00-shared.md`
- Modify: `docs/specs/commands/kb-create.md`
- Modify: `docs/specs/commands/kb-ingest.md`
- Modify: `docs/superpowers/specs/2026-07-20-shared-write-pipeline-design.md`
- Modify: `docs/superpowers/plans/2026-07-20-shared-write-pipeline.md`
- Modify: `src/kb/core/ingest.py`
- Modify: `src/kb/core/write_pipeline.py`
- Modify focused pipeline/create/ingest tests.

**Interfaces:**
- Consumes: the completed rooted allocating snapshot, exact unsafe-path
  provenance on `WriteFailure`, the stable ingest/create envelopes, and the
  public staged write-pipeline interface.
- Produces: exact destination-component context classification and a privately
  prepared log row with no public interface change.

- [ ] **Step 1: Commit normative documentation before code**

Pin exact destination provenance, unchanged validation/acquisition order,
pre-mutation log formatting/encoding, typed preflight log failure, and
bytes-only application in the shared and command specs plus design/plan.

- [ ] **Step 2: Establish destination-provenance RED**

Add final and intermediate `.md`-named directory link/junction regressions in
plain and JSON forms as appropriate. Assert exact `E_INGEST_DEST_INVALID`, exit
2, no adapter call, and byte-stable KB/external input. Add an unrelated unsafe
Markdown context failure proving generic `E_INGEST_IO` and established
precedence.

- [ ] **Step 3: Implement comparison-only provenance mapping**

On the existing context exception path, safely parse destination parts without
raising. Compare the typed unsafe path with every lexical prefix from the raw
class directory through the destination. Reuse the exact destination failure
mapping. Add no filesystem access before normal destination validation.

- [ ] **Step 4: Establish and fix log-render RED**

Add direct pipeline coverage for private prepared bytes and a typed
preflight/render/log encoding failure, plus create surrogate-actor and ingest
surrogate-source/default-origin stable-envelope/no-mutation coverage. Format
and encode once during preparation, wrap expected formatter `TypeError` or
`ValueError` as an `EINVAL` `OSError` and encoding as an `EILSEQ` `OSError`,
store bytes privately, and make application use them exclusively. Preserve
successful bytes, existing/missing-log behavior, log-last order, and receipts.

- [ ] **Step 5: Verify and commit code/tests separately**

Run focused pipeline/create/ingest/architecture suites, explicit AC
collection, the full suite, and `git diff --check`. Do not modify Task 9A/9B or
the separate CLI/core input-seam plan, and do not dispatch a reviewer.

**Executed:** All five steps are complete in documentation commit `43063f5`
and implementation commit `62c6068`; 439 repository tests passed and the task
review was approved.

---

### Task 11: Harden Traversal, Index Metadata, and the Final Log Boundary

**Files:**
- Modify: `src/kb/core/safeio.py`
- Modify: `src/kb/core/write_pipeline.py`
- Modify: `src/kb/core/indexing.py`
- Modify focused safe-I/O, pipeline, and indexing tests.

- [x] **Step 1: Replace recursive rooted scan traversal**

Add a descriptor-created tree deeper than Python's recursion limit and prove
the operation never leaks `RecursionError`. Implement iterative traversal with
bounded live descriptors, descriptor-relative descent/ascent, identity
verification, deterministic lexical order, and no root-to-descendant quadratic
reopening.

- [x] **Step 2: Acquire projected child metadata by prefix**

Use `read_frontmatter_prefix()` for existing Markdown child metadata in both
the rooted pipeline and ordinary convenience acquisition paths. Preserve full
subdirectory `index.md` reads where the body heading is required, and pin the
behavior with a multi-megabyte-body regression.

- [x] **Step 3: Verify born directories immediately before logging**

Move final born-directory verification after all other non-log writes and
immediately before log creation/append. Pin that a verification failure leaves
log bytes unchanged and that no fallible pipeline operation follows logging.

- [x] **Step 4: Verify and commit code/tests separately from documentation**

Run focused safe-I/O/index/pipeline tests, create and ingest plus architecture
tests, explicit AC collection, deep-tree resource regressions, the full suite,
and `git diff --check`.

---

### Task 12: Pin the First-Open Born-Directory Binding Boundary

**Decision:** The user selected first-open binding after the platform review
established that `mkdirat` cannot atomically return a created-directory
descriptor on supported Darwin/Linux systems.

- [x] Document that staging-path creation does not authenticate creator
      provenance and that first no-follow open plus `fstat` binds identity.
- [x] Pin deterministic pre-binding real-directory and symlink substitutions.
- [x] Remove authoritative pre-open pathname `stat`; publish and verify only
      the identity acquired from the opened descriptor.
- [x] Verify focused, command, architecture, AC, and full regressions.
- [x] **Final-review correction:** reject any directory observed non-empty
      through the held descriptor at first-open binding, before final-name
      publication or pipeline writes; re-run all release gates.

---

### Task 13: Define Descriptor/Object Containment Under Post-Open Rename

**Decision:** The user accepts the portable POSIX limitation: a
non-cooperating actor that renames an already-open inode outside the lexical KB
root is outside the containment threat model. No lock, exclusive-writer model,
or public interface is added.

- [x] Scope the design and plan to descriptor/object containment and document
      post-open movement as possible no-rollback partial state.
- [x] Pin the exact post-open parent-rename interval with a typed-failure,
      replacement-stability, moved-object partial-bytes, and unchanged-log
      regression.
- [x] Verify focused, command, architecture, exact AC, full-suite, diff, and
      status gates.

---

### Task 14: Preserve Acquisition Provenance and Type Born-Index Failures

**Scope:** Close the two final typed-error/provenance findings without changing
the public staged interface, validation/acquisition order, or successful bytes.

- [x] Pin exact relative-path and safely acquired partial-prefix provenance for
      rooted tree acquisition failures, plus typed born-index render/encoding
      failures, in the design and plan.
- [ ] Preserve acquisition provenance through the internal safe-I/O seam and
      exact create/ingest command classifications.
- [ ] Wrap born-index formatting and UTF-8 encoding as exact typed preflight
      index failures before mutation.
- [ ] Verify focused, command, architecture, exact AC, full-suite, diff, and
      status gates.

---

## Implementation Completion Checklist

- [x] `slug()` is defined only in `src/kb/core/naming.py` and both commands import it.
- [x] `src/kb/core/write_pipeline.py` exposes the approved three-function staged interface.
- [x] Preparation captures mutable document, affected-index, and log identities before any writes.
- [x] Create performs lossless supersession transformation from `PreparedWrite.sources` before `apply_write()`.
- [x] Ingest binary originals are typed companions created before stubs.
- [x] Born indexes are exclusive and current; only the nearest pre-existing index is identity-overwritten.
- [x] Existing/missing log behavior and exact rows remain unchanged, with log last.
- [x] The log row is privately rendered and UTF-8 encoded during preparation;
      application consumes only prepared bytes and encoding failure is typed
      before mutation.
- [x] Ingest context failures map to destination-invalid only for an exact
      requested class/destination component, with no extra traversal.
- [x] Late occupants and changed identities are never overwritten or followed.
- [x] No rollback was added; documented partial-write behavior remains.
- [x] Receipts exactly preserve command `created`/`updated` output fields.
- [x] Create AC01–AC52 and ingest AC01–AC50 pass unchanged.
- [x] Architecture tests prevent command-owned persistence from returning.
- [x] Full repository tests and `git diff --check` pass through Task 10.
- [x] Task 11 iterative traversal, prefix-only projected child acquisition,
      and pre-log final verification are complete.
- [x] Task 12 first-open born-directory binding correction is implemented and
      verified; only an empty real directory may be accepted at binding and
      pathname replacements are detected at the available identity checks.
- [x] Task 13 descriptor/object containment scope and the accepted post-open
      namespace-movement limitation are documented and regression-tested.
- [ ] Task 14 partial acquisition provenance and born-index typed preflight
      envelopes are implemented and verified.
- [ ] Revalidate the downstream CLI/core input-seam plan after this branch is
      integrated. Its source paths exist, but its separate prepared models
      still contain stale `missing_directories` assumptions and are explicitly
      outside this extraction.
