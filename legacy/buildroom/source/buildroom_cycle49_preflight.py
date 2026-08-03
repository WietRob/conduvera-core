#!/usr/bin/env python3
"""Cycle 49 safety reconstruction and explicit hold-release primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, MutableMapping


@dataclass(frozen=True)
class WorkerObservation:
    task_id: str
    board: str
    profile: str
    task_status: str
    run_status: str
    worker_pid: int | None
    worker_alive: bool
    workspace: str | None
    cycle: int | None
    project_matches: bool
    historical_preserved: bool


@dataclass(frozen=True)
class WorkerClassification:
    observation: WorkerObservation
    classification: str
    conflicts_with_project: bool
    reason: str


@dataclass(frozen=True)
class SafetySnapshot:
    main_green: bool
    no_conflicting_active_workers: bool
    no_active_cycle48_worker: bool
    no_ambiguous_board_binding: bool
    origin_main_contains_cycle48_merge: bool
    working_state_policy_passes: bool
    projectpack_autonomous: bool

    def failures(self) -> list[str]:
        return [name for name, value in asdict(self).items() if not value]


def classify_worker(
    observation: WorkerObservation, *, completed_cycles: set[int]
) -> WorkerClassification:
    active = (
        observation.task_status == "running"
        and observation.run_status == "running"
    )
    if observation.historical_preserved:
        return WorkerClassification(
            observation, "HISTORICAL_PRESERVED", False, "explicit preserved evidence"
        )
    if active and observation.worker_alive:
        return WorkerClassification(
            observation,
            "ACTIVE_VALID",
            observation.project_matches,
            "live running task and worker",
        )
    if active and not observation.worker_alive:
        return WorkerClassification(
            observation,
            "ORPHANED_WORKER",
            observation.project_matches,
            "task/run claim is running but worker PID is not live",
        )
    if observation.cycle in completed_cycles:
        if observation.task_status in {"blocked", "todo", "ready"}:
            return WorkerClassification(
                observation,
                "STALE_RECOVERY_TASK",
                False,
                "nonterminal task row belongs to a completed cycle",
            )
        return WorkerClassification(
            observation,
            "TERMINAL_NOT_RECONCILED",
            False,
            "terminal task belongs to a completed cycle",
        )
    if observation.task_status in {"done", "archived"} or observation.run_status in {
        "done",
        "completed",
        "blocked",
        "crashed",
        "failed",
        "timed_out",
        "gave_up",
        "released",
    }:
        return WorkerClassification(
            observation,
            "TERMINAL_NOT_RECONCILED",
            False,
            "terminal task/run is not an active worker",
        )
    return WorkerClassification(
        observation,
        "UNKNOWN",
        observation.project_matches,
        "insufficient terminal or liveness evidence",
    )


def release_hold(
    state: MutableMapping[str, Any],
    safety: SafetySnapshot,
    *,
    evidence_path: str,
) -> None:
    """Release a terminal Cycle 49 hold without dispatching or selecting work."""
    if state.get("cycle") != 49 or state.get("phase") != "RESEARCHER":
        raise ValueError("HOLD_RELEASE_STATE_MISMATCH")
    if state.get("status") != "HOLD_FOR_BOSS":
        raise ValueError("HOLD_RELEASE_NOT_TERMINAL")
    if state.get("current_candidate") is not None:
        raise ValueError("HOLD_RELEASE_CANDIDATE_PRESENT")
    if state.get("task_bindings"):
        raise ValueError("HOLD_RELEASE_ACTIVE_TASK_BINDING")
    failures = safety.failures()
    if failures:
        raise ValueError(f"HOLD_RELEASE_BLOCKED:{','.join(failures)}")
    released_at = datetime.now(timezone.utc).isoformat()
    terminal_blocker = str(state.get("blocker") or "")
    root_blocker = str(state.get("root_blocker") or terminal_blocker)
    state.setdefault("hold_history", []).append(
        {
            "status": "HOLD_FOR_BOSS",
            "blocker": terminal_blocker,
            "root_blocker": root_blocker,
            "released_at": released_at,
            "release_evidence": evidence_path,
        }
    )
    state["hold_release"] = {
        "result": "HOLD_RELEASED_AFTER_SAFETY_RECONCILIATION",
        "evidence_path": evidence_path,
        "released_at": released_at,
        "safety": asdict(safety),
        "candidate_dispatched": False,
    }
    state["status"] = "NEXT_CYCLE"
    state["blocker"] = None
    state["root_blocker"] = root_blocker
    state["no_progress"] = {
        "count": 0,
        "threshold": 3,
        "terminal_hold": False,
        "reset_reason": "HOLD_RELEASED_AFTER_SAFETY_RECONCILIATION",
        "root_blocker": root_blocker,
        "last_observed_at": released_at,
    }
