# CLI/Core External-Input Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move external file, stdin, clipboard, and create-body acquisition out of `src/kb/core/` while preserving every observable `kb ingest` and `kb create` behavior.

**Architecture:** Core remains delivery-independent rather than side-effect-free: it owns KB discovery, scanning, validation, normalization, allocation, and KB filesystem mutation, but never reads process-global streams or launches processes. Command-specific core modules expose transient prepare/execute interfaces; CLI-owned adapters acquire explicit bytes between those phases, preserving the normative environment-before-acquisition error order. The Typer callbacks hide that choreography in private workflow functions, and an AST architecture test prevents the prohibited dependencies from returning.

**Tech Stack:** Python >=3.14, Typer, Pydantic 2.x, PyYAML, pytest, `uv`; no new runtime or development dependencies.

## Global Constraints

- **Blocked execution order:** first complete Tasks 4–7 of `docs/superpowers/plans/2026-07-16-kb-ingest.md` so AC24–AC50 pass; then land the separately reviewed shared create/ingest write-pipeline extraction required by `AGENTS.md`; only then execute this plan.
- Before Task 1, `uv run pytest tests/cli/test_ingest.py -q` must collect AC01–AC50 and pass every runnable test; only AC44 may skip under its declared platform condition.
- Before Task 1, `src/kb/core/create.py` and `src/kb/core/ingest.py` must already consume the shared write pipeline; this plan must preserve that internal seam rather than recreate command-specific write/index/log implementations.
- If either prerequisite changed a file name named below, update only the path references in this plan before execution; do not change the interfaces, ordering, or behavioral constraints established here.
- The PRD remains unchanged. Update `docs/specs/commands/kb-ingest.md` and `AGENTS.md` because the former currently places concrete adapters in core and the latter uses the ambiguous phrase “pure logic.”
- Commit the normative documentation change separately from implementation changes.
- `src/kb/core/` may perform KB filesystem I/O but contains no Typer, printing, `sys.exit`, `sys.stdin`, `sys.stdout`, `sys.stderr`, `subprocess`, `os.system`, `os.popen`, `os.spawn*`, `os.posix_spawn*`, or `os.exec*` use.
- External source paths are CLI acquisition concerns. Paths inside the discovered KB remain core concerns.
- The CLI behavior is fixed: preserve text output, JSON fields, streams, exit codes, error codes/messages, help text, file bytes/paths, warning behavior, validation order, and documented partial-write behavior.
- Preserve the current ordering: root discovery → config load → scan/malformed guard → command surface checks → external acquisition → byte interpretation and remaining command validation → write phase.
- Every data model introduced in core is a Pydantic 2.x `BaseModel`. Core plans are invocation-local opaque transport values; CLI code may relay them but must not inspect their fields.
- `AdapterPayload` carries raw bytes. Strict UTF-8 decoding, non-text classification, empty-input handling, and newline normalization stay in core.
- Keep command-specific failure contracts: CLI acquisition code raises `IngestFailure` or `CreateFailure`, and Typer callbacks retain one rendering/exit path per command.
- Do not introduce a generic external-input manager, runtime plugin loader, filesystem port, persistent index/cache, network call, Git call, or new top-level package.
- Use `uv run pytest`; CLI acceptance tests continue to use Typer's `CliRunner`, never a subprocess.
- Preserve unrelated user changes. At plan-writing time `.gitignore` is modified and `.claude/skills/*` is untracked; do not stage or edit them.

---

## File Structure

- Modify `AGENTS.md`: define core as delivery-independent, explicitly allow KB filesystem I/O, and assign process-environment acquisition to CLI adapters.
- Modify `docs/specs/commands/kb-ingest.md`: move the concrete adapter registry to the CLI seam and document the prepare → acquire → execute ordering and payload contract.
- Create `src/kb/cli/create_input.py`: acquire optional create body bytes from an external file or stdin and raise exact `CreateFailure` values.
- Create `src/kb/cli/ingest_adapters.py`: bind file/stdin/clipboard selections without I/O, then acquire a self-describing `AdapterPayload` through a private registry.
- Modify `src/kb/core/create.py`: remove `body_file` from `CreateRequest`, add `PreparedCreate`, and split the command into `prepare_create()` and `execute_create(prepared, body_data)`.
- Modify `src/kb/core/ingest.py`: remove concrete adapters and `source` from `IngestRequest`, add `IngestSourceShape`, self-describing `AdapterPayload`, `PreparedIngest`, and split into `prepare_ingest()` / `execute_ingest()`.
- Modify `src/kb/cli/create.py`: keep the Typer callback thin with a private workflow function that acquires body bytes between core preparation and execution.
- Modify `src/kb/cli/ingest.py`: keep the Typer callback thin with a private workflow function that binds a source without I/O, prepares core state, acquires bytes, then executes.
- Create `tests/cli/test_create_input.py`: direct external-file/stdin acquisition and exact-error tests.
- Create `tests/cli/test_ingest_adapters.py`: binding-without-I/O, payload metadata, file/stdin, and clipboard adapter tests.
- Create `tests/core/test_create_command.py`: direct tests of the explicit prepared create interface and error precedence.
- Create `tests/core/test_ingest_command.py`: direct tests of source-shape validation, explicit payload execution, and mismatched payload rejection.
- Create `tests/test_core_architecture.py`: AST-based examples plus a repository-wide core integration guard.
- Modify `tests/cli/test_create.py`: add paired-failure regression coverage without changing AC01–AC52.
- Modify `tests/cli/test_ingest.py`: add paired-failure regression coverage without changing AC01–AC50.

