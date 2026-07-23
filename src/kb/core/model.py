from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    ValidationError,
    field_validator,
)

CURRENT_SCHEMA = 1
ID_PREFIX_PATTERN = re.compile(r"^[A-Z]+$")
CANONICAL_NUMERIC_ID_PATTERN = re.compile(
    r"^[A-Z]+-(?:[0-9]{6}|[1-9][0-9]{6,})$"
)
RESERVED_GOVERNANCE_ID_PATTERN = re.compile(r"^GOVERNANCE-[A-Z][A-Z0-9-]*$")


class DocClass(StrEnum):
    RAW = "raw"
    SYNTHETIC = "synthetic"
    GOVERNANCE = "governance"
    INDEX = "index"
    OPERATIONAL = "operational"


class RawClass(StrEnum):
    SOURCE = "source"
    CHAT = "chat"
    FEEDBACK = "feedback"


class Frontmatter(RootModel[dict[str, Any]]):
    """Insertion-ordered, lossless view of parsed YAML frontmatter."""


class GovernanceFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["charter", "conventions", "kb-config", "health"]
    title: str
    description: str


class IndexFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["index"]
    description: str
    title: str | None = None


class OperationalFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["log"]


class RawFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["raw-source", "chat", "feedback"]
    ingested_at: str
    origin: str
    title: str
    about: str | None = None


class SyntheticFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    title: str
    description: str
    status: Literal["draft", "current", "superseded", "retired"]
    derived_from: list[str]
    timestamp: str
    last_human_touch: str
    tags: list[str] | None = None
    supersedes: str | None = None
    instructions: str | None = None
    links: dict[str, list[str]] | None = None
    pending_upstream: list[str] | None = None


class Document(BaseModel):
    id: str | None
    path: Path
    doc_class: DocClass
    frontmatter: Frontmatter
    _source_path: Path = PrivateAttr()

    @classmethod
    def from_scan(
        cls,
        *,
        source_path: Path,
        relative_path: Path,
        doc_class: DocClass,
        frontmatter: Frontmatter,
    ) -> Document:
        raw_id = frontmatter.root.get("id")
        document_id: str | None = None
        if isinstance(raw_id, str):
            if (
                doc_class in {DocClass.RAW, DocClass.SYNTHETIC}
                and CANONICAL_NUMERIC_ID_PATTERN.fullmatch(raw_id)
            ) or (
                doc_class is DocClass.GOVERNANCE
                and RESERVED_GOVERNANCE_ID_PATTERN.fullmatch(raw_id)
            ):
                document_id = raw_id
        document = cls(
            id=document_id,
            path=relative_path,
            doc_class=doc_class,
            frontmatter=frontmatter,
        )
        document._source_path = source_path
        return document

    @property
    def body(self) -> str:
        text = self._source_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines[1:], start=1):
            if line.rstrip("\r\n") == "---":
                return "".join(lines[index + 1 :])
        raise ValueError(f"missing closing frontmatter delimiter: {self.path}")


def _default_prefixes() -> dict[str, str]:
    return {
        "synthetic": "KB",
        "source": "RAW",
        "chat": "CHAT",
        "feedback": "FEED",
    }


class Config(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    schema_: int = Field(
        default=CURRENT_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    link_types: list[str] = Field(default_factory=list)
    id_prefixes: dict[str, str] = Field(default_factory=_default_prefixes)
    propagation_auto_safe: list[str] = Field(default_factory=list)

    @field_validator("id_prefixes", mode="before")
    @classmethod
    def merge_default_id_prefixes(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        merged = _default_prefixes()
        merged.update(value)
        return merged

    @field_validator("id_prefixes")
    @classmethod
    def validate_id_prefixes(cls, value: dict[str, str]) -> dict[str, str]:
        for class_name, prefix in value.items():
            if not ID_PREFIX_PATTERN.fullmatch(prefix):
                raise ValueError(
                    f"id prefix for {class_name!r} must contain uppercase letters only"
                )
            if prefix == "GOVERNANCE":
                raise ValueError("reserved id prefix: GOVERNANCE")
        return value

    @property
    def schema(self) -> int:
        return self.schema_


class ConfigLoadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_config_bytes(content: bytes) -> Config:
    try:
        parsed = json.loads(content.decode("utf-8", errors="strict"))
        if not isinstance(parsed, dict):
            raise TypeError("configuration must be a JSON object")
        config = Config.model_validate(parsed)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise ConfigLoadError("E_CONFIG_INVALID", f"invalid kb-config.json: {error}") from error
    if config.schema > CURRENT_SCHEMA:
        raise ConfigLoadError(
            "E_SCHEMA_UNSUPPORTED",
            f"unsupported KB schema {config.schema}; maximum supported schema is {CURRENT_SCHEMA}",
        )
    return config


def load_config(root: Path) -> Config:
    path = root / "kb-config.json"
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ConfigLoadError(
            "E_CONFIG_INVALID",
            f"invalid kb-config.json: {error}",
        ) from error
    return parse_config_bytes(content)
