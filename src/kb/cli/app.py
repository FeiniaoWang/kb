import typer

from kb.cli.ingest import INGEST_DESCRIPTION, INGEST_EXAMPLES, ingest_command
from kb.cli.init import INIT_DESCRIPTION, INIT_EXAMPLES, init_command


app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)


@app.callback()
def main() -> None:
    pass


app.command(
    name="init",
    help=INIT_DESCRIPTION.replace("\n\n", "\n\n\b\n", 1),
    epilog=INIT_EXAMPLES,
)(init_command)

app.command(
    name="ingest",
    help=INGEST_DESCRIPTION.replace("\n\n", "\n\n\b\n", 1),
    epilog=INGEST_EXAMPLES,
)(ingest_command)
