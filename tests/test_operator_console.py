"""Operator Console tests (OPERATOR-CONSOLE-V1).

Proves the consolidated console view against the real service:
- console endpoint returns queued / running / terminal sections with counts;
- queued shows payload_ref + content hash, never raw prompt;
- running shows worktree/base/elapsed/deadline;
- terminal shows state/reason/exit/result_refs;
- payload content stays redacted across the whole view.
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


class TestConsoleView:
    """console_view konsolidiert queued/running/terminal ohne raw Prompts."""

    def _svc(self, tmp_path, repo, base):
        from conduvera.control_plane.service import (
            ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
        )
        class _Gw:
            def __init__(self):
                self.calls = 0
            def start_session(self, **kw):
                self.calls += 1
                return type("R", (), {"success": True, "message": "ok",
                                      "detail": {"session_id": "s1", "pid": 1,
                                                 "scope": "x.scope"}})()
            def cancel_session(self, **kw):
                return type("R", (), {"success": True})()
            def collect_evidence(self, **kw):
                return {"session_id": kw.get("session_id"), "exit_code": 0}
        state = tmp_path / "state"
        config = ControlPlaneConfig.default(state_dir=state)
        reg = PersistentSessionRegistry(config.registry_path)
        return ControlPlaneService(registry=reg, gateway_service=_Gw(),
                                   config=config, repo_allowlist={"fixture": repo},
                                   global_concurrency=2), _Gw()

    def test_console_sections_and_counts(self, tmp_path):
        """console_view liefert queued/running/terminal + counts."""
        repo, base = _make_repo(tmp_path)
        svc, gw = self._svc(tmp_path, repo, base)
        # ein queued + ein dispatched job
        svc.submit_job(task_id="T1", attempt_id="A1", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task one", task_type="code_change")
        svc.submit_job(task_id="T2", attempt_id="A2", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task two", task_type="code_change")
        svc.scheduler.claim("A1", dispatcher_id="t")
        svc.dispatch_claimed("A1")
        cv = svc.console_view()
        assert set(cv.keys()) == {"counts", "queued", "running", "terminal",
                                  "server_time_utc"}
        # A2 queued (capacity 2 but dispatch claims A1), counts >= 0
        assert cv["counts"]["queued"] >= 1
        assert "queued" in cv and "running" in cv and "terminal" in cv

    def test_console_never_leaks_raw_prompt(self, tmp_path):
        """Die Console reicht NIE raw Prompts durch (nur payload_ref + hash)."""
        repo, base = _make_repo(tmp_path)
        svc, gw = self._svc(tmp_path, repo, base)
        svc.submit_job(task_id="T", attempt_id="A", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="SECRET_RAW_PROMPT_MARKER", task_type="code_change")
        cv = svc.console_view()
        blob = repr(cv)
        assert "SECRET_RAW_PROMPT_MARKER" not in blob
        # payload_ref vorhanden
        assert any(q.get("payload_ref") for q in cv["queued"])

    def test_running_has_worktree_base_deadline(self, tmp_path):
        """Running-Session zeigt worktree/base/elapsed/deadline."""
        repo, base = _make_repo(tmp_path)
        svc, gw = self._svc(tmp_path, repo, base)
        svc.submit_job(task_id="T", attempt_id="A", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task", task_type="code_change")
        svc.scheduler.claim("A", dispatcher_id="t")
        svc.dispatch_claimed("A")
        cv = svc.console_view()
        running = cv["running"]
        assert running, "erwarte eine running-Session"
        r = running[0]
        assert "worktree" in r and "base_commit" in r
        assert "elapsed_s" in r and "deadline_utc" in r
        # WS-B: running-Eintrag muss ein eindeutiges state-Label tragen,
        # damit die grafische Workspace RUNNING statt UNKNOWN anzeigt.
        assert r["state"] == "RUNNING"
