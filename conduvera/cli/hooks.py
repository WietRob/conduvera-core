"""
Git Hooks Management for CuraOps CLI

Manages Git hooks integration for:
- Pre-commit: Safety Guard validation
- Post-checkout: Session logging
"""

import os
import stat
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

HOOKS_DIR = Path(__file__).parent / "hooks"


class GitHookManager:
    """Manage Git hooks for CuraOps integration."""
    
    # Available hooks
    AVAILABLE_HOOKS = {
        "pre-commit": {
            "description": "Safety Guard - Validates staged deletions",
            "file": "pre-commit.sh",
        },
        "post-checkout": {
            "description": "Session logging & ASPICE checks",
            "file": "post-checkout.sh",
        },
    }
    
    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize Git Hook Manager.
        
        Args:
            repo_path: Path to git repository (auto-detect if None)
        """
        if repo_path is None:
            repo_path = self._find_git_root()
        
        self.repo_path = Path(repo_path) if repo_path else None
        self.hooks_dir = self.repo_path / ".git" / "hooks" if self.repo_path else None
    
    def _find_git_root(self) -> Optional[Path]:
        """Find git repository root from current directory."""
        current = Path.cwd()
        
        while current != current.parent:
            git_dir = current / ".git"
            if git_dir.exists() and git_dir.is_dir():
                return current
            current = current.parent
        
        return None
    
    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        return self.repo_path is not None and self.hooks_dir.exists()
    
    def list_installed_hooks(self) -> List[str]:
        """List currently installed CuraOps hooks."""
        if not self.is_git_repo():
            return []
        
        installed = []
        for hook_name in self.AVAILABLE_HOOKS.keys():
            hook_path = self.hooks_dir / hook_name
            if hook_path.exists():
                content = hook_path.read_text()
                if "CuraOps" in content or "conduvera" in content.lower():
                    installed.append(hook_name)
        
        return installed
    
    def install_hook(self, hook_name: str, force: bool = False) -> bool:
        """
        Install a Git hook.
        
        Args:
            hook_name: Name of hook (pre-commit, post-checkout)
            force: Overwrite existing hook
            
        Returns:
            True if successful
        """
        if not self.is_git_repo():
            console.print("[red]Error: Not a git repository[/red]")
            return False
        
        if hook_name not in self.AVAILABLE_HOOKS:
            console.print(f"[red]Unknown hook: {hook_name}[/red]")
            console.print(f"Available: {', '.join(self.AVAILABLE_HOOKS.keys())}")
            return False
        
        hook_info = self.AVAILABLE_HOOKS[hook_name]
        source_file = HOOKS_DIR / hook_info["file"]
        target_file = self.hooks_dir / hook_name
        
        if not source_file.exists():
            console.print(f"[red]Hook template not found: {source_file}[/red]")
            return False
        
        # Check if hook already exists
        if target_file.exists() and not force:
            content = target_file.read_text()
            if "CuraOps" in content:
                console.print(f"[yellow]⚠️  {hook_name} already installed[/yellow]")
                return False
            else:
                console.print(f"[yellow]⚠️  {hook_name} exists (not CuraOps)[/yellow]")
                console.print("Use --force to overwrite or manually merge")
                return False
        
        # Install hook
        try:
            import shutil
            shutil.copy2(source_file, target_file)
            
            # Make executable
            target_file.chmod(target_file.stat().st_mode | stat.S_IEXEC)
            
            console.print(f"[green]✅ Installed {hook_name}[/green]")
            console.print(f"   Location: {target_file}")
            console.print(f"   Purpose: {hook_info['description']}")
            
            return True
            
        except Exception as e:
            console.print(f"[red]Error installing {hook_name}: {e}[/red]")
            return False
    
    def uninstall_hook(self, hook_name: str) -> bool:
        """
        Uninstall a Git hook.
        
        Args:
            hook_name: Name of hook to uninstall
            
        Returns:
            True if successful
        """
        if not self.is_git_repo():
            console.print("[red]Error: Not a git repository[/red]")
            return False
        
        target_file = self.hooks_dir / hook_name
        
        if not target_file.exists():
            console.print(f"[yellow]⚠️  {hook_name} not installed[/yellow]")
            return False
        
        # Verify it's a CuraOps hook
        content = target_file.read_text()
        if "CuraOps" not in content:
            console.print(f"[yellow]⚠️  {hook_name} is not a CuraOps hook[/yellow]")
            console.print("Manual removal required")
            return False
        
        try:
            target_file.unlink()
            console.print(f"[green]✅ Uninstalled {hook_name}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Error uninstalling {hook_name}: {e}[/red]")
            return False
    
    def install_all(self, force: bool = False) -> int:
        """
        Install all available hooks.
        
        Args:
            force: Overwrite existing hooks
            
        Returns:
            Number of hooks installed
        """
        installed = 0
        for hook_name in self.AVAILABLE_HOOKS.keys():
            if self.install_hook(hook_name, force=force):
                installed += 1
        return installed
    
    def get_hook_status(self) -> Table:
        """Get status table of all hooks."""
        table = Table(title="Git Hooks Status")
        table.add_column("Hook", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Description", style="dim")
        
        installed = set(self.list_installed_hooks())
        
        for hook_name, info in self.AVAILABLE_HOOKS.items():
            status = "[green]✅ Installed[/green]" if hook_name in installed else "[dim]Not installed[/dim]"
            table.add_row(hook_name, status, info["description"])
        
        return table


# Typer CLI commands
hooks_app = typer.Typer(help="Git hooks management")


@hooks_app.command("install")
def hooks_install(
    hook: Optional[str] = typer.Argument(None, help="Hook name (pre-commit, post-checkout)"),
    all: bool = typer.Option(False, "--all", "-a", help="Install all hooks"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing hooks"),
):
    """Install Git hooks for CuraOps integration."""
    manager = GitHookManager()
    
    if not manager.is_git_repo():
        console.print("[red]Error: Not in a git repository[/red]")
        raise typer.Exit(1)
    
    if all:
        count = manager.install_all(force=force)
        console.print(f"\n[green]✅ Installed {count} hooks[/green]")
    elif hook:
        if manager.install_hook(hook, force=force):
            console.print("\n[green]✅ Hook installed successfully[/green]")
        else:
            raise typer.Exit(1)
    else:
        # Show status
        console.print(manager.get_hook_status())
        console.print("\n[dim]Use --all to install all hooks, or specify a hook name[/dim]")


@hooks_app.command("uninstall")
def hooks_uninstall(
    hook: str = typer.Argument(..., help="Hook name to uninstall"),
):
    """Uninstall a Git hook."""
    manager = GitHookManager()
    
    if not manager.is_git_repo():
        console.print("[red]Error: Not in a git repository[/red]")
        raise typer.Exit(1)
    
    if manager.uninstall_hook(hook):
        console.print("\n[green]✅ Hook uninstalled[/green]")
    else:
        raise typer.Exit(1)


@hooks_app.command("status")
def hooks_status():
    """Show Git hooks status."""
    manager = GitHookManager()
    
    if not manager.is_git_repo():
        console.print("[red]Error: Not in a git repository[/red]")
        raise typer.Exit(1)
    
    console.print(f"[bold]Repository:[/bold] {manager.repo_path}")
    console.print(f"[bold]Hooks directory:[/bold] {manager.hooks_dir}\n")
    console.print(manager.get_hook_status())


@hooks_app.command("test")
def hooks_test(
    hook: str = typer.Argument(..., help="Hook name to test"),
):
    """Test a hook without installing."""
    if hook not in GitHookManager.AVAILABLE_HOOKS:
        console.print(f"[red]Unknown hook: {hook}[/red]")
        raise typer.Exit(1)
    
    hook_info = GitHookManager.AVAILABLE_HOOKS[hook]
    source_file = HOOKS_DIR / hook_info["file"]
    
    if not source_file.exists():
        console.print(f"[red]Hook template not found: {source_file}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[bold]Testing {hook}...[/bold]\n")
    
    # Run the hook with test mode
    import subprocess
    result = subprocess.run(
        ["bash", str(source_file)],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
    )
    
    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(f"[yellow]{result.stderr}[/yellow]")
    
    if result.returncode == 0:
        console.print(f"\n[green]✅ {hook} test passed[/green]")
    else:
        console.print(f"\n[red]❌ {hook} test failed (exit {result.returncode})[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    hooks_app()
