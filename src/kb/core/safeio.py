from __future__ import annotations

import ctypes
import errno
import os
import secrets
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Literal

_ROOTED_SUPPORTED = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.listdir in os.supports_fd
)
_UNSUPPORTED_ERRNO = getattr(
    errno,
    "ENOTSUP",
    getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
)
_BORN_STAGING_PREFIX = ".kb-born-"
_STAGING_ATTEMPTS = 128
_DARWIN_RENAME_EXCL = 0x00000004
_LINUX_RENAME_NOREPLACE = 1
_ExclusiveDirectoryPublish = tuple[Callable[..., int], int]


def _load_exclusive_directory_publish() -> _ExclusiveDirectoryPublish | None:
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        function = libc.renameatx_np
        flag = _DARWIN_RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        function = libc.renameat2
        flag = _LINUX_RENAME_NOREPLACE
    else:
        return None
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    return function, flag


_EXCLUSIVE_DIRECTORY_PUBLISH = _load_exclusive_directory_publish()


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class RootedEntry:
    name: str
    kind: Literal["directory", "file", "symlink", "other"]
    identity: FileIdentity


@dataclass(frozen=True)
class RootedDirectoryListing:
    identity: FileIdentity
    entries: tuple[RootedEntry, ...]


@dataclass(frozen=True)
class RootedAcquiredEntry:
    path: Path
    kind: Literal["file", "symlink", "other"]
    content: bytes | None = None


class RootedContainmentError(OSError):
    """A rooted operation could no longer prove its acquisition boundary."""


class _RootedTreeAcquisitionError(OSError):
    """A tree acquisition failed after zero or more entries were bound."""

    def __init__(
        self,
        cause: OSError,
        path: Path,
        acquired: tuple[RootedAcquiredEntry, ...],
    ) -> None:
        super().__init__(
            cause.errno or errno.EIO,
            cause.strerror or str(cause),
            path,
        )
        self.cause = cause
        self.path = path
        self.acquired = acquired


def _identity(status: os.stat_result) -> FileIdentity:
    return FileIdentity(device=status.st_dev, inode=status.st_ino)


def _stale_error(path: Path) -> RootedContainmentError:
    stale = getattr(errno, "ESTALE", errno.EIO)
    return RootedContainmentError(
        stale,
        "mutable file identity changed",
        path,
    )


def _require_rooted_support() -> None:
    if not _ROOTED_SUPPORTED:
        raise RootedContainmentError(
            _UNSUPPORTED_ERRNO,
            "root-anchored no-follow filesystem operations are unsupported",
        )


def _require_exclusive_directory_publish() -> None:
    if _EXCLUSIVE_DIRECTORY_PUBLISH is None:
        raise RootedContainmentError(
            _UNSUPPORTED_ERRNO,
            "atomic exclusive directory publication is unsupported",
        )


def _publish_directory_exclusive(
    parent_descriptor: int,
    staging_name: str,
    final_name: str,
) -> None:
    _require_exclusive_directory_publish()
    assert _EXCLUSIVE_DIRECTORY_PUBLISH is not None
    function, flag = _EXCLUSIVE_DIRECTORY_PUBLISH
    ctypes.set_errno(0)
    result = function(
        parent_descriptor,
        os.fsencode(staging_name),
        parent_descriptor,
        os.fsencode(final_name),
        flag,
    )
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(
            error_number,
            os.strerror(error_number),
            final_name,
        )


def _relative_parts(relative: Path) -> tuple[str, ...]:
    shown = relative.as_posix()
    parts = relative.parts
    if (
        relative.is_absolute()
        or not parts
        or "\\" in shown
        or any(part in {".", ".."} for part in parts)
    ):
        raise OSError(
            errno.EINVAL,
            "rooted path must be relative and normalized",
            shown,
        )
    return parts


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _require_empty_bound_directory(descriptor: int, relative: Path) -> None:
    if os.listdir(descriptor):
        raise OSError(
            errno.ENOTEMPTY,
            "bound staging directory is not empty",
            relative,
        )


def inspect_root(root: Path) -> FileIdentity:
    _require_rooted_support()
    descriptor = os.open(root, _directory_flags())
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            raise OSError(errno.ENOTDIR, "KB root is not a directory", root)
        return _identity(status)
    finally:
        os.close(descriptor)


