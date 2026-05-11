"""
Shell Completion Support for CuraOps CLI

Auto-generates bash/zsh completion scripts using Typer's built-in support.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

# Shell configuration paths
SHELL_CONFIGS = {
    "bash": {
        "config_file": "~/.bashrc",
        "completion_dir": "~/.bash_completion.d",
    },
    "zsh": {
        "config_file": "~/.zshrc",
        "completion_dir": "~/.zsh/completions",
    },
    "fish": {
        "config_file": "~/.config/fish/config.fish",
        "completion_dir": "~/.config/fish/completions",
    },
}


def detect_shell() -> str:
    """Detect current shell from environment."""
    shell = os.environ.get("SHELL", "/bin/bash")
    return Path(shell).name


def generate_completion_script(shell: str, prog_name: str = "matrix") -> str:
    """
    Generate completion script using Typer's click integration.
    
    Args:
        shell: Shell type (bash, zsh, fish)
        prog_name: Program name for completion
        
    Returns:
        Completion script content
    """
    import sys
    
    # Get the main module path
    matrix_cli_path = Path(__file__).parent / "main.py"
    
    if shell == "bash":
        env_var = f"_{prog_name.upper()}_COMPLETE"
        script = f'''# Matrix CLI Bash Completion
_{prog_name}_complete()
{{
    local IFS=$'\\n'
    local response
    
    response=$(env COMP_WORDS="${{COMP_WORDS[*]}}" COMP_CWORD="$COMP_CWORD" {env_var}=bash_complete $1)
    
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        
        if [[ $type == 'dir' ]]; then
            COMPREPLY+=("$value/")
        elif [[ $type == 'file' ]]; then
            COMPREPLY+=("$value ")
        else
            COMPREPLY+=("$value ")
        fi
    done
    
    return 0
}}

complete -F _{prog_name}_complete {prog_name}
'''
    elif shell == "zsh":
        env_var = f"_{prog_name.upper()}_COMPLETE"
        script = f'''#compdef {prog_name}

# Matrix CLI Zsh Completion
_{prog_name}_complete()
{{
    local IFS=$'\\n'
    local response
    
    response=$(env COMP_WORDS="${{words[*]}}" COMP_CWORD=$((CURRENT-1)) {env_var}=zsh_complete {prog_name})
    
    for completion in $response; do
        IFS=',' read type value <<< "$completion"
        
        if [[ $type == 'dir' ]]; then
            _path_files -/
        elif [[ $type == 'file' ]]; then
            _path_files -f
        else
            compadd -- "$value"
        fi
    done
}}

compdef _{prog_name}_complete {prog_name}
'''
    elif shell == "fish":
        script = f'''# Matrix CLI Fish Completion
complete -c {prog_name} -a "(env _{prog_name.upper()}_COMPLETE=fish_complete {prog_name})"
'''
    else:
        raise ValueError(f"Unsupported shell: {shell}")
    
    return script


def install_completion(
    shell: Optional[str] = None,
    prog_name: str = "matrix",
    global_install: bool = False,
) -> bool:
    """
    Install shell completion for Matrix CLI.
    
    Args:
        shell: Shell type (auto-detect if None)
        prog_name: Program name
        global_install: Install system-wide (requires sudo)
        
    Returns:
        True if successful
    """
    if shell is None:
        shell = detect_shell()
    
    shell = shell.lower()
    
    if shell not in SHELL_CONFIGS:
        console.print(f"[red]Unsupported shell: {shell}[/red]")
        console.print(f"Supported: {', '.join(SHELL_CONFIGS.keys())}")
        return False
    
    config = SHELL_CONFIGS[shell]
    
    try:
        # Generate completion script
        script = generate_completion_script(shell, prog_name)
        
        if global_install:
            # System-wide installation
            if shell == "bash":
                completion_file = Path(f"/etc/" f"bash_completion.d/{prog_name}")
            elif shell == "zsh":
                completion_file = Path(f"/usr/share/zsh/site-functions/_{prog_name}")
            elif shell == "fish":
                completion_file = Path(f"/usr/share/fish/completions/{prog_name}.fish")
            
            # Note: Would need sudo for this
            console.print(f"[yellow]Global install would write to: {completion_file}[/yellow]")
            console.print("[dim]Run with sudo for global installation[/dim]")
            return False
        else:
            # User-local installation
            completion_dir = Path(config["completion_dir"]).expanduser()
            completion_dir.mkdir(parents=True, exist_ok=True)
            
            if shell == "bash":
                completion_file = completion_dir / f"{prog_name}"
            elif shell == "zsh":
                completion_file = completion_dir / f"_{prog_name}"
            elif shell == "fish":
                completion_file = Path(f"~/.config/fish/completions/{prog_name}.fish").expanduser()
                completion_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write completion file
            completion_file.write_text(script)
            completion_file.chmod(0o644)
            
            # Add source line to shell config if not present
            config_file = Path(config["config_file"]).expanduser()
            source_line = f"\n# Matrix CLI Completion\nsource {completion_file}\n"
            
            if config_file.exists():
                current_content = config_file.read_text()
                if str(completion_file) not in current_content:
                    with open(config_file, "a") as f:
                        f.write(source_line)
                    console.print(f"[green]✅ Added completion source to {config_file}[/green]")
            else:
                console.print(f"[yellow]⚠️  Config file not found: {config_file}[/yellow]")
                console.print(f"[dim]Add this to your shell config:[/dim]")
                console.print(f"[dim]source {completion_file}[/dim]")
            
            console.print(f"[green]✅ Completion installed: {completion_file}[/green]")
            console.print(f"\n[bold]Reload your shell or run:[/bold]")
            console.print(f"[dim]source {config['config_file']}[/dim]")
            
            return True
            
    except Exception as e:
        console.print(f"[red]Error installing completion: {e}[/red]")
        return False


def generate_aliases(prog_name: str = "matrix") -> str:
    """Generate shell aliases for common commands."""
    aliases = f'''# Matrix CLI Aliases
alias matrix="{prog_name}"
alias m="{prog_name}"
alias m-safety="{prog_name} safety"
alias m-cr="{prog_name} cr"
alias m-session="{prog_name} session"
alias m-aspice="{prog_name} aspice"
alias m-lock="{prog_name} lock"
alias m-pattern="{prog_name} pattern"

# Safe delete alias
alias rm-safe="{prog_name} safety validate-delete"

# Quick CR commands
alias m-cr-new="{prog_name} cr create"
alias m-cr-ls="{prog_name} cr list"

# Quick session commands  
alias m-session-start="{prog_name} session start"
alias m-session-status="{prog_name} session status"

# Quick lock commands
alias m-lock-claim="{prog_name} lock claim"
alias m-lock-status="{prog_name} lock status"

# Quick ASPICE commands
alias m-aspice-link="{prog_name} aspice link"
alias m-aspice-check="{prog_name} aspice check"
'''
    return aliases


def install_aliases(
    shell: Optional[str] = None,
    prog_name: str = "matrix",
) -> bool:
    """Install shell aliases."""
    if shell is None:
        shell = detect_shell()
    
    shell = shell.lower()
    
    if shell not in SHELL_CONFIGS:
        console.print(f"[red]Unsupported shell: {shell}[/red]")
        return False
    
    config = SHELL_CONFIGS[shell]
    config_file = Path(config["config_file"]).expanduser()
    
    aliases = generate_aliases(prog_name)
    
    try:
        # Check if aliases already exist
        if config_file.exists():
            current_content = config_file.read_text()
            if "# Matrix CLI Aliases" in current_content:
                console.print(f"[yellow]⚠️  Aliases already installed in {config_file}[/yellow]")
                return False
        
        # Append aliases
        with open(config_file, "a") as f:
            f.write(f"\n{aliases}\n")
        
        console.print(f"[green]✅ Aliases installed: {config_file}[/green]")
        console.print(f"\n[bold]Available aliases:[/bold]")
        console.print("  m, matrix          - Main CLI")
        console.print("  m-safety           - Safety Guard")
        console.print("  m-cr               - Change Request")
        console.print("  m-session          - Session Manager")
        console.print("  m-aspice           - ASPICE Compliance")
        console.print("  m-lock             - Multi-Agent Lock")
        console.print("  m-pattern          - Pattern Learning")
        console.print("  rm-safe            - Safe delete")
        
        return True
        
    except Exception as e:
        console.print(f"[red]Error installing aliases: {e}[/red]")
        return False


# CLI Commands for completion management
completion_app = typer.Typer(help="Shell completion management")


@completion_app.command("install")
def completion_install(
    shell: str = typer.Option(None, "--shell", "-s", help="Shell type (bash/zsh/fish)"),
    prog_name: str = typer.Option("matrix", "--name", "-n", help="Program name"),
    aliases: bool = typer.Option(True, "--aliases/--no-aliases", help="Install aliases too"),
):
    """Install shell completion for Matrix CLI."""
    console.print("[bold]Installing shell completion...[/bold]\n")
    
    # Install completion
    if install_completion(shell, prog_name):
        console.print()
    
    # Install aliases
    if aliases:
        install_aliases(shell, prog_name)


@completion_app.command("show")
def completion_show(
    shell: str = typer.Option(None, "--shell", "-s", help="Shell type"),
    prog_name: str = typer.Option("matrix", "--name", "-n", help="Program name"),
):
    """Show completion script without installing."""
    if shell is None:
        shell = detect_shell()
    
    script = generate_completion_script(shell.lower(), prog_name)
    console.print(f"[bold]{shell} completion script:[/bold]")
    console.print(f"[dim]{'─' * 50}[/dim]")
    console.print(script)


@completion_app.command("aliases")
def completion_aliases(
    prog_name: str = typer.Option("matrix", "--name", "-n", help="Program name"),
    install: bool = typer.Option(False, "--install", "-i", help="Install aliases"),
    shell: str = typer.Option(None, "--shell", "-s", help="Shell type"),
):
    """Show or install shell aliases."""
    if install:
        install_aliases(shell, prog_name)
    else:
        aliases = generate_aliases(prog_name)
        console.print("[bold]Suggested aliases:[/bold]")
        console.print(f"[dim]{'─' * 50}[/dim]")
        console.print(aliases)


if __name__ == "__main__":
    completion_app()
