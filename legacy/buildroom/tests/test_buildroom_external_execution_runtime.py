"""Dormant compatibility and native lifecycle tests for Buildroom execution adapters."""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from buildroom_core import ProjectPack
from buildroom_execution import (
    _run_execution_for_test,
    BackendIdentity,
    ExecutionRequest,
    ExecutionRuntimeError,
    ExecutionStatus,
    calculate_cost,
    command_for_request,
    execution_evidence_v2_schema,
    execution_request_schema,
    execution_run_schema,
    parse_codex_events,
    parse_opencode_events,
    record_retry_lineage,

    validate_backend_independence,
    validate_execution_evidence_v2,
    validate_request,
)


def init_repo(path: Path, branch: str = "task/branch") -> str:
    path.mkdir(parents=True, exist_ok=True)
    if (path / ".git").exists():
        shutil.rmtree(path / ".git")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=path, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def request_for(tmp_path: Path, **overrides) -> ExecutionRequest:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    data = {
        "role": "BUILDER",
        "backend": "native",
        "provider": "openai-codex",
        "model": "gpt-5.6-sol",
        "repo": "Owner/repo",
        "worktree": str(repo),
        "base_commit": base,
        "branch": "task/branch",
        "prompt": "Return structured evidence only.",
        "allowed_paths": ["README.md", "src"],
        "test_command": "python -c 'print(1)'",
        "output_path": str(tmp_path / "evidence" / "output.json"),
        "timeout_seconds": 5,
        "max_attempts": 2,
    }
    data.update(overrides)
    return ExecutionRequest.create(**data)


def fake_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / f"fake_{len(list(tmp_path.glob('fake_*')))}.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_schemas_are_versioned() -> None:
    assert execution_request_schema()["properties"]["schema"]["const"] == "execution-request-v1"
    assert execution_run_schema()["properties"]["schema"]["const"] == "execution-run-v1"
    assert execution_evidence_v2_schema()["properties"]["schema"]["const"] == "execution-evidence-v2"


def test_unknown_backend_rejected(tmp_path: Path) -> None:
    req = request_for(tmp_path, backend="mystery")
    with pytest.raises(ExecutionRuntimeError, match="UNKNOWN_BACKEND"):
        validate_request(req)


def test_invalid_role_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExecutionRuntimeError, match="INVALID_ROLE"):
        request_for(tmp_path, role="MERGE")


def test_worktree_path_escape_rejected(tmp_path: Path) -> None:
    req = request_for(tmp_path, worktree=str(tmp_path / "missing" / ".." / "outside"))
    with pytest.raises(ExecutionRuntimeError, match="WORKTREE_NOT_FOUND"):
        validate_request(req)


def test_allowed_path_escape_rejected(tmp_path: Path) -> None:
    req = request_for(tmp_path, allowed_paths=["../secret.txt"])
    with pytest.raises(ExecutionRuntimeError, match="ALLOWED_PATH_ESCAPE"):
        validate_request(req)


def test_branch_and_base_mismatch_rejected(tmp_path: Path) -> None:
    req = request_for(tmp_path, branch="other")
    with pytest.raises(ExecutionRuntimeError, match="BRANCH_MISMATCH"):
        validate_request(req)
    req = request_for(tmp_path, base_commit="deadbeef")
    with pytest.raises(ExecutionRuntimeError, match="BASE_COMMIT_NOT_FOUND"):
        validate_request(req)


def test_codex_command_uses_argument_array_and_assigned_directory(tmp_path: Path) -> None:
    req = request_for(tmp_path, backend="codex_cli", model="gpt-5.5")
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        command_for_request(req, executable="codex")


