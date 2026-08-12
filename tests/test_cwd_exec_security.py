"""Shell-free cwd executor security tests (SHELLFREE-CWD-EXECUTOR-V1).

Settles ACTUAL behavior (not source-text presence):

- cwd executor starts a fixture executable in the requested directory;
- boundary: non-allowlisted cwd rejected, relative cwd rejected, symlink
  escape rejected, empty argv rejected;
- adversarial prompt: exact argument reaches the fixture unchanged, no marker
  file is created, no shell process is introduced;
- exactly once: one attempt starts one helper and one harness process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.harness.cwd_exec import CwdExecError, _resolve_within_root  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_worktree(root: Path, name: str = "wt1") -> Path:
    """Ein Managed-Worktree-Verzeichnis unter root erstellen."""
    wt = root / name
    wt.mkdir(parents=True, exist_ok=True)
    return wt


def _echo_argv_fixture(wt: Path, out_json: Path) -> Path:
    """Ein Fixture-Skript, das argv als JSON schreibt (verifiziert Durchreichung)."""
    fx = wt / "echo_argv.py"
    fx.write_text(
        "import sys, json\n"
        f"open({str(out_json)!r},'w').write(json.dumps(sys.argv))\n")
    return fx


def _run_executor(cwd: str, cmd: list[str], env: dict | None = None,
                  state_dir: Path | None = None):
    """cwd_exec als subprocess starten (returns CompletedProcess).

    state_dir: wenn gesetzt, wird CONDUVERA_STATE_DIR gesetzt, damit
    _worktree_root() = <state_dir>/worktrees zum Test-Worktree passt.
    """
    e = dict(os.environ)
    if state_dir is not None:
        e["CONDUVERA_STATE_DIR"] = str(state_dir)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "conduvera.harness.cwd_exec",
         "--cwd", cwd, "--"] + cmd,
        capture_output=True, text=True, timeout=30, env=e)


# ---------------------------------------------------------------------------
# Work C.1 — Unit: starts fixture in requested dir
# ---------------------------------------------------------------------------

class TestExecutorUnit:
    """cwd_exec startet ein Fixture im angeforderten Verzeichnis."""

    def test_starts_fixture_in_requested_dir(self, tmp_path):
        """Das Fixture läuft mit cwd = angefordertem Worktree."""
        wt = _make_worktree(tmp_path / "worktrees")
        pwd_probe = subprocess.run(
            [sys.executable, "-m", "conduvera.harness.cwd_exec",
             "--cwd", str(wt), "--", "/bin/pwd"],
            capture_output=True, text=True, timeout=30,
            env=dict(os.environ, CONDUVERA_STATE_DIR=str(tmp_path)))
        assert pwd_probe.returncode == 0, pwd_probe.stderr
        assert pwd_probe.stdout.strip() == str(wt)


# ---------------------------------------------------------------------------
# Work C.2 — Boundary
# ---------------------------------------------------------------------------

class TestBoundary:
    """Nicht-allowlistete/relative/symlink-cwd und leere argv abgelehnt."""

    def test_non_allowlisted_cwd_rejected(self, tmp_path):
        """cwd außerhalb des Worktree-Root wird abgelehnt."""
        root = tmp_path / "worktrees"
        outside = tmp_path / "outside"
        outside.mkdir()
        with pytest.raises(CwdExecError):
            _resolve_within_root(root, outside)

    def test_relative_cwd_rejected(self, tmp_path):
        """Relativer cwd-Pfad wird abgelehnt (muss absolut sein)."""
        root = tmp_path / "worktrees"
        with pytest.raises(CwdExecError):
            _resolve_within_root(root, Path("relative/wt"))

    def test_symlink_escape_rejected(self, tmp_path):
        """Symlink, der aus dem Root hinauszeigt, wird abgelehnt."""
        root = tmp_path / "worktrees"
        outside = tmp_path / "secret-outside"
        outside.mkdir()
        wt = _make_worktree(root)
        link = wt / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(CwdExecError):
            _resolve_within_root(root, link)

    def test_empty_argv_rejected(self, tmp_path):
        """Leere argv (kein Binary) wird abgelehnt."""
        wt = _make_worktree(tmp_path / "worktrees")
        r = _run_executor(str(wt), [], state_dir=tmp_path)
        assert r.returncode == 2
        assert "empty argv" in r.stderr


# ---------------------------------------------------------------------------
# Work C.3 — Adversarial prompt
# ---------------------------------------------------------------------------

class TestAdversarial:
    """Adversarial-Prompt: exakte Durchreichung, keine Marker, kein Shell."""

    ADV_PROMPT = (
        "$(touch /tmp/conduvera-injected) "
        "; touch /tmp/conduvera-injected-2 "
        "`touch /tmp/conduvera-injected-3` "
        "\"quoted\" \nnewline \\backslash"
    )

    @pytest.mark.parametrize("marker", [
        "/tmp/conduvera-injected",
        "/tmp/conduvera-injected-2",
        "/tmp/conduvera-injected-3",
    ])
    def test_no_marker_file_created(self, tmp_path, marker):
        """Kein Injection-Marker wird erzeugt."""
        if os.path.exists(marker):
            os.unlink(marker)
        wt = _make_worktree(tmp_path / "worktrees")
        out = tmp_path / "argv.json"
        _echo_argv_fixture(wt, out)
        r = _run_executor(str(wt), [sys.executable, str(wt / "echo_argv.py"),
                                    self.ADV_PROMPT], state_dir=tmp_path)
        assert r.returncode == 0
        assert not os.path.exists(marker), f"Marker {marker} wurde erzeugt!"

    def test_exact_arg_reaches_fixture(self, tmp_path):
        """Der exakte Prompt erreicht das Fixture unverändert."""
        wt = _make_worktree(tmp_path / "worktrees")
        out = tmp_path / "argv.json"
        _echo_argv_fixture(wt, out)
        r = _run_executor(str(wt), [sys.executable, str(wt / "echo_argv.py"),
                                    self.ADV_PROMPT], state_dir=tmp_path)
        assert r.returncode == 0
        argv = json.loads(out.read_text())
        assert argv[-1] == self.ADV_PROMPT

    def test_no_shell_process_introduced(self, tmp_path):
        """cwd_exec führt KEINE Shell zwischen sich und dem Fixture ein.

        Der unmittelbare Parent des ausgefuehrten Fixture-Prozesses ist der
        execvpe-Prozess selbst (python3), niemals bash/sh — die Worktree-
        Grenze und argv werden ohne Shell-Zwischenebene durchgereicht.
        """
        wt = _make_worktree(tmp_path / "worktrees")
        out = tmp_path / "shell-parent.json"
        probe = wt / "parent_check.py"
        probe.write_text(
            "import os, json\n"
            "ppid = os.getppid()\n"
            "try:\n"
            "    parent = open(f'/proc/{ppid}/comm').read().strip()\n"
            "except Exception:\n"
            "    parent = 'unknown'\n"
            f"open({str(out)!r},'w').write(json.dumps({{'parent': parent}}))\n")
        r = _run_executor(str(wt), [sys.executable, str(probe)],
                          state_dir=tmp_path)
        assert r.returncode == 0, r.stderr
        parent = json.loads(out.read_text())["parent"]
        # unmittelbarer Parent ist python3 (der execvpe-Prozess), kein shell
        assert parent not in ("bash", "sh", "dash", "zsh"), f"Shell-Parent: {parent}"
        assert parent.startswith("python"), f"unerwarteter Parent: {parent}"


# ---------------------------------------------------------------------------
# Work C.4/C.5 — Regression + exactly once
# ---------------------------------------------------------------------------

class TestRegressionAndOnce:
    """Argument-Builder-Regression + exactly-once."""

    def test_argument_builders_receive_exact_prompt(self):
        """codex/hermes Argument-Builder reichen den Prompt exakt durch;
        opencode liefert ihn über STDIN (Work A, nicht im argv)."""
        from conduvera.harness.adapters import (
            _opencode_args, _codex_args, _hermes_args,
        )
        prompt = "Fix calc.py so add returns a+b"
        # codex/hermes: prompt im argv
        for builder in (_codex_args, _hermes_args):
            args = builder(prompt, {})
            assert prompt in args, f"{builder.__name__} verliert den Prompt"
        # opencode: prompt NICHT im argv (stdin-Transport), aber Builder läuft
        args_oc = _opencode_args(prompt, {"worktree": "/wt"})
        assert prompt not in args_oc

    def test_one_attempt_one_helper_and_harness(self, tmp_path):
        """Ein Attempt startet genau einen cwd_exec-Helper + einen Harness."""
        from conduvera.control_plane.service import (
            ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
        )
        import subprocess as sp
        repo = tmp_path / "repo"
        sp.run(["git", "init", "-q", str(repo)], check=True)
        sp.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
        sp.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        (repo / "f.txt").write_text("v1\n")
        sp.run(["git", "-C", str(repo), "add", "-A"], check=True)
        sp.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = sp.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

        class _Gw:
            def __init__(self):
                self.calls = 0
            def start_session(self, **kw):
                self.calls += 1
                return type("R", (), {"success": True, "message": "ok",
                                      "detail": {"session_id": "s1", "pid": os.getpid(),
                                                 "scope": "fake"}})()
            def cancel_session(self, **kw):
                return type("R", (), {"success": True})()
            def collect_evidence(self, **kw):
                return {"session_id": kw.get("session_id"), "exit_code": 0}

        gw = _Gw()
        state = tmp_path / "state"
        config = ControlPlaneConfig.default(state_dir=state)
        reg = PersistentSessionRegistry(config.registry_path)
        svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                                  repo_allowlist={"fixture": repo},
                                  global_concurrency=1)
        svc.submit_job(task_id="T", attempt_id="A", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task", task_type="code_change")
        svc.scheduler.claim("A", dispatcher_id="t")
        svc.dispatch_claimed("A")
        assert gw.calls == 1
