from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from kb.core.frontmatter import render_synthetic_document
from kb.core.housekeeping import LogEntry, append_log, utc_now
from kb.core.ids import next_id
from kb.core.indexing import regenerate_directory_index
from kb.core.ingest import slug
from kb.core.model import ConfigLoadError, SyntheticFrontmatter, load_config
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
    parents: list[str] = []
    for ref in refs:
        document = resolve_ref(kb, ref)
        if document is None or document.id is None:
            raise CreateFailure(
                "E_CREATE_PARENT_UNRESOLVED",
                f"parent cannot be resolved to a document id: {ref}",
                1,
            )
        parents.append(document.id)
    parents = _stable_unique(parents)
    if not parents:
        raise CreateFailure(
            "E_CREATE_NO_PARENTS",
            "at least one --derived-from or --supersedes parent is required",
            2,
        )
    return parents


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
    doc_id = next_id(kb, config.id_prefixes["synthetic"]).format()
    stem = slug(request.title, doc_id)
    target_dir = root / "synthetic"
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
    )
    relative = path.relative_to(root).as_posix()
    index = target_dir / "index.md"
    try:
        path.write_text(
            render_synthetic_document(frontmatter, body),
            encoding="utf-8",
            newline="\n",
        )
        index.write_text(
            regenerate_directory_index(root, target_dir),
            encoding="utf-8",
            newline="\n",
        )
        append_log(
            root,
            LogEntry(
                at=timestamp,
                action="created",
                actor=request.actor,
                doc_ids=[doc_id],
                note=relative,
            ),
        )
    except OSError as error:
        raise CreateFailure("E_CREATE_IO", str(error), 2) from error
    return CreateResult(
        id=doc_id,
        path=relative,
        created=[relative],
        updated=[index.relative_to(root).as_posix()],
    )
