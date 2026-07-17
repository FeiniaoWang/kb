# `kb validate` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the read-only `kb validate` CI gate so one deterministic pass checks every Markdown file, reports all twenty stable finding codes, supports scoped and piped references, and emits the exact text/JSON/exit contracts in AC1–AC74.

**Architecture:** Extend the existing single-pass scanner with a lossless record for every `*.md` file, including parsed files that cannot be classified and operational `log` files, while preserving the existing `KB.documents`, `KB.by_id`, and `KB.malformed` query interfaces. Put validation models, rule helpers, global relationship checks, scoping, ordering, and gate calculation in `core/validate.py`; keep `cli/validate.py` limited to Typer parsing, optional stdin collection, rendering, diagnostics, and exit mapping. Add rules in independently reviewable TDD slices, but always run them over the complete scan before filtering by scope.

**Tech Stack:** Python >=3.14, Typer >=0.26.8, Pydantic >=2.13.4, PyYAML >=6.0.3, pytest >=9.1.1, `uv`.

## Global Constraints

- Implementation context is exactly `docs/specs/commands/kb-validate.md` plus `docs/specs/commands/00-shared.md`; `kb-validate.md` takes precedence.
- Preserve the fixed top-level package layout. Internal modules may change only under `src/kb/core/` and `src/kb/cli/`.
- Runtime dependencies remain exactly `typer`, `PyYAML`, and `pydantic` 2.x; do not edit `pyproject.toml` or `uv.lock`.
- `core/` contains no Typer, printing, `sys.exit`, subprocesses, network calls, Git calls, persistent indexes, or caches.
- `cli/` only parses arguments, reads piped refs, invokes core, renders results/errors, emits unresolved-ref diagnostics, and maps results to exit codes.
- Resolve the root, load config, and perform exactly one recursive scan per invocation; the check universe is every `*.md`, including malformed, index, stray, and operational files.
- `type` is mandatory and authoritative; path never reclassifies a document.
- Parsed files with absent/empty/non-string `type` produce only `FM0_MISSING_TYPE`; unreadable, undecodable, missing/unclosed-frontmatter, invalid-YAML, and non-mapping files produce only `FM0_UNPARSEABLE`.
- A `type: log` file receives only FM0 and location checks; all other frontmatter/body fields are ignored.
- Every rule runs over the whole universe before scope filtering. Scope changes only reported anchors, `checked`, and the exit gate.
- Findings sort by `(path, code, occurrence)` and stable list/key order is retained. Multi-file defects emit one finding per participating anchor.
- The twenty finding codes and fixed severities are append-only machine contracts: sixteen errors and four warnings.
- `--strict` changes only gate calculation; it never changes findings or their ordering.
- Success is exit 0; reported errors, strict-mode reported warnings, or unresolved refs are exit 1; usage/root/config/schema failures are exit 2.
- Validation is byte-for-byte read-only, writes no log entry or cache, and never runs or inspects Git.
- Text findings and summaries go to stdout; unresolved-ref notes and non-JSON command errors go to stderr. JSON command errors use the shared error envelope on stdout.
- Tests use Typer `CliRunner`, never a CLI subprocess. Exactly one `test_ac<NN>_<slug>` function in `tests/cli/test_validate.py` covers each validate AC1–AC74.
- Commit messages cite CLI-6/CLI-12 and the AC range delivered by the task.

---

## File Structure

- Modify `src/kb/core/model.py`: make `Document.from_scan()` retain only literal string ids so an otherwise classifiable file with a malformed `id` remains query-safe and validate-able.
- Modify `src/kb/core/scan.py`: add `ScannedMarkdown`, retain every Markdown file in `KB.files`, split parse failure from missing-type classification, expose `doc_class_from_type()`, and preserve existing document/id/malformed views.
- Create `src/kb/core/validate.py`: define `Finding`, request/result/failure models, all twenty checks, deterministic ordering, global graph/link/id checks, REF scoping, and exit calculation.
- Create `src/kb/cli/validate.py`: define normative help/examples/options, collect piped refs only when no arguments were supplied, call core, print unresolved refs, and exit with the core result.
- Modify `src/kb/cli/render.py`: add exact validate text and JSON renderers while retaining shared error rendering.
- Modify `src/kb/cli/app.py`: register `validate` alongside the existing commands.
- Modify `tests/conftest.py`: add reusable `make_kb`, `make_doc`, and `invoke_validate` helpers required by the shared testing contract.
- Modify `tests/core/test_scan.py`: pin the expanded scan universe and update the old assumption that a bad `id` makes a document unclassifiable.
- Create `tests/core/test_validate.py`: unit-pin canonical id/timestamp/cycle helpers where a focused core test gives clearer failures than a CLI acceptance test.
- Create `tests/cli/test_validate.py`: implement exactly AC1–AC74 in functional slices.
- Modify `tests/cli/test_init.py`: remove the `xfail` marker from init AC30 once validate makes the fresh scaffold gate pass.

## Stable Interfaces

```python
# src/kb/core/scan.py
class ScannedMarkdown(BaseModel):
    path: Path
    frontmatter: Frontmatter | None = None
    parse_error: str | None = None

class KB(BaseModel):
    root: Path
    files: list[ScannedMarkdown] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    by_id: dict[str, Document] = Field(default_factory=dict)
    malformed: list[tuple[Path, str]] = Field(default_factory=list)

def read_frontmatter(path: Path) -> Frontmatter
def doc_class_from_type(type_name: str) -> DocClass | None
def scan(root: Path) -> KB
def resolve_ref(kb: KB, ref: str) -> Document | None

# src/kb/core/validate.py
Severity = Literal["error", "warning"]

class Finding(BaseModel):
    code: str
    severity: Severity
    path: str
    id: str | None
    message: str
    _occurrence: int = PrivateAttr(default=0)

    @property
    def occurrence(self) -> int:
        return self._occurrence

class ValidateRequest(BaseModel):
    refs: list[str] = Field(default_factory=list)
    strict: bool = False
    kb_root: Path | None = None

class ValidateResult(BaseModel):
    checked: int
    findings: list[Finding] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    exit_code: Literal[0, 1]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

class ValidateFailure(Exception):
    code: str
    message: str
    exit_code: Literal[2]

def validate(request: ValidateRequest) -> ValidateResult

# src/kb/cli/render.py
def render_validate_text(result: ValidateResult) -> str
def render_validate_json(result: ValidateResult) -> str

# src/kb/cli/validate.py
def validate_command(
    refs: list[str] | None = None,
    strict: bool = False,
    kb_root: Path | None = None,
    json_output: bool = False,
) -> None
```

---

### Task 1: Preserve the complete Markdown scan universe

**Files:**
- Modify: `src/kb/core/model.py:58-91`
- Modify: `src/kb/core/scan.py:14-102`
- Modify: `tests/core/test_scan.py:41-77`

**Interfaces:**
- Consumes: existing `Frontmatter`, `Document`, `DocClass`, `KB.documents`, `KB.by_id`, and `KB.malformed` contracts.
- Produces: `ScannedMarkdown`, `KB.files`, parse-only `read_frontmatter()`, and public `doc_class_from_type()` as declared above. Existing write/query commands continue consuming `documents`, `by_id`, and `malformed` unchanged.

- [ ] **Step 1: Write failing scan-universe tests**

Replace `test_scan_collects_bad_yaml_and_missing_type` and `test_scan_collects_document_validation_errors_in_path_order` in `tests/core/test_scan.py`, and add the operational-file test:

```python
def test_scan_retains_parse_failures_and_missing_type_in_complete_file_view(tmp_path) -> None:
    write_doc(tmp_path, "bad-yaml.md", "type: [\n")
    write_doc(tmp_path, "missing-type.md", "id: RAW-000004\n")
    kb = scan(tmp_path)
    assert kb.documents == []
    assert [item.path.as_posix() for item in kb.files] == [
        "bad-yaml.md",
        "missing-type.md",
    ]
    assert kb.files[0].frontmatter is None
    assert kb.files[0].parse_error is not None
    assert kb.files[1].frontmatter is not None
    assert kb.files[1].parse_error is None
    assert [path.as_posix() for path, _ in kb.malformed] == [
        "bad-yaml.md",
        "missing-type.md",
    ]


def test_scan_keeps_bad_id_shapes_classifiable_for_validate(tmp_path) -> None:
    write_doc(tmp_path, "raw/sources/z-invalid.md", "id: [RAW-000009]\ntype: raw-source\n")
    write_doc(tmp_path, "raw/sources/a-invalid.md", "id: 7\ntype: raw-source\n")
    write_doc(tmp_path, "raw/sources/middle.md", "id: RAW-000005\ntype: raw-source\n")
    kb = scan(tmp_path)
    assert [document.path.as_posix() for document in kb.documents] == [
        "raw/sources/a-invalid.md",
        "raw/sources/middle.md",
        "raw/sources/z-invalid.md",
    ]
    assert [document.id for document in kb.documents] == [None, "RAW-000005", None]
    assert kb.malformed == []


def test_scan_retains_log_in_files_but_excludes_it_from_documents(tmp_path) -> None:
    write_doc(tmp_path, "log.md", "type: log\ncustom: ignored\n")
    kb = scan(tmp_path)
    assert [item.path.as_posix() for item in kb.files] == ["log.md"]
    assert kb.files[0].frontmatter.root["type"] == "log"
    assert kb.documents == []
    assert kb.by_id == {}
    assert kb.malformed == []
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/core/test_scan.py -k 'complete_file_view or bad_id_shapes or retains_log' -v`

Expected: FAIL because `KB.files`/`ScannedMarkdown` do not exist and bad ids are currently placed in `KB.malformed`.

- [ ] **Step 3: Make `Document.from_scan()` tolerant of non-string literal ids**

Replace the `Document.from_scan()` constructor body in `src/kb/core/model.py` with:

```python
        raw_id = frontmatter.root.get("id")
        document = cls(
            id=raw_id if isinstance(raw_id, str) else None,
            path=relative_path,
            doc_class=doc_class,
            frontmatter=frontmatter,
        )
        document._source_path = source_path
        return document
```

- [ ] **Step 4: Extend the scanner without adding a second filesystem walk**

In `src/kb/core/scan.py`, add `ScannedMarkdown`, add `files` to `KB`, remove the `type` check from `read_frontmatter()`, rename `_doc_class()` to `doc_class_from_type()`, and replace `scan()` with:

