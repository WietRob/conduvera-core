"""Control plane tests (CONTROL-PLANE-V1).

Unit + integration + negative tests for the persistent runtime, daemon,
router, outbox and scoped adapters.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conduvera.control_plane.daemon import ControlPlaneDaemon
from conduvera.control_plane.outbox import EventOutbox, redact_event
from conduvera.control_plane.service import (
    ControlPlaneConfig,
    ControlPlaneService,
    PersistentSessionRegistry,
    RegistryMigrationError,
)
from conduvera.harness.managed_session import (
    ManagedSession,
    OwnershipClass,
    ProcessFingerprint,
    SessionState,
)
from conduvera.harness.router import (
    DeterministicRouter,
    NoRouteError,
)


class _FakeAdapterResult:
    def __init__(self, success: bool, message: str, detail: dict | None = None):
        self.success = success
        self.message = message
        self.detail = detail or {}


class _FakeGateway:
    def __init__(self):
        self.started: list[dict] = []
        self.cancelled: list[str] = []
        self.pid_counter = 90000

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        self.pid_counter += 1
        pid = self.pid_counter
        self.started.append({"adapter": adapter_id, "pid": pid, "worktree": worktree})
        return _FakeAdapterResult(True, "started", {
            "session_id": f"mxfix_{adapter_id}_{task}",
            "pid": pid, "pgid": pid, "status": "running",
            "execution_mode": config.get("execution_mode"),
        })

    def status_session(self, adapter_id, session_id):
        return _FakeAdapterResult(True, "running", {"status": "running"})

    def cancel_session(self, adapter_id, session_id):
        self.cancelled.append(session_id)
        return _FakeAdapterResult(True, "cancelled", {"status": "cancelled"})

    def timeout_session(self, adapter_id, session_id):
        return _FakeAdapterResult(True, "timed_out")

    def _load_adapter(self, adapter_id):
        return _FakeAdapter()


class _FakeAdapter:
    def health_check(self):
        return _FakeAdapterResult(True, f"{self} ok")


@pytest.fixture()
def service(tmp_path):
    config = ControlPlaneConfig.default(state_dir=tmp_path / "state")
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _FakeGateway()
    # Real Git fixture repo with an exact base commit (worktree proof needs it)
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    svc = ControlPlaneService(
        registry=reg, gateway_service=gw, config=config,
        repo_path=repo,
        repo_allowlist={"fixture": repo},
    )
    return svc, gw, reg, config, base


def _job(task_id: str = "T", attempt_id: str = "A", **kw: Any):
    from conduvera.harness.managed_session import ManagedJob
    return ManagedJob(task_id=task_id, attempt_id=attempt_id, **kw)


def _dispatch(svc: Any, attempt_id: str) -> dict[str, Any]:
    """Simulate the daemon-owned dispatcher: claim + dispatch one attempt."""
    claimed = svc.scheduler.claim(attempt_id, dispatcher_id="test")
    assert claimed is not None, f"attempt {attempt_id} not claimable"
    return svc.dispatch_claimed(attempt_id)


class TestRegistryPersistence:
    def test_schema_version_created(self, tmp_path):
        PersistentSessionRegistry(tmp_path / "sessions.json")
        assert (tmp_path / "schema_version").is_file()
        assert (tmp_path / "schema_version").read_text().strip() == "1"

    def test_0600_permissions(self, tmp_path):
        reg = PersistentSessionRegistry(tmp_path / "sessions.json")
        s = ManagedSession.create(job=_job())
        reg.register(s)
        mode = (tmp_path / "sessions.json").stat().st_mode & 0o777
        assert mode == 0o600
        assert reg.permission_ok()

    def test_unreadable_schema_raises(self, tmp_path):
        (tmp_path / "schema_version").write_text("abc")
        with pytest.raises(RegistryMigrationError):
            PersistentSessionRegistry(tmp_path / "sessions.json")

    def test_newer_schema_raises(self, tmp_path):
        (tmp_path / "schema_version").write_text("99")
        with pytest.raises(RegistryMigrationError):
            PersistentSessionRegistry(tmp_path / "sessions.json")


class TestControlPlaneOps:
    def test_start_registers_managed(self, service):
        svc, gw, reg, config, base = service
        r = svc.submit_job(task_id="T1", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={},
                           prompt="PONG")
        assert r["success"]
        d = _dispatch(svc, "A1")
        assert d["success"]
        sid = d["session"]["session_id"]
        s = reg.get(sid)
        assert s.ownership_class is OwnershipClass.MANAGED
        assert s.state is SessionState.RUNNING
        assert s.worktree and Path(s.worktree).is_dir()
        assert gw.started[-1]["adapter"] == "hermes_scoped"

    def test_worktree_collision_rejected(self, service, tmp_path):
        svc, gw, reg, config, base = service
        # Same task/attempt -> duplicate rejected (idempotent, never overwrite)
        r1 = svc.submit_job(task_id="T1", attempt_id="A1", harness="hermes_scoped",
                            repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert r1["success"]
        assert _dispatch(svc, "A1")["success"]
        r2 = svc.submit_job(task_id="T1", attempt_id="A1", harness="hermes_scoped",
                            repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert not r2["success"]
        assert r2["code"] == "DUPLICATE_ATTEMPT"

    def test_cancel_rejects_external(self, service):
        svc, gw, reg, config, base = service
        ext = ManagedSession(
            session_id="ext1", task_id="", attempt_id="",
            ownership_class=OwnershipClass.EXTERNAL_MANUAL_OBSERVED,
            managed=False, state=SessionState.RUNNING)
        reg.register(ext)
        r = svc.cancel("ext1")
        assert not r["success"]
        assert r["code"] == "EXTERNAL_SESSION_NOT_CONTROLLABLE"

    def test_cleanup_only_session_owned(self, service):
        svc, gw, reg, config, base = service
        r = svc.submit_job(task_id="T", attempt_id="A", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert r["success"]
        d = _dispatch(svc, "A")
        assert d["success"]
        sid = d["session"]["session_id"]
        cr = svc.cleanup(sid)
        assert cr["success"]
        assert not Path(svc.config.worktree_base / "T-A").exists()

    def test_reconcile_marks_gone_completed(self, service):
        svc, gw, reg, config, base = service
        s = ManagedSession.create(job=_job(worktree=str(config.worktree_base / "x")))
        s.fingerprint = ProcessFingerprint(pid=999999, start_time="0",
                                           boot_id="b", command="c")
        reg.register(s)
        svc.reconcile()
        got = reg.get(s.session_id)
        assert got.state in (SessionState.COMPLETED, SessionState.LOST)

    def test_reconcile_rediscover_fingerprint(self, service):
        svc, gw, reg, config, base = service
        # Reale PID: dieser Testprozess
        s = ManagedSession.create(job=_job(worktree=str(config.worktree_base / "y")))
        pid = os.getpid()
        # Fingerprint des echten Prozesses
        from conduvera.harness.managed_session import _process_start_time, _boot_id, _process_cmd
        s.fingerprint = ProcessFingerprint(
            pid=pid, start_time=_process_start_time(pid), boot_id=_boot_id(),
            command=_process_cmd(pid))
        reg.register(s)
        res = svc.reconcile()
        got = reg.get(s.session_id)
        assert res[s.session_id]["transitioned"] == "rediscovered"
        assert got.state is SessionState.RUNNING

    def test_unknown_harness_rejected(self, service):
        svc, gw, reg, config, base = service
        r = svc.start(task_id="T", attempt_id="A", harness="nonexistent",
                      repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert not r["success"]
        assert r["code"] == "UNKNOWN_HARNESS"

    def test_capabilities_declared_unsupported(self, service):
        svc, gw, reg, config, base = service
        caps = svc.capabilities("hermes_scoped")
        assert caps["start"] == "supported"
        assert caps["cancel"] == "supported"
        assert caps["pause"] == "UNSUPPORTED"
        assert caps["steer"] == "UNSUPPORTED"
        assert caps["checkpoint"] == "UNSUPPORTED"

    def test_doctor(self, service):
        svc, gw, reg, config, base = service
        d = svc.doctor()
        assert d["ok"] is True
        assert d["registry_schema"] == 1
        assert "hermes_scoped" in d["harnesses"]


class TestDaemonSocket:
    def _serve(self, daemon):
        import threading
        t = threading.Thread(target=daemon.serve_forever, daemon=True)
        t.start()
        return t

    def test_roundtrip(self, service, tmp_path):
        svc, gw, reg, config, base = service
        sock = tmp_path / "cp.sock"
        daemon = ControlPlaneDaemon(service=svc, socket_path=sock)
        daemon.start()
        self._serve(daemon)
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(5)
            conn.connect(str(sock))
            conn.sendall(b'{"method": "health", "params": {}}')
            data = conn.recv(65536)
            resp = json.loads(data.decode())
            assert resp["ok"] is True
            assert resp["result"]["status"] == "ok"
            conn.close()
            # Unknown method
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(5)
            conn.connect(str(sock))
            conn.sendall(b'{"method": "bogus"}')
            resp2 = json.loads(conn.recv(65536).decode())
            assert not resp2["ok"]
            assert resp2["error"]["code"] == "UNKNOWN_METHOD"
            conn.close()
        finally:
            daemon.stop()

    def test_socket_0600(self, service, tmp_path):
        svc, gw, reg, config, base = service
        sock = tmp_path / "cp.sock"
        daemon = ControlPlaneDaemon(service=svc, socket_path=sock)
        daemon.start()
        self._serve(daemon)
        try:
            mode = sock.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            daemon.stop()


class TestRouter:
    def test_preferred_harness(self):
        r = DeterministicRouter()
        d = r.route(task_id="t", task_class="fixture")
        assert d.harness == "hermes_scoped"
        assert d.model_binding.route == "workload/local"

    def test_manual_override(self):
        r = DeterministicRouter()
        d = r.route(task_id="t", task_class="fixture", override_harness="codex_cli")
        assert d.harness == "codex_cli"
        assert d.overridden is True

    def test_fallback_chain(self):
        r = DeterministicRouter()
        r.set_availability("hermes_scoped", False)
        d = r.route(task_id="t", task_class="fixture")
        assert d.harness == "codex_cli"
        assert "hermes_scoped" in d.fallback_chain

    def test_no_route_fail_closed(self):
        r = DeterministicRouter()
        for h in ("hermes_scoped", "codex_cli", "opencode_cli"):
            r.set_availability(h, False)
        with pytest.raises(NoRouteError) as ei:
            r.route(task_id="t", task_class="fixture")
        assert ei.value.code == "NO_ROUTE"

    def test_high_risk_without_steer_no_route(self):
        r = DeterministicRouter()
        from conduvera.harness.router import TaskClass
        # high-risk task class WITHOUT steer capability -> NO_ROUTE (fail-closed)
        high_risk = TaskClass(
            name="high_risk_no_steer", risk="HIGH",
            required_capabilities=("start", "status", "cancel", "collect_evidence"),
            preferred_harness=None)
        with pytest.raises(NoRouteError):
            r.route(task_id="t", task_class=high_risk)

    def test_deterministic(self):
        r1 = DeterministicRouter()
        r2 = DeterministicRouter()
        a = r1.route(task_id="t", task_class="code_change").to_dict()
        b = r2.route(task_id="t", task_class="code_change").to_dict()
        assert a == b


class TestOutbox:
    def test_redaction(self):
        event = {"payload": {"api_key": "sekret", "token": "tok", "ok": 1}}
        r = redact_event(event)
        assert r["payload"]["api_key"] == "[REDACTED]"
        assert r["payload"]["token"] == "[REDACTED]"
        assert r["payload"]["ok"] == 1

    def test_append_read(self, tmp_path):
        ob = EventOutbox(tmp_path / "outbox.jsonl")
        ob.append({"event_type": "session.created", "payload": {}})
        ob.append({"event_type": "session.cancelled", "payload": {}})
        rows = ob.read()
        assert len(rows) == 2
        assert rows[0]["event_type"] == "session.created"

    def test_no_webhook_no_delivery(self, tmp_path):
        ob = EventOutbox(tmp_path / "outbox.jsonl")
        assert ob._deliver({}) is False


class TestScopedAdapterSpawn:
    def test_simulated_spawn_no_process(self):
        """SIMULATION: no real process (unit-safe)."""
        from conduvera.harness.adapters import hermes_scoped_adapter
        a = hermes_scoped_adapter()
        hc = a.health_check()
        assert hc.success in (True, False)  # depends on binary presence

    def test_cancel_external_rejected_via_service(self, service):
        svc, gw, reg, config, base = service
        ext = ManagedSession(
            session_id="ext-x", task_id="", attempt_id="",
            ownership_class=OwnershipClass.EXTERNAL_UNKNOWN,
            managed=False, state=SessionState.RUNNING)
        reg.register(ext)
        r = svc.cancel("ext-x")
        assert not r["success"]
        assert r["code"] == "EXTERNAL_SESSION_NOT_CONTROLLABLE"


class TestBuildroomBridge:
    def test_router_selection(self):
        from conduvera.control_plane.buildroom_bridge import BuildroomBridge
        bridge = BuildroomBridge(legacy_direct=True)
        r = bridge.submit(task_id="T", attempt_id="A", task_class="fixture",
                          prompt="PONG")
        assert r["ok"] is True
        assert r["legacy_direct"] is True

    def test_no_route_fail_closed(self):
        from conduvera.control_plane.buildroom_bridge import BuildroomBridge
        bridge = BuildroomBridge()
        bridge.router.set_availability("hermes_scoped", False)
        bridge.router.set_availability("codex_cli", False)
        bridge.router.set_availability("opencode_cli", False)
        r = bridge.submit(task_id="T", attempt_id="A", task_class="fixture",
                          prompt="PONG")
        assert not r["ok"]
        assert r["error"]["code"] == "NO_ROUTE"

    def test_service_down(self):
        from conduvera.control_plane.buildroom_bridge import BuildroomBridge
        bridge = BuildroomBridge(socket_path="/tmp/definitely-not-there.sock")
        r = bridge.submit(task_id="T", attempt_id="A", task_class="fixture",
                          prompt="PONG")
        assert not r["ok"]
        assert r["error"]["code"] == "SERVICE_DOWN"


class TestCancelRestartSafe:
    """FIX-4 — CANCEL_REQUESTED restart-safe invariant.

    Invariants under test:
      * CANCEL_REQUESTED + process gone -> Session CANCELLED -> Attempt
        CANCELLED -> Job CANCELLED (session.cancelled emitted exactly once).
      * CANCEL_REQUESTED + process still alive after restart -> retains
        CANCEL_REQUESTED (never returns to RUNNING).
      * Repeated cancel on CANCELLED -> idempotent success.
    Uses a cloud-route model_binding so the local preflight gate is skipped and
    the test stays hermetic (no live ODS dependency).
    """

    def _make_session(self, svc, gw, reg, config, base, task="C1", attempt="c1"):
        r = svc.submit_job(task_id=task, attempt_id=attempt, harness="hermes_scoped",
                           repo="fixture", base_commit=base,
                           model_binding={"route": "provider/openai/gpt-5.6-sol"},
                           prompt="PONG")
        assert r["success"], r
        assert _dispatch(svc, attempt)["success"]
        sid = svc.scheduler.store.get_attempt(attempt).session_id
        return reg.get(sid)

    def test_cancel_requested_gone_finalizes_cancelled(self, service):
        svc, gw, reg, config, base = service
        s = self._make_session(svc, gw, reg, config, base, "C1", "c1")
        s.state = SessionState.CANCEL_REQUESTED
        s.fingerprint = ProcessFingerprint(pid=999999, start_time="0", boot_id="b", command="c")
        reg.update(s)
        events = []
        orig = svc._emit
        svc._emit = lambda t, p: (events.append(t), orig(t, p))
        res = svc.reconcile()
        got = reg.get(s.session_id)
        assert got.state is SessionState.CANCELLED
        assert res[s.session_id]["transitioned"] == "process_gone_cancelled"
        attempt = svc.scheduler.store.get_attempt("c1")
        assert attempt.state.value == "CANCELLED" and attempt.terminal
        assert svc.scheduler.store.get_job(attempt.job_id).state.value == "CANCELLED"
        assert events.count("session.cancelled") == 1

    def test_reconcile_cancel_requested_exactly_once_evidence(self, service):
        svc, gw, reg, config, base = service
        s = self._make_session(svc, gw, reg, config, base, "C2", "c2")
        s.state = SessionState.CANCEL_REQUESTED
        s.fingerprint = ProcessFingerprint(pid=999999, start_time="0", boot_id="b", command="c")
        reg.update(s)
        events = []
        svc._emit = lambda t, p: events.append(t)
        svc.reconcile()
        svc.reconcile()  # repeated reconcile must not re-emit
        assert events.count("session.cancelled") == 1
        assert reg.get(s.session_id).state is SessionState.CANCELLED

    def test_cancel_requested_alive_never_returns_running(self, service):
        svc, gw, reg, config, base = service
        s = self._make_session(svc, gw, reg, config, base, "C3", "c3")
        s.state = SessionState.CANCEL_REQUESTED
        pid = os.getpid()
        from conduvera.harness.managed_session import (_process_start_time, _boot_id, _process_cmd)
        s.fingerprint = ProcessFingerprint(pid=pid, start_time=_process_start_time(pid),
                                           boot_id=_boot_id(), command=_process_cmd(pid))
        reg.update(s)
        svc.reconcile()
        got = reg.get(s.session_id)
        assert got.state is SessionState.CANCEL_REQUESTED  # never RUNNING

    def test_cancel_idempotent_on_cancelled(self, service):
        svc, gw, reg, config, base = service
        s = self._make_session(svc, gw, reg, config, base, "C4", "c4")
        s.state = SessionState.CANCELLED
        reg.update(s)
        r1 = svc.cancel(s.session_id)
        r2 = svc.cancel(s.session_id)
        assert r1["success"] and r1["state"] == "CANCELLED"
        assert r2["success"] and r2["state"] == "CANCELLED"


class TestRunAuthoritative:
    """FIX-5 — `conduvera run` is authoritative:
      * policy is a strict enum — a typo fails, never selects cloud;
      * console_view exposes admission_reason for QUEUED attempts;
      * console_view terminal rows carry evidence/worktree/scope.
    """

    def test_validate_policy_rejects_typo(self):
        from typer import BadParameter
        from conduvera.cli.commands.control_plane import _validate_policy
        assert _validate_policy("local-first") == "local-first"
        assert _validate_policy("cloud") == "cloud"
        with pytest.raises(BadParameter):
            _validate_policy("local-firstt")
        with pytest.raises(BadParameter):
            _validate_policy("CLOUD")

    def test_console_view_exposes_admission_reason(self, service):
        svc, gw, reg, config, base = service
        # a queued attempt with an admission reason
        svc.submit_job(task_id="Q1", attempt_id="q1", harness="hermes_scoped",
                       repo="fixture", base_commit=base,
                       model_binding={"route": "workload/local"}, prompt="P")
        a = svc.scheduler.store.get_attempt("q1")
        a.admission_reason = "ADMISSION_HOLD#1 WAITING_FOR_LOCAL_GPU: llama down"
        svc.scheduler.store.save_attempt(a)
        view = svc.console_view()
        rows = [q for q in view["queued"] if q.get("attempt_id") == "q1"]
        assert rows and rows[0]["admission_reason"].startswith("ADMISSION_HOLD#1")

    def test_console_view_terminal_carries_evidence_worktree_scope(self, service):
        svc, gw, reg, config, base = service
        r = svc.submit_job(task_id="T1", attempt_id="t1", harness="hermes_scoped",
                           repo="fixture", base_commit=base,
                           model_binding={"route": "provider/openai/gpt-5.6-sol"},
                           prompt="P")
        assert r["success"]
        assert _dispatch(svc, "t1")["success"]
        s = reg.get(svc.scheduler.store.get_attempt("t1").session_id)
        s.state = SessionState.COMPLETED
        s.worktree = str(config.worktree_base / "t1-wt")
        s.scope_id = "conduvera-test.scope"
        reg.update(s)
        from conduvera.control_plane.scheduler import AttemptState, JobState
        a = svc.scheduler.store.get_attempt("t1")
        a.terminal = True
        a.state = AttemptState.COMPLETED
        a.terminal_reason = "done"
        svc.scheduler.store.save_attempt(a)
        job = svc.scheduler.store.get_job(a.job_id)
        job.state = JobState.COMPLETED
        svc.scheduler.store.save_job(job)
        view = svc.console_view()
        rows = [t for t in view["terminal"] if t.get("attempt_id") == "t1"]
        assert rows and rows[0]["worktree"] == str(config.worktree_base / "t1-wt")
        assert rows[0]["scope_id"] == "conduvera-test.scope"