## Stable Interfaces

```python
# src/kb/core/ingest.py
SourceKind = Literal["file", "stdin", "clipboard"]

class IngestSourceShape(BaseModel):
    source_kind: SourceKind
    locator_present: bool

class AdapterPayload(BaseModel):
    source_kind: SourceKind
    data: bytes
    default_origin: str
    source_filename: str | None = None

class IngestRequest(BaseModel):
    raw_class: RawClass
    dest: str | None = None
    about: str | None = None
    title: str | None = None
    origin: str | None = None
    actor: str = "kb-cli"
    kb_root: Path | None = None

class PreparedIngest(BaseModel):
    request: IngestRequest
    source_shape: IngestSourceShape
    root: Path
    config: Config
    kb: KB
    target_dir: Path
    missing_directories: list[Path]

def prepare_ingest(
    request: IngestRequest,
    source_shape: IngestSourceShape,
) -> PreparedIngest

def execute_ingest(
    prepared: PreparedIngest,
    payload: AdapterPayload,
) -> IngestResult
```

```python
# src/kb/cli/ingest_adapters.py
class BoundIngestSource:
    @property
    def shape(self) -> IngestSourceShape
    def acquire(self) -> AdapterPayload

def bind_ingest_source(
    source_kind: SourceKind,
    source: str | None,
) -> BoundIngestSource
```

`bind_ingest_source()` performs no filesystem access, stream read, platform lookup, PATH lookup, or process execution. All such work happens in `BoundIngestSource.acquire()`.

```python
# src/kb/core/create.py
class CreateRequest(BaseModel):
    type_name: str
    title: str
    description: str
    derived_from: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    status: CreateStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    instructions: str | None = None
    dest: str | None = None
    actor: str = "kb-cli"
    kb_root: Path | None = None

class PreparedCreate(BaseModel):
    request: CreateRequest
    root: Path
    config: Config
    kb: KB
    target_dir: Path
    missing_directories: list[Path]
    tags: list[str]
    warnings: list[str]

def prepare_create(request: CreateRequest) -> PreparedCreate

def execute_create(
    prepared: PreparedCreate,
    body_data: bytes | None,
) -> CreateResult
```

```python
# src/kb/cli/create_input.py
def acquire_create_body(
    body_file: str | None,
    *,
    stdin: BinaryIO | TextIO | None = None,
) -> bytes | None
```

The optional `stdin` argument is an internal test seam. Production callers omit it; the adapter reads `sys.stdin` only when `body_file == "-"`.

```python
# src/kb/cli/create.py
def _run_create(request: CreateRequest, body_file: str | None) -> CreateResult

# src/kb/cli/ingest.py
def _run_ingest(
    request: IngestRequest,
    source_kind: SourceKind,
    source: str | None,
) -> IngestResult
```

---

### Task 1: Correct the Normative Seam Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/specs/commands/kb-ingest.md`

**Interfaces:**
- Consumes: the PRD CLI-8 behavior and current ingest/create command specifications.
- Produces: the normative delivery-independent core rule and the exact adapter/payload lifecycle implemented by Tasks 2–4.

- [ ] **Step 1: Edit the package and layering wording in `AGENTS.md`**

Replace the current `core/` and `cli/` descriptions and layering paragraph with wording that contains these exact requirements:

```markdown
│   ├── core/             deterministic KB application logic: scan, query, graph, validate, ids, ingest, models, …
│   └── cli/              Typer commands, renderers, and process-environment input adapters

Layering rule: `core/` is delivery-independent application logic. It may read and write the discovered KB filesystem, but it contains no Typer, printing, process exit, process-global standard-stream access, or process-launching calls. Concrete acquisition of user-supplied external files, stdin, and clipboard contents belongs to adapters in `cli/`; those adapters pass explicit bytes and provenance metadata through core-owned Pydantic models. Typer callbacks parse arguments, orchestrate prepare → acquire → execute, render output, and map failures to exit codes. This layering rule is normative; the module breakdown inside each layer is a developer decision.
```

- [ ] **Step 2: Replace ingest §4.1 with the CLI-owned adapter contract**

Keep the normative file/stdin/clipboard behavior unchanged and replace only the internal placement/interface text with:

````markdown
### 4.1 Adapter registry (internal contract)

Concrete adapters live at the CLI seam and register in a private table so later adapters (Slack, mail, ticketing — Phase 4) are additive. Binding a source selection performs no I/O. Core preparation runs first; only then does the bound adapter acquire bytes:

