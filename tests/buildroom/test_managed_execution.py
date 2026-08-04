"""Integration tests: ManagedBuildroomCaller with the three helpers.

Covers the mandatory scenarios A-F and the DOD-13 negative tests, using a
RecordingAdapter (SIMULATION) so no real process is spawned. The productive
LIVE path is proven separately by fixtures/live/verify_managed_live.py.

Scenarios:
A. successful live-like path (task -> binding -> policy -> gateway ->
   hermes -> evidence -> reconciliation -> no hold)
B. backend fail-closed (disabled backend -> no spawn)
C. unknown backend -> no spawn, policy decision in evidence
D. no-progress threshold (1 -> 2 -> 3 -> HOLD_FOR_BOSS)
E. progress reset (new evidence -> count 0, reset_reason NEW_EVIDENCE)
F. binding safety (wrong current board ignored; replacement; clear)
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.managed_execution import ManagedBuildroomCaller  # noqa: E402
from curaops.buildroom.task_binding import TaskBinding, binding_for_phase  # noqa: E402
from curaops.harness.registry import ExecutionMode  # noqa: E402

FIXTURES = ROOT / "fixtures"
ROUTE_MANIFEST = FIXTURES / "ods/route-manifest.fixture.yaml"

CANONICAL_POLICY = """execution_backends:
  native:
    enabled: true
  codex_cli:
    enabled: false
    status: disabled_by_owner
    requires_explicit_owner_activation: true
  opencode_cli:
    enabled: false
    status: disabled_by_owner
    requires_explicit_owner_activation: true
"""


class RecordingAdapter:
    """Protocol-conforming recording adapter (SIMULATION)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.session_id = "SES-TEST-0001"

    def start_session(self, config=None, **kwargs):
        self.calls.append({"op": "start", "config": config, **kwargs})
        return _AdapterResult(True, "started", {
            "session_id": self.session_id, "pid": 4242, "pgid": 4242,
            "route": (config or {}).get("route", "workload/local"),
        })

    def status_session(self, session_id):
        return _AdapterResult(True, "running", {"session_id": session_id})

    def cancel_session(self, session_id):
        return _AdapterResult(True, "cancelled", {"session_id": session_id})

    def timeout_session(self, session_id):
        return _AdapterResult(True, "timed out", {"session_id": session_id})

    def await_completion(self, session_id, timeout_policy=None):
        return _AdapterResult(True, "completed", {
            "session_id": session_id, "status": "completed",
        })

    def collect_evidence(self, session_id):
        return {
            "session_id": session_id,
            "ok": True,
            "response": "CONDUVERA_FIXTURE_OK",
            "output_files": ["/tmp/out.txt"],
        }


class _AdapterResult:
    def __init__(self, success, message, detail):
        self.success = success
        self.message = message
        self.detail = detail


def make_caller(tmp_path, *, policy=..., threshold=3, adapter=None, **kw):
    state_path = tmp_path / "state.json"
    if policy is ...:
        policy = CANONICAL_POLICY
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(policy, encoding="utf-8")
    return ManagedBuildroomCaller(
        state_path=state_path,
        route_manifest=ROUTE_MANIFEST,
        adapter=adapter or RecordingAdapter(),
        producer={"name": "conduvera-core", "version": "0.1.0"},
        execution_mode=ExecutionMode.SIMULATION.value,
        policy_path=policy_path,
        threshold=threshold,
        **kw,
    )


# -- A: Erfolgreicher Pfad ---------------------------------------------------

def test_a_successful_path(tmp_path):
    caller = make_caller(tmp_path)
    result = caller.execute(task_description="test task A")
    assert result.status == "completed"
    assert result.policy_decision["decision"] == "ALLOWED"
    assert result.reconciliation["count"] == 1
    assert result.reconciliation["terminal_hold"] is False
    # TaskBinding stored + reloaded identity verified
    state = json.loads(caller.state_path.read_text())
    assert state["task_bindings"]["BUILDER"]["task_id"].startswith("t_")
    assert state["task_bindings"]["BUILDER"]["board"] == "conduvera"
    # Evidence file exists
    assert len(result.evidence_paths) == 1
    ev = json.loads(Path(result.evidence_paths[0]).read_text())
    assert ev["schema"] == "MXOS-EVIDENCE-1.0.0"
    assert ev["goal_id"] == "CONDUVERA-FIXTURE-001"
    # Full state persisted
    assert "call_trace" in state


