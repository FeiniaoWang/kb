from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from kb.core.model import Config, ConfigLoadError, load_config
from kb.core.scan import KB, RootDiscoveryError, ScannedMarkdown, discover_root, scan

Severity = Literal["error", "warning"]


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


def _file_findings(file: ScannedMarkdown, config: Config, kb: KB) -> list[Finding]:
    return _fm0(file, kb.root)


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