```python
class IngestSourceShape(BaseModel):
    source_kind: Literal["file", "stdin", "clipboard"]
    locator_present: bool

class AdapterPayload(BaseModel):
    source_kind: Literal["file", "stdin", "clipboard"]
    data: bytes
    default_origin: str
    source_filename: str | None = None

class BoundIngestSource(NamedTuple):
    shape: IngestSourceShape
    acquire: Callable[[], AdapterPayload]
```

`IngestSourceShape` contains no source path and lets core validate the command surface after root/config/scan checks but before acquisition. Adapters only acquire bytes and provenance. Strict decoding, classification, normalization, naming, allocation, and filing remain uniform core behavior. The payload is self-describing; core execution rejects a payload whose `source_kind` differs from the prepared source shape.
````

In §4, retain steps 1–3 as core preparation, label step 4 as CLI-adapter acquisition, and state that steps 5–15 resume core execution. Do not reorder or rewrite any error, output, or filesystem requirement.

- [ ] **Step 3: Verify the documentation diff does not change user behavior**

Run:

```bash
git diff --check -- AGENTS.md docs/specs/commands/kb-ingest.md
git diff --word-diff=plain -- docs/specs/commands/kb-ingest.md
```

Expected: no whitespace errors; changes are limited to adapter placement, payload/interface wording, and phase ownership. CLI syntax, help, AC01–AC50, E1–E16, and PRD text are unchanged.

- [ ] **Step 4: Commit the normative documentation separately**

```bash
git add AGENTS.md docs/specs/commands/kb-ingest.md
git commit -m "docs(ingest): define CLI acquisition seam (CLI-8)"
```

Expected: the commit contains exactly the two documentation files.

---

### Task 2: Move Create Body Acquisition to the CLI Seam

**Files:**
- Create: `src/kb/cli/create_input.py`
- Modify: `src/kb/core/create.py`
- Modify: `src/kb/cli/create.py`
- Create: `tests/cli/test_create_input.py`
- Create: `tests/core/test_create_command.py`
- Modify: `tests/cli/test_create.py`

**Interfaces:**
- Consumes: the prerequisite shared write pipeline and existing `CreateFailure`, `CreateResult`, and create write behavior.
- Produces: `acquire_create_body()`, `PreparedCreate`, `prepare_create()`, and `execute_create()` with explicit `bytes | None` input.

- [ ] **Step 1: Write direct failing acquisition tests**

Create `tests/cli/test_create_input.py` with these cases:

```python
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from kb.cli.create_input import acquire_create_body
from kb.core.create import CreateFailure


def test_omitted_body_returns_none_without_reading_stdin() -> None:
    class ExplodingStream:
        def read(self) -> bytes:
            raise AssertionError("stdin must not be read")

    assert acquire_create_body(None, stdin=ExplodingStream()) is None


def test_dash_reads_explicit_stdin_as_bytes() -> None:
    assert acquire_create_body("-", stdin=BytesIO(b"body\r\n")) == b"body\r\n"


def test_external_body_file_is_read_byte_identically(tmp_path: Path) -> None:
    path = tmp_path / "body.md"
    path.write_bytes(b"\xffbody\r\n")
    assert acquire_create_body(str(path)) == b"\xffbody\r\n"


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_unavailable_body_raises_exact_create_failure(
    tmp_path: Path,
    kind: str,
) -> None:
    path = tmp_path / "body.md"
    if kind == "directory":
        path.mkdir()
    with pytest.raises(CreateFailure) as raised:
        acquire_create_body(str(path))
    assert raised.value.code == "E_CREATE_BODY_NOT_FOUND"
    assert raised.value.exit_code == 2
    assert raised.value.message.startswith(f"body file is unavailable: {path}:")
```

- [ ] **Step 2: Run the acquisition tests and verify the module is absent**

Run:

```bash
uv run pytest tests/cli/test_create_input.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'kb.cli.create_input'`.

- [ ] **Step 3: Implement create-body acquisition without decoding**

Create `src/kb/cli/create_input.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from kb.core.create import CreateFailure


def acquire_create_body(
    body_file: str | None,
    *,
    stdin: BinaryIO | TextIO | None = None,
) -> bytes | None:
    if body_file is None:
        return None
    if body_file == "-":
        stream = stdin if stdin is not None else getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        return data.encode("utf-8") if isinstance(data, str) else data
    path = Path(body_file).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        return resolved.read_bytes()
    except OSError as error:
        raise CreateFailure(
            "E_CREATE_BODY_NOT_FOUND",
            f"body file is unavailable: {body_file}: {error}",
            2,
        ) from error
```

- [ ] **Step 4: Run the acquisition tests**

Run:

```bash
uv run pytest tests/cli/test_create_input.py -q
```

Expected: all five parameterized cases pass.

- [ ] **Step 5: Write failing core-interface and error-precedence tests**

Create `tests/core/test_create_command.py` by reusing `make_kb`, `make_doc`, and the canonical create arguments from `tests/cli/test_create.py`. Add these exact assertions:

