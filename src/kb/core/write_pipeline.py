from __future__ import annotations

import errno
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from kb.core.housekeeping import LogEntry, empty_log_content, format_log_entry
from kb.core.indexing import (
    file_listing_line,
    regenerate_directory_index,
    render_index,
    subdirectory_listing_line,
)
from kb.core.model import Config, load_config
from kb.core.safeio import (
    FileIdentity,
    append_rooted_bytes,
    create_rooted_directory,
    create_rooted_file_bytes,
    inspect_root,
    inspect_rooted_directory,
    inspect_rooted_file,
    overwrite_rooted_bytes,
    read_rooted_bytes,
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
    _root_identity: FileIdentity = PrivateAttr()
    _intent: WriteIntent = PrivateAttr()
    _mutation_identities: dict[str, FileIdentity] = PrivateAttr(default_factory=dict)
    _birth_relative: Path = PrivateAttr()
    _companion_relatives: list[Path] = PrivateAttr(default_factory=list)
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


def _relative_path(
    root: Path,
    value: Path,
    *,
    final_link_is_inspectable: bool = False,
) -> Path:
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
    checked_parts = (
        relative.parts[:-1] if final_link_is_inspectable else relative.parts
    )
    for part in checked_parts:
        current /= part
        if _is_link_or_junction(current):
            raise ValueError(f"write path contains a symlink or junction: {shown}")
    containment_path = relative.parent if final_link_is_inspectable else relative
    resolved = (root / containment_path).resolve(strict=False)
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


def _missing_directories(
    root: Path,
    target_dir: Path,
    root_identity: FileIdentity,
) -> list[Path]:
    missing: list[Path] = []
    current = Path()
    found_missing = False
    for part in target_dir.parts:
        current /= part
        if found_missing:
            missing.append(current)
            continue
        try:
            identity = inspect_rooted_directory(
                root,
                current,
                root_identity,
                allow_missing=True,
            )
        except OSError as error:
            if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise ValueError(
                    f"write destination component is not a directory: "
                    f"{current.as_posix()}"
                ) from error
            raise WriteFailure(
                "preflight",
                "inspect",
                "directory",
                current,
                error,
            ) from error
        if identity is None:
            found_missing = True
            missing.append(current)
    return missing


def _render_born_indexes(
    missing: list[Path],
    birth_relative: Path,
    document_listing: str,
) -> dict[Path, bytes]:
    if missing and birth_relative.parent != missing[-1]:
        raise ValueError("planned document parent does not match write destination")
    contents: dict[Path, bytes] = {}
    for offset, directory in enumerate(reversed(missing)):
        relative = directory.as_posix()
        if offset == 0:
            listing = "## Files\n" + document_listing
        else:
            child = missing[len(missing) - offset]
            child_relative = child.as_posix()
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
    root = context.root
    try:
        root_identity = inspect_root(root)
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "directory",
            Path("."),
            error,
        ) from error
    birth_relative = _relative_path(root, intent.birth.path)
    if birth_relative.suffix != ".md":
        raise ValueError("citable document birth must end in .md")
    companion_relatives = [
        _relative_path(root, companion.path)
        for companion in intent.birth.companions_before
    ]
    mutation_relatives = [
        _relative_path(
            root,
            mutation.path,
            final_link_is_inspectable=True,
        )
        for mutation in intent.mutations
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
    new_directories = _missing_directories(
        root,
        birth_relative.parent,
        root_identity,
    )
    refresh_directory = (
        new_directories[0].parent if new_directories else birth_relative.parent
    )
    refresh_index = refresh_directory / "index.md"
    born_indexes = {directory / "index.md" for directory in new_directories}
    implicit_paths = {Path("log.md"), refresh_index, *born_indexes}
    conflicts = sorted(set(all_paths) & implicit_paths)
    if conflicts:
        shown = ", ".join(path.as_posix() for path in conflicts)
        raise ValueError(f"write intent collides with implicit pipeline path: {shown}")

    if not new_directories:
        for role, relative in [
            ("document", birth_relative),
            *(("companion", path) for path in companion_relatives),
        ]:
            try:
                inspect_rooted_file(
                    root,
                    relative,
                    root_identity,
                    allow_missing=True,
                )
            except OSError as error:
                if error.errno in {errno.EINVAL, errno.ELOOP, errno.ENOTDIR}:
                    raise ValueError(
                        f"write birth must be a file path: {relative.as_posix()}"
                    ) from error
                raise WriteFailure(
                    "preflight",
                    "inspect",
                    role,
                    relative,
                    error,
                ) from error

    sources: dict[str, MutationSource] = {}
    mutation_identities: dict[str, FileIdentity] = {}
    for mutation, relative in zip(intent.mutations, mutation_relatives, strict=True):
        try:
            identity = inspect_rooted_file(root, relative, root_identity)
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
            content = read_rooted_bytes(root, relative, root_identity, identity)
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
        refresh_identity = inspect_rooted_file(root, refresh_index, root_identity)
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "index",
            refresh_index,
            error,
        ) from error
    assert refresh_identity is not None
    try:
        refresh_source = read_rooted_bytes(
            root,
            refresh_index,
            root_identity,
            refresh_identity,
        )
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "read",
            "index",
            refresh_index,
            error,
        ) from error
    try:
        log_identity = inspect_rooted_file(
            root,
            Path("log.md"),
            root_identity,
            allow_missing=True,
        )
    except OSError as error:
        raise WriteFailure(
            "preflight", "inspect", "log", Path("log.md"), error
        ) from error

    listing = _document_listing(intent.birth.content, birth_relative.name)
    new_indexes = _render_born_indexes(
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
                f"{new_directories[0].as_posix()}/.",
            )
        }
    )
    try:
        refresh_content = regenerate_directory_index(
            root,
            root / refresh_directory,
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
            refresh_index,
            cause,
        ) from error

    prepared = PreparedWrite(sources=sources)
    prepared._root = root
    prepared._root_identity = root_identity
    prepared._intent = intent.model_copy(deep=True)
    prepared._mutation_identities = mutation_identities
    prepared._birth_relative = birth_relative
    prepared._companion_relatives = companion_relatives
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
            *(path.as_posix() for path in new_indexes),
        ]
    )
    prepared._updated = sorted(
        [
            *(path.as_posix() for path in mutation_relatives),
            refresh_index.as_posix(),
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
    root_identity = prepared._root_identity
    intent = prepared._intent
    try:
        for directory in prepared._new_directories:
            try:
                create_rooted_directory(root, directory, root_identity)
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "mkdir",
                    "directory",
                    directory,
                    error,
                ) from error
            index_relative = directory / "index.md"
            try:
                create_rooted_file_bytes(
                    root,
                    index_relative,
                    prepared._new_indexes[index_relative],
                    root_identity,
                )
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "create",
                    "index",
                    index_relative,
                    error,
                ) from error
        for companion, relative in zip(
            intent.birth.companions_before,
            prepared._companion_relatives,
            strict=True,
        ):
            try:
                create_rooted_file_bytes(
                    root,
                    relative,
                    companion.content,
                    root_identity,
                )
            except OSError as error:
                raise WriteFailure(
                    "write", "create", "companion", relative, error
                ) from error
        try:
            create_rooted_file_bytes(
                root,
                prepared._birth_relative,
                intent.birth.content,
                root_identity,
            )
        except OSError as error:
            raise WriteFailure(
                "write",
                "create",
                "document",
                prepared._birth_relative,
                error,
            ) from error
        for mutation in intent.mutations:
            source = prepared.sources[mutation.key]
            try:
                overwrite_rooted_bytes(
                    root,
                    source.path,
                    replacement_map[mutation.key],
                    root_identity,
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
            overwrite_rooted_bytes(
                root,
                prepared._refresh_index,
                prepared._refresh_content,
                root_identity,
                prepared._refresh_identity,
            )
        except OSError as error:
            raise WriteFailure(
                "write",
                "overwrite",
                "index",
                prepared._refresh_index,
                error,
            ) from error
        try:
            row = f"{format_log_entry(intent.log_entry)}\n".encode("utf-8")
            if prepared._log_identity is None:
                create_rooted_file_bytes(
                    root,
                    Path("log.md"),
                    empty_log_content().encode("utf-8") + row,
                    root_identity,
                )
            else:
                existing = read_rooted_bytes(
                    root,
                    Path("log.md"),
                    root_identity,
                    prepared._log_identity,
                )
                separator = b"" if existing.endswith(b"\n") else b"\n"
                append_rooted_bytes(
                    root,
                    Path("log.md"),
                    separator + row,
                    root_identity,
                    prepared._log_identity,
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
