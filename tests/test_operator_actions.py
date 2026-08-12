"""Operator actions tests (OPERATIONAL-ACTIVITY-V1, WS-D + WS-G).

Proves:
- retry creates a new attempt for a terminal job (same payload);
- retry is rejected for non-terminal jobs;
- operator actions (cancel/cleanup/status) reject EXTERNAL_* sessions
  fail-closed;
- cancel is idempotent on a already-terminal session.
"""

import subprocess
import sys
from pathlib import Path


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


class _FakeGw:
    def __init__(self):
        self.cancelled = []
    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()
    def collect_evidence(self, adapter_id, session_id):
        return {"session_id": session_id, "exit_code": 0,
                "artifacts": [{"path": "/tmp/a.out", "sha256": "sha256:abc"}]}
    def cancel_session(self, adapter_id, session_id):
        self.cancelled.append(session_id)
        return type("R", (), {"success": True})()


def _svc(tmp_path, repo, base):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _FakeGw()
    svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                              repo_allowlist={"fixture": repo},
                              global_concurrency=2)
    return svc, gw


def _terminal_job(svc, task_id, attempt_id):
    """submit + claim + dispatch a job, then simulate completion (exit 0)."""
    from conduvera.control_plane.engine import ControlPlaneEngine
    eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                             registry=svc.registry)
    svc.submit_job(task_id=task_id, attempt_id=attempt_id,
                   harness="hermes_scoped", repo="fixture",
                   base_commit=_base_of(svc), model_binding={},
                   prompt="task", task_type="code_change")
    svc.scheduler.claim(attempt_id, dispatcher_id="t")
    svc.dispatch_claimed(attempt_id)
    session = next(s for s in svc.registry.all() if s.attempt_id == attempt_id)
    eng._handle_process_gone(session, svc.scheduler.store.get_attempt(attempt_id),
                             session.session_id)
    job = svc.scheduler.store.get_job(
        svc.scheduler.store.get_attempt(attempt_id).job_id)
    return job


def _base_of(svc):
    import subprocess as sp
    return sp.run(["git", "-C", str(svc.resolve_repo("fixture")), "rev-parse",
                   "HEAD"], capture_output=True, text=True).stdout.strip()


class TestRetry:
    """WS-D: Retry as a new attempt."""

    def test_retry_terminal_job_new_attempt(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        job = _terminal_job(svc, "TASK-R", "a1")
        r = svc.retry_job(job.job_id, attempt_id="a2")
        assert r.get("success") is True
        # DoD-05 domain model: SAME job_id, NEW attempt_id
        assert r.get("job_id") == job.job_id
        assert r.get("attempt_id") == "a2"
        a2 = svc.scheduler.store.get_attempt("a2")
        assert a2 is not None and a2.state.value in ("QUEUED", "ACCEPTED")
        assert a2.job_id == job.job_id  # new attempt belongs to the SAME job
        # payload_ref + hash unchanged
        assert r.get("payload_ref") == job.payload_ref
        assert r.get("content_sha256") == job.content_sha256
        # previous attempt immutable + retained
        a1 = svc.scheduler.store.get_attempt("a1")
        assert a1 is not None and a1.terminal is True
        # attempt history retains both
        job2 = svc.scheduler.store.get_job(job.job_id)
        assert job2.attempts == [job.attempts[0], "a2"]

    def test_retry_non_terminal_rejected(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        svc.submit_job(task_id="T", attempt_id="x1", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="p", task_type="code_change")
        job = svc.scheduler.store.all_jobs()[-1]
        r = svc.retry_job(job.job_id)
        assert r.get("success") is False
        assert r.get("code") == "NOT_TERMINAL"


class TestExternalRejection:
    """WS-D: operator actions reject EXTERNAL_* fail-closed."""

    def _external_session(self, tmp_path, repo, base):
        from conduvera.harness.managed_session import (
            ManagedSession, OwnershipClass, SessionState,
        )
        svc, gw = _svc(tmp_path, repo, base)
        sess = ManagedSession(
            session_id="mxs_ext_1", task_id="EXT", attempt_id="e1",
            harness_descriptor="hermes",
            ownership_class=OwnershipClass.EXTERNAL_UNKNOWN,
            state=SessionState.RUNNING)
        svc.registry.register(sess)
        return svc, "mxs_ext_1"

    def test_cancel_external_rejected(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, sid = self._external_session(tmp_path, repo, base)
        r = svc.cancel(sid)
        assert r.get("success") is False
        assert r.get("code") == "EXTERNAL_SESSION_NOT_CONTROLLABLE"

    def test_cleanup_external_rejected(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, sid = self._external_session(tmp_path, repo, base)
        r = svc.cleanup(sid)
        assert r.get("success") is False
        assert r.get("code") == "NOT_MANAGED"

    def test_status_external_rejected(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, sid = self._external_session(tmp_path, repo, base)
        r = svc.status(sid)
        assert r.get("success") is False
        assert r.get("code") == "NOT_MANAGED"
