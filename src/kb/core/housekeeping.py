from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from kb.core.indexing import render_index


class LogEntry(BaseModel):
    at: str
    action: str
    actor: str
    doc_ids: list[str] = Field(default_factory=list)
    note: str


class ScaffoldEntry(BaseModel):
    content: str
    cli_owned: bool


class InitResult(BaseModel):
    root: Path
    created: list[str] = Field(default_factory=list)
    overwritten: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class InitFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _io_failure(error: Exception, fallback: Path | None) -> InitFailure:
    os_message = (
        error.strerror or str(error) if isinstance(error, OSError) else str(error)
    )
    source = (
        Path(error.filename)
        if isinstance(error, OSError) and error.filename
        else fallback
    )
    if source is None:
        return InitFailure("E_INIT_IO", os_message)
    try:
        offending = source.absolute()
    except (OSError, RuntimeError):
        offending = source
    return InitFailure("E_INIT_IO", f"{offending}: {os_message}")


def _reject_manifest_link(path: Path) -> None:
    is_junction = getattr(path, "is_junction", lambda: False)
    if path.is_symlink() or is_junction():
        raise InitFailure(
            "E_INIT_IO",
            f"manifest path must not be a symlink or junction: {path}",
        )


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _inspect_manifest_target(
    root: Path, target: Path, *, create_parents: bool
) -> os.stat_result | None:
    current = root
    for part in target.relative_to(root).parts[:-1]:
        current /= part
        _reject_manifest_link(current)
        current_stat = _lstat_or_none(current)
        if current_stat is None and create_parents:
            current.mkdir()
            _reject_manifest_link(current)
            current_stat = current.lstat()
        if current_stat is None or not stat.S_ISDIR(current_stat.st_mode):
            raise InitFailure(
                "E_INIT_IO",
                f"manifest path parent is not a directory: {current}",
            )
    _reject_manifest_link(target)
    return _lstat_or_none(target)


def _open_flags(flags: int) -> int:
    return flags | getattr(os, "O_NOFOLLOW", 0)


def _write_manifest_text(path: Path, content: str, *, create: bool) -> None:
    flags = os.O_WRONLY
    flags |= os.O_CREAT | os.O_EXCL if create else os.O_TRUNC
    descriptor = os.open(path, _open_flags(flags), 0o666)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _read_manifest_text(path: Path) -> str:
    descriptor = os.open(path, _open_flags(os.O_RDONLY))
    with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as stream:
        return stream.read()


def _append_manifest_text(path: Path, content: str) -> None:
    descriptor = os.open(path, _open_flags(os.O_WRONLY | os.O_APPEND))
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def format_log_entry(entry: LogEntry) -> str:
    ids = ",".join(entry.doc_ids) if entry.doc_ids else "-"
    return f"- {entry.at} | {entry.action} | {entry.actor} | {ids} | {entry.note}"


