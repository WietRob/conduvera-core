"""Structured provider-failure receipt (provider-failure.v1).

Goal close-the-true-provider-lifecycle-e2e, Arbeit 2: the receipt schema is
versioned INSIDE the serialized payload (``schema: provider-failure.v1``) —
a dataclass field, present in REQUIRED_FIELDS, round-tripped through
to_dict()/to_json()/from_dict(). Unknown or incompatible MAJOR versions are
rejected fail-closed (no silent reinterpretation).

Every field is present — explicitly null when unknown, never only free-text
in a ``detail`` blob. ``last_failure_error`` may exist additionally but is
NOT the canonical evidence.

Source must be ``worker-runtime/provider-failure-normalizer`` (never
``capability-resolver`` — that source is for capability routing blocks).
``raw_error_excerpt`` is an honest short excerpt of the raw error text (not
a stable artifact hash — renamed from the earlier ``raw_error_ref``).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

RECEIPT_SCHEMA = "provider-failure.v1"
RECEIPT_SCHEMA_MAJOR = "provider-failure.v1"
RECEIPT_SOURCE = "worker-runtime/provider-failure-normalizer"

# Canonical field order (all required — explicit null when unknown).
REQUIRED_FIELDS = (
    "schema", "task_id", "attempt_id", "session_id", "assignee", "provider",
    "model", "failure_reason", "http_status", "retryable", "retry_after_s",
    "retry_at", "timestamp", "exit_code", "source", "raw_error_excerpt",
)


def validate_schema(data: dict[str, Any]) -> str:
    """Fail-closed schema check (Arbeit 2).

    Returns the schema string when compatible (exact major match); raises
    :class:`ValueError` for an unknown or incompatible MAJOR version.
    """
    schema = data.get("schema")
    if schema is None:
        raise ValueError("provider-failure receipt missing required 'schema'")
    if schema == RECEIPT_SCHEMA:
        return schema
    # Major-version compatibility: the major is the "provider-failure.v<N>"
    # prefix up to and including the dot-number. Only v1 is currently known;
    # anything else is incompatible and fails closed.
    raise ValueError(
        f"incompatible provider-failure receipt schema {schema!r} "
        f"(expected {RECEIPT_SCHEMA!r})"
    )


@dataclass(frozen=True)
class ProviderFailureReceipt:
    """One structured provider-failure record (provider-failure.v1)."""

    schema: str = RECEIPT_SCHEMA
    task_id: str = ""
    attempt_id: Optional[str] = None
    session_id: Optional[str] = None
    assignee: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    failure_reason: Optional[str] = None
    http_status: Optional[int] = None
    retryable: bool = True
    retry_after_s: Optional[int] = None
    retry_at: Optional[int] = None  # epoch seconds; None = not scheduled
    timestamp: int = field(default_factory=lambda: int(time.time()))
    exit_code: Optional[int] = None
    source: str = RECEIPT_SOURCE
    raw_error_excerpt: Optional[str] = None  # honest excerpt of the raw error

    def to_dict(self) -> dict[str, Any]:
        """Dict with ALL required fields present (explicit null)."""
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "ProviderFailureReceipt":
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderFailureReceipt":
        # Fail-closed on unknown/incompatible schema before interpreting.
        validate_schema(data)
        return cls(
            schema=str(data.get("schema") or RECEIPT_SCHEMA),
            task_id=str(data.get("task_id") or ""),
            attempt_id=data.get("attempt_id"),
            session_id=data.get("session_id"),
            assignee=data.get("assignee"),
            provider=data.get("provider"),
            model=data.get("model"),
            failure_reason=data.get("failure_reason"),
            http_status=data.get("http_status"),
            retryable=bool(data.get("retryable", True)),
            retry_after_s=data.get("retry_after_s"),
            retry_at=data.get("retry_at"),
            timestamp=int(data.get("timestamp") or int(time.time())),
            exit_code=data.get("exit_code"),
            source=str(data.get("source") or RECEIPT_SOURCE),
            raw_error_excerpt=data.get("raw_error_excerpt"),
        )


def build_provider_failure_receipt(
    *,
    task_id: str,
    failure_reason: str,
    exit_code: int,
    assignee: Optional[str] = None,
    attempt_id: Optional[str] = None,
    session_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    http_status: Optional[int] = None,
    retry_after_s: Optional[int] = None,
    raw_error_excerpt: Optional[str] = None,
) -> dict[str, Any]:
    """Build a complete provider-failure.v1 receipt dict.

    ``retryable`` derives from the reason (billing is never retryable);
    ``retry_at`` = now + retry_after_s when provided AND retryable. Every
    required field is present (explicit null when unknown), including the
    versioned ``schema`` tag.
    """
    retryable = failure_reason != "billing"
    now = int(time.time())
    # Billing invariant (goal close-provider-failure-lifecycle, Arbeit 4,
    # P2-B aus finalem Review): billing is NEVER retryable AND never gets a
    # retry_at — an auto-recovery after a cooldown would re-spawn the worker
    # into the same billing wall forever. blocked_until stays NULL.
    retry_at = (now + retry_after_s) if (retry_after_s and retryable) else None
    return {
        "schema": RECEIPT_SCHEMA,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "session_id": session_id,
        "assignee": assignee,
        "provider": provider,
        "model": model,
        "failure_reason": failure_reason,
        "http_status": http_status,
        "retryable": retryable,
        "retry_after_s": retry_after_s,
        "retry_at": retry_at,
        "timestamp": now,
        "exit_code": exit_code,
        "source": RECEIPT_SOURCE,
        "raw_error_excerpt": raw_error_excerpt,
    }
