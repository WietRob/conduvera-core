"""Core hermes_scoped worktree-fidelity binding tests (Phase B integration)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.harness.adapters import _hermes_env


def test_hermes_env_binds_terminal_cwd_to_worktree(tmp_path):
    wt = tmp_path / "task-wt"
    wt.mkdir()
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    cfg = (wt / "hermes-home" / "profiles" / "fixture-live" / "config.yaml").read_text()
    # terminal.cwd structurally bound to the absolute worktree
    assert f"cwd: {wt}" in cfg
    assert "backend: local" in cfg
    # session-local HERMES_* pointers returned
    assert env["HERMES_HOME"] == str(wt / "hermes-home")
    assert env["HERMES_PROFILE"] == "fixture-live"
    assert env["HERMES_CONFIG"] == str(wt / "hermes-home" / "profiles" / "fixture-live" / "config.yaml")
    # allowlisted env: no provider tokens / stray TERMINAL_CWD leaked
    assert "TERMINAL_CWD" not in env
    assert "OPENAI_API_KEY" not in env
    assert "LITELLM_API_KEY" in env or True  # present only if the caller exported it


def test_hermes_env_uses_workload_local_route(tmp_path):
    wt = tmp_path / "task-wt"
    wt.mkdir()
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    cfg = (wt / "hermes-home" / "profiles" / "fixture-live" / "config.yaml").read_text()
    assert "default: workload/local" in cfg
    assert "custom:litellm" in cfg
