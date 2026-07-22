from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

import kb.cli.ingest_adapters as adapters
from kb.core.ingest import IngestFailure


def test_bind_is_inert_and_reports_only_source_shape(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("binding and shape inspection must perform no acquisition")

    monkeypatch.setattr(Path, "stat", explode)
    monkeypatch.setattr(Path, "resolve", explode)
    monkeypatch.setattr(Path, "read_bytes", explode)
    monkeypatch.setattr(adapters, "_stdin_stream", explode)
    monkeypatch.setattr(adapters.platform, "system", explode)
    monkeypatch.setattr(adapters.shutil, "which", explode)
    monkeypatch.setattr(adapters.subprocess, "run", explode)

    for source_kind, source, locator_present in [
        ("file", "/missing/source.md", True),
        ("stdin", None, False),
        ("clipboard", None, False),
    ]:
        bound = adapters.bind_ingest_source(source_kind, source)
        assert bound.shape.source_kind == source_kind
        assert bound.shape.locator_present is locator_present


def test_adapter_registry_uses_private_module_convention() -> None:
    assert hasattr(adapters, "_ADAPTERS")
    assert not hasattr(adapters, "ADAPTERS")


def test_file_adapter_preserves_bytes_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "Report.PDF"
    source.write_bytes(b"\xff\x00report")
    payload = adapters.bind_ingest_source("file", str(source)).acquire()
    assert payload.source_kind == "file"
    assert payload.data == b"\xff\x00report"
    assert payload.default_origin == str(source.resolve())
    assert payload.source_filename == "Report.PDF"


def test_stdin_adapter_preserves_bytes(monkeypatch) -> None:
    monkeypatch.setattr(adapters, "_stdin_stream", lambda: BytesIO(b"chat\r\n"))
    payload = adapters.bind_ingest_source("stdin", None).acquire()
    assert payload.model_dump() == {
        "source_kind": "stdin",
        "data": b"chat\r\n",
        "default_origin": "stdin",
        "source_filename": None,
    }


def test_clipboard_adapter_reports_nonzero_exit(monkeypatch) -> None:
    class Completed:
        returncode = 9
        stdout = b""
        stderr = b"clipboard unavailable"

    monkeypatch.setattr(adapters.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(adapters.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(adapters.subprocess, "run", lambda *args, **kwargs: Completed())
    with pytest.raises(IngestFailure) as raised:
        adapters.bind_ingest_source("clipboard", None).acquire()
    assert (raised.value.code, raised.value.exit_code) == (
        "E_INGEST_CLIPBOARD",
        2,
    )
    assert raised.value.message == "clipboard tool exited 9: clipboard unavailable"
