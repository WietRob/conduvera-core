"""
Stream State Store — Runtime state machine for agent streams.

Complements the Agent Registry with fine-grained stream state tracking.
Compatible with legacy .git/agent-state/streams/ path.

State transitions are guarded. BLOCKED streams only accept BLOCKER.
READY_FOR_REVIEW requires head_sha evidence.

Storage: .captain/state/streams/<agent>.json
Legacy:  .git/agent-state/streams/<agent>.json (read-compatible)
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List


class StreamState(str, Enum):
    """Agent stream states."""
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    WORKING = "WORKING"
    READY_CANDIDATE = "READY_CANDIDATE"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    MERGED = "MERGED"
    CLOSED = "CLOSED"
    BLOCKED_LOCAL_QUALITY_GATE = "BLOCKED_LOCAL_QUALITY_GATE"
    BLOCKED_SCOPE_POLICY = "BLOCKED_SCOPE_POLICY"
    BLOCKED_WORKTREE_CONTAMINATION = "BLOCKED_WORKTREE_CONTAMINATION"
    BLOCKED_EXTERNAL_PLATFORM = "BLOCKED_EXTERNAL_PLATFORM"
    BLOCKED_CLASSIFICATION = "BLOCKED_CLASSIFICATION"
    BLOCKED_HUMAN_DECISION = "BLOCKED_HUMAN_DECISION"


class AgentReply(str, Enum):
    """Allowed agent reply types."""
    ACK = "ACK"
    PROGRESS = "PROGRESS"
    BLOCKER = "BLOCKER"
    READY_CANDIDATE = "READY_CANDIDATE"
    READY = "READY"


# Which replies are allowed per state
STATE_REPLY_MATRIX: Dict[StreamState, List[AgentReply]] = {
    StreamState.WORKING: [
        AgentReply.ACK, AgentReply.PROGRESS, AgentReply.BLOCKER, AgentReply.READY_CANDIDATE,
    ],
    StreamState.READY_CANDIDATE: [
        AgentReply.READY_CANDIDATE, AgentReply.BLOCKER,
    ],
    StreamState.READY_FOR_REVIEW: [],  # No agent action needed
    StreamState.MERGED: [],
    StreamState.CLOSED: [],
    StreamState.BLOCKED_LOCAL_QUALITY_GATE: [AgentReply.BLOCKER],
    StreamState.BLOCKED_SCOPE_POLICY: [AgentReply.BLOCKER],
    StreamState.BLOCKED_WORKTREE_CONTAMINATION: [AgentReply.BLOCKER],
    StreamState.BLOCKED_EXTERNAL_PLATFORM: [AgentReply.BLOCKER],
    StreamState.BLOCKED_CLASSIFICATION: [AgentReply.BLOCKER],
    StreamState.BLOCKED_HUMAN_DECISION: [AgentReply.BLOCKER],
    StreamState.NEW: [AgentReply.ACK],
    StreamState.ASSIGNED: [AgentReply.ACK],
}

# Valid transitions
TRANSITIONS: Dict[StreamState, List[StreamState]] = {
    StreamState.NEW: [StreamState.ASSIGNED],
    StreamState.ASSIGNED: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.WORKING: [
        StreamState.READY_CANDIDATE,
        StreamState.BLOCKED_LOCAL_QUALITY_GATE,
        StreamState.BLOCKED_SCOPE_POLICY,
        StreamState.BLOCKED_WORKTREE_CONTAMINATION,
        StreamState.BLOCKED_EXTERNAL_PLATFORM,
        StreamState.BLOCKED_CLASSIFICATION,
        StreamState.BLOCKED_HUMAN_DECISION,
        StreamState.CLOSED,
    ],
    StreamState.READY_CANDIDATE: [
        StreamState.READY_FOR_REVIEW,
        StreamState.WORKING,
        StreamState.BLOCKED_LOCAL_QUALITY_GATE,
        StreamState.CLOSED,
    ],
    StreamState.READY_FOR_REVIEW: [
        StreamState.MERGED,
        StreamState.WORKING,
        StreamState.CLOSED,
    ],
    StreamState.MERGED: [],
    StreamState.CLOSED: [],
    StreamState.BLOCKED_LOCAL_QUALITY_GATE: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.BLOCKED_SCOPE_POLICY: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.BLOCKED_WORKTREE_CONTAMINATION: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.BLOCKED_EXTERNAL_PLATFORM: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.BLOCKED_CLASSIFICATION: [StreamState.WORKING, StreamState.CLOSED],
    StreamState.BLOCKED_HUMAN_DECISION: [StreamState.WORKING, StreamState.CLOSED],
}


@dataclass
class StreamRecord:
    """A single agent's stream state."""
    agent: str
    state: StreamState = StreamState.NEW
    reason: str = ""
    required_agent_reply: str = ""
    head_sha: str = ""
    updated_at: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            now = datetime.now(timezone.utc).isoformat()
            self.created_at = now
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StreamRecord":
        if "state" in data and isinstance(data["state"], str):
            data["state"] = StreamState(data["state"])
        return cls(**data)


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""
    pass


