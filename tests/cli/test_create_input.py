from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from kb.cli.create_input import acquire_create_body
from kb.core.create import CreateFailure


def test_omitted_body_returns_none_without_reading_stdin() -> None:
    class ExplodingStream:
        def read(self) -> bytes:
            raise AssertionError("stdin must not be read")

    assert acquire_create_body(None, stdin=ExplodingStream()) is None


def test_dash_reads_explicit_stdin_as_bytes() -> None:
    assert acquire_create_body("-", stdin=BytesIO(b"body\r\n")) == b"body\r\n"


def test_external_body_file_is_read_byte_identically(tmp_path: Path) -> None:
    path = tmp_path / "body.md"
    path.write_bytes(b"\xffbody\r\n")
    assert acquire_create_body(str(path)) == b"\xffbody\r\n"


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_unavailable_body_raises_exact_create_failure(
    tmp_path: Path,
    kind: str,
) -> None:
    path = tmp_path / "body.md"
    if kind == "directory":
        path.mkdir()
    with pytest.raises(CreateFailure) as raised:
        acquire_create_body(str(path))
    assert raised.value.code == "E_CREATE_BODY_NOT_FOUND"
    assert raised.value.exit_code == 2
    assert raised.value.message.startswith(f"body file is unavailable: {path}:")
