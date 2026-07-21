from __future__ import annotations

import errno
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_ROOTED_SUPPORTED = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)
_UNSUPPORTED_ERRNO = getattr(
    errno,
    "ENOTSUP",
    getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
)


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


def _identity(status: os.stat_result) -> FileIdentity:
    return FileIdentity(device=status.st_dev, inode=status.st_ino)


def _stale_error(path: Path) -> OSError:
    stale = getattr(errno, "ESTALE", errno.EIO)
    return OSError(stale, "mutable file identity changed", path)


def _require_rooted_support() -> None:
    if not _ROOTED_SUPPORTED:
        raise OSError(
            _UNSUPPORTED_ERRNO,
            "root-anchored no-follow filesystem operations are unsupported",
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


@contextmanager
def _open_rooted_parent(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
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
        yield descriptors[-1], parts[-1]
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def create_rooted_directory(
    root: Path,
    relative: Path,
    root_identity: FileIdentity,
) -> None:
    with _open_rooted_parent(root, relative, root_identity) as (
        parent_descriptor,
        name,
    ):
        os.mkdir(name, dir_fd=parent_descriptor)


def create_rooted_file_bytes(
    root: Path,
    relative: Path,
    content: bytes,
    root_identity: FileIdentity,
) -> None:
    with _open_rooted_parent(root, relative, root_identity) as (
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
            return _identity(status)
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
