"""Restart-safe event stream bus (SHIP-CONDUVERA-DELIVERY, Workstream F).

A one-way event stream with monotonically ordered event ids and Last-Event-ID
resume. Subscribers (the SSE HTTP endpoint) block on the bus and receive
events; the bus keeps a bounded ring buffer so a reconnecting client can resume
from its last seen id. No external broker.

All events carry no raw prompt / secret material — the producer is responsible
for redaction before publishing.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class EventStreamBus:
    """Thread-safe ordered event bus with bounded history."""

    def __init__(self, *, max_history: int = 500, time_fn=None):
        self._history: deque[dict] = deque(maxlen=max_history)
        self._seq = 0
        self._cond = threading.Condition()
        self._time_fn = time_fn or (lambda: time.time())

    def publish(self, event_type: str, payload: dict) -> int:
        """Append one event; returns its monotonic sequence id."""
        with self._cond:
            self._seq += 1
            event = {
                "id": self._seq,
                "event": event_type,
                "at": self._time_fn(),
                "data": dict(payload),
            }
            self._history.append(event)
            self._cond.notify_all()
            return self._seq

    def last_id(self) -> int:
        with self._cond:
            return self._seq

    def events_since(self, last_id: int) -> list[dict]:
        """Return events with id > last_id (for Last-Event-ID resume)."""
        with self._cond:
            return [e for e in self._history if e["id"] > last_id]

    def wait_for_events(self, last_id: int, timeout: float = 15.0) -> list[dict]:
        """Block until at least one event newer than last_id or timeout."""
        with self._cond:
            deadline = time.time() + timeout
            while self._seq <= last_id:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return [e for e in self._history if e["id"] > last_id]


class EventStreamNotifier:
    """Wraps a bus for subscriber use (resume + incremental fetch)."""

    def __init__(self, bus: EventStreamBus):
        self.bus = bus

    def sse_format(self, event: dict) -> str:
        lines = [f"id: {event['id']}", f"event: {event['event']}"]
        data = event.get("data") or {}
        import json
        payload = json.dumps(data, sort_keys=True)
        lines.append(f"data: {payload}")
        return "\n".join(lines) + "\n\n"
