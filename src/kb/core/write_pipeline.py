from __future__ import annotations

import errno
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from kb.core.housekeeping import LogEntry, empty_log_content, format_log_entry
from kb.core.indexing import (
    DirectoryListingMetadata,
    file_listing_line,
    file_listing_metadata,
    render_index,
    render_projected_directory_index,
    subdirectory_listing_metadata,
    subdirectory_listing_line,
)
from kb.core.model import Config, ConfigLoadError, parse_config_bytes
from kb.core.safeio import (
    FileIdentity,
    _RootedReader,
    _RootedTreeAcquisitionError,
    _append_rooted_final_bytes,
    _create_rooted_final_file_bytes,
    RootedContainmentError,
    create_rooted_directory,
    create_rooted_file_bytes,
    inspect_rooted_directory,
    inspect_rooted_file,
    overwrite_rooted_bytes,
    read_rooted_bytes,
    rooted_reader,
    verify_root,
)
from kb.core.scan import (
    KB,
    discover_root,
    read_frontmatter_prefix,
    scan_snapshot,
)

_EMPTY_LOG_CONTENT = empty_log_content().encode("utf-8")

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
    _root_identity: FileIdentity = PrivateAttr()


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
    _refresh_directory_identity: FileIdentity = PrivateAttr()
    _refresh_identity: FileIdentity = PrivateAttr()
    _refresh_content: bytes = PrivateAttr()
    _log_identity: FileIdentity | None = PrivateAttr(default=None)
    _log_row: bytes = PrivateAttr()
    _created: list[str] = PrivateAttr(default_factory=list)
    _updated: list[str] = PrivateAttr(default_factory=list)
    _consumed: bool = PrivateAttr(default=False)


class WriteReceipt(BaseModel):
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _RootedIndexSnapshot:
    identity: FileIdentity
    content: bytes
    listing: DirectoryListingMetadata


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
        snapshot_kb: KB | None = None,
    ) -> None:
        super().__init__(str(cause))
        self.phase = phase
        self.operation = operation
        self.role = role
        self.path = path
        self.cause = cause
        self.key = key
        self.snapshot_kb = snapshot_kb


class _MarkdownSnapshotError(OSError):
    def __init__(
        self,
        error_number: int,
        message: str,
        path: Path,
        files: Mapping[Path, bytes],
    ) -> None:
        super().__init__(error_number, message, path)
        self.files = dict(files)


def load_write_context(kb_root: Path | None) -> WriteContext:
    root = discover_root(kb_root)
    try:
        with rooted_reader(root) as reader:
            root_identity = reader.identity
            try:
                config_content = reader.read_file(Path("kb-config.json"))
            except RootedContainmentError:
                raise
            except OSError as error:
                raise ConfigLoadError(
                    "E_CONFIG_INVALID",
                    f"invalid kb-config.json: {error}",
                ) from error
            config = parse_config_bytes(config_content)
            kb = scan_snapshot(root, _snapshot_markdown_prefixes(reader))
    except _MarkdownSnapshotError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "directory",
            Path(error.filename),
            error,
            snapshot_kb=scan_snapshot(root, error.files),
        ) from error
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "directory",
            Path("."),
            error,
        ) from error
    if kb.malformed:
        paths = tuple(sorted(path for path, _ in kb.malformed))
        raise AllocationBlocked(paths)
    context = WriteContext(root=root, config=config, kb=kb)
    context._root_identity = root_identity
    return context


def _snapshot_markdown_prefixes(reader: _RootedReader) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    unsafe: list[tuple[int, str, Path]] = []
    try:
        entries = reader.acquire_tree_files(
            suffix=".md",
            acquire=read_frontmatter_prefix,
        )
    except _RootedTreeAcquisitionError as error:
        files.update(
            {
                entry.path: entry.content
                for entry in error.acquired
                if entry.kind == "file" and entry.content is not None
            }
        )
        raise _MarkdownSnapshotError(
            error.errno or errno.EIO,
            error.strerror or str(error.cause),
            error.path,
            files,
        ) from error
    for entry in entries:
        if entry.kind == "file":
            assert entry.content is not None
            files[entry.path] = entry.content
        elif entry.kind == "symlink":
            unsafe.append(
                (
                    getattr(errno, "ELOOP", errno.EINVAL),
                    "Markdown scan path must not be a symlink or junction",
                    entry.path,
                )
            )
        else:
            unsafe.append(
                (
                    errno.EINVAL,
                    "Markdown scan path is not a regular file",
                    entry.path,
                )
            )
    if unsafe:
        error_number, message, path = unsafe[0]
        raise _MarkdownSnapshotError(
            error_number,
            message,
            path,
            files,
        )
    return files


