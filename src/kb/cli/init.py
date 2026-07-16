from pathlib import Path
from typing import Annotated

import typer

from kb.cli.render import render_init_text
from kb.core.housekeeping import init_kb


def init_command(
    root: Annotated[Path | None, typer.Option("--root")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    result = init_kb(root if root is not None else Path.cwd(), force=force)
    typer.echo(render_init_text(result))
