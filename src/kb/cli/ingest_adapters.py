from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from kb.core.ingest import (
    AdapterPayload,
    IngestFailure,
    IngestSourceShape,
    SourceKind,
)

Adapter = Callable[[str | None], AdapterPayload]


def _stdin_stream():
    return getattr(sys.stdin, "buffer", sys.stdin)


def _file_adapter(source: str | None) -> AdapterPayload:
    if source is None:
        raise IngestFailure("E_INGEST_USAGE", "SOURCE is required with --from file", 2)
    path = Path(source).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        data = resolved.read_bytes()
    except OSError as error:
        raise IngestFailure(
            "E_INGEST_SOURCE_NOT_FOUND",
            f"source file is unavailable: {source}: {error}",
            2,
        ) from error
    return AdapterPayload(
        source_kind="file",
        data=data,
        default_origin=str(resolved),
        source_filename=resolved.name,
    )


def _stdin_adapter(source: str | None) -> AdapterPayload:
    if source is not None:
        raise IngestFailure(
            "E_INGEST_USAGE", "SOURCE is forbidden with --from stdin", 2
        )
    data = _stdin_stream().read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    return AdapterPayload(
        source_kind="stdin",
        data=data,
        default_origin="stdin",
        source_filename=None,
    )


def _clipboard_adapter(source: str | None) -> AdapterPayload:
    if source is not None:
        raise IngestFailure(
            "E_INGEST_USAGE", "SOURCE is forbidden with --from clipboard", 2
        )
    system = platform.system()
    candidates: list[list[str]]
    if system == "Darwin":
        candidates = [["pbpaste"]]
    elif system == "Windows":
        candidates = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    else:
        candidates = [["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]]
    command = next(
        (candidate for candidate in candidates if shutil.which(candidate[0])), None
    )
    if command is None:
        raise IngestFailure(
            "E_INGEST_CLIPBOARD", "no supported clipboard tool found on PATH", 2
        )
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise IngestFailure("E_INGEST_CLIPBOARD", str(error), 2) from error
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise IngestFailure(
            "E_INGEST_CLIPBOARD",
            f"clipboard tool exited {completed.returncode}"
            + (f": {message}" if message else ""),
            2,
        )
    return AdapterPayload(
        source_kind="clipboard",
        data=completed.stdout,
        default_origin="clipboard",
        source_filename=None,
    )


ADAPTERS: dict[SourceKind, Adapter] = {
    "file": _file_adapter,
    "stdin": _stdin_adapter,
    "clipboard": _clipboard_adapter,
}


class BoundIngestSource:
    def __init__(self, source_kind: SourceKind, source: str | None) -> None:
        self._source_kind = source_kind
        self._source = source

    @property
    def shape(self) -> IngestSourceShape:
        return IngestSourceShape(
            source_kind=self._source_kind,
            locator_present=self._source is not None,
        )

    def acquire(self) -> AdapterPayload:
        return ADAPTERS[self._source_kind](self._source)


def bind_ingest_source(
    source_kind: SourceKind,
    source: str | None,
) -> BoundIngestSource:
    return BoundIngestSource(source_kind, source)
