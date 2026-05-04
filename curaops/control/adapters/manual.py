"""
Manual Adapter — For human-driven sessions or agents without tool integration.

No session management. Just worktree preparation.
Useful for: human developers, one-off scripts, local testing.
"""

from pathlib import Path
from typing import Dict, Any

from curaops.control.adapters.base import BaseAdapter, AdapterResult


class ManualAdapter(BaseAdapter):
    """Adapter for manual/human-driven sessions."""

    name = "manual"

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: Dict[str, Any],
    ) -> AdapterResult:
        """Manual sessions don't need starting — just acknowledge."""
        return AdapterResult(
            success=True,
            message=f"Manual session registered for {agent_id}",
            detail={"session_ref": "manual"},
        )

    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Manual sessions don't need stopping."""
        return AdapterResult(
            success=True,
            message=f"Manual session ended for {agent_id}",
        )

    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Manual sessions are always 'alive' until explicitly stopped."""
        return AdapterResult(
            success=True,
            message="alive",
            detail={"alive": True, "session_ref": "manual"},
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

        (wt / ".agent-id").write_text(agent_id)
        written.append(".agent-id")

        task = config.get("task", "")
        if task:
            (wt / ".task-key").write_text(task)
            written.append(".task-key")

        if scope_files:
            (wt / ".scope").write_text("\n".join(scope_files))
            written.append(".scope")

        gate_profile = config.get("gate_profile", "default")
        (wt / ".gate-profile").write_text(gate_profile)
        written.append(".gate-profile")

        return AdapterResult(
            success=True,
            message=f"Boot pack written: {len(written)} files",
            detail={"written": written},
        )
