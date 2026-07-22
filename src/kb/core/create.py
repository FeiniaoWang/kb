from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from kb.core.frontmatter import render_synthetic_document, replace_frontmatter_scalars
from kb.core.housekeeping import LogEntry, utc_now
from kb.core.ids import next_id
from kb.core.naming import slug
from kb.core.model import (
    Config,
    ConfigLoadError,
    DocClass,
    Document,
    SyntheticFrontmatter,
)
from kb.core.scan import ID_REF_PATTERN, KB, RootDiscoveryError, resolve_ref
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


def _unsafe_path_is_supersedes_target(
    error: WriteFailure,
    ref: str | None,
) -> bool:
    if ref is None:
        return False
    if ID_REF_PATTERN.fullmatch(ref):
        if error.snapshot_kb is None:
            return False
        document = resolve_ref(error.snapshot_kb, ref)
        return document is not None and document.path == error.path
    candidate = PurePosixPath(ref)
    if (
        candidate.is_absolute()
        or "\\" in ref
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        return False
    if candidate.suffix != ".md":
        candidate = PurePosixPath(f"{candidate}.md")
    return Path(*candidate.parts) == error.path


def create(request: CreateRequest) -> CreateResult:
    try:
        context = load_write_context(request.kb_root)
    except RootDiscoveryError as error:
        raise CreateFailure(error.code, error.message, 2) from error
    except ConfigLoadError as error:
        raise CreateFailure(error.code, error.message, 2) from error
    except WriteFailure as error:
        if _unsafe_path_is_supersedes_target(error, request.supersedes):
            raise CreateFailure(
                "E_CREATE_SUPERSEDES_INVALID",
                f"supersedes target cannot be updated safely: "
                f"{request.supersedes}: {error.cause}",
                1,
            ) from error
        raise CreateFailure("E_CREATE_IO", str(error.cause), 2) from error
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
    target_dir, _ = _target_directory(root, request.dest)
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
    implicit_index_path = target_dir / "index.md"
    superseded_path = (
        root / superseded_document.path if superseded_document is not None else None
    )
    suffix = f"-{doc_id.lower()}"
    while (
        path.exists()
        or path == superseded_path
        or path == implicit_index_path
    ):
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
    return CreateResult(
        id=doc_id,
        path=relative,
        superseded=superseded_document.id if superseded_document else None,
        created=receipt.created,
        updated=receipt.updated,
        warnings=warnings,
    )
