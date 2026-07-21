import errno
import os
from pathlib import Path

import pytest

import kb.core.safeio as safeio
from kb.core.safeio import (
    append_mutable_bytes,
    create_rooted_directory,
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


def test_rooted_directory_birth_returns_its_identity(tmp_path) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)

    born_identity = create_rooted_directory(
        root,
        Path("born"),
        root_identity,
        parent_expected=root_identity,
    )

    assert born_identity == inspect_rooted_directory(
        root,
        Path("born"),
        root_identity,
    )


def test_rooted_file_birth_rejects_replaced_expected_parent(tmp_path) -> None:
    root = tmp_path / "kb"
    parent = root / "born"
    parent.mkdir(parents=True)
    root_identity = inspect_root(root)
    parent_identity = inspect_rooted_directory(root, Path("born"), root_identity)
    assert parent_identity is not None
    parent.rename(root / "born-original")
    parent.mkdir()

    with pytest.raises(OSError, match="identity changed"):
        create_rooted_file_bytes(
            root,
            Path("born/index.md"),
            b"index",
            root_identity,
            parent_expected=parent_identity,
        )

    assert list(parent.iterdir()) == []


def test_rooted_directory_birth_binds_created_identity_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_open = safeio.os.open
    injected = False
    staging_descriptor: int | None = None
    late_identity = None

    def install_late_occupant_before_identity_binding(
        path,
        flags,
        mode=0o777,
        *,
        dir_fd=None,
    ):
        nonlocal injected, staging_descriptor, late_identity
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if not injected and dir_fd is not None and (path == "born" or is_staging):
            injected = True
            if path == "born":
                os.rename(
                    "born",
                    "born-created",
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
            os.mkdir("born", dir_fd=dir_fd)
            status = os.stat("born", dir_fd=dir_fd, follow_symlinks=False)
            late_identity = (status.st_dev, status.st_ino)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_staging:
            staging_descriptor = descriptor
        return descriptor

    monkeypatch.setattr(
        safeio.os,
        "open",
        install_late_occupant_before_identity_binding,
    )

    with pytest.raises(OSError):
        create_rooted_directory(
            root,
            Path("born"),
            root_identity,
            parent_expected=root_identity,
        )

    assert injected
    status = (root / "born").stat()
    assert (status.st_dev, status.st_ino) == late_identity
    assert list((root / "born").iterdir()) == []
    assert not any(path.name.startswith(".kb-born-") for path in root.iterdir())
    assert staging_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(staging_descriptor)


def test_rooted_directory_birth_never_overwrites_late_occupant(tmp_path) -> None:
    root = tmp_path / "kb"
    occupant = root / "born"
    occupant.mkdir(parents=True)
    root_identity = inspect_root(root)
    before = occupant.stat()

    with pytest.raises(FileExistsError):
        create_rooted_directory(
            root,
            Path("born"),
            root_identity,
            parent_expected=root_identity,
        )

    after = occupant.stat()
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    assert list(occupant.iterdir()) == []
    assert not any(path.name.startswith(".kb-born-") for path in root.iterdir())


def test_rooted_directory_birth_fails_before_staging_without_exclusive_publish(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    monkeypatch.setattr(
        safeio,
        "_EXCLUSIVE_DIRECTORY_PUBLISH",
        None,
        raising=False,
    )

    with pytest.raises(OSError) as raised:
        create_rooted_directory(root, Path("born"), root_identity)

    assert raised.value.errno == errno.ENOTSUP
    assert list(root.iterdir()) == []


def test_rooted_directory_birth_rejects_staging_replacement_before_open(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_open = safeio.os.open
    replacement_descriptor: int | None = None
    injected = False

    def replace_staging_before_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected, replacement_descriptor
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if is_staging and not injected:
            injected = True
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if is_staging:
            replacement_descriptor = descriptor
        return descriptor

    monkeypatch.setattr(safeio.os, "open", replace_staging_before_open)

    with pytest.raises(OSError, match="identity changed"):
        create_rooted_directory(root, Path("born"), root_identity)

    assert injected
    assert not (root / "born").exists()
    private_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(private_entries) == 2
    assert all(path.is_dir() and not any(path.iterdir()) for path in private_entries)
    assert replacement_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(replacement_descriptor)
