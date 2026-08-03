#!/usr/bin/env python3
"""Structured Kanban terminal truth and exact task-bound evidence validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class TaskTerminalState(str, Enum):
    SUCCESS_TERMINAL = "SUCCESS_TERMINAL"
    FAILURE_TERMINAL = "FAILURE_TERMINAL"
    PENDING = "PENDING"
    INCONSISTENT = "INCONSISTENT"
    MISSING = "MISSING"


_SUCCESS = frozenset({"done", "completed"})
_FAILURE = frozenset({"blocked", "gave_up", "crashed", "failed"})
_PENDING = frozenset({"todo", "ready", "running", "waiting"})
_ALLOWED_REVIEWER_VERDICTS = frozenset(
    {"APPROVE_MERGE", "REQUEST_FIX", "BLOCK", "HOLD_FOR_BOSS"}
)


@dataclass(frozen=True)
class TaskCheckResult:
    state: TaskTerminalState
    kanban_status: str
    raw: str = ""

    def __iter__(self):
        """Compatibility for legacy diagnostics; completion uses ``state``."""
        yield self.kanban_status
        yield self.raw


@dataclass(frozen=True)
class PhaseEvidenceExpectation:
    task_id: str
    board: str
    cycle: int
    phase: str
    role: str
    repo: str
    git_head: str
    git_base: str | None
    reviewer_verdict_required: bool = False


@dataclass(frozen=True)
class PhaseCompletionResult:
    complete: bool
    reason: str
    task_state: TaskTerminalState
    evidence: dict[str, Any] | None = None


def classify_kanban_status(status: str | None) -> TaskTerminalState:
    normalized = str(status or "").strip().lower()
    if normalized in _SUCCESS:
        return TaskTerminalState.SUCCESS_TERMINAL
    if normalized in _FAILURE:
        return TaskTerminalState.FAILURE_TERMINAL
    if normalized in _PENDING:
        return TaskTerminalState.PENDING
    if normalized in {"", "not_found", "missing"}:
        return TaskTerminalState.MISSING
    return TaskTerminalState.INCONSISTENT


def parse_kanban_show(*, ok: bool, output: str) -> TaskCheckResult:
    if not ok or not output.strip():
        return TaskCheckResult(TaskTerminalState.MISSING, "not_found", output)
    match = re.search(r"(?im)^\s*status:\s*([a-z_]+)\s*$", output)
    if not match:
        return TaskCheckResult(TaskTerminalState.INCONSISTENT, "unknown", output)
    status = match.group(1).lower()
    return TaskCheckResult(classify_kanban_status(status), status, output)


def _extract_binding_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    records: list[dict[str, Any]] = []
    for raw in candidates:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("schema") == "buildroom-task-evidence-v1":
            records.append(value)
    if len(records) != 1:
        raise ValueError(f"RECORD_COUNT_{len(records)}")
    return records[0]


def load_task_evidence(path: Path) -> dict[str, Any]:
    """Load the single task-binding record from an exact evidence path."""
    return _extract_task_evidence(path)


def validate_task_evidence(
    path: Path, expected: PhaseEvidenceExpectation
) -> dict[str, Any]:
    try:
        record = _extract_binding_record(path)
    except (OSError, ValueError) as exc:
        token = str(exc) if isinstance(exc, ValueError) else "READ_FAILED"
        raise ValueError(token) from exc
    required = {
        "schema", "task_id", "board", "cycle", "phase", "role", "repo",
        "git_head", "git_base", "verdict", "result",
    }
    if set(record) != required:
        raise ValueError("SCHEMA_FIELDS")
    comparisons = (
        ("task_id", expected.task_id, "TASK_ID_MISMATCH"),
        ("board", expected.board, "BOARD_MISMATCH"),
        ("cycle", expected.cycle, "CYCLE_MISMATCH"),
        ("phase", expected.phase, "PHASE_MISMATCH"),
        ("role", expected.role, "ROLE_MISMATCH"),
        ("repo", expected.repo, "REPO_MISMATCH"),
        ("git_head", expected.git_head, "GIT_HEAD_MISMATCH"),
        ("git_base", expected.git_base, "GIT_BASE_MISMATCH"),
    )
    for field, wanted, token in comparisons:
        if record.get(field) != wanted:
            raise ValueError(token)
    if record.get("result") != "COMPLETE":
        raise ValueError("RESULT_NOT_COMPLETE")
    if expected.reviewer_verdict_required:
        verdict = str(record.get("verdict") or "").strip()
        if not verdict:
            raise ValueError("REVIEWER_VERDICT_REQUIRED")
        if verdict not in _ALLOWED_REVIEWER_VERDICTS:
            raise ValueError("REVIEWER_VERDICT_INVALID")
    return record


def evaluate_phase_completion(
    kanban_status: str,
    evidence_path: Path,
    expected: PhaseEvidenceExpectation,
) -> PhaseCompletionResult:
    state = classify_kanban_status(kanban_status)
    evidence_exists = evidence_path.is_file()
    if state is TaskTerminalState.FAILURE_TERMINAL:
        return PhaseCompletionResult(False, f"TASK_TERMINAL_FAILURE:{kanban_status}", state)
    if state is TaskTerminalState.PENDING:
        reason = "EVIDENCE_BEFORE_TASK_SUCCESS" if evidence_exists else "TASK_PENDING"
        return PhaseCompletionResult(False, reason, state)
    if state in (TaskTerminalState.INCONSISTENT, TaskTerminalState.MISSING):
        reason = "TASK_MISSING" if state is TaskTerminalState.MISSING else "TASK_STATE_INCONSISTENT"
        return PhaseCompletionResult(False, reason, state)
    if not evidence_exists:
        return PhaseCompletionResult(False, "TASK_DONE_BUT_NO_EVIDENCE", state)
    try:
        record = validate_task_evidence(evidence_path, expected)
    except ValueError as exc:
        return PhaseCompletionResult(False, f"TASK_EVIDENCE_INVALID:{exc}", state)
    return PhaseCompletionResult(True, "PHASE_COMPLETE", state, record)