def _open_verified_root(root: Path, expected: FileIdentity) -> int:
    _require_rooted_support()
    descriptor = os.open(root, _directory_flags())
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode) or _identity(status) != expected:
            raise _stale_error(root)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def verify_root(root: Path, expected: FileIdentity) -> None:
    try:
        descriptor = _open_verified_root(root, expected)
    except RootedContainmentError:
        raise
    except OSError as error:
        raise RootedContainmentError(
            error.errno,
            error.strerror or str(error),
            root,
        ) from error
    os.close(descriptor)


def _list_open_directory(
    descriptor: int,
    expected: FileIdentity,
    relative: Path,
) -> RootedDirectoryListing:
    status = os.fstat(descriptor)
    identity = _identity(status)
    if not stat.S_ISDIR(status.st_mode):
        raise OSError(errno.ENOTDIR, "rooted path is not a directory", relative)
    if identity != expected:
        raise _stale_error(relative)
    entries: list[RootedEntry] = []
    for name in sorted(os.listdir(descriptor)):
        child_status = os.stat(
            name,
            dir_fd=descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISDIR(child_status.st_mode):
            kind: Literal["directory", "file", "symlink", "other"] = "directory"
        elif stat.S_ISREG(child_status.st_mode):
            kind = "file"
        elif stat.S_ISLNK(child_status.st_mode):
            kind = "symlink"
        else:
            kind = "other"
        entries.append(
            RootedEntry(
                name=name,
                kind=kind,
                identity=_identity(child_status),
            )
        )
    return RootedDirectoryListing(identity=identity, entries=tuple(entries))


class _RootedReader:
    def __init__(
        self,
        root: Path,
        descriptor: int,
        identity: FileIdentity,
    ) -> None:
        self.root = root
        self._descriptor = descriptor
        self.identity = identity

    def verify_root(self) -> None:
        verify_root(self.root, self.identity)

    def _open_directory(
        self,
        relative: Path,
        expected: FileIdentity | None = None,
    ) -> int:
        parts = relative.parts
        descriptor = os.dup(self._descriptor)
        try:
            for part in parts:
                child = os.open(part, _directory_flags(), dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            status = os.fstat(descriptor)
            actual = _identity(status)
            if not stat.S_ISDIR(status.st_mode):
                raise OSError(
                    errno.ENOTDIR,
                    "rooted path is not a directory",
                    relative,
                )
            if expected is not None and actual != expected:
                raise _stale_error(relative)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def list_directory(
        self,
        relative: Path,
        expected: FileIdentity | None = None,
    ) -> RootedDirectoryListing:
        self.verify_root()
        descriptor = self._open_directory(relative, expected)
        try:
            identity = _identity(os.fstat(descriptor))
            entries: list[RootedEntry] = []
            for name in sorted(os.listdir(descriptor)):
                status = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISDIR(status.st_mode):
                    kind: Literal["directory", "file", "symlink", "other"] = (
                        "directory"
                    )
                elif stat.S_ISREG(status.st_mode):
                    kind = "file"
                elif stat.S_ISLNK(status.st_mode):
                    kind = "symlink"
                else:
                    kind = "other"
                entries.append(
                    RootedEntry(
                        name=name,
                        kind=kind,
                        identity=_identity(status),
                    )
                )
        finally:
            os.close(descriptor)
        verification = self._open_directory(relative, identity)
        os.close(verification)
        self.verify_root()
        return RootedDirectoryListing(identity=identity, entries=tuple(entries))

    def acquire_tree_files(
        self,
        *,
        suffix: str,
        acquire: Callable[[BinaryIO], bytes],
    ) -> tuple[RootedAcquiredEntry, ...]:
        """Acquire matching files with iterative, descriptor-relative DFS."""
        descriptor: int | None = None
        failure_path = Path()
        parts: tuple[str, ...] = ()
        expected = self.identity
        frames: list[
            tuple[
                tuple[str, ...],
                FileIdentity,
                tuple[RootedEntry, ...],
                int,
                RootedEntry,
            ]
        ] = []
        acquired: list[RootedAcquiredEntry] = []
        try:
            self.verify_root()
            descriptor = os.dup(self._descriptor)
            listing = _list_open_directory(descriptor, expected, Path())
            entries = listing.entries
            offset = 0
            while True:
                failure_path = Path()
                self.verify_root()
                if offset < len(entries):
                    entry = entries[offset]
                    offset += 1
                    if entry.kind == "directory":
                        failure_path = Path(*parts, entry.name)
                        child = os.open(
                            entry.name,
                            _directory_flags(),
                            dir_fd=descriptor,
                        )
                        try:
                            child_parts = (*parts, entry.name)
                            child_listing = _list_open_directory(
                                child,
                                entry.identity,
                                Path(*child_parts),
                            )
                        except BaseException:
                            os.close(child)
                            raise
                        frames.append(
                            (
                                parts,
                                listing.identity,
                                entries,
                                offset,
                                entry,
                            )
                        )
                        os.close(descriptor)
                        descriptor = child
                        parts = child_parts
                        expected = entry.identity
                        listing = child_listing
                        entries = listing.entries
                        offset = 0
                        continue
                    if not entry.name.endswith(suffix):
                        continue
                    relative = Path(*parts, entry.name)
                    if entry.kind != "file":
                        acquired.append(
                            RootedAcquiredEntry(
                                path=relative,
                                kind=entry.kind,
                            )
                        )
                        continue
                    failure_path = relative
                    file_descriptor = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                    try:
                        status = os.fstat(file_descriptor)
                        if not stat.S_ISREG(status.st_mode):
                            raise OSError(
                                errno.EINVAL,
                                "rooted path is not a regular file",
                                relative,
                            )
                        if _identity(status) != entry.identity:
                            raise _stale_error(relative)
                        with os.fdopen(os.dup(file_descriptor), "rb") as stream:
                            content = acquire(stream)
                    finally:
                        os.close(file_descriptor)
                    acquired.append(
                        RootedAcquiredEntry(
                            path=relative,
                            kind="file",
                            content=content,
                        )
                    )
                    failure_path = Path(*parts)
                    if _identity(os.fstat(descriptor)) != listing.identity:
                        raise _stale_error(Path(*parts))
                    continue
                failure_path = Path(*parts)
                if _identity(os.fstat(descriptor)) != expected:
                    raise _stale_error(Path(*parts))
                if not frames:
                    break
                (
                    parent_parts,
                    parent_identity,
                    parent_entries,
                    parent_offset,
                    entered_child,
                ) = frames.pop()
                failure_path = Path(*parent_parts)
                parent = os.open("..", _directory_flags(), dir_fd=descriptor)
                try:
                    if _identity(os.fstat(parent)) != parent_identity:
                        raise _stale_error(Path(*parent_parts))
                    child_status = os.stat(
                        entered_child.name,
                        dir_fd=parent,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(child_status.st_mode)
                        or _identity(child_status) != entered_child.identity
                    ):
                        failure_path = Path(
                            *parent_parts,
                            entered_child.name,
                        )
                        raise _stale_error(
                            Path(*parent_parts, entered_child.name)
                        )
                except BaseException:
                    os.close(parent)
                    raise
                os.close(descriptor)
                descriptor = parent
                parts = parent_parts
                expected = parent_identity
                listing = RootedDirectoryListing(
                    identity=parent_identity,
                    entries=parent_entries,
                )
                entries = parent_entries
                offset = parent_offset
            failure_path = Path()
            self.verify_root()
            return tuple(acquired)
        except _RootedTreeAcquisitionError:
            raise
        except OSError as error:
            raise _RootedTreeAcquisitionError(
                error,
                failure_path,
                tuple(acquired),
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def read_file(
        self,
        relative: Path,
        *,
        expected: FileIdentity | None = None,
        parent_expected: FileIdentity | None = None,
        acquire: Callable[[BinaryIO], bytes] | None = None,
    ) -> bytes:
        parts = _relative_parts(relative)
        self.verify_root()
        parent = self._open_directory(Path(*parts[:-1]), parent_expected)
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            try:
                status = os.fstat(descriptor)
                if not stat.S_ISREG(status.st_mode):
                    raise OSError(
                        errno.EINVAL,
                        "rooted path is not a regular file",
                        relative,
                    )
                if expected is not None and _identity(status) != expected:
                    raise _stale_error(relative)
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    content = stream.read() if acquire is None else acquire(stream)
            finally:
                os.close(descriptor)
            parent_identity = _identity(os.fstat(parent))
        finally:
            os.close(parent)
        verification = self._open_directory(
            Path(*parts[:-1]),
            parent_expected or parent_identity,
        )
        os.close(verification)
        self.verify_root()
        return content


@contextmanager
def rooted_reader(
    root: Path,
    expected: FileIdentity | None = None,
) -> Iterator[_RootedReader]:
    _require_rooted_support()
    descriptor = os.open(root, _directory_flags())
    try:
        status = os.fstat(descriptor)
        identity = _identity(status)
        if not stat.S_ISDIR(status.st_mode):
            raise OSError(errno.ENOTDIR, "KB root is not a directory", root)
        if expected is not None and identity != expected:
            raise _stale_error(root)
        reader = _RootedReader(root, descriptor, identity)
        reader.verify_root()
        yield reader
        reader.verify_root()
    finally:
        os.close(descriptor)


@contextmanager
def _open_rooted_parent(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
    parent_expected: FileIdentity | None = None,
) -> Iterator[tuple[int, str]]:
    parts = _relative_parts(relative)
    descriptors = [_open_verified_root(root, root_identity)]
    try:
        for part in parts[:-1]:
            descriptor = os.open(
                part,
                _directory_flags(),
                dir_fd=descriptors[-1],
            )
            try:
                if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise OSError(
                        errno.ENOTDIR,
                        "rooted path component is not a directory",
                        part,
                    )
            except BaseException:
                os.close(descriptor)
                raise
            descriptors.append(descriptor)
        if (
            parent_expected is not None
            and _identity(os.fstat(descriptors[-1])) != parent_expected
        ):
            raise _stale_error(relative.parent)
        yield descriptors[-1], parts[-1]
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def create_rooted_directory(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
    *,
    parent_expected: FileIdentity | None = None,
) -> FileIdentity:
    _require_exclusive_directory_publish()
    with _open_rooted_parent(
        root,
        relative,
        root_identity,
        parent_expected,
    ) as (
        parent_descriptor,
        name,
    ):
        staging_name: str | None = None
        for _ in range(_STAGING_ATTEMPTS):
            candidate = f"{_BORN_STAGING_PREFIX}{secrets.token_hex(16)}"
            try:
                os.mkdir(candidate, dir_fd=parent_descriptor)
            except FileExistsError:
                continue
            staging_name = candidate
            break
        if staging_name is None:
            raise OSError(
                errno.EEXIST,
                "could not allocate a private directory staging name",
                relative,
            )
        descriptor: int | None = None
        # A failure after staging creation intentionally leaves the randomized
        # path in place. No generic path-based deletion can remain bound to
        # this identity if another process replaces the directory.
        try:
            descriptor = os.open(
                staging_name,
                _directory_flags(),
                dir_fd=parent_descriptor,
            )
            status = os.fstat(descriptor)
            if not stat.S_ISDIR(status.st_mode):
                raise OSError(
                    errno.ENOTDIR,
                    "bound staging path is not a directory",
                    relative,
                )
            bound_identity = _identity(status)
            _require_empty_bound_directory(descriptor, relative)
            staging_status = os.stat(
                staging_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(staging_status.st_mode)
                or _identity(staging_status) != bound_identity
            ):
                raise _stale_error(relative)
            _require_empty_bound_directory(descriptor, relative)
            _publish_directory_exclusive(
                parent_descriptor,
                staging_name,
                name,
            )
            published_status = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(published_status.st_mode)
                or _identity(published_status) != bound_identity
            ):
                raise _stale_error(relative)
            return bound_identity
        finally:
            if descriptor is not None:
                os.close(descriptor)


def create_rooted_file_bytes(
    root: Path,
    relative: Path,
    content: bytes,
    root_identity: FileIdentity,
    *,
    parent_expected: FileIdentity | None = None,
) -> None:
    with _open_rooted_parent(
        root,
        relative,
        root_identity,
        parent_expected,
    ) as (
        parent_descriptor,
        name,
    ):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(name, flags, 0o666, dir_fd=parent_descriptor)
        try:
            _write_all(descriptor, content)
        finally:
            os.close(descriptor)


def inspect_rooted_file(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
    *,
    allow_missing: bool = False,
) -> FileIdentity | None:
    with _open_rooted_parent(root, relative, root_identity) as (
        parent_descriptor,
        name,
    ):
        try:
            status = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if allow_missing:
                return None
            raise
        if stat.S_ISLNK(status.st_mode):
            raise OSError(
                errno.ELOOP,
                "mutable file must not be a symlink or junction",
                relative,
            )
        if not stat.S_ISREG(status.st_mode):
            raise OSError(
                errno.EINVAL,
                "mutable path is not a regular file",
                relative,
            )
        return _identity(status)


def inspect_rooted_directory(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
    *,
    allow_missing: bool = False,
    expected: FileIdentity | None = None,
) -> FileIdentity | None:
    with _open_rooted_parent(root, relative, root_identity) as (
        parent_descriptor,
        name,
    ):
        try:
            descriptor = os.open(
                name,
                _directory_flags(),
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError:
            if allow_missing:
                return None
            raise
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISDIR(status.st_mode):
                raise OSError(
                    errno.ENOTDIR,
                    "rooted path is not a directory",
                    relative,
                )
            identity = _identity(status)
            if expected is not None and identity != expected:
                raise _stale_error(relative)
            return identity
        finally:
            os.close(descriptor)


@contextmanager
def _open_rooted_existing(
    root: Path,
    relative: Path,
    flags: int,
    root_identity: FileIdentity,
    expected: FileIdentity,
) -> Iterator[int]:
    with _open_rooted_parent(root, relative, root_identity) as (
        parent_descriptor,
        name,
    ):
        descriptor = os.open(
            name,
            flags | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or _identity(status) != expected:
                raise _stale_error(relative)
            yield descriptor
        finally:
            os.close(descriptor)


def read_rooted_bytes(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
    expected: FileIdentity,
) -> bytes:
    with _open_rooted_existing(
        root,
        relative,
        os.O_RDONLY,
        root_identity,
        expected,
    ) as descriptor:
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            return stream.read()


def overwrite_rooted_bytes(
    root: Path,
    relative: Path,
    content: bytes,
    root_identity: FileIdentity,
    expected: FileIdentity,
) -> None:
    with _open_rooted_existing(
        root,
        relative,
        os.O_WRONLY,
        root_identity,
        expected,
    ) as descriptor:
        os.ftruncate(descriptor, 0)
        _write_all(descriptor, content)


def append_rooted_bytes(
    root: Path,
    relative: Path,
    content: bytes,
    root_identity: FileIdentity,
    expected: FileIdentity,
) -> None:
    with _open_rooted_existing(
        root,
        relative,
        os.O_WRONLY | os.O_APPEND,
        root_identity,
        expected,
    ) as descriptor:
        _write_all(descriptor, content)


def _open_flags(flags: int) -> int:
    return flags | getattr(os, "O_NOFOLLOW", 0)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def inspect_mutable_file(
    path: Path, *, allow_missing: bool = False
) -> FileIdentity | None:
    if _is_link_or_junction(path):
        raise OSError(errno.ELOOP, "mutable file must not be a symlink or junction", path)
    try:
        status = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    if not stat.S_ISREG(status.st_mode):
        raise OSError(errno.EINVAL, "mutable path is not a regular file", path)
    return FileIdentity(device=status.st_dev, inode=status.st_ino)


def _open_existing(path: Path, flags: int, expected: FileIdentity) -> int:
    descriptor = os.open(path, _open_flags(flags))
    try:
        status = os.fstat(descriptor)
        actual = FileIdentity(device=status.st_dev, inode=status.st_ino)
        if not stat.S_ISREG(status.st_mode) or actual != expected:
            stale = getattr(errno, "ESTALE", errno.EIO)
            raise OSError(stale, "mutable file identity changed", path)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _write_all(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written == 0:
            raise OSError(errno.EIO, "mutable file write made no progress")
        remaining = remaining[written:]


def create_file_bytes(path: Path, content: bytes) -> None:
    flags = _open_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    descriptor = os.open(path, flags, 0o666)
    try:
        _write_all(descriptor, content)
    finally:
        os.close(descriptor)


def read_mutable_bytes(path: Path, expected: FileIdentity) -> bytes:
    descriptor = _open_existing(path, os.O_RDONLY, expected)
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


def overwrite_mutable_bytes(
    path: Path, content: bytes, expected: FileIdentity
) -> None:
    descriptor = _open_existing(path, os.O_WRONLY, expected)
    try:
        os.ftruncate(descriptor, 0)
        _write_all(descriptor, content)
    finally:
        os.close(descriptor)


def append_mutable_bytes(path: Path, content: bytes, expected: FileIdentity) -> None:
    descriptor = _open_existing(path, os.O_WRONLY | os.O_APPEND, expected)
    try:
        _write_all(descriptor, content)
    finally:
        os.close(descriptor)
