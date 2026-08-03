#!/usr/bin/env python3
"""Generic bounded no-progress reconciliation guard for Buildroom phases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, MutableMapping


@dataclass(frozen=True)
class NoProgressResult:
    """Result of one reconciliation observation."""

    count: int
    terminal_hold: bool
    fingerprint: tuple[str, ...]


def observe_reconciliation(
    state: MutableMapping[str, Any],
    *,
    phase: str,
    status: str,
    blocker: str,
    task_id: str,
    task_board: str = "",
    evidence_fingerprint: str,
    log_fingerprint: str,
    threshold: int = 3,
) -> NoProgressResult:
    """Count identical no-progress observations and fail closed at ``threshold``.

    A new evidence artifact is progress and clears the counter. A changed task,
    log, phase, status, or blocker starts a fresh sequence at one. The terminal
    action changes only status/blocker; phase, PR, task IDs, and merge state are
    intentionally untouched.
    """
    if threshold < 1:
        raise ValueError("NO_PROGRESS_THRESHOLD_INVALID")

    fingerprint = (
        str(phase),
        str(status),
        str(blocker),
        str(task_id),
        str(evidence_fingerprint),
        str(log_fingerprint),
    )
    previous = state.get("no_progress")
    observed_at = datetime.now(timezone.utc).isoformat()

    if evidence_fingerprint:
        state["no_progress"] = {
            "count": 0,
            "fingerprint": list(fingerprint),
            "terminal_hold": False,
            "reset_reason": "NEW_EVIDENCE",
            "threshold": threshold,
            "first_observed_at": observed_at,
            "last_observed_at": observed_at,
            "root_blocker": str(blocker),
            "task_binding": {"task_id": str(task_id), "board": str(task_board)},
            "evidence_fingerprint": str(evidence_fingerprint),
            "log_fingerprint": str(log_fingerprint),
        }
        return NoProgressResult(count=0, terminal_hold=False, fingerprint=fingerprint)

    previous_fingerprint = tuple(previous.get("fingerprint", ())) if isinstance(previous, dict) else ()
    previous_count = int(previous.get("count", 0)) if isinstance(previous, dict) else 0
    count = previous_count + 1 if previous_fingerprint == fingerprint else 1
    terminal_hold = count >= threshold
    first_observed_at = (
        str(previous.get("first_observed_at"))
        if isinstance(previous, dict)
        and previous_fingerprint == fingerprint
        and previous.get("first_observed_at")
        else observed_at
    )

    state["no_progress"] = {
        "count": count,
        "fingerprint": list(fingerprint),
        "terminal_hold": terminal_hold,
        "threshold": threshold,
        "first_observed_at": first_observed_at,
        "last_observed_at": observed_at,
        "root_blocker": str(blocker),
        "task_binding": {"task_id": str(task_id), "board": str(task_board)},
        "evidence_fingerprint": str(evidence_fingerprint),
        "log_fingerprint": str(log_fingerprint),
    }
    if terminal_hold:
        state["status"] = "HOLD_FOR_BOSS"
        state["blocker"] = "REPEATED_NO_PROGRESS"
        state["root_blocker"] = str(blocker)

    return NoProgressResult(count=count, terminal_hold=terminal_hold, fingerprint=fingerprint)