```python
from pathlib import Path

import pytest

from kb.core.create import (
    CreateFailure,
    CreateRequest,
    execute_create,
    prepare_create,
)


def add_chat(root: Path) -> None:
    path = root / "raw/chats/planning.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: CHAT-000001\n"
        "type: chat\n"
        "ingested_at: 2026-07-16T09:00:00Z\n"
        "origin: stdin\n"
        "title: Planning\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )


def request(root: Path) -> CreateRequest:
    return CreateRequest(
        type_name="spec",
        title="Explicit body",
        description="Exercises explicit body bytes.",
        derived_from=["CHAT-000001"],
        kb_root=root,
    )


def test_prepare_then_execute_accepts_explicit_body_bytes(initialized_kb: Path) -> None:
    add_chat(initialized_kb)
    prepared = prepare_create(request(initialized_kb))
    result = execute_create(prepared, b"body\r\n")
    assert result.id == "KB-000001"
    assert (initialized_kb / result.path).read_bytes().endswith(b"---\nbody\n")


def test_execute_create_keeps_strict_utf8_in_core(initialized_kb: Path) -> None:
    add_chat(initialized_kb)
    prepared = prepare_create(request(initialized_kb))
    with pytest.raises(CreateFailure) as raised:
        execute_create(prepared, b"\xff")
    assert (raised.value.code, raised.value.exit_code) == (
        "E_CREATE_BODY_NOT_TEXT",
        1,
    )
```

In `tests/cli/test_create.py`, add a non-AC regression test proving preparation precedes acquisition:

```python
def test_environment_failure_precedes_missing_external_body(
    tmp_path: Path,
    invoke_create,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    result = invoke_create(
        outside,
        "--type",
        "spec",
        "--title",
        "Ordering",
        "--description",
        "Environment errors win.",
        "--derived-from",
        "CHAT-000001",
        "--body-file",
        str(tmp_path / "missing.md"),
    )
    assert result.exit_code == 2
    assert "E_NO_KB" in result.output
    assert "E_CREATE_BODY_NOT_FOUND" not in result.output
```

- [ ] **Step 6: Run the new tests and verify the old core interface fails them**

Run:

```bash
uv run pytest tests/core/test_create_command.py tests/cli/test_create.py::test_environment_failure_precedes_missing_external_body -q
```

Expected: collection fails because `prepare_create` and `execute_create` do not exist.

- [ ] **Step 7: Split core creation into preparation and execution**

In `src/kb/core/create.py`:

1. Remove `import sys`.
2. Remove `body_file` from `CreateRequest`.
3. Add `PreparedCreate` using the exact stable interface above. Its fields are core implementation state; CLI callers only relay the model to `execute_create()`.
4. Replace `_body(request: CreateRequest)` with this byte interpreter:

```python
def _body(data: bytes | None) -> str:
    if data is None:
        return ""
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CreateFailure(
            "E_CREATE_BODY_NOT_TEXT",
            "body is not UTF-8 text",
            1,
        ) from error
    if not decoded.strip():
        return ""
    return decoded.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
```

5. Make `prepare_create(request)` perform exactly the existing root discovery, config load, scan, malformed guard, destination preparation, stable tag de-duplication, reserved-type check, and warning calculation. Return those values in `PreparedCreate` without reading body input, resolving parents, allocating an id, or writing.
6. Rename the remaining operation to `execute_create(prepared, body_data)`. Start it with:

```python
def execute_create(
    prepared: PreparedCreate,
    body_data: bytes | None,
) -> CreateResult:
    request = prepared.request
    root = prepared.root
    config = prepared.config
    kb = prepared.kb
    target_dir = prepared.target_dir
    missing_directories = prepared.missing_directories
    tags = prepared.tags
    warnings = prepared.warnings
    body = _body(body_data)
```

Continue with the existing parent resolution, supersession, allocation, naming, frontmatter construction, shared-pipeline commit, and result construction in their existing order. Do not copy root/config/scan/destination/index/log behavior out of the prerequisite shared pipeline.

- [ ] **Step 8: Hide prepare → acquire → execute behind a private CLI workflow**

In `src/kb/cli/create.py`, import `acquire_create_body`, `CreateResult`, `prepare_create`, and `execute_create`. Keep the existing `CreateFailure` and `CreateRequest` imports. Add this function above `create_command`:

```python
def _run_create(
    request: CreateRequest,
    body_file: str | None,
) -> CreateResult:
    prepared = prepare_create(request)
    body_data = acquire_create_body(body_file)
    return execute_create(prepared, body_data)
```

Replace the current core call inside the existing `try` block with:

```python
request = CreateRequest(
    type_name=type_name,
    title=title,
    description=description,
    derived_from=derived_from or [],
    supersedes=supersedes,
    status=status,
    tags=tags or [],
    instructions=instructions,
    dest=dest,
    actor=actor,
    kb_root=kb_root,
)
result = _run_create(request, body_file)
```

Do not change the `except`, warning rendering, success rendering, Typer annotations, help text, or examples.

- [ ] **Step 9: Run focused and complete create tests**

Run:

```bash
uv run pytest tests/cli/test_create_input.py tests/core/test_create_command.py tests/cli/test_create.py -q
```

Expected: acquisition tests, direct core tests, AC01–AC52, and the additional precedence regression all pass.

