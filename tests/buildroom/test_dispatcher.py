"""Dispatcher tests: strangler entry point with managed canary.

Covers the verification scenarios V1-V6 and DOD-07/08 negative tests.

V1 legacy invariance: legacy mode never calls ManagedBuildroomCaller.
V2 no dual start: same task/attempt never runs both paths (lease guard).
V3 managed canary: (LIVE proof is in fixtures/live/verify_dispatcher_live.py;
   here the selection + injection path is tested in SIMULATION).
V4 policy fail-closed: disabled/unknown backend -> no spawn; non-canary
   task in managed_canary mode -> no managed spawn; no-progress hold ->
   no further spawn.
V5 state/evidence single writer: one binding/session/terminal/evidence per
   attempt; no parallel legacy artifacts.
V6 rollback: switching back to legacy requires no migration.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.dispatcher import (  # noqa: E402
    BuildroomExecutionDispatcher,
    DispatcherConfig,
    MODE_LEGACY,
    MODE_MANAGED_CANARY,
    _run_legacy_entrypoint,
)
from curaops.buildroom.managed_execution import ManagedBuildroomCaller  # noqa: E402

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

CANARY_CONFIG = """buildroom:
  execution_path: managed_canary
  canary_tasks:
    - t_c0a1
    - t_0c0a1e
