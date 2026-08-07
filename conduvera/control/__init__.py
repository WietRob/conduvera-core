"""
CuraOps-Control — Governance Harness fuer lokale Agenten.

Module:
    registry       — AgentRegistry (JSON-backed, Single Source of Truth)
    eventlog       — Append-only EventLog (JSONL)
    gates          — GateRunner + Builtin Gates + Gate Profiles
    stream_state   — StreamStateStore (7+ States, Transition Guards)
    worktree_sentinel — WorktreeSentinel (read-only/mutating/destructive ops)
    scripts_bridge — ScriptRunner (9 Legacy-Skripte als Wrapper)
    launcher       — AgentLauncher (kontrollierter Agent-Start)
    gateway/       — Pi-native AI Gateway (FastAPI, kein LiteLLM)
"""

from .registry import AgentRegistry, AgentRecord, AgentStatus
from .eventlog import EventLog
from .stream_state import StreamStateStore, StreamState, AgentReply
from .worktree_sentinel import WorktreeSentinel
from .scripts_bridge import ScriptRunner, ScriptConfig
from .launcher import AgentLauncher, LaunchResult

__all__ = [
    "AgentRegistry", "AgentRecord", "AgentStatus",
    "EventLog",
    "StreamStateStore", "StreamState", "AgentReply",
    "WorktreeSentinel",
    "ScriptRunner", "ScriptConfig",
    "AgentLauncher", "LaunchResult",
]
