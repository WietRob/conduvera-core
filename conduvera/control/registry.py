"""
Agent Registry — Single Source of Truth for CuraOps-Control.

JSON-backed registry of all active agent sessions.
Every agent that works in this project MUST be registered here.
No agent without boot pack. No READY without registry entry.

Storage: .conduvera/control/registry.json
"""

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any


class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    BOOTING = "booting"        # Being set up
    ACTIVE = "active"          # Working on task
    READY = "ready"            # Claims to be ready (pending gate check)
    BLOCKED = "blocked"        # Blocked by gate failure or manual block
    STOPPED = "stopped"        # Gracefully stopped
    CRASHED = "crashed"        # Unexpected termination


@dataclass
class AgentRecord:
    """A single agent entry in the registry."""
    agent_id: str                        # e.g. "Batman"
    tool: str                            # e.g. "opencode", "manual", "droid", "zed"
    task: str                            # e.g. "TASK-I198"
    issue: Optional[int] = None          # GitHub issue number
    worktree: str = ""                   # e.g. ".ai/worktrees/Batman-..."
    session: str = ""                    # e.g. "tmux:conduvera-Batman"
    gate_profile: str = "default"        # Gate profile name
    status: AgentStatus = AgentStatus.BOOTING
    scope_files: List[str] = field(default_factory=list)  # Allowed paths
    credentials_ref: Dict[str, str] = field(default_factory=dict)
    blocked_reason: str = ""
    ready_evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            now = datetime.now(timezone.utc).isoformat()
            self.created_at = now
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRecord":
        if "status" in data and isinstance(data["status"], str):
            data["status"] = AgentStatus(data["status"])
        return cls(**data)


class AgentRegistry:
    """
    JSON-backed agent registry.

    Thread-safe. File locking for concurrent access.
    """

    def __init__(self, control_dir: Optional[Path] = None):
        if control_dir is None:
            control_dir = Path.cwd() / ".conduvera" / "control"
        self._control_dir = control_dir
        self._registry_path = control_dir / "registry.json"
        self._lock = threading.Lock()

    def _ensure_dir(self):
        self._control_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, dict]:
        if not self._registry_path.exists():
            return {"agents": {}, "version": "0.1.0"}
        with open(self._registry_path, "r") as f:
            return json.load(f)

    def _save(self, data: Dict[str, dict]):
        self._ensure_dir()
        with open(self._registry_path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)

    # ── CRUD ──────────────────────────────────────────────────────

    def register(self, record: AgentRecord) -> AgentRecord:
        """Register a new agent. Raises if agent_id already exists."""
        with self._lock:
            data = self._load()
            agents = data.setdefault("agents", {})
            if record.agent_id in agents:
                raise ValueError(f"Agent '{record.agent_id}' already registered")
            record.updated_at = datetime.now(timezone.utc).isoformat()
            agents[record.agent_id] = record.to_dict()
            self._save(data)
            return record

    def get(self, agent_id: str) -> Optional[AgentRecord]:
        """Get a single agent by ID."""
        data = self._load()
        entry = data.get("agents", {}).get(agent_id)
        if entry is None:
            return None
        return AgentRecord.from_dict(entry)

    def update(self, agent_id: str, **kwargs) -> AgentRecord:
        """Update specific fields of an agent."""
        with self._lock:
            data = self._load()
            agents = data.get("agents", {})
            if agent_id not in agents:
                raise KeyError(f"Agent '{agent_id}' not found")
            entry = agents[agent_id]
            for key, value in kwargs.items():
                if key == "status" and isinstance(value, AgentStatus):
                    value = value.value
                entry[key] = value
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            agents[agent_id] = entry
            self._save(data)
            return AgentRecord.from_dict(entry)

    def remove(self, agent_id: str) -> bool:
        """Remove an agent from the registry."""
        with self._lock:
            data = self._load()
            agents = data.get("agents", {})
            if agent_id not in agents:
                return False
            del agents[agent_id]
            self._save(data)
            return True

    # ── Queries ───────────────────────────────────────────────────

    def list_all(self) -> List[AgentRecord]:
        """List all registered agents."""
        data = self._load()
        return [AgentRecord.from_dict(v) for v in data.get("agents", {}).values()]

    def list_by_status(self, status: AgentStatus) -> List[AgentRecord]:
        """List agents filtered by status."""
        return [a for a in self.list_all() if a.status == status]

    def list_active(self) -> List[AgentRecord]:
        """List all active (non-stopped, non-crashed) agents."""
        terminal = {AgentStatus.STOPPED, AgentStatus.CRASHED}
        return [a for a in self.list_all() if a.status not in terminal]

    def find_by_task(self, task: str) -> List[AgentRecord]:
        """Find agents working on a specific task."""
        return [a for a in self.list_all() if a.task == task]

    def find_by_worktree(self, worktree: str) -> Optional[AgentRecord]:
        """Find the agent using a specific worktree."""
        for a in self.list_all():
            if a.worktree == worktree:
                return a
        return None

    # ── Status Transitions ────────────────────────────────────────

    def set_active(self, agent_id: str) -> AgentRecord:
        """Transition agent to active (working)."""
        return self.update(agent_id, status=AgentStatus.ACTIVE)

    def set_ready(self, agent_id: str, evidence: Optional[Dict] = None) -> AgentRecord:
        """Transition agent to ready (pending gate check)."""
        updates = {"status": AgentStatus.READY}
        if evidence:
            updates["ready_evidence"] = evidence
        return self.update(agent_id, **updates)

    def set_blocked(self, agent_id: str, reason: str) -> AgentRecord:
        """Block an agent with a reason."""
        return self.update(
            agent_id,
            status=AgentStatus.BLOCKED,
            blocked_reason=reason,
        )

    def set_stopped(self, agent_id: str) -> AgentRecord:
        """Gracefully stop an agent."""
        return self.update(agent_id, status=AgentStatus.STOPPED)

    def set_crashed(self, agent_id: str, reason: str = "") -> AgentRecord:
        """Mark an agent as crashed."""
        return self.update(
            agent_id,
            status=AgentStatus.CRASHED,
            blocked_reason=reason,
        )

    # ── Import/Export ─────────────────────────────────────────────

    def export_dict(self) -> dict:
        """Export full registry as dict."""
        return self._load()

    def to_json(self) -> str:
        """Export full registry as JSON string."""
        return json.dumps(self._load(), indent=2)
