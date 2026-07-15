from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

CURRENT_SCHEMA = 1


class DocClass(StrEnum):
    RAW = "raw"
    SYNTHETIC = "synthetic"
    GOVERNANCE = "governance"
    INDEX = "index"


class RawClass(StrEnum):
    SOURCE = "source"
    CHAT = "chat"
    FEEDBACK = "feedback"


class Frontmatter(RootModel[dict[str, Any]]):
    """Insertion-ordered, lossless view of parsed YAML frontmatter."""


class GovernanceFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["conventions", "kb-config", "health"]
    title: str
    description: str


class IndexFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["index"]
    description: str
    title: str | None = None


def _default_prefixes() -> dict[str, str]:
    return {
        "synthetic": "KB",
        "source": "RAW",
        "chat": "CHAT",
        "feedback": "FEED",
    }


class Config(BaseModel):
    schema: int = CURRENT_SCHEMA
    types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    id_prefixes: dict[str, str] = Field(default_factory=_default_prefixes)
    propagation_auto_safe: list[str] = Field(default_factory=list)


class ConfigLoadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_config(root: Path) -> Config:
    path = root / "kb-config.json"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise TypeError("configuration must be a JSON object")
        config = Config.model_validate(parsed)
    except (OSError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise ConfigLoadError("E_CONFIG_INVALID", f"invalid kb-config.json: {error}") from error
    if config.schema > CURRENT_SCHEMA:
        raise ConfigLoadError(
            "E_SCHEMA_UNSUPPORTED",
            f"unsupported KB schema {config.schema}; maximum supported schema is {CURRENT_SCHEMA}",
        )
    return config