def _utc_now() -> str:
    value = datetime.now(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return _utc_now()


ROOT_LISTING = """## Subdirectories
* [Governance](governance/index.md) - Project governance — configuration, conventions, and templates.
* [Raw Evidence](raw/index.md) - Immutable evidence — sources, session records, and feedback.
* [Synthetic Documents](synthetic/index.md) - Human-created, agent-maintained documents (the derivation graph)."""

GOVERNANCE_LISTING = """## Subdirectories
* [Templates](templates/index.md) - Optional per-type document templates.

## Files
* [GOVERNANCE-CONVENTIONS][Project Conventions](conventions.md) - Standing conventions for this knowledge base. Human-maintained.
* [GOVERNANCE-KB-CONFIG][KB Configuration Reference](kb-config.md) - Explains each field in the root kb-config.json. Human-readable companion to the machine-read config."""

RAW_LISTING = """## Subdirectories
* [Session Records](chats/index.md) - Session records from kb-author and kb-ingest sessions (immutable).
* [Feedback](feedback/index.md) - Consumer feedback about synthetic documents (immutable).
* [Sources](sources/index.md) - Normalized external evidence (immutable)."""

CONFIG_CONTENT = """{
  "schema": 1,
  "types": [],
  "tags": [],
  "id_prefixes": {
    "synthetic": "KB",
    "source": "RAW",
    "chat": "CHAT",
    "feedback": "FEED"
  },
  "propagation_auto_safe": []
}
"""

CONVENTIONS_CONTENT = """---
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
"""

CONFIG_REFERENCE_CONTENT = """---
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
- **`id_prefixes`** — the id prefix used per document class: `synthetic` (`KB`),
  `source` (`RAW`), `chat` (`CHAT`), `feedback` (`FEED`). Ids are `<PREFIX>-<6+ digits>`.
- **`propagation_auto_safe`** — change classes governance considers auto-safe
  during propagation (CS3). Start empty; expand from field data (PRD OQ1).
"""


def empty_log_content() -> str:
    return (
        "---\ntype: log\n---\n"
        "<!-- KB history — append-only; written by `kb log`. Format: - <UTC ISO> | <action> | <actor> | <ids or -> | <note> -->\n"
        "# Knowledge Base Log\n\n"
    )


def _log_content(timestamp: str) -> str:
    entry = format_log_entry(
        LogEntry(
            at=timestamp,
            action="initialized",
            actor="kb-cli",
            doc_ids=[],
            note="KB scaffolded by kb init",
        )
    )
    return f"{empty_log_content()}{entry}\n"


def append_log(root: Path, entry: LogEntry) -> None:
    path = root / "log.md"
    if not path.exists():
        path.write_text(empty_log_content(), encoding="utf-8", newline="\n")
    existing = path.read_text(encoding="utf-8")
    separator = "" if existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{separator}{format_log_entry(entry)}\n")


def _manifest(timestamp: str) -> dict[str, ScaffoldEntry]:
    return {
        "governance/conventions.md": ScaffoldEntry(
            content=CONVENTIONS_CONTENT, cli_owned=False
        ),
        "governance/index.md": ScaffoldEntry(
            content=render_index(
                "Governance",
                "Project governance — configuration, conventions, and templates.",
                GOVERNANCE_LISTING,
            ),
            cli_owned=True,
        ),
        "governance/kb-config.md": ScaffoldEntry(
            content=CONFIG_REFERENCE_CONTENT, cli_owned=False
        ),
        "governance/templates/index.md": ScaffoldEntry(
            content=render_index("Templates", "Optional per-type document templates."),
            cli_owned=True,
        ),
        "index.md": ScaffoldEntry(
            content=render_index(
                "Knowledge Base",
                "Root of the knowledge base — raw evidence, synthetic documents, and governance.",
                ROOT_LISTING,
            ),
            cli_owned=True,
        ),
        "kb-config.json": ScaffoldEntry(content=CONFIG_CONTENT, cli_owned=True),
        "log.md": ScaffoldEntry(content=_log_content(timestamp), cli_owned=False),
        "raw/chats/index.md": ScaffoldEntry(
            content=render_index(
                "Session Records",
                "Session records from kb-author and kb-ingest sessions (immutable).",
            ),
            cli_owned=True,
        ),
        "raw/feedback/index.md": ScaffoldEntry(
            content=render_index(
                "Feedback", "Consumer feedback about synthetic documents (immutable)."
            ),
            cli_owned=True,
        ),
        "raw/index.md": ScaffoldEntry(
            content=render_index(
                "Raw Evidence",
                "Immutable evidence — sources, session records, and feedback.",
                RAW_LISTING,
            ),
            cli_owned=True,
        ),
        "raw/sources/index.md": ScaffoldEntry(
            content=render_index("Sources", "Normalized external evidence (immutable)."),
            cli_owned=True,
        ),
        "synthetic/index.md": ScaffoldEntry(
            content=render_index(
                "Synthetic Documents",
                "Human-created, agent-maintained documents (the derivation graph).",
            ),
            cli_owned=True,
        ),
    }


def _ensure_initialized_log(root: Path, path: Path, timestamp: str) -> None:
    target_stat = _inspect_manifest_target(root, path, create_parents=False)
    if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
        raise InitFailure("E_INIT_IO", f"manifest path is not a file: {path}")
    existing = _read_manifest_text(path)
    for line in existing.splitlines():
        fields = line.split(" | ", 4)
        is_initialized = (
            len(fields) == 5
            and fields[0].startswith("- ")
            and fields[1] == "initialized"
        )
        if is_initialized:
            return
    entry = format_log_entry(
        LogEntry(
            at=timestamp,
            action="initialized",
            actor="kb-cli",
            doc_ids=[],
            note="KB scaffolded by kb init",
        )
    )
    separator = "" if not existing or existing.endswith("\n") else "\n"
    target_stat = _inspect_manifest_target(root, path, create_parents=False)
    if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
        raise InitFailure("E_INIT_IO", f"manifest path is not a file: {path}")
    _append_manifest_text(path, f"{separator}{entry}\n")


def init_kb(root: Path | None, *, force: bool = False) -> InitResult:
    try:
        requested = root if root is not None else Path.cwd()
        resolved = requested.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise _io_failure(error, root) from error
    if resolved.exists() and not resolved.is_dir():
        raise InitFailure(
            "E_INIT_NOT_DIR",
            f"target exists and is not a directory: {resolved}",
        )
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise _io_failure(error, resolved) from error

    timestamp = _utc_now()
    result = InitResult(root=resolved)
    for relative_path, entry in sorted(_manifest(timestamp).items()):
        target = resolved / relative_path
        try:
            target_stat = _inspect_manifest_target(
                resolved, target, create_parents=True
            )
            if target_stat is not None and not stat.S_ISREG(target_stat.st_mode):
                raise InitFailure("E_INIT_IO", f"manifest path is not a file: {target}")
            if target_stat is None:
                _write_manifest_text(target, entry.content, create=True)
                result.created.append(relative_path)
            elif force and entry.cli_owned:
                _write_manifest_text(target, entry.content, create=False)
                result.overwritten.append(relative_path)
            else:
                result.skipped.append(relative_path)
        except InitFailure:
            raise
        except OSError as error:
            raise _io_failure(error, target) from error
    try:
        _ensure_initialized_log(resolved, resolved / "log.md", timestamp)
    except InitFailure:
        raise
    except (OSError, UnicodeError) as error:
        raise _io_failure(error, resolved / "log.md") from error
    return result
