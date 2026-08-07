"""
Agent Session Manager - Session Persistence & Management
Extracted from CuraOps Framework (SW-REQ-053)

Manages:
- Session creation and persistence
- Session history and context
- Session resumption
- Session listing and browsing
- Execution tracking

Features:
- JSON-based session storage
- Session resume capability
- Session metadata tracking
- Session search and filtering
"""

import json
import hashlib
import time
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Agent session data model."""
    session_id: str
    agent: str
    model: str
    mode: str  # interactive, batch, auto
    prompt: str
    created_at: str
    updated_at: str
    status: str  # active, paused, completed, error
    history: List[Dict] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.history is None:
            self.history = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class SessionExchange:
    """A single exchange in a session."""
    timestamp: str
    task: str
    outcome: str
    tokens: int = 0
    duration_ms: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


class AgentSessionManager:
    """
    Manages AI agent sessions with persistence.
    
    Features:
    - Create new sessions
    - Load and resume existing sessions
    - Append exchanges to sessions
    - List and search sessions
    - Session metadata tracking
    
    Storage:
    Sessions are stored as JSON files in the sessions directory:
    sessions/
    ├── sess_20260405_123456_abc123.json
    ├── sess_20260405_123501_def456.json
    └── ...
    
    Example:
        >>> manager = AgentSessionManager(storage_dir="./sessions")
        >>> session = manager.create_session(
        ...     agent="cursor",
        ...     model="claude-sonnet",
        ...     prompt="Refactor auth module"
        ... )
        >>> manager.append_exchange(session.session_id, "Task", "Result")
        >>> 
        >>> # Later: resume
        >>> session = manager.load_session(session.session_id)
    """
    
    def __init__(self, storage_dir: Path):
        """
        Initialize session manager.
        
        Args:
            storage_dir: Directory to store session files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AgentSessionManager initialized: {self.storage_dir}")
    
    def create_session(
        self,
        agent: str,
        model: str,
        prompt: str,
        mode: str = "interactive",
        metadata: Dict = None,
    ) -> Session:
        """
        Create a new session.
        
        Args:
            agent: Agent name (e.g., "cursor", "vscode", "cli")
            model: Model used (e.g., "claude-sonnet", "gpt-4")
            prompt: Initial prompt/task
            mode: Session mode (interactive, batch, auto)
            metadata: Optional metadata dict
            
        Returns:
            Created Session object
        """
        timestamp = datetime.now()
        timestamp_str = timestamp.isoformat()
        
        # Generate session ID
        session_id = self._generate_session_id(agent, prompt, timestamp)
        
        session = Session(
            session_id=session_id,
            agent=agent,
            model=model,
            mode=mode,
            prompt=prompt,
            created_at=timestamp_str,
            updated_at=timestamp_str,
            status="active",
            history=[],
            metadata=metadata or {},
        )
        
        # Save to disk
        self._save_session(session)
        
        logger.info(f"Created session: {session_id}")
        return session
    
    def _generate_session_id(self, agent: str, prompt: str, timestamp: datetime) -> str:
        """Generate unique session ID."""
        time_str = timestamp.strftime("%Y%m%d_%H%M%S")
        hash_input = f"{agent}|{prompt}|{time_str}|{time.time()}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"sess_{time_str}_{hash_suffix}"
    
    def _save_session(self, session: Session):
        """Save session to disk."""
        session_file = self.storage_dir / f"{session.session_id}.json"
        
        try:
            session_file.write_text(
                json.dumps(session.to_dict(), indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise
    
    def load_session(self, session_id: str) -> Optional[Session]:
        """
        Load session by ID.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            Session object or None if not found
        """
        session_file = self.storage_dir / f"{session_id}.json"
        
        if not session_file.exists():
            logger.warning(f"Session not found: {session_id}")
            return None
        
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            return Session.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    def append_exchange(
        self,
        session_id: str,
        task: str,
        outcome: str,
        tokens: int = 0,
        duration_ms: int = 0,
    ) -> bool:
        """
        Append an exchange to session history.
        
        Args:
            session_id: Session ID
            task: Task/prompt
            outcome: Result/outcome
            tokens: Token count (optional)
            duration_ms: Duration in milliseconds (optional)
            
        Returns:
            True if successful
        """
        session = self.load_session(session_id)
        if not session:
            return False
        
        exchange = SessionExchange(
            timestamp=datetime.now().isoformat(),
            task=task,
            outcome=outcome,
            tokens=tokens,
            duration_ms=duration_ms,
        )
        
        session.history.append(exchange.to_dict())
        session.updated_at = datetime.now().isoformat()
        
        self._save_session(session)
        
        logger.info(f"Appended exchange to session {session_id}")
        return True
    
    def update_status(self, session_id: str, status: str) -> bool:
        """
        Update session status.
        
        Args:
            session_id: Session ID
            status: New status (active, paused, completed, error)
            
        Returns:
            True if successful
        """
        session = self.load_session(session_id)
        if not session:
            return False
        
        session.status = status
        session.updated_at = datetime.now().isoformat()
        
        self._save_session(session)
        
        logger.info(f"Updated session {session_id} status to {status}")
        return True
    
    def update_metadata(self, session_id: str, key: str, value: Any) -> bool:
        """
        Update session metadata.
        
        Args:
            session_id: Session ID
            key: Metadata key
            value: Metadata value
            
        Returns:
            True if successful
        """
        session = self.load_session(session_id)
        if not session:
            return False
        
        session.metadata[key] = value
        session.updated_at = datetime.now().isoformat()
        
        self._save_session(session)
        return True
    
    def list_sessions(
        self,
        agent: str = None,
        status: str = None,
        limit: int = 100,
    ) -> List[Session]:
        """
        List sessions with optional filtering.
        
        Args:
            agent: Filter by agent name
            status: Filter by status
            limit: Maximum number of sessions to return
            
        Returns:
            List of Session objects
        """
        sessions = []
        
        for session_file in sorted(self.storage_dir.glob("sess_*.json"), reverse=True):
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                session = Session.from_dict(data)
                
                # Apply filters
                if agent and session.agent != agent:
                    continue
                if status and session.status != status:
                    continue
                
                sessions.append(session)
                
                if len(sessions) >= limit:
                    break
            
            except Exception as e:
                logger.warning(f"Failed to load session file {session_file}: {e}")
                continue
        
        return sessions
    
    def get_session_stats(self) -> Dict:
        """Get session statistics."""
        sessions = self.list_sessions(limit=10000)
        
        stats = {
            "total_sessions": len(sessions),
            "by_agent": {},
            "by_status": {},
            "by_model": {},
            "total_exchanges": 0,
        }
        
        for session in sessions:
            # By agent
            stats["by_agent"][session.agent] = stats["by_agent"].get(session.agent, 0) + 1
            
            # By status
            stats["by_status"][session.status] = stats["by_status"].get(session.status, 0) + 1
            
            # By model
            stats["by_model"][session.model] = stats["by_model"].get(session.model, 0) + 1
            
            # Total exchanges
            stats["total_exchanges"] += len(session.history)
        
        return stats
    
    def search_sessions(self, query: str) -> List[Session]:
        """
        Search sessions by prompt content.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching Session objects
        """
        query_lower = query.lower()
        matches = []
        
        for session in self.list_sessions(limit=10000):
            if query_lower in session.prompt.lower():
                matches.append(session)
            else:
                # Search in history
                for exchange in session.history:
                    if query_lower in exchange.get("task", "").lower():
                        matches.append(session)
                        break
        
        return matches
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted
        """
        session_file = self.storage_dir / f"{session_id}.json"
        
        if session_file.exists():
            session_file.unlink()
            logger.info(f"Deleted session: {session_id}")
            return True
        
        return False
    
    def get_recent_sessions(self, count: int = 10) -> List[Session]:
        """Get most recent sessions."""
        return self.list_sessions(limit=count)


# CLI Interface
def create_session(storage_dir: str, agent: str, model: str, prompt: str) -> str:
    """CLI: Create new session."""
    manager = AgentSessionManager(storage_dir=Path(storage_dir))
    
    session = manager.create_session(
        agent=agent,
        model=model,
        prompt=prompt,
    )
    
    return f"✅ Created session: {session.session_id}\n   Agent: {agent}\n   Model: {model}"


def list_sessions(storage_dir: str, agent: str = None, status: str = None) -> str:
    """CLI: List sessions."""
    manager = AgentSessionManager(storage_dir=Path(storage_dir))
    
    sessions = manager.list_sessions(agent=agent, status=status, limit=50)
    
    if not sessions:
        return "📭 No sessions found"
    
    lines = [f"📋 {len(sessions)} Sessions:", ""]
    
    for session in sessions:
        status_emoji = {
            "active": "🟢",
            "paused": "⏸️",
            "completed": "✅",
            "error": "❌",
        }.get(session.status, "⚪")
        
        lines.append(f"{status_emoji} {session.session_id}")
        lines.append(f"   Agent: {session.agent} | Model: {session.model}")
        lines.append(f"   Status: {session.status} | Exchanges: {len(session.history)}")
        lines.append(f"   Prompt: {session.prompt[:60]}...")
        lines.append("")
    
    return "\n".join(lines)


def show_session(storage_dir: str, session_id: str) -> str:
    """CLI: Show session details."""
    manager = AgentSessionManager(storage_dir=Path(storage_dir))
    
    session = manager.load_session(session_id)
    if not session:
        return f"❌ Session not found: {session_id}"
    
    lines = [
        f"📋 Session: {session.session_id}",
        f"",
        f"Agent: {session.agent}",
        f"Model: {session.model}",
        f"Mode: {session.mode}",
        f"Status: {session.status}",
        f"Created: {session.created_at}",
        f"Updated: {session.updated_at}",
        f"",
        f"Prompt:",
        f"{session.prompt}",
        f"",
        f"History ({len(session.history)} exchanges):",
    ]
    
    for i, exchange in enumerate(session.history[-5:], 1):  # Show last 5
        lines.append(f"  {i}. {exchange.get('task', 'N/A')[:50]}...")
    
    if len(session.history) > 5:
        lines.append(f"  ... and {len(session.history) - 5} more")
    
    return "\n".join(lines)


def session_stats(storage_dir: str) -> str:
    """CLI: Show session statistics."""
    manager = AgentSessionManager(storage_dir=Path(storage_dir))
    
    stats = manager.get_session_stats()
    
    lines = [
        f"📊 Session Statistics:",
        f"",
        f"Total Sessions: {stats['total_sessions']}",
        f"Total Exchanges: {stats['total_exchanges']}",
        f"",
        f"By Agent:",
    ]
    
    for agent, count in stats["by_agent"].items():
        lines.append(f"  {agent}: {count}")
    
    lines.append("")
    lines.append("By Status:")
    
    for status, count in stats["by_status"].items():
        lines.append(f"  {status}: {count}")
    
    return "\n".join(lines)


__all__ = [
    "AgentSessionManager",
    "Session",
    "SessionExchange",
]