- [ ] **Step 10: Commit the create seam**

```bash
git add src/kb/cli/create_input.py src/kb/core/create.py src/kb/cli/create.py tests/cli/test_create_input.py tests/core/test_create_command.py tests/cli/test_create.py
git commit -m "refactor(create): inject acquired body bytes (CLI-13)"
```

Expected: the commit contains only create acquisition/core/CLI/test changes.

---

### Task 3: Move Ingest Adapters to the CLI Seam

**Files:**
- Create: `src/kb/cli/ingest_adapters.py`
- Modify: `src/kb/core/ingest.py`
- Modify: `src/kb/cli/ingest.py`
- Create: `tests/cli/test_ingest_adapters.py`
- Create: `tests/core/test_ingest_command.py`
- Modify: `tests/cli/test_ingest.py`

**Interfaces:**
- Consumes: `IngestFailure`, `IngestResult`, the prerequisite shared pipeline, and the completed AC01–AC50 ingest behavior.
- Produces: `IngestSourceShape`, self-describing `AdapterPayload`, `BoundIngestSource`, `bind_ingest_source()`, `PreparedIngest`, `prepare_ingest()`, and `execute_ingest()`.

- [ ] **Step 1: Write failing adapter tests**

Create `tests/cli/test_ingest_adapters.py`:

```python
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

import kb.cli.ingest_adapters as adapters
from kb.core.ingest import IngestFailure


def test_bind_is_inert_and_reports_only_source_shape(monkeypatch) -> None:
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(
        AssertionError("bind must not read a file")
    ))
    bound = adapters.bind_ingest_source("file", "/missing/source.md")
    assert bound.shape.source_kind == "file"
    assert bound.shape.locator_present is True


def test_file_adapter_preserves_bytes_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "Report.PDF"
    source.write_bytes(b"\xff\x00report")
    payload = adapters.bind_ingest_source("file", str(source)).acquire()
    assert payload.source_kind == "file"
    assert payload.data == b"\xff\x00report"
    assert payload.default_origin == str(source.resolve())
    assert payload.source_filename == "Report.PDF"


def test_stdin_adapter_preserves_bytes(monkeypatch) -> None:
    monkeypatch.setattr(adapters, "_stdin_stream", lambda: BytesIO(b"chat\r\n"))
    payload = adapters.bind_ingest_source("stdin", None).acquire()
    assert payload.model_dump() == {
        "source_kind": "stdin",
        "data": b"chat\r\n",
        "default_origin": "stdin",
        "source_filename": None,
    }


def test_clipboard_adapter_reports_nonzero_exit(monkeypatch) -> None:
    class Completed:
        returncode = 9
        stdout = b""
        stderr = b"clipboard unavailable"

    monkeypatch.setattr(adapters.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(adapters.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(adapters.subprocess, "run", lambda *args, **kwargs: Completed())
    with pytest.raises(IngestFailure) as raised:
        adapters.bind_ingest_source("clipboard", None).acquire()
    assert (raised.value.code, raised.value.exit_code) == (
        "E_INGEST_CLIPBOARD",
        2,
    )
    assert raised.value.message == "clipboard tool exited 9: clipboard unavailable"
```

- [ ] **Step 2: Run the adapter tests and verify the module is absent**

Run:

```bash
uv run pytest tests/cli/test_ingest_adapters.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'kb.cli.ingest_adapters'`.

- [ ] **Step 3: Implement inert binding and the private concrete registry**

Create `src/kb/cli/ingest_adapters.py`. Move the existing file/stdin/clipboard acquisition implementations from `src/kb/core/ingest.py` without changing their stable error codes/messages. Use this public shape:

```python
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from kb.core.ingest import (
    AdapterPayload,
    IngestFailure,
    IngestSourceShape,
    SourceKind,
)

Adapter = Callable[[str | None], AdapterPayload]


def _stdin_stream():
    return getattr(sys.stdin, "buffer", sys.stdin)


class BoundIngestSource:
    def __init__(self, source_kind: SourceKind, source: str | None) -> None:
        self._source_kind = source_kind
        self._source = source

    @property
    def shape(self) -> IngestSourceShape:
        return IngestSourceShape(
            source_kind=self._source_kind,
            locator_present=self._source is not None,
        )

    def acquire(self) -> AdapterPayload:
        return ADAPTERS[self._source_kind](self._source)


def bind_ingest_source(
    source_kind: SourceKind,
    source: str | None,
) -> BoundIngestSource:
    return BoundIngestSource(source_kind, source)
```

Each moved adapter must populate `source_kind` explicitly. The stdin adapter calls `_stdin_stream()`. The clipboard adapter must keep `shell=False` by passing the existing argument-vector list directly to `subprocess.run`; do not use a shell command string.

- [ ] **Step 4: Run the adapter tests**

Run:

```bash
uv run pytest tests/cli/test_ingest_adapters.py -q
```

Expected: all adapter tests pass.

- [ ] **Step 5: Write failing core-interface and precedence tests**

Create `tests/core/test_ingest_command.py` with a valid initialized KB fixture and these assertions:

