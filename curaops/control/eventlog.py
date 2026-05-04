"""
Event Log — Append-only audit trail for CuraOps-Control.

Every state change, gate result, dispatch, and boot event is recorded here.
Immutable: events are appended, never modified or deleted.

Storage: .curaops/control/events.jsonl
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Iterator


@dataclass
class ControlEvent:
    """A single event in the control log."""
    timestamp: str
    event_type: str       # boot, status_change, gate_run, dispatch, evidence, sync, block
    agent_id: str
    detail: str
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json_line(self) -> str:
        d = asdict(self)
        return json.dumps(d, sort_keys=False)

    @classmethod
    def from_json_line(cls, line: str) -> "ControlEvent":
        data = json.loads(line.strip())
        return cls(**data)


class EventLog:
    """
    Append-only JSONL event log.

    Thread-safe via atomic appends. No locking needed for reads.
    """

    def __init__(self, control_dir: Optional[Path] = None):
        if control_dir is None:
            control_dir = Path.cwd() / ".curaops" / "control"
        self._control_dir = control_dir
        self._log_path = control_dir / "events.jsonl"

    def _ensure_dir(self):
        self._control_dir.mkdir(parents=True, exist_ok=True)

    # ── Write ─────────────────────────────────────────────────────

    def append(self, event: ControlEvent):
        """Append a single event. Atomic write."""
        self._ensure_dir()
        with open(self._log_path, "a") as f:
            f.write(event.to_json_line() + "\n")

    def log(self, event_type: str, agent_id: str, detail: str, **metadata):
        """Convenience: create and append an event in one call."""
        event = ControlEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            agent_id=agent_id,
            detail=detail,
            metadata=metadata,
        )
        self.append(event)
        return event

    # ── Read ──────────────────────────────────────────────────────

    def read_all(self) -> List[ControlEvent]:
        """Read all events (memory-heavy for large logs)."""
        if not self._log_path.exists():
            return []
        events = []
        with open(self._log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(ControlEvent.from_json_line(line))
        return events

    def read_last(self, n: int = 50) -> List[ControlEvent]:
        """Read last N events. Efficient for tail-view."""
        if not self._log_path.exists():
            return []
        events = []
        with open(self._log_path, "r") as f:
            # Read all lines (simple approach; for very large logs use seek)
            lines = f.readlines()
        for line in lines[-n:]:
            line = line.strip()
            if line:
                events.append(ControlEvent.from_json_line(line))
        return events

    def iter_events(self) -> Iterator[ControlEvent]:
        """Stream events one by one."""
        if not self._log_path.exists():
            return
        with open(self._log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield ControlEvent.from_json_line(line)

    # ── Queries ───────────────────────────────────────────────────

    def events_for_agent(self, agent_id: str, limit: int = 50) -> List[ControlEvent]:
        """Get events for a specific agent."""
        events = []
        for event in reversed(self.read_all()):
            if event.agent_id == agent_id:
                events.append(event)
                if len(events) >= limit:
                    break
        return list(reversed(events))

    def events_of_type(self, event_type: str, limit: int = 50) -> List[ControlEvent]:
        """Get events of a specific type."""
        events = []
        for event in reversed(self.read_all()):
            if event.event_type == event_type:
                events.append(event)
                if len(events) >= limit:
                    break
        return list(reversed(events))

    def count(self) -> int:
        """Count total events."""
        if not self._log_path.exists():
            return 0
        with open(self._log_path, "r") as f:
            return sum(1 for line in f if line.strip())
