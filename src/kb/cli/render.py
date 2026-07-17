import json
from typing import Protocol

from kb.core.create import CreateResult
from kb.core.housekeeping import InitFailure, InitResult
from kb.core.ingest import IngestResult
from kb.core.validate import ValidateResult


class CommandError(Protocol):
    code: str
    message: str


def render_init_text(result: InitResult) -> str:
    lines = [f"created  {path}" for path in result.created]
    lines.extend(f"overwritten  {path}" for path in result.overwritten)
    lines.extend(f"skipped  {path} (exists)" for path in result.skipped)
    lines.sort(key=lambda line: line.split("  ", 1)[1].removesuffix(" (exists)"))
    lines.append(
        f"KB ready at {result.root} — {len(result.created)} created, "
        f"{len(result.overwritten)} overwritten, {len(result.skipped)} skipped"
    )
    return "\n".join(lines)


def render_init_json(result: InitResult) -> str:
    return json.dumps(
        {
            "ok": True,
            "root": str(result.root),
            "created": result.created,
            "overwritten": result.overwritten,
            "skipped": result.skipped,
        },
        ensure_ascii=False,
    )


def render_ingest_text(result: IngestResult) -> str:
    lines = [f"created  {path}" for path in sorted(result.created)]
    lines.extend(f"updated  {path}" for path in sorted(result.updated))
    lines.append(f"ingested {result.id} as {result.path}")
    return "\n".join(lines)


def render_ingest_json(result: IngestResult) -> str:
    return json.dumps(
        {
            "ok": True,
            "id": result.id,
            "path": result.path,
            "original": result.original,
            "created": result.created,
            "updated": result.updated,
        },
        ensure_ascii=False,
    )


def render_create_text(result: CreateResult) -> str:
    changes = [(path, "created") for path in result.created]
    changes.extend((path, "updated") for path in result.updated)
    lines = [f"{action}  {path}" for path, action in sorted(changes)]
    lines.append(f"created {result.id} as {result.path}")
    return "\n".join(lines)


def render_create_json(result: CreateResult) -> str:
    return json.dumps(
        {
            "ok": True,
            "id": result.id,
            "path": result.path,
            "superseded": result.superseded,
            "created": sorted(result.created),
            "updated": sorted(result.updated),
        },
        ensure_ascii=False,
    )


def render_validate_text(result: ValidateResult) -> str:
    lines = [
        f"{item.severity}  {item.path}  {item.code}  {item.message}"
        for item in result.findings
    ]
    errors = sum(item.severity == "error" for item in result.findings)
    warnings = sum(item.severity == "warning" for item in result.findings)
    total = len(result.findings)
    if total == 0:
        lines.append(f"no findings — checked {result.checked} files")
    else:
        noun = "finding" if total == 1 else "findings"
        error_noun = "error" if errors == 1 else "errors"
        warning_noun = "warning" if warnings == 1 else "warnings"
        lines.append(
            f"{total} {noun} ({errors} {error_noun}, "
            f"{warnings} {warning_noun}) — "
            f"checked {result.checked} files"
        )
    return "\n".join(lines)


def render_validate_json(result: ValidateResult) -> str:
    errors = sum(item.severity == "error" for item in result.findings)
    warnings = sum(item.severity == "warning" for item in result.findings)
    return json.dumps(
        {
            "ok": result.ok,
            "checked": result.checked,
            "findings": [item.model_dump() for item in result.findings],
            "counts": {"errors": errors, "warnings": warnings},
            "unresolved_refs": result.unresolved_refs,
        },
        ensure_ascii=False,
    )


def render_error_text(error: CommandError) -> str:
    return f"{error.code}: {error.message}"


def render_error_json(error: CommandError) -> str:
    return json.dumps(
        {"error": {"code": error.code, "message": error.message}},
        ensure_ascii=False,
    )
