"""Restart-recovery evidence fallback tests (CLOSURE-V1, WS-F / DOD-04).

Proves the engine reconstructs the real exit code after a control-plane
restart when the adapter in-memory session state is gone:
- scope ExecMainStatus unavailable -> fixture status file exit_code used;
- exit 0 + evidence_invalid false -> COMPLETED (never EVIDENCE_INVALID).
"""

import json
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
    """Gateway that loses in-memory session state (restart simulation)."""

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()

    def collect_evidence(self, adapter_id, session_id):
        # restart: adapter has no record -> no exit_code, ok False
        return {"session_id": session_id, "ok": False, "exit_code": None}


def _svc(tmp_path, repo, base):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _Gw()
    svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                              repo_allowlist={"fixture": repo},
                              global_concurrency=1)
    return svc, gw


class TestRestartEvidenceFallback:
    @pytest.fixture(autouse=True)
    def _acceptance_mode(self, monkeypatch):
        # the worktree fixture-status reconstruction is gated to the
        # acceptance fixture harness under CONDUVERA_ACCEPTANCE_MODE=1
        monkeypatch.setenv("CONDUVERA_ACCEPTANCE_MODE", "1")

    def test_non_acceptance_harness_ignores_worktree_file(self, tmp_path):
        """Trust boundary: a normal harness never reads agent-writable
        fixture-status.json from the worktree as evidence authority."""
        from conduvera.control_plane.engine import ControlPlaneEngine
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        # ensure acceptance mode OFF for this test
        os.environ.pop("CONDUVERA_ACCEPTANCE_MODE", None)
        eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                                 registry=svc.registry)
        wt = tmp_path / "wt"
        wt.mkdir()
        # a malicious agent-writable file claiming exit 0
        (wt / "fixture-status.json").write_text(json.dumps(
            {"scenario": "HOLD_THEN_EXIT_0", "exit_code": 0,
             "evidence_invalid": False}))
        from conduvera.harness.managed_session import ManagedSession, OwnershipClass, SessionState
        sess = ManagedSession(session_id="mxs_x", task_id="X", attempt_id="x1",
                              harness_descriptor="opencode_cli",  # NOT fixture
                              ownership_class=OwnershipClass.MANAGED,
                              state=SessionState.RUNNING,
                              adapter_session_id="mxs_x", worktree=str(wt),
                              scope_id="", base_commit=base)
        svc.registry.register(sess)
        from conduvera.control_plane.scheduler import AttemptDescriptor, JobDescriptor
        from conduvera.control_plane.service import _utc_now
        now = _utc_now()
        job = JobDescriptor(job_id="job_x2", task_id="X", repo="fixture",
                            base_commit=base, harness="opencode_cli",
                            model_binding={}, prompt="", created_at=now,
                            updated_at=now)
        svc.scheduler.store.save_job(job)
        attempt = AttemptDescriptor(attempt_id="x1", job_id="job_x2",
                                    task_id="X", created_at=now, updated_at=now)
        svc.scheduler.store.save_attempt(attempt)
        # collect_evidence returns no exit (adapter state gone)
        gw.collect_evidence = lambda *a, **k: {"ok": False, "exit_code": None}
        eng._handle_process_gone(sess, attempt, sess.session_id)
        job_after = svc.scheduler.store.get_job("job_x2")
        # worktree file must NOT be trusted -> fail closed (EVIDENCE_INVALID)
        assert job_after.state.value == "FAILED"
        assert job_after.terminal_reason == "EVIDENCE_INVALID"

    def test_fixture_status_reconstructs_exit0(self, tmp_path):
        """Rediscovered session with fixture-status exit 0 -> COMPLETED."""
        from conduvera.control_plane.engine import ControlPlaneEngine
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                                 registry=svc.registry)
        # worktree with a fixture-status.json reporting exit 0, no invalid
        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / "fixture-status.json").write_text(json.dumps(
            {"scenario": "HOLD_THEN_EXIT_0", "exit_code": 0,
             "evidence_invalid": False}))
        # session with adapter session id, scope empty (gone), worktree set
        from conduvera.harness.managed_session import ManagedSession, OwnershipClass, SessionState
        sess = ManagedSession(session_id="mxs_r", task_id="R", attempt_id="r1",
                              harness_descriptor="acceptance_fixture_cli",
                              ownership_class=OwnershipClass.MANAGED,
                              state=SessionState.RUNNING,
                              adapter_session_id="mxs_r", worktree=str(wt),
                              scope_id="", base_commit=base)
        svc.registry.register(sess)
        from conduvera.control_plane.scheduler import AttemptDescriptor, JobDescriptor
        from conduvera.control_plane.service import _utc_now
        now = _utc_now()
        job = JobDescriptor(job_id="job_x", task_id="R", repo="fixture",
                            base_commit=base, harness="acceptance_fixture_cli",
                            model_binding={}, prompt="", created_at=now,
                            updated_at=now)
        svc.scheduler.store.save_job(job)
        attempt = AttemptDescriptor(attempt_id="r1", job_id="job_x",
                                    task_id="R", created_at=now,
                                    updated_at=now)
        svc.scheduler.store.save_attempt(attempt)
        eng._handle_process_gone(sess, attempt, sess.session_id)
        job = svc.scheduler.store.get_job("job_x")
        assert job.state.value == "COMPLETED"
        assert job.exit_code == 0
        assert job.terminal_reason == "process exited normally"

    def test_fixture_status_invalid_still_fails_closed(self, tmp_path):
        """exit 0 + evidence_invalid true -> FAILED EVIDENCE_INVALID."""
        from conduvera.control_plane.engine import ControlPlaneEngine
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                                 registry=svc.registry)
        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / "fixture-status.json").write_text(json.dumps(
            {"scenario": "EXIT_0_WITH_INVALID_EVIDENCE", "exit_code": 0,
             "evidence_invalid": True}))
        from conduvera.harness.managed_session import ManagedSession, OwnershipClass, SessionState
        sess = ManagedSession(session_id="mxs_e", task_id="E", attempt_id="e1",
                              harness_descriptor="acceptance_fixture_cli",
                              ownership_class=OwnershipClass.MANAGED,
                              state=SessionState.RUNNING,
                              adapter_session_id="mxs_e", worktree=str(wt),
                              scope_id="", base_commit=base)
        svc.registry.register(sess)
        from conduvera.control_plane.scheduler import AttemptDescriptor, JobDescriptor
        from conduvera.control_plane.service import _utc_now
        now = _utc_now()
        job = JobDescriptor(job_id="job_y", task_id="E", repo="fixture",
                            base_commit=base, harness="acceptance_fixture_cli",
                            model_binding={}, prompt="", created_at=now,
                            updated_at=now)
        svc.scheduler.store.save_job(job)
        attempt = AttemptDescriptor(attempt_id="e1", job_id="job_y",
                                    task_id="E", created_at=now,
                                    updated_at=now)
        svc.scheduler.store.save_attempt(attempt)
        eng._handle_process_gone(sess, attempt, sess.session_id)
        job = svc.scheduler.store.get_job("job_y")
        assert job.state.value == "FAILED"
        assert job.terminal_reason == "EVIDENCE_INVALID"
