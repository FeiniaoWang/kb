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
    private_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(private_entries) == 1
    assert private_entries[0].is_dir()
    assert list(private_entries[0].iterdir()) == []
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
    private_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(private_entries) == 1
    assert private_entries[0].is_dir()
    assert list(private_entries[0].iterdir()) == []


def test_failed_directory_publication_never_path_deletes_staging_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    occupant = root / "born"
    occupant.mkdir(parents=True)
    root_identity = inspect_root(root)
    occupant_before = occupant.stat()
    real_rmdir = safeio.os.rmdir
    cleanup_rmdir_called = False
    replacement_was_deleted = False

    def replace_staging_at_former_cleanup_seam(path, *, dir_fd=None):
        nonlocal cleanup_rmdir_called, replacement_was_deleted
        if isinstance(path, str) and path.startswith(".kb-born-"):
            cleanup_rmdir_called = True
            owned_name = f"{path}-owned"
            os.rename(
                path,
                owned_name,
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
            real_rmdir(path, dir_fd=dir_fd)
            replacement_was_deleted = True
            return None
        return real_rmdir(path, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "rmdir", replace_staging_at_former_cleanup_seam)

    with pytest.raises(FileExistsError):
        create_rooted_directory(
            root,
            Path("born"),
            root_identity,
            parent_expected=root_identity,
        )

    occupant_after = occupant.stat()
    assert (occupant_after.st_dev, occupant_after.st_ino) == (
        occupant_before.st_dev,
        occupant_before.st_ino,
    )
    assert not cleanup_rmdir_called
    assert not replacement_was_deleted
    private_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(private_entries) == 1
    assert private_entries[0].is_dir()
    assert list(private_entries[0].iterdir()) == []


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


def test_rooted_directory_birth_binds_real_staging_replacement_at_first_open(
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

    bound_identity = create_rooted_directory(root, Path("born"), root_identity)

    assert injected
    published = (root / "born").stat()
    assert bound_identity == safeio.FileIdentity(
        device=published.st_dev,
        inode=published.st_ino,
    )
    private_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(private_entries) == 1
    assert private_entries[0].name.endswith("-created")
    assert private_entries[0].is_dir()
    assert not any(private_entries[0].iterdir())
    assert replacement_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(replacement_descriptor)


def test_rooted_directory_birth_rejects_nonempty_replacement_at_first_open(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"outside")
    root_identity = inspect_root(root)
    real_open = safeio.os.open
    injected = False
    replacement_name: str | None = None

    def install_nonempty_replacement(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected, replacement_name
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if is_staging and not injected:
            injected = True
            replacement_name = path
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
            replacement_descriptor = real_open(
                path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=dir_fd,
            )
            try:
                os.mkdir("nested", dir_fd=replacement_descriptor)
                rogue_descriptor = real_open(
                    "rogue.md",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o666,
                    dir_fd=replacement_descriptor,
                )
                try:
                    os.write(rogue_descriptor, b"rogue markdown\n")
                finally:
                    os.close(rogue_descriptor)
            finally:
                os.close(replacement_descriptor)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", install_nonempty_replacement)

    with pytest.raises(OSError) as raised:
        create_rooted_directory(root, Path("born"), root_identity)

    assert raised.value.errno == errno.ENOTEMPTY
    assert injected
    assert not (root / "born").exists()
    assert replacement_name is not None
    replacement = root / replacement_name
    assert replacement.joinpath("rogue.md").read_bytes() == b"rogue markdown\n"
    assert replacement.joinpath("nested").is_dir()
    assert marker.read_bytes() == b"outside"
    assert sorted(path.name for path in outside.iterdir()) == ["marker"]
    staging_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(staging_entries) == 2


def test_rooted_directory_birth_opens_before_inspecting_staging_path(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_mkdir = safeio.os.mkdir
    real_open = safeio.os.open
    real_stat = safeio.os.stat
    replacement_identity = None
    staging_opened = False

    def replace_staging_before_mkdir_returns(path, mode=0o777, *, dir_fd=None):
        nonlocal replacement_identity
        real_mkdir(path, mode, dir_fd=dir_fd)
        if isinstance(path, str) and path.startswith(".kb-born-"):
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            real_mkdir(path, mode, dir_fd=dir_fd)
            status = real_stat(path, dir_fd=dir_fd, follow_symlinks=False)
            replacement_identity = safeio.FileIdentity(
                device=status.st_dev,
                inode=status.st_ino,
            )

    def record_staging_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal staging_opened
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if isinstance(path, str) and path.startswith(".kb-born-"):
            staging_opened = True
        return descriptor

    def reject_pre_open_staging_stat(path, *, dir_fd=None, follow_symlinks=True):
        if (
            isinstance(path, str)
            and path.startswith(".kb-born-")
            and not staging_opened
        ):
            raise AssertionError("staging path was inspected before first open")
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(safeio.os, "mkdir", replace_staging_before_mkdir_returns)
    monkeypatch.setattr(safeio.os, "open", record_staging_open)
    monkeypatch.setattr(safeio.os, "stat", reject_pre_open_staging_stat)

    bound_identity = create_rooted_directory(root, Path("born"), root_identity)

    assert bound_identity == replacement_identity
    assert (root / "born").is_dir()
    retained = [
        path for path in root.iterdir() if path.name.endswith("-created")
    ]
    assert len(retained) == 1
    assert retained[0].is_dir()


def test_rooted_directory_birth_rejects_prebinding_staging_symlink(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"outside")
    root_identity = inspect_root(root)
    real_mkdir = safeio.os.mkdir

    def replace_staging_with_symlink(path, mode=0o777, *, dir_fd=None):
        real_mkdir(path, mode, dir_fd=dir_fd)
        if isinstance(path, str) and path.startswith(".kb-born-"):
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(
                outside,
                path,
                target_is_directory=True,
                dir_fd=dir_fd,
            )

    monkeypatch.setattr(safeio.os, "mkdir", replace_staging_with_symlink)

    with pytest.raises(OSError):
        create_rooted_directory(root, Path("born"), root_identity)

    assert not (root / "born").exists()
    assert marker.read_bytes() == b"outside"
    assert sorted(path.name for path in outside.iterdir()) == ["marker"]
    staging_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(staging_entries) == 2
    assert sum(path.is_symlink() for path in staging_entries) == 1
    assert sum(path.name.endswith("-created") for path in staging_entries) == 1


def test_rooted_directory_birth_rejects_real_swap_after_binding(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_publish = safeio._publish_directory_exclusive
    replacement_identity = None

    def replace_bound_staging_before_publish(parent_descriptor, staging, final):
        nonlocal replacement_identity
        os.rename(
            staging,
            f"{staging}-bound",
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.mkdir(staging, dir_fd=parent_descriptor)
        status = os.stat(
            staging,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        replacement_identity = safeio.FileIdentity(
            device=status.st_dev,
            inode=status.st_ino,
        )
        real_publish(parent_descriptor, staging, final)

    monkeypatch.setattr(
        safeio,
        "_publish_directory_exclusive",
        replace_bound_staging_before_publish,
    )

    with pytest.raises(OSError, match="identity changed"):
        create_rooted_directory(root, Path("born"), root_identity)

    published = (root / "born").stat()
    assert replacement_identity == safeio.FileIdentity(
        device=published.st_dev,
        inode=published.st_ino,
    )
    retained = [path for path in root.iterdir() if path.name.endswith("-bound")]
    assert len(retained) == 1
    assert retained[0].is_dir()
    assert not any(retained[0].iterdir())


def test_rooted_directory_birth_rejects_swap_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_stat = safeio.os.stat
    injected = False

    def replace_bound_staging_at_prepublication_check(
        path,
        *,
        dir_fd=None,
        follow_symlinks=True,
    ):
        nonlocal injected
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if is_staging and not injected:
            injected = True
            os.rename(
                path,
                f"{path}-bound",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(
        safeio.os,
        "stat",
        replace_bound_staging_at_prepublication_check,
    )

    with pytest.raises(OSError, match="identity changed"):
        create_rooted_directory(root, Path("born"), root_identity)

    assert injected
    assert not (root / "born").exists()
    staging_entries = [
        path for path in root.iterdir() if path.name.startswith(".kb-born-")
    ]
    assert len(staging_entries) == 2
    assert all(path.is_dir() and not any(path.iterdir()) for path in staging_entries)


def test_rooted_directory_birth_rechecks_emptiness_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "kb"
    root.mkdir()
    root_identity = inspect_root(root)
    real_stat = safeio.os.stat
    injected = False
    staging_name: str | None = None

    def add_entry_at_prepublication_identity_check(
        path,
        *,
        dir_fd=None,
        follow_symlinks=True,
    ):
        nonlocal injected, staging_name
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if is_staging and not injected:
            injected = True
            staging_name = path
            descriptor = os.open(
                path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=dir_fd,
            )
            try:
                late_descriptor = os.open(
                    "late.md",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o666,
                    dir_fd=descriptor,
                )
                os.close(late_descriptor)
            finally:
                os.close(descriptor)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(
        safeio.os,
        "stat",
        add_entry_at_prepublication_identity_check,
    )

    with pytest.raises(OSError) as raised:
        create_rooted_directory(root, Path("born"), root_identity)

    assert raised.value.errno == errno.ENOTEMPTY
    assert injected
    assert not (root / "born").exists()
    assert staging_name is not None
    assert (root / staging_name / "late.md").is_file()
