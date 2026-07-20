from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from kb.core.housekeeping import LogEntry, append_log, utc_now
from kb.core.ids import next_id
from kb.core.indexing import regenerate_directory_index
from kb.core.model import ConfigLoadError, RawClass, RawFrontmatter, load_config
from kb.core.scan import KB, RootDiscoveryError, discover_root, resolve_ref, scan

CLASS_DIR = {
    RawClass.SOURCE: Path("raw/sources"),
    RawClass.CHAT: Path("raw/chats"),
    RawClass.FEEDBACK: Path("raw/feedback"),
}
CLASS_TYPE = {
    RawClass.SOURCE: "raw-source",
    RawClass.CHAT: "chat",
    RawClass.FEEDBACK: "feedback",
}


class AdapterPayload(BaseModel):
    data: bytes
    default_origin: str
    source_filename: str | None


Adapter = Callable[[str | None], AdapterPayload]


class IngestRequest(BaseModel):
    raw_class: RawClass
    source_kind: Literal["file", "stdin", "clipboard"]
    source: str | None = None
    dest: str | None = None
    about: str | None = None
    title: str | None = None
    origin: str | None = None
    actor: str = "kb-cli"
    kb_root: Path | None = None


class IngestResult(BaseModel):
    id: str
    path: str
    original: str | None = None
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)


class IngestFailure(Exception):
    def __init__(self, code: str, message: str, exit_code: Literal[1, 2]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


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
        data=data,
        default_origin=str(resolved),
        source_filename=resolved.name,
    )


def _stdin_adapter(source: str | None) -> AdapterPayload:
    if source is not None:
        raise IngestFailure(
            "E_INGEST_USAGE", "SOURCE is forbidden with --from stdin", 2
        )
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    data = stream.read()
    if isinstance(data, str):
        data = data.encode("utf-8")
    return AdapterPayload(data=data, default_origin="stdin", source_filename=None)


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
        data=completed.stdout,
        default_origin="clipboard",
        source_filename=None,
    )


ADAPTERS: dict[str, Adapter] = {
    "file": _file_adapter,
    "stdin": _stdin_adapter,
    "clipboard": _clipboard_adapter,
}


