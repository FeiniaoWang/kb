from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from kb.core.frontmatter import render_synthetic_document, replace_frontmatter_scalars
from kb.core.housekeeping import LogEntry, append_log, utc_now
from kb.core.ids import next_id
from kb.core.indexing import regenerate_directory_index
from kb.core.ingest import slug
from kb.core.model import (
    ConfigLoadError,
    DocClass,
    Document,
    SyntheticFrontmatter,
    load_config,
)
from kb.core.scan import KB, RootDiscoveryError, discover_root, resolve_ref, scan

CreateStatus = Literal["draft", "current"]


class CreateRequest(BaseModel):
    type_name: str
    title: str
    description: str
    derived_from: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    status: CreateStatus = "draft"
    tags: list[str] = Field(default_factory=list)
    instructions: str | None = None
    body_file: str | None = None
    dest: str | None = None
    actor: str = "kb-cli"
    kb_root: Path | None = None


class CreateResult(BaseModel):
    id: str
    path: str
    superseded: str | None = None
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CreateFailure(Exception):
    def __init__(self, code: str, message: str, exit_code: Literal[1, 2]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _body(request: CreateRequest) -> str:
    if request.body_file is None:
        return ""
    if request.body_file == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
    else:
        path = Path(request.body_file).expanduser()
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_file():
                raise OSError("not a regular file")
            data = resolved.read_bytes()
        except OSError as error:
            raise CreateFailure(
                "E_CREATE_BODY_NOT_FOUND",
                f"body file is unavailable: {request.body_file}: {error}",
                2,
            ) from error
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CreateFailure(
            "E_CREATE_BODY_NOT_TEXT", "body is not UTF-8 text", 1
        ) from error
    if not decoded.strip():
        return ""
    return decoded.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def _parents(kb: KB, refs: list[str]) -> list[str]:
    canonical: list[str] = []
    for ref in refs:
        document = resolve_ref(kb, ref)
        if document is None or document.id is None:
            raise CreateFailure(
                "E_CREATE_PARENT_UNRESOLVED",
                f"parent cannot be resolved to a document id: {ref}",
                1,
            )
        canonical.append(document.id)
    return _stable_unique(canonical)


def _require_parents(parents: list[str]) -> None:
    if not parents:
        raise CreateFailure(
            "E_CREATE_NO_PARENTS",
            "at least one --derived-from or --supersedes parent is required",
            2,
        )


def _resolve_supersedes(kb: KB, ref: str | None) -> Document | None:
    if ref is None:
        return None
    document = resolve_ref(kb, ref)
    if document is None or document.id is None:
        raise CreateFailure(
            "E_CREATE_SUPERSEDES_UNRESOLVED",
            f"supersedes target cannot be resolved to a document id: {ref}",
            1,
        )
    status = document.frontmatter.root.get("status")
    if document.doc_class is not DocClass.SYNTHETIC or status not in {
        "draft",
        "current",
    }:
        raise CreateFailure(
            "E_CREATE_SUPERSEDES_INVALID",
            f"supersedes target is not a live synthetic document: {ref} "
            f"(status={status!r})",
            1,
        )
    return document


def _superseded_bytes(root: Path, document: Document, timestamp: str) -> bytes:
    return replace_frontmatter_scalars(
        (root / document.path).read_bytes(),
        {
            "status": "superseded",
            "timestamp": timestamp,
            "last_human_touch": timestamp,
        },
        append_missing=("timestamp", "last_human_touch"),
    )


def create(request: CreateRequest) -> CreateResult:
    try:
        root = discover_root(request.kb_root)
    except RootDiscoveryError as error:
        raise CreateFailure(error.code, error.message, 2) from error
    try:
        config = load_config(root)
    except ConfigLoadError as error:
        raise CreateFailure(error.code, error.message, 2) from error
    kb = scan(root)
    if kb.malformed:
        paths = ", ".join(path.as_posix() for path, _ in kb.malformed)
        raise CreateFailure(
            "E_CREATE_MALFORMED",
            f"malformed documents block id allocation: {paths}; run kb validate",
            2,
        )
    if request.dest is not None:
        raise CreateFailure(
            "E_CREATE_DEST_INVALID", f"invalid --dest: {request.dest}", 2
        )
    body = _body(request)
    parents = _parents(kb, request.derived_from)
    superseded_document = _resolve_supersedes(kb, request.supersedes)
    if superseded_document is not None and superseded_document.id not in parents:
        parents.append(superseded_document.id)
    _require_parents(parents)
    doc_id = next_id(kb, config.id_prefixes["synthetic"]).format()
    stem = slug(request.title, doc_id)
    target_dir = root / "synthetic"
    path = target_dir / f"{stem}.md"
    superseded_path = (
        root / superseded_document.path if superseded_document is not None else None
    )
    suffix = f"-{doc_id.lower()}"
    while path.exists() or path == superseded_path:
        stem += suffix
        path = target_dir / f"{stem}.md"
    timestamp = utc_now()
    frontmatter = SyntheticFrontmatter(
        id=doc_id,
        type=request.type_name,
        title=request.title,
        description=request.description,
        status=request.status,
        derived_from=parents,
        timestamp=timestamp,
        last_human_touch=timestamp,
        tags=_stable_unique(request.tags) or None,
        supersedes=superseded_document.id if superseded_document else None,
        instructions=request.instructions,
    )
    relative = path.relative_to(root).as_posix()
    index = target_dir / "index.md"
    try:
        superseded_content = (
            _superseded_bytes(root, superseded_document, timestamp)
            if superseded_document is not None
            else None
        )
    except OSError as error:
        raise CreateFailure("E_CREATE_IO", str(error), 2) from error
    except ValueError as error:
        raise CreateFailure(
            "E_CREATE_SUPERSEDES_INVALID",
            f"supersedes target cannot be updated safely: {request.supersedes}: "
            f"{error}",
            1,
        ) from error
    try:
        path.write_text(
            render_synthetic_document(frontmatter, body),
            encoding="utf-8",
            newline="\n",
        )
        if superseded_document is not None and superseded_content is not None:
            (root / superseded_document.path).write_bytes(superseded_content)
        index.write_text(
            regenerate_directory_index(root, target_dir),
            encoding="utf-8",
            newline="\n",
        )
        old_id = superseded_document.id if superseded_document else None
        append_log(
            root,
            LogEntry(
                at=timestamp,
                action="created",
                actor=request.actor,
                doc_ids=[doc_id] + ([old_id] if old_id else []),
                note=relative + (f" supersedes {old_id}" if old_id else ""),
            ),
        )
    except OSError as error:
        raise CreateFailure("E_CREATE_IO", str(error), 2) from error
    updated = [index.relative_to(root).as_posix()]
    if superseded_document is not None:
        updated.append(superseded_document.path.as_posix())
    return CreateResult(
        id=doc_id,
        path=relative,
        superseded=superseded_document.id if superseded_document else None,
        created=[relative],
        updated=sorted(updated),
    )
