from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

import yaml
from pydantic import BaseModel, Field

from kb.core.model import DocClass, Document, Frontmatter

ID_REF_PATTERN = re.compile(
    r"^(?:[A-Z]+-(?:[0-9]{6}|[1-9][0-9]{6,})|GOVERNANCE-[A-Z][A-Z0-9-]*)$"
)
NO_KB_MESSAGE = (
    "not inside a knowledge base (no kb-config.json found); "
    "run 'kb init' or pass --kb"
)
YAML_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


class _FrontmatterSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that leaves timestamp-looking scalars as strings."""


_FrontmatterSafeLoader.yaml_implicit_resolvers = {
    initial: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag != YAML_TIMESTAMP_TAG
    ]
    for initial, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class ScannedMarkdown(BaseModel):
    path: Path
    frontmatter: Frontmatter | None = None
    parse_error: str | None = None


class KB(BaseModel):
    root: Path
    files: list[ScannedMarkdown] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    by_id: dict[str, Document] = Field(default_factory=dict)
    malformed: list[tuple[Path, str]] = Field(default_factory=list)


class RootDiscoveryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def discover_root(explicit: Path | None, *, cwd: Path | None = None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if (candidate / "kb-config.json").is_file():
            return candidate
        raise RootDiscoveryError("E_NO_KB", NO_KB_MESSAGE)
    current = (cwd if cwd is not None else Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "kb-config.json").is_file():
            return candidate
    raise RootDiscoveryError("E_NO_KB", NO_KB_MESSAGE)


def read_frontmatter_bytes(content: bytes) -> Frontmatter:
    text = content.decode("utf-8", errors="strict")
    yaml_lines: list[str] = []
    lines = iter(text.splitlines(keepends=True))
    first = next(lines, "")
    if first.rstrip("\r\n") != "---":
        raise ValueError("missing opening frontmatter delimiter")
    for line in lines:
        if line.rstrip("\r\n") == "---":
            break
        yaml_lines.append(line)
    else:
        raise ValueError("missing closing frontmatter delimiter")
    parsed: Any = yaml.load("".join(yaml_lines), Loader=_FrontmatterSafeLoader)
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return Frontmatter.model_validate(parsed)


def read_frontmatter_prefix(stream: BinaryIO) -> bytes:
    prefix = bytearray()
    first = stream.readline()
    prefix.extend(first)
    if first.rstrip(b"\r\n") != b"---":
        return bytes(prefix)
    while True:
        line = stream.readline()
        if not line:
            return bytes(prefix)
        prefix.extend(line)
        if line.rstrip(b"\r\n") == b"---":
            return bytes(prefix)


def read_frontmatter(path: Path) -> Frontmatter:
    with path.open("rb") as stream:
        return read_frontmatter_bytes(read_frontmatter_prefix(stream))


def doc_class_from_type(type_name: str) -> DocClass | None:
    if type_name == "log":
        return DocClass.OPERATIONAL
    if type_name == "index":
        return DocClass.INDEX
    if type_name in {"raw-source", "chat", "feedback"}:
        return DocClass.RAW
    if type_name in {"charter", "conventions", "kb-config", "health"}:
        return DocClass.GOVERNANCE
    return DocClass.SYNTHETIC


def _scan_sources(
    resolved: Path,
    sources: Iterable[tuple[Path, bytes | None]],
) -> KB:
    kb = KB(root=resolved)
    for relative, frontmatter_prefix in sources:
        source_path = resolved / relative
        try:
            frontmatter = (
                read_frontmatter(source_path)
                if frontmatter_prefix is None
                else read_frontmatter_bytes(frontmatter_prefix)
            )
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            message = str(error)
            kb.files.append(ScannedMarkdown(path=relative, parse_error=message))
            kb.malformed.append((relative, message))
            continue
        kb.files.append(ScannedMarkdown(path=relative, frontmatter=frontmatter))
        type_name = frontmatter.root.get("type")
        if not isinstance(type_name, str) or not type_name:
            kb.malformed.append((relative, "frontmatter is missing mandatory type"))
            continue
        doc_class = doc_class_from_type(type_name)
        if doc_class is None:
            continue
        document = Document.from_scan(
            source_path=source_path,
            relative_path=relative,
            doc_class=doc_class,
            frontmatter=frontmatter,
        )
        kb.documents.append(document)
        if document.id is not None:
            kb.by_id.setdefault(document.id, document)
    return kb


def scan(root: Path) -> KB:
    resolved = root.resolve()
    sources = (
        (source_path.relative_to(resolved), None)
        for source_path in sorted(resolved.rglob("*.md"))
    )
    return _scan_sources(resolved, sources)


def scan_snapshot(root: Path, files: Mapping[Path, bytes]) -> KB:
    return _scan_sources(root, sorted(files.items()))


def resolve_ref(kb: KB, ref: str) -> Document | None:
    if ID_REF_PATTERN.fullmatch(ref):
        return kb.by_id.get(ref)
    candidate = PurePosixPath(ref)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        return None
    if not str(candidate).endswith(".md"):
        candidate = PurePosixPath(f"{candidate}.md")
    path = Path(*candidate.parts)
    return next((document for document in kb.documents if document.path == path), None)
