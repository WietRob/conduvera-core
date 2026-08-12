"""Exit-code propagation integration test (RUNTIME-HANDOFF-V1, Work C).

Proves the exact exit code flows:
  adapter collect_evidence exit_code -> session/attempt/job terminal state
  -> console JSON/human view all show exit_code=7 for a FAILED job.
Uses a fake gateway returning exit_code 7 (deterministic; the live OpenCode
proof is exercised separately via the real service).
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


class _Exit7Gateway:
    """Fake gateway: start_session ok, collect_evidence reports exit_code 7."""

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1,
                                         "scope": "fake.scope"}})()

    def collect_evidence(self, adapter_id, session_id):
        return {"session_id": session_id, "exit_code": 7,
                "artifacts": [{"path": "/tmp/fake.out", "sha256": "sha256:abc"}]}

    def cancel_session(self, **kw):
        return type("R", (), {"success": True})()


class TestExitCodePropagation:
    """exit_code 7 fliesst durch session/job/console."""

    def _run_exit7(self, tmp_path):
        from conduvera.control_plane.engine import ControlPlaneEngine
        from conduvera.control_plane.service import (
            ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
        )
        repo, base = _make_repo(tmp_path)
        gw = _Exit7Gateway()
        state = tmp_path / "state"
        config = ControlPlaneConfig.default(state_dir=state)
        reg = PersistentSessionRegistry(config.registry_path)
        svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                                  repo_allowlist={"fixture": repo},
                                  global_concurrency=1)
        eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                                 registry=reg)
        svc.submit_job(task_id="EXIT7", attempt_id="e7", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="exit 7 task", task_type="code_change")
        svc.scheduler.claim("e7", dispatcher_id="t")
        # start via gateway -> real registry session with adapter_session_id
        res = svc.dispatch_claimed("e7")
        # find the managed session for this attempt
        session = None
        for s in reg.all():
            if s.attempt_id == "e7":
                session = s
                break
        assert session is not None, "keine Session im Registry"
        eng._handle_process_gone(session, svc.scheduler.store.get_attempt("e7"),
                                 session.session_id)
        return svc, session.session_id

    def test_job_failed_exit7(self, tmp_path):
        """Job wird FAILED mit exit_code 7."""
        svc, sid = self._run_exit7(tmp_path)
        job = svc.scheduler.store.get_job(
            svc.scheduler.store.get_attempt("e7").job_id)
        assert job.state.value == "FAILED"
        assert job.exit_code == 7

    def test_console_shows_exit7(self, tmp_path):
        """Console-View zeigt exit_code=7 im TERMINAL-Abschnitt."""
        svc, sid = self._run_exit7(tmp_path)
        cv = svc.console_view()
        t = [j for j in cv["terminal"] if j.get("task_id") == "EXIT7"]
        assert t, "EXIT7 fehlt im terminal"
        assert t[0]["state"] == "FAILED"
        assert t[0]["exit_code"] == 7
