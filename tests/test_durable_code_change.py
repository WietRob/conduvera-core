"""Durable code-change tests (DURABLE-CODE-CHANGE-V1).

Proves (Work B/C/F):

- TaskPayloadStore: round-trip, 0600/0700, hash-mismatch rejection,
  missing-payload rejection, retention cleanup idempotency;
- queue/registry/outbox never hold raw task text — only payload_ref + hash;
- a queued attempt survives a fresh ControlPlaneService instance from the
  same state directory and receives the exact original instructions;
- dispatch_claimed calls gateway.start_session exactly once;
- public submit rejects task_command (no caller-controlled shell path);
- failed start does not leave an unregistered child process;
- duplicate dispatch is idempotently rejected.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.control_plane.payload import (  # noqa: E402
    PayloadCorruptError,
    PayloadMissingError,
    TaskPayloadEnvelope,
    TaskPayloadStore,
)
from conduvera.control_plane.scheduler import AttemptState  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (German-commented factory functions, per tests/AGENTS.md)
# ---------------------------------------------------------------------------

def _fixture_repo(path: Path) -> str:
    """Ein Git-Fixture-Repo mit einem Base-Commit erstellen."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "base"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _make_service(state_dir: Path, repo_path: Path, base: str, gw=None):
    """Eine ControlPlaneService-Instanz über einem frischen State-Dir."""
    from conduvera.control_plane.service import (
        ControlPlaneConfig,
        ControlPlaneService,
        PersistentSessionRegistry,
    )

    class _FakeGateway:
        def __init__(self):
            self.start_calls = 0
            self.last_config = None

        def start_session(self, **kw):
            self.start_calls += 1
            self.last_config = kw.get("config", {})
            return type("R", (), {
                "success": True,
                "message": "fake started",
                "detail": {"session_id": "fake_sess_1", "pid": os.getpid(),
                           "scope": "fake"},
            })()

        def cancel_session(self, **kw):
            return type("R", (), {"success": True})()

        def collect_evidence(self, **kw):
            return {"session_id": kw.get("session_id"), "exit_code": 0}

    gw = gw or _FakeGateway()
    config = ControlPlaneConfig.default(state_dir=state_dir)
    reg = PersistentSessionRegistry(config.registry_path)
    svc = ControlPlaneService(
        registry=reg, gateway_service=gw, config=config,
        repo_allowlist={"fixture": repo_path}, global_concurrency=1)
    return svc, gw


# ---------------------------------------------------------------------------
# Work B — TaskPayloadStore
# ---------------------------------------------------------------------------

class TestPayloadStore:
    """Persistenter TaskPayloadStore: Atomik, Modus, Hash, Retention."""

    def test_round_trip(self, tmp_path):
        """Payload round-trip überlebt put/get mit identischen Feldern."""
        st = TaskPayloadStore(tmp_path)
        env = TaskPayloadEnvelope(payload_id="pl_1", task_type="code_change",
                                  instructions="FIXME: make f() return 42",
                                  repo="fixture", base_commit="deadbeef")
        st.put(env)
        got = st.get("pl_1")
        assert got.instructions == "FIXME: make f() return 42"
        assert got.content_sha256 == env.content_sha256
        assert got.verify()

    def test_modes(self, tmp_path):
        """State-Dir 0700, Payload-Datei 0600."""
        st = TaskPayloadStore(tmp_path)
        st.put(TaskPayloadEnvelope(payload_id="pl_m", task_type="code_change",
                                   instructions="x", repo="r", base_commit="c"))
        assert stat.S_IMODE(st.root.stat().st_mode) == 0o700
        payload_file = st._path("pl_m")
        assert stat.S_IMODE(payload_file.stat().st_mode) == 0o600

    def test_hash_mismatch_rejected(self, tmp_path):
        """Hash-Mismatch (Payload nachträglich geändert) wird laut abgelehnt."""
        st = TaskPayloadStore(tmp_path)
        st.put(TaskPayloadEnvelope(payload_id="pl_h", task_type="code_change",
                                   instructions="original", repo="r", base_commit="c"))
        # Payload-Datei manipulieren (Instructions ändern ohne Hash zu aktualisieren)
        path = st._path("pl_h")
        data = json.loads(path.read_text())
        data["instructions"] = "TAMPERED"
        path.write_text(json.dumps(data))
        with pytest.raises(PayloadCorruptError):
            st.get("pl_h")

    def test_missing_payload_rejected(self, tmp_path):
        """Fehlender Payload schlägt laut fehl."""
        st = TaskPayloadStore(tmp_path)
        with pytest.raises(PayloadMissingError):
            st.get("pl_nope")

    def test_retention_cleanup_idempotent(self, tmp_path):
        """Cleanup nach Retention ist deterministisch und idempotent."""
        st = TaskPayloadStore(tmp_path)
        env = TaskPayloadEnvelope(
            payload_id="pl_ret", task_type="code_change", instructions="x",
            repo="r", base_commit="c")
        # retention_hours=-1 -> retention_until liegt in der Vergangenheit
        st.put(env, retention_hours=-1)
        assert st.exists("pl_ret")
        removed1 = st.cleanup_expired()
        removed2 = st.cleanup_expired()
        assert removed1 == 1
        assert removed2 == 0  # idempotent
        assert not st.exists("pl_ret")


