from __future__ import annotations

import errno
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from kb.core.housekeeping import LogEntry, append_log
from kb.core.indexing import (
    file_listing_line,
    regenerate_directory_index,
    render_index,
    subdirectory_listing_line,
)
from kb.core.model import Config, load_config
from kb.core.safeio import (
    FileIdentity,
    create_file_bytes,
    inspect_mutable_file,
    overwrite_mutable_bytes,
    read_mutable_bytes,
)
from kb.core.scan import KB, discover_root, scan

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


class WriteReceipt(BaseModel):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)


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


def load_write_context(kb_root: Path | None) -> WriteContext:
    root = discover_root(kb_root)
    config = load_config(root)
    kb = scan(root)
    if kb.malformed:
        paths = tuple(sorted(path for path, _ in kb.malformed))
        raise AllocationBlocked(paths)
    return WriteContext(root=root, config=config, kb=kb)


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
    current = root
    for part in relative.parts:
        current /= part
        if _is_link_or_junction(current):
            raise ValueError(f"write path contains a symlink or junction: {shown}")
    resolved = (root / relative).resolve(strict=False)
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(f"write path escapes KB root: {shown}")
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
    for relative in [birth_relative, *companion_relatives]:
        absolute = root / relative
        if absolute.exists() and not absolute.is_file():
            raise ValueError(
                f"write birth must be a file path: {relative.as_posix()}"
            )

    target_dir = root / birth_relative.parent
    new_directories = _missing_directories(root, target_dir)
    refresh_directory = new_directories[0].parent if new_directories else target_dir
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
        assert identity is not None
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
    assert refresh_identity is not None
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


def apply_write(
    prepared: PreparedWrite,
    replacements: Mapping[str, bytes] | None = None,
) -> WriteReceipt:
    if prepared._consumed:
        raise ValueError("prepared write is already consumed")
    replacement_map = dict(replacements or {})
    expected_keys = set(prepared.sources)
    if set(replacement_map) != expected_keys:
        raise ValueError("replacement keys must exactly match prepared mutation keys")
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
                relative = _relative_path(root, source.path)
            except ValueError as error:
                cause = OSError(errno.ELOOP, str(error), root / source.path)
                raise WriteFailure(
                    "write",
                    "overwrite",
                    "mutation",
                    source.path,
                    cause,
                    key=mutation.key,
                ) from error
            try:
                overwrite_mutable_bytes(
                    root / relative,
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
