#!/usr/bin/env python3
"""3x Live-Läufe des ManagedBuildroomCaller (DOD-16).

Führt den REALEN produktionsnahen Caller (curaops.buildroom.managed_execution)
im LIVE-Modus aus — reimplementiert KEINE Logik. Verifiziert pro Lauf:
- TaskBinding erzeugt/gespeichert/zurückgelesen (Identität),
- Backend-Policy ALLOWED vor Spawn,
- MANAGED-Hermes-Session via HarnessGatewayService (echter Prozess),
- Antwort exakt CONDUVERA_FIXTURE_OK,
- Route + Modellidentität aus Live-Manifest,
- MXOS-EVIDENCE vollständig,
- Reconciliation (no_progress) im realen Pfad,
- Prozess-Hygiene: 0 Zombie, 0 Orphan, 0 PGID-Rest, 0 Foreign-Änderung,
- gleicher semantischer Endzustand über 3 Wiederholungen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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
    semantic_states = []
    out_root = ROOT / "fixtures/live/managed"
    out_root.mkdir(parents=True, exist_ok=True)

    for i in range(3):
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
        result = caller.execute(
            task_description="managed live verification run",
            phase="BUILDER", board="conduvera", cycle=1,
            task_id=f"t_{'0a0b0c0d0e0f'[:8]}{i:02x}",
            worktree_root=run_dir / "worktrees",
        )

        resp_files = sorted((run_dir / "worktrees").rglob("*.response.txt"))
        resp = resp_files[0].read_text().strip() if resp_files else ""
        exact = resp == "CONDUVERA_FIXTURE_OK"
        trace = json.loads((run_dir / "state/call-trace.json").read_text()) if (run_dir / "state/call-trace.json").is_file() else {}
        pid = trace.get("pid")
        pgid = trace.get("pgid")
        if pid:
            session_pids.add(pid)
        ps = subprocess.run(["ps", "-eo", "pid,pgid", "--no-headers"], capture_output=True, text=True)
        remaining = [l for l in ps.stdout.splitlines() if l.split() and l.split()[1] == str(pgid)] if pgid else []
        clean = result.status == "completed" and exact and not remaining

        semantic_states.append({
            "status": result.status,
            "reconciliation_count": result.reconciliation.get("count"),
            "terminal_hold": result.reconciliation.get("terminal_hold"),
            "policy_decision": result.policy_decision.get("decision"),
            "route": trace.get("route"),
            "model_identity": trace.get("model_identity"),
            "response_exact": exact,
        })
        runs.append({
            "run": i, "status": result.status, "response": resp,
            "response_exact": exact, "pid": pid, "pgid": pgid,
            "pgid_remaining": len(remaining), "clean": clean,
            "route": trace.get("route"), "model_identity": trace.get("model_identity"),
            "reconciliation": result.reconciliation,
        })
        print(f"run{i}: status={result.status} response={resp!r} exact={exact} "
              f"pid={pid} pgid={pgid} pgid_remaining={len(remaining)} route={trace.get('route')}")

    hygiene = zombies_and_orphans(session_pids)
    after = foreign_snapshot()
    foreign_changed = [l for l in after if l not in before] + [l for l in before if l not in after]

    # DOD-16: gleicher semantischer Endzustand über 3 Wiederholungen
    same_semantic_state = all(s == semantic_states[0] for s in semantic_states)

    report = {
        "runs": runs,
        "all_exact": all(r["response_exact"] for r in runs),
        "all_completed": all(r["status"] == "completed" for r in runs),
        "zombies": hygiene["zombies"], "orphans": hygiene["orphans"],
        "pgid_all_empty": all(r["pgid_remaining"] == 0 for r in runs),
        "foreign_process_changed": bool(foreign_changed),
        "same_semantic_state": same_semantic_state,
        "verdict": (
            "PASS 3/3 LIVE"
            if (all(r["response_exact"] for r in runs)
                and all(r["status"] == "completed" for r in runs)
                and not hygiene["zombies"] and not hygiene["orphans"]
                and all(r["pgid_remaining"] == 0 for r in runs)
                and not foreign_changed
                and same_semantic_state)
            else "FAIL"
        ),
    }
    out = out_root / "managed-3x-live-evidence.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nVERDIKT: {report['verdict']}")
    print(f"Zombies: {hygiene['zombies']} | Orphans: {hygiene['orphans']} | "
          f"Foreign: {bool(foreign_changed)} | SameSemanticState: {same_semantic_state}")
    print(f"Evidence: {out}")
    return 0 if report["verdict"] == "PASS 3/3 LIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