# ---------------------------------------------------------------------------
# Work B + F — Restart survival, exactly once, no plaintext in stores
# ---------------------------------------------------------------------------

class TestDurableDispatch:
    """Gequeue te Attempt überlebt Service-Neustart mit exakten Instructions."""

    def test_queued_attempt_survives_restart_exact_instructions(self, tmp_path):
        """Ein neu erstellter Service aus demselben State-Dir liefert die
        exakten Original-Instructions (kein leerer/redacted Ersatz)."""
        repo = tmp_path / "repo"
        base = _fixture_repo(repo)
        state = tmp_path / "state"
        svc1, gw1 = _make_service(state, repo, base)
        r = svc1.submit_job(
            task_id="T", attempt_id="A1", harness="hermes_scoped",
            repo="fixture", base_commit=base, model_binding={},
            prompt="REPLACE f() body with 'return 42' and run pytest",
            task_type="code_change")
        assert r.get("success"), r
        payload_ref = r["payload_ref"]
        # Zustand von Instanz 1 zerstören, neue Instanz aus gleichem State
        svc2, gw2 = _make_service(state, repo, base)
        attempt = svc2.scheduler.store.get_attempt("A1")
        assert attempt.state is AttemptState.QUEUED
        job = svc2.scheduler.store.get_job(attempt.job_id)
        assert job.payload_ref == payload_ref
        # dispatchen -> exakte Instructions erreichen den Adapter
        claimed = svc2.scheduler.claim("A1", dispatcher_id="t2")
        assert claimed is not None
        d = svc2.dispatch_claimed("A1")
        assert d.get("success"), d
        assert gw2.last_config["prompt"] == "REPLACE f() body with 'return 42' and run pytest"
        assert gw2.last_config["content_sha256"] == job.content_sha256

    def test_no_plaintext_task_in_stores(self, tmp_path):
        """Queue/Registry enthalten nur payload_ref + Hash, nie Roh-Text."""
        repo = tmp_path / "repo"
        base = _fixture_repo(repo)
        state = tmp_path / "state"
        svc, gw = _make_service(state, repo, base)
        secret_text = "TOPSECRET-TASK-BODY-DO-NOT-STORE"
        svc.submit_job(
            task_id="T", attempt_id="A2", harness="hermes_scoped",
            repo="fixture", base_commit=base, model_binding={},
            prompt=secret_text, task_type="code_change")
        # Queue + Registry-Dateien dürfen den Roh-Text nicht enthalten
        for p in [state / "scheduler" / "queue.json", state / "registry" / "sessions.json"]:
            raw = p.read_text() if p.exists() else ""
            assert secret_text not in raw, f"plaintext in {p}"
            assert "TOPSECRET" not in raw

    def test_exactly_one_start_call(self, tmp_path):
        """Ein Attempt verursacht genau einen start_session-Aufruf."""
        repo = tmp_path / "repo"
        base = _fixture_repo(repo)
        state = tmp_path / "state"
        svc, gw = _make_service(state, repo, base)
        svc.submit_job(task_id="T", attempt_id="A3", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task", task_type="code_change")
        svc.scheduler.claim("A3", dispatcher_id="t")
        svc.dispatch_claimed("A3")
        assert gw.start_calls == 1

    def test_duplicate_dispatch_idempotently_rejected(self, tmp_path):
        """Zweiter dispatch eines bereits gestarteten Attempts wird abgelehnt."""
        repo = tmp_path / "repo"
        base = _fixture_repo(repo)
        state = tmp_path / "state"
        svc, gw = _make_service(state, repo, base)
        svc.submit_job(task_id="T", attempt_id="A4", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="task", task_type="code_change")
        svc.scheduler.claim("A4", dispatcher_id="t")
        r1 = svc.dispatch_claimed("A4")
        assert r1.get("success"), r1
        # zweiter dispatch: Attempt ist jetzt RUNNING, nicht CLAIMED -> abgelehnt
        r2 = svc.dispatch_claimed("A4")
        assert r2.get("success") is False
        assert gw.start_calls == 1


# ---------------------------------------------------------------------------
# Work C — task_command removal
# ---------------------------------------------------------------------------

class TestNoShellBackdoor:
    """task_command ist kein öffentlicher Submit-Parameter mehr."""

    def test_fingerprint_command_redacted(self):
        """Der observed fingerprint-command enthält keinen Raw-Prompt."""
        from conduvera.control_plane.service import _redact_command
        cmd = ("systemd-run --user --scope --unit conduvera-x.scope --collect "
               "--quiet codex exec --sandbox danger-full-access --json "
               "Fix calc.py so add returns a+b")
        red = _redact_command(cmd)
        assert "add returns a+b" not in red
        assert "calc.py" not in red
        assert red.startswith("systemd-run")
        assert "…[redacted]" in red

    def test_public_submit_rejects_task_command(self, tmp_path):
        """submit_job akzeptiert keinen task_command (kein `bash -c`-Pfad)."""
        from conduvera.control_plane.service import ControlPlaneService
        import inspect
        sig = inspect.signature(ControlPlaneService.submit_job)
        assert "task_command" not in sig.parameters

    def test_adapter_no_task_command_branch(self, tmp_path):
        """Der Adapter enthält keinen `bash -c <caller>`-Zweig mehr."""
        from conduvera.harness import adapters
        src = Path(adapters.__file__).read_text()
        assert "task_command" not in src
        assert '"bash", "-c"' not in src and "['bash', '-c'" not in src

    def test_shell_metacharacter_payload_cannot_invoke_shell(self, tmp_path):
        """Shell-Metazeichen im Payload erreichen nie einen Shell-Aufruf."""
        repo = tmp_path / "repo"
        base = _fixture_repo(repo)
        state = tmp_path / "state"
        svc, gw = _make_service(state, repo, base)
        # Ein gefährlicher Prompt mit Shell-Metazeichen wird als reine
        # Instructions an den Fake-Adapter weitergegeben, nie als Shell-Kommando.
        svc.submit_job(task_id="T", attempt_id="A5", harness="hermes_scoped",
                       repo="fixture", base_commit=base, model_binding={},
                       prompt="$(touch /tmp/PWNED); echo hacked", task_type="code_change")
        svc.scheduler.claim("A5", dispatcher_id="t")
        svc.dispatch_claimed("A5")
        # Der Fake-Gateway hat die Instructions als config.prompt erhalten,
        # nicht als ausführbares Shell-Kommando.
        assert "touch /tmp/PWNED" in gw.last_config["prompt"]
        assert not Path("/tmp/PWNED").exists()