```python
from pathlib import Path

import pytest

from kb.core.ingest import (
    AdapterPayload,
    IngestFailure,
    IngestRequest,
    IngestSourceShape,
    execute_ingest,
    prepare_ingest,
)
from kb.core.model import RawClass


def request(root: Path) -> IngestRequest:
    return IngestRequest(raw_class=RawClass.CHAT, kb_root=root)


def test_prepare_then_execute_accepts_explicit_payload(initialized_kb: Path) -> None:
    prepared = prepare_ingest(
        request(initialized_kb),
        IngestSourceShape(source_kind="stdin", locator_present=False),
    )
    result = execute_ingest(
        prepared,
        AdapterPayload(
            source_kind="stdin",
            data=b"chat\r\n",
            default_origin="stdin",
        ),
    )
    assert result.id == "CHAT-000001"
    assert (initialized_kb / result.path).read_bytes().endswith(b"---\nchat\n")


@pytest.mark.parametrize(
    ("source_kind", "locator_present", "message"),
    [
        ("file", False, "SOURCE is required with --from file"),
        ("stdin", True, "SOURCE is forbidden with --from stdin"),
        ("clipboard", True, "SOURCE is forbidden with --from clipboard"),
    ],
)
def test_prepare_validates_source_shape_before_acquisition(
    initialized_kb: Path,
    source_kind: str,
    locator_present: bool,
    message: str,
) -> None:
    with pytest.raises(IngestFailure) as raised:
        prepare_ingest(
            request(initialized_kb),
            IngestSourceShape(
                source_kind=source_kind,
                locator_present=locator_present,
            ),
        )
    assert (raised.value.code, raised.value.message, raised.value.exit_code) == (
        "E_INGEST_USAGE",
        message,
        2,
    )


def test_execute_rejects_payload_for_another_prepared_source(
    initialized_kb: Path,
) -> None:
    prepared = prepare_ingest(
        request(initialized_kb),
        IngestSourceShape(source_kind="stdin", locator_present=False),
    )
    with pytest.raises(ValueError, match="payload source kind does not match prepared ingest"):
        execute_ingest(
            prepared,
            AdapterPayload(
                source_kind="clipboard",
                data=b"chat\n",
                default_origin="clipboard",
            ),
        )
```

In `tests/cli/test_ingest.py`, add this non-AC regression test:

```python
def test_environment_failure_precedes_missing_external_source(
    tmp_path: Path,
    invoke_ingest,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    result = invoke_ingest(
        outside,
        "--class",
        "source",
        "--from",
        "file",
        str(tmp_path / "missing.md"),
    )
    assert result.exit_code == 2
    assert "E_NO_KB" in result.output
    assert "E_INGEST_SOURCE_NOT_FOUND" not in result.output
```

- [ ] **Step 6: Run the new tests and verify the old core interface fails them**

Run:

```bash
uv run pytest tests/core/test_ingest_command.py tests/cli/test_ingest.py::test_environment_failure_precedes_missing_external_source -q
```

Expected: collection fails because `IngestSourceShape`, `prepare_ingest`, and `execute_ingest` do not exist.

- [ ] **Step 7: Split core ingest into preparation and execution**

In `src/kb/core/ingest.py`:

1. Remove `platform`, `shutil`, `subprocess`, and `sys` imports.
2. Delete `_file_adapter`, `_stdin_adapter`, `_clipboard_adapter`, `Adapter`, and `ADAPTERS`.
3. Add `SourceKind`, `IngestSourceShape`, and the `source_kind` field on `AdapterPayload` exactly as defined under Stable Interfaces.
4. Remove `source_kind` and `source` from `IngestRequest`.
5. Change surface validation to accept `IngestSourceShape` and use `locator_present`; keep source-pairing validation before `about` and destination validation.
6. Add `PreparedIngest` using the exact stable interface above. Its fields are core implementation state; CLI callers only relay the model to `execute_ingest()`.
7. Make `prepare_ingest(request, source_shape)` perform root discovery, config loading, scan/malformed guard, source/about/destination surface validation, and destination preparation. It must return before reading or interpreting payload bytes.
8. Start `execute_ingest` with this invariant and unpacking:

```python
def execute_ingest(
    prepared: PreparedIngest,
    payload: AdapterPayload,
) -> IngestResult:
    if payload.source_kind != prepared.source_shape.source_kind:
        raise ValueError("payload source kind does not match prepared ingest")
    request = prepared.request
    root = prepared.root
    config = prepared.config
    kb = prepared.kb
    target_dir = prepared.target_dir
    missing_directories = prepared.missing_directories
    body = _normalized_text(payload, payload.source_kind)
```

Continue with existing `about` resolution, id allocation, naming, text/non-text handling, frontmatter construction, shared-pipeline commit, and result construction. Replace every policy check formerly reading `request.source_kind` with `payload.source_kind`. Do not duplicate the prerequisite shared write pipeline.

- [ ] **Step 8: Hide inert bind → prepare → acquire → execute behind a private CLI workflow**

In `src/kb/cli/ingest.py`, import `bind_ingest_source`, `IngestResult`, `SourceKind`, `prepare_ingest`, and `execute_ingest`. Keep the existing `IngestFailure` and `IngestRequest` imports. Add this function above `ingest_command`:

