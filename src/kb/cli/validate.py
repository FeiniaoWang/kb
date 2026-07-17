from pathlib import Path
from typing import Annotated

import typer

from kb.cli.render import (
    render_error_json,
    render_error_text,
    render_validate_json,
    render_validate_text,
)
from kb.core.validate import ValidateFailure, ValidateRequest, validate

VALIDATE_DESCRIPTION = """Check the knowledge base's mechanical integrity.

The single authoritative integrity checker and CI gate: verifies every rule checkable without judgment — universal type and type/location agreement, per-class frontmatter schemas, type and tag vocabularies, id format and uniqueness, link resolution, derivation-graph acyclicity, session parentage, and supersedes/status coupling. Reports every finding with a stable code and severity; errors exit 1, warnings exit 0 unless --strict. Reads everything, writes nothing. With REF arguments (or refs piped on stdin), only findings for the named documents are reported. Does not touch Git."""

VALIDATE_EXAMPLES = """Examples:
  kb validate                                  Check the whole KB (the CI gate)
  kb validate --strict                         Warnings fail the run too
  kb validate KB-000042 synthetic/notes.md     Only findings for the named documents
  kb search "retry" --output paths | kb validate    Validate a piped candidate set
  kb validate --json                           Machine-readable findings"""


def validate_command(
    refs: Annotated[
        list[str] | None,
        typer.Argument(
            help="Documents to report findings for (id or KB-relative path). Also read from stdin when piped. [default: the whole KB]"
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat warnings as errors for the exit code."),
    ] = False,
    kb_root: Annotated[
        Path | None,
        typer.Option(
            "--kb",
            help="KB root. [default: discovered upward from the current directory]",
            show_default=False,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit findings as JSON."),
    ] = False,
) -> None:
    try:
        result = validate(
            ValidateRequest(refs=refs or [], strict=strict, kb_root=kb_root)
        )
    except ValidateFailure as error:
        typer.echo(
            render_error_json(error) if json_output else render_error_text(error),
            err=not json_output,
        )
        raise typer.Exit(code=2) from error
    typer.echo(
        render_validate_json(result) if json_output else render_validate_text(result)
    )
    if result.exit_code:
        raise typer.Exit(code=result.exit_code)
