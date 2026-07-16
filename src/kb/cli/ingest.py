from pathlib import Path
from typing import Annotated, Literal

import typer

from kb.cli.render import (
    render_error_json,
    render_error_text,
    render_ingest_json,
    render_ingest_text,
)
from kb.core.ingest import IngestFailure, IngestRequest, ingest
from kb.core.model import RawClass

INGEST_DESCRIPTION = """Ingest material into the knowledge base as immutable raw evidence.

Reads from a file, stdin, or the clipboard and files one normalized Markdown document into raw/sources/, raw/chats/, or raw/feedback/, with the next sequential id and the reduced raw frontmatter. The body is copied verbatim — ingest normalizes and files, it never synthesizes. A non-text file is copied unchanged alongside a generated Markdown stub, which becomes the citable form. Feedback requires --about: the document the feedback concerns. Updates the affected index.md listings and appends an ingested entry to log.md. Does not touch Git."""

INGEST_EXAMPLES = """Examples:
  kb ingest --class source --from file notes.md                 File a document into raw/sources/
  kb ingest --class source --from file report.pdf --dest q3     Non-text original + citable stub into raw/sources/q3/
  kb ingest --class feedback --from stdin --about KB-000007     Pipe feedback about KB-000007
  kb ingest --class chat --from clipboard --title "Planning session"   Clipboard into raw/chats/
  kb ingest --class source --from file page.html --origin https://ex.com/post   Record the web page it came from"""


def ingest_command(
    raw_class: Annotated[
        RawClass,
        typer.Option(
            "--class", help="Raw subclass to file under: source, chat, or feedback."
        ),
    ],
    source_kind: Annotated[
        Literal["file", "stdin", "clipboard"],
        typer.Option(
            "--from",
            help="Where to read the material from: file, stdin, or clipboard.",
        ),
    ],
    source: Annotated[
        str | None,
        typer.Argument(
            help="Path to the source file (required with --from file, forbidden otherwise)."
        ),
    ] = None,
    dest: Annotated[
        str | None,
        typer.Option(
            "--dest",
            help="Subdirectory under the class directory (e.g. api → raw/sources/api/). Created with its index.md if missing.",
        ),
    ] = None,
    about: Annotated[
        str | None,
        typer.Option(
            "--about",
            help="Document the feedback concerns (id or KB-relative path). Required for --class feedback.",
        ),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option(
            "--title",
            help="Document title; also drives the target filename. [default: derived from the source filename or the id]",
            show_default=False,
        ),
    ] = None,
    origin: Annotated[
        str | None,
        typer.Option(
            "--origin",
            help='Provenance recorded in the frontmatter — a path, a URL, or a label. [default: the source path, "stdin", or "clipboard"]',
            show_default=False,
        ),
    ] = None,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            help="Actor recorded in the log entry. [default: kb-cli]",
            show_default=False,
        ),
    ] = "kb-cli",
    kb_root: Annotated[
        Path | None,
        typer.Option(
            "--kb",
            help="KB root. [default: discovered upward from the current directory]",
            show_default=False,
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit results as JSON.")
    ] = False,
) -> None:
    try:
        result = ingest(
            IngestRequest(
                raw_class=raw_class,
                source_kind=source_kind,
                source=source,
                dest=dest,
                about=about,
                title=title,
                origin=origin,
                actor=actor,
                kb_root=kb_root,
            )
        )
    except IngestFailure as error:
        typer.echo(
            render_error_json(error) if json_output else render_error_text(error),
            err=not json_output,
        )
        raise typer.Exit(code=error.exit_code) from error
    typer.echo(render_ingest_json(result) if json_output else render_ingest_text(result))
