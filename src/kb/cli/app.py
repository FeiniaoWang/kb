import typer

from kb.cli.init import init_command


app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    pass


app.command(name="init")(init_command)
