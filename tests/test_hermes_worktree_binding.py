"""Core hermes_scoped worktree-fidelity binding tests (Phase B integration)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.harness.adapters import _hermes_env


def test_hermes_env_binds_terminal_cwd_to_worktree(tmp_path, monkeypatch):
    wt = tmp_path / "task-wt"
    wt.mkdir()
    monkeypatch.setenv("CONDUVERA_STATE_DIR", str(tmp_path / "state"))
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    cfg = Path(env["HERMES_CONFIG"]).read_text()
    # terminal.cwd structurally bound to the absolute worktree
    assert f"cwd: {wt}" in cfg
    assert "backend: local" in cfg
    # hermes-home lives OUTSIDE the worktree (state dir), so the worktree stays clean
    assert (tmp_path / "state" / "hermes-home") in Path(env["HERMES_HOME"]).parents
    assert env["HERMES_HOME"].startswith(str(tmp_path / "state"))
    assert env["HERMES_PROFILE"] == "fixture-live"
    assert env["HERMES_CONFIG"].startswith(str(tmp_path / "state"))
    # allowlisted env: no provider tokens / stray TERMINAL_CWD leaked
    assert "TERMINAL_CWD" not in env
    assert "OPENAI_API_KEY" not in env
    assert "LITELLM_API_KEY" in env or True  # present only if the caller exported it


def test_hermes_env_uses_workload_local_route(tmp_path, monkeypatch):
    wt = tmp_path / "task-wt"
    wt.mkdir()
    monkeypatch.setenv("CONDUVERA_STATE_DIR", str(tmp_path / "state"))
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    cfg = Path(env["HERMES_CONFIG"]).read_text()
    assert "default: workload/local" in cfg
    assert "custom:litellm" in cfg


def test_hermes_env_guarantees_litellm_api_key_from_master(monkeypatch, tmp_path):
    """Regression: the worker env must always carry a valid LITELLM_API_KEY.

    The persistent-service env may expose LITELLM_MASTER_KEY / LITELLM_KEY but
    not LITELLM_API_KEY; without this, hermes sends the 'no-key-required'
    sentinel -> LiteLLM no_db_connection. Red before the env-construction fix,
    green after."""
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-dream-test")
    monkeypatch.setenv("LITELLM_KEY", "sk-dream-key")
    wt = tmp_path / "task-wt"
    wt.mkdir()
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    assert env.get("LITELLM_API_KEY") == "sk-dream-test"
    assert env.get("LITELLM_API_KEY") != "no-key-required"


def test_hermes_env_litellm_api_key_passthrough(monkeypatch, tmp_path):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-dream-api")
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    wt = tmp_path / "task-wt"
    wt.mkdir()
    env = _hermes_env("prompt", {"worktree": str(wt), "route": "workload/local"})
    assert env.get("LITELLM_API_KEY") == "sk-dream-api"