def _relative_path(value: Path) -> Path:
    shown = value.as_posix()
    candidate = PurePosixPath(shown)
    if (
        value.is_absolute()
        or not candidate.parts
        or "\\" in shown
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"write path must be KB-root-relative POSIX: {shown}")
    return Path(*candidate.parts)


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
        index_path = directory / "index.md"
        relative = directory.as_posix()
        try:
            if offset == 0:
                listing = "## Files\n" + document_listing
            else:
                child = missing[len(missing) - offset]
                child_relative = child.as_posix()
                listing = "## Subdirectories\n" + subdirectory_listing_line(
                    child.name,
                    f"Documents under {child_relative}/.",
                )
            rendered = render_index(
                directory.name,
                f"Documents under {relative}/.",
                listing,
            )
            if not isinstance(rendered, str):
                raise TypeError("born index renderer must return text")
        except (TypeError, ValueError) as error:
            cause = OSError(
                errno.EINVAL,
                "born index could not be formatted",
                index_path,
            )
            raise WriteFailure(
                "preflight",
                "render",
                "index",
                index_path,
                cause,
            ) from error
        try:
            contents[index_path] = rendered.encode("utf-8")
        except UnicodeEncodeError as error:
            cause = OSError(
                errno.EILSEQ,
                "born index is not valid UTF-8",
                index_path,
            )
            raise WriteFailure(
                "preflight",
                "render",
                "index",
                index_path,
                cause,
            ) from error
    return {
        directory / "index.md": contents[directory / "index.md"]
        for directory in missing
    }


def _rooted_index_snapshot(
    root: Path,
    directory: Path,
    root_identity: FileIdentity,
    directory_identity: FileIdentity,
) -> _RootedIndexSnapshot:
    files = []
    subdirectories = []
    with rooted_reader(root, root_identity) as reader:
        listing = reader.list_directory(directory, directory_identity)
        refresh_index_entry = next(
            (entry for entry in listing.entries if entry.name == "index.md"),
            None,
        )
        if refresh_index_entry is None:
            raise FileNotFoundError(
                errno.ENOENT,
                "directory index is missing",
                directory / "index.md",
            )
        if refresh_index_entry.kind != "file":
            error_number = (
                getattr(errno, "ELOOP", errno.EINVAL)
                if refresh_index_entry.kind == "symlink"
                else errno.EINVAL
            )
            raise OSError(
                error_number,
                "directory index is not a regular file",
                directory / "index.md",
            )
        index_content = reader.read_file(
            directory / "index.md",
            expected=refresh_index_entry.identity,
            parent_expected=listing.identity,
        )
        for entry in listing.entries:
            relative = directory / entry.name
            if entry.kind == "symlink":
                raise OSError(
                    getattr(errno, "ELOOP", errno.EINVAL),
                    "index listing child must not be a symlink or junction",
                    relative,
                )
            if entry.kind == "directory":
                child_listing = reader.list_directory(relative, entry.identity)
                child_index_entry = next(
                    (
                        child
                        for child in child_listing.entries
                        if child.name == "index.md"
                    ),
                    None,
                )
                if child_index_entry is None:
                    continue
                if child_index_entry.kind != "file":
                    raise OSError(
                        errno.EINVAL,
                        "subdirectory index is not a regular file",
                        relative / "index.md",
                    )
                content = reader.read_file(
                    relative / "index.md",
                    expected=child_index_entry.identity,
                    parent_expected=child_listing.identity,
                )
                subdirectories.append(
                    subdirectory_listing_metadata(entry.name, content)
                )
                continue
            if entry.kind == "other":
                raise OSError(
                    errno.EINVAL,
                    "index listing child is not a regular file or directory",
                    relative,
                )
            if (
                entry.kind == "file"
                and relative.suffix == ".md"
                and entry.name not in {"index.md", "log.md"}
            ):
                content = reader.read_file(
                    relative,
                    expected=entry.identity,
                    parent_expected=listing.identity,
                    acquire=read_frontmatter_prefix,
                )
                files.append(file_listing_metadata(entry.name, content))
        reader.list_directory(directory, listing.identity)
    return _RootedIndexSnapshot(
        identity=refresh_index_entry.identity,
        content=index_content,
        listing=DirectoryListingMetadata(
            files=files,
            subdirectories=subdirectories,
        ),
    )