# -- B: Backend fail-closed --------------------------------------------------

def test_b_disabled_backend_no_spawn(tmp_path):
    adapter = RecordingAdapter()
    caller = make_caller(tmp_path, adapter=adapter)
    result = caller.execute(task_description="task B", backend="codex_cli")
    assert result.status == "policy_blocked"
    assert result.policy_decision["decision"] == "BACKEND_DISABLED_BY_OWNER"
    assert adapter.calls == []  # KEIN Harness-Spawn, keine PID/PGID
    assert result.session_id == ""  # keine Session angelegt
    # Kein teilweise angelegter Versuch, der als erfolgreich erscheint
    state = json.loads(caller.state_path.read_text())
    assert "call_trace" not in state
    assert result.final_status_readable.startswith("BLOCKED")


# -- C: Unbekanntes Backend --------------------------------------------------

def test_c_unknown_backend_no_spawn(tmp_path):
    adapter = RecordingAdapter()
    caller = make_caller(tmp_path, adapter=adapter)
    result = caller.execute(task_description="task C", backend="claude")
    assert result.status == "policy_blocked"
    assert result.policy_decision["decision"] == "UNKNOWN_BACKEND"
    assert adapter.calls == []
    # Policy-Entscheidung in Events (Evidence)
    events = result.events
    assert any("policy_blocked" in e["event_type"] for e in events)
    assert any(e["payload"].get("decision") == "UNKNOWN_BACKEND" for e in events)


# -- D: No-Progress-Schwelle -------------------------------------------------

def test_d_no_progress_threshold_sequence(tmp_path):
    """Identische Reconciliation (gleiche Task) -> Zähler 1→2→3 -> Hold."""
    caller = make_caller(tmp_path, threshold=3)
    kwargs = dict(task_description="task D", task_id="t_deadbeef")
    r1 = caller.execute(**kwargs)
    r2 = caller.execute(**kwargs)
    r3 = caller.execute(**kwargs)
    assert (r1.reconciliation["count"], r2.reconciliation["count"],
            r3.reconciliation["count"]) == (1, 2, 3)
    assert r1.status == "completed" and r2.status == "completed"
    assert r3.status == "hold"
    state = json.loads(caller.state_path.read_text())
    assert state["status"] == "HOLD_FOR_BOSS"
    assert state["blocker"] == "REPEATED_NO_PROGRESS"
    assert state["root_blocker"] == "TASK_DONE_BUT_NO_EVIDENCE"
    assert state["no_progress"]["count"] == 3
    # Keine zusätzliche Session nach terminalem Hold
    assert r3.reconciliation["terminal_hold"] is True


# -- E: Progress-Reset -------------------------------------------------------

def test_e_progress_reset(tmp_path):
    caller = make_caller(tmp_path, threshold=3)
    caller.execute(task_description="task E")
    caller.execute(task_description="task E")
    r3 = caller.execute(task_description="task E", evidence_fingerprint="sha256:new-evidence")
    assert r3.reconciliation["count"] == 0
    state = json.loads(caller.state_path.read_text())
    assert state["no_progress"]["reset_reason"] == "NEW_EVIDENCE"
    assert state["no_progress"]["terminal_hold"] is False
    assert r3.status == "completed"  # kein falscher Hold


# -- F: Binding-Sicherheit ---------------------------------------------------

def test_f_wrong_current_board_ignored(tmp_path):
    """Falsches aktuelles Board beeinflusst das gespeicherte Binding nicht."""
    import os

    os.environ["HERMES_KANBAN_BOARD"] = "default-board"
    try:
        caller = make_caller(tmp_path)
        caller.execute(task_description="task F", board="conduvera")
        state = json.loads(caller.state_path.read_text())
        assert state["task_bindings"]["BUILDER"]["board"] == "conduvera"
        loaded = binding_for_phase(state, "BUILDER")
        assert loaded.board == "conduvera"
    finally:
        os.environ.pop("HERMES_KANBAN_BOARD", None)


