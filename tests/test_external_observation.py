"""External-session observation tests (CLOSURE-V1, DOD-08).

Proves a real external process is observed read-only: visible with
control_rights=none, never adopted, control actions rejected fail-closed,
process stays alive after every rejected action.
"""

import os
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


class _Gw:
    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()


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
    return svc


class TestExternalObservation:
    def test_observe_external_readonly_and_rejected(self, tmp_path):
        """A real external process is observed, never adopted, stays alive."""
        repo, base = _make_repo(tmp_path)
        svc = _svc(tmp_path, repo, base)
        # start a real long-running external process
        child = subprocess.Popen(["sleep", "60"])
        try:
            r = svc.observe_external(pid=child.pid,
                                     classification="EXTERNAL_UNKNOWN")
            assert r.get("success") is True
            sid = r["session_id"]
            assert r.get("control_rights") == "none"
            assert r.get("ownership_class") == "EXTERNAL_UNKNOWN"
            # never adopted: still EXTERNAL in registry
            sess = svc.registry.get(sid)
            assert sess.ownership_class.value == "EXTERNAL_UNKNOWN"
            # control actions rejected fail-closed
            cancel = svc.cancel(sid)
            assert cancel.get("success") is False
            assert cancel.get("code") == "EXTERNAL_SESSION_NOT_CONTROLLABLE"
            retry = svc.retry_job("job_does_not_exist", attempt_id="x")
            assert retry.get("success") is False  # no job to retry
            # cleanup on external
            cleanup = svc.cleanup(sid)
            assert cleanup.get("success") is False
            # process stays alive after all rejected actions
            os.kill(child.pid, 0)  # no exception => alive
        finally:
            child.kill()

    def test_observe_dead_process_rejected(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc = _svc(tmp_path, repo, base)
        # a PID that cannot be alive (outside the normal PID range)
        r = svc.observe_external(pid=9999999)
        assert r.get("success") is False

    def test_external_never_gains_managed_job_authority(self, tmp_path):
        """An EXTERNAL session has no MANAGED job: retry fails closed and the
        session never transitions to MANAGED (no adoption)."""
        repo, base = _make_repo(tmp_path)
        svc = _svc(tmp_path, repo, base)
        child = subprocess.Popen(["sleep", "60"])
        try:
            r = svc.observe_external(pid=child.pid, classification="EXTERNAL_UNKNOWN")
            sid = r["session_id"]
            # retry on an external-owned identity is fail-closed (no managed job)
            retry = svc.retry_job("job_of_external_session", attempt_id="x")
            assert retry.get("success") is False
            assert retry.get("code") == "UNKNOWN_JOB"
            # session is still EXTERNAL after all attempts (never adopted)
            sess = svc.registry.get(sid)
            assert sess.ownership_class.value == "EXTERNAL_UNKNOWN"
            assert sess.managed is False
            # no MANAGED session was created
            assert not any(s.ownership_class.value == "MANAGED"
                           for s in svc.registry.all())
        finally:
            child.kill()