```python
def _run_ingest(
    request: IngestRequest,
    source_kind: SourceKind,
    source: str | None,
) -> IngestResult:
    bound_source = bind_ingest_source(source_kind, source)
    prepared = prepare_ingest(request, bound_source.shape)
    payload = bound_source.acquire()
    return execute_ingest(prepared, payload)
```

Replace the current core call inside the existing `try` block with:

```python
request = IngestRequest(
    raw_class=raw_class,
    dest=dest,
    about=about,
    title=title,
    origin=origin,
    actor=actor,
    kb_root=kb_root,
)
result = _run_ingest(request, source_kind, source)
```

Do not change the `except`, success renderer, option types, help text, or examples.

- [ ] **Step 9: Run focused and complete ingest tests**

Run:

```bash
uv run pytest tests/cli/test_ingest_adapters.py tests/core/test_ingest_command.py tests/cli/test_ingest.py -q
```

Expected: adapter tests, direct core tests, AC01–AC50, and the additional precedence regression all pass; only AC44 may skip under its declared condition.

- [ ] **Step 10: Commit the ingest seam**

```bash
git add src/kb/cli/ingest_adapters.py src/kb/core/ingest.py src/kb/cli/ingest.py tests/cli/test_ingest_adapters.py tests/core/test_ingest_command.py tests/cli/test_ingest.py
git commit -m "refactor(ingest): move acquisition adapters to CLI seam (CLI-8)"
```

Expected: the commit contains only ingest adapter/core/CLI/test changes.

---

### Task 4: Enforce the Core Architecture and Run Full Regression

**Files:**
- Create: `tests/test_core_architecture.py`

**Interfaces:**
- Consumes: the completed create and ingest seams from Tasks 2–3.
- Produces: a repository-wide guard against delivery/process dependencies under `src/kb/core/`.

- [ ] **Step 1: Write scanner examples and the repository integration test**

Create `tests/test_core_architecture.py` with an AST scanner that resolves import aliases. Its public test-local interface is:

```python
def violations(path: Path, source: str) -> list[str]
```

Add table-driven examples that require these results:

```python
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import typer\n", ["forbidden import: typer"]),
        ("import subprocess as sp\nsp.run(['x'])\n", ["forbidden import: subprocess"]),
        ("from sys import stdin as stream\nstream.read()\n", ["forbidden process global: sys.stdin"]),
        ("import sys as runtime\nruntime.stdout.write('x')\n", ["forbidden process global: sys.stdout"]),
        ("print('x')\n", ["forbidden output call: print"]),
        ("import os\nos.posix_spawn('/x', ['/x'], {})\n", ["forbidden process launch: os.posix_spawn"]),
        ("from os import execv as replace\nreplace('/x', ['/x'])\n", ["forbidden process launch: os.execv"]),
    ],
)
def test_scanner_detects_aliases(source: str, expected: list[str]) -> None:
    assert violations(Path("example.py"), source) == expected


def test_core_contains_no_delivery_or_process_dependencies() -> None:
    root = Path(__file__).parents[1] / "src" / "kb" / "core"
    found = [
        f"{path.relative_to(root)}: {item}"
        for path in sorted(root.rglob("*.py"))
        for item in violations(path, path.read_text(encoding="utf-8"))
    ]
    assert found == []
```

The scanner must report:

- imports whose top-level module is `typer` or `subprocess`;
- imported or attributed `sys.stdin`, `sys.stdout`, `sys.stderr`, or `sys.exit`;
- direct `print("text")` and `builtins.print("text")` calls;
- `os.system`, `os.popen`, and any `os` member beginning `spawn`, `posix_spawn`, or `exec`;
- `raise SystemExit` and `raise SystemExit("message")`.

Ordinary `os.open`, `os.fdopen`, `pathlib.Path`, and KB filesystem calls must not be reported.

- [ ] **Step 2: Run scanner examples before implementing the scanner**

Run:

```bash
uv run pytest tests/test_core_architecture.py -q
```

Expected: examples fail until alias resolution and forbidden-call classification are implemented; the repository integration case must pass after Tasks 2–3 and must not report `safeio.py` or `housekeeping.py` filesystem calls.

- [ ] **Step 3: Implement the AST scanner inside the test module**

Place this implementation above the tests in `tests/test_core_architecture.py`. It resolves import aliases, sorts and de-duplicates findings, and deliberately allows ordinary filesystem calls:

