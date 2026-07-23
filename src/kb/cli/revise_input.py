from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from kb.core.revise import ReviseFailure


def acquire_revise_body(
    body_file: str | None,
    *,
    stdin: BinaryIO | TextIO | None = None,
) -> bytes | None:
    if body_file is None:
        return None
    if body_file == "-":
        stream = stdin if stdin is not None else getattr(sys.stdin, "buffer", sys.stdin)
        try:
            data = stream.read()
        except UnicodeDecodeError as error:
            raise ReviseFailure(
                "E_REVISE_BODY_NOT_TEXT",
                "body is not valid UTF-8 text",
                1,
            ) from error
        except OSError as error:
            raise ReviseFailure(
                "E_REVISE_IO",
                f"stdin body is unavailable: {error}",
                2,
            ) from error
        try:
            return data.encode("utf-8") if isinstance(data, str) else data
        except UnicodeEncodeError as error:
            raise ReviseFailure(
                "E_REVISE_BODY_NOT_TEXT",
                "body is not valid UTF-8 text",
                1,
            ) from error
    try:
        path = Path(body_file).expanduser()
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        return resolved.read_bytes()
    except (OSError, RuntimeError) as error:
        raise ReviseFailure(
            "E_REVISE_BODY_NOT_FOUND",
            f"body file is unavailable: {body_file}: {error}",
            2,
        ) from error
