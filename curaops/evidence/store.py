"""JSONL event store for Matrix OS evidence backbone events."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from curaops.evidence.contract import EventEnvelope, ValidationError


def default_event_store_path(project_root: str | Path | None = None) -> Path:
    """Return the Matrix OS harness-side event store path convention."""

    root = Path(project_root) if project_root is not None else Path.cwd()
    return root / "changes" / "evidence" / "events.jsonl"


class EvidenceStore:
    """Append/read JSONL store for validated Matrix OS evidence events."""

    def __init__(self, path: str | Path | None = None, *, project_root: str | Path | None = None):
        self.path = Path(path) if path is not None else default_event_store_path(project_root)

    def append(self, event: EventEnvelope) -> Path:
        """Validate and append one event to the JSONL store."""

        event = EventEnvelope.from_dict(event.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        return self.path

    def read_all(self) -> list[EventEnvelope]:
        """Read and validate all events from the store."""

        return list(read_event_stream(self.path))


def read_event_stream(path: str | Path) -> Iterable[EventEnvelope]:
    path = Path(path)
    if not path.exists():
        return []

    def iterator():
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield EventEnvelope.from_dict(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
                except ValidationError as exc:
                    raise ValidationError(f"line {line_number}: {exc}") from exc

    return iterator()


def write_event_stream(path: str | Path, events: Iterable[EventEnvelope]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            event = EventEnvelope.from_dict(event.to_dict())
            handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    return path


def validate_event_stream(path: str | Path) -> dict[str, object]:
    """Validate a JSONL event stream and return a CLI-friendly result."""

    count = 0
    errors: list[str] = []
    path = Path(path)
    if not path.exists():
        return {"valid": False, "events": 0, "errors": [f"missing file: {path}"]}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                EventEnvelope.from_dict(json.loads(line))
                count += 1
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            except ValidationError as exc:
                errors.append(f"line {line_number}: {exc}")
    return {"valid": not errors, "events": count, "errors": errors}


def summarize_event_stream(path: str | Path) -> dict[str, object]:
    """Summarize a valid event stream by event type, producer, and subject kind."""

    events = list(read_event_stream(path))
    return {
        "events": len(events),
        "event_types": dict(sorted(Counter(event.event_type for event in events).items())),
        "producers": dict(sorted(Counter(event.producer["name"] for event in events).items())),
        "subjects": dict(sorted(Counter(event.subject["kind"] for event in events).items())),
    }
