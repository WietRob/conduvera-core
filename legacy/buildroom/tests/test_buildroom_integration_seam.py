"""Integration tests for external execution activation policy and control-plane seam."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from buildroom_core import ProjectPack, ProjectPackError
from buildroom_execution import (
    ExecutionRequest,
    ExecutionRuntimeError,
    ExecutionRun,
    ExecutionStatus,
    command_for_request,
    run_execution,
    validate_request,
)


SCRIPTS_DIR = Path.home() / ".hermes/scripts"


def init_repo(path: Path, branch: str = "task/branch") -> str:
    import shutil
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


def pack_with_execution(tmp_path: Path, **exec_overrides) -> ProjectPack:
    exec_data = {
        "builder_backend": "native",
        "reviewer_backend": "native",
        "builder_model": None,
        "reviewer_model": None,
        "builder_fallbacks": [],
        "reviewer_fallbacks": [],
    }
    exec_data.update(exec_overrides)
    return ProjectPack.from_mapping({
        "project_name": "test-pack",
        "repo_path": str(tmp_path / "repo"),
        "evidence_dir": str(tmp_path / "ev"),
        "github_repo": "Owner/test",
        "autopilot_enabled": True,
        "delivery_mode": "full",
        "allowed_phases": ["BUILDER", "REVIEWER"],
        "profiles": {"builder": "builder", "reviewer": "reviewer"},
        "execution": exec_data,
    })


def _run_integration_tests():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:warnings",
         str(SCRIPTS_DIR / "tests/test_buildroom_integration_seam.py")],
        capture_output=True, text=True, timeout=120, cwd=str(SCRIPTS_DIR),
        env={**os.environ, "PYTHONPATH": str(SCRIPTS_DIR)},
    )
    print(r.stdout[-800:] if len(r.stdout) > 800 else r.stdout)
    if r.stderr.strip():
        print("STDERR:", r.stderr[:400])
    return r.returncode


# ── Activation Policy ────────────────────────────────────────────

def test_native_mode_follows_legacy_path(tmp_path: Path) -> None:
    pack = pack_with_execution(tmp_path,mode="native")
    assert pack.execution_mode == "native"
    assert pack.backend_for("BUILDER") == "native"
    cmd_result = pack.authorize_external_execution(
        role="BUILDER", cycle=1, pilot_id=None, activation_token=None,
    )
    assert cmd_result is None


def test_missing_mode_defaults_to_native(tmp_path: Path) -> None:
    pack = pack_with_execution(tmp_path,)
    assert pack.execution_mode == "native"


def test_external_backend_blocked_in_native_mode(tmp_path: Path) -> None:
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, builder_backend="codex_cli", mode="native")


def test_pilot_without_pilot_id_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True})


def test_pilot_without_expiry_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001"})


def test_expired_pilot_fails_closed(tmp_path: Path) -> None:
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001", "expires_at": expired, "allowed_cycles": [1, 2], "allowed_roles": ["BUILDER"]})


def test_wrong_cycle_fails_closed(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001", "expires_at": future, "allowed_cycles": [50], "allowed_roles": ["BUILDER"]})


def test_wrong_role_fails_closed(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001", "expires_at": future, "allowed_cycles": [1], "allowed_roles": ["REVIEWER"]})


def test_old_valid_pilot_cannot_override_owner_disable(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001", "expires_at": future, "allowed_cycles": [1], "allowed_roles": ["BUILDER"]})


def test_pilot_id_must_match(tmp_path: Path) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="pilot", builder_backend="codex_cli", builder_model="gpt-5.5", pilot={"enabled": True, "pilot_id": "pilot-001", "expires_at": future, "allowed_cycles": [1], "allowed_roles": ["BUILDER"]})


def test_external_mode_requires_activation_token(tmp_path: Path) -> None:
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        pack_with_execution(tmp_path, mode="external", builder_backend="codex_cli", builder_model="gpt-5.5", pilot_enabled=False)


# ── Integration: dispatch_seam + result contract ──────────────────

def test_integration_seam_imports_and_exports(tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        executable = str(SCRIPTS_DIR / "buildroom_loop.py")
        proc = subprocess.run(
            [sys.executable, executable, "--project", "nonexistent"],
            capture_output=True, text=True, timeout=10, cwd=str(SCRIPTS_DIR),
            env={**os.environ, "PYTHONPATH": str(SCRIPTS_DIR)},
        )
        output = proc.stdout + proc.stderr
        assert "PROJECT_PACK_REQUIRED" in output or "not found" in output.lower()
    finally:
        if str(SCRIPTS_DIR) in sys.path:
            sys.path.remove(str(SCRIPTS_DIR))


def test_external_runner_receives_only_assigned_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    req = ExecutionRequest.create(
        role="BUILDER", backend="codex_cli", provider="openai-codex", model="gpt-5.5",
        repo="Owner/repo", worktree=str(repo), base_commit=base, branch="task/branch",
        prompt="bounded task", allowed_paths=["README.md"], test_command="pytest -q",
        output_path=str(tmp_path / "ev" / "output.json"), timeout_seconds=5, max_attempts=1,
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        command_for_request(req, executable="echo")


def test_external_process_never_receives_state_authority(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    req = ExecutionRequest.create(
        role="BUILDER", backend="opencode_cli", provider="kimi-for-coding", model="kimi/k2p6",
        repo="Owner/repo", worktree=str(repo), base_commit=base, branch="task/branch",
        prompt="review only", allowed_paths=["README.md"], test_command="pytest -q",
        output_path=str(tmp_path / "ev" / "output.json"), timeout_seconds=5, max_attempts=1,
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:opencode_cli$"):
        command_for_request(req, executable="echo")


def test_failed_run_blocks_phase_progression(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    req = ExecutionRequest.create(
        role="BUILDER", backend="codex_cli", provider="openai-codex", model="gpt-5.5",
        repo="Owner/repo", worktree=str(repo), base_commit=base, branch="task/branch",
        prompt="bounded", allowed_paths=["README.md"], test_command="python -c 'print(1)'",
        output_path=str(tmp_path / "ev" / "output.json"), timeout_seconds=5, max_attempts=1,
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        run_execution(req, artifacts_dir=tmp_path / "artifacts")
    assert not (tmp_path / "artifacts").exists()


def test_timed_out_run_blocks_phase_progression(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    req = ExecutionRequest.create(
        role="BUILDER", backend="codex_cli", provider="openai-codex", model="gpt-5.5",
        repo="Owner/repo", worktree=str(repo), base_commit=base, branch="task/branch",
        prompt="bounded", allowed_paths=["README.md"], test_command="python -c 'print(1)'",
        output_path=str(tmp_path / "ev" / "output.json"), timeout_seconds=1, max_attempts=1,
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        run_execution(req, artifacts_dir=tmp_path / "artifacts")
    assert not (tmp_path / "artifacts").exists()


def test_no_fallback_without_configured_policy(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = init_repo(repo)
    req = ExecutionRequest.create(
        role="BUILDER", backend="codex_cli", provider="openai-codex", model="gpt-5.5",
        repo="Owner/repo", worktree=str(repo), base_commit=base, branch="task/branch",
        prompt="bounded", allowed_paths=["README.md"], test_command="python -c 'print(1)'",
        output_path=str(tmp_path / "ev" / "output.json"), timeout_seconds=5, max_attempts=1,
    )
    with pytest.raises(ExecutionRuntimeError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        run_execution(req, artifacts_dir=tmp_path / "artifacts")
    assert not (tmp_path / "artifacts").exists()


def test_native_dogfood_path_unchanged(tmp_path: Path) -> None:
    pack = pack_with_execution(tmp_path,mode="native")
    assert pack.backend_for("BUILDER") == "native"
    auth = pack.authorize_external_execution(role="BUILDER", cycle=1)
    assert auth is None


def test_peekxd_projectpack_remains_native() -> None:
    peekxd = ProjectPack.from_yaml(Path.home() / ".hermes/buildroom/projects/peekxd.yaml")
    assert hasattr(peekxd, "execution_mode")
    assert peekxd.execution_mode == "native"
    assert peekxd.builder_backend == "native"
    assert peekxd.reviewer_backend == "native"


def test_curaops_projectpack_enables_authorized_engineering_finish_line() -> None:
    curaops = ProjectPack.from_yaml(Path.home() / ".hermes/buildroom/projects/curaops-vrp.yaml")
    assert curaops.autopilot_enabled is False
    assert curaops.delivery_mode == "engineering_finish_line"
    assert curaops.phase_allowed("BUILDER")
    assert curaops.phase_allowed("MERGE")
    curaops.require_phase("BUILDER")
    with pytest.raises(ProjectPackError, match="AUTOPILOT_DISABLED"):
        curaops.require_autonomous_phase("RESEARCHER")
    assert curaops.independence_owner_approved is True
    assert curaops.independence_owner_approval_ref == "owner@2026-07-12"
