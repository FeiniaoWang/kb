from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, Field

from kb.core.model import DocClass, Document, Frontmatter

ID_REF_PATTERN = re.compile(r"^[A-Z]+-(?:[0-9]{6,}|[A-Z][A-Z0-9-]*)$")
NO_KB_MESSAGE = (
    "not inside a knowledge base (no kb-config.json found); "
    "run 'kb init' or pass --kb"
)


class KB(BaseModel):
    root: Path
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


def read_frontmatter(path: Path) -> Frontmatter:
    yaml_lines: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        if stream.readline().rstrip("\r\n") != "---":
            raise ValueError("missing opening frontmatter delimiter")
        for line in stream:
            if line.rstrip("\r\n") == "---":
                break
            yaml_lines.append(line)
        else:
            raise ValueError("missing closing frontmatter delimiter")
    parsed: Any = yaml.safe_load("".join(yaml_lines))
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    if not isinstance(parsed.get("type"), str) or not parsed["type"]:
        raise ValueError("frontmatter is missing mandatory type")
    return Frontmatter.model_validate(parsed)


def _doc_class(type_name: str) -> DocClass | None:
    if type_name == "log":
        return None
    if type_name == "index":
        return DocClass.INDEX
    if type_name in {"raw-source", "chat", "feedback"}:
        return DocClass.RAW
    if type_name in {"conventions", "kb-config", "health"}:
        return DocClass.GOVERNANCE
    return DocClass.SYNTHETIC


def scan(root: Path) -> KB:
    resolved = root.resolve()
    kb = KB(root=resolved)
    for source_path in sorted(resolved.rglob("*.md")):
        relative = source_path.relative_to(resolved)
        try:
            frontmatter = read_frontmatter(source_path)
            doc_class = _doc_class(frontmatter.root["type"])
            if doc_class is None:
                continue
            document = Document.from_scan(
                source_path=source_path,
                relative_path=relative,
                doc_class=doc_class,
                frontmatter=frontmatter,
            )
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            kb.malformed.append((relative, str(error)))
            continue
        kb.documents.append(document)
        if document.id is not None:
            kb.by_id.setdefault(document.id, document)
    return kb


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