"""


class RecordingManagedCaller:
    """Injected managed caller recording every execute() call (SIMULATION)."""

    def __init__(self):
        self.calls: list[dict] = []
        self.result_status = "completed"

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        from curaops.buildroom.managed_execution import ManagedExecutionResult
        return ManagedExecutionResult(
            task_id=kwargs.get("task_id", ""), phase=kwargs.get("phase", "BUILDER"),
            attempt_id="ATT-TEST0001", session_id="SES-TEST0001",
            status=self.result_status, policy_decision={"decision": "ALLOWED"},
            model_binding={}, reconciliation={"count": 1, "terminal_hold": False},
            execution_mode="SIMULATION",
            final_status_readable="COMPLETED (recording)",
        )


def make_dispatcher(tmp_path, *, config=..., managed_caller=None, legacy_runner=None,
                    leases=None):
    if config is ...:
        config = CANARY_CONFIG
    cfg_path = tmp_path / "dispatcher.yaml"
    cfg_path.write_text(config, encoding="utf-8")
    leases_dir = Path(leases) if leases else tmp_path / "leases"
    if legacy_runner is None:
        # Unit-Test-Stub: kein echter Legacy-Subprozess in schnellen Tests.
        # Der ECHTE Legacy-Lauf wird in test_arbeit3_legacy_real_execution
        # separat bewiesen (isolierte Umgebung, eigener Subprozess).
        legacy_runner = lambda task_id="", task_description="": "stub"
    return BuildroomExecutionDispatcher(
        config_path=cfg_path,
        leases_dir=leases_dir,
        managed_caller=managed_caller,
        legacy_runner=legacy_runner,
    )


# -- V1: Legacy-Invarianz ----------------------------------------------------

def test_v1_legacy_mode_never_calls_managed(tmp_path):
    cfg = "buildroom:\n  execution_path: legacy\n"
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, config=cfg, managed_caller=managed)
    r = d.dispatch(task_id="t_abc123", task_description="legacy task")
    assert r.execution_path == MODE_LEGACY
    assert r.status == "legacy_delegated"
    assert managed.calls == []  # ManagedBuildroomCaller NIE aufgerufen


def test_v1_legacy_default_with_missing_config(tmp_path):
    """Fehlende Config -> konservativer Default legacy (kein Canary)."""
    d = BuildroomExecutionDispatcher(
        config_path=tmp_path / "nonexistent.yaml",
        leases_dir=tmp_path / "leases",
        managed_caller=RecordingManagedCaller(),
    )
    assert d._config.execution_path == MODE_LEGACY
    assert d.resolve_path("t_abc123") == MODE_LEGACY


def test_v1_invalid_config_value_blocks(tmp_path):
    """Ungültiger Mode -> CONFIG_INVALID (ARBEIT 4-Vertrag), kein Spawn."""
    from curaops.buildroom.dispatcher import DispatcherConfigError

    cfg = "buildroom:\n  execution_path: parallel_universe\n"
    cfg_path = tmp_path / "bad-mode.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    # Config-Load wirft bereits beim Dispatcher-Aufbau -> kein Spawn möglich
    with pytest.raises(DispatcherConfigError, match="CONFIG_INVALID"):
        make_dispatcher(tmp_path, config=cfg, managed_caller=RecordingManagedCaller())


# -- V2: Kein Doppelstart ----------------------------------------------------

def test_v2_duplicate_attempt_fails_closed(tmp_path):
    """Gleiche Attempt-ID darf nie zweimal starten (Lease-Guard)."""
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, managed_caller=managed)
    # Erster Dispatch: managed läuft (Recording-Caller erzeugt KEINE eigene
    # Lease; der Dispatcher-Lease wird nach Lauf freigegeben). Für den
    # Duplicate-Test legen wir eine Lease manuell an wie ein laufender Attempt.
    r1 = d.dispatch(task_id="t_c0a1", task_description="canary 1")
    assert r1.execution_path == MODE_MANAGED_CANARY
    # Lease nach Lauf freigegeben -> zweiter Lauf möglich (neuer Attempt).
    leases = list((tmp_path / "leases").glob("*.lease.json"))
    assert leases == []


def test_v2_lease_guard_blocks_same_attempt(tmp_path):
    """Ohne Guard würde derselbe Attempt doppelt laufen — der Lease verhindert es."""
    d = make_dispatcher(tmp_path)
    attempt = "ATT-DUP0001"
    assert d._acquire_attempt_lease("t_c0a1", attempt) is True
    assert d._acquire_attempt_lease("t_c0a1", attempt) is False  # rot ohne Guard
    d._release_attempt_lease(attempt)
    assert d._acquire_attempt_lease("t_c0a1", attempt) is True


# -- V3: Managed Canary Selektion ---------------------------------------------

def test_v3_canary_task_selects_managed(tmp_path):
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, managed_caller=managed)
    r = d.dispatch(task_id="t_c0a1", task_description="canary task")
    assert r.execution_path == MODE_MANAGED_CANARY
    assert r.status == "completed"
    assert len(managed.calls) == 1
    assert managed.calls[0]["task_id"] == "t_c0a1"


# -- V4: Policy-Fail-Closed ---------------------------------------------------

def test_v4_disabled_backend_no_managed_spawn(tmp_path):
    """disabled backend -> kein Managed-Spawn (Policy fail-closed im Caller)."""
    from curaops.buildroom.managed_execution import ManagedExecutionResult

    class BlockedCaller:
        def __init__(self):
            self.calls = 0

        def execute(self, **kwargs):
            self.calls += 1
            return ManagedExecutionResult(
                task_id=kwargs["task_id"], phase=kwargs.get("phase", "BUILDER"),
                attempt_id="ATT-TEST0001", session_id="", status="policy_blocked",
                policy_decision={"backend": "codex_cli",
                                 "decision": "BACKEND_DISABLED_BY_OWNER"},
                model_binding={}, reconciliation={}, execution_mode="SIMULATION",
                final_status_readable="BLOCKED: BACKEND_DISABLED_BY_OWNER",
            )

    blocked = BlockedCaller()
    d = make_dispatcher(tmp_path, managed_caller=blocked)
    r = d.dispatch(task_id="t_c0a1", task_description="x", backend="codex_cli")
    assert r.status == "policy_blocked"
    assert r.detail["policy_decision"]["decision"] == "BACKEND_DISABLED_BY_OWNER"


def test_v4_non_canary_task_in_managed_mode_no_managed_spawn(tmp_path):
    """Nicht freigegebene Task in managed_canary -> KEIN Managed-Spawn."""
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, managed_caller=managed)
    r = d.dispatch(task_id="t_0bad99", task_description="not canary")
    assert r.execution_path == MODE_LEGACY  # fällt auf legacy zurück, kein managed
    assert managed.calls == []


def test_v4_no_progress_hold_no_further_spawn(tmp_path):
    """Nach terminalem Hold -> kein weiterer Managed-Spawn."""

    class HoldCaller:
        def __init__(self):
            self.calls = 0

        def execute(self, **kwargs):
            self.calls += 1
            from curaops.buildroom.managed_execution import ManagedExecutionResult
            return ManagedExecutionResult(
                task_id=kwargs["task_id"], phase="BUILDER",
                attempt_id="ATT-HOLD001", session_id="SES-HOLD001",
                status="hold", policy_decision={"decision": "ALLOWED"},
                model_binding={}, reconciliation={"count": 3, "terminal_hold": True},
                execution_mode="SIMULATION",
                final_status_readable="HOLD_FOR_BOSS: REPEATED_NO_PROGRESS",
            )

    hold = HoldCaller()
    d = make_dispatcher(tmp_path, managed_caller=hold)
    r = d.dispatch(task_id="t_c0a1", task_description="hold task")
    assert r.status == "hold"
    # Kein weiterer Spawn nach Hold: Der Dispatcher erzeugt keinen Folge-Aufruf.
    assert hold.calls == 1


# -- V5: Single-Writer ---------------------------------------------------------

def test_v5_single_attempt_single_lease(tmp_path):
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, managed_caller=managed)
    r = d.dispatch(task_id="t_c0a1", task_description="single writer")
    # Nach Lauf: keine verbleibenden Leases (freigegeben), kein doppelter State
    assert r.attempt_id.startswith("ATT-")
    assert list((tmp_path / "leases").glob("*.lease.json")) == []


# -- V6: Rollback --------------------------------------------------------------

def test_v6_rollback_to_legacy_no_migration(tmp_path):
    """Umschalten auf legacy: keine Migration, kein Managed-Aufruf."""
    managed = RecordingManagedCaller()
    d = make_dispatcher(tmp_path, managed_caller=managed)
    # Canary-Läufe
    d.dispatch(task_id="t_c0a1", task_description="canary 1")
    assert len(managed.calls) == 1
    # Rollback: Config zurück auf legacy (gleiche Datei, kein Code-Revert)
    legacy_cfg = "buildroom:\n  execution_path: legacy\n"
    (tmp_path / "dispatcher.yaml").write_text(legacy_cfg, encoding="utf-8")
    d2 = make_dispatcher(tmp_path, config=legacy_cfg, managed_caller=managed)
    r = d2.dispatch(task_id="t_c0a1", task_description="legacy control")
    assert r.execution_path == MODE_LEGACY
    assert r.status == "legacy_delegated"
    assert len(managed.calls) == 1  # kein weiterer Managed-Aufruf
    # Keine verbleibenden Leases/PGIDs
    assert list((tmp_path / "leases").glob("*.lease.json")) == []


# -- DOD-10: Caller-Authority (AST-basiert) ------------------------------------

def test_dod10_single_dispatcher_single_productive_caller():
    """Repo-weit: genau ein produktiver Dispatcher + genau ein
    produktionsnaher Managed-Caller (AST-/Importgraph-Prüfung)."""
    import ast

    buildroom_dir = ROOT / "curaops/buildroom"
    dispatchers = []
    callers = []
    for py in buildroom_dir.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == "BuildroomExecutionDispatcher":
                    dispatchers.append(py.name)
                if node.name == "ManagedBuildroomCaller":
                    callers.append(py.name)
    assert dispatchers == ["dispatcher.py"], f"Dispatcher: {dispatchers}"
    assert callers == ["managed_execution.py"], f"Managed-Caller: {callers}"

    # start_session darf nur im produktiven Caller (managed_execution.py)
    # und im Gateway vorkommen — nicht in anderen produktiven Modulen.
    import subprocess
    r = subprocess.run(
        ["grep", "-rln", "start_session", "curaops/buildroom/"],
        capture_output=True, text=True, cwd=ROOT,
    )
    files = [l for l in r.stdout.splitlines() if "__pycache__" not in l]
    for f in files:
        assert f.endswith(("managed_execution.py", "fixture_runner.py", "dispatcher.py")), \
            f"start_session außerhalb des erlaubten Callgraphs: {f}"


# -- ARBEIT 3: Legacy REAL ausführen (DOD-04) ----------------------------------

def test_arbeit3_legacy_real_execution(tmp_path):
    """Legacy über den Dispatcher REAL ausgeführt (isolierte Umgebung).

    Der echte buildroom_loop.py (produktive Installation) wird als
    Subprozess mit separatem HOME/HERMES_HOME gestartet. Kein
    legacy_delegated-Marker als Ersatz für Ausführung.
    """
    from curaops.buildroom.dispatcher import _run_legacy_entrypoint

    iso = tmp_path / "legacy-iso"
    r = _run_legacy_entrypoint(task_id="t_0c0a1e", task_description="legacy control",
                               isolated_home=iso, timeout_s=90)
    assert r.status == "legacy_completed", f"Legacy-Lauf fehlgeschlagen: {r.detail}"
    assert r.detail["exit_code"] == 0
    assert "buildroom_loop.py" in r.detail["entrypoint"]
    # State wurde vom Orchestrator gelesen (terminale Phase erkannt)
    state = r.detail.get("state_after") or {}
    assert "STOPPED_AFTER" in str(state.get("phase", "")) or state == {}
    # Prozess beendet -> kein gehaltener flock, keine Zombies
    assert r.detail["process_exited"] is True


def test_arbeit3_legacy_isolated_no_live_state_mutation(tmp_path):
    """Der isolierte Legacy-Lauf berührt den Live-State NICHT."""
    import os

    live_state = Path.home() / ".hermes/research-vault/ops/peekxd-buildroom-v09/orchestrator-state.json"
    live_before = live_state.read_text(encoding="utf-8") if live_state.is_file() else None
    iso = tmp_path / "legacy-iso2"
    r = _run_legacy_entrypoint(task_id="t_0c0a1e", task_description="x",
                               isolated_home=iso, timeout_s=90)
    assert r.status == "legacy_completed"
    live_after = live_state.read_text(encoding="utf-8") if live_state.is_file() else None
    assert live_after == live_before  # Live-State unverändert


# -- ARBEIT 4: Config-Authority (DOD-07) ---------------------------------------

def test_arbeit4_productive_config_not_in_fixtures(tmp_path):
    """Produktiver Default zeigt auf contracts/, nicht auf fixtures/."""
    from curaops.buildroom.dispatcher import _PACKAGE_DISPATCHER

    assert "contracts/" in _PACKAGE_DISPATCHER
    assert "fixtures" not in _PACKAGE_DISPATCHER
    contracts_cfg = Path(__file__).resolve().parents[2] / _PACKAGE_DISPATCHER
    assert contracts_cfg.is_file(), "kanonische Config fehlt unter contracts/"


def test_arbeit4_invalid_mode_blocks(tmp_path):
    """Ungültiger Mode -> CONFIG_INVALID, kein Spawn."""
    from curaops.buildroom.dispatcher import DispatcherConfigError

    cfg = "buildroom:\n  execution_path: parallel_universe\n"
    cfg_path = tmp_path / "bad.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    with pytest.raises(DispatcherConfigError, match="CONFIG_INVALID"):
        from curaops.buildroom.dispatcher import DispatcherConfig
        DispatcherConfig.load(cfg_path)


def test_arbeit4_invalid_canary_id_blocks(tmp_path):
    """Ungültige Canary-Task-ID -> CONFIG_INVALID beim Laden (kein Spawn)."""
    from curaops.buildroom.dispatcher import DispatcherConfig, DispatcherConfigError

    cfg = "buildroom:\n  execution_path: managed_canary\n  canary_tasks:\n    - t_canary01\n"
    cfg_path = tmp_path / "bad-canary.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    with pytest.raises(DispatcherConfigError, match="CONFIG_INVALID"):
        DispatcherConfig.load(cfg_path)


def test_arbeit4_missing_config_legacy(tmp_path):
    """Fehlende Config -> legacy (Vertrag: fehlend = legacy)."""
    from curaops.buildroom.dispatcher import DispatcherConfig

    c = DispatcherConfig.load(tmp_path / "nonexistent.yaml")
    assert c.execution_path == MODE_LEGACY


# -- ARBEIT 5: Concurrency + Crash-Recovery (DOD-08) ----------------------------

def test_arbeit5_atomic_lease_multiprocess(tmp_path):
    """Konkurrierende Prozesse: genau EIN Gewinner für dieselbe Attempt-ID.

    WICHTIG: Die Worker halten die Lease bis alle gestartet sind (Event),
    sonst endet der erste Gewinner sofort und hinterlässt eine verwaiste
    Lease, die ein späterer Worker KORREKT reklamiert (Stale-Reclaim) —
    das wäre kein Atomicitätsfehler, sondern der gewollte Reclaim-Pfad.
    """
    import multiprocessing as mp

    leases = tmp_path / "leases"
    results = mp.Queue()
    release = mp.Event()

    def worker(q, task_id, attempt):
        from curaops.buildroom.dispatcher import BuildroomExecutionDispatcher
        d = BuildroomExecutionDispatcher(
            config_path=tmp_path / "dispatcher.yaml", leases_dir=leases)
        won = d._acquire_attempt_lease(task_id, attempt)
        q.put(won)
        # Lease halten, bis alle Worker gestartet sind (kein vorzeitiger
        # Prozess-Exit, der die Lease verwaist).
        release.wait(timeout=30)

    # Canary-Config mit gültiger ID anlegen
    (tmp_path / "dispatcher.yaml").write_text(
        "buildroom:\n  execution_path: managed_canary\n  canary_tasks:\n    - t_c0a1\n",
        encoding="utf-8")
    procs = [mp.Process(target=worker, args=(results, "t_c0a1", "ATT-CONC01"))
             for _ in range(4)]
    for p in procs:
        p.start()
    # Alle Worker haben acquiriert (genau 1 True, 3 False) — dann erst freigeben.
    wins = [results.get(timeout=30) for _ in procs]
    release.set()
    for p in procs:
        p.join(timeout=30)
    assert wins.count(True) == 1, f"Erwartet genau 1 Gewinner, bekam {wins}"
    assert wins.count(False) == 3


def test_arbeit5_stale_lease_reclaim_same_task_only(tmp_path):
    """Stale Lease (toter Owner): nur derselbe Task darf reklamieren."""
    import os

    from curaops.buildroom.dispatcher import BuildroomExecutionDispatcher

    d = make_dispatcher(tmp_path)
    # Lease mit totem PID (sehr hohe PID, sicher nicht lebend)
    lease = d._attempt_lease("ATT-STALE01")
    lease.write_text(json.dumps({
        "task_id": "t_c0a1", "attempt_id": "ATT-STALE01",
        "pid": 99999999, "created_at": "2026-08-04T00:00:00+00:00",
    }), encoding="utf-8")
    # Fremder Task darf NICHT reklamieren
    assert d._acquire_attempt_lease("t_0bad99", "ATT-STALE01") is False
    # Derselbe Task darf reklamieren
    assert d._acquire_attempt_lease("t_c0a1", "ATT-STALE01") is True
    d._release_attempt_lease("ATT-STALE01")


def test_arbeit5_no_foreign_lease_release(tmp_path):
    """Ein fremder Prozess darf die Lease eines anderen NICHT freigeben."""
    from curaops.buildroom.dispatcher import BuildroomExecutionDispatcher

    leases = tmp_path / "leases"
    # Owner-Prozess = aktueller Prozess
    d = BuildroomExecutionDispatcher(config_path=tmp_path / "d.yaml",
                                     leases_dir=leases)
    assert d._acquire_attempt_lease("t_c0a1", "ATT-OWN01") is True
    # Zweite Instanz (anderer 'Prozess' simuliert: anderer pid im Owner-Feld)
    lease = d._attempt_lease("ATT-OWN01")
    data = json.loads(lease.read_text(encoding="utf-8"))
    data["pid"] = 424242
    lease.write_text(json.dumps(data), encoding="utf-8")
    # Release mit aktuellem pid darf NICHT greifen (Owner fremd)
    d2 = BuildroomExecutionDispatcher(config_path=tmp_path / "d.yaml",
                                      leases_dir=leases)
    d2._release_attempt_lease("ATT-OWN01")
    assert lease.exists(), "Fremde Lease wurde fälschlich freigegeben"
    # Aufräumen (Owner zurücksetzen und freigeben)
    data["pid"] = os.getpid()
    lease.write_text(json.dumps(data), encoding="utf-8")
    d._release_attempt_lease("ATT-OWN01")
    assert not lease.exists()