def test_opencode_command_uses_argument_array_and_assigned_directory(tmp_path: Path) -> None:
    req = request_for(
        tmp_path,
        role="REVIEWER",
        backend="opencode_cli",
        provider="kimi-for-coding",
        model="kimi-k2.6",
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:opencode_cli$"):
        command_for_request(req, executable="opencode")


def test_runner_captures_stdout_stderr_and_events(tmp_path: Path) -> None:
    req = request_for(tmp_path, backend="native")
    script = fake_script(
        tmp_path,
        "import sys, json\nprint(json.dumps({'type':'session','id':'s1'}))\nprint('err-line', file=sys.stderr)\n",
    )
    run = _run_execution_for_test(req, command=[sys.executable, str(script)], artifacts_dir=tmp_path / "artifacts")
    assert run.status == ExecutionStatus.SUCCEEDED
    assert run.exit_code == 0
    assert Path(run.stdout_path).read_text(encoding="utf-8").strip()
    assert "err-line" in Path(run.stderr_path).read_text(encoding="utf-8")
    assert Path(run.raw_event_path).exists()


def test_nonzero_exit_reaches_failed(tmp_path: Path) -> None:
    req = request_for(tmp_path)
    script = fake_script(tmp_path, "import sys\nprint('bad')\nsys.exit(7)\n")
    run = _run_execution_for_test(req, command=[sys.executable, str(script)], artifacts_dir=tmp_path / "artifacts")
    assert run.status == ExecutionStatus.FAILED
    assert run.exit_code == 7
    assert run.termination_reason == "nonzero_exit"


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_timeout_kills_complete_process_group_and_children(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    req = request_for(tmp_path, timeout_seconds=1)
    script = fake_script(
        tmp_path,
        f"""
import pathlib, subprocess, sys, time
p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
pathlib.Path({str(child_pid_file)!r}).write_text(str(p.pid))
time.sleep(30)
""",
    )
    run = _run_execution_for_test(
        req,
        command=[sys.executable, str(script)],
        artifacts_dir=tmp_path / "artifacts",
        kill_grace_seconds=0.2,
    )
    assert run.status == ExecutionStatus.TIMED_OUT
    child_pid = int(child_pid_file.read_text())
    time.sleep(0.2)
    assert not _process_alive(child_pid)


def test_cancellation_kills_complete_process_group_and_children(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    req = request_for(tmp_path, timeout_seconds=20)
    script = fake_script(
        tmp_path,
        f"""
import pathlib, subprocess, sys, time
p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
pathlib.Path({str(child_pid_file)!r}).write_text(str(p.pid))
time.sleep(30)
""",
    )
    run = _run_execution_for_test(
        req,
        command=[sys.executable, str(script)],
        artifacts_dir=tmp_path / "artifacts",
        cancel_after_seconds=0.4,
        kill_grace_seconds=0.2,
    )
    assert run.status == ExecutionStatus.CANCELLED
    child_pid = int(child_pid_file.read_text())
    time.sleep(0.2)
    assert not _process_alive(child_pid)


def test_retry_lineage_is_preserved_and_budget_enforced(tmp_path: Path) -> None:
    req = request_for(tmp_path, max_attempts=2)
    first = _run_execution_for_test(req, command=[sys.executable, "-c", "import sys; sys.exit(1)"], artifacts_dir=tmp_path / "a1")
    retry = record_retry_lineage(
        req,
        parent_run=first,
        failure_class="transient_provider_error",
        prompt_changed=False,
        backend_changed=False,
        policy_reason="configured bounded retry",
    )
    assert retry.parent_run_id == first.run_id
    assert retry.attempt == 2
    with pytest.raises(ExecutionRuntimeError, match="RETRY_BUDGET_EXHAUSTED"):
        record_retry_lineage(req, parent_run=retry, failure_class="timeout")


def test_missing_usage_and_cost_remain_unknown(tmp_path: Path) -> None:
    usage = parse_codex_events(tmp_path / "missing.jsonl")["usage"]
    assert usage == {}
    cost = calculate_cost(usage, price_config=None, backend_reported_cost=None)
    assert cost == {"amount": None, "currency": None, "source": "unknown"}


def test_event_parsers_capture_usage_when_backend_exposes_it(tmp_path: Path) -> None:
    codex_events = tmp_path / "codex.jsonl"
    codex_events.write_text(
        '{"type":"usage","input_tokens":3,"output_tokens":4,"cached_tokens":1,"reasoning_tokens":2}\n'
        '{"type":"session","id":"codex-session"}\n',
        encoding="utf-8",
    )
    parsed = parse_codex_events(codex_events)
    assert parsed["session_id"] == "codex-session"
    assert parsed["usage"]["total_tokens"] == 10

    opencode_events = tmp_path / "opencode.jsonl"
    opencode_events.write_text(
        '{"type":"session.updated","properties":{"info":{"id":"ses_1"}}}\n'
        '{"type":"message.part.updated","properties":{"usage":{"input":5,"output":6}}}\n',
        encoding="utf-8",
    )
    parsed = parse_opencode_events(opencode_events)
    assert parsed["session_id"] == "ses_1"
    assert parsed["usage"]["input_tokens"] == 5
    assert parsed["usage"]["output_tokens"] == 6


def test_malformed_structured_evidence_blocks_completion(tmp_path: Path) -> None:
    req = request_for(tmp_path)
    run = _run_execution_for_test(req, command=[sys.executable, "-c", "print('ok')"], artifacts_dir=tmp_path / "artifacts")
    evidence = {"schema": "execution-evidence-v2", "run_id": run.run_id}
    with pytest.raises(ExecutionRuntimeError, match="MISSING_EVIDENCE_FIELD"):
        validate_execution_evidence_v2(evidence, run=run, expected_request=req, observation={"tests_exit_code": 0})


def test_disk_test_mismatch_blocks_completion(tmp_path: Path) -> None:
    req = request_for(tmp_path)
    run = _run_execution_for_test(req, command=[sys.executable, "-c", "print('ok')"], artifacts_dir=tmp_path / "artifacts")
    evidence = {
        "schema": "execution-evidence-v2",
        "v1": {"schema": "execution-evidence-v1"},
        "run_id": run.run_id,
        "request_schema": "execution-request-v1",
        "run_schema": "execution-run-v1",
        "attempt": 1,
        "retry_lineage": [],
        "backend_process_status": "SUCCEEDED",
        "raw_event_path": run.raw_event_path,
        "timeout": False,
        "cancelled": False,
        "usage": {},
        "cost": {"amount": None, "currency": None, "source": "unknown"},
        "validation_result": "passed",
        "independent_observation": {"tests_exit_code": 1},
    }
    with pytest.raises(ExecutionRuntimeError, match="OBSERVATION_MISMATCH"):
        validate_execution_evidence_v2(evidence, run=run, expected_request=req, observation={"tests_exit_code": 1})


def test_builder_reviewer_identity_collision_rejected() -> None:
    builder = BackendIdentity(role="BUILDER", backend="codex_cli", provider="openai-codex", model="gpt-5.5")
    reviewer = BackendIdentity(role="REVIEWER", backend="opencode_cli", provider="openai", model="gpt-5.5")
    with pytest.raises(ExecutionRuntimeError, match="BUILDER_REVIEWER_NOT_INDEPENDENT"):
        validate_backend_independence(builder, reviewer)


def test_native_backend_behavior_remains_unchanged(tmp_path: Path) -> None:
    pack = ProjectPack.from_mapping(
        {
            "project_name": "native",
            "repo_path": str(tmp_path / "repo"),
            "evidence_dir": str(tmp_path / "ev"),
            "github_repo": "Owner/native",
            "autopilot_enabled": True,
            "delivery_mode": "full",
            "allowed_phases": ["BUILDER", "REVIEWER"],
            "profiles": {"builder": "builder", "reviewer": "reviewer"},
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )
    assert pack.backend_for("BUILDER") == "native"
    assert pack.backend_for("REVIEWER") == "native"


def test_projectpacks_remain_native_and_only_peekxd_is_autonomous() -> None:
    peekxd = ProjectPack.from_yaml(Path.home() / ".hermes/buildroom/projects/peekxd.yaml")
    curaops = ProjectPack.from_yaml(Path.home() / ".hermes/buildroom/projects/curaops-vrp.yaml")
    assert peekxd.builder_backend == "native"
    assert peekxd.reviewer_backend == "native"
    assert peekxd.autopilot_enabled is True
    assert curaops.autopilot_enabled is False
    assert curaops.delivery_mode == "engineering_finish_line"
    assert curaops.phase_allowed("BUILDER")
    assert curaops.phase_allowed("MERGE")
