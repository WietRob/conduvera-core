"""Evidence event contract for the Matrix OS harness."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

SCHEMA_VERSION = "MXOS-EVIDENCE-1.0.0"
CORE_EVENT_TYPES = {
    "change_request.evidence.generated",
    "accountable_change.evidence.generated",
    "aspice.check.completed",
    "gate.run.completed",
}
ADAPTER_EVENT_TYPES = {
    # Thin adapter event types imported from agent-evidence-plane. These are
    # explicit Matrix OS adapter contract types, not an open-ended registry.
    "agent.run.started",
    "agent.run.completed",
    "agent.run.failed",
    "failure.observed",
    "rule.proposed",
    # Thin adapter event types imported from CuraOps Safety Guard result
    # fixtures/logs. These are explicit Matrix OS adapter contract types, not
    # an open-ended safety-event registry.
    "safety_guard.check.completed",
    "safety_guard.action.allowed",
    "safety_guard.action.blocked",
    "safety_guard.approval.required",
    # Buildroom legacy integration slice (read-only strangler, MXOS-RUNTIME-1):
    # explicit event types for the frozen legacy reader. Same envelope, same
    # schema (MXOS-EVIDENCE-1.0.0); no new schema introduced.
    "buildroom.legacy.inventory.completed",
    "buildroom.legacy.readiness.completed",
    # Managed fixture run (CONDUVERA-GOAL-1.0, first vertical slice):
    # task/attempt/session lifecycle events for the internal Buildroom module.
    "fixture.run.started",
    "fixture.run.completed",
    "fixture.run.failed",
    "fixture.run.timed_out",
    "fixture.run.cancelled",
    "fixture.run.reconciled",
    "fixture.attempt.bound",
    "fixture.attempt.restarted",
}
EVENT_TYPES = CORE_EVENT_TYPES | ADAPTER_EVENT_TYPES
SEVERITIES = {"debug", "info", "warning", "error", "critical"}


class ValidationError(ValueError):
    """Raised when a Matrix OS evidence event or event stream is invalid."""


class EvidenceProducer(Protocol):
    """Adapter boundary for future external evidence producers.

    Implementers return Matrix OS ``EventEnvelope`` instances. Matrix OS owns this
    protocol; external producers such as agent-evidence-plane stay separately
    maintainable and may adapt into it later.
    """

    def produce_events(self) -> list["EventEnvelope"]:
        """Return events ready to validate and append to the Matrix OS store."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(data: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _canonical_event_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(data, ensure_ascii=False))
    payload.pop("event_hash", None)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("hash", None)
    return payload


@dataclass(frozen=True)
class EventEnvelope:
    """Validated Matrix OS evidence event envelope."""

    schema_version: str
    event_id: str
    event_type: str
    occurred_at: str
    producer: dict[str, Any]
    subject: dict[str, Any]
    payload: dict[str, Any]
    severity: str = "info"
    correlation_id: str | None = None
    run_id: str | None = None
    references: list[dict[str, Any]] | None = None
    links: list[dict[str, Any]] | None = None
    event_hash: str | None = None

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        producer: dict[str, Any],
        subject: dict[str, Any],
        payload: dict[str, Any],
        severity: str = "info",
        correlation_id: str | None = None,
        run_id: str | None = None,
        references: list[dict[str, Any]] | None = None,
        links: list[dict[str, Any]] | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> "EventEnvelope":
        data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id or f"mxev_{uuid.uuid4().hex}",
            "event_type": event_type,
            "occurred_at": occurred_at or _utc_now(),
            "producer": producer,
            "subject": subject,
            "severity": severity,
            "payload": payload,
            "integrity": {
                "algorithm": "sha256",
                "hash_excludes": ["event_hash", "integrity.hash"],
                "hash": None,
            },
        }
        if correlation_id:
            data["correlation_id"] = correlation_id
        if run_id:
            data["run_id"] = run_id
        if references:
            data["references"] = references
        if links:
            data["links"] = links
        digest = _hash_payload(_canonical_event_payload(data))
        data["event_hash"] = digest
        data["integrity"]["hash"] = digest
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        _validate_event_dict(data)
        integrity = data.get("integrity") if isinstance(data.get("integrity"), dict) else {}
        event_hash = data.get("event_hash") or integrity.get("hash")
        return cls(
            schema_version=data["schema_version"],
            event_id=data["event_id"],
            event_type=data["event_type"],
            occurred_at=data["occurred_at"],
            producer=data["producer"],
            subject=data["subject"],
            payload=data["payload"],
            severity=data.get("severity", "info"),
            correlation_id=data.get("correlation_id"),
            run_id=data.get("run_id"),
            references=data.get("references"),
            links=data.get("links"),
            event_hash=event_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "producer": self.producer,
            "subject": self.subject,
            "severity": self.severity,
            "payload": self.payload,
            "integrity": {
                "algorithm": "sha256",
                "hash_excludes": ["event_hash", "integrity.hash"],
                "hash": self.event_hash,
            },
            "event_hash": self.event_hash,
        }
        if self.correlation_id:
            data["correlation_id"] = self.correlation_id
        if self.run_id:
            data["run_id"] = self.run_id
        if self.references:
            data["references"] = self.references
        if self.links:
            data["links"] = self.links
        return data


def compute_event_hash(data: dict[str, Any]) -> str:
    """Compute the deterministic hash for an event dictionary."""

    return _hash_payload(_canonical_event_payload(data))


def _validate_event_dict(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("event must be an object")
    for field in ("schema_version", "event_id", "event_type", "occurred_at", "producer", "subject", "payload"):
        if field not in data:
            raise ValidationError(f"missing required field: {field}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(f"unsupported schema_version: {data['schema_version']}")
    if not isinstance(data["event_id"], str) or not data["event_id"].startswith("mxev_"):
        raise ValidationError("event_id must start with mxev_")
    if data["event_type"] not in EVENT_TYPES:
        raise ValidationError(f"unsupported event_type: {data['event_type']}")
    if not isinstance(data["occurred_at"], str) or not data["occurred_at"].endswith("Z"):
        raise ValidationError("occurred_at must be UTC RFC3339 with Z suffix")
    if not isinstance(data["producer"], dict) or not data["producer"].get("name"):
        raise ValidationError("missing required field: producer.name")
    if not isinstance(data["subject"], dict) or not data["subject"].get("kind"):
        raise ValidationError("missing required field: subject.kind")
    if not isinstance(data["payload"], dict):
        raise ValidationError("payload must be an object")
    severity = data.get("severity", "info")
    if severity not in SEVERITIES:
        raise ValidationError(f"unsupported severity: {severity}")
    references = data.get("references")
    if references is not None and not isinstance(references, list):
        raise ValidationError("references must be a list")
    links = data.get("links")
    if links is not None and not isinstance(links, list):
        raise ValidationError("links must be a list")
    stored = data.get("event_hash")
    integrity = data.get("integrity")
    if not isinstance(integrity, dict) or not integrity.get("hash"):
        raise ValidationError("missing required field: event_hash")
    if not stored:
        raise ValidationError("missing required field: event_hash")
    if stored != integrity["hash"]:
        raise ValidationError("event_hash mismatch with integrity.hash")
    computed = compute_event_hash(data)
    if stored != computed:
        raise ValidationError("event_hash mismatch")
