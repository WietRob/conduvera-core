#!/usr/bin/env python3
"""Backend-neutral external execution runtime for Hermes Buildroom.

This module provides process lifecycle, request/run schemas, telemetry parsing,
and retry lineage for external CLI execution backends. It deliberately does not
activate any ProjectPack routing. The Buildroom control plane remains the only
state, scope, review, and merge authority.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from buildroom_backend_policy import BackendPolicyError, require_backend_enabled

SUPPORTED_SCHEMAS = {"execution-request-v1"}
SUPPORTED_ROLES = {"BUILDER", "REVIEWER"}
SUPPORTED_BACKENDS = {"native", "codex_cli", "opencode_cli"}
MAX_TIMEOUT_SECONDS = 6 * 60 * 60
MAX_ATTEMPTS = 5
RAW_EVENT_MAX_BYTES = 2_000_000


class ExecutionRuntimeError(ValueError):
    """Raised when an execution request/run violates runtime policy."""


class ExecutionStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    OBSERVATION_MISMATCH = "OBSERVATION_MISMATCH"


@dataclass(frozen=True)
class BackendIdentity:
    role: str
    backend: str
    provider: str
    model: str

    @property
    def family(self) -> str:
        text = f"{self.backend}/{self.provider}/{self.model}".lower()
        if any(token in text for token in ("openai", "codex", "gpt-")):
            return "openai"
        if any(token in text for token in ("kimi", "moonshot")):
            return "kimi"
        if "deepseek" in text:
            return "deepseek"
        if any(token in text for token in ("zai", "z.ai", "glm")):
            return "zai"
        if "anthropic" in text or "claude" in text:
            return "anthropic"
        if self.backend == "native":
            return f"native:{self.provider}:{self.model}"
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class ExecutionRequest:
    schema: str
    run_id: str
    role: str
    backend: str
    provider: str
    model: str
    repo: str
    worktree: str
    base_commit: str
    branch: str
    prompt: str
    allowed_paths: tuple[str, ...]
    test_command: str
    output_path: str
    timeout_seconds: int
    max_attempts: int
    output_schema_path: str | None = None

    @classmethod
    def create(cls, **kwargs: Any) -> "ExecutionRequest":
        role = str(kwargs.get("role", "")).upper()
        if role not in SUPPORTED_ROLES:
            raise ExecutionRuntimeError(f"INVALID_ROLE: {role}")
        schema = str(kwargs.get("schema", "execution-request-v1"))
        run_id = str(kwargs.get("run_id") or f"run-{uuid.uuid4()}")
        allowed_paths = tuple(str(item) for item in kwargs.get("allowed_paths", ()) or ())
        return cls(
            schema=schema,
            run_id=run_id,
            role=role,
            backend=str(kwargs.get("backend", "")),
            provider=str(kwargs.get("provider", "")),
            model=str(kwargs.get("model", "")),
            repo=str(kwargs.get("repo", "")),
            worktree=str(Path(str(kwargs.get("worktree", ""))).expanduser()),
            base_commit=str(kwargs.get("base_commit", "")),
            branch=str(kwargs.get("branch", "")),
            prompt=str(kwargs.get("prompt", "")),
            allowed_paths=allowed_paths,
            test_command=str(kwargs.get("test_command", "")),
            output_path=str(Path(str(kwargs.get("output_path", ""))).expanduser()),
            timeout_seconds=int(kwargs.get("timeout_seconds", 0)),
            max_attempts=int(kwargs.get("max_attempts", 0)),
            output_schema_path=str(Path(str(kwargs["output_schema_path"])).expanduser())
            if kwargs.get("output_schema_path") is not None
            else None,
        )


@dataclass
class RetryRecord:
    parent_run_id: str
    attempt: int
    original_failure_class: str
    prompt_changed: bool
    backend_changed: bool
    policy_reason: str
    independence_revalidated: bool = True


@dataclass
class ExecutionRun:
    schema: str = "execution-run-v1"
    run_id: str = ""
    parent_run_id: str | None = None
    attempt: int = 1
    role: str = ""
    backend: str = ""
    provider: str = ""
    model: str = ""
    backend_version: str = "unknown"
    pid: int | None = None
    process_group_id: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    status: ExecutionStatus = ExecutionStatus.CREATED
    exit_code: int | None = None
    termination_reason: str | None = None
    raw_event_path: str | None = None
    evidence_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=lambda: {"amount": None, "currency": None, "source": "unknown"})
    retry_lineage: list[dict[str, Any]] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    def default(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return str(value)
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=default), encoding="utf-8")
    tmp.replace(path)


def execution_request_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "execution-request-v1",
        "type": "object",
        "required": [
            "schema", "run_id", "role", "backend", "provider", "model", "repo", "worktree",
            "base_commit", "branch", "prompt", "allowed_paths", "test_command", "output_path",
            "timeout_seconds", "max_attempts",
        ],
        "properties": {
            "schema": {"const": "execution-request-v1"},
            "role": {"enum": sorted(SUPPORTED_ROLES)},
            "backend": {"enum": sorted(SUPPORTED_BACKENDS)},
        },
    }


def execution_run_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "execution-run-v1",
        "type": "object",
        "properties": {
            "schema": {"const": "execution-run-v1"},
            "status": {"enum": [status.value for status in ExecutionStatus]},
        },
    }


def execution_evidence_v2_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "execution-evidence-v2",
        "type": "object",
        "properties": {"schema": {"const": "execution-evidence-v2"}},
    }


def validate_backend_independence(builder: BackendIdentity, reviewer: BackendIdentity, *, owner_approved: bool = False) -> None:
    if builder.role.upper() != "BUILDER" or reviewer.role.upper() != "REVIEWER":
        raise ExecutionRuntimeError("INVALID_INDEPENDENCE_ROLE_PAIR")
    if builder.family == reviewer.family and not owner_approved:
        raise ExecutionRuntimeError("BUILDER_REVIEWER_NOT_INDEPENDENT")


def validate_request(request: ExecutionRequest) -> ExecutionRequest:
    if request.schema not in SUPPORTED_SCHEMAS:
        raise ExecutionRuntimeError(f"UNSUPPORTED_REQUEST_SCHEMA: {request.schema}")
    if request.role not in SUPPORTED_ROLES:
        raise ExecutionRuntimeError(f"INVALID_ROLE: {request.role}")
    if request.backend not in SUPPORTED_BACKENDS:
        raise ExecutionRuntimeError(f"UNKNOWN_BACKEND: {request.backend}")
    try:
        require_backend_enabled(request.backend)
    except BackendPolicyError as exc:
        raise ExecutionRuntimeError(str(exc)) from exc
    if not request.provider.strip() or not request.model.strip():
        raise ExecutionRuntimeError("BACKEND_IDENTITY_REQUIRED")
    if request.timeout_seconds <= 0 or request.timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ExecutionRuntimeError("TIMEOUT_OUT_OF_BOUNDS")
    if request.max_attempts <= 0 or request.max_attempts > MAX_ATTEMPTS:
        raise ExecutionRuntimeError("ATTEMPTS_OUT_OF_BOUNDS")
    worktree = Path(request.worktree).expanduser().resolve()
    if not worktree.exists() or not worktree.is_dir():
        raise ExecutionRuntimeError("WORKTREE_NOT_FOUND")
    git_top = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if git_top.returncode != 0:
        raise ExecutionRuntimeError("WORKTREE_NOT_GIT_REPO")
    if Path(git_top.stdout.strip()).resolve() != worktree:
        raise ExecutionRuntimeError("WORKTREE_TOPLEVEL_MISMATCH")
    base = subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-e", f"{request.base_commit}^{{commit}}"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if base.returncode != 0:
        raise ExecutionRuntimeError("BASE_COMMIT_NOT_FOUND")
    branch = subprocess.run(
        ["git", "-C", str(worktree), "branch", "--show-current"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if branch.stdout.strip() != request.branch:
        raise ExecutionRuntimeError("BRANCH_MISMATCH")
    for rel in request.allowed_paths:
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ExecutionRuntimeError("ALLOWED_PATH_ESCAPE")
        resolved = (worktree / rel_path).resolve()
        try:
            resolved.relative_to(worktree)
        except ValueError as exc:
            raise ExecutionRuntimeError("ALLOWED_PATH_ESCAPE") from exc
    output = Path(request.output_path).expanduser().resolve()
    try:
        output.relative_to(worktree)
    except ValueError:
        pass
    else:
        raise ExecutionRuntimeError("OUTPUT_PATH_INSIDE_WORKTREE")
    return request


def command_for_request(request: ExecutionRequest, *, executable: str | None = None) -> list[str]:
    """Return argv only for an enabled backend.

    External adapter branches are dormant compatibility code and remain
    unreachable while canonical Owner policy disables them.
    """
    validate_request(request)
    if request.backend == "native":
        return []
    if request.backend == "codex_cli":
        argv = [
            executable or "codex", "exec",
            "--sandbox", "workspace-write",
            "--json",
            "--output-last-message", request.output_path,
            "-C", request.worktree,
        ]
        if request.output_schema_path:
            argv.extend(["--output-schema", request.output_schema_path])
        if request.model:
            argv.extend(["--model", request.model])
        argv.append(request.prompt)
        return argv
    if request.backend == "opencode_cli":
        agent = "plan" if request.role == "REVIEWER" else "build"
        return [
            executable or "opencode", "run",
            "--dir", request.worktree,
            "--agent", agent,
            "--format", "json",
            "--model", request.model,
            request.prompt,
        ]
    raise ExecutionRuntimeError(f"UNKNOWN_BACKEND: {request.backend}")


def _write_raw_events(path: Path, stdout: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = stdout.encode("utf-8")[:RAW_EVENT_MAX_BYTES]
    path.write_bytes(data)


def _terminate_process_group(proc: subprocess.Popen[str], *, grace_seconds: float) -> str:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return "process_exited"
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "process_exited"
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return "terminated"
        time.sleep(0.02)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


def run_execution(
    request: ExecutionRequest,
    *,
    artifacts_dir: str | Path,
    parent_run_id: str | None = None,
    attempt: int = 1,
    retry_lineage: list[dict[str, Any]] | None = None,
    cancel_after_seconds: float | None = None,
    kill_grace_seconds: float = 5.0,
) -> ExecutionRun:
    """Execute an enabled backend without caller-supplied argv overrides."""
    return _run_execution_impl(
        request,
        command=None,
        artifacts_dir=artifacts_dir,
        parent_run_id=parent_run_id,
        attempt=attempt,
        retry_lineage=retry_lineage,
        cancel_after_seconds=cancel_after_seconds,
        kill_grace_seconds=kill_grace_seconds,
    )


def _run_execution_for_test(
    request: ExecutionRequest,
    *,
    command: list[str],
    artifacts_dir: str | Path,
    parent_run_id: str | None = None,
    attempt: int = 1,
    retry_lineage: list[dict[str, Any]] | None = None,
    cancel_after_seconds: float | None = None,
    kill_grace_seconds: float = 5.0,
) -> ExecutionRun:
    """Private lifecycle-test seam; only the active Python executable is allowed."""
    if command:
        executable = Path(command[0]).expanduser().resolve()
        for backend, binary in (("codex_cli", "codex"), ("opencode_cli", "opencode")):
            if executable.name.lower() == binary:
                raise ExecutionRuntimeError(f"BACKEND_DISABLED_BY_OWNER:{backend}")
        if executable != Path(sys.executable).resolve():
            raise ExecutionRuntimeError("TEST_COMMAND_EXECUTABLE_FORBIDDEN")
    return _run_execution_impl(
        request,
        command=command,
        artifacts_dir=artifacts_dir,
        parent_run_id=parent_run_id,
        attempt=attempt,
        retry_lineage=retry_lineage,
        cancel_after_seconds=cancel_after_seconds,
        kill_grace_seconds=kill_grace_seconds,
    )


def _run_execution_impl(
    request: ExecutionRequest,
    *,
    command: list[str] | None = None,
    artifacts_dir: str | Path,
    parent_run_id: str | None = None,
    attempt: int = 1,
    retry_lineage: list[dict[str, Any]] | None = None,
    cancel_after_seconds: float | None = None,
    kill_grace_seconds: float = 5.0,
) -> ExecutionRun:
    validate_request(request)
    artifacts = Path(artifacts_dir).expanduser().resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    run = ExecutionRun(
        run_id=request.run_id,
        parent_run_id=parent_run_id,
        attempt=attempt,
        role=request.role,
        backend=request.backend,
        provider=request.provider,
        model=request.model,
        status=ExecutionStatus.VALIDATED,
        evidence_path=request.output_path,
        retry_lineage=retry_lineage or [],
    )
    run_json = artifacts / f"{request.run_id}.run.json"
    run.stdout_path = str(artifacts / f"{request.run_id}.stdout.txt")
    run.stderr_path = str(artifacts / f"{request.run_id}.stderr.txt")
    run.raw_event_path = str(artifacts / f"{request.run_id}.events.jsonl")
    _atomic_write_json(run_json, asdict(run))

    argv = command if command is not None else command_for_request(request)
    if request.backend == "native" and not argv:
        run.status = ExecutionStatus.SUCCEEDED
        run.started_at = run.ended_at = _utc_now()
        run.duration_ms = 0
        run.exit_code = 0
        _atomic_write_json(run_json, asdict(run))
        return run

    run.status = ExecutionStatus.STARTING
    _atomic_write_json(run_json, asdict(run))
    start = time.monotonic()
    run.started_at = _utc_now()
    proc = subprocess.Popen(
        argv,
        cwd=request.worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    run.pid = proc.pid
    try:
        run.process_group_id = os.getpgid(proc.pid)
    except ProcessLookupError:
        run.process_group_id = None
    run.status = ExecutionStatus.RUNNING
    _atomic_write_json(run_json, asdict(run))

    stdout = ""
    stderr = ""
    try:
        wait_window = cancel_after_seconds if cancel_after_seconds is not None else request.timeout_seconds
        stdout, stderr = proc.communicate(timeout=wait_window)
        if cancel_after_seconds is not None:
            # Process ended before the requested cancellation time.
            pass
    except subprocess.TimeoutExpired:
        if cancel_after_seconds is not None:
            run.termination_reason = _terminate_process_group(proc, grace_seconds=kill_grace_seconds)
            run.status = ExecutionStatus.CANCELLED
        else:
            run.termination_reason = _terminate_process_group(proc, grace_seconds=kill_grace_seconds)
            run.status = ExecutionStatus.TIMED_OUT
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
    finally:
        end = time.monotonic()
        run.ended_at = _utc_now()
        run.duration_ms = int((end - start) * 1000)
        run.exit_code = proc.returncode

    Path(run.stdout_path).write_text(stdout, encoding="utf-8")
    Path(run.stderr_path).write_text(stderr, encoding="utf-8")
    _write_raw_events(Path(run.raw_event_path), stdout)

    if run.status == ExecutionStatus.RUNNING:
        if proc.returncode == 0:
            run.status = ExecutionStatus.SUCCEEDED
        else:
            run.status = ExecutionStatus.FAILED
            run.termination_reason = "nonzero_exit"
    if request.backend == "codex_cli":
        parsed = parse_codex_events(Path(run.raw_event_path))
    elif request.backend == "opencode_cli":
        parsed = parse_opencode_events(Path(run.raw_event_path))
    else:
        parsed = {"usage": {}}
    run.usage = parsed.get("usage", {})
    run.cost = calculate_cost(run.usage, price_config=None, backend_reported_cost=parsed.get("backend_cost"))
    _atomic_write_json(run_json, asdict(run))
    return run


def _load_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _usage_from_mapping(data: dict[str, Any]) -> dict[str, int]:
    input_tokens = data.get("input_tokens", data.get("input", data.get("prompt_tokens")))
    output_tokens = data.get("output_tokens", data.get("output", data.get("completion_tokens")))
    cached_tokens = data.get("cached_tokens", data.get("cache_read_tokens"))
    reasoning_tokens = data.get("reasoning_tokens")
    usage: dict[str, int] = {}
    for key, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
        ("cached_tokens", cached_tokens),
        ("reasoning_tokens", reasoning_tokens),
    ):
        if isinstance(value, int):
            usage[key] = value
    if usage:
        usage["total_tokens"] = sum(usage.values())
    return usage


def parse_codex_events(path: Path) -> dict[str, Any]:
    records = _load_json_lines(path)
    usage: dict[str, int] = {}
    session_id = None
    tool_calls = 0
    for record in records:
        if record.get("type") == "session" and record.get("id"):
            session_id = str(record["id"])
        if record.get("type") in {"tool_call", "exec_command", "apply_patch"}:
            tool_calls += 1
        candidate = record.get("usage") if isinstance(record.get("usage"), dict) else record
        parsed_usage = _usage_from_mapping(candidate)
        if parsed_usage:
            usage = parsed_usage
    return {"events": len(records), "tool_calls": tool_calls, "session_id": session_id, "usage": usage}


def parse_opencode_events(path: Path) -> dict[str, Any]:
    records = _load_json_lines(path)
    usage: dict[str, int] = {}
    session_id = None
    tool_calls = 0
    for record in records:
        props = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        info = props.get("info") if isinstance(props.get("info"), dict) else {}
        if info.get("id"):
            session_id = str(info["id"])
        if "tool" in str(record.get("type", "")).lower():
            tool_calls += 1
        raw_usage = None
        if isinstance(props.get("usage"), dict):
            raw_usage = props["usage"]
        elif isinstance(record.get("usage"), dict):
            raw_usage = record["usage"]
        if raw_usage:
            parsed_usage = _usage_from_mapping(raw_usage)
            if parsed_usage:
                usage = parsed_usage
    return {"events": len(records), "tool_calls": tool_calls, "session_id": session_id, "usage": usage}


def calculate_cost(
    usage: dict[str, Any],
    *,
    price_config: dict[str, Any] | None,
    backend_reported_cost: dict[str, Any] | None,
) -> dict[str, Any]:
    if backend_reported_cost and backend_reported_cost.get("amount") is not None and backend_reported_cost.get("currency"):
        return {
            "amount": backend_reported_cost["amount"],
            "currency": backend_reported_cost["currency"],
            "source": backend_reported_cost.get("source", "backend"),
        }
    if not price_config:
        return {"amount": None, "currency": None, "source": "unknown"}
    currency = price_config.get("currency")
    source = price_config.get("source")
    input_price = price_config.get("input_per_million")
    output_price = price_config.get("output_per_million")
    if not currency or not source or input_price is None or output_price is None:
        return {"amount": None, "currency": None, "source": "unknown"}
    amount = ((usage.get("input_tokens", 0) * input_price) + (usage.get("output_tokens", 0) * output_price)) / 1_000_000
    return {"amount": amount, "currency": currency, "source": source}


def record_retry_lineage(
    request: ExecutionRequest,
    *,
    parent_run: ExecutionRun,
    failure_class: str,
    prompt_changed: bool = False,
    backend_changed: bool = False,
    policy_reason: str = "",
) -> ExecutionRun:
    next_attempt = parent_run.attempt + 1
    if next_attempt > request.max_attempts:
        raise ExecutionRuntimeError("RETRY_BUDGET_EXHAUSTED")
    if failure_class in {"security_policy_violation", "scope_expansion", "quality_failure"}:
        raise ExecutionRuntimeError("RETRY_NOT_ALLOWED")
    record = RetryRecord(
        parent_run_id=parent_run.run_id,
        attempt=next_attempt,
        original_failure_class=failure_class,
        prompt_changed=prompt_changed,
        backend_changed=backend_changed,
        policy_reason=policy_reason,
    )
    return ExecutionRun(
        run_id=f"run-{uuid.uuid4()}",
        parent_run_id=parent_run.run_id,
        attempt=next_attempt,
        role=request.role,
        backend=request.backend,
        provider=request.provider,
        model=request.model,
        status=ExecutionStatus.CREATED,
        retry_lineage=[*parent_run.retry_lineage, asdict(record)],
    )


def validate_execution_evidence_v2(
    evidence: dict[str, Any],
    *,
    run: ExecutionRun,
    expected_request: ExecutionRequest,
    observation: dict[str, Any],
) -> dict[str, Any]:
    required = [
        "schema", "v1", "run_id", "request_schema", "run_schema", "attempt", "retry_lineage",
        "backend_process_status", "raw_event_path", "timeout", "cancelled", "usage", "cost",
        "validation_result", "independent_observation",
    ]
    missing = [field for field in required if field not in evidence]
    if missing:
        raise ExecutionRuntimeError(f"MISSING_EVIDENCE_FIELD: {', '.join(missing)}")
    if evidence["schema"] != "execution-evidence-v2":
        raise ExecutionRuntimeError("INVALID_EVIDENCE_SCHEMA")
    if evidence["run_id"] != run.run_id or evidence["request_schema"] != expected_request.schema:
        raise ExecutionRuntimeError("EVIDENCE_RUN_MISMATCH")
    if evidence["backend_process_status"] != run.status.value:
        raise ExecutionRuntimeError("EVIDENCE_PROCESS_STATUS_MISMATCH")
    observed = evidence.get("independent_observation") or {}
    if observed.get("tests_exit_code") != 0 or observation.get("tests_exit_code") != 0:
        raise ExecutionRuntimeError("OBSERVATION_MISMATCH")
    return evidence
