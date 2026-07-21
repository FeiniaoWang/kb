import errno
import os
from pathlib import Path

import pytest

import kb.core.safeio as safeio
from kb.core.safeio import (
    append_mutable_bytes,
    create_rooted_file_bytes,
    inspect_root,
    inspect_mutable_file,
    inspect_rooted_directory,
    inspect_rooted_file,
    overwrite_mutable_bytes,
    overwrite_rooted_bytes,
)


def test_overwrite_rejects_changed_identity_before_truncating(tmp_path) -> None:
    path = tmp_path / "mutable.md"
    path.write_bytes(b"original\n")
    identity = inspect_mutable_file(path)
    path.rename(tmp_path / "original.md")
    path.write_bytes(b"replacement\n")

    with pytest.raises(OSError, match="identity changed"):
        overwrite_mutable_bytes(path, b"new content\n", identity)

    assert path.read_bytes() == b"replacement\n"


def test_append_rejects_changed_identity_before_writing(tmp_path) -> None:
    path = tmp_path / "log.md"
    path.write_bytes(b"original\n")
    identity = inspect_mutable_file(path)
    path.rename(tmp_path / "original-log.md")
    path.write_bytes(b"replacement\n")

    with pytest.raises(OSError, match="identity changed"):
        append_mutable_bytes(path, b"appended\n", identity)

    assert path.read_bytes() == b"replacement\n"


def test_rooted_create_does_not_follow_parent_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    parent = root / "inside"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    root_identity = inspect_root(root)
    moved = root / "inside-moved"
    real_open = safeio.os.open
    swapped = False

    def swap_parent(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "planned.md" and flags & os.O_CREAT and not swapped:
            swapped = True
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", swap_parent)

    create_rooted_file_bytes(
        root,
        Path("inside/planned.md"),
        b"planned",
        root_identity,
    )

    assert (moved / "planned.md").read_bytes() == b"planned"
    assert not (outside / "planned.md").exists()


def test_rooted_overwrite_does_not_follow_parent_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    parent = root / "inside"
    outside = tmp_path / "outside"
    parent.mkdir(parents=True)
    outside.mkdir()
    mutable = parent / "mutable.md"
    mutable.write_bytes(b"original")
    (outside / "mutable.md").write_bytes(b"external")
    root_identity = inspect_root(root)
    identity = inspect_rooted_file(
        root,
        Path("inside/mutable.md"),
        root_identity,
    )
    assert identity is not None
    moved = root / "inside-moved"
    real_open = safeio.os.open
    swapped = False

    def swap_parent(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "mutable.md" and flags & os.O_WRONLY and not swapped:
            swapped = True
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", swap_parent)

    overwrite_rooted_bytes(
        root,
        Path("inside/mutable.md"),
        b"updated",
        root_identity,
        identity,
    )

    assert (moved / "mutable.md").read_bytes() == b"updated"
    assert (outside / "mutable.md").read_bytes() == b"external"


def test_rooted_create_closes_parent_descriptor_on_failure(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    (root / "inside").mkdir(parents=True)
    root_identity = inspect_root(root)
    real_open = safeio.os.open
    parent_descriptor: int | None = None

    def fail_final_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal parent_descriptor
        if path == "planned.md" and flags & os.O_CREAT:
            parent_descriptor = dir_fd
            raise OSError(errno.EIO, "planned failure")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", fail_final_open)

    with pytest.raises(OSError, match="planned failure"):
        create_rooted_file_bytes(
            root,
            Path("inside/planned.md"),
            b"planned",
            root_identity,
        )

    assert parent_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(parent_descriptor)


def test_rooted_io_fails_before_mutation_without_dir_fd_support(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    monkeypatch.setattr(safeio, "_ROOTED_SUPPORTED", False)

    with pytest.raises(OSError) as raised:
        create_rooted_file_bytes(
            root,
            Path("planned.md"),
            b"planned",
            root_identity,
        )

    assert raised.value.errno == errno.ENOTSUP
    assert not (root / "planned.md").exists()


def test_rooted_directory_inspection_distinguishes_existing_and_missing(
    tmp_path,
) -> None:
    root = tmp_path / "kb"
    (root / "existing").mkdir(parents=True)
    root_identity = inspect_root(root)

    existing = inspect_rooted_directory(
        root,
        Path("existing"),
        root_identity,
        allow_missing=True,
    )
    missing = inspect_rooted_directory(
        root,
        Path("missing"),
        root_identity,
        allow_missing=True,
    )

    assert existing is not None
    assert missing is None
