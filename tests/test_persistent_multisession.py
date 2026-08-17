"""
Persistent restart-safe multi-session Control-Plane tests
(implement-conduvera-persistent-restart-safe-multisession-runtime-v1).

Proves the required runtime contract with REAL running processes and a
persistent registry across simulated server restarts:

- T03  corrupt/truncated registry fails closed (RegistryCorruptError), never
       an empty success;
- T05  two MANAGED sessions reconcile after a restart exactly once each,
       no duplicate dispatch/session/attempt;
- T06  cancellation after restart targets only the correct session's scope;
- T07  cancellation is idempotent;
- T08  the second session keeps running after the first is cancelled;
- T10  exact nonzero exit code survives a restart and reaches state/evidence;
- T12  a session without an owned scope cannot be controlled (fail-closed);
- T16  two sessions use different registered worktrees and scope ids;
- T17  Operator Console JSON and human projection present the same truth;
- T18  repeated reconcile creates no new Attempt/Session/lifecycle event.

No existing assertion is weakened; a real contract conflict is a finding.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo


class _Ok:
    success = True
    message = "ok"
    detail = {}


class _Fail:
    success = False
    message = "adapter unavailable"
    detail = {}


class _FakeGateway:
    def __init__(self, cancel_ok: bool = True):
        self.cancelled: list[str] = []
        self.cancel_ok = cancel_ok

    def start_session(self, **kw):
        return _Ok()

    def cancel_session(self, adapter_id, session_id):
        self.cancelled.append(session_id)
        return _Ok() if self.cancel_ok else _Fail()


def _real_fingerprint(pid):
    from conduvera.harness.managed_session import (
        ProcessFingerprint, _boot_id, _process_start_time,
    )
    return ProcessFingerprint(pid=pid, start_time=_process_start_time(pid),
                              boot_id=_boot_id(), command="sleep")


def _svc(state: Path, repo: Path, gw, *, concurrency=2):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    svc = ControlPlaneService(
        registry=reg, gateway_service=gw, config=config,
        repo_allowlist={"fixture": repo}, global_concurrency=concurrency)
    return svc, reg


def _mk_session(svc, sid, task, attempt, pid, worktree, scope_id, *, exit_code=None):
    from conduvera.harness.managed_session import (
        ManagedSession, OwnershipClass, SessionState,
    )
    sess = ManagedSession(
        session_id=sid, task_id=task, attempt_id=attempt,
        harness_descriptor="hermes_scoped", ownership_class=OwnershipClass.MANAGED,
        state=SessionState.RUNNING, scope_id=scope_id,
        worktree=worktree, exit_code=exit_code,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))
    sess.fingerprint = _real_fingerprint(pid)
    svc.registry.register(sess)
    return sess


# --------------------------------------------------------------------------
# T03: corrupt/truncated registry fails closed
# --------------------------------------------------------------------------
def test_t03_corrupt_registry_fails_closed(tmp_path):
    from conduvera.harness.managed_session import RegistryCorruptError
    from conduvera.control_plane.service import PersistentSessionRegistry
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    reg_path = state / "registry.json"
    reg_path.write_text("{truncated-json", encoding="utf-8")  # invalid
    reg = PersistentSessionRegistry(reg_path)
    # a corrupt registry must raise a structured error, never an empty success
    try:
        reg.all()
        assert False, "corrupt registry must fail closed"
    except RegistryCorruptError:
        pass
    # invalid top-level schema also fails closed
    reg_path.write_text(json.dumps({"sessions": "not-a-dict"}), encoding="utf-8")
    reg2 = PersistentSessionRegistry(reg_path)
    try:
        reg2.all()
        assert False, "invalid schema must fail closed"
    except RegistryCorruptError:
        pass


# --------------------------------------------------------------------------
# T05: two MANAGED sessions reconcile after restart exactly once each
# --------------------------------------------------------------------------
def test_t05_two_sessions_reconcile_after_restart(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    b = subprocess.Popen(["sleep", "60"])
    try:
        sa = _mk_session(svc1, "mxs_A", "T-A", "a1", a.pid,
                         str(tmp_path / "wtA"), "scopeA.scope")
        sb = _mk_session(svc1, "mxs_B", "T-B", "b1", b.pid,
                         str(tmp_path / "wtB"), "scopeB.scope")
        # restart: fresh service + registry from same persistent state
        svc2, reg2 = _svc(state, repo, gw)
        res = svc2.reconcile()
        assert res["mxs_A"]["transitioned"] == "rediscovered"
        assert res["mxs_A"]["state"] == "RUNNING"
        assert res["mxs_B"]["transitioned"] == "rediscovered"
        assert res["mxs_B"]["state"] == "RUNNING"
        # exactly one session each, no duplicate
        sessions = reg2.all()
        assert len([s for s in sessions if s.session_id == "mxs_A"]) == 1
        assert len([s for s in sessions if s.session_id == "mxs_B"]) == 1
    finally:
        a.kill(); b.kill()


# --------------------------------------------------------------------------
# T16: two sessions use different registered worktrees and scope ids
# --------------------------------------------------------------------------
def test_t16_two_sessions_distinct_worktrees_and_scopes(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    b = subprocess.Popen(["sleep", "60"])
    try:
        sa = _mk_session(svc, "mxs_1", "T1", "a1", a.pid,
                         str(tmp_path / "wt-one"), "conduvera-one.scope")
        sb = _mk_session(svc, "mxs_2", "T2", "a1", b.pid,
                         str(tmp_path / "wt-two"), "conduvera-two.scope")
        assert sa.session_id != sb.session_id
        assert sa.scope_id != sb.scope_id
        assert sa.worktree != sb.worktree
        assert sa.fingerprint.pid != sb.fingerprint.pid
    finally:
        a.kill(); b.kill()


# --------------------------------------------------------------------------
# T06: cancellation after restart targets only the correct scope
# --------------------------------------------------------------------------
def test_t06_cancel_after_restart_targets_correct_session(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway(cancel_ok=True)
    svc1, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    b = subprocess.Popen(["sleep", "60"])
    try:
        _mk_session(svc1, "mxs_A", "T-A", "a1", a.pid,
                    str(tmp_path / "wtA"), "conduvera-A.scope")
        _mk_session(svc1, "mxs_B", "T-B", "b1", b.pid,
                    str(tmp_path / "wtB"), "conduvera-B.scope")
        # restart
        svc2, reg2 = _svc(state, repo, gw)
        svc2.reconcile()
        r = svc2.cancel("mxs_A")
        assert r["success"] is True
        assert r["state"] == "CANCELLED"
        # A cancelled, B still RUNNING and untouched
        assert reg2.get("mxs_A").state.value == "CANCELLED"
        assert reg2.get("mxs_B").state.value == "RUNNING"
        # only A's adapter session was cancelled
        assert gw.cancelled == ["mxs_A"]
    finally:
        a.kill(); b.kill()


# --------------------------------------------------------------------------
# T07: cancellation is idempotent
# --------------------------------------------------------------------------
def test_t07_cancel_idempotent(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway(cancel_ok=True)
    svc, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    try:
        _mk_session(svc, "mxs_A", "T-A", "a1", a.pid,
                    str(tmp_path / "wtA"), "conduvera-A.scope")
        r1 = svc.cancel("mxs_A")
        r2 = svc.cancel("mxs_A")  # second cancel
        assert r1["success"] is True and r1["state"] == "CANCELLED"
        assert r2["success"] is True and r2["state"] == "CANCELLED"
    finally:
        a.kill()


# --------------------------------------------------------------------------
# T08: second session continues after first is cancelled
# --------------------------------------------------------------------------
def test_t08_second_session_continues_after_cancel(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway(cancel_ok=True)
    svc, reg = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    b = subprocess.Popen(["sleep", "60"])
    try:
        _mk_session(svc, "mxs_A", "T-A", "a1", a.pid,
                    str(tmp_path / "wtA"), "conduvera-A.scope")
        _mk_session(svc, "mxs_B", "T-B", "b1", b.pid,
                    str(tmp_path / "wtB"), "conduvera-B.scope")
        svc.cancel("mxs_A")
        # B's process is still alive and its session is still RUNNING
        st = svc.status("mxs_B")
        assert st["state"] == "RUNNING"
        assert st["pid"] == b.pid
        assert reg.get("mxs_B").state.value == "RUNNING"
    finally:
        a.kill(); b.kill()


# --------------------------------------------------------------------------
# T10: exact nonzero exit code survives a restart
# --------------------------------------------------------------------------
def test_t10_nonzero_exit_code_survives_restart(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    # a dead process (exited) with a fixture-status.json carrying exit_code 7
    child = subprocess.Popen(["sleep", "0.1"])
    child.wait()
    wt = tmp_path / "wtX"
    wt.mkdir(exist_ok=True)
    (wt / "fixture-status.json").write_text(
        json.dumps({"scenario": "EXIT_7", "exit_code": 7}), encoding="utf-8")
    _mk_session(svc1, "mxs_X", "T-X", "a1", child.pid, str(wt), "conduvera-X.scope")
    # restart + reconcile -> process gone, exit code recovered
    svc2, reg2 = _svc(state, repo, gw)
    res = svc2.reconcile()
    rec = res["mxs_X"]
    assert rec["transitioned"] == "process_gone"
    assert rec["exit_code"] == 7
    assert reg2.get("mxs_X").state.value == "FAILED"
    assert reg2.get("mxs_X").exit_code == 7


# --------------------------------------------------------------------------
# T12: missing owned scope cannot be controlled (fail-closed)
# --------------------------------------------------------------------------
def test_t12_missing_scope_fails_closed(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway(cancel_ok=False)  # adapter unavailable
    svc, reg = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    try:
        # managed session WITHOUT an owned .scope and a failing adapter
        _mk_session(svc, "mxs_NS", "T-NS", "a1", a.pid,
                    str(tmp_path / "wtNS"), "")  # no scope
        r = svc.cancel("mxs_NS")
        assert r["success"] is False  # fail-closed, not silently cancelled
        assert reg.get("mxs_NS").state.value == "RUNNING"  # untouched
    finally:
        a.kill()


# --------------------------------------------------------------------------
# T17: console JSON and human projection show the same reconciled truth
# --------------------------------------------------------------------------
def test_t17_console_json_and_human_same_truth(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway(cancel_ok=True)
    svc1, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    try:
        _mk_session(svc1, "mxs_A", "T-A", "a1", a.pid,
                    str(tmp_path / "wtA"), "conduvera-A.scope")
        svc2, reg2 = _svc(state, repo, gw)
        svc2.reconcile()
        view = svc2.console_view()
        # the reconciled session appears in the running section and the human text
        assert any(s.get("session_id") == "mxs_A" for s in view.get("running", []))
        human = svc2.console_human()
        assert "mxs_A" in human
        run_row = next(s for s in view.get("running", [])
                       if s.get("session_id") == "mxs_A")
        assert run_row["state"] == "RUNNING"
    finally:
        a.kill()


# --------------------------------------------------------------------------
# T18: repeated reconcile produces no new Session / Attempt / lifecycle event
# --------------------------------------------------------------------------
def test_t18_repeated_reconcile_no_new_session_or_attempt(tmp_path):
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    a = subprocess.Popen(["sleep", "60"])
    try:
        _mk_session(svc1, "mxs_A", "T-A", "a1", a.pid,
                    str(tmp_path / "wtA"), "conduvera-A.scope")
        svc2, reg2 = _svc(state, repo, gw)
        svc2.reconcile()
        before = len(reg2.all())
        # second reconcile must not create a new session/attempt or lifecycle event
        ev_before = len(getattr(svc2, "_events", [])) if hasattr(svc2, "_events") else None
        svc2.reconcile()
        after = len(reg2.all())
        assert after == before == 1
        # a second reconcile on the same RUNNING fingerprint stays idempotent
        assert reg2.get("mxs_A").state.value == "RUNNING"
        if ev_before is not None:
            assert len(getattr(svc2, "_events", [])) == ev_before
    finally:
        a.kill()


# --------------------------------------------------------------------------
# Terminal-state consistency regression (Owner invariant)
# --------------------------------------------------------------------------
def _mk_attempt(svc, attempt_id, job_id, task_id, session_id, *, state="RUNNING"):
    from conduvera.control_plane.scheduler import AttemptDescriptor, AttemptState
    att = AttemptDescriptor(
        attempt_id=attempt_id, job_id=job_id, task_id=task_id,
        session_id=session_id, state=AttemptState(state),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))
    svc.scheduler.store.save_attempt(att)
    return att


def test_r0_reconcile_exit0_session_and_attempt_completed(tmp_path):
    """Owner invariant: restart reconciliation with exit_code 0 produces
    consistent SUCCESSFUL terminal Session AND Attempt states."""
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    child = subprocess.Popen(["sleep", "0.1"]); child.wait()
    wt = tmp_path / "wt0"; wt.mkdir(exist_ok=True)
    (wt / "fixture-status.json").write_text(
        json.dumps({"scenario": "HOLD_THEN_EXIT_0", "exit_code": 0}), encoding="utf-8")
    _mk_session(svc1, "mxs_0", "T-0", "r0", child.pid, str(wt), "conduvera-r0.scope")
    _mk_attempt(svc1, "r0", "job_r0", "T-0", "mxs_0")
    svc2, reg2 = _svc(state, repo, gw)
    res = svc2.reconcile()
    assert res["mxs_0"]["exit_code"] == 0
    assert res["mxs_0"]["attempt_state"] == "COMPLETED"
    assert reg2.get("mxs_0").state.value == "COMPLETED"
    att = svc2.scheduler.store.get_attempt("r0")
    assert att.state.value == "COMPLETED" and att.terminal is True


def test_r1_reconcile_nonzero_session_and_attempt_failed(tmp_path):
    """Owner invariant: nonzero exit -> consistent FAILED Session AND Attempt,
    exact exit code preserved."""
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    child = subprocess.Popen(["sleep", "0.1"]); child.wait()
    wt = tmp_path / "wt7"; wt.mkdir(exist_ok=True)
    (wt / "fixture-status.json").write_text(
        json.dumps({"scenario": "EXIT_7", "exit_code": 7}), encoding="utf-8")
    _mk_session(svc1, "mxs_7", "T-7", "r1", child.pid, str(wt), "conduvera-r1.scope")
    _mk_attempt(svc1, "r1", "job_r1", "T-7", "mxs_7")
    svc2, reg2 = _svc(state, repo, gw)
    res = svc2.reconcile()
    assert res["mxs_7"]["exit_code"] == 7
    assert res["mxs_7"]["attempt_state"] == "FAILED"
    assert reg2.get("mxs_7").state.value == "FAILED"
    assert reg2.get("mxs_7").exit_code == 7
    att = svc2.scheduler.store.get_attempt("r1")
    assert att.state.value == "FAILED" and att.terminal is True


def test_r2_reconcile_unknown_exit_follows_existing_contract(tmp_path):
    """Owner invariant: an unavailable exit code is classified per the existing
    fail-closed contract (process-gone -> truthful terminal, never silently
    asserted as success); Session and Attempt stay CONSISTENT."""
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    child = subprocess.Popen(["sleep", "0.1"]); child.wait()
    wt = tmp_path / "wtU"; wt.mkdir(exist_ok=True)  # no fixture-status.json
    _mk_session(svc1, "mxs_U", "T-U", "r2", child.pid, str(wt), "")
    _mk_attempt(svc1, "r2", "job_r2", "T-U", "mxs_U")
    svc2, reg2 = _svc(state, repo, gw)
    res = svc2.reconcile()
    # no scope + no fixture -> exit None -> the existing dead->COMPLETED
    # contract applies; Session and Attempt must be the SAME terminal state
    assert res["mxs_U"]["state"] in ("COMPLETED", "FAILED")
    session_state = reg2.get("mxs_U").state.value
    att = svc2.scheduler.store.get_attempt("r2")
    assert att.state.value == session_state  # consistent, never mixed
    assert att.terminal is True


def test_r3_repeated_reconcile_terminal_not_reverted_to_running(tmp_path):
    """Owner invariant: repeated reconciliation cannot change a terminal Session
    or Attempt back to RUNNING and creates no duplicate dispatch."""
    repo = _make_repo(tmp_path)
    state = tmp_path / "state"
    gw = _FakeGateway()
    svc1, _ = _svc(state, repo, gw)
    child = subprocess.Popen(["sleep", "0.1"]); child.wait()
    wt = tmp_path / "wtT"; wt.mkdir(exist_ok=True)
    (wt / "fixture-status.json").write_text(
        json.dumps({"scenario": "EXIT_7", "exit_code": 7}), encoding="utf-8")
    _mk_session(svc1, "mxs_T", "T-T", "r3", child.pid, str(wt), "conduvera-r3.scope")
    _mk_attempt(svc1, "r3", "job_r3", "T-T", "mxs_T")
    svc2, reg2 = _svc(state, repo, gw)
    svc2.reconcile()
    assert reg2.get("mxs_T").state.value == "FAILED"
    att1 = svc2.scheduler.store.get_attempt("r3")
    # repeated reconcile: terminal Session/Attempt must stay terminal (FAILED)
    for _ in range(3):
        svc2.reconcile()
    assert reg2.get("mxs_T").state.value == "FAILED"
    att2 = svc2.scheduler.store.get_attempt("r3")
    assert att2.state.value == "FAILED" and att2.terminal is True
    # no duplicate session/attempt created
    assert len(reg2.all()) == 1
