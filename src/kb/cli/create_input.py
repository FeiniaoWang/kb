from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from kb.core.create import CreateFailure


def acquire_create_body(
    body_file: str | None,
    *,
    stdin: BinaryIO | TextIO | None = None,
) -> bytes | None:
    if body_file is None:
        return None
    if body_file == "-":
        stream = stdin if stdin is not None else getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        return data.encode("utf-8") if isinstance(data, str) else data
    path = Path(body_file).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        return resolved.read_bytes()
    except OSError as error:
        raise CreateFailure(
            "E_CREATE_BODY_NOT_FOUND",
            f"body file is unavailable: {body_file}: {error}",
            2,
        ) from error