```python
from __future__ import annotations

import ast
from pathlib import Path

import pytest


FORBIDDEN_IMPORT_ROOTS = {"typer", "subprocess"}
FORBIDDEN_SYS_MEMBERS = {"stdin", "stdout", "stderr", "exit"}
FORBIDDEN_OS_EXACT = {"system", "popen"}


def forbidden_os_member(member: str) -> bool:
    return member in FORBIDDEN_OS_EXACT or member.startswith(
        ("spawn", "posix_spawn", "exec")
    )


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                local = item.asname or item.name.split(".", 1)[0]
                aliases[local] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for item in node.names:
                if item.name == "*":
                    continue
                local = item.asname or item.name
                aliases[local] = f"{node.module}.{item.name}"
    return aliases


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value, aliases)
        return None if owner is None else f"{owner}.{node.attr}"
    return None


def violations(path: Path, source: str) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    aliases = _import_aliases(tree)
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    found.add(f"forbidden import: {root}")
            continue

        if isinstance(node, ast.ImportFrom) and node.module is not None:
            root = node.module.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                found.add(f"forbidden import: {root}")
            continue

        qualified = _qualified_name(node, aliases)
        if qualified is not None:
            parts = qualified.split(".")
            if len(parts) >= 2 and parts[0] == "sys" and parts[1] in FORBIDDEN_SYS_MEMBERS:
                found.add(f"forbidden process global: sys.{parts[1]}")

        if isinstance(node, ast.Call):
            called = _qualified_name(node.func, aliases)
            if called in {"print", "builtins.print"}:
                found.add("forbidden output call: print")
            if called is not None:
                parts = called.split(".")
                if len(parts) == 2 and parts[0] == "os" and forbidden_os_member(parts[1]):
                    found.add(f"forbidden process launch: {called}")

        if isinstance(node, ast.Raise) and node.exc is not None:
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if _qualified_name(raised, aliases) in {"SystemExit", "builtins.SystemExit"}:
                found.add("forbidden process exit: SystemExit")

    return sorted(found)
```

Avoid duplicate reports when a forbidden imported module is also called: `import subprocess; subprocess.run(["x"])` reports the import once.

- [ ] **Step 4: Run the architecture test**

Run:

```bash
uv run pytest tests/test_core_architecture.py -q
```

Expected: all scanner examples and the real-core integration test pass.

- [ ] **Step 5: Run command regressions and the full suite**

Run:

```bash
uv run pytest tests/cli/test_create_input.py tests/core/test_create_command.py tests/cli/test_create.py -q
uv run pytest tests/cli/test_ingest_adapters.py tests/core/test_ingest_command.py tests/cli/test_ingest.py -q
uv run pytest -q
git diff --check
```

Expected: create AC01–AC52 pass; ingest AC01–AC50 pass except the declared AC44 platform skip; architecture tests pass; the complete repository suite passes; no whitespace errors are reported.

- [ ] **Step 6: Verify prohibited calls and dependency direction directly**

Run:

```bash
rg -n "(^|[.( ])(print|sys\\.(stdin|stdout|stderr|exit)|subprocess\\.|os\\.(system|popen|spawn|posix_spawn|exec))" src/kb/core
rg -n "from kb\\.cli|import kb\\.cli" src/kb/core
```

Expected: both commands produce no matches. `src/kb/cli/ingest_adapters.py` contains the clipboard subprocess implementation, and `src/kb/cli/create_input.py` contains the create stdin access.

- [ ] **Step 7: Commit the architecture guard**

```bash
git add tests/test_core_architecture.py
git commit -m "test(core): enforce delivery-independent modules"
```

Expected: the commit contains only the architecture test.

---

## Final Verification Checklist

- [ ] `git log -4 --oneline` shows a documentation commit, create seam commit, ingest seam commit, and architecture-test commit in that order.
- [ ] `uv run pytest -q` passes the full suite.
- [ ] `uv run pytest tests/cli/test_ingest.py --collect-only -q` includes AC01 through AC50 with no gaps.
- [ ] `uv run pytest tests/cli/test_create.py --collect-only -q` includes AC01 through AC52 with no gaps.
- [ ] `src/kb/core/create.py` has no `body_file`, `sys.stdin`, or external-body path read.
- [ ] `src/kb/core/ingest.py` has no concrete adapter registry, external-source path read, standard-stream access, platform lookup, PATH lookup, or subprocess execution.
- [ ] `bind_ingest_source()` performs no I/O; only `BoundIngestSource.acquire()` does.
- [ ] Core strict UTF-8 decoding, ingest non-text policy, newline normalization, and empty-input rules remain covered.
- [ ] Environment/config/malformed/surface failures still precede external acquisition failures.
- [ ] Payload/source-shape mismatch is rejected before any KB write.
- [ ] Existing error codes, messages, output streams, JSON fields, exit codes, warnings, help text, file bytes, paths, indexes, logs, and partial-write behavior are unchanged.
- [ ] The AST guard allows KB filesystem I/O and rejects delivery/process dependencies, including aliased imports.
- [ ] `git status --short` contains no unintended files and does not stage `.gitignore` or `.claude/skills/*`.

## Coverage Map

- Normative seam wording and spec correction: Task 1.
- Create external file/stdin acquisition and explicit core bytes: Task 2.
- Ingest file/stdin/clipboard adapters, self-describing payload, and source-shape validation: Task 3.
- Environment-before-acquisition precedence: Tasks 2–3.
- Stable command failure/rendering behavior: Tasks 2–3 and full regression in Task 4.
- Prohibited Typer/output/global/process dependencies in core: Task 4.
- Full create AC01–AC52, ingest AC01–AC50, and repository regression: Task 4.
