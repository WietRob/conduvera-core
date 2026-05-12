#!/usr/bin/env python3
"""Matrix OS CuraOps CLI baseline.

This PR only introduces the package and command surface needed for later
Compliance Change Control and Accountable Agent Layer review PRs.
"""

import typer
from rich.console import Console

from curaops.cli.commands.cr import cr_app

console = Console()
app = typer.Typer(
    name="matrix-cli",
    help="Matrix OS - CuraOps Skills CLI baseline",
    no_args_is_help=True,
)


app.add_typer(cr_app, name="cr", help="Compliance Change Control — CR lifecycle")


@app.command("version")
def version() -> None:
    """Print the baseline CLI version."""
    console.print("matrix-cli baseline 0.1.0")


@app.command("doctor")
def doctor() -> None:
    """Run a minimal package/import smoke check."""
    import curaops
    import curaops.cli.main
    import curaops.skills

    _ = (curaops, curaops.cli.main, curaops.skills)
    console.print("matrix-cli baseline imports OK")


def main() -> None:
    """Console entry point for the Matrix OS CuraOps CLI baseline."""
    app()


if __name__ == "__main__":
    main()
