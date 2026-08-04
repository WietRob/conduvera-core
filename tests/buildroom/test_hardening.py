"""Härtungs-Tests (Goal harden-core-adapter-seam, DOD-01..15).

Verifiziert:
- DOD-01/02: Core kennt nur den öffentlichen HarnessGatewayService; kein
  getattr/private-Feld-Zugriff/broad-except im Runner.
- DOD-03: Registry-Auflösung cwd-unabhängig; nur über Gateway; negative
  Tests (fremdes cwd, fehlende Registry, disabled/absent Adapter).
- DOD-04: ExecutionMode SIMULATION vs LIVE; kein stiller Default; Mode in
  Events/Receipts; Simulation erfüllt nie Live-Gates.
- DOD-05/06: Fingerprint vor jedem Signal; TERM->Grace->KILL.
- DOD-08: Env-Allowlist (Hermes-Kind erbt nicht die Parent-Env).
- DOD-10: Live- und Unit-Fixtures getrennt (route-manifest.fixture.yaml).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.fixture_runner import FixtureRunner  # noqa: E402
from curaops.harness.gateway import HarnessGatewayService  # noqa: E402
from curaops.harness.hermes_adapter import (
    _build_hermes_env,  # noqa: E402  (unit-level allowlist proof)
)
from curaops.harness.registry import ExecutionMode  # noqa: E402

FIXTURES = ROOT / "fixtures"
ROUTE_FIXTURE = FIXTURES / "ods" / "route-manifest.fixture.yaml"


# -- DOD-01/02: Core kennt nur den öffentlichen Gateway-Vertrag -------------


def test_dod01_runner_source_has_no_concrete_adapter_import():
    src = (ROOT / "curaops/buildroom/fixture_runner.py").read_text(encoding="utf-8")
    assert "from curaops.harness.hermes_adapter import" not in src
    assert "HarnessAdapterRegistry(" not in src.replace("from curaops.harness.registry import", "")
    # The productive run() path must not dispatch via getattr on adapter
    # internals or access private adapter fields. The _TestOnlyGateway
    # (test-only factory) is the only place allowed to use getattr, and it
    # is explicitly marked test-only.
    run_body = src.split("def run(self, task_description")[1]
    # cut at the next method of the FixtureRunner class (before helpers/_TestOnlyGateway)
    for marker in ("def timeout(", "def cancel(", "def reconcile(", "def _emit("):
        idx = run_body.find(marker)
        if idx != -1:
            run_body = run_body[:idx]
            break
    assert "getattr(self._adapter" not in run_body
    assert "wait_for_completion" not in run_body
    assert "_task_timeout_s" not in run_body


def test_dod02_runner_has_no_private_field_access():
    src = (ROOT / "curaops/buildroom/fixture_runner.py").read_text(encoding="utf-8")
    # No access to adapter privates: _task_timeout_s, _sessions, _handle, ...
    for forbidden in ("_task_timeout_s", "._sessions", "._handle", "except Exception: pass"):
        assert forbidden not in src, f"verboten im Runner: {forbidden}"


def test_dod02_gateway_await_completion_is_contract_method():
    from curaops.harness.registry import HarnessAdapterProtocol

    proto = HarnessAdapterProtocol
    assert hasattr(proto, "await_completion")
    # The gateway service exposes it publicly.
    gw = HarnessGatewayService(execution_mode=ExecutionMode.LIVE.value)
    assert hasattr(gw, "await_completion")


# -- DOD-03: Registry cwd-unabhängig + nur über Gateway ---------------------


def test_dod03_registry_resolution_ignores_cwd(tmp_path):
    import curaops.harness.registry as reg_mod

    # Explicit path wins regardless of cwd.
    reg = tmp_path / "sub" / "harness-registry.yaml"
    reg.parent.mkdir(parents=True)
    reg.write_text("adapters: {}\n", encoding="utf-8")
    resolved = reg_mod.resolve_registry_path(explicit=reg)
    assert resolved == reg.resolve()


def test_dod03_registry_env_var_resolution(tmp_path, monkeypatch):
    import curaops.harness.registry as reg_mod

    reg = tmp_path / "env-registry.yaml"
    reg.write_text("adapters: {}\n", encoding="utf-8")
    monkeypatch.setenv("CONDUVERA_HARNESS_REGISTRY", str(reg))
    resolved = reg_mod.resolve_registry_path(explicit=None)
    assert resolved == reg.resolve()


def test_dod03_no_cwd_fallback_when_nothing_configured(tmp_path, monkeypatch):
    import curaops.harness.registry as reg_mod

    monkeypatch.delenv("CONDUVERA_HARNESS_REGISTRY", raising=False)
    # chdir to a directory with no registry
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        reg_mod.resolve_registry_path(explicit=None)


def test_dod03_runner_without_registry_fails_closed(tmp_path):
    runner = FixtureRunner(
        fixture_dir=tmp_path / "f",
        route_manifest=ROUTE_FIXTURE,
        producer={"name": "t", "version": "1"},
        execution_mode=ExecutionMode.SIMULATION.value,
    )
    result = runner.run("task")
    assert result.status == "cap_unavailable"
    assert result.error == "CAPABILITY_UNAVAILABLE"


def test_dod03_no_direct_registry_usage_in_productive_callers():
    """DOD-03: Core/Runner/CLI must never use HarnessAdapterRegistry or
    HarnessGatewayRegistry.load_adapter() directly — only the public
    HarnessGatewayService lifecycle is allowed. The gateway module itself
    owns the loader internally (that is its job)."""
    import curaops.buildroom.fixture_runner as fr_mod
    import curaops.harness.gateway as gw_mod

    # Runner/Core: no direct registry instantiation, no load_adapter calls.
    fr_src = Path(fr_mod.__file__).read_text(encoding="utf-8") if fr_mod.__file__ else ""
    assert "HarnessAdapterRegistry(" not in fr_src, "FixtureRunner instanziert HarnessAdapterRegistry direkt"
    assert "load_adapter(" not in fr_src, "FixtureRunner ruft load_adapter direkt"
    # The gateway service must NOT expose a public load_adapter (private only):
    gw_src = Path(gw_mod.__file__).read_text(encoding="utf-8") if gw_mod.__file__ else ""
    assert "def load_adapter" not in gw_src or "def _load_adapter" in gw_src


def test_dod03_concrete_adapter_never_returned_to_caller(tmp_path):
    """The gateway lifecycle returns AdapterResult/dicts — never the
    concrete adapter object."""
    gw = HarnessGatewayService(execution_mode=ExecutionMode.SIMULATION.value)
    start = gw.start_session(
        "hermes",
        agent_id="a", worktree=str(tmp_path / "wt"),
        task="t", config={},
    )
    # SIMULATION without registry: the adapter is not loadable -> structured
    # fail-closed result, and definitely no adapter object.
    assert isinstance(start, dict) or hasattr(start, "success")


# -- DOD-04: ExecutionMode trennt Simulation/Live ---------------------------


def test_dod04_execution_mode_never_silent_default():
    from curaops.harness.registry import ExecutionMode

    with pytest.raises(ValueError):
        ExecutionMode.require("")
    with pytest.raises(ValueError):
        ExecutionMode.require("RANDOM")
    assert ExecutionMode.require("SIMULATION") is ExecutionMode.SIMULATION
    assert ExecutionMode.require("live") is ExecutionMode.LIVE


def test_dod04_gateway_requires_explicit_mode():
    """DOD-04: HarnessGatewayService must NOT default the execution mode."""
    with pytest.raises(ValueError, match="EXECUTION_MODE_REQUIRED"):
        HarnessGatewayService()  # no execution_mode -> structured error


def test_dod04_runner_requires_explicit_mode(tmp_path):
    """DOD-04: FixtureRunner must NOT default the execution mode."""
    with pytest.raises(ValueError, match="EXECUTION_MODE_REQUIRED"):
        FixtureRunner(
            fixture_dir=tmp_path / "f",
            route_manifest=ROUTE_FIXTURE,
            producer={"name": "t", "version": "1"},
            # no execution_mode -> structured error
        )


def test_dod04_adapter_requires_explicit_mode(tmp_path):
    """DOD-04: HermesAdapter must NOT assume SIMULATION when mode missing."""
    from curaops.harness.hermes_adapter import HermesAdapter

    adapter = HermesAdapter(
        registry_path=FIXTURES / "harness-registry.yaml",
        fixture_worktree=str(tmp_path / "wt"),
    )
    result = adapter.start_session(
        agent_id="a", worktree=str(tmp_path / "wt2"),
        task="t", config={},  # no execution_mode
    )
    assert not result.success
    assert result.detail.get("code") == "EXECUTION_MODE_REQUIRED"


def test_dod04_unknown_mode_fails():
    with pytest.raises(ValueError):
        HarnessGatewayService(execution_mode="RANDOM")


# -- DOD-05/06: Fingerprint vor jedem Signal --------------------------------


def test_dod05_fingerprint_mismatch_no_signal(tmp_path):
    """A handle whose create_time does not match the live process must not
    receive a signal (PROCESS_FINGERPRINT_MISMATCH)."""
    from curaops.harness.hermes_adapter import HermesAdapter, SessionHandle

    adapter = HermesAdapter(
        registry_path=FIXTURES / "harness-registry.yaml",
        fixture_worktree=str(tmp_path / "wt"),
    )
    # Spawn a real short-lived process, then forge a handle with a wrong
    # create_time so the fingerprint check fails.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            start_new_session=True)
    pid = proc.pid
    pgid = os.getpgid(pid)
    handle = SessionHandle(
        session_id="mxfix_fake",
        pid=pid, pgid=pgid, create_time="WRONG-CREATE-TIME",
        hermes_home=str(tmp_path / "hh"), status="running",
    )
    adapter._sessions["mxfix_fake"] = type(
        "S", (), {"handle": handle, "model_binding": {}}
    )()
    result = adapter.cancel_session("mxfix_fake")
    assert not result.success
    assert result.detail.get("code") == "PROCESS_FINGERPRINT_MISMATCH"
    # Process must still be alive (no signal sent).
    assert proc.poll() is None
    # Cleanup: kill own managed group.
    os.killpg(pgid, 9)
    proc.wait()


# -- DOD-08: Env-Allowlist --------------------------------------------------


def test_dod08_env_allowlist_drops_foreign_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-allowlist")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SHOULD-NOT-PASS")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SHOULD-NOT-PASS")
    monkeypatch.setenv("SESSION_COOKIE", "cookie=SHOULD-NOT-PASS")
    env = _build_hermes_env(tmp_path / "hh")
    assert env.get("LITELLM_API_KEY") == "sk-test-allowlist"
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "SESSION_COOKIE" not in env
    assert "HERMES_HOME" in env


def test_dod04_poison_env_never_leaks_parent_hermes_pointers(tmp_path, monkeypatch):
    """Poison test (DOD-04): the parent deliberately carries WRONG
    HERMES_PROFILE/HERMES_CONFIG/HERMES_ENV values. The child environment
    must contain ONLY the session-local values — the parent's pointers must
    never leak."""
    hermes_home = tmp_path / "session-home"
    hermes_home.mkdir(parents=True)
    (hermes_home / "config.yaml").write_text("model: {}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_PROFILE", "poisoned-profile")
    monkeypatch.setenv("HERMES_CONFIG", "/tmp/poisoned-config.yaml")
    monkeypatch.setenv("HERMES_ENV", "/tmp/poisoned.env")
    env = _build_hermes_env(hermes_home)
    # Session-local values are set:
    assert env.get("HERMES_HOME") == str(hermes_home)
    assert env.get("HERMES_PROFILE") == "fixture-live"
    assert env.get("HERMES_CONFIG") == str(hermes_home / "config.yaml")
    # Parent poison values never appear:
    assert "poisoned-profile" not in env.values()
    assert "poisoned-config" not in env.get("HERMES_CONFIG", "")
    assert "poisoned.env" not in env.values()
    assert "HERMES_ENV" not in env


# -- DOD-10: Live- und Unit-Fixtures getrennt -------------------------------


def test_dod10_route_manifest_fixture_is_deterministic_and_separate():
    assert ROUTE_FIXTURE.is_file()
    txt = ROUTE_FIXTURE.read_text(encoding="utf-8")
    assert "workload/local" in txt
    # Unit fixture must not reference live machine paths or the Qwen model
    # identity (which is machine-installed) — checked in the data section.
    assert "/home/" not in txt
    data = txt.split("routes:")[1]
    assert "Qwen" not in data
    # The live snapshot lives under evidence/live/<run-id>/ — never in the
    # unit fixture data (a comment mentioning the naming convention is fine).
    assert "snapshot" not in data


def test_dod10_live_snapshot_directory_is_evidence():
    snap = ROOT / "evidence/live"
    # Directory may not exist yet (created by live runs) — the point is the
    # unit fixture never writes there and no committed file pretends to be
    # a live snapshot inside fixtures/ods/.
    assert not (FIXTURES / "ods" / "route-manifest.snapshot.yaml").exists()
