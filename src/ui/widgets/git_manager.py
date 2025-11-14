"""Git Integration widget with visual diff and status."""
from textual.widgets import Static, DataTable, Tree
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.syntax import Syntax
from typing import List, Dict, Any, Optional, Tuple
import subprocess
import re
from datetime import datetime
from pathlib import Path
from src.utils.logger import logger


class GitManager(VerticalScroll):
    """
    Git Integration widget.

    Provides visual git status, diff viewer, commit dialog, branch management.
    """

    repo_path = reactive(None)
    current_branch = reactive("main")
    has_changes = reactive(False)
    ahead_behind = reactive((0, 0))  # (ahead, behind)

    DEFAULT_CSS = """
    GitManager {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    GitManager:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .git-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .git-status {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin: 1 0;
    }

    .git-diff {
        background: rgba(0, 20, 0, 0.7);
        border: round #00FF00;
        padding: 1;
        margin: 1 0;
        height: auto;
    }

    .git-branch {
        color: #00FFFF;
        text-style: bold;
    }

    .git-modified {
        color: #FFAA00;
    }

    .git-added {
        color: #00FF00;
    }

    .git-deleted {
        color: #FF0000;
    }

    .git-untracked {
        color: #AAAAAA;
    }

    .git-success {
        color: #00FF00;
        text-style: bold;
    }

    .git-error {
        color: #FF0000;
        text-style: bold;
    }
    """

    class CommitCreated(Message):
        """Message sent when commit is created."""

        def __init__(self, commit_hash: str, message: str) -> None:
            super().__init__()
            self.commit_hash = commit_hash
            self.message = message

    class BranchChanged(Message):
        """Message sent when branch is changed."""

        def __init__(self, branch: str) -> None:
            super().__init__()
            self.branch = branch

    def __init__(self, repo_path: Optional[Path] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repo_path = repo_path or Path.cwd()
        self.staged_files = []
        self.modified_files = []
        self.untracked_files = []
        self.deleted_files = []

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║      🔧 Git Matrix - Visual Git GUI       ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="git-header"
        )
        yield Static(
            "[dim green]Visual git interface with diff viewer[/]\n\n"
            "[cyan]Commands:[/]\n"
            "[green]  • C[/] - Commit changes\n"
            "[green]  • P[/] - Push to remote\n"
            "[green]  • D[/] - View diff\n"
            "[green]  • B[/] - Switch branch\n"
            "[green]  • L[/] - View log\n"
            "[green]  • S[/] - Stage file\n"
            "[green]  • U[/] - Unstage file\n",
            id="git-help"
        )

    def on_mount(self) -> None:
        """Initialize git status on mount."""
        if self.check_git_repo():
            self.refresh_status()
            logger.info(f"Git Manager initialized for: {self.repo_path}")
        else:
            self.show_error("Not a git repository")

    def check_git_repo(self) -> bool:
        """
        Check if current directory is a git repository.

        Returns:
            True if git repo exists
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Git check failed: {e}")
            return False

    def get_current_branch(self) -> str:
        """
        Get current git branch name.

        Returns:
            Branch name or 'detached'
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return branch if branch else "detached"
            return "unknown"
        except Exception as e:
            logger.error(f"Error getting branch: {e}")
            return "error"

    def get_ahead_behind(self) -> Tuple[int, int]:
        """
        Get commits ahead/behind remote.

        Returns:
            Tuple of (ahead, behind) counts
        """
        try:
            result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))
            return (0, 0)
        except Exception:
            return (0, 0)

    def get_status(self) -> Dict[str, List[str]]:
        """
        Get git status (modified, staged, untracked, deleted files).

        Returns:
            Dictionary with file lists by status
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error(f"Git status failed: {result.stderr}")
                return {"modified": [], "staged": [], "untracked": [], "deleted": []}

            modified = []
            staged = []
            untracked = []
            deleted = []

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                status = line[:2]
                filename = line[3:]

                # Parse git status codes
                if status == "??":
                    untracked.append(filename)
                elif status[0] == "D" or status[1] == "D":
                    deleted.append(filename)
                elif status[0] in ["M", "A", "R"]:
                    staged.append(filename)
                elif status[1] == "M":
                    modified.append(filename)
                elif status[0] == " " and status[1] == "M":
                    modified.append(filename)

            return {
                "modified": modified,
                "staged": staged,
                "untracked": untracked,
                "deleted": deleted
            }

        except Exception as e:
            logger.error(f"Error getting git status: {e}")
            return {"modified": [], "staged": [], "untracked": [], "deleted": []}

    def refresh_status(self) -> None:
        """Refresh git status display."""
        if not self.check_git_repo():
            self.show_error("Not a git repository")
            return

        # Get status data
        self.current_branch = self.get_current_branch()
        self.ahead_behind = self.get_ahead_behind()
        status = self.get_status()

        self.staged_files = status["staged"]
        self.modified_files = status["modified"]
        self.untracked_files = status["untracked"]
        self.deleted_files = status["deleted"]

        self.has_changes = any([
            self.staged_files,
            self.modified_files,
            self.untracked_files,
            self.deleted_files
        ])

        # Clear previous status displays
        for widget in self.query(".git-status"):
            widget.remove()

        # Display status
        self.display_status()

    def display_status(self) -> None:
        """Display current git status."""
        ahead, behind = self.ahead_behind

        # Branch info
        branch_indicator = "●" if self.has_changes else "○"
        ahead_behind_text = ""
        if ahead > 0 or behind > 0:
            ahead_behind_text = f"  {ahead}↑ {behind}↓"

        status_text = (
            f"[bold cyan]Branch:[/] [bold bright_green]{self.current_branch}[/] "
            f"[yellow]{branch_indicator}[/]{ahead_behind_text}\n\n"
        )

        # Staged files
        if self.staged_files:
            status_text += f"[bold green]📦 Staged Files ({len(self.staged_files)}):[/]\n"
            for f in self.staged_files[:10]:  # Limit display
                status_text += f"  [green]A  {f}[/]\n"
            if len(self.staged_files) > 10:
                status_text += f"  [dim]... {len(self.staged_files) - 10} more[/]\n"
            status_text += "\n"

        # Modified files
        if self.modified_files:
            status_text += f"[bold yellow]📝 Modified Files ({len(self.modified_files)}):[/]\n"
            for f in self.modified_files[:10]:
                # Get diff stats
                stats = self.get_file_diff_stats(f)
                status_text += f"  [yellow]M  {f}[/]  [green]+{stats[0]}[/] [red]-{stats[1]}[/]\n"
            if len(self.modified_files) > 10:
                status_text += f"  [dim]... {len(self.modified_files) - 10} more[/]\n"
            status_text += "\n"

        # Deleted files
        if self.deleted_files:
            status_text += f"[bold red]🗑️  Deleted Files ({len(self.deleted_files)}):[/]\n"
            for f in self.deleted_files[:10]:
                status_text += f"  [red]D  {f}[/]\n"
            if len(self.deleted_files) > 10:
                status_text += f"  [dim]... {len(self.deleted_files) - 10} more[/]\n"
            status_text += "\n"

        # Untracked files
        if self.untracked_files:
            status_text += f"[dim]❓ Untracked Files ({len(self.untracked_files)}):[/]\n"
            for f in self.untracked_files[:10]:
                status_text += f"  [dim]?  {f}[/]\n"
            if len(self.untracked_files) > 10:
                status_text += f"  [dim]... {len(self.untracked_files) - 10} more[/]\n"
            status_text += "\n"

        # Clean status
        if not self.has_changes:
            status_text += "[bold green]✅ Working tree clean[/]\n"

        self.mount(
            Static(
                status_text,
                classes="git-status"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def get_file_diff_stats(self, filename: str) -> Tuple[int, int]:
        """
        Get diff statistics for a file.

        Args:
            filename: File to get stats for

        Returns:
            Tuple of (additions, deletions)
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--numstat", filename],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout:
                parts = result.stdout.split()
                if len(parts) >= 2:
                    return (int(parts[0]), int(parts[1]))
            return (0, 0)
        except Exception:
            return (0, 0)

    def get_file_diff(self, filename: str, cached: bool = False) -> str:
        """
        Get diff for a specific file.

        Args:
            filename: File to get diff for
            cached: Get staged diff instead of working tree

        Returns:
            Diff text
        """
        try:
            cmd = ["git", "diff"]
            if cached:
                cmd.append("--cached")
            cmd.append(filename)

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            return result.stdout if result.returncode == 0 else ""

        except Exception as e:
            logger.error(f"Error getting diff for {filename}: {e}")
            return ""

    def show_diff(self, filename: str) -> None:
        """
        Display diff for a file.

        Args:
            filename: File to show diff for
        """
        diff_text = self.get_file_diff(filename)

        if not diff_text:
            self.show_error(f"No diff available for {filename}")
            return

        # Parse and format diff
        formatted_diff = self.format_diff(diff_text)

        self.mount(
            Static(
                f"[bold cyan]╭─ Diff: {filename} ──────────────────────╮[/]\n"
                f"{formatted_diff}\n"
                f"[bold cyan]╰────────────────────────────────────────────╯[/]",
                classes="git-diff"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def format_diff(self, diff_text: str) -> str:
        """
        Format diff text with colors.

        Args:
            diff_text: Raw diff text

        Returns:
            Formatted diff with Rich markup
        """
        lines = diff_text.split("\n")
        formatted_lines = []

        for line in lines:
            if line.startswith("+++") or line.startswith("---"):
                formatted_lines.append(f"[bold cyan]{line}[/]")
            elif line.startswith("+"):
                formatted_lines.append(f"[green]{line}[/]")
            elif line.startswith("-"):
                formatted_lines.append(f"[red]{line}[/]")
            elif line.startswith("@@"):
                formatted_lines.append(f"[bold magenta]{line}[/]")
            else:
                formatted_lines.append(f"[dim]{line}[/]")

        return "\n".join(formatted_lines[:100])  # Limit lines

    def stage_file(self, filename: str) -> bool:
        """
        Stage a file for commit.

        Args:
            filename: File to stage

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                ["git", "add", filename],
                cwd=self.repo_path,
                capture_output=True,
                timeout=5
            )

            success = result.returncode == 0
            if success:
                logger.info(f"Staged file: {filename}")
                self.show_success(f"Staged: {filename}")
                self.refresh_status()
            else:
                self.show_error(f"Failed to stage: {result.stderr.decode()}")

            return success

        except Exception as e:
            self.show_error(f"Error staging file: {e}")
            logger.error(f"Error staging {filename}: {e}")
            return False

    def unstage_file(self, filename: str) -> bool:
        """
        Unstage a file.

        Args:
            filename: File to unstage

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                ["git", "restore", "--staged", filename],
                cwd=self.repo_path,
                capture_output=True,
                timeout=5
            )

            success = result.returncode == 0
            if success:
                logger.info(f"Unstaged file: {filename}")
                self.show_success(f"Unstaged: {filename}")
                self.refresh_status()
            else:
                self.show_error(f"Failed to unstage: {result.stderr.decode()}")

            return success

        except Exception as e:
            self.show_error(f"Error unstaging file: {e}")
            logger.error(f"Error unstaging {filename}: {e}")
            return False

    def commit(self, message: str, files: Optional[List[str]] = None) -> bool:
        """
        Create a git commit.

        Args:
            message: Commit message
            files: Optional list of files to commit (stages all if None)

        Returns:
            True if successful
        """
        try:
            # Stage files if provided
            if files:
                for f in files:
                    self.stage_file(f)

            # Create commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Extract commit hash
                commit_hash = ""
                for line in result.stdout.split("\n"):
                    if line.strip().startswith("["):
                        # Extract hash from "[branch hash] message" format
                        match = re.search(r'\[.+?\s+([a-f0-9]+)\]', line)
                        if match:
                            commit_hash = match.group(1)
                        break

                logger.info(f"Created commit: {commit_hash}")
                self.show_success(f"✅ Commit created: {commit_hash[:7]}")
                self.post_message(self.CommitCreated(commit_hash, message))
                self.refresh_status()
                return True
            else:
                error = result.stderr or "Unknown error"
                self.show_error(f"Commit failed: {error}")
                return False

        except Exception as e:
            self.show_error(f"Error creating commit: {e}")
            logger.error(f"Error creating commit: {e}")
            return False

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        """
        Push commits to remote.

        Args:
            remote: Remote name
            branch: Branch to push (uses current if None)

        Returns:
            True if successful
        """
        try:
            branch = branch or self.current_branch
            self.show_success(f"🚀 Pushing to {remote}/{branch}...")

            result = subprocess.run(
                ["git", "push", remote, branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Pushed to {remote}/{branch}")
                self.show_success(f"✅ Pushed to {remote}/{branch}")
                self.refresh_status()
                return True
            else:
                error = result.stderr or "Unknown error"
                self.show_error(f"Push failed: {error}")
                return False

        except Exception as e:
            self.show_error(f"Error pushing: {e}")
            logger.error(f"Error pushing: {e}")
            return False

    def get_log(self, count: int = 10) -> List[Dict[str, str]]:
        """
        Get git commit log.

        Args:
            count: Number of commits to fetch

        Returns:
            List of commit dictionaries
        """
        try:
            result = subprocess.run(
                ["git", "log", f"-{count}", "--pretty=format:%H|%an|%ar|%s"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        commits.append({
                            "hash": parts[0][:7],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3]
                        })

            return commits

        except Exception as e:
            logger.error(f"Error getting log: {e}")
            return []

    def show_log(self, count: int = 10) -> None:
        """
        Display git log.

        Args:
            count: Number of commits to show
        """
        commits = self.get_log(count)

        if not commits:
            self.show_error("No commits found")
            return

        log_text = "[bold cyan]📊 Git Log:[/]\n\n"

        for i, commit in enumerate(commits):
            connector = "●" if i == 0 else "○"
            log_text += (
                f"[yellow]{connector}[/] [bold green]{commit['hash']}[/] "
                f"[dim]{commit['date']}[/]\n"
                f"  [cyan]{commit['author']}[/]: {commit['message']}\n"
            )
            if i < len(commits) - 1:
                log_text += "  [dim]│[/]\n"

        self.mount(
            Static(
                log_text,
                classes="git-status"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def show_success(self, message: str) -> None:
        """Show success message."""
        self.mount(
            Static(
                f"[bold green]✅ {message}[/]",
                classes="git-success"
            )
        )

    def show_error(self, error: str) -> None:
        """Show error message."""
        self.mount(
            Static(
                f"[bold red]❌ Error[/]\n[red]{error}[/]",
                classes="git-error"
            )
        )

    def get_branches(self) -> List[str]:
        """
        Get list of local branches.

        Returns:
            List of branch names
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                return result.stdout.strip().split("\n")
            return []

        except Exception as e:
            logger.error(f"Error getting branches: {e}")
            return []

    def checkout_branch(self, branch: str) -> bool:
        """
        Switch to a branch.

        Args:
            branch: Branch name to switch to

        Returns:
            True if successful
        """
        try:
            result = subprocess.run(
                ["git", "checkout", branch],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(f"Switched to branch: {branch}")
                self.current_branch = branch
                self.show_success(f"Switched to branch: {branch}")
                self.post_message(self.BranchChanged(branch))
                self.refresh_status()
                return True
            else:
                error = result.stderr or "Unknown error"
                self.show_error(f"Checkout failed: {error}")
                return False

        except Exception as e:
            self.show_error(f"Error checking out branch: {e}")
            logger.error(f"Error checking out {branch}: {e}")
            return False