```python
class ScannedMarkdown(BaseModel):
    path: Path
    frontmatter: Frontmatter | None = None
    parse_error: str | None = None


class KB(BaseModel):
    root: Path
    files: list[ScannedMarkdown] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    by_id: dict[str, Document] = Field(default_factory=dict)
    malformed: list[tuple[Path, str]] = Field(default_factory=list)


def read_frontmatter(path: Path) -> Frontmatter:
    yaml_lines: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        if stream.readline().rstrip("\r\n") != "---":
            raise ValueError("missing opening frontmatter delimiter")
        for line in stream:
            if line.rstrip("\r\n") == "---":
                break
            yaml_lines.append(line)
        else:
            raise ValueError("missing closing frontmatter delimiter")
    parsed: Any = yaml.safe_load("".join(yaml_lines))
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return Frontmatter.model_validate(parsed)


def doc_class_from_type(type_name: str) -> DocClass | None:
    if type_name == "log":
        return None
    if type_name == "index":
        return DocClass.INDEX
    if type_name in {"raw-source", "chat", "feedback"}:
        return DocClass.RAW
    if type_name in {"conventions", "kb-config", "health"}:
        return DocClass.GOVERNANCE
    return DocClass.SYNTHETIC


def scan(root: Path) -> KB:
    resolved = root.resolve()
    kb = KB(root=resolved)
    for source_path in sorted(resolved.rglob("*.md")):
        relative = source_path.relative_to(resolved)
        try:
            frontmatter = read_frontmatter(source_path)
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            message = str(error)
            kb.files.append(ScannedMarkdown(path=relative, parse_error=message))
            kb.malformed.append((relative, message))
            continue
        kb.files.append(ScannedMarkdown(path=relative, frontmatter=frontmatter))
        type_name = frontmatter.root.get("type")
        if not isinstance(type_name, str) or not type_name:
            kb.malformed.append((relative, "frontmatter is missing mandatory type"))
            continue
        doc_class = doc_class_from_type(type_name)
        if doc_class is None:
            continue
        document = Document.from_scan(
            source_path=source_path,
            relative_path=relative,
            doc_class=doc_class,
            frontmatter=frontmatter,
        )
        kb.documents.append(document)
        if document.id is not None:
            kb.by_id.setdefault(document.id, document)
    return kb
```

- [ ] **Step 5: Run scanner and existing command regressions**

Run: `uv run pytest tests/core/test_scan.py tests/cli/test_ingest.py tests/cli/test_create.py -q`

Expected: all selected tests pass; no query/write behavior regresses.

- [ ] **Step 6: Commit the scan foundation**

```bash
git add src/kb/core/model.py src/kb/core/scan.py tests/core/test_scan.py
git commit -m "refactor: retain validate scan universe (CLI-6 AC5-AC10)"
```

---

### Task 2: Add the validation command, result models, FM0 checks, and read-only baseline

**Files:**
- Create: `src/kb/core/validate.py`
- Create: `src/kb/cli/validate.py`
- Modify: `src/kb/cli/render.py`
- Modify: `src/kb/cli/app.py`
- Modify: `tests/conftest.py`
- Create: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: Task 1's `KB.files`, existing root/config loaders, Typer app/renderer conventions, and `CliRunner` fixtures.
- Produces: all stable validate interfaces declared above, whole-KB validation, FM0 findings, exact summaries, read-only behavior, and AC1–AC10.

- [ ] **Step 1: Add reusable KB/test builders and the validate invoker**

Append to `tests/conftest.py`:

```python
import json
from typing import Any


def make_kb(
    root: Path,
    *,
    types: list[str] | None = None,
    tags: list[str] | None = None,
    id_prefixes: dict[str, str] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    prefixes = {
        "synthetic": "KB",
        "source": "RAW",
        "chat": "CHAT",
        "feedback": "FEED",
    }
    if id_prefixes is not None:
        prefixes.update(id_prefixes)
    (root / "kb-config.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "types": [] if types is None else types,
                "tags": [] if tags is None else tags,
                "id_prefixes": prefixes,
                "propagation_auto_safe": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def make_doc(
    root: Path,
    relative: str,
    frontmatter: dict[str, Any],
    body: str = "body\n",
) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{yaml_text}---\n{body}", encoding="utf-8")
    return path


@pytest.fixture
def invoke_validate(runner: CliRunner, monkeypatch) -> Callable[..., object]:
    def invoke(
        cwd: Path,
        *arguments: str,
        input: str | bytes | None = None,
    ):
        monkeypatch.chdir(cwd)
        return runner.invoke(app, ["validate", *arguments], input=input)

    return invoke
```

Also add `import yaml` beside the existing imports in `tests/conftest.py`.

- [ ] **Step 2: Write AC1–AC10 as failing command tests**

Create `tests/cli/test_validate.py` with these helpers and tests:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from conftest import make_doc, make_kb


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def chat(root: Path, doc_id: str = "CHAT-000001", relative: str = "raw/chats/session.md") -> Path:
    return make_doc(
        root,
        relative,
        {
            "id": doc_id,
            "type": "chat",
            "ingested_at": "2026-07-16T09:00:00Z",
            "origin": "stdin",
            "title": "Session",
        },
    )


def source(root: Path, doc_id: str = "RAW-000001", relative: str = "raw/sources/source.md") -> Path:
    return make_doc(
        root,
        relative,
        {
            "id": doc_id,
            "type": "raw-source",
            "ingested_at": "2026-07-16T08:00:00Z",
            "origin": "file",
            "title": "Source",
        },
    )


