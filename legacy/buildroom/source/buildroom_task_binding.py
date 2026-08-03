#!/usr/bin/env python3
"""Canonical Buildroom task-to-Kanban-board bindings.

Current-schema operations never consult the process-global current board. Legacy
state may be read only when it carries both the historical task ID and board.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, MutableMapping, Sequence
import re

_TASK_ID_RE = re.compile(r"^t_[a-f0-9]+$")
_BOARD_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PHASE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TASK_OPERATIONS = {
    "show",
    "runs",
    "log",
    "context",
    "complete",
    "block",
    "unblock",
    "archive",
    "comment",
}
_BOARD_OPERATIONS = {"create", "dispatch"}


@dataclass(frozen=True)
class TaskBinding:
    task_id: str
    board: str
    phase: str
    cycle: int
    created_at: str
    evidence_path: str | None = None
    dispatched_head: str | None = None
    repo: str | None = None
    default_branch: str | None = None

    def __post_init__(self) -> None:
        if not _TASK_ID_RE.fullmatch(self.task_id):
            raise ValueError("KANBAN_TASK_ID_INVALID")
        if not _BOARD_RE.fullmatch(self.board):
            raise ValueError("KANBAN_BOARD_INVALID")
        if not _PHASE_RE.fullmatch(self.phase):
            raise ValueError("BUILDROOM_PHASE_INVALID")
        if self.cycle < 1:
            raise ValueError("BUILDROOM_CYCLE_INVALID")
        if not self.created_at:
            raise ValueError("TASK_BINDING_CREATED_AT_REQUIRED")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value for key, value in asdict(self).items()
            if value not in (None, "")
        }


def store_task_binding(state: MutableMapping[str, Any], binding: TaskBinding) -> None:
    bindings = state.setdefault("task_bindings", {})
    if not isinstance(bindings, dict):
        raise ValueError("TASK_BINDINGS_INVALID")
    bindings[binding.phase] = binding.to_dict()


def binding_for_phase(
    state: MutableMapping[str, Any], phase: str, *, allow_legacy: bool = True
) -> TaskBinding | None:
    raw = state.get("task_bindings", {}).get(phase)
    if raw is not None:
        if not isinstance(raw, dict):
            raise ValueError("TASK_BINDING_INVALID")
        return TaskBinding(
            task_id=str(raw.get("task_id", "")),
            board=str(raw.get("board", "")),
            phase=str(raw.get("phase", phase)),
            cycle=int(raw.get("cycle", state.get("cycle", 0))),
            created_at=str(raw.get("created_at", "")),
            evidence_path=str(raw.get("evidence_path") or "") or None,
            dispatched_head=str(raw.get("dispatched_head") or "") or None,
            repo=str(raw.get("repo") or "") or None,
            default_branch=str(raw.get("default_branch") or "") or None,
        )
    if not allow_legacy:
        return None
    task_id = state.get("task_ids", {}).get(phase)
    if not task_id:
        return None
    board = state.get("task_boards", {}).get(phase)
    if not board:
        raise ValueError(f"TASK_BOARD_REQUIRED:{phase}:{task_id}")
    return TaskBinding(
        task_id=str(task_id),
        board=str(board),
        phase=phase,
        cycle=int(state.get("cycle", 1)),
        created_at=str(state.get("last_run") or "legacy-state-binding"),
    )


def clear_task_binding(state: MutableMapping[str, Any], phase: str) -> TaskBinding | None:
    binding = binding_for_phase(state, phase)
    bindings = state.get("task_bindings")
    if isinstance(bindings, dict):
        bindings.pop(phase, None)
    # Remove migrated legacy mirrors so current state cannot become ambiguous.
    for key in ("task_ids", "task_boards"):
        mapping = state.get(key)
        if isinstance(mapping, dict):
            mapping.pop(phase, None)
    return binding


def kanban_argv(
    operation: str,
    binding: TaskBinding | None = None,
    *,
    board: str | None = None,
    extra: Sequence[str] = (),
) -> list[str]:
    if operation in _TASK_OPERATIONS:
        if binding is None:
            raise ValueError(f"TASK_BINDING_REQUIRED:{operation}")
        selected_board = binding.board
    elif operation in _BOARD_OPERATIONS:
        if not board:
            raise ValueError(f"KANBAN_BOARD_REQUIRED:{operation}")
        selected_board = board
    else:
        raise ValueError(f"KANBAN_OPERATION_UNSUPPORTED:{operation}")
    if not _BOARD_RE.fullmatch(selected_board):
        raise ValueError("KANBAN_BOARD_INVALID")
    argv = ["hermes", "kanban", "--board", selected_board, operation]
    if operation in _TASK_OPERATIONS:
        argv.append(binding.task_id)  # type: ignore[union-attr]
    argv.extend(str(item) for item in extra)
    return argv