def prepare_write(context: WriteContext, intent: WriteIntent) -> PreparedWrite:
    root = context.root
    root_identity = context._root_identity
    try:
        verify_root(root, root_identity)
    except OSError as error:
        raise WriteFailure(
            "preflight",
            "inspect",
            "directory",
            Path("."),
            error,
        ) from error
    birth_relative = _relative_path(intent.birth.path)
    if birth_relative.suffix != ".md":
        raise ValueError("citable document birth must end in .md")
    companion_relatives = [
        _relative_path(companion.path)
        for companion in intent.birth.companions_before
    ]
    mutation_relatives = [
        _relative_path(mutation.path)
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

    if not refresh_directory.parts:
        refresh_directory_identity = root_identity
    else:
        try:
            refresh_directory_identity = inspect_rooted_directory(
                root,
                refresh_directory,
                root_identity,
            )
        except OSError as error:
            raise WriteFailure(
                "preflight",
                "inspect",
                "index",
                refresh_index,
                error,
            ) from error
        assert refresh_directory_identity is not None
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
        index_snapshot = _rooted_index_snapshot(
            root,
            refresh_directory,
            root_identity,
            refresh_directory_identity,
        )
        refresh_content = render_projected_directory_index(
            index_snapshot.content,
            refresh_directory.name or root.name,
            index_snapshot.listing,
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

    try:
        formatted_log_row = format_log_entry(intent.log_entry)
    except (TypeError, ValueError) as error:
        cause = OSError(errno.EINVAL, "log row could not be formatted")
        raise WriteFailure(
            "preflight",
            "render",
            "log",
            Path("log.md"),
            cause,
        ) from error

    try:
        log_row = f"{formatted_log_row}\n".encode("utf-8")
    except UnicodeEncodeError as error:
        cause = OSError(errno.EILSEQ, "log row is not valid UTF-8")
        raise WriteFailure(
            "preflight",
            "render",
            "log",
            Path("log.md"),
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
    prepared._refresh_directory_identity = refresh_directory_identity
    prepared._refresh_identity = index_snapshot.identity
    prepared._refresh_content = refresh_content
    prepared._log_identity = log_identity
    prepared._log_row = log_row
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
    born_identities: dict[Path, FileIdentity] = {}
    birth_parent_identities = {
        prepared._refresh_index.parent: prepared._refresh_directory_identity,
    }
    try:
        for directory in prepared._new_directories:
            parent_expected = birth_parent_identities[directory.parent]
            try:
                born_identity = create_rooted_directory(
                    root,
                    directory,
                    root_identity,
                    parent_expected=parent_expected,
                )
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "mkdir",
                    "directory",
                    directory,
                    error,
                ) from error
            born_identities[directory] = born_identity
            birth_parent_identities[directory] = born_identity
            index_relative = directory / "index.md"
            try:
                create_rooted_file_bytes(
                    root,
                    index_relative,
                    prepared._new_indexes[index_relative],
                    root_identity,
                    parent_expected=born_identity,
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
            parent_expected = birth_parent_identities[relative.parent]
            try:
                create_rooted_file_bytes(
                    root,
                    relative,
                    companion.content,
                    root_identity,
                    parent_expected=parent_expected,
                )
            except OSError as error:
                raise WriteFailure(
                    "write", "create", "companion", relative, error
                ) from error
        birth_parent_expected = birth_parent_identities[
            prepared._birth_relative.parent
        ]
        try:
            create_rooted_file_bytes(
                root,
                prepared._birth_relative,
                intent.birth.content,
                root_identity,
                parent_expected=birth_parent_expected,
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
        for directory, identity in born_identities.items():
            try:
                inspect_rooted_directory(
                    root,
                    directory,
                    root_identity,
                    expected=identity,
                )
            except OSError as error:
                raise WriteFailure(
                    "write",
                    "inspect",
                    "directory",
                    directory,
                    error,
                ) from error
        try:
            if prepared._log_identity is None:
                _create_rooted_final_file_bytes(
                    root,
                    Path("log.md"),
                    _EMPTY_LOG_CONTENT + prepared._log_row,
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
                _append_rooted_final_bytes(
                    root,
                    Path("log.md"),
                    separator + prepared._log_row,
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
