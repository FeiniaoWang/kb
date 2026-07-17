from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from kb.core.model import Config, ConfigLoadError, load_config
from kb.core.scan import KB, RootDiscoveryError, ScannedMarkdown, discover_root, scan

Severity = Literal["error", "warning"]

RESERVED_KEYS = {
    "id",
    "type",
    "title",
    "description",
    "status",
    "derived_from",
    "timestamp",
    "last_human_touch",
    "tags",
    "supersedes",
    "instructions",
    "ingested_at",
    "origin",
    "about",
}
STRING_FIELDS = {
    "id",
    "title",
    "description",
    "origin",
    "instructions",
    "supersedes",
    "about",
}
TIMESTAMP_FIELDS = {"timestamp", "last_human_touch", "ingested_at"}
STATUS_VALUES = {"draft", "current", "superseded", "retired"}
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


class Finding(BaseModel):
    code: str
    severity: Severity
    path: str
    id: str | None
    message: str
    _occurrence: int = PrivateAttr(default=0)

    @property
    def occurrence(self) -> int:
        return self._occurrence


class ValidateRequest(BaseModel):
    refs: list[str] = Field(default_factory=list)
    strict: bool = False
    kb_root: Path | None = None


class ValidateResult(BaseModel):
    checked: int
    findings: list[Finding] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    exit_code: Literal[0, 1]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class ValidateFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code: Literal[2] = 2


def _literal_id(file: ScannedMarkdown) -> str | None:
    if file.frontmatter is None:
        return None
    value = file.frontmatter.root.get("id")
    return value if isinstance(value, str) else None


def _finding(
    file: ScannedMarkdown,
    code: str,
    severity: Severity,
    message: str,
    occurrence: int = 0,
) -> Finding:
    finding = Finding(
        code=code,
        severity=severity,
        path=file.path.as_posix(),
        id=_literal_id(file),
        message=message,
    )
    finding._occurrence = occurrence
    return finding


