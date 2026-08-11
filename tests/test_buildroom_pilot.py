"""Buildroom operational pilot tests (BUILDROOM-PILOT-V1).

Tests the full queue -> dispatch -> monitor -> terminal loop:

- FIFO queue with capacity 1: A runs, B stays queued, B auto-starts after A;
- atomic claims (one owner only) and expired-claim recovery;
- monitor: normal completion, timeout escalation, exactly-once terminal events;
- repository allowlist + identifier normalization (path traversal rejected);
- prompt redaction (raw prompts never persisted);
- outbox durable delivery + idempotency.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from conduvera.control_plane.engine import ControlPlaneEngine
from conduvera.control_plane.outbox import EventOutbox
from conduvera.control_plane.scheduler import (
    AttemptState,
    JobState,
)
from conduvera.control_plane.service import ControlPlaneService, _normalize_identifiers
from conduvera.harness.managed_session import (
    ManagedSession,
    OwnershipClass,
    ProcessFingerprint,
    SessionState,
)


class _R:
    def __init__(self, success: bool, message: str, detail: dict | None = None):
        self.success = success
        self.message = message
        self.detail = detail or {}


class _FakeGateway:
    """Fake gateway with controllable session outcomes."""

    def __init__(self):
        self.n = 90000
        self.pid_alive = True
        self.exit_code = 0

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        self.n += 1
        return _R(True, "ok", {"session_id": f"mxfix_{adapter_id}_{self.n}",
                               "pid": self.n, "pgid": self.n, "status": "running"})

    def cancel_session(self, adapter_id, session_id):
        return _R(True, "cancelled", {"status": "cancelled"})

    def collect_evidence(self, adapter_id, session_id):
        return {"exit_code": self.exit_code, "schema_version": "MXOS-EVIDENCE-1.0.0"}

    def _load_adapter(self, adapter_id):
        class A:
            def health_check(self):
                return _R(True, "ok")
        return A()


@pytest.fixture()
def svc(tmp_path):
    from conduvera.control_plane.service import ControlPlaneConfig, PersistentSessionRegistry
    config = ControlPlaneConfig.default(state_dir=tmp_path / "state")
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _FakeGateway()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    service = ControlPlaneService(
        registry=reg, gateway_service=gw, config=config,
        repo_path=repo, repo_allowlist={"fixture": repo},
        global_concurrency=1, per_harness_limits={"hermes_scoped": 1},
    )
    return service, gw, base


class TestFifoQueueCapacityOne:
    def test_capacity_one_a_runs_b_queued(self, svc):
        """Job A starts, job B stays queued while A runs (capacity 1)."""
        service, gw, base = svc
        ra = service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                                repo="fixture", base_commit=base, model_binding={},
                                prompt="PONG", timeout_s=300)
        assert ra["success"]
        # A claimed + dispatched
        assert service.scheduler.claim("A1", dispatcher_id="t") is not None
        da = service.dispatch_claimed("A1")
        assert da["success"]
        # B submitted -> stays QUEUED (A RUNNING, capacity 1)
        rb = service.submit_job(task_id="B", attempt_id="B1", harness="hermes_scoped",
                                repo="fixture", base_commit=base, model_binding={},
                                prompt="PONG", timeout_s=300)
        assert rb["success"]
        b = service.scheduler.store.get_attempt("B1")
        assert b.state is AttemptState.QUEUED
        assert service.scheduler.can_start("hermes_scoped")[0] is False

    def test_b_starts_after_a_releases(self, svc):
        """B auto-starts when A ends (capacity release triggers next queued)."""
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={},
                           prompt="PONG", timeout_s=300)
        assert service.scheduler.claim("A1", dispatcher_id="t") is not None
        assert service.dispatch_claimed("A1")["success"]
        service.submit_job(task_id="B", attempt_id="B1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={},
                           prompt="PONG", timeout_s=300)
        assert service.scheduler.store.get_attempt("B1").state is AttemptState.QUEUED
        # A ends -> engine finalizes -> capacity released
        sid_a = service.scheduler.store.get_attempt("A1").session_id
        sess = service.registry.get(sid_a)
        engine = ControlPlaneEngine(service=service, scheduler=service.scheduler,
                                    registry=service.registry, poll_interval_s=0.1)
        engine._running = True
        engine._finalize(sess, service.scheduler.store.get_attempt("A1"), sid_a,
                         SessionState.COMPLETED, AttemptState.COMPLETED,
                         JobState.COMPLETED, "done", 0, "session.completed")
        assert service.scheduler.can_start("hermes_scoped")[0] is True
        # dispatcher picks B automatically
        engine._dispatch_once()
        b = service.scheduler.store.get_attempt("B1")
        assert b.state in (AttemptState.CLAIMED, AttemptState.RUNNING)


class TestClaims:
    def test_one_owner_only(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={}, prompt="P")
        c1 = service.scheduler.claim("A1", dispatcher_id="d1")
        assert c1 is not None
        c2 = service.scheduler.claim("A1", dispatcher_id="d2")
        assert c2 is None  # exactly one owner

    def test_release_returns_to_queue(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={}, prompt="P")
        service.scheduler.claim("A1", dispatcher_id="d1")
        service.scheduler.release_claim("A1")
        assert service.scheduler.store.get_attempt("A1").state is AttemptState.QUEUED


class TestMonitor:
    def test_process_gone_completes(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={}, prompt="P")
        service.scheduler.claim("A1", dispatcher_id="t")
        service.dispatch_claimed("A1")
        sid = service.scheduler.store.get_attempt("A1").session_id
        sess = service.registry.get(sid)
        # Fingerprint with a dead PID -> process gone -> COMPLETED
        sess.fingerprint = ProcessFingerprint(pid=999999, start_time="0",
                                              boot_id="b", command="c")
        service.registry.update(sess)
        engine = ControlPlaneEngine(service=service, scheduler=service.scheduler,
                                    registry=service.registry, poll_interval_s=0.1)
        engine._running = True
        engine._monitor_once()
        a = service.scheduler.store.get_attempt("A1")
        assert a.state is AttemptState.COMPLETED
        assert a.terminal is True
        assert service.scheduler.can_start("hermes_scoped")[0] is True

    def test_timeout_escalation(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={},
                           prompt="P", timeout_s=0.01)
        service.scheduler.claim("A1", dispatcher_id="t")
        service.dispatch_claimed("A1")
        sid = service.scheduler.store.get_attempt("A1").session_id
        sess = service.registry.get(sid)
        # Live process (this test process) with a long-past deadline:
        # fingerprint matches a real running process -> timeout path applies.
        from conduvera.harness.managed_session import (
            _boot_id, _process_cmd, _process_start_time)
        pid = os.getpid()
        sess.fingerprint = ProcessFingerprint(
            pid=pid, start_time=_process_start_time(pid), boot_id=_boot_id(),
            command=_process_cmd(pid))
        sess.started_at = "2000-01-01T00:00:00+00:00"  # deadline long past
        service.registry.update(sess)
        engine = ControlPlaneEngine(service=service, scheduler=service.scheduler,
                                    registry=service.registry, poll_interval_s=0.1,
                                    timeout_grace_s=0.05)
        engine._running = True
        engine._monitor_once()
        a = service.scheduler.store.get_attempt("A1")
        assert a.state is AttemptState.TIMED_OUT
        assert a.terminal is True

    def test_terminal_event_exactly_once(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={}, prompt="P")
        service.scheduler.claim("A1", dispatcher_id="t")
        service.dispatch_claimed("A1")
        sid = service.scheduler.store.get_attempt("A1").session_id
        sess = service.registry.get(sid)
        sess.fingerprint = ProcessFingerprint(pid=999999, start_time="0",
                                              boot_id="b", command="c")
        service.registry.update(sess)
        engine = ControlPlaneEngine(service=service, scheduler=service.scheduler,
                                    registry=service.registry, poll_interval_s=0.1)
        engine._running = True
        engine._monitor_once()
        engine._monitor_once()  # duplicate delivery attempt
        assert sid in engine._emitted_terminal
        # terminal attempt stays terminal (no double transition)
        a = service.scheduler.store.get_attempt("A1")
        assert a.state is AttemptState.COMPLETED

    def test_external_never_monitored(self, svc):
        service, gw, base = svc
        ext = ManagedSession(
            session_id="ext1", task_id="", attempt_id="",
            ownership_class=OwnershipClass.EXTERNAL_MANUAL_OBSERVED,
            managed=False, state=SessionState.RUNNING,
            fingerprint=ProcessFingerprint(pid=999999, start_time="0",
                                           boot_id="b", command="c"))
        service.registry.register(ext)
        engine = ControlPlaneEngine(service=service, scheduler=service.scheduler,
                                    registry=service.registry, poll_interval_s=0.1)
        engine._running = True
        engine._monitor_once()
        assert service.registry.get("ext1").state is SessionState.RUNNING  # untouched


class TestRepoBoundary:
    def test_repo_not_allowlisted(self, svc):
        service, gw, base = svc
        r = service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                               repo="evil", base_commit=base, model_binding={}, prompt="P")
        assert not r["success"]
        assert r["code"] == "REPO_NOT_ALLOWED"

    def test_identifier_normalization_rejects_traversal(self):
        with pytest.raises(ValueError):
            _normalize_identifiers("../etc", "a1")
        with pytest.raises(ValueError):
            _normalize_identifiers("a/b", "a1")
        with pytest.raises(ValueError):
            _normalize_identifiers("a", "a\\b")
        assert _normalize_identifiers("TASK-1", "att_2") == ("TASK-1", "att_2")

    def test_duplicate_attempt_rejected(self, svc):
        service, gw, base = svc
        r1 = service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                                repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert r1["success"]
        r2 = service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                                repo="fixture", base_commit=base, model_binding={}, prompt="P")
        assert not r2["success"]
        assert r2["code"] == "DUPLICATE_ATTEMPT"


class TestRedaction:
    def test_no_raw_prompt_in_store(self, svc):
        service, gw, base = svc
        service.submit_job(task_id="A", attempt_id="A1", harness="hermes_scoped",
                           repo="fixture", base_commit=base, model_binding={
                               "api_key": "sekret-123", "route": "workload/local"},
                           prompt="GEHEIM-PROMPT mit token abc123", timeout_s=10)
        raw = service.scheduler.store.path.read_text(encoding="utf-8")
        assert "GEHEIM-PROMPT" not in raw
        assert "abc123" not in raw
        assert "sekret-123" not in raw
        assert "sha256:" in raw  # hash reference present

    def test_outbox_durable_delivery(self, tmp_path):
        ob = EventOutbox(tmp_path / "outbox.jsonl", webhook_url="http://127.0.0.1:1/nope")
        ob.append({"event_type": "session.completed", "event_id": "mxev_1", "payload": {}})
        # persisted BEFORE delivery attempt (never ack before durable)
        assert (tmp_path / "outbox.jsonl").is_file()
        rows = ob.read()
        assert rows[0]["delivery_state"] in ("failed", "pending")
        assert rows[0]["idempotency_key"] == "mxev_1"
        # no webhook -> no delivery -> stays pending
        ob2 = EventOutbox(tmp_path / "o2.jsonl")
        ob2.append({"event_type": "job.accepted", "event_id": "mxev_2", "payload": {}})
        assert ob2.read()[0]["delivery_state"] == "pending"