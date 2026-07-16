from pathlib import Path
from typing import Annotated

import typer

from kb.cli.render import render_error_text, render_init_text
from kb.core.housekeeping import InitFailure, init_kb


def init_command(
    root: Annotated[Path | None, typer.Option("--root")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    try:
        result = init_kb(root if root is not None else Path.cwd(), force=force)
    except InitFailure as error:
        typer.echo(render_error_text(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(render_init_text(result))
