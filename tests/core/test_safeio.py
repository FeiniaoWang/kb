import pytest

from kb.core.safeio import (
    append_mutable_bytes,
    inspect_mutable_file,
    overwrite_mutable_bytes,
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
