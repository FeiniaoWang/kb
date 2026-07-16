from pathlib import Path
from typing import Annotated

import typer

from kb.cli.render import (
    render_error_json,
    render_error_text,
    render_init_json,
    render_init_text,
)
from kb.core.housekeeping import InitFailure, init_kb

INIT_DESCRIPTION = """Scaffold a new knowledge base, or repair an existing one.

Run this from the folder you want to become the KB root; it scaffolds the current directory by default (pass --root to target a different folder). Creates the standard KB layout (raw/, synthetic/, governance/), the root index.md and log.md, and kb-config.json — the file at the KB root that holds project configuration and marks the root for every other command. Safe to re-run: existing files are never touched; --force restores pristine kb-config.json and index.md files, but documents and log.md are never overwritten. Does not touch Git — putting the KB under version control is up to you."""

INIT_EXAMPLES = """Examples:
  kb init                       Scaffold a KB in the current directory (the KB root)
  kb init --root ~/team-kb      Scaffold a KB at the given path
  kb init --force               Restore pristine kb-config.json and index.md files
  kb init --json                Machine-readable scaffold output"""


def init_command(
    root: Annotated[
        Path | None,
        typer.Option(
            "--root",
            help="\b\nFolder to become the KB root. Resolved to an absolute path and created if it does not exist. [default: current directory]",
            show_default=False,
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="\b\nRestore pristine kb-config.json and index.md files. Documents and log.md are never touched.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit results as JSON."),
    ] = False,
) -> None:
    try:
        result = init_kb(root, force=force)
    except InitFailure as error:
        if json_output:
            typer.echo(render_error_json(error))
        else:
            typer.echo(render_error_text(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(render_init_json(result) if json_output else render_init_text(result))
