from pathlib import Path
from typing import Annotated, Literal

import typer

from kb.cli.render import (
    render_create_json,
    render_create_text,
    render_error_json,
    render_error_text,
)
from kb.core.create import CreateFailure, CreateRequest, create

CREATE_DESCRIPTION = """Create a synthetic document in the knowledge base.

The deterministic write path for synthetic/ — the counterpart to kb ingest for raw evidence. Allocates the next sequential id, emits the full synthetic frontmatter, and files one Markdown document under synthetic/. At least one parent is required: every synthetic document derives from prior evidence, named via --derived-from (--supersedes also counts as a parent). --supersedes marks the replaced document superseded in the same atomic write. Updates the affected index.md listings and appends a created entry to log.md. Agents never hand-write synthetic files — id allocation and frontmatter stay CLI-authoritative. Does not touch Git."""

CREATE_EXAMPLES = """Examples:

\b
  kb create --type spec --title "Retry Policy" --description "Retry rules." --derived-from CHAT-000027 --body-file draft.md    Draft from a body file
  kb create --type outcome --title "Q3 Outcomes" --description "Q3 results." --derived-from CHAT-000012 --derived-from RAW-000004 --status current    Accepted at creation
  kb create --type spec --title "Retry Policy" --description "Retry rules." --supersedes KB-000031 --derived-from CHAT-000040 --body-file -    Replace KB-000031, body from stdin
  kb create --type note --title "Cache Sizing" --description "Sizing note." --derived-from RAW-000004 --dest notes    File under synthetic/notes/"""


def create_command(
    type_name: Annotated[
        str,
        typer.Option(
            "--type",
            help="\b\nSynthetic document type (open vocabulary; reserved types rejected).",
        ),
    ],
    title: Annotated[
        str,
        typer.Option(
            "--title",
            help="\b\nDocument title; also drives the target filename.",
        ),
    ],
    description: Annotated[
        str,
        typer.Option(
            "--description",
            help="\b\nOne-to-two-sentence summary, shown in index.md listings.",
        ),
    ],
    derived_from: Annotated[
        list[str] | None,
        typer.Option(
            "--derived-from",
            help="\b\nParent document (id or KB-relative path); repeatable. At least one parent is required.",
        ),
    ] = None,
    supersedes: Annotated[
        str | None,
        typer.Option(
            "--supersedes",
            help="\b\nDocument this one replaces; marked superseded in the same write and counted as a parent.",
        ),
    ] = None,
    status: Annotated[
        Literal["draft", "current"],
        typer.Option(
            "--status",
            help="\b\nLifecycle status at birth: draft or current. [default: draft]",
            show_default=False,
        ),
    ] = "draft",
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            help="\b\nTag for the tags frontmatter list; repeatable (a tag missing from the vocabulary warns).",
        ),
    ] = None,
    instructions: Annotated[
        str | None,
        typer.Option(
            "--instructions",
            help="\b\nStanding guidance for the document's consumers, stored in the instructions field.",
        ),
    ] = None,
    body_file: Annotated[
        str | None,
        typer.Option(
            "--body-file",
            help="\b\nFile to read the body from, or - for stdin. [default: empty body]",
            show_default=False,
        ),
    ] = None,
    dest: Annotated[
        str | None,
        typer.Option(
            "--dest",
            help="\b\nSubdirectory under synthetic/ (e.g. specs → synthetic/specs/). Created with its index.md if missing.",
        ),
    ] = None,
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
        result = create(
            CreateRequest(
                type_name=type_name,
                title=title,
                description=description,
                derived_from=derived_from or [],
                supersedes=supersedes,
                status=status,
                tags=tags or [],
                instructions=instructions,
                body_file=body_file,
                dest=dest,
                actor=actor,
                kb_root=kb_root,
            )
        )
    except CreateFailure as error:
        typer.echo(
            render_error_json(error) if json_output else render_error_text(error),
            err=not json_output,
        )
        raise typer.Exit(code=error.exit_code) from error
    for warning in result.warnings:
        typer.echo(warning, err=True)
    typer.echo(render_create_json(result) if json_output else render_create_text(result))