def synthetic(
    root: Path,
    doc_id: str = "KB-000001",
    relative: str = "synthetic/note.md",
    **overrides: object,
) -> Path:
    chat(root)
    values: dict[str, object] = {
        "id": doc_id,
        "type": "spec",
        "title": "Note",
        "description": "A concise note.",
        "status": "current",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return make_doc(root, relative, values)


def finding_payload(result) -> list[dict[str, object]]:
    return json.loads(result.stdout)["findings"]


def test_ac01_fresh_init_scaffold_is_born_valid(initialized_kb, invoke_validate) -> None:
    result = invoke_validate(initialized_kb)
    assert result.exit_code == 0
    assert result.stdout == "no findings — checked 11 files\n"


def test_ac02_fully_conforming_populated_kb_has_no_findings(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", types=["spec"], tags=["api"])
    source(root)
    chat(root)
    make_doc(root, "raw/feedback/feedback.md", {
        "id": "FEED-000001", "type": "feedback",
        "ingested_at": "2026-07-16T09:30:00Z", "origin": "stdin",
        "title": "Feedback", "about": "KB-000001",
    })
    synthetic(root, tags=["api"], instructions="Keep examples runnable.")
    synthetic(root, "KB-000002", "synthetic/old.md", status="superseded")
    synthetic(root, "KB-000003", "synthetic/new.md", supersedes="KB-000002")
    result = invoke_validate(root)
    assert result.exit_code == 0
    assert "no findings" in result.stdout


def test_ac03_validation_is_byte_for_byte_read_only(initialized_kb, invoke_validate) -> None:
    (initialized_kb / "README.md").write_text("not frontmatter\n", encoding="utf-8")
    before = snapshot(initialized_kb)
    result = invoke_validate(initialized_kb)
    assert result.exit_code == 1
    assert snapshot(initialized_kb) == before


def test_ac04_config_only_empty_kb_checks_zero_files(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "empty")
    result = invoke_validate(root)
    assert result.exit_code == 0
    assert result.stdout == "no findings — checked 0 files\n"


def test_ac05_malformed_guard_does_not_block_validate(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "broken.md").write_text("broken\n", encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert "FM0_UNPARSEABLE" in result.stdout


def test_ac06_missing_unclosed_and_invalid_yaml_are_unparseable(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "a.md").write_text("body\n", encoding="utf-8")
    (root / "b.md").write_text("---\ntype: spec\n", encoding="utf-8")
    (root / "c.md").write_text("---\ntype: [\n---\n", encoding="utf-8")
    result = invoke_validate(root, "--json")
    assert result.exit_code == 1
    findings = finding_payload(result)
    assert [item["code"] for item in findings] == ["FM0_UNPARSEABLE"] * 3
    assert all("frontmatter cannot be parsed" in item["message"] for item in findings)


def test_ac07_non_mapping_and_non_utf8_are_unparseable(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "a.md").write_text("---\n- x\n---\n", encoding="utf-8")
    (root / "b.md").write_bytes(b"---\ntype: spec\n---\n\xff")
    result = invoke_validate(root, "--json")
    assert result.exit_code == 1
    assert [item["code"] for item in finding_payload(result)] == [
        "FM0_UNPARSEABLE", "FM0_UNPARSEABLE"
    ]


def test_ac08_bad_type_shapes_stop_classification(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "a.md", {"id": "KB-000001"})
    make_doc(root, "b.md", {"type": ""})
    make_doc(root, "c.md", {"type": ["x"]})
    result = invoke_validate(root, "--json")
    findings = finding_payload(result)
    assert result.exit_code == 1
    assert [item["code"] for item in findings] == ["FM0_MISSING_TYPE"] * 3


def test_ac09_log_without_type_gets_fm0(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "log.md", {"note": "operational"})
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert "error  log.md  FM0_MISSING_TYPE  missing mandatory type frontmatter field" in result.stdout


def test_ac10_stray_readme_is_in_the_check_universe(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "README.md").write_text("# Read me\n", encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert "error  README.md  FM0_UNPARSEABLE" in result.stdout
```

- [ ] **Step 3: Run AC1–AC10 and verify the command is absent**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac01 or ac02 or ac03 or ac04 or ac05 or ac06 or ac07 or ac08 or ac09 or ac10' -v`

Expected: FAIL with Typer's “No such command 'validate'”.

- [ ] **Step 4: Implement the typed core skeleton and FM0 classification**

Create `src/kb/core/validate.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from kb.core.model import Config, ConfigLoadError, load_config
from kb.core.scan import KB, RootDiscoveryError, ScannedMarkdown, discover_root, scan

Severity = Literal["error", "warning"]


class Finding(BaseModel):
    code: str
    severity: Severity
    path: str
    id: str | None
    message: str
    _occurrence: int = PrivateAttr(default=0)

    @property
    def occurrence(self) -> int:
        return self._occurrence


class ValidateRequest(BaseModel):
    refs: list[str] = Field(default_factory=list)
    strict: bool = False
    kb_root: Path | None = None


class ValidateResult(BaseModel):
    checked: int
    findings: list[Finding] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    exit_code: Literal[0, 1]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class ValidateFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code: Literal[2] = 2


def _literal_id(file: ScannedMarkdown) -> str | None:
    if file.frontmatter is None:
        return None
    value = file.frontmatter.root.get("id")
    return value if isinstance(value, str) else None


def _finding(
    file: ScannedMarkdown,
    code: str,
    severity: Severity,
    message: str,
    occurrence: int = 0,
) -> Finding:
    finding = Finding(
        code=code,
        severity=severity,
        path=file.path.as_posix(),
        id=_literal_id(file),
        message=message,
    )
    finding._occurrence = occurrence
    return finding


def _fm0(file: ScannedMarkdown, root: Path) -> list[Finding]:
    if file.parse_error is not None:
        return [_finding(
            file,
            "FM0_UNPARSEABLE",
            "error",
            f"frontmatter cannot be parsed: {file.parse_error}",
        )]
    try:
        (root / file.path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [_finding(
            file,
            "FM0_UNPARSEABLE",
            "error",
            f"frontmatter cannot be parsed: {error}",
        )]
    assert file.frontmatter is not None
    type_name = file.frontmatter.root.get("type")
    if not isinstance(type_name, str) or not type_name:
        return [_finding(
            file,
            "FM0_MISSING_TYPE",
            "error",
            "missing mandatory type frontmatter field",
        )]
    return []


def _file_findings(file: ScannedMarkdown, config: Config, kb: KB) -> list[Finding]:
    return _fm0(file, kb.root)


def _all_findings(kb: KB, config: Config) -> list[Finding]:
    findings = [
        finding
        for file in kb.files
        for finding in _file_findings(file, config, kb)
    ]
    return sorted(findings, key=lambda item: (item.path, item.code, item.occurrence))


def validate(request: ValidateRequest) -> ValidateResult:
    try:
        root = discover_root(request.kb_root)
        config = load_config(root)
    except (RootDiscoveryError, ConfigLoadError) as error:
        raise ValidateFailure(error.code, error.message) from error
    kb = scan(root)
    findings = _all_findings(kb, config)
    failed = any(item.severity == "error" for item in findings)
    if request.strict and findings:
        failed = True
    return ValidateResult(
        checked=len(kb.files),
        findings=findings,
        unresolved_refs=[],
        exit_code=1 if failed else 0,
    )
```

- [ ] **Step 5: Implement exact rendering, Typer parsing, and registration**

Append to `src/kb/cli/render.py`:

```python
from kb.core.validate import ValidateResult


def render_validate_text(result: ValidateResult) -> str:
    lines = [
        f"{item.severity}  {item.path}  {item.code}  {item.message}"
        for item in result.findings
    ]
    errors = sum(item.severity == "error" for item in result.findings)
    warnings = sum(item.severity == "warning" for item in result.findings)
    total = len(result.findings)
    if total == 0:
        lines.append(f"no findings — checked {result.checked} files")
    else:
        noun = "finding" if total == 1 else "findings"
        lines.append(
            f"{total} {noun} ({errors} errors, {warnings} warnings) — "
            f"checked {result.checked} files"
        )
    return "\n".join(lines)


def render_validate_json(result: ValidateResult) -> str:
    errors = sum(item.severity == "error" for item in result.findings)
    warnings = sum(item.severity == "warning" for item in result.findings)
    return json.dumps(
        {
            "ok": result.ok,
            "checked": result.checked,
            "findings": [
                item.model_dump() for item in result.findings
            ],
            "counts": {"errors": errors, "warnings": warnings},
            "unresolved_refs": result.unresolved_refs,
        },
        ensure_ascii=False,
    )
```

Create `src/kb/cli/validate.py`:

```python
from pathlib import Path
from typing import Annotated

import typer

from kb.cli.render import (
    render_error_json,
    render_error_text,
    render_validate_json,
    render_validate_text,
)
from kb.core.validate import ValidateFailure, ValidateRequest, validate

VALIDATE_DESCRIPTION = """Check the knowledge base's mechanical integrity.

The single authoritative integrity checker and CI gate: verifies every rule checkable without judgment — universal type and type/location agreement, per-class frontmatter schemas, type and tag vocabularies, id format and uniqueness, link resolution, derivation-graph acyclicity, session parentage, and supersedes/status coupling. Reports every finding with a stable code and severity; errors exit 1, warnings exit 0 unless --strict. Reads everything, writes nothing. With REF arguments (or refs piped on stdin), only findings for the named documents are reported. Does not touch Git."""

VALIDATE_EXAMPLES = """Examples:
  kb validate                                  Check the whole KB (the CI gate)
  kb validate --strict                         Warnings fail the run too
  kb validate KB-000042 synthetic/notes.md     Only findings for the named documents
  kb search "retry" --output paths | kb validate    Validate a piped candidate set
  kb validate --json                           Machine-readable findings"""


def validate_command(
    refs: Annotated[
        list[str] | None,
        typer.Argument(
            help="Documents to report findings for (id or KB-relative path). Also read from stdin when piped. [default: the whole KB]"
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat warnings as errors for the exit code."),
    ] = False,
    kb_root: Annotated[
        Path | None,
        typer.Option(
            "--kb",
            help="KB root. [default: discovered upward from the current directory]",
            show_default=False,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit findings as JSON."),
    ] = False,
) -> None:
    try:
        result = validate(ValidateRequest(
            refs=refs or [], strict=strict, kb_root=kb_root
        ))
    except ValidateFailure as error:
        typer.echo(
            render_error_json(error) if json_output else render_error_text(error),
            err=not json_output,
        )
        raise typer.Exit(code=2) from error
    typer.echo(
        render_validate_json(result) if json_output else render_validate_text(result)
    )
    if result.exit_code:
        raise typer.Exit(code=result.exit_code)
```

Add the import and registration to `src/kb/cli/app.py`:

```python
from kb.cli.validate import VALIDATE_DESCRIPTION, VALIDATE_EXAMPLES, validate_command

app.command(
    name="validate",
    help=VALIDATE_DESCRIPTION.replace("\n\n", "\n\n\b\n", 1),
    epilog=VALIDATE_EXAMPLES,
)(validate_command)
```

- [ ] **Step 6: Run AC1–AC10 and the existing suite**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac01 or ac02 or ac03 or ac04 or ac05 or ac06 or ac07 or ac08 or ac09 or ac10' tests/core/test_scan.py -v`

Expected: PASS.

Run: `uv run pytest -q`

Expected: the existing 185 tests plus AC1–AC10 pass; init AC30 remains the single expected xfail until Task 8.

- [ ] **Step 7: Commit the command baseline**

```bash
git add src/kb/core/validate.py src/kb/cli/validate.py src/kb/cli/render.py src/kb/cli/app.py tests/conftest.py tests/cli/test_validate.py
git commit -m "feat: add validate FM0 gate (CLI-6 CLI-12 AC1-AC10)"
```

---

### Task 3: Enforce type/location agreement and per-class FM1 schemas

**Files:**
- Modify: `src/kb/core/validate.py`
- Modify: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: Task 2's `_finding()`, `_fm0()`, ordered `Frontmatter.root`, and `Config`.
- Produces: `_location_findings()` and `_schema_findings()` covering `LOC_TYPE_MISMATCH`, `FM1_FIELD_MISSING`, `FM1_FIELD_INVALID`, `FM1_KEY_FORBIDDEN`, and `FM1_DESCRIPTION_LONG`, including log minimalism and graceful degradation.

- [ ] **Step 1: Add concise assertion/build helpers for rule tests**

Append to `tests/cli/test_validate.py`:

```python
def payload_for(result, path: str | None = None) -> list[dict[str, object]]:
    items = finding_payload(result)
    return items if path is None else [item for item in items if item["path"] == path]


def codes_for(result, path: str | None = None) -> list[str]:
    return [str(item["code"]) for item in payload_for(result, path)]


def valid_synthetic_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": "KB-000001",
        "type": "spec",
        "title": "Note",
        "description": "A concise note.",
        "status": "current",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return values


def run_one(invoke_validate, root: Path, relative: str, values: dict[str, object]):
    make_doc(root, relative, values)
    return invoke_validate(root, "--json")
```

- [ ] **Step 2: Write AC11–AC20 location and missing-field tests**

Append these exact tests:

```python
def test_ac11_raw_subtypes_must_match_their_class_directories(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/chat.md", {
        "id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"
    })
    make_doc(root, "synthetic/source.md", {
        "id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file"
    })
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac12_root_synthetic_and_misplaced_governance_are_location_errors(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "note.md", valid_synthetic_values())
    make_doc(root, "synthetic/conventions.md", {
        "id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Conventions", "description": "Rules."
    })
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac13_log_type_is_reserved_for_root_log(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "log.md", {"type": "log", "anything": [1]})
    make_doc(root, "raw/notes.md", {"type": "log", "id": 7})
    result = invoke_validate(root, "--json")
    assert codes_for(result, "log.md") == []
    assert codes_for(result, "raw/notes.md") == ["LOC_TYPE_MISMATCH"]


def test_ac14_index_location_rule_is_bidirectional(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "synthetic/listing.md", {"type": "index", "description": "Listing."})
    chat(root)
    make_doc(root, "synthetic/index.md", valid_synthetic_values())
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac15_matching_locations_are_valid_at_any_depth(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/api/deep/x.md", {
        "id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file"
    })
    chat(root)
    make_doc(root, "synthetic/specs/x.md", valid_synthetic_values())
    result = invoke_validate(root, "--json")
    assert "LOC_TYPE_MISMATCH" not in codes_for(result)


def test_ac16_each_missing_synthetic_mandatory_field_is_reported(tmp_path, invoke_validate) -> None:
    for field in ["id", "title", "description", "status", "derived_from", "timestamp", "last_human_touch"]:
        root = make_kb(tmp_path / field)
        chat(root)
        values = valid_synthetic_values()
        del values[field]
        result = run_one(invoke_validate, root, "synthetic/note.md", values)
        matching = [item for item in payload_for(result, "synthetic/note.md") if item["code"] == "FM1_FIELD_MISSING"]
        assert len(matching) == 1
        assert f"'{field}'" in matching[0]["message"]


def test_ac17_multiple_missing_fields_emit_one_finding_each(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    values = valid_synthetic_values()
    for field in ["title", "status", "timestamp"]:
        del values[field]
    result = run_one(invoke_validate, root, "synthetic/note.md", values)
    assert codes_for(result, "synthetic/note.md").count("FM1_FIELD_MISSING") == 3


def test_ac18_raw_mandatory_set_excludes_title(tmp_path, invoke_validate) -> None:
    for field, expected in [("ingested_at", True), ("origin", True), ("title", False)]:
        root = make_kb(tmp_path / field)
        values = {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "title": "Source"}
        del values[field]
        result = run_one(invoke_validate, root, "raw/sources/source.md", values)
        assert ("FM1_FIELD_MISSING" in codes_for(result, "raw/sources/source.md")) is expected


def test_ac19_about_is_mandatory_only_for_feedback(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/feedback/f.md", {"id": "FEED-000001", "type": "feedback", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    make_doc(root, "raw/chats/c.md", {"id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    result = invoke_validate(root, "--json")
    assert codes_for(result, "raw/feedback/f.md") == ["FM1_FIELD_MISSING"]
    assert codes_for(result, "raw/chats/c.md") == []


def test_ac20_governance_and_index_require_description(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "governance/conventions.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Rules"})
    make_doc(root, "index.md", {"type": "index"})
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["FM1_FIELD_MISSING", "FM1_FIELD_MISSING"]
```

- [ ] **Step 3: Write AC21–AC28 shape, forbidden-key, and FM2 tests**

```python
def test_ac21_status_vocabulary_is_literal_and_case_sensitive(tmp_path, invoke_validate) -> None:
    for value in ["accepted", "Current"]:
        root = make_kb(tmp_path / value)
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(status=value))
        assert "FM1_FIELD_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac22_bad_derived_from_shape_preempts_graph_checks(tmp_path, invoke_validate) -> None:
    for offset, value in enumerate(["CHAT-000001", ["CHAT-000001", 42]]):
        root = make_kb(tmp_path / str(offset))
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(derived_from=value))
        anchored = codes_for(result, "synthetic/note.md")
        assert anchored == ["FM1_FIELD_INVALID"]


def test_ac23_timestamp_fields_accept_iso_offsets_and_reject_bad_dates(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "synthetic")
    chat(root)
    bad = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(timestamp="not-a-date"))
    assert "FM1_FIELD_INVALID" in codes_for(bad, "synthetic/note.md")
    root = make_kb(tmp_path / "raw")
    raw_bad = run_one(invoke_validate, root, "raw/sources/source.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-13-40", "origin": "file"})
    assert "FM1_FIELD_INVALID" in codes_for(raw_bad, "raw/sources/source.md")
    root = make_kb(tmp_path / "offset")
    chat(root)
    valid = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(timestamp="2026-07-16T10:00:00+02:00", last_human_touch="2026-07-16T10:00:00+02:00"))
    assert "FM1_FIELD_INVALID" not in codes_for(valid, "synthetic/note.md")


def test_ac24_required_strings_must_be_non_whitespace(tmp_path, invoke_validate) -> None:
    for offset, values in enumerate([valid_synthetic_values(title=""), valid_synthetic_values(description="   ")]):
        root = make_kb(tmp_path / str(offset))
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", values)
        assert "FM1_FIELD_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac25_tags_must_be_a_string_list_but_may_be_empty(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "bad")
    chat(root)
    bad = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(tags="api"))
    assert "FM1_FIELD_INVALID" in codes_for(bad, "synthetic/note.md")
    root = make_kb(tmp_path / "empty")
    chat(root)
    clean = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(tags=[]))
    assert "FM1_FIELD_INVALID" not in codes_for(clean, "synthetic/note.md")


def test_ac26_reserved_keys_are_forbidden_outside_their_schema(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/s.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "about": "KB-000001"})
    make_doc(root, "raw/chats/c.md", {"id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin", "status": "current"})
    make_doc(root, "governance/conventions.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Rules", "description": "Rules.", "derived_from": ["RAW-000001"]})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("FM1_KEY_FORBIDDEN") == 3


def test_ac27_index_id_is_forbidden_without_id_checks(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    result = run_one(invoke_validate, root, "index.md", {"type": "index", "description": "Root.", "id": "KB-000009"})
    assert codes_for(result, "index.md") == ["FM1_KEY_FORBIDDEN"]


def test_ac28_unknown_extension_keys_are_never_flagged(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(custom_field="x"))
    make_doc(root, "raw/sources/s.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "custom_field": "x"})
    result = invoke_validate(root, "--json")
    assert result.exit_code == 0
    assert finding_payload(result) == []
```

- [ ] **Step 4: Run AC11–AC28 and verify the rules are absent**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac11 or ac12 or ac13 or ac14 or ac15 or ac16 or ac17 or ac18 or ac19 or ac20 or ac21 or ac22 or ac23 or ac24 or ac25 or ac26 or ac27 or ac28' -v`

Expected: FAIL because Task 2 emits only FM0 findings.

- [ ] **Step 5: Implement location and schema helpers**

Add these imports/constants/helpers to `src/kb/core/validate.py` and call them from `_file_findings()` after FM0 has returned no finding:

```python
import re
from datetime import datetime

from kb.core.model import DocClass, Document
from kb.core.scan import doc_class_from_type

RESERVED_KEYS = {
    "id", "type", "title", "description", "status", "derived_from",
    "timestamp", "last_human_touch", "tags", "supersedes", "instructions",
    "ingested_at", "origin", "about",
}
STRING_FIELDS = {"id", "title", "description", "origin", "instructions", "supersedes", "about"}
TIMESTAMP_FIELDS = {"timestamp", "last_human_touch", "ingested_at"}
STATUS_VALUES = {"draft", "current", "superseded", "retired"}
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def _type_name(file: ScannedMarkdown) -> str:
    assert file.frontmatter is not None
    value = file.frontmatter.root["type"]
    assert isinstance(value, str) and value
    return value


def _class_contract(type_name: str) -> tuple[str, tuple[str, ...], set[str]]:
    if type_name in {"raw-source", "chat"}:
        return "raw", ("id", "ingested_at", "origin"), {"id", "ingested_at", "origin", "title"}
    if type_name == "feedback":
        return "raw", ("id", "ingested_at", "origin", "about"), {"id", "ingested_at", "origin", "title", "about"}
    if type_name in {"conventions", "kb-config", "health"}:
        return "governance", ("id", "title", "description"), {"id", "title", "description"}
    if type_name == "index":
        return "index", ("description",), {"description", "title"}
    return "synthetic", ("id", "title", "description", "status", "derived_from", "timestamp", "last_human_touch"), {
        "id", "title", "description", "status", "derived_from", "timestamp",
        "last_human_touch", "tags", "supersedes", "instructions",
    }


def _location_expectation(type_name: str) -> tuple[bool, str]:
    if type_name == "index":
        return True, "a file named index.md"
    if type_name == "raw-source":
        return False, "under raw/sources/"
    if type_name == "chat":
        return False, "under raw/chats/"
    if type_name == "feedback":
        return False, "under raw/feedback/"
    if type_name in {"conventions", "kb-config", "health"}:
        return False, "under governance/"
    if type_name == "log":
        return False, "the root log.md"
    return False, "under synthetic/"


def _location_matches(file: ScannedMarkdown, type_name: str) -> bool:
    path = file.path
    if type_name == "index":
        return path.name == "index.md"
    if path.name == "index.md":
        return False
    if type_name == "log":
        return path == Path("log.md")
    expected = {
        "raw-source": Path("raw/sources"),
        "chat": Path("raw/chats"),
        "feedback": Path("raw/feedback"),
    }.get(type_name)
    if expected is None:
        expected = Path("governance") if type_name in {"conventions", "kb-config", "health"} else Path("synthetic")
    return path.parent == expected or expected in path.parent.parents


def _location_findings(file: ScannedMarkdown) -> list[Finding]:
    type_name = _type_name(file)
    if _location_matches(file, type_name):
        return []
    _, expectation = _location_expectation(type_name)
    return [_finding(
        file,
        "LOC_TYPE_MISMATCH",
        "error",
        f"type '{type_name}' does not agree with location '{file.path.as_posix()}' (expected {expectation})",
    )]


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _invalid_reason(field: str, value: object) -> str | None:
    if field in STRING_FIELDS:
        return None if isinstance(value, str) and value.strip() else "must be a non-empty string"
    if field == "status":
        return None if value in STATUS_VALUES else "must be one of draft, current, superseded, retired"
    if field in {"derived_from", "tags"}:
        valid = isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
        return None if valid else "must be a list of non-empty strings"
    if field in TIMESTAMP_FIELDS:
        return None if _parse_timestamp(value) is not None else "must be an ISO-8601 date-time string"
    return None


def _schema_findings(file: ScannedMarkdown) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    if type_name == "log":
        return []
    class_name, mandatory, legal = _class_contract(type_name)
    findings: list[Finding] = []
    for occurrence, field in enumerate(mandatory):
        if field not in values:
            findings.append(_finding(
                file, "FM1_FIELD_MISSING", "error",
                f"missing mandatory field '{field}' for {class_name} documents",
                occurrence,
            ))
    for occurrence, (field, value) in enumerate(values.items()):
        if field == "type" or field not in RESERVED_KEYS:
            continue
        if field not in legal:
            findings.append(_finding(
                file, "FM1_KEY_FORBIDDEN", "error",
                f"key '{field}' is not part of the {class_name} schema",
                occurrence,
            ))
            continue
        reason = _invalid_reason(field, value)
        if reason is not None:
            findings.append(_finding(
                file, "FM1_FIELD_INVALID", "error",
                f"field '{field}' is invalid: {reason}", occurrence,
            ))
    description = values.get("description")
    if isinstance(description, str) and len(SENTENCE_END.findall(description)) > 2:
        findings.append(_finding(
            file, "FM1_DESCRIPTION_LONG", "warning",
            "description exceeds two sentences",
            list(values).index("description"),
        ))
    return findings


def _file_findings(file: ScannedMarkdown, config: Config, kb: KB) -> list[Finding]:
    fm0 = _fm0(file, kb.root)
    if fm0:
        return fm0
    findings = _location_findings(file)
    if _type_name(file) != "log":
        findings.extend(_schema_findings(file))
    return findings
```

- [ ] **Step 6: Run the schema slice and all earlier validate ACs**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac01 or ac02 or ac03 or ac04 or ac05 or ac06 or ac07 or ac08 or ac09 or ac10 or ac11 or ac12 or ac13 or ac14 or ac15 or ac16 or ac17 or ac18 or ac19 or ac20 or ac21 or ac22 or ac23 or ac24 or ac25 or ac26 or ac27 or ac28' -v`

Expected: PASS with exact finding counts and no extra log checks.

- [ ] **Step 7: Commit the schema slice**

```bash
git add src/kb/core/validate.py tests/cli/test_validate.py
git commit -m "feat: validate location and FM1 schemas (CLI-6 AC11-AC28)"
```

---

### Task 4: Enforce descriptions, vocabularies, canonical ids, prefixes, and duplicate ids

**Files:**
- Modify: `src/kb/core/validate.py`
- Create: `tests/core/test_validate.py`
- Modify: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: Task 3's class contracts and field-shape checks plus config `types`, `tags`, and `id_prefixes`.
- Produces: canonical numeric/slug parsers, `_vocabulary_findings()`, `_id_findings()`, and `_duplicate_id_findings()` covering AC29–AC39. Duplicate detection uses literal strings across all classified non-log files and never trusts `KB.by_id` to retain collisions.

- [ ] **Step 1: Pin the two legal id forms in focused core tests**

Create `tests/core/test_validate.py`:

```python
from kb.core.validate import _canonical_numeric_id, _reserved_slug_id


def test_canonical_numeric_id_has_exact_width_and_growth_rules() -> None:
    assert _canonical_numeric_id("KB-000042") == ("KB", "000042")
    assert _canonical_numeric_id("KB-1000001") == ("KB", "1000001")
    assert _canonical_numeric_id("KB-42") is None
    assert _canonical_numeric_id("KB-0000042") is None
    assert _canonical_numeric_id("kb-000042") is None


def test_reserved_slug_id_is_governance_only() -> None:
    assert _reserved_slug_id("GOVERNANCE-CONVENTIONS")
    assert _reserved_slug_id("GOVERNANCE-KB-CONFIG")
    assert not _reserved_slug_id("GOVERNANCE-000001")
    assert not _reserved_slug_id("CONV-CONVENTIONS")
```

- [ ] **Step 2: Write AC29–AC39**

Append to `tests/cli/test_validate.py`:

```python
def test_ac29_description_warning_uses_the_sentence_heuristic(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(description="One. Two! Three?"))
    make_doc(root, "index.md", {"type": "index", "description": "One. Two. Three."})
    make_doc(root, "raw/sources/two.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "description": "One. Two."})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("FM1_DESCRIPTION_LONG") == 2


def test_ac30_declared_synthetic_type_is_clean_and_undeclared_warns(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", types=["spec"])
    chat(root)
    make_doc(root, "synthetic/retro.md", valid_synthetic_values(type="retro"))
    make_doc(root, "synthetic/spec.md", valid_synthetic_values(id="KB-000002"))
    result = invoke_validate(root, "--json")
    warnings = [item for item in finding_payload(result) if item["code"] == "TYPE_UNDECLARED"]
    assert len(warnings) == 1 and "retro" in warnings[0]["message"]


def test_ac31_empty_type_vocabulary_is_unconstrained(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", types=[])
    synthetic(root, type="retro")
    result = invoke_validate(root, "--json")
    assert "TYPE_UNDECLARED" not in codes_for(result)


def test_ac32_each_undeclared_tag_warns_in_list_order(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", tags=["api"])
    synthetic(root, tags=["api", "internal", "wip"])
    result = invoke_validate(root, "--json")
    warnings = [item for item in finding_payload(result) if item["code"] == "TAG_UNDECLARED"]
    assert [item["message"].split("'")[1] for item in warnings] == ["internal", "wip"]


def test_ac33_empty_tag_vocabulary_declares_no_tags(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", tags=[])
    synthetic(root, tags=["api"])
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("TAG_UNDECLARED") == 1


def test_ac34_noncanonical_synthetic_ids_are_invalid(tmp_path, invoke_validate) -> None:
    for offset, doc_id in enumerate(["KB-42", "kb-000042", "KB-FOO"]):
        root = make_kb(tmp_path / str(offset))
        synthetic(root, doc_id)
        result = invoke_validate(root, "--json")
        assert "ID_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac35_seven_digit_id_with_leading_zero_is_invalid(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, "KB-0000042")
    result = invoke_validate(root, "--json")
    assert "ID_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac36_governance_slug_and_numeric_growth_forms_are_class_specific(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "governance/a.md", {"id": "GOVERNANCE-000001", "type": "conventions", "title": "A", "description": "A."})
    make_doc(root, "governance/b.md", {"id": "CONV-CONVENTIONS", "type": "conventions", "title": "B", "description": "B."})
    make_doc(root, "governance/c.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "C", "description": "C."})
    chat(root)
    make_doc(root, "synthetic/large.md", valid_synthetic_values(id="KB-1000001"))
    result = invoke_validate(root, "--json")
    assert codes_for(result, "governance/a.md") == ["ID_INVALID"]
    assert codes_for(result, "governance/b.md") == ["ID_INVALID"]
    assert "ID_INVALID" not in codes_for(result, "governance/c.md")
    assert "ID_INVALID" not in codes_for(result, "synthetic/large.md")


def test_ac37_cross_class_numeric_prefixes_are_mismatches(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, "RAW-000009")
    make_doc(root, "raw/chats/other.md", {"id": "FEED-000002", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("ID_PREFIX_MISMATCH") == 2


def test_ac38_configured_prefix_wins(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", id_prefixes={"synthetic": "SYN"})
    chat(root)
    make_doc(root, "synthetic/bad.md", valid_synthetic_values(id="KB-000001"))
    make_doc(root, "synthetic/good.md", valid_synthetic_values(id="SYN-000001"))
    result = invoke_validate(root, "--json")
    assert "ID_PREFIX_MISMATCH" in codes_for(result, "synthetic/bad.md")
    assert "ID_PREFIX_MISMATCH" not in codes_for(result, "synthetic/good.md")


def test_ac39_duplicate_literal_id_emits_one_finding_per_participant(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(id="KB-000007"))
    make_doc(root, "synthetic/b.md", valid_synthetic_values(id="KB-000007"))
    result = invoke_validate(root, "--json")
    duplicates = [item for item in finding_payload(result) if item["code"] == "ID_DUPLICATE"]
    assert [item["path"] for item in duplicates] == ["synthetic/a.md", "synthetic/b.md"]
    assert "synthetic/b.md" in duplicates[0]["message"]
    assert "synthetic/a.md" in duplicates[1]["message"]
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py -k 'canonical or reserved_slug or ac29 or ac30 or ac31 or ac32 or ac33 or ac34 or ac35 or ac36 or ac37 or ac38 or ac39' -v`

Expected: FAIL because the id/vocabulary helpers and findings do not exist.

- [ ] **Step 4: Implement vocabulary and id checks**

Add to `src/kb/core/validate.py`:

```python
CANONICAL_NUMERIC_ID = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<number>(?:[0-9]{6}|[1-9][0-9]{6,}))$")
RESERVED_SLUG_ID = re.compile(r"^GOVERNANCE-[A-Z][A-Z0-9-]*$")


def _canonical_numeric_id(value: str) -> tuple[str, str] | None:
    match = CANONICAL_NUMERIC_ID.fullmatch(value)
    return None if match is None else (match.group("prefix"), match.group("number"))


def _reserved_slug_id(value: str) -> bool:
    return RESERVED_SLUG_ID.fullmatch(value) is not None


def _vocabulary_findings(file: ScannedMarkdown, config: Config) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    if doc_class_from_type(type_name) is not DocClass.SYNTHETIC:
        return []
    findings: list[Finding] = []
    if config.types and type_name not in config.types:
        findings.append(_finding(
            file, "TYPE_UNDECLARED", "warning",
            f"type '{type_name}' is not declared in the kb-config.json types vocabulary",
            list(values).index("type"),
        ))
    tags = values.get("tags")
    if isinstance(tags, list) and all(isinstance(tag, str) and tag.strip() for tag in tags):
        key_occurrence = list(values).index("tags") if "tags" in values else 0
        for offset, tag in enumerate(tags):
            if tag not in config.tags:
                findings.append(_finding(
                    file, "TAG_UNDECLARED", "warning",
                    f"tag '{tag}' is not declared in the kb-config.json tags vocabulary",
                    key_occurrence * 10_000 + offset,
                ))
    return findings


def _prefix_contract(type_name: str) -> str | None:
    if type_name == "raw-source":
        return "source"
    if type_name in {"chat", "feedback"}:
        return type_name
    if doc_class_from_type(type_name) is DocClass.SYNTHETIC:
        return "synthetic"
    return None


def _id_findings(file: ScannedMarkdown, config: Config) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    class_name, _, legal = _class_contract(type_name)
    raw_id = values.get("id")
    if "id" not in legal or not isinstance(raw_id, str):
        return []
    occurrence = list(values).index("id")
    if class_name == "governance":
        if _reserved_slug_id(raw_id):
            return []
        return [_finding(file, "ID_INVALID", "error", f"id '{raw_id}' is not a valid governance id", occurrence)]
    parsed = _canonical_numeric_id(raw_id)
    if parsed is None:
        return [_finding(file, "ID_INVALID", "error", f"id '{raw_id}' is not a valid {class_name} id", occurrence)]
    class_key = _prefix_contract(type_name)
    if class_key is None:
        return []
    prefix, _ = parsed
    expected = config.id_prefixes[class_key]
    if prefix == expected:
        return []
    return [_finding(
        file, "ID_PREFIX_MISMATCH", "error",
        f"id prefix '{prefix}' does not match the configured {class_key} prefix '{expected}'",
        occurrence,
    )]


def _duplicate_id_findings(kb: KB) -> list[Finding]:
    participants: dict[str, list[ScannedMarkdown]] = {}
    for file in kb.files:
        if file.frontmatter is None:
            continue
        type_name = file.frontmatter.root.get("type")
        raw_id = file.frontmatter.root.get("id")
        if isinstance(type_name, str) and type_name and type_name != "log" and isinstance(raw_id, str):
            participants.setdefault(raw_id, []).append(file)
    findings: list[Finding] = []
    for raw_id, files in participants.items():
        if len(files) < 2:
            continue
        for file in files:
            others = sorted(item.path.as_posix() for item in files if item.path != file.path)
            occurrence = list(file.frontmatter.root).index("id")
            findings.append(_finding(
                file, "ID_DUPLICATE", "error",
                f"id '{raw_id}' is also carried by {', '.join(others)}",
                occurrence,
            ))
    return findings
```

Extend `_file_findings()` after the schema/location checks:

```python
    if _type_name(file) != "log":
        findings.extend(_schema_findings(file))
        findings.extend(_vocabulary_findings(file, config))
        findings.extend(_id_findings(file, config))
```

Extend `_all_findings()` before sorting:

```python
    findings.extend(_duplicate_id_findings(kb))
```

- [ ] **Step 5: Run id/vocabulary tests and the cumulative validate suite**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py -v`

Expected: AC1–AC39 and focused core tests pass.

- [ ] **Step 6: Commit the id and vocabulary slice**

```bash
git add src/kb/core/validate.py tests/core/test_validate.py tests/cli/test_validate.py
git commit -m "feat: validate vocabularies and ids (CLI-6 AC29-AC39)"
```

---

### Task 5: Validate links, parentage, and derivation cycles globally

**Files:**
- Modify: `src/kb/core/validate.py`
- Modify: `tests/core/test_validate.py`
- Modify: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: the scan's first-document `by_id` resolution, authoritative document types, and well-shaped legal relation fields.
- Produces: `_relationship_findings()`, `_derivation_graph()`, `_cycle_from()`, and `_cycle_findings()` covering `LINK_UNRESOLVED`, `DG1_NO_PARENTS`, `DG2_CYCLE`, and `DG5_NO_SESSION_PARENT`. Duplicate parent entries are stable-deduplicated only for traversal and never become findings.

- [ ] **Step 1: Pin deterministic cycle rendering in a core test**

Append to `tests/core/test_validate.py`:

```python
from kb.core.validate import _cycle_from


def test_cycle_from_starts_and_ends_at_the_anchor() -> None:
    graph = {
        "KB-000001": ["KB-000002"],
        "KB-000002": ["KB-000003"],
        "KB-000003": ["KB-000001"],
        "KB-000099": ["KB-000002"],
    }
    assert _cycle_from("KB-000001", graph) == [
        "KB-000001", "KB-000002", "KB-000003", "KB-000001"
    ]
    assert _cycle_from("KB-000002", graph) == [
        "KB-000002", "KB-000003", "KB-000001", "KB-000002"
    ]
    assert _cycle_from("KB-000099", graph) is None
```

- [ ] **Step 2: Write AC40–AC49**

Append to `tests/cli/test_validate.py`:

```python
def test_ac40_each_unresolved_parent_is_reported_in_list_order(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["CHAT-000001", "KB-999999", "RAW-999999"]))
    result = invoke_validate(root, "--json")
    links = [item for item in payload_for(result, "synthetic/note.md") if item["code"] == "LINK_UNRESOLVED"]
    assert [item["message"].split("'")[1] for item in links] == ["KB-999999", "RAW-999999"]


def test_ac41_supersedes_and_feedback_about_must_resolve(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, supersedes="KB-999999")
    make_doc(root, "raw/feedback/f.md", {"id": "FEED-000001", "type": "feedback", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin", "about": "KB-999999"})
    result = invoke_validate(root, "--json")
    links = [item for item in finding_payload(result) if item["code"] == "LINK_UNRESOLVED"]
    assert {item["message"].split()[0] for item in links} == {"about", "supersedes"}


def test_ac42_link_values_never_resolve_as_paths(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["raw/chats/session.md"]))
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" in codes_for(result, "synthetic/note.md")


def test_ac43_reserved_governance_slug_resolves_as_a_parent(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "governance/conventions.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Rules", "description": "Rules."})
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["GOVERNANCE-CONVENTIONS", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" not in codes_for(result, "synthetic/note.md")


def test_ac44_empty_parent_list_is_only_dg1(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=[]))
    result = invoke_validate(root, "--json")
    anchored = codes_for(result, "synthetic/note.md")
    assert anchored.count("DG1_NO_PARENTS") == 1
    assert "FM1_FIELD_MISSING" not in anchored
    assert "DG5_NO_SESSION_PARENT" not in anchored


def test_ac45_two_document_cycle_anchors_once_to_each_participant(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(id="KB-000001", derived_from=["KB-000002", "CHAT-000001"]))
    make_doc(root, "synthetic/b.md", valid_synthetic_values(id="KB-000002", derived_from=["KB-000001", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    cycles = [item for item in finding_payload(result) if item["code"] == "DG2_CYCLE"]
    assert [item["path"] for item in cycles] == ["synthetic/a.md", "synthetic/b.md"]
    assert cycles[0]["message"] == "derivation cycle: KB-000001 -> KB-000002 -> KB-000001"
    assert cycles[1]["message"] == "derivation cycle: KB-000002 -> KB-000001 -> KB-000002"


def test_ac46_self_parent_is_a_one_node_cycle(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(derived_from=["KB-000001", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    cycle = [item for item in payload_for(result, "synthetic/a.md") if item["code"] == "DG2_CYCLE"]
    assert len(cycle) == 1
    assert cycle[0]["message"] == "derivation cycle: KB-000001 -> KB-000001"


def test_ac47_diamond_derivation_is_acyclic(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/one.md", valid_synthetic_values(id="KB-000001"))
    make_doc(root, "synthetic/two.md", valid_synthetic_values(id="KB-000002", derived_from=["KB-000001", "CHAT-000001"]))
    make_doc(root, "synthetic/three.md", valid_synthetic_values(id="KB-000003", derived_from=["KB-000001", "CHAT-000001"]))
    make_doc(root, "synthetic/four.md", valid_synthetic_values(id="KB-000004", derived_from=["KB-000002", "KB-000002", "KB-000003", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    assert "DG2_CYCLE" not in codes_for(result)


def test_ac48_a_resolvable_chat_parent_is_required(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "without-chat")
    source(root)
    chat(root)
    make_doc(root, "synthetic/parent.md", valid_synthetic_values(id="KB-000002", derived_from=["CHAT-000001"]))
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["RAW-000001", "KB-000002"]))
    result = invoke_validate(root, "--json")
    assert "DG5_NO_SESSION_PARENT" in codes_for(result, "synthetic/note.md")
    root = make_kb(tmp_path / "with-chat")
    source(root)
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["RAW-000001", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    assert "DG5_NO_SESSION_PARENT" not in codes_for(result, "synthetic/note.md")


def test_ac49_dg5_uses_only_resolvable_parents(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "none")
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["CHAT-999999"]))
    result = invoke_validate(root, "--json")
    assert {"LINK_UNRESOLVED", "DG5_NO_SESSION_PARENT"}.issubset(codes_for(result, "synthetic/note.md"))
    root = make_kb(tmp_path / "one")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(derived_from=["KB-999999", "CHAT-000001"]))
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" in codes_for(result, "synthetic/note.md")
    assert "DG5_NO_SESSION_PARENT" not in codes_for(result, "synthetic/note.md")
```

- [ ] **Step 3: Run the relation tests and verify they fail**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py -k 'cycle_from or ac40 or ac41 or ac42 or ac43 or ac44 or ac45 or ac46 or ac47 or ac48 or ac49' -v`

Expected: FAIL because link/graph findings are not implemented.

- [ ] **Step 4: Implement legal link checks and DG1/DG5**

Add to `src/kb/core/validate.py`:

```python
def _resolved_document(kb: KB, value: str) -> Document | None:
    return kb.by_id.get(value)


def _well_shaped_string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _relationship_findings(file: ScannedMarkdown, kb: KB) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    doc_class = doc_class_from_type(type_name)
    findings: list[Finding] = []
    if doc_class is DocClass.SYNTHETIC:
        derived_from = values.get("derived_from")
        if _well_shaped_string_list(derived_from):
            occurrence = list(values).index("derived_from")
            for offset, parent in enumerate(derived_from):
                if _resolved_document(kb, parent) is None:
                    findings.append(_finding(
                        file, "LINK_UNRESOLVED", "error",
                        f"derived_from reference '{parent}' does not resolve to a document id",
                        occurrence * 10_000 + offset,
                    ))
            if not derived_from:
                findings.append(_finding(
                    file, "DG1_NO_PARENTS", "error",
                    "derived_from is empty — every synthetic document declares at least one parent",
                    occurrence,
                ))
            elif not any(
                parent_doc is not None and parent_doc.frontmatter.root.get("type") == "chat"
                for parent_doc in (_resolved_document(kb, parent) for parent in derived_from)
            ):
                findings.append(_finding(
                    file, "DG5_NO_SESSION_PARENT", "error",
                    "no session record (type chat) among derived_from parents",
                    occurrence,
                ))
        supersedes = values.get("supersedes")
        if isinstance(supersedes, str) and supersedes.strip() and _resolved_document(kb, supersedes) is None:
            findings.append(_finding(
                file, "LINK_UNRESOLVED", "error",
                f"supersedes reference '{supersedes}' does not resolve to a document id",
                list(values).index("supersedes"),
            ))
    if type_name == "feedback":
        about = values.get("about")
        if isinstance(about, str) and about.strip() and _resolved_document(kb, about) is None:
            findings.append(_finding(
                file, "LINK_UNRESOLVED", "error",
                f"about reference '{about}' does not resolve to a document id",
                list(values).index("about"),
            ))
    return findings
```

- [ ] **Step 5: Implement deterministic cycle checks over synthetic edges only**

Add:

```python
def _derivation_graph(kb: KB) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for document in kb.documents:
        if document.doc_class is not DocClass.SYNTHETIC or document.id is None:
            continue
        parents = document.frontmatter.root.get("derived_from")
        if not _well_shaped_string_list(parents):
            continue
        synthetic_parents = [
            parent
            for parent in parents
            if (resolved := kb.by_id.get(parent)) is not None
            and resolved.doc_class is DocClass.SYNTHETIC
        ]
        graph[document.id] = list(dict.fromkeys(synthetic_parents))
    return graph


def _cycle_from(start: str, graph: dict[str, list[str]]) -> list[str] | None:
    def visit(current: str, path: list[str]) -> list[str] | None:
        for target in graph.get(current, []):
            if target == start:
                return [*path, start]
            if target in path:
                continue
            found = visit(target, [*path, target])
            if found is not None:
                return found
        return None

    return visit(start, [start])


def _cycle_findings(kb: KB) -> list[Finding]:
    graph = _derivation_graph(kb)
    files_by_path = {file.path: file for file in kb.files}
    findings: list[Finding] = []
    for document in kb.documents:
        if document.doc_class is not DocClass.SYNTHETIC or document.id is None:
            continue
        cycle = _cycle_from(document.id, graph)
        if cycle is None:
            continue
        file = files_by_path[document.path]
        parents = file.frontmatter.root.get("derived_from")
        occurrence = list(file.frontmatter.root).index("derived_from") if _well_shaped_string_list(parents) else 0
        findings.append(_finding(
            file, "DG2_CYCLE", "error",
            f"derivation cycle: {' -> '.join(cycle)}",
            occurrence,
        ))
    return findings
```

Extend `_file_findings()` for non-log classified files:

```python
        findings.extend(_relationship_findings(file, kb))
```

Extend `_all_findings()` before sorting:

```python
    findings.extend(_cycle_findings(kb))
```

- [ ] **Step 6: Run relation/graph and cumulative tests**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py -v`

Expected: AC1–AC49 and all focused core tests pass. AC44 emits DG1 but not DG5; AC49 emits both link and DG5 only in the unresolved-only case.

- [ ] **Step 7: Commit the relationship slice**

```bash
git add src/kb/core/validate.py tests/core/test_validate.py tests/cli/test_validate.py
git commit -m "feat: validate links and derivation graph (CLI-6 AC40-AC49)"
```

---

### Task 6: Enforce lifecycle coupling, timestamp ordering, severity, and strict mode

**Files:**
- Modify: `src/kb/core/validate.py`
- Modify: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: resolved non-self synthetic `supersedes` links, `_parse_timestamp()`, and Task 2's gate calculation.
- Produces: `_lifecycle_findings()` covering all four `LS_*` codes and AC50–AC57. Self-supersession preempts target-class/status checks; non-synthetic targets preempt status checks; timestamp comparison happens only after both shapes parse.

- [ ] **Step 1: Write AC50–AC57**

Append to `tests/cli/test_validate.py`:

```python
def test_ac50_supersedes_target_must_be_marked_superseded(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "status")
    chat(root)
    make_doc(root, "synthetic/old.md", valid_synthetic_values(id="KB-000031", status="current"))
    make_doc(root, "synthetic/new.md", valid_synthetic_values(id="KB-000032", supersedes="KB-000031"))
    result = invoke_validate(root, "--json")
    marked = [item for item in payload_for(result, "synthetic/new.md") if item["code"] == "LS_SUPERSEDES_NOT_MARKED"]
    assert len(marked) == 1 and "has status 'current'" in marked[0]["message"]
    root = make_kb(tmp_path / "missing")
    chat(root)
    old = valid_synthetic_values(id="KB-000031")
    del old["status"]
    make_doc(root, "synthetic/old.md", old)
    make_doc(root, "synthetic/new.md", valid_synthetic_values(id="KB-000032", supersedes="KB-000031"))
    result = invoke_validate(root, "--json")
    marked = [item for item in payload_for(result, "synthetic/new.md") if item["code"] == "LS_SUPERSEDES_NOT_MARKED"]
    assert len(marked) == 1 and "has no status" in marked[0]["message"]


def test_ac51_non_synthetic_supersedes_target_gets_only_class_error(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    source(root)
    synthetic(root, supersedes="RAW-000001")
    result = invoke_validate(root, "--json")
    anchored = codes_for(result, "synthetic/note.md")
    assert "LS_SUPERSEDES_NOT_SYNTHETIC" in anchored
    assert "LS_SUPERSEDES_NOT_MARKED" not in anchored


def test_ac52_self_supersedes_preempts_other_lifecycle_findings(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, supersedes="KB-000001")
    result = invoke_validate(root, "--json")
    lifecycle = [code for code in codes_for(result, "synthetic/note.md") if code.startswith("LS_SUPERSEDES")]
    assert lifecycle == ["LS_SUPERSEDES_SELF"]


def test_ac53_conforming_supersession_pair_is_clean(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/old.md", valid_synthetic_values(id="KB-000031", status="superseded"))
    make_doc(root, "synthetic/new.md", valid_synthetic_values(id="KB-000032", supersedes="KB-000031"))
    make_doc(root, "synthetic/also-new.md", valid_synthetic_values(id="KB-000033", supersedes="KB-000031"))
    make_doc(root, "synthetic/unlinked.md", valid_synthetic_values(id="KB-000034", status="superseded"))
    result = invoke_validate(root, "--json")
    assert not any(code.startswith("LS_") for code in codes_for(result))


def test_ac54_last_human_touch_may_not_be_later_than_timestamp(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "later")
    synthetic(root, timestamp="2026-07-16T10:00:00Z", last_human_touch="2026-07-16T11:00:00Z")
    result = invoke_validate(root, "--json")
    assert "LS_TOUCH_AFTER_TIMESTAMP" in codes_for(result, "synthetic/note.md")
    root = make_kb(tmp_path / "equal")
    synthetic(root, timestamp="2026-07-16T10:00:00Z", last_human_touch="2026-07-16T10:00:00Z")
    result = invoke_validate(root, "--json")
    assert "LS_TOUCH_AFTER_TIMESTAMP" not in codes_for(result, "synthetic/note.md")
    root = make_kb(tmp_path / "bad")
    synthetic(root, last_human_touch="bad")
    result = invoke_validate(root, "--json")
    assert "FM1_FIELD_INVALID" in codes_for(result, "synthetic/note.md")
    assert "LS_TOUCH_AFTER_TIMESTAMP" not in codes_for(result, "synthetic/note.md")


def test_ac55_warnings_are_reported_but_exit_zero_by_default(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, description="One. Two. Three.")
    result = invoke_validate(root)
    assert result.exit_code == 0
    assert "warning" in result.stdout and "FM1_DESCRIPTION_LONG" in result.stdout


def test_ac56_strict_changes_only_the_warning_gate(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, description="One. Two. Three.")
    normal = invoke_validate(root)
    strict = invoke_validate(root, "--strict")
    assert normal.stdout == strict.stdout
    assert normal.exit_code == 0
    assert strict.exit_code == 1


def test_ac57_errors_exit_one_with_and_without_strict(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "README.md").write_text("broken\n", encoding="utf-8")
    assert invoke_validate(root).exit_code == 1
    assert invoke_validate(root, "--strict").exit_code == 1
```

- [ ] **Step 2: Run lifecycle/severity tests and verify lifecycle cases fail**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac50 or ac51 or ac52 or ac53 or ac54 or ac55 or ac56 or ac57' -v`

Expected: AC50–AC54 FAIL because lifecycle findings are absent; AC55–AC57 already pin the existing gate calculation.

- [ ] **Step 3: Implement lifecycle checks with preemption**

Add `timezone` to the datetime import and add:

```python
from datetime import datetime, timezone


def _lifecycle_findings(file: ScannedMarkdown, kb: KB) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    if doc_class_from_type(_type_name(file)) is not DocClass.SYNTHETIC:
        return []
    findings: list[Finding] = []
    supersedes = values.get("supersedes")
    own_id = values.get("id")
    if isinstance(supersedes, str) and supersedes.strip():
        occurrence = list(values).index("supersedes")
        if isinstance(own_id, str) and supersedes == own_id:
            findings.append(_finding(
                file, "LS_SUPERSEDES_SELF", "error",
                "document supersedes itself", occurrence,
            ))
        else:
            target = kb.by_id.get(supersedes)
            if target is not None:
                if target.doc_class is not DocClass.SYNTHETIC:
                    findings.append(_finding(
                        file, "LS_SUPERSEDES_NOT_SYNTHETIC", "error",
                        f"supersedes target {supersedes} is not a synthetic document",
                        occurrence,
                    ))
                else:
                    status = target.frontmatter.root.get("status")
                    if status != "superseded":
                        state = "has no status" if "status" not in target.frontmatter.root else f"has status '{status}'"
                        findings.append(_finding(
                            file, "LS_SUPERSEDES_NOT_MARKED", "error",
                            f"supersedes target {supersedes} {state}, expected 'superseded'",
                            occurrence,
                        ))
    timestamp = _parse_timestamp(values.get("timestamp"))
    touched = _parse_timestamp(values.get("last_human_touch"))
    if timestamp is not None and touched is not None:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if touched.tzinfo is None:
            touched = touched.replace(tzinfo=timezone.utc)
        if touched > timestamp:
            findings.append(_finding(
                file, "LS_TOUCH_AFTER_TIMESTAMP", "warning",
                f"last_human_touch {values['last_human_touch']} is later than timestamp {values['timestamp']}",
                list(values).index("last_human_touch"),
            ))
    return findings
```

Extend `_file_findings()` after relation checks:

```python
        findings.extend(_lifecycle_findings(file, kb))
```

- [ ] **Step 4: Run AC1–AC57 cumulatively**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py -v`

Expected: AC1–AC57 pass; text output is identical with and without `--strict` while exit codes differ for warnings.

- [ ] **Step 5: Commit lifecycle and strict-mode behavior**

```bash
git add src/kb/core/validate.py tests/cli/test_validate.py
git commit -m "feat: validate lifecycle coupling (CLI-6 AC50-AC57)"
```

---

### Task 7: Add global-check/local-report scoping and stdin pipelines

**Files:**
- Modify: `src/kb/core/validate.py`
- Modify: `src/kb/cli/validate.py`
- Modify: `tests/cli/test_validate.py`

**Interfaces:**
- Consumes: Task 1's complete universe, `ID_REF_PATTERN`, the scan id map, and already globally computed findings.
- Produces: `_resolve_scope()` returning `(scope_paths, unresolved_refs)`, argument-wins stdin collection, stable ref/scope deduplication, filtered findings, scoped `checked`, and AC58–AC64.

- [ ] **Step 1: Write AC58–AC64**

Append to `tests/cli/test_validate.py`:

```python
def scoped_pair(root: Path) -> None:
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(id="KB-000001"))
    bad = valid_synthetic_values(id="KB-000002")
    del bad["title"]
    make_doc(root, "synthetic/b.md", bad)


def test_ac58_scope_hides_other_files_findings_and_gate(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    scoped_pair(root)
    result = invoke_validate(root, "synthetic/a.md")
    assert result.exit_code == 0
    assert result.stdout == "no findings — checked 1 files\n"


def test_ac59_id_and_extensionless_path_scope_to_the_same_document(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    scoped_pair(root)
    by_id = invoke_validate(root, "KB-000002")
    by_path = invoke_validate(root, "synthetic/b")
    assert by_id.exit_code == by_path.exit_code == 1
    assert by_id.stdout == by_path.stdout
    assert "synthetic/b.md" in by_id.stdout


def test_ac60_piped_refs_work_and_arguments_win_over_stdin(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    scoped_pair(root)
    piped = invoke_validate(root, input="\nsynthetic/b.md\n\n")
    assert piped.exit_code == 1 and "synthetic/b.md" in piped.stdout
    arguments = invoke_validate(root, "synthetic/a.md", input="synthetic/b.md\n")
    assert arguments.exit_code == 0
    assert "synthetic/b.md" not in arguments.stdout


def test_ac61_global_duplicate_check_reports_only_the_scoped_anchor(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(id="KB-000007"))
    make_doc(root, "synthetic/b.md", valid_synthetic_values(id="KB-000007"))
    result = invoke_validate(root, "synthetic/a.md", "--json")
    duplicates = [item for item in finding_payload(result) if item["code"] == "ID_DUPLICATE"]
    assert len(duplicates) == 1
    assert duplicates[0]["path"] == "synthetic/a.md"
    assert "synthetic/b.md" in duplicates[0]["message"]


def test_ac62_malformed_file_resolves_by_path(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    path = root / "raw/sources/broken.md"
    path.parent.mkdir(parents=True)
    path.write_text("broken\n", encoding="utf-8")
    result = invoke_validate(root, "raw/sources/broken.md")
    assert result.exit_code == 1
    assert "FM0_UNPARSEABLE" in result.stdout
    assert "checked 1 files" in result.stdout


def test_ac63_unresolvable_ref_is_a_batch_diagnostic_and_exit_one(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values())
    result = invoke_validate(root, "KB-999999", "synthetic/a.md")
    assert result.exit_code == 1
    assert result.stderr == "unresolvable ref: KB-999999\n"
    assert result.stdout == "no findings — checked 1 files\n"


def test_ac64_duplicate_refs_are_silently_deduplicated(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values())
    once = invoke_validate(root, "KB-000001")
    twice = invoke_validate(root, "KB-000001", "KB-000001")
    assert twice.exit_code == once.exit_code
    assert twice.stdout == once.stdout
    assert twice.stderr == once.stderr == ""
```

- [ ] **Step 2: Run scoping tests and verify they fail**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac58 or ac59 or ac60 or ac61 or ac62 or ac63 or ac64' -v`

Expected: FAIL because Task 2 ignores `ValidateRequest.refs` and does not read stdin.

- [ ] **Step 3: Resolve refs against ids and the complete universe**

Add imports and helpers to `src/kb/core/validate.py`:

```python
from pathlib import Path, PurePosixPath

from kb.core.scan import ID_REF_PATTERN


def _stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _path_ref(ref: str) -> Path | None:
    candidate = PurePosixPath(ref)
    if candidate.is_absolute() or "." in candidate.parts or ".." in candidate.parts:
        return None
    if not str(candidate).endswith(".md"):
        candidate = PurePosixPath(f"{candidate}.md")
    return Path(*candidate.parts)


def _resolve_scope(kb: KB, refs: list[str]) -> tuple[set[Path], list[str]]:
    universe = {file.path for file in kb.files}
    if not refs:
        return universe, []
    scope: set[Path] = set()
    unresolved: list[str] = []
    for ref in _stable_unique(refs):
        resolved: Path | None
        if ID_REF_PATTERN.fullmatch(ref):
            document = kb.by_id.get(ref)
            resolved = None if document is None else document.path
        else:
            candidate = _path_ref(ref)
            resolved = candidate if candidate in universe else None
        if resolved is None:
            unresolved.append(ref)
        else:
            scope.add(resolved)
    return scope, unresolved
```

Replace the final part of `validate()` after `kb = scan(root)` with:

```python
    all_findings = _all_findings(kb, config)
    scope, unresolved = _resolve_scope(kb, request.refs)
    findings = [item for item in all_findings if Path(item.path) in scope]
    failed = bool(unresolved) or any(item.severity == "error" for item in findings)
    if request.strict and findings:
        failed = True
    return ValidateResult(
        checked=len(scope),
        findings=findings,
        unresolved_refs=unresolved,
        exit_code=1 if failed else 0,
    )
```

- [ ] **Step 4: Read stdin only when positional refs are absent**

Add this helper to `src/kb/cli/validate.py` and use it when constructing `ValidateRequest`:

```python
def _effective_refs(argument_refs: list[str]) -> list[str]:
    if argument_refs:
        return argument_refs
    stream = typer.get_text_stream("stdin")
    if stream.isatty():
        return []
    return [line.strip() for line in stream if line.strip()]
```

Replace `refs=refs or []` with:

```python
            refs=_effective_refs(refs or []),
```

After a successful core call and before stdout rendering, emit batch diagnostics:

```python
    for ref in result.unresolved_refs:
        typer.echo(f"unresolvable ref: {ref}", err=True)
```

- [ ] **Step 5: Run scoping, pipeline, and cumulative tests**

Run: `uv run pytest tests/cli/test_validate.py -v`

Expected: AC1–AC64 pass. AC61 proves duplicate detection remains global; AC58 proves out-of-scope errors do not affect the exit code.

- [ ] **Step 6: Commit scoping and pipelines**

```bash
git add src/kb/core/validate.py src/kb/cli/validate.py tests/cli/test_validate.py
git commit -m "feat: scope validate reports and pipelines (CLI-6 AC58-AC64)"
```

---

### Task 8: Pin output/JSON/errors/help/Git behavior and activate the init gate

**Files:**
- Modify: `src/kb/cli/render.py`
- Modify: `tests/cli/test_validate.py`
- Modify: `tests/cli/test_init.py:649-654`

**Interfaces:**
- Consumes: complete `ValidateResult` semantics, shared error renderers, normative command copy, and all prior rule/scoping behavior.
- Produces: exact singular/plural summaries, stable JSON schema, command-level error envelopes, normative help coverage, Git-agnostic/read-only proof, AC65–AC74, and a hard-passing init AC30.

- [ ] **Step 1: Write AC65–AC69 output and JSON tests**

Append to `tests/cli/test_validate.py`:

```python
def error_and_warning_kb(root: Path) -> None:
    chat(root)
    values = valid_synthetic_values(description="One. Two. Three.")
    del values["title"]
    make_doc(root, "synthetic/note.md", values)


def test_ac65_text_lines_summary_counts_and_channels_are_exact(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    error_and_warning_kb(root)
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "warning  synthetic/note.md  FM1_DESCRIPTION_LONG  description exceeds two sentences",
        "error  synthetic/note.md  FM1_FIELD_MISSING  missing mandatory field 'title' for synthetic documents",
        "2 findings (1 error, 1 warning) — checked 2 files",
    ]


def test_ac66_findings_sort_by_path_then_code(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "z.md").write_text("broken\n", encoding="utf-8")
    make_doc(root, "a.md", {"type": "spec"})
    make_doc(root, "m.md", {"type": "index"})
    result = invoke_validate(root, "--json")
    pairs = [(item["path"], item["code"]) for item in finding_payload(result)]
    assert pairs == sorted(pairs)


def test_ac67_json_schema_is_exact_and_id_is_nullable(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    error_and_warning_kb(root)
    result = invoke_validate(root, "--json")
    payload = json.loads(result.stdout)
    assert result.exit_code == 1 and result.stderr == ""
    assert set(payload) == {"ok", "checked", "findings", "counts", "unresolved_refs"}
    assert payload["ok"] is False
    assert isinstance(payload["checked"], int)
    assert payload["counts"] == {"errors": 1, "warnings": 1}
    assert payload["unresolved_refs"] == []
    assert all(set(item) == {"code", "severity", "path", "id", "message"} for item in payload["findings"])
    assert all(item["id"] == "KB-000001" for item in payload["findings"])
    root = make_kb(tmp_path / "null-id")
    (root / "README.md").write_text("broken\n", encoding="utf-8")
    malformed = invoke_validate(root, "--json")
    assert finding_payload(malformed)[0]["id"] is None


def test_ac68_json_ok_is_equivalent_to_exit_zero(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "warnings")
    synthetic(root, description="One. Two. Three.")
    normal = invoke_validate(root, "--json")
    strict = invoke_validate(root, "--strict", "--json")
    assert normal.exit_code == 0 and json.loads(normal.stdout)["ok"] is True
    assert strict.exit_code == 1 and json.loads(strict.stdout)["ok"] is False
    root = make_kb(tmp_path / "unresolved")
    unresolved = invoke_validate(root, "KB-999999", "--json")
    payload = json.loads(unresolved.stdout)
    assert unresolved.exit_code == 1 and payload["ok"] is False
    assert payload["unresolved_refs"] == ["KB-999999"]


def test_ac69_clean_json_envelope_has_zero_counts(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    result = invoke_validate(root, "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "checked": 0,
        "findings": [],
        "counts": {"errors": 0, "warnings": 0},
        "unresolved_refs": [],
    }
```

- [ ] **Step 2: Write AC70–AC74 command failure, help, and Git tests**

Add `import subprocess` near the top of `tests/cli/test_validate.py`, then append:

```python
def test_ac70_no_kb_errors_are_shared_in_text_and_json(tmp_path, runner, invoke_validate) -> None:
    text = invoke_validate(tmp_path)
    explicit = invoke_validate(tmp_path, "--kb", str(tmp_path / "missing"))
    json_result = invoke_validate(tmp_path, "--json")
    message = "not inside a knowledge base (no kb-config.json found); run 'kb init' or pass --kb"
    assert text.exit_code == explicit.exit_code == json_result.exit_code == 2
    assert text.stderr == f"E_NO_KB: {message}\n"
    assert "E_NO_KB" in explicit.stderr
    assert json.loads(json_result.stdout) == {"error": {"code": "E_NO_KB", "message": message}}


def test_ac71_invalid_config_is_a_command_error(tmp_path, invoke_validate) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    (root / "kb-config.json").write_text("{", encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 2
    assert "E_CONFIG_INVALID" in result.stderr
    assert result.stdout == ""


def test_ac72_newer_schema_is_unsupported(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    config_path = root / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["schema"] = 999
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 2
    assert "E_SCHEMA_UNSUPPORTED" in result.stderr


def test_ac73_usage_and_help_copy_are_normative(tmp_path, invoke_validate) -> None:
    bad = invoke_validate(tmp_path, "--bogus-flag")
    assert bad.exit_code == 2 and bad.stderr
    help_result = invoke_validate(tmp_path, "--help")
    normalized = " ".join(help_result.stdout.split())
    required = [
        "Check the knowledge base's mechanical integrity.",
        "The single authoritative integrity checker and CI gate: verifies every rule checkable without judgment — universal type and type/location agreement, per-class frontmatter schemas, type and tag vocabularies, id format and uniqueness, link resolution, derivation-graph acyclicity, session parentage, and supersedes/status coupling.",
        "Reports every finding with a stable code and severity; errors exit 1, warnings exit 0 unless --strict.",
        "Reads everything, writes nothing.",
        "With REF arguments (or refs piped on stdin), only findings for the named documents are reported.",
        "Does not touch Git.",
        "Documents to report findings for (id or KB-relative path). Also read from stdin when piped. [default: the whole KB]",
        "Treat warnings as errors for the exit code.",
        "KB root. [default: discovered upward from the current directory]",
        "Emit findings as JSON.",
        "kb validate Check the whole KB (the CI gate)",
        "kb validate --strict Warnings fail the run too",
        "kb validate KB-000042 synthetic/notes.md Only findings for the named documents",
        "kb search \"retry\" --output paths | kb validate Validate a piped candidate set",
        "kb validate --json Machine-readable findings",
    ]
    assert help_result.exit_code == 0
    for text in required:
        assert " ".join(text.split()) in normalized


def test_ac74_validate_is_git_agnostic(tmp_path, invoke_validate, monkeypatch) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "README.md").write_text("broken\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError(f"subprocess invocation is forbidden: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_call", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert not (root / ".git").exists()
```

- [ ] **Step 3: Run AC65–AC74 and inspect failures**

Run: `uv run pytest tests/cli/test_validate.py -k 'ac65 or ac66 or ac67 or ac68 or ac69 or ac70 or ac71 or ac72 or ac73 or ac74' -v`

Expected: output tests reveal any copy/count/schema mismatch; environment and Git tests should pass through the typed core/CLI boundaries already built.

- [ ] **Step 4: Correct singular/plural summary grammar**

Replace the finding-summary branch in `render_validate_text()` with:

```python
    if total == 0:
        lines.append(f"no findings — checked {result.checked} files")
    else:
        finding_noun = "finding" if total == 1 else "findings"
        error_noun = "error" if errors == 1 else "errors"
        warning_noun = "warning" if warnings == 1 else "warnings"
        lines.append(
            f"{total} {finding_noun} ({errors} {error_noun}, "
            f"{warnings} {warning_noun}) — checked {result.checked} files"
        )
```

Keep `render_validate_json()` explicitly selecting the five public finding fields, so the private occurrence attribute can never leak even if Pydantic serialization defaults change:

```python
            "findings": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "path": item.path,
                    "id": item.id,
                    "message": item.message,
                }
                for item in result.findings
            ],
```

- [ ] **Step 5: Activate the existing fresh-scaffold gate**

In `tests/cli/test_init.py`, delete only this marker:

```python
@pytest.mark.xfail(reason="kb validate is not implemented yet", strict=True)
```

Do not change the body of `test_ac30_fresh_scaffold_is_born_valid`; it must now pass as a hard regression gate.

- [ ] **Step 6: Run every validate and init acceptance test**

Run: `uv run pytest tests/core/test_validate.py tests/cli/test_validate.py tests/cli/test_init.py -v`

Expected: all tests pass with no xfail/xpass; `test_ac30_fresh_scaffold_is_born_valid` is a normal PASS.

- [ ] **Step 7: Run the complete repository regression suite**

Run: `uv run pytest -q`

Expected: all tests pass with no failure, xfail, xpass, warning, or unexpected skip.

- [ ] **Step 8: Verify the implementation remains read-only and dependency-neutral**

Run:

```bash
git diff --check
git diff -- pyproject.toml uv.lock
rg -n "subprocess|os\.system|git " src/kb/core/validate.py src/kb/cli/validate.py
```

Expected: `git diff --check` is silent; the dependency diff is empty; the source search has no matches.

- [ ] **Step 9: Commit the output contract and completed command**

```bash
git add src/kb/cli/render.py tests/cli/test_validate.py tests/cli/test_init.py
git commit -m "test: complete validate contract (CLI-6 CLI-12 AC65-AC74)"
```

---

## Final Verification Checklist

- [ ] `uv run pytest tests/core/test_scan.py tests/core/test_validate.py tests/cli/test_validate.py tests/cli/test_init.py -v` passes with no xfail/xpass.
- [ ] `uv run pytest -q` passes the complete repository suite.
- [ ] The AC01 through AC74 test functions each appear exactly once in `tests/cli/test_validate.py`.
- [ ] Every finding code has a triggering test and a clean-negative assertion.
- [ ] A fresh scaffold prints exactly `no findings — checked 11 files`.
- [ ] A config-only KB prints exactly `no findings — checked 0 files`.
- [ ] Scoped runs compute all global checks first, then filter by finding anchor.
- [ ] `--strict` changes only `exit_code`/JSON `ok`, never finding lines or order.
- [ ] Malformed and operational files resolve by path, never by a hidden/non-document id.
- [ ] Text/JSON channels and all singular/plural forms match §6.
- [ ] No KB bytes, indexes, logs, caches, Git state, dependencies, or specs are changed by the implementation.
