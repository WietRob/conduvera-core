"""
Base Adapter — Abstract interface for agent tool adapters.

Every adapter must implement start/stop/status/prepare.
Adapters are called by the harness, never directly by agents.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class AdapterResult:
    """Result from an adapter operation."""
    success: bool
    message: str
    detail: Dict[str, Any] = None

    def __post_init__(self):
        if self.detail is None:
            self.detail = {}


class BaseAdapter(ABC):
    """Abstract base class for agent tool adapters."""

    name: str = "base"

    @abstractmethod
    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: Dict[str, Any],
    ) -> AdapterResult:
        """Start a tool session for an agent.

        Returns AdapterResult with session info in detail.
        """
        ...

    @abstractmethod
    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Stop a running tool session."""
        ...

    @abstractmethod
    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Check if a session is still running."""
        ...

    @abstractmethod
    def prepare_worktree(
        self,
        agent_id: str,
        worktree: str,
        scope_files: list,
        config: Dict[str, Any],
    ) -> AdapterResult:
        """Prepare the worktree for the agent.

        Writes .agent-id, .task-key, scope file, etc.
        """
        ...

    def health_check(self) -> AdapterResult:
        """Check if the adapter's tool is available."""
        return AdapterResult(success=True, message="OK")
