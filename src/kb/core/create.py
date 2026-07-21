from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from kb.core.frontmatter import render_synthetic_document, replace_frontmatter_scalars
from kb.core.housekeeping import LogEntry, append_log, utc_now
from kb.core.ids import next_id
from kb.core.indexing import (
    file_listing_line,
    regenerate_directory_index,
    render_index,
    subdirectory_listing_line,
)
from kb.core.naming import slug
from kb.core.model import (
    Config,
    ConfigLoadError,
    DocClass,
    Document,
    SyntheticFrontmatter,
    load_config,
)
from kb.core.safeio import (
    FileIdentity,
    create_file_bytes,
    inspect_mutable_file,
    overwrite_mutable_bytes,
    read_mutable_bytes,
)
from kb.core.scan import KB, RootDiscoveryError, discover_root, resolve_ref, scan

CreateStatus = Literal["draft", "current"]

RESERVED_TYPES = {
    "index",
    "log",
    "raw-source",
    "chat",
    "feedback",
    "conventions",
    "kb-config",
    "health",
}
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


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


def _invalid_destination(dest: str | None) -> CreateFailure:
    shown = "synthetic/" if dest is None else dest
    return CreateFailure("E_CREATE_DEST_INVALID", f"invalid --dest: {shown}", 2)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _target_directory(root: Path, dest: str | None) -> tuple[Path, list[Path]]:
    base = root / "synthetic"
    normalized = "" if dest is None else dest.rstrip("/")
    raw_parts = [] if dest is None else normalized.split("/")
    candidate = PurePosixPath(normalized)
    if dest is not None and (
        not normalized
        or "\\" in normalized
        or candidate.is_absolute()
        or any(part in {".", ".."} for part in raw_parts)
    ):
        raise _invalid_destination(dest)
    target = base.joinpath(*candidate.parts)
    missing: list[Path] = []
    current = root
    components = ("synthetic", *candidate.parts)
    for part in components:
        current /= part
        if _is_link_or_junction(current):
            raise _invalid_destination(dest)
        if current.exists() and not current.is_dir():
            raise _invalid_destination(dest)
        if not current.exists():
            missing.append(current)
    real_base = base.resolve(strict=False)
    real_target = target.resolve(strict=False)
    if real_target != real_base and real_base not in real_target.parents:
        raise _invalid_destination(dest)
    return target, missing


def _warnings(config: Config, request: CreateRequest, tags: list[str]) -> list[str]:
    if request.type_name in RESERVED_TYPES:
        raise CreateFailure(
            "E_CREATE_TYPE_RESERVED",
            f"reserved synthetic document type: {request.type_name}",
            2,
        )
    warnings: list[str] = []
    if request.type_name not in config.types:
        warnings.append(
            f"warning: type is not declared in kb-config.json: {request.type_name}"
        )
    warnings.extend(
        f"warning: tag is not declared in kb-config.json: {tag}"
        for tag in tags
        if tag not in config.tags
    )
    if len(SENTENCE_END.findall(request.description)) > 2:
        warnings.append("warning: description is longer than two sentences")
    return warnings


def _new_index_contents(
    root: Path,
    missing: list[Path],
    *,
    filename: str,
    doc_id: str,
    title: str,
    description: str,
) -> dict[Path, str]:
    contents: dict[Path, str] = {}
    for offset, directory in enumerate(reversed(missing)):
        relative = directory.relative_to(root).as_posix()
        index_description = f"Documents under {relative}/."
        if offset == 0:
            listing = "## Files\n" + file_listing_line(
                filename, doc_id, title, description
            )
        else:
            child = missing[len(missing) - offset]
            child_relative = child.relative_to(root).as_posix()
            listing = "## Subdirectories\n" + subdirectory_listing_line(
                child.name, f"Documents under {child_relative}/."
            )
        contents[directory / "index.md"] = render_index(
            directory.name, index_description, listing
        )
    return contents


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


def _superseded_bytes(
    root: Path,
    document: Document,
    timestamp: str,
    identity: FileIdentity,
) -> bytes:
    return replace_frontmatter_scalars(
        read_mutable_bytes(root / document.path, identity),
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
    target_dir, missing_directories = _target_directory(root, request.dest)
    tags = _stable_unique(request.tags)
    warnings = _warnings(config, request, tags)
    body = _body(request)
    parents = _parents(kb, request.derived_from)
    superseded_document = _resolve_supersedes(kb, request.supersedes)
    if superseded_document is not None and superseded_document.id not in parents:
        parents.append(superseded_document.id)
    _require_parents(parents)
    doc_id = next_id(kb, config.id_prefixes["synthetic"]).format()
    stem = slug(request.title, doc_id)
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
        tags=tags or None,
        supersedes=superseded_document.id if superseded_document else None,
        instructions=request.instructions,
    )
    document_content = render_synthetic_document(frontmatter, body)
    relative = path.relative_to(root).as_posix()
    new_indexes = _new_index_contents(
        root,
        missing_directories,
        filename=path.name,
        doc_id=doc_id,
        title=request.title,
        description=request.description,
    )
    existing_index_dir = (
        missing_directories[0].parent if missing_directories else target_dir
    )
    existing_index = existing_index_dir / "index.md"
    superseded_identity: FileIdentity | None = None
    if superseded_document is not None:
        try:
            inspected = inspect_mutable_file(root / superseded_document.path)
            if inspected is None:
                raise OSError("supersedes target disappeared")
            superseded_identity = inspected
        except OSError as error:
            raise CreateFailure(
                "E_CREATE_SUPERSEDES_INVALID",
                f"supersedes target cannot be updated safely: {request.supersedes}: "
                f"{error}",
                1,
            ) from error
    try:
        inspected_index = inspect_mutable_file(existing_index)
        if inspected_index is None:
            raise OSError("index disappeared")
        existing_index_identity = inspected_index
        log_identity = inspect_mutable_file(root / "log.md", allow_missing=True)
    except OSError as error:
        raise CreateFailure("E_CREATE_IO", str(error), 2) from error
    try:
        superseded_content = (
            _superseded_bytes(
                root, superseded_document, timestamp, superseded_identity
            )
            if superseded_document is not None and superseded_identity is not None
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
        for directory in missing_directories:
            directory.mkdir()
            index_path = directory / "index.md"
            index_path.write_text(
                new_indexes[index_path], encoding="utf-8", newline="\n"
            )
        create_file_bytes(path, document_content.encode("utf-8"))
        if (
            superseded_document is not None
            and superseded_content is not None
            and superseded_identity is not None
        ):
            overwrite_mutable_bytes(
                root / superseded_document.path,
                superseded_content,
                superseded_identity,
            )
        overwrite_mutable_bytes(
            existing_index,
            regenerate_directory_index(root, existing_index_dir).encode("utf-8"),
            existing_index_identity,
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
            expected_identity=log_identity,
        )
    except OSError as error:
        raise CreateFailure("E_CREATE_IO", str(error), 2) from error
    created = [relative] + [
        path.relative_to(root).as_posix() for path in new_indexes
    ]
    updated = [existing_index.relative_to(root).as_posix()]
    if superseded_document is not None:
        updated.append(superseded_document.path.as_posix())
    return CreateResult(
        id=doc_id,
        path=relative,
        superseded=superseded_document.id if superseded_document else None,
        created=sorted(created),
        updated=sorted(updated),
        warnings=warnings,
    )