def test_f_replacement_exact_phase_key(tmp_path):
    caller = make_caller(tmp_path)
    caller.execute(task_description="task F2", phase="REVIEWER")
    caller.execute(task_description="task F2b", phase="REVIEWER")  # Replacement
    state = json.loads(caller.state_path.read_text())
    bindings = state["task_bindings"]
    assert len(bindings) == 1  # kein Duplicate-State
    assert "REVIEWER" in bindings


# -- DOD-13: Negativtests ----------------------------------------------------

def test_dod13_no_spawn_after_policy_deny(tmp_path):
    adapter = RecordingAdapter()
    caller = make_caller(tmp_path, adapter=adapter)
    caller.execute(task_description="neg", backend="opencode_cli")
    assert adapter.calls == []


def test_dod13_no_spawn_after_terminal_hold(tmp_path):
    """Nach terminalem Hold wird KEINE neue Session gestartet."""
    adapter = RecordingAdapter()
    caller = make_caller(tmp_path, adapter=adapter, threshold=2)
    kwargs = dict(task_description="hold task", task_id="t_0a00a0")
    caller.execute(**kwargs)
    r2 = caller.execute(**kwargs)
    assert r2.status == "hold"
    starts = [c for c in adapter.calls if c["op"] == "start"]
    assert len(starts) == 2  # nur die zwei Läufe VOR dem Hold-Erkennen


def test_dod13_no_foreign_process_changed(tmp_path):
    """Kein fremder codex/opencode-Prozess wird verändert (wie verify_5x)."""
    def foreign():
        r = subprocess.run(["ps", "-eo", "pid,lstart,comm", "--sort=pid"],
                           capture_output=True, text=True)
        return [l for l in r.stdout.splitlines() if any(k in l for k in ("codex", "opencode"))]

    before = foreign()
    caller = make_caller(tmp_path)
    caller.execute(task_description="foreign check")
    after = foreign()
    # SIMULATION startet keine Prozesse: keine codex/opencode-Veränderung
    assert after == before


def test_dod13_no_implicit_ai_stack_model_use(tmp_path):
    """Der Caller ruft nie 'ai-stack model use' auf — ODS bleibt Authority."""
    src = (ROOT / "curaops/buildroom/managed_execution.py").read_text(encoding="utf-8")
    assert "ai-stack model use" not in src
    assert "model use" not in src.replace('"""', "")


def test_dod13_no_secrets_in_evidence(tmp_path):
    caller = make_caller(tmp_path)
    result = caller.execute(task_description="secret check")
    for p in result.evidence_paths:
        txt = Path(p).read_text(encoding="utf-8")
        for secret_marker in ("api_key", "apikey", "password", "token=", "Bearer "):
            assert secret_marker not in txt.lower()


# -- DOD-10: State-Snapshot vor/nach ------------------------------------------

def test_dod10_state_snapshot_before_after(tmp_path):
    caller = make_caller(tmp_path)
    state_before = copy.deepcopy(caller.load_state())
    result = caller.execute(task_description="snapshot task")
    state_after = json.loads(caller.state_path.read_text())
    # Vorher leer (kein task_bindings), nachher vollständig
    assert "task_bindings" not in state_before
    assert "task_bindings" in state_after
    assert state_after["task_bindings"]["BUILDER"]["task_id"].startswith("t_")
    assert result.status == "completed"
    # Konsistenz: State auf Disk == in-memory state
    assert caller._state["task_bindings"] == state_after["task_bindings"]


# -- DOD-11: MXOS-EVIDENCE-Pflichtfelder ---------------------------------------

def test_dod11_mxos_evidence_fields(tmp_path):
    caller = make_caller(tmp_path)
    result = caller.execute(task_description="evidence fields")
    ev = json.loads(Path(result.evidence_paths[0]).read_text())
    for key in ("schema", "goal_id", "task_id", "attempt_id", "session_id",
                "harness", "producer", "evidence", "generated_at"):
        assert key in ev, f"fehlendes Evidence-Feld: {key}"
    assert ev["schema"] == "MXOS-EVIDENCE-1.0.0"
    # call_trace enthält route + model_identity
    state = json.loads(caller.state_path.read_text())
    assert "route" in state["call_trace"]
    assert "model_identity" in state["call_trace"]
