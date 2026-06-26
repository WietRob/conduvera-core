"""
OpenCode Adapter — Manages OpenCode coding agent sessions.

OpenCode is a terminal-based coding agent. This adapter:
- Starts OpenCode in a tmux session within the agent's worktree
- Prepares worktree with boot pack files
- Injects skills and AGENTS.md
- Checks session liveness via tmux

OpenCode manages its own credentials/providers.
The harness only stores a reference to the tool.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any

from curaops.control.adapters.base import BaseAdapter, AdapterResult


class OpenCodeAdapter(BaseAdapter):
    """Adapter for OpenCode terminal coding agent."""

    name = "opencode"

    def __init__(self, tmux_prefix: str = "curaops"):
        self._tmux_prefix = tmux_prefix

    def _session_name(self, agent_id: str) -> str:
        return f"{self._tmux_prefix}-{agent_id}"

    def health_check(self) -> AdapterResult:
        """Check if tmux and opencode are available."""
        try:
            subprocess.run(
                ["tmux", "-V"],
                capture_output=True, text=True, timeout=5,
            )
        except FileNotFoundError:
            return AdapterResult(
                success=False,
                message="tmux not installed",
            )
        # Check opencode (might not be in PATH, that's OK)
        opencode_check = subprocess.run(
            ["which", "opencode"],
            capture_output=True, text=True, timeout=5,
        )
        if opencode_check.returncode != 0:
            return AdapterResult(
                success=False,
                message="opencode not found in PATH",
            )
        return AdapterResult(success=True, message="tmux + opencode available")

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: Dict[str, Any],
    ) -> AdapterResult:
        """Start OpenCode in a tmux session."""
        session_name = self._session_name(agent_id)
        wt = Path(worktree)
        if not wt.exists():
            return AdapterResult(
                success=False,
                message=f"Worktree does not exist: {worktree}",
            )

        # Check if tmux session already exists
        check = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode == 0:
            return AdapterResult(
                success=True,
                message=f"Session already exists: {session_name}",
                detail={"session_ref": f"tmux:{session_name}"},
            )

        # Start new tmux session with opencode
        try:
            result = subprocess.run(
                [
                    "tmux", "new-session",
                    "-d",
                    "-s", session_name,
                    "-c", str(wt),
                    "opencode",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return AdapterResult(
                    success=False,
                    message=f"Failed to start tmux session: {result.stderr.strip()}",
                )
            return AdapterResult(
                success=True,
                message=f"Started OpenCode session: {session_name}",
                detail={"session_ref": f"tmux:{session_name}"},
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                message=f"Error starting session: {e}",
            )

    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Kill the tmux session."""
        session_name = self._session_name(agent_id)
        try:
            result = subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return AdapterResult(
                    success=True,
                    message=f"Killed session: {session_name}",
                )
            return AdapterResult(
                success=False,
                message=f"Session not found: {session_name}",
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                message=str(e),
            )

    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Check if tmux session is alive."""
        session_name = self._session_name(agent_id)
        check = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True, text=True, timeout=5,
        )
        alive = check.returncode == 0
        return AdapterResult(
            success=True,
            message="alive" if alive else "dead",
            detail={"alive": alive, "session_ref": f"tmux:{session_name}"},
        )

    def prepare_worktree(
        self,
        agent_id: str,
        worktree: str,
        scope_files: list,
        config: Dict[str, Any],
    ) -> AdapterResult:
        """Write boot pack files into the worktree."""
        wt = Path(worktree)
        if not wt.exists():
            return AdapterResult(
                success=False,
                message=f"Worktree does not exist: {worktree}",
            )

        written = []
        errors = []

        # .agent-id
        (wt / ".agent-id").write_text(agent_id)
        written.append(".agent-id")

        # .task-key
        task = config.get("task", "")
        if task:
            (wt / ".task-key").write_text(task)
            written.append(".task-key")

        # .scope (allowed paths)
        if scope_files:
            (wt / ".scope").write_text("\n".join(scope_files))
            written.append(".scope")

        # .gate-profile
        gate_profile = config.get("gate_profile", "default")
        (wt / ".gate-profile").write_text(gate_profile)
        written.append(".gate-profile")

        # .ready-command (how to declare ready)
        (wt / ".ready-command").write_text("curaops-control agent ready " + agent_id)
        written.append(".ready-command")

        # .blocked-command
        (wt / ".blocked-command").write_text("curaops-control agent blocked " + agent_id + " --reason <REASON>")
        written.append(".blocked-command")

        return AdapterResult(
            success=True,
            message=f"Boot pack written: {len(written)} files",
            detail={"written": written, "errors": errors},
        )
