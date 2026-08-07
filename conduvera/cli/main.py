#!/usr/bin/env python3
"""Matrix OS CuraOps CLI baseline.

This PR only introduces the package and command surface needed for later
Compliance Change Control and Accountable Agent Layer review PRs.
"""

import typer
from rich.console import Console

from conduvera.cli.commands.accountable import accountable_app
from conduvera.cli.commands.aspice import aspice_app
from conduvera.cli.commands.cr import cr_app
from conduvera.cli.commands.evidence import evidence_app
from conduvera.cli.commands.harness import harness_app
from conduvera.cli.commands.scaffold import scaffold_app

console = Console()
app = typer.Typer(
    name="matrix-cli",
    help="Matrix OS - CuraOps Skills CLI baseline",
    no_args_is_help=True,
)


app.add_typer(cr_app, name="cr", help="Compliance Change Control — CR lifecycle")
app.add_typer(accountable_app, name="accountable", help="Accountable Agent - AI change accountability")
app.add_typer(aspice_app, name="aspice", help="ASPICE support utilities - traceability checks")
app.add_typer(evidence_app, name="evidence", help="Matrix OS evidence backbone contract utilities")
app.add_typer(harness_app, name="harness", help="Read-only Matrix OS harness operator workflow")
app.add_typer(scaffold_app, name="scaffold", help="Matrix OS UI/MCP/editor scaffolding")


@app.command("version")
def version() -> None:
    """Print the baseline CLI version."""
    console.print("matrix-cli baseline 0.1.0")


@app.command("doctor")
def doctor() -> None:
    """Run a minimal package/import smoke check."""
    import conduvera
    import conduvera.cli.main
    import conduvera.skills

    _ = (conduvera, conduvera.cli.main, conduvera.skills)
    console.print("matrix-cli baseline imports OK")


def main() -> None:
    """Console entry point for the Matrix OS CuraOps CLI baseline."""
    app()


if __name__ == "__main__":
    main()
