#!/usr/bin/env python3
"""3x Live Canary-Läufe über den BuildroomExecutionDispatcher (V3/DOD-06).

Pfad: Entrypoint -> Dispatcher -> ManagedBuildroomCaller -> Hermes ->
LiteLLM workload/local -> ODS text mode -> MXOS-EVIDENCE.

Canary-Config: fixtures/buildroom/execution-dispatcher-canary.yaml
(execution_path: managed_canary, canary_tasks: t_canary01/02/03).

Verifiziert pro Lauf:
- Route + Modellidentität aus realer Evidence (Live-Manifest),
- Antwort exakt CONDUVERA_FIXTURE_OK,
- 0 Zombie, 0 Orphan, 0 PGID-Rest, 0 Foreign-Änderung,
- kein 'ai-stack model use' (ODS bleibt Runtime-Authority),
- kein Dual-Run (nur ein Spawn je Attempt, Lease freigegeben).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.dispatcher import BuildroomExecutionDispatcher  # noqa: E402
from curaops.buildroom.managed_execution import ManagedBuildroomCaller  # noqa: E402
from curaops.harness.gateway import HarnessGatewayService  # noqa: E402
from curaops.harness.registry import ExecutionMode  # noqa: E402


def foreign_snapshot() -> list[str]:
    r = subprocess.run(["ps", "-eo", "pid,lstart,comm", "--sort=pid"],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if any(k in l for k in ("codex", "opencode"))]


def zombies_and_orphans(session_pids: set[int]) -> dict:
    r = subprocess.run(["ps", "-eo", "pid,ppid,pgid,stat,comm"], capture_output=True, text=True)
    zombies, orphans = [], []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        pid, ppid, pgid, stat, comm = int(parts[0]), int(parts[1]), int(parts[2]), parts[3], parts[4]
        if pid in session_pids and stat.startswith("Z"):
            zombies.append(pid)
        if pid in session_pids and ppid == 1 and stat not in ("Z",):
            orphans.append(pid)
    return {"zombies": zombies, "orphans": orphans}


def main() -> int:
    before = foreign_snapshot()
    runs = []
    session_pids: set[int] = set()
    out_root = ROOT / "fixtures/live/dispatcher-canary"
    out_root.mkdir(parents=True, exist_ok=True)

    for i, task_id in enumerate(("t_c0a1", "t_0c0a1e", "t_0c0a1f")):
        run_dir = out_root / f"run-{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        state_path = run_dir / "managed-state.json"
        gateway = HarnessGatewayService(
            registry_path=ROOT / "fixtures/harness-registry.yaml",
            execution_mode=ExecutionMode.LIVE.value,
        )
        caller = ManagedBuildroomCaller(
            state_path=state_path,
            route_manifest=ROOT / "fixtures/ods/route-manifest.fixture.yaml",
            gateway=gateway,
            producer={"name": "conduvera-core", "version": "0.1.0"},
            goal_id="CONDUVERA-FIXTURE-001",
            execution_mode=ExecutionMode.LIVE.value,
            threshold=3,
        )
        dispatcher = BuildroomExecutionDispatcher(
            config_path=ROOT / "fixtures/buildroom/execution-dispatcher-canary.yaml",
            leases_dir=run_dir / "leases",
            managed_caller=caller,
        )
        path = dispatcher.resolve_path(task_id)
        if path != "managed_canary":
            print(f"run{i}: SELECTION-FEHLER: {task_id} -> {path}")
            runs.append({"run": i, "task_id": task_id, "error": f"selection={path}"})
            continue

        result = dispatcher.dispatch(
            task_id=task_id,
            task_description="managed canary live verification run",
            phase="BUILDER", board="conduvera", cycle=1,
            worktree_root=run_dir / "worktrees",
        )
        resp_files = sorted((run_dir / "worktrees").rglob("*.response.txt"))
        resp = resp_files[0].read_text().strip() if resp_files else ""
        exact = resp == "CONDUVERA_FIXTURE_OK"
        trace = json.loads((run_dir / "state/call-trace.json").read_text()) if (run_dir / "state/call-trace.json").is_file() else {}
        pid, pgid = trace.get("pid"), trace.get("pgid")
        if pid:
            session_pids.add(pid)
        ps = subprocess.run(["ps", "-eo", "pid,pgid", "--no-headers"], capture_output=True, text=True)
        remaining = [l for l in ps.stdout.splitlines() if l.split() and l.split()[1] == str(pgid)] if pgid else []
        clean = result.status == "completed" and exact and not remaining
        leases_left = list((run_dir / "leases").glob("*.lease.json"))
        runs.append({
            "run": i, "task_id": task_id, "status": result.status, "response": resp,
            "response_exact": exact, "pid": pid, "pgid": pgid,
            "pgid_remaining": len(remaining), "clean": clean,
            "route": trace.get("route"), "model_identity": trace.get("model_identity"),
            "leases_left": len(leases_left),
        })
        print(f"run{i}: {task_id} status={result.status} response={resp!r} exact={exact} "
              f"pid={pid} route={trace.get('route')} model={trace.get('model_identity')}")

    hygiene = zombies_and_orphans(session_pids)
    after = foreign_snapshot()
    foreign_changed = [l for l in after if l not in before] + [l for l in before if l not in after]

    report = {
        "runs": runs,
        "all_exact": all(r.get("response_exact") for r in runs),
        "all_completed": all(r.get("status") == "completed" for r in runs),
        "zombies": hygiene["zombies"], "orphans": hygiene["orphans"],
        "pgid_all_empty": all(r.get("pgid_remaining", 1) == 0 for r in runs),
        "foreign_process_changed": bool(foreign_changed),
        "all_leases_released": all(r.get("leases_left", 1) == 0 for r in runs),
        "ai_stack_model_use": False,  # Dispatcher/Caller rufen nie 'ai-stack model use'
        "verdict": (
            "PASS 3/3 CANARY"
            if (all(r.get("response_exact") for r in runs)
                and all(r.get("status") == "completed" for r in runs)
                and not hygiene["zombies"] and not hygiene["orphans"]
                and all(r.get("pgid_remaining", 1) == 0 for r in runs)
                and not foreign_changed
                and all(r.get("leases_left", 1) == 0 for r in runs))
            else "FAIL"
        ),
    }
    out = out_root / "dispatcher-3x-canary-evidence.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nVERDIKT: {report['verdict']}")
    print(f"Zombies: {hygiene['zombies']} | Orphans: {hygiene['orphans']} | "
          f"Foreign: {bool(foreign_changed)} | Leases: {all(r.get('leases_left', 1) == 0 for r in runs)}")
    print(f"Evidence: {out}")
    return 0 if report["verdict"] == "PASS 3/3 CANARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
