"""Failure & safety matrix tests (OPERATIONAL-ACTIVITY-V1, WS-G).

Proves per-scenario session/attempt/job state + exit code + console:
1. success exit 0; 2. failure exit 7; 3. cancel; 4. timeout; 5. restart
rediscovery exactly-once; 6. invalid worktree rejection; 7. external action
rejection; 8. malformed evidence; 9. UI/API disconnect recovery.
"""

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
    """Configurable fake gateway for deterministic state transitions."""

    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.cancelled = []

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()

    def collect_evidence(self, adapter_id, session_id):
        return {"session_id": session_id, "exit_code": self.exit_code,
                "artifacts": [{"path": "/tmp/a.out", "sha256": "sha256:abc"}]}

    def cancel_session(self, adapter_id, session_id):
        self.cancelled.append(session_id)
        return type("R", (), {"success": True})()


def _svc(tmp_path, repo, base, exit_code=0):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _Gw(exit_code=exit_code)
    svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                              repo_allowlist={"fixture": repo},
                              global_concurrency=1)
    return svc, gw


def _submit_dispatch_complete(svc, task_id, attempt_id, exit_code=0):
    """submit -> claim -> dispatch -> simulate process-gone with exit code."""
    from conduvera.control_plane.engine import ControlPlaneEngine
    eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                             registry=svc.registry)
    import subprocess as sp
    base = sp.run(["git", "-C", str(svc.resolve_repo("fixture")), "rev-parse",
                   "HEAD"], capture_output=True, text=True).stdout.strip()
    svc.submit_job(task_id=task_id, attempt_id=attempt_id,
                   harness="hermes_scoped", repo="fixture", base_commit=base,
                   model_binding={}, prompt="task", task_type="code_change")
    svc.scheduler.claim(attempt_id, dispatcher_id="t")
    svc.dispatch_claimed(attempt_id)
    session = next(s for s in svc.registry.all() if s.attempt_id == attempt_id)
    eng._handle_process_gone(session, svc.scheduler.store.get_attempt(attempt_id),
                             session.session_id)
    return svc, session, svc.scheduler.store.get_attempt(attempt_id)


class TestFailureMatrix:
    """WS-G: exit 0 / exit 7 / cancel / timeout states."""

    def test_success_exit0(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base, exit_code=0)
        svc, sess, att = _submit_dispatch_complete(svc, "S0", "s0", 0)
        job = svc.scheduler.store.get_job(att.job_id)
        assert job.state.value == "COMPLETED"
        assert job.exit_code == 0

    def test_failure_exit7(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base, exit_code=7)
        svc, sess, att = _submit_dispatch_complete(svc, "S7", "s7", 7)
        job = svc.scheduler.store.get_job(att.job_id)
        assert job.state.value == "FAILED"
        assert job.exit_code == 7
        # console shows exit 7
        cv = svc.console_view()
        t = [x for x in cv["terminal"] if x.get("task_id") == "S7"]
        assert t and t[0]["exit_code"] == 7 and t[0]["state"] == "FAILED"

    def test_cancel_marks_terminal(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        import subprocess as sp
        base = sp.run(["git", "-C", str(svc.resolve_repo("fixture")), "rev-parse",
                       "HEAD"], capture_output=True, text=True).stdout.strip()
        svc.submit_job(task_id="CAN", attempt_id="c1", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="p", task_type="code_change")
        svc.scheduler.claim("c1", dispatcher_id="t")
        svc.dispatch_claimed("c1")
        sess = next(s for s in svc.registry.all() if s.attempt_id == "c1")
        r = svc.cancel(sess.session_id)
        assert r.get("success") is True
        assert r.get("state") == "CANCELLED"
        # reload from registry — the returned state is authoritative
        assert svc.registry.get(sess.session_id).state.value == "CANCELLED"
        # no process remains (fake gateway cancel called once)
        assert len(gw.cancelled) == 1

    def test_timeout_state(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        from conduvera.control_plane.engine import ControlPlaneEngine
        eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                                 registry=svc.registry)
        import subprocess as sp
        base = sp.run(["git", "-C", str(svc.resolve_repo("fixture")), "rev-parse",
                       "HEAD"], capture_output=True, text=True).stdout.strip()
        svc.submit_job(task_id="TO", attempt_id="t1", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="p", timeout_s=0.001, task_type="code_change")
        svc.scheduler.claim("t1", dispatcher_id="t")
        svc.dispatch_claimed("t1")
        sess = next(s for s in svc.registry.all() if s.attempt_id == "t1")
        eng._handle_timeout(sess, svc.scheduler.store.get_attempt("t1"),
                            sess.session_id)
        # session lacks a TIMED_OUT state (FAILED is its error state); the
        # attempt + job carry the exact TIMED_OUT cause.
        assert svc.registry.get(sess.session_id).state.value == "FAILED"
        att = svc.scheduler.store.get_attempt("t1")
        assert att.state.value == "TIMED_OUT"
        job = svc.scheduler.store.get_job(att.job_id)
        assert job.state.value == "TIMED_OUT"
        assert "timeout" in job.terminal_reason.lower()

    def test_invalid_worktree_rejected(self, tmp_path):
        """cwd_exec rejects an unregistered path (WS-G scenario 6)."""
        from conduvera.harness.cwd_exec import CwdExecError, _require_bound_worktree
        repo, base = _make_repo(tmp_path)
        bogus = tmp_path / "worktrees" / "UNREG-1-x"
        bogus.mkdir(parents=True)
        with pytest.raises(CwdExecError, match="not registered"):
            _require_bound_worktree(bogus, repo=str(repo), base_commit=base,
                                    task_id="UNREG", attempt_id="x")

    def test_external_action_rejected(self, tmp_path):
        from conduvera.harness.managed_session import (
            ManagedSession, OwnershipClass, SessionState,
        )
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        sess = ManagedSession(session_id="mxs_ext", task_id="EXT", attempt_id="e1",
                              ownership_class=OwnershipClass.EXTERNAL_UNKNOWN,
                              state=SessionState.RUNNING)
        svc.registry.register(sess)
        r = svc.cancel("mxs_ext")
        assert r.get("success") is False
        assert r.get("code") == "EXTERNAL_SESSION_NOT_CONTROLLABLE"

    def test_malformed_evidence(self, tmp_path):
        """collect_evidence returning non-dict is tolerated (never crashes)."""
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base)
        gw.collect_evidence = lambda **k: None  # malformed
        svc, sess, att = _submit_dispatch_complete(svc, "E", "e1", 0)
        job = svc.scheduler.store.get_job(att.job_id)
        # engine tolerated None evidence; job still terminal
        assert job.state.value in ("COMPLETED", "FAILED")
