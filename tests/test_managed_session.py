"""Managed harness session tests (MXOS-SAFETY-1 / MXOS-RUNTIME-1 vertical slice).

Testet die ManagedSession-Runtime: Lifecycle, Fingerprint-basierte Status,
Cancel nur an MANAGED, External-No-Adoption, PID-Reuse -> LOST, atomare
0600-Registry, Evidence-Hash-Validierung, Cleanup, unveraenderte externe
Prozessliste.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from conduvera.evidence.contract import EventEnvelope, ValidationError
from conduvera.harness.managed_session import (
    ManagedJob,
    ManagedSession,
    ManagedSessionRegistry,
    OwnershipClass,
    ProcessFingerprint,
    SessionState,
)
from conduvera.harness.managed_session_runtime import (
    ManagedSessionRuntime,
)


class _FakeAdapterResult:
    def __init__(self, success: bool, message: str, detail: dict | None = None):
        self.success = success
        self.message = message
        self.detail = detail or {}


class _FakeGateway:
    """Deterministic gateway double for lifecycle tests (no real process)."""

    def __init__(self):
        self.started = []
        self.cancelled = []
        self.status_calls = 0
        self.fingerprint: ProcessFingerprint | None = None
        self.pid = 4242

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        self.started.append({"adapter": adapter_id, "worktree": worktree, "task": task})
        fp = self.fingerprint or ProcessFingerprint(
            pid=self.pid, start_time="12345", boot_id="boot-test", command="fake-hermes -z")
        return _FakeAdapterResult(True, "started", {
            "session_id": f"mxfix_{task}",
            "pid": fp.pid, "pgid": fp.pid,
            "status": "running", "execution_mode": config.get("execution_mode"),
        })

    def status_session(self, adapter_id, session_id):
        self.status_calls += 1
        return _FakeAdapterResult(True, "running", {"status": "running"})

    def cancel_session(self, adapter_id, session_id):
        self.cancelled.append(session_id)
        return _FakeAdapterResult(True, "cancelled", {"status": "cancelled"})


@pytest.fixture()
def runtime(tmp_path):
    reg = ManagedSessionRegistry(tmp_path / "registry.json")
    gw = _FakeGateway()
    rt = ManagedSessionRuntime(
        registry=reg,
        gateway_service=gw,
        worktree_base=tmp_path / "wts",
    )
    return rt, gw, reg


def _job(tmp_path, **kw: Any) -> ManagedJob:
    base: dict[str, Any] = dict(
        task_id="TASK-001",
        attempt_id="attempt-001",
        repo="fixture-repo",
        base_commit="63fb334cc02ee101f95c48e41de9dcfcfd5f6f9c",
        worktree=str(tmp_path / "wt-slice"),
        harness_descriptor="hermes-adapter.v1",
        model_binding={"route": "workload/local"},
        timeout_s=30.0,
    )
    base.update(kw)
    return ManagedJob(**base)


class TestManagedStartLifecycle:
    def test_start_creates_managed_session(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="TASK-001", attempt_id="attempt-001",
            repo="fixture-repo", base_commit="63fb334",
            harness_descriptor="hermes-adapter.v1",
            model_binding={"route": "workload/local"},
            worktree=str(tmp_path / "wt-live"),
        )
        assert res.success
        session = reg.get(res.detail["session"]["session_id"])
        assert session is not None
        assert session.ownership_class is OwnershipClass.MANAGED
        assert session.managed is True
        assert session.state is SessionState.RUNNING
        assert session.fingerprint is not None
        assert session.fingerprint.pid > 0
        # Dedicated worktree exists
        assert Path(session.worktree).is_dir()

    def test_state_transitions_created_to_running(self, runtime, tmp_path):
        rt, gw, reg = runtime
        job = _job(tmp_path)
        session = ManagedSession.create(job=job)
        assert session.state is SessionState.CREATED
        assert session.created_at != ""
        assert session.session_id.startswith("mxs_")
        assert session.instance_id != ""


class TestStatusFingerprint:
    def test_running_status_uses_fingerprint(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="T-1", attempt_id="a1", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt1"),
        )
        sid = res.detail["session"]["session_id"]
        # Überleben: Fingerprint des Fake-Prozesses wird beim Start gesetzt;
        # beim Status-Aufruf muss der Prozess-Fingerprint übereinstimmen —
        # wir simulieren das durch Registrieren eines "lebenden" Prozesses.
        session = reg.get(sid)
        # Erzeuge einen echten, stabilen Marker-Prozess (sleep) für den Fingerprint
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            fp = ProcessFingerprint(
                pid=proc.pid, start_time="", boot_id="boot-x", command="sleep 30")
            session.fingerprint = fp
            reg.update(session)
            # PID-Reuse-Simulation: gleiche PID, anderes start_time -> LOST
            session2 = reg.get(sid)
            session2.fingerprint = ProcessFingerprint(
                pid=proc.pid, start_time="DIFFERENT", boot_id="boot-x",
                command="sleep 30")
            reg.update(session2)
            r = rt.status(sid)
            assert r.success
            assert r.detail["state"] in ("LOST", "COMPLETED")
        finally:
            proc.kill()
            proc.wait()

    def test_pid_reuse_marks_lost(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="T-2", attempt_id="a2", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt2"),
        )
        sid = res.detail["session"]["session_id"]
        session = reg.get(sid)
        # PID-Reuse: ein neuer Prozess besetzt dieselbe PID, aber start_time
        # und command unterscheiden sich -> LOST, nie Kontrolle über den neuen
        # Prozess. Wir nutzen einen echten Prozess (sleep) und simulieren den
        # alten Fingerprint mit anderem start_time.
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            real_start = _proc_start(proc.pid)
            assert real_start != ""
            session.fingerprint = ProcessFingerprint(
                pid=proc.pid, start_time="000000", boot_id="boot-x", command="old-cmd")
            reg.update(session)
            r = rt.status(sid)
            assert r.success
            assert r.detail["state"] == "LOST"
            # Der neue Prozess wurde NICHT kontrolliert/beendet
            assert proc.poll() is None
        finally:
            proc.kill()
            proc.wait()


class TestCancelManagedOnly:
    def test_cancel_managed(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="T-3", attempt_id="a3", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt3"),
        )
        sid = res.detail["session"]["session_id"]
        r = rt.cancel(sid)
        assert r.success
        session = reg.get(sid)
        assert session.state is SessionState.CANCELLED
        assert session.ended_at != ""

    def test_cancel_rejects_external_manual_observed(self, runtime, tmp_path):
        rt, gw, reg = runtime
        ext = rt.observe_external(
            pid=77777,
            classification=OwnershipClass.EXTERNAL_MANUAL_OBSERVED,
            label="manual-hermes",
        )
        assert ext.managed is False
        assert ext.ownership_class is OwnershipClass.EXTERNAL_MANUAL_OBSERVED
        r = rt.cancel(ext.session_id)
        assert not r.success
        assert r.detail["code"] == "EXTERNAL_SESSION_NOT_CONTROLLABLE"

    def test_cancel_rejects_external_unknown(self, runtime, tmp_path):
        rt, gw, reg = runtime
        ext = rt.observe_external(
            pid=77778, classification=OwnershipClass.EXTERNAL_UNKNOWN,
            label="unknown-session")
        r = rt.cancel(ext.session_id)
        assert not r.success
        assert r.detail["code"] == "EXTERNAL_SESSION_NOT_CONTROLLABLE"

    def test_external_adoption_impossible(self, runtime, tmp_path):
        rt, gw, reg = runtime
        ext = rt.observe_external(
            pid=77779, classification=OwnershipClass.EXTERNAL_UNKNOWN)
        # Der Runtime hat KEINE Adoptions-API; selbst ein direkter
        # Registry-Update kann ownership_class nicht auf MANAGED ändern
        # (Invariante wird durch die Runtime-Operationen garantiert).
        session = reg.get(ext.session_id)
        assert session.ownership_class is not OwnershipClass.MANAGED
        assert session.managed is False
        assert session.scope_id.startswith("ext-")


class TestRegistryAtomic:
    def test_atomic_0600(self, tmp_path):
        reg = ManagedSessionRegistry(tmp_path / "reg.json")
        job = _job(tmp_path)
        s = ManagedSession.create(job=job)
        reg.register(s)
        assert reg.permission_ok()
        mode = (tmp_path / "reg.json").stat().st_mode & 0o777
        assert mode == 0o600

    def test_roundtrip(self, tmp_path):
        reg = ManagedSessionRegistry(tmp_path / "reg.json")
        job = _job(tmp_path)
        s = ManagedSession.create(job=job)
        s.state = SessionState.RUNNING
        s.fingerprint = ProcessFingerprint(pid=1, start_time="1", boot_id="b", command="c")
        reg.register(s)
        got = reg.get(s.session_id)
        assert got.state is SessionState.RUNNING
        assert got.fingerprint.pid == 1


class TestEvidenceHashes:
    def test_event_hashes_validate(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="T-4", attempt_id="a4", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt4"),
        )
        assert res.success
        sid = res.detail["session"]["session_id"]
        rt.status(sid)
        rt.cancel(sid)
        chain = rt.evidence_chain()
        types = [e["event_type"] for e in chain]
        assert "session.created" in types
        assert "session.start.requested" in types
        assert "session.started" in types
        assert "session.status.observed" in types
        assert "session.cancel.requested" in types
        assert "session.cancelled" in types
        assert "session.cleanup.completed" in types
        # Jedes Event validiert gegen den Envelope-Contract (Hash-Check)
        for e in chain:
            env = EventEnvelope.from_dict(e)
            assert env.schema_version == "MXOS-EVIDENCE-1.0.0"
            assert env.event_hash and env.event_hash.startswith("sha256:")

    def test_hash_validation_rejects_tampered(self, runtime, tmp_path):
        rt, gw, reg = runtime
        rt.start(
            task_id="T-5", attempt_id="a5", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt5"),
        )
        chain = rt.evidence_chain()
        e = dict(chain[0])
        e["payload"] = {"tampered": True}
        with pytest.raises((ValidationError, ValueError)):
            EventEnvelope.from_dict(e)


class TestCleanupAndExternalUntouched:
    def test_cleanup_only_session_owned(self, runtime, tmp_path):
        rt, gw, reg = runtime
        res = rt.start(
            task_id="T-6", attempt_id="a6", repo="r",
            base_commit="63fb334", harness_descriptor="h",
            model_binding={}, worktree=str(tmp_path / "wt6"),
        )
        assert res.success
        sid = res.detail["session"]["session_id"]
        rt.cancel(sid)
        session = reg.get(sid)
        # Cleanup-Evidence verweist auf den Session-Worktree; die Registry
        # selbst bleibt (Session-Record ist Evidence, nicht weggeworfen).
        assert Path(session.worktree).is_dir()
        assert reg.get(sid).state is SessionState.CANCELLED

    def test_external_processes_unchanged(self, runtime, tmp_path):
        rt, gw, reg = runtime
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            before = (proc.pid, _proc_start(proc.pid))
            ext = rt.observe_external(
                pid=proc.pid, classification=OwnershipClass.EXTERNAL_MANUAL_OBSERVED,
                label="manual")
            # cancel lehnt ab, also wird der externe Prozess nie signalisiert
            r = rt.cancel(ext.session_id)
            assert not r.success
            after = (proc.pid, _proc_start(proc.pid))
            assert before == after
            assert proc.poll() is None  # lebt weiter
        finally:
            proc.kill()
            proc.wait()


def _proc_start(pid: int) -> str:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""
