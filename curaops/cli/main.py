#!/usr/bin/env python3
"""
Matrix OS CLI - CuraOps Skills Integration

Usage:
    matrix-cli safety check /path --operation delete
    matrix-cli cr create --title "Fix bug"
    matrix-cli session start --agent cursor
    matrix-cli aspice check
    matrix-cli lock claim --file src/main.py --agent cursor
    matrix-cli pattern record "action" --context "..."
"""

import typer
from rich.console import Console

# Import skill command groups
from curaops.cli.commands.skills import (
    safety_app,
    cr_app,
    session_app,
    aspice_app,
    lock_app,
    pattern_app,
)
from curaops.cli.completion import completion_app
from curaops.cli.hooks import hooks_app

console = Console()

# Main CLI app
app = typer.Typer(
    name="matrix-cli",
    help="Matrix OS - CuraOps Skills CLI",
    no_args_is_help=True,
)

# Add sub-commands
app.add_typer(safety_app, name="safety", help="Safety Guard - Protect production data")
app.add_typer(cr_app, name="cr", help="Change Request - CR-driven workflow")
app.add_typer(session_app, name="session", help="Session Manager - Session lifecycle")
app.add_typer(aspice_app, name="aspice", help="ASPICE Compliance - Traceability")
app.add_typer(lock_app, name="lock", help="Multi-Agent Lock - File coordination")
app.add_typer(pattern_app, name="pattern", help="Pattern Learning - Behavior learning")
app.add_typer(completion_app, name="completion", help="Shell completion & aliases")
app.add_typer(hooks_app, name="hooks", help="Git hooks integration")


@app.callback()
def main():
    """Matrix OS CLI with CuraOps Skills."""
    pass


def main():
    """Entry point - handles both CLI and MCP server modes."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "mcp-server":
        # Run in MCP server mode for Zed integration
        from curaops.cli.mcp_server import run_mcp_server
        run_mcp_server()
    else:
        # Normal CLI mode
        app()


if __name__ == "__main__":
    main()
