from pathlib import Path
from typing import Annotated, Literal

import typer

from kb.cli.render import (
    render_error_json,
    render_error_text,
    render_revise_json,
    render_revise_text,
)
from kb.cli.revise_input import acquire_revise_body
from kb.core.revise import (
    ReviseFailure,
    ReviseRequest,
    ReviseResult,
    execute_revise,
    prepare_revise,
)


REVISE_DESCRIPTION = """Revise a synthetic document in place, preserving its id.

The single mutation path for synthetic documents: append parents (consolidation), add associative links, replace the body, perform explicit status transitions (never superseded — that belongs to kb create --supersedes), and set or clear pending_upstream markers. Advances timestamp on every revision and last_human_touch only with --human. Appends a revised entry to log.md. Does not touch Git."""

REVISE_EXAMPLES = """Examples:

\b
  kb revise KB-000042 --add-parent RAW-000113 --human    Consolidate new evidence, human-confirmed
  kb revise KB-000042 --link references=KB-000012    Declare an associative link
  kb revise KB-000042 --status current --human    Complete a draft
  kb revise KB-000042 --pending KB-000007    Defer propagation of a parent's revision
  kb revise KB-000042 --clear-pending KB-000007 --body-file - --human    Propagate: new body from stdin"""


def _run_revise(request: ReviseRequest, body_file: str | None) -> ReviseResult:
    prepared = prepare_revise(request)
    body_data = acquire_revise_body(body_file)
    return execute_revise(prepared, body_data)


def revise_command(
    ref: Annotated[
        str,
        typer.Argument(
            metavar="REF",
            help="\b\nDocument id or KB-relative path.",
        ),
    ],
    add_parent: Annotated[
        list[str] | None,
        typer.Option(
            "--add-parent",
            help="\b\nAppend a parent to derived_from; repeatable.",
        ),
    ] = None,
    link: Annotated[
        list[str] | None,
        typer.Option(
            "--link",
            metavar="TYPE=REF",
            help="\b\nAppend an associative link target; repeatable.",
        ),
    ] = None,
    body_file: Annotated[
        str | None,
        typer.Option(
            "--body-file",
            help="\b\nFile to replace the body from, or - for stdin. [default: body unchanged]",
            show_default=False,
        ),
    ] = None,
    status: Annotated[
        Literal["draft", "current", "retired"] | None,
        typer.Option(
            "--status",
            help="\b\nExplicit, human-directed status transition (never superseded). [default: unchanged]",
            show_default=False,
        ),
    ] = None,
    pending: Annotated[
        list[str] | None,
        typer.Option(
            "--pending",
            help="\b\nMark a parent's revision as awaiting propagation; repeatable.",
        ),
    ] = None,
    clear_pending: Annotated[
        list[str] | None,
        typer.Option(
            "--clear-pending",
            help="\b\nClear a pending_upstream marker; repeatable.",
        ),
    ] = None,
    human: Annotated[
        bool,
        typer.Option(
            "--human",
            help="\b\nMark the revision human-confirmed (advances last_human_touch).",
        ),
    ] = False,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            help="\b\nActor recorded in the log entry. [default: kb-cli]",
            show_default=False,
        ),
    ] = "kb-cli",
    kb_root: Annotated[
        Path | None,
        typer.Option(
            "--kb",
            help="\b\nKB root. [default: discovered upward from the current directory]",
            show_default=False,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="\b\nEmit results as JSON."),
    ] = False,
) -> None:
    try:
        request = ReviseRequest(
            ref=ref,
            add_parents=add_parent or [],
            links=link or [],
            status=status,
            pending=pending or [],
            clear_pending=clear_pending or [],
            body_change=body_file is not None,
            human=human,
            actor=actor,
            kb_root=kb_root,
        )
        result = _run_revise(request, body_file)
    except ReviseFailure as error:
        typer.echo(
            render_error_json(error) if json_output else render_error_text(error),
            err=not json_output,
        )
        raise typer.Exit(code=error.exit_code) from error
    for warning in result.warnings:
        typer.echo(warning, err=True)
    typer.echo(render_revise_json(result) if json_output else render_revise_text(result))