def _fm0(file: ScannedMarkdown, root: Path) -> list[Finding]:
    if file.parse_error is not None:
        return [
            _finding(
                file,
                "FM0_UNPARSEABLE",
                "error",
                f"frontmatter cannot be parsed: {file.parse_error}",
            )
        ]
    try:
        (root / file.path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [
            _finding(
                file,
                "FM0_UNPARSEABLE",
                "error",
                f"frontmatter cannot be parsed: {error}",
            )
        ]
    assert file.frontmatter is not None
    type_name = file.frontmatter.root.get("type")
    if not isinstance(type_name, str) or not type_name:
        return [
            _finding(
                file,
                "FM0_MISSING_TYPE",
                "error",
                "missing mandatory type frontmatter field",
            )
        ]
    return []


def _type_name(file: ScannedMarkdown) -> str:
    assert file.frontmatter is not None
    value = file.frontmatter.root["type"]
    assert isinstance(value, str) and value
    return value


def _class_contract(type_name: str) -> tuple[str, tuple[str, ...], set[str]]:
    if type_name in {"raw-source", "chat"}:
        return (
            "raw",
            ("id", "ingested_at", "origin"),
            {"id", "ingested_at", "origin", "title"},
        )
    if type_name == "feedback":
        return (
            "raw",
            ("id", "ingested_at", "origin", "about"),
            {"id", "ingested_at", "origin", "title", "about"},
        )
    if type_name in {"conventions", "kb-config", "health"}:
        return (
            "governance",
            ("id", "title", "description"),
            {"id", "title", "description"},
        )
    if type_name == "index":
        return "index", ("description",), {"description", "title"}
    return (
        "synthetic",
        (
            "id",
            "title",
            "description",
            "status",
            "derived_from",
            "timestamp",
            "last_human_touch",
        ),
        {
            "id",
            "title",
            "description",
            "status",
            "derived_from",
            "timestamp",
            "last_human_touch",
            "tags",
            "supersedes",
            "instructions",
        },
    )


def _location_expectation(type_name: str) -> tuple[bool, str]:
    if type_name == "index":
        return True, "a file named index.md"
    if type_name == "raw-source":
        return False, "under raw/sources/"
    if type_name == "chat":
        return False, "under raw/chats/"
    if type_name == "feedback":
        return False, "under raw/feedback/"
    if type_name in {"conventions", "kb-config", "health"}:
        return False, "under governance/"
    if type_name == "log":
        return False, "the root log.md"
    return False, "under synthetic/"


def _location_matches(file: ScannedMarkdown, type_name: str) -> bool:
    path = file.path
    if type_name == "index":
        return path.name == "index.md"
    if path.name == "index.md":
        return False
    if type_name == "log":
        return path == Path("log.md")
    expected = {
        "raw-source": Path("raw/sources"),
        "chat": Path("raw/chats"),
        "feedback": Path("raw/feedback"),
    }.get(type_name)
    if expected is None:
        expected = (
            Path("governance")
            if type_name in {"conventions", "kb-config", "health"}
            else Path("synthetic")
        )
    return path.parent == expected or expected in path.parent.parents


def _location_findings(file: ScannedMarkdown) -> list[Finding]:
    type_name = _type_name(file)
    if _location_matches(file, type_name):
        return []
    _, expectation = _location_expectation(type_name)
    return [
        _finding(
            file,
            "LOC_TYPE_MISMATCH",
            "error",
            f"type '{type_name}' does not agree with location "
            f"'{file.path.as_posix()}' (expected {expectation})",
        )
    ]


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _invalid_reason(field: str, value: object) -> str | None:
    if field in STRING_FIELDS:
        return (
            None
            if isinstance(value, str) and value.strip()
            else "must be a non-empty string"
        )
    if field == "status":
        return (
            None
            if isinstance(value, str) and value in STATUS_VALUES
            else "must be one of draft, current, superseded, retired"
        )
    if field in {"derived_from", "tags"}:
        valid = isinstance(value, list) and all(
            isinstance(item, str) and item.strip() for item in value
        )
        return None if valid else "must be a list of non-empty strings"
    if field in TIMESTAMP_FIELDS:
        return (
            None
            if _parse_timestamp(value) is not None
            else "must be an ISO-8601 date-time string"
        )
    return None


def _schema_findings(file: ScannedMarkdown) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    if type_name == "log":
        return []
    class_name, mandatory, legal = _class_contract(type_name)
    findings: list[Finding] = []
    for occurrence, field in enumerate(mandatory):
        if field not in values:
            findings.append(
                _finding(
                    file,
                    "FM1_FIELD_MISSING",
                    "error",
                    f"missing mandatory field '{field}' for {class_name} documents",
                    occurrence,
                )
            )
    for occurrence, (field, value) in enumerate(values.items()):
        if field == "type" or field not in RESERVED_KEYS:
            continue
        if field not in legal:
            findings.append(
                _finding(
                    file,
                    "FM1_KEY_FORBIDDEN",
                    "error",
                    f"key '{field}' is not part of the {class_name} schema",
                    occurrence,
                )
            )
            continue
        reason = _invalid_reason(field, value)
        if reason is not None:
            findings.append(
                _finding(
                    file,
                    "FM1_FIELD_INVALID",
                    "error",
                    f"field '{field}' is invalid: {reason}",
                    occurrence,
                )
            )
    description = values.get("description")
    if isinstance(description, str) and len(SENTENCE_END.findall(description)) > 2:
        findings.append(
            _finding(
                file,
                "FM1_DESCRIPTION_LONG",
                "warning",
                "description exceeds two sentences",
                list(values).index("description"),
            )
        )
    return findings


def _file_findings(file: ScannedMarkdown, config: Config, kb: KB) -> list[Finding]:
    fm0 = _fm0(file, kb.root)
    if fm0:
        return fm0
    findings = _location_findings(file)
    if _type_name(file) != "log":
        findings.extend(_schema_findings(file))
    return findings


def _all_findings(kb: KB, config: Config) -> list[Finding]:
    findings = [
        finding for file in kb.files for finding in _file_findings(file, config, kb)
    ]
    return sorted(findings, key=lambda item: (item.path, item.code, item.occurrence))


def validate(request: ValidateRequest) -> ValidateResult:
    try:
        root = discover_root(request.kb_root)
        config = load_config(root)
    except (RootDiscoveryError, ConfigLoadError) as error:
        raise ValidateFailure(error.code, error.message) from error
    kb = scan(root)
    findings = _all_findings(kb, config)
    failed = any(item.severity == "error" for item in findings)
    if request.strict and findings:
        failed = True
    return ValidateResult(
        checked=len(kb.files),
        findings=findings,
        unresolved_refs=[],
        exit_code=1 if failed else 0,
    )
