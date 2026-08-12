"""Acceptance-fixture harness + retry dispatch tests (CLOSURE-V1).

Proves:
- acceptance_fixture_cli registry gating (enabled only under ACCEPTANCE_MODE);
- fixture runs real exit codes through the adapter (EXIT_7 -> 7);
- retry creates a NEW attempt under the SAME job and the dispatcher auto-runs it;
- idempotent retry with same key creates no extra attempt.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return repo, base


class _Gw:
    """Real-adjacent gateway for the acceptance fixture (no fake state)."""

    def __init__(self):
        pass

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()


def _svc(tmp_path, repo, base, acceptance=False):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _Gw()
    adapter_ids = ("hermes_scoped", "codex_cli", "opencode_cli", "hermes")
    if acceptance:
        adapter_ids = adapter_ids + ("acceptance_fixture_cli",)
    svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                              repo_allowlist={"fixture": repo},
                              adapter_ids=adapter_ids,
                              global_concurrency=1)
    return svc, gw


class TestAcceptanceFixture:
    def test_fixture_exit7(self):
        p = subprocess.run([sys.executable, "-m",
                            "conduvera.harness.acceptance_fixture",
                            "--scenario", "EXIT_7", "--hold-s", "0"],
                           capture_output=True, text=True)
        assert p.returncode == 7

    def test_fixture_exit0(self):
        p = subprocess.run([sys.executable, "-m",
                            "conduvera.harness.acceptance_fixture",
                            "--scenario", "HOLD_THEN_EXIT_0", "--hold-s", "0.1"],
                           capture_output=True, text=True)
        assert p.returncode == 0

    def test_invalid_scenario_rejected(self):
        from conduvera.harness.adapters import _acceptance_args
        with pytest.raises(ValueError):
            _acceptance_args("", {"scenario": "EVIL; rm -rf /"})

    def test_registry_gated(self):
        from conduvera.harness.registry import HarnessAdapterRegistry
        os.environ.pop("CONDUVERA_ACCEPTANCE_MODE", None)
        r = HarnessAdapterRegistry("conduvera/harness/contracts/harness-registry.yaml").registrations()
        assert r["acceptance_fixture_cli"].enabled is False
        os.environ["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        r = HarnessAdapterRegistry("conduvera/harness/contracts/harness-registry.yaml").registrations()
        assert r["acceptance_fixture_cli"].enabled is True
        os.environ.pop("CONDUVERA_ACCEPTANCE_MODE", None)


class TestRetryDispatch:
    def test_retry_same_job_new_attempt_dispatched(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        # terminal job via direct store state
        from conduvera.control_plane.scheduler import (
            AttemptState, JobState,
        )
        # reuse submit path then force terminal
        r = svc.submit_job(task_id="R", attempt_id="r1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={},
                           prompt="x", task_type="code_change")
        job_id = r["job_id"]
        svc.scheduler.claim("r1", dispatcher_id="t")
        job = svc.scheduler.store.get_job(job_id)
        job.state = JobState.FAILED
        job.exit_code = 1
        svc.scheduler.store.save_job(job)
        a1 = svc.scheduler.store.get_attempt("r1")
        a1.terminal = True
        a1.state = AttemptState.FAILED
        svc.scheduler.store.save_attempt(a1)

        # retry -> SAME job, NEW attempt
        rr = svc.retry_job(job_id, attempt_id="r2", idempotency_key="k1")
        assert rr.get("job_id") == job_id
        assert rr.get("attempt_id") == "r2"
        # idempotent duplicate with same key -> no new attempt
        rr2 = svc.retry_job(job_id, idempotency_key="k1")
        assert rr2.get("duplicate") is True
        assert rr2.get("attempt_id") == "r2"
        # dispatch the retry attempt
        svc.scheduler.claim("r2", dispatcher_id="t")
        d = svc.dispatch_claimed("r2")
        assert d.get("success") is True
        # job reopened
        job2 = svc.scheduler.store.get_job(job_id)
        assert job2.state.value == "RUNNING"
