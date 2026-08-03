#!/usr/bin/env python3
"""Exact-board Kanban artifact resolution for Buildroom reconciliation."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_TASK_ID_RE = re.compile(r"^t_[a-f0-9]+$")
_BOARD_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class AmbiguousTaskBoardError(RuntimeError):
    """A legacy task identifier exists on more than one Kanban board."""


def _validate(task_id: str, board: str | None = None) -> None:
    if not _TASK_ID_RE.fullmatch(task_id):
        raise ValueError("KANBAN_TASK_ID_INVALID")
    if board is not None and not _BOARD_RE.fullmatch(board):
        raise ValueError("KANBAN_BOARD_INVALID")


def _board_log_path(root: Path, task_id: str, board: str) -> Path:
    if board == "default":
        return root / "logs" / f"{task_id}.log"
    return root / "boards" / board / "logs" / f"{task_id}.log"


def resolve_task_log(home: str | Path, task_id: str, board: str) -> Path | None:
    """Resolve only the exact log path for a current-schema task binding."""
    _validate(task_id, board)
    root = Path(home).expanduser().resolve() / ".hermes/kanban"
    candidate = _board_log_path(root, task_id, board).resolve()
    return candidate if candidate.is_file() else None


def resolve_legacy_task_board(home: str | Path, task_id: str) -> str | None:
    """Find a legacy task's board, failing closed when candidates are ambiguous."""
    _validate(task_id)
    root = Path(home).expanduser().resolve() / ".hermes/kanban"
    candidates: list[str] = []
    if _board_log_path(root, task_id, "default").is_file():
        candidates.append("default")
    for path in sorted((root / "boards").glob(f"*/logs/{task_id}.log")):
        candidates.append(path.parent.parent.name)
    databases = [("default", root.parent / "kanban.db")]
    databases.extend(
        (path.parent.name, path) for path in (root / "boards").glob("*/kanban.db")
    )
    for board, database in databases:
        if not database.is_file():
            continue
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            found = connection.execute(
                "SELECT 1 FROM tasks WHERE id=? LIMIT 1", (task_id,)
            ).fetchone()
            connection.close()
            if found:
                candidates.append(board)
        except sqlite3.Error:
            continue
    unique = sorted(set(candidates))
    if len(unique) > 1:
        raise AmbiguousTaskBoardError(
            f"AMBIGUOUS_TASK_BOARD:{task_id}:{','.join(unique)}"
        )
    return unique[0] if unique else None


def resolve_legacy_task_log(home: str | Path, task_id: str) -> Path | None:
    board = resolve_legacy_task_board(home, task_id)
    return resolve_task_log(home, task_id, board) if board else None