class InvalidReplyError(Exception):
    """Raised when an agent reply is not allowed in current state."""
    pass


class StreamStateStore:
    """
    Manages agent stream states with transition guards.

    Storage: .captain/state/streams/<agent>.json
    Legacy compat: .git/agent-state/streams/<agent>.json (read-only fallback)
    """

    def __init__(self, control_dir: Optional[Path] = None):
        if control_dir is None:
            control_dir = Path.cwd() / ".captain" / "state"
        self._control_dir = control_dir
        self._streams_dir = control_dir / "streams"
        # Legacy compat
        self._legacy_dir = Path.cwd() / ".git" / "agent-state" / "streams"

    def _ensure_dir(self):
        self._streams_dir.mkdir(parents=True, exist_ok=True)

    def _stream_path(self, agent: str) -> Path:
        return self._streams_dir / f"{agent}.json"

    def _legacy_path(self, agent: str) -> Path:
        return self._legacy_dir / f"{agent}.json"

    # ── Read ──────────────────────────────────────────────────────

    def get(self, agent: str) -> StreamRecord:
        """Get stream state. Falls back to legacy path."""
        path = self._stream_path(agent)
        if path.exists():
            with open(path, "r") as f:
                return StreamRecord.from_dict(json.load(f))

        # Legacy fallback
        legacy = self._legacy_path(agent)
        if legacy.exists():
            with open(legacy, "r") as f:
                return StreamRecord.from_dict(json.load(f))

        # Default: NEW
        return StreamRecord(agent=agent)

    # ── Write ─────────────────────────────────────────────────────

    def set_state(
        self,
        agent: str,
        new_state: StreamState,
        reason: str = "",
        head_sha: str = "",
    ) -> StreamRecord:
        """Transition to a new state with guard check."""
        record = self.get(agent)

        if new_state not in TRANSITIONS.get(record.state, []):
            raise InvalidTransitionError(
                f"Cannot transition {record.state.value} → {new_state.value} "
                f"for agent '{agent}'"
            )

        # READY_FOR_REVIEW requires head_sha
        if new_state == StreamState.READY_FOR_REVIEW and not head_sha and not record.head_sha:
            raise InvalidTransitionError(
                "READY_FOR_REVIEW requires head_sha evidence"
            )

        record.state = new_state
        record.reason = reason
        if head_sha:
            record.head_sha = head_sha
        record.updated_at = datetime.now(timezone.utc).isoformat()

        # Set required reply based on new state
        allowed = STATE_REPLY_MATRIX.get(new_state, [])
        if allowed:
            record.required_agent_reply = allowed[0].value
        else:
            record.required_agent_reply = ""

        self._save(record)
        return record

    def _save(self, record: StreamRecord):
        self._ensure_dir()
        with open(self._stream_path(record.agent), "w") as f:
            json.dump(record.to_dict(), f, indent=2)

    # ── Reply Validation ──────────────────────────────────────────

    def validate_reply(self, agent: str, reply: AgentReply) -> bool:
        """Check if an agent reply is allowed in current state."""
        record = self.get(agent)
        allowed = STATE_REPLY_MATRIX.get(record.state, [])
        return reply in allowed

    def accept_reply(self, agent: str, reply: AgentReply) -> StreamRecord:
        """Accept an agent reply, potentially transitioning state."""
        if not self.validate_reply(agent, reply):
            record = self.get(agent)
            allowed = [r.value for r in STATE_REPLY_MATRIX.get(record.state, [])]
            raise InvalidReplyError(
                f"Reply '{reply.value}' not allowed in state '{record.state.value}'. "
                f"Allowed: {allowed}"
            )

        record = self.get(agent)

        # READY_CANDIDATE reply from WORKING → transition to READY_CANDIDATE
        if reply == AgentReply.READY_CANDIDATE and record.state == StreamState.WORKING:
            return self.set_state(agent, StreamState.READY_CANDIDATE, reason="Agent declared ready candidate")

        # ACK from NEW → ASSIGNED
        if reply == AgentReply.ACK and record.state == StreamState.NEW:
            return self.set_state(agent, StreamState.ASSIGNED, reason="Agent acknowledged")

        return record

    # ── Queries ───────────────────────────────────────────────────

    def list_all(self) -> List[StreamRecord]:
        """List all stream states."""
        records = []
        seen = set()

        # New path
        if self._streams_dir.exists():
            for p in self._streams_dir.glob("*.json"):
                agent = p.stem
                seen.add(agent)
                with open(p, "r") as f:
                    records.append(StreamRecord.from_dict(json.load(f)))

        # Legacy path (only agents not in new path)
        if self._legacy_dir.exists():
            for p in self._legacy_dir.glob("*.json"):
                agent = p.stem
                if agent not in seen:
                    with open(p, "r") as f:
                        records.append(StreamRecord.from_dict(json.load(f)))

        return records

    def list_blocked(self) -> List[StreamRecord]:
        """List all blocked streams."""
        return [r for r in self.list_all() if r.state.value.startswith("BLOCKED")]

    def list_by_state(self, state: StreamState) -> List[StreamRecord]:
        """List streams in a specific state."""
        return [r for r in self.list_all() if r.state == state]
