"""
Multi-Agent Lock - Coordinate file access between multiple AI agents.

Purpose:
Prevent multiple agents from modifying the same files simultaneously
by implementing a claim/lock system with conflict detection and
resolution suggestions.

Traceability:
- Implements: SW-REQ-096 (Multi-Agent Coordination)
- Derived from: SYS-REQ-033 (Agent-Governance)
- Validated by: TC-IT-096, TC-UT-096
"""

import fnmatch
import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LockScope(str, Enum):
    """Lock scope types."""

    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    PATTERN = "PATTERN"


class ConflictType(str, Enum):
    """Conflict types."""

    FILE_ALREADY_LOCKED = "FILE_ALREADY_LOCKED"
    DIRECTORY_OVERLAP = "DIRECTORY_OVERLAP"
    PATTERN_MATCH = "PATTERN_MATCH"
    AGENT_SELF_CONFLICT = "AGENT_SELF_CONFLICT"


@dataclass
class Lock:
    """Lock data model."""

    lock_id: str
    agent_id: str
    path: str
    scope: LockScope
    claimed_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict:
        """Convert lock to dictionary."""
        return {
            "lock_id": self.lock_id,
            "agent_id": self.agent_id,
            "path": self.path,
            "scope": self.scope.value,
            "claimed_at": self.claimed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lock":
        """Create lock from dictionary."""
        return cls(
            lock_id=data["lock_id"],
            agent_id=data["agent_id"],
            path=data["path"],
            scope=LockScope(data["scope"]),
            claimed_at=datetime.fromisoformat(data["claimed_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    def is_expired(self) -> bool:
        """Check if lock has expired."""
        return datetime.now() > self.expires_at


@dataclass
class Conflict:
    """Conflict data model."""

    type: ConflictType
    path: str
    requested_by: str
    existing_lock: Lock
    message: str

    def to_dict(self) -> dict:
        """Convert conflict to dictionary."""
        return {
            "type": self.type.value,
            "path": self.path,
            "requested_by": self.requested_by,
            "existing_lock": self.existing_lock.to_dict(),
            "message": self.message,
        }


class MultiAgentLockError(Exception):
    """Base exception for multi-agent lock errors."""

    pass


class MultiAgentLock:
    """
    Coordinate file access between multiple AI agents.

    Implements: SW-REQ-096
    Purpose: Prevent conflicting file modifications

    Features:
    - File/directory/pattern claiming
    - Conflict detection
    - Resolution suggestions
    - Automatic expiration (TTL)
    """

    def __init__(self, storage_dir: Path | str | None = None):
        """
        Initialize multi-agent lock manager.

        Args:
            storage_dir: Directory to store lock files (default: ~/.local/share/multi_agent_lock)
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".local" / "share" / "multi_agent_lock"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"MultiAgentLock initialized: {self.storage_dir}")

    def claim_file(
        self,
        path: Path | str,
        agent_id: str,
        scope: LockScope = LockScope.FILE,
        ttl: int = 3600,
    ) -> Lock:
        """
        Claim a file/directory for an agent.

        Args:
            path: Path to claim
            agent_id: Agent identifier (e.g., "cursor", "claude", "codex")
            scope: Lock scope (FILE, DIRECTORY, PATTERN)
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)

        Returns:
            Lock object

        Raises:
            MultiAgentLockError: If file is already locked by another agent
        """
        path_str = str(path)

        # Clean up expired locks first
        self._cleanup_expired()

        # Check for conflicts
        conflicts = self.check_conflicts([path_str], agent_id)
        if conflicts:
            conflict_msgs = "; ".join([c.message for c in conflicts])
            raise MultiAgentLockError(f"Cannot claim {path_str}: {conflict_msgs}")

        # Create new lock
        lock = Lock(
            lock_id=str(uuid.uuid4())[:8],
            agent_id=agent_id,
            path=path_str,
            scope=scope,
            claimed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=ttl),
        )

        # Save lock
        self._save_lock(lock)

        logger.info(f"Lock created: {lock.lock_id} for {agent_id} on {path_str}")
        return lock

    def check_conflicts(self, paths: list[str], agent_id: str) -> list[Conflict]:
        """
        Check for conflicts before claiming.

        Args:
            paths: List of paths to check
            agent_id: Agent requesting the paths

        Returns:
            List of conflicts (empty if no conflicts)
        """
        conflicts = []
        active_locks = self.get_active_locks()

        for path in paths:
            for lock in active_locks:
                # Skip own locks (unless self-conflict check needed)
                if lock.agent_id == agent_id:
                    continue

                # Check if paths conflict
                if self._paths_conflict(path, lock):
                    conflict_type = self._determine_conflict_type(path, lock)
                    conflict = Conflict(
                        type=conflict_type,
                        path=path,
                        requested_by=agent_id,
                        existing_lock=lock,
                        message=f"{path} conflicts with lock by {lock.agent_id} on {lock.path}",
                    )
                    conflicts.append(conflict)

        return conflicts

    def get_resolution_suggestions(self, conflicts: list[Conflict]) -> list[dict]:
        """
        Get resolution suggestions for conflicts.

        Args:
            conflicts: List of conflicts to resolve

        Returns:
            List of suggestion dictionaries
        """
        suggestions = []

        for conflict in conflicts:
            suggestion = {
                "conflict_type": conflict.type.value,
                "path": conflict.path,
                "locked_by": conflict.existing_lock.agent_id,
                "suggestions": [],
            }

            if conflict.type == ConflictType.FILE_ALREADY_LOCKED:
                suggestion["suggestions"] = [
                    f"Wait for {conflict.existing_lock.agent_id} to release the lock",
                    f"Coordinate with {conflict.existing_lock.agent_id} to work sequentially",
                    f"Claim a different file and return later",
                ]
            elif conflict.type == ConflictType.DIRECTORY_OVERLAP:
                suggestion["suggestions"] = [
                    f"Use narrower file scope instead of directory",
                    f"Wait for {conflict.existing_lock.agent_id} to finish",
                    f"Split work between agents by subdirectories",
                ]
            elif conflict.type == ConflictType.PATTERN_MATCH:
                suggestion["suggestions"] = [
                    f"Use specific file paths instead of patterns",
                    f"Refine pattern to exclude locked files",
                    f"Coordinate pattern scope with {conflict.existing_lock.agent_id}",
                ]

            suggestions.append(suggestion)

        return suggestions

    def release_lock(self, lock_id: str) -> bool:
        """
        Release a specific lock.

        Args:
            lock_id: Lock identifier

        Returns:
            True if lock was released, False if not found
        """
        lock_file = self.storage_dir / f"{lock_id}.json"

        if lock_file.exists():
            lock_file.unlink()
            logger.info(f"Lock released: {lock_id}")
            return True

        return False

    def release_agent_locks(self, agent_id: str) -> int:
        """
        Release all locks for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Number of locks released
        """
        count = 0
        for lock_file in self.storage_dir.glob("*.json"):
            try:
                lock = self._load_lock(lock_file)
                if lock.agent_id == agent_id:
                    lock_file.unlink()
                    count += 1
            except Exception:
                continue

        logger.info(f"Released {count} locks for agent {agent_id}")
        return count

    def is_locked(self, path: Path | str) -> bool:
        """
        Check if a path is locked.

        Args:
            path: Path to check

        Returns:
            True if path is locked by any agent
        """
        path_str = str(path)
        active_locks = self.get_active_locks()

        for lock in active_locks:
            if self._paths_conflict(path_str, lock):
                return True

        return False

    def get_active_locks(self) -> list[Lock]:
        """
        Get all active (non-expired) locks.

        Returns:
            List of active locks
        """
        locks = []

        for lock_file in self.storage_dir.glob("*.json"):
            try:
                lock = self._load_lock(lock_file)
                if not lock.is_expired():
                    locks.append(lock)
                else:
                    # Clean up expired lock
                    lock_file.unlink()
            except Exception as e:
                logger.debug(f"Error loading lock file {lock_file}: {e}")
                continue

        return locks

    def get_agent_locks(self, agent_id: str) -> list[Lock]:
        """
        Get all locks for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            List of locks for the agent
        """
        all_locks = self.get_active_locks()
        return [lock for lock in all_locks if lock.agent_id == agent_id]

    def _save_lock(self, lock: Lock) -> None:
        """Save lock to file."""
        lock_file = self.storage_dir / f"{lock.lock_id}.json"
        lock_file.write_text(json.dumps(lock.to_dict(), indent=2))

    def _load_lock(self, lock_file: Path) -> Lock:
        """Load lock from file."""
        return Lock.from_dict(json.loads(lock_file.read_text()))

    def _cleanup_expired(self) -> None:
        """Remove expired lock files."""
        for lock_file in self.storage_dir.glob("*.json"):
            try:
                lock = self._load_lock(lock_file)
                if lock.is_expired():
                    lock_file.unlink()
                    logger.debug(f"Cleaned up expired lock: {lock.lock_id}")
            except Exception:
                continue

    def _paths_conflict(self, path: str, lock: Lock) -> bool:
        """Check if path conflicts with lock."""
        # Normalize paths
        path = path.rstrip("/")
        lock_path = lock.path.rstrip("/")

        if lock.scope == LockScope.FILE:
            # File lock: exact match OR
            # - if checking a directory, check if locked file is inside it
            # - if checking a file, check if it's the locked file
            if path == lock_path:
                return True
            # If checking a directory, does it contain the locked file?
            if "/" in lock_path:
                return lock_path.startswith(path + "/")
            return False

        elif lock.scope == LockScope.DIRECTORY:
            # Directory lock: 
            # - path is within the locked directory
            # - locked directory is within the path (path is a parent)
            # - exact match
            return (
                path.startswith(lock_path + "/")  # path inside locked dir
                or lock_path.startswith(path + "/")  # locked dir inside path
                or path == lock_path  # exact match
            )

        elif lock.scope == LockScope.PATTERN:
            # Pattern lock: fnmatch in both directions
            return fnmatch.fnmatch(path, lock_path) or fnmatch.fnmatch(lock_path, path)

        return False

    def _determine_conflict_type(self, path: str, lock: Lock) -> ConflictType:
        """Determine the type of conflict."""
        if lock.scope == LockScope.DIRECTORY or path.endswith("/"):
            return ConflictType.DIRECTORY_OVERLAP
        elif lock.scope == LockScope.PATTERN:
            return ConflictType.PATTERN_MATCH
        else:
            return ConflictType.FILE_ALREADY_LOCKED