def slug(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    candidate = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return candidate or fallback.lower()


def _normalized_input(
    payload: AdapterPayload, source_kind: str
) -> tuple[str | None, bytes | None]:
    try:
        decoded = payload.data.decode("utf-8")
    except UnicodeDecodeError as error:
        if source_kind == "file":
            return None, payload.data
        raise IngestFailure(
            "E_INGEST_NOT_TEXT", f"{source_kind} input is not UTF-8 text", 1
        ) from error
    if not decoded.strip():
        raise IngestFailure("E_INGEST_EMPTY", "input is empty or whitespace-only", 1)
    return (
        decoded.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n",
        None,
    )


def _surface(request: IngestRequest) -> None:
    if request.source_kind == "file" and request.source is None:
        raise IngestFailure("E_INGEST_USAGE", "SOURCE is required with --from file", 2)
    if request.source_kind != "file" and request.source is not None:
        raise IngestFailure(
            "E_INGEST_USAGE",
            f"SOURCE is forbidden with --from {request.source_kind}",
            2,
        )
    if request.raw_class is RawClass.FEEDBACK and request.about is None:
        raise IngestFailure(
            "E_INGEST_USAGE", "--about is required for --class feedback", 2
        )
    if request.raw_class is not RawClass.FEEDBACK and request.about is not None:
        raise IngestFailure(
            "E_INGEST_USAGE", "--about is forbidden unless --class feedback", 2
        )
    if request.dest is not None:
        raise IngestFailure(
            "E_INGEST_DEST_INVALID", f"invalid --dest: {request.dest}", 2
        )


def _canonical_about(kb: KB, request: IngestRequest) -> str | None:
    if request.about is None:
        return None
    document = resolve_ref(kb, request.about)
    if document is None or document.id is None:
        raise IngestFailure(
            "E_INGEST_ABOUT_UNRESOLVED",
            f"feedback target cannot be resolved: {request.about}",
            1,
        )
    return document.id


def _derived_title(
    request: IngestRequest, payload: AdapterPayload, doc_id: str
) -> str:
    if request.title is not None:
        return request.title
    if payload.source_filename is not None:
        stem = Path(payload.source_filename).stem
        return re.sub(r"\s+", " ", stem.replace("-", " ").replace("_", " ")).strip()
    return doc_id


def _scalar(value: str) -> str:
    dumped = yaml.safe_dump(
        value, allow_unicode=True, default_flow_style=True
    ).strip()
    lines = dumped.splitlines()
    if lines and lines[-1] == "." * 3:
        lines.pop()
    return "\n".join(lines).rstrip()


def _document(frontmatter: RawFrontmatter, body: str) -> str:
    lines = [
        f"id: {_scalar(frontmatter.id)}",
        f"type: {_scalar(frontmatter.type)}",
        f"ingested_at: {frontmatter.ingested_at}",
        f"origin: {_scalar(frontmatter.origin)}",
        f"title: {_scalar(frontmatter.title)}",
    ]
    if frontmatter.about is not None:
        lines.append(f"about: {_scalar(frontmatter.about)}")
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def _failure_from_config(error: ConfigLoadError) -> IngestFailure:
    return IngestFailure(error.code, error.message, 2)


def ingest(request: IngestRequest) -> IngestResult:
    try:
        root = discover_root(request.kb_root)
    except RootDiscoveryError as error:
        raise IngestFailure(error.code, error.message, 2) from error
    try:
        config = load_config(root)
    except ConfigLoadError as error:
        raise _failure_from_config(error) from error
    kb = scan(root)
    if kb.malformed:
        paths = ", ".join(path.as_posix() for path, _ in kb.malformed)
        raise IngestFailure(
            "E_INGEST_MALFORMED",
            f"malformed documents block id allocation: {paths}; run kb validate",
            2,
        )
    _surface(request)
    payload = ADAPTERS[request.source_kind](request.source)
    text_body, original_bytes = _normalized_input(payload, request.source_kind)
    about = _canonical_about(kb, request)
    doc_id = next_id(kb, config.id_prefixes[request.raw_class.value]).format()
    title = _derived_title(request, payload, doc_id)
    stem_source = request.title if request.title is not None else (
        Path(payload.source_filename).stem
        if payload.source_filename is not None
        else doc_id.lower()
    )
    stem = slug(stem_source, doc_id)
    target_dir = root / CLASS_DIR[request.raw_class]
    extension = ""
    if original_bytes is not None and payload.source_filename is not None:
        extension = Path(payload.source_filename).suffix.lower()
    document_path = target_dir / f"{stem}.md"
    original_path = target_dir / f"{stem}{extension}" if original_bytes is not None else None
    if document_path.exists() or (
        original_path is not None and original_path.exists()
    ):
        stem = f"{stem}-{doc_id.lower()}"
        document_path = target_dir / f"{stem}.md"
        original_path = target_dir / f"{stem}{extension}" if original_bytes is not None else None
        if document_path.exists() or (
            original_path is not None and original_path.exists()
        ):
            raise IngestFailure(
                "E_INGEST_IO",
                "refusing to overwrite existing raw path",
                2,
            )
    body = text_body
    if original_path is not None:
        body = (
            f"Non-text original stored alongside this stub: "
            f"[{original_path.name}]({original_path.name})\n"
        )
    assert body is not None
    path = document_path
    timestamp = utc_now()
    frontmatter = RawFrontmatter(
        id=doc_id,
        type=CLASS_TYPE[request.raw_class],
        ingested_at=timestamp,
        origin=request.origin if request.origin is not None else payload.default_origin,
        title=title,
        about=about,
    )
    relative = path.relative_to(root).as_posix()
    try:
        if original_path is not None and original_bytes is not None:
            original_path.write_bytes(original_bytes)
        path.write_text(_document(frontmatter, body), encoding="utf-8", newline="\n")
        index = target_dir / "index.md"
        index.write_text(
            regenerate_directory_index(root, target_dir),
            encoding="utf-8",
            newline="\n",
        )
        append_log(
            root,
            LogEntry(
                at=timestamp,
                action="ingested",
                actor=request.actor,
                doc_ids=[doc_id],
                note=f"{relative} from {frontmatter.origin}",
            ),
        )
    except OSError as error:
        raise IngestFailure("E_INGEST_IO", str(error), 2) from error
    created = [relative]
    original_relative = None
    if original_path is not None:
        original_relative = original_path.relative_to(root).as_posix()
        created.append(original_relative)
    return IngestResult(
        id=doc_id,
        path=relative,
        original=original_relative,
        created=sorted(created),
        updated=[index.relative_to(root).as_posix()],
    )
