from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


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
