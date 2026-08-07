"""Multi-Agent Lock - Coordinate file access between multiple AI agents."""

from .multi_agent_lock import (
    Conflict,
    ConflictType,
    Lock,
    LockScope,
    MultiAgentLock,
    MultiAgentLockError,
)

__all__ = [
    "Conflict",
    "ConflictType",
    "Lock",
    "LockScope",
    "MultiAgentLock",
    "MultiAgentLockError",
]

__version__ = "1.0.0"
