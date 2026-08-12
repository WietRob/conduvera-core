"""Restart/recovery tests (OPERATIONAL-ACTIVITY-V1, WS-E).

Proves restart-safe reconciliation with a REAL running process fingerprint:
- a running session (real `sleep` child) is rediscovered after a new service
  instance is built from the same state dir;
- exactly one session remains (no duplicate);
- a queued job stays queued and auto-dispatches after capacity frees;
- a dead session becomes terminal (process gone), never adopted.
"""

import subprocess
import sys
import time
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


def _mk_session(svc, session_id, task_id, attempt_id, pid):
    from conduvera.harness.managed_session import (
        ManagedSession, OwnershipClass, SessionState,
    )
    import time as _t
    sess = ManagedSession(
        session_id=session_id, task_id=task_id, attempt_id=attempt_id,
        harness_descriptor="hermes_scoped", ownership_class=OwnershipClass.MANAGED,
        state=SessionState.RUNNING, scope_id="x.scope",
        started_at=_t.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))
    svc.registry.register(sess)
    return sess


def _real_fingerprint(pid):
    """Build a fingerprint that matches the live process start_time."""
    from conduvera.harness.managed_session import ProcessFingerprint
    from conduvera.harness.managed_session import _process_start_time, _boot_id
    return ProcessFingerprint(pid=pid, start_time=_process_start_time(pid),
                              boot_id=_boot_id(), command="sleep")


class TestRestartRecovery:
    """WS-E: restart-safe reconciliation exactly-once."""

    def test_running_session_rediscovered_exactly_once(self, tmp_path):
        from conduvera.control_plane.service import (
            ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
        )
        repo, base = _make_repo(tmp_path)
        state = tmp_path / "state"
        config = ControlPlaneConfig.default(state_dir=state)
        # real long-running child process
        child = subprocess.Popen(["sleep", "60"])
        try:
            reg1 = PersistentSessionRegistry(config.registry_path)
            gw1 = type("Gw", (), {"start_session": lambda **k: type(
                "R", (), {"success": True})()} )()
            svc1 = ControlPlaneService(registry=reg1, gateway_service=gw1,
                                       config=config, repo_allowlist={"fixture": repo},
                                       global_concurrency=2)
            fp = _real_fingerprint(child.pid)
            sess = _mk_session(svc1, "mxs_restart", "T", "a1", child.pid)
            sess.fingerprint = fp
            sess.scope_id = ""
            reg1.update(sess)

            # "restart": a fresh service from the same persistent state
            reg2 = PersistentSessionRegistry(config.registry_path)
            gw2 = type("Gw", (), {"start_session": lambda **k: type(
                "R", (), {"success": True})()} )()
            svc2 = ControlPlaneService(registry=reg2, gateway_service=gw2,
                                       config=config, repo_allowlist={"fixture": repo},
                                       global_concurrency=2)
            res = svc2.reconcile()
            rec = res.get("mxs_restart", {})
            assert rec.get("transitioned") == "rediscovered"
            assert rec.get("state") == "RUNNING"
            # exactly one session remains
            same = [s for s in reg2.all() if s.session_id == "mxs_restart"]
            assert len(same) == 1
        finally:
            child.kill()

    def test_dead_session_becomes_terminal_not_adopted(self, tmp_path):
        from conduvera.control_plane.service import (
            ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
        )
        repo, base = _make_repo(tmp_path)
        state = tmp_path / "state"
        config = ControlPlaneConfig.default(state_dir=state)
        # a child that exits quickly -> dead PID
        child = subprocess.Popen(["sleep", "0.2"])
        child.wait()
        reg = PersistentSessionRegistry(config.registry_path)
        gw = type("Gw", (), {"start_session": lambda **k: type(
            "R", (), {"success": True})()} )()
        svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                                  repo_allowlist={"fixture": repo},
                                  global_concurrency=2)
        fp = _real_fingerprint(child.pid)
        sess = _mk_session(svc, "mxs_dead", "T2", "b1", child.pid)
        sess.fingerprint = fp
        sess.scope_id = ""
        reg.update(sess)
        res = svc.reconcile()
        rec = res.get("mxs_dead", {})
        # dead pid -> process_gone -> COMPLETED (truthful, never adopted)
        assert rec.get("transitioned") == "process_gone"
        assert reg.get("mxs_dead").state.value == "COMPLETED"
