#!/usr/bin/env python3
"""5/5 Live-Läufe (DOD-07): exakt CONDUVERA_FIXTURE_OK, keine Zombies/Orphans,
keine verbleibenden PGID-Mitglieder, keine Foreign-Process-Änderung.

Läuft ausschließlich über den öffentlichen HarnessGatewayService (LIVE) —
der einzige produktive Call-Path. Jeder Lauf erzeugt eine eigene isolierte
Hermes-Session; nach jedem Lauf wird die Prozess-Hygiene verifiziert.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.fixture_runner import FixtureRunner  # noqa: E402
from curaops.harness.gateway import HarnessGatewayService  # noqa: E402
from curaops.harness.registry import ExecutionMode  # noqa: E402


def foreign_snapshot() -> list[str]:
    r = subprocess.run(
        ["ps", "-eo", "pid,lstart,comm", "--sort=pid"],
        capture_output=True, text=True,
    )
    return [l for l in r.stdout.splitlines() if any(k in l for k in ("codex", "opencode"))]


def zombies_and_orphans(session_pids: set[int]) -> dict:
    r = subprocess.run(["ps", "-eo", "pid,ppid,pgid,stat,comm"], capture_output=True, text=True)
    zombies = []
    orphans = []
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
    results = []
    session_pids: set[int] = set()
    all_clean = True

    for i in range(5):
        gateway = HarnessGatewayService(
            registry_path=ROOT / "fixtures" / "harness-registry.yaml",
            execution_mode=ExecutionMode.LIVE.value,
        )
        runner = FixtureRunner(
            fixture_dir=ROOT / "fixtures" / "live" / "run5" / f"run-{i}",
            route_manifest=ROOT / "fixtures" / "ods" / "route-manifest.fixture.yaml",
            gateway=gateway,
            producer={"name": "conduvera-core", "version": "0.1.0"},
            goal_id="CONDUVERA-FIXTURE-001",
            execution_mode=ExecutionMode.LIVE.value,
        )
        result = runner.run("5x live verification run")
        resp_files = sorted((ROOT / "fixtures/live/run5" / f"run-{i}" / "worktrees").rglob("*.response.txt"))
        resp = resp_files[0].read_text().strip() if resp_files else ""
        exact = resp == "CONDUVERA_FIXTURE_OK"
        trace = json.loads((ROOT / "fixtures/live/run5" / f"run-{i}" / "state/call-trace.json").read_text())
        pid, pgid = trace["pid"], trace["pgid"]
        session_pids.add(pid)
        # PGID leer nach Lauf (keine verbleibenden Mitglieder)
        ps = subprocess.run(["ps", "-eo", "pid,pgid", "--no-headers"], capture_output=True, text=True)
        remaining = [l for l in ps.stdout.splitlines() if l.split() and l.split()[1] == str(pgid)]
        clean = result.status == "completed" and exact and not remaining
        all_clean = all_clean and clean
        results.append({
            "run": i, "status": result.status, "response": resp,
            "response_exact": exact, "pid": pid, "pgid": pgid,
            "pgid_remaining": len(remaining), "clean": clean,
        })
        print(f"run{i}: status={result.status} response={resp!r} exact={exact} "
              f"pid={pid} pgid={pgid} pgid_remaining={len(remaining)}")

    hygiene = zombies_and_orphans(session_pids)
    after = foreign_snapshot()
    foreign_changed = [l for l in after if l not in before] + [l for l in before if l not in after]

    report = {
        "runs": results,
        "all_exact": all(r["response_exact"] for r in results),
        "zombies": hygiene["zombies"],
        "orphans": hygiene["orphans"],
        "pgid_all_empty": all(r["pgid_remaining"] == 0 for r in results),
        "foreign_process_changed": bool(foreign_changed),
        "verdict": (
            "PASS 5/5"
            if (all(r["response_exact"] for r in results)
                and not hygiene["zombies"] and not hygiene["orphans"]
                and all(r["pgid_remaining"] == 0 for r in results)
                and not foreign_changed)
            else "FAIL"
        ),
    }
    out = ROOT / "fixtures/live/run5/live-5x-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nVERDIKT: {report['verdict']}")
    print(f"Zombies: {hygiene['zombies']} | Orphans: {hygiene['orphans']} | "
          f"Foreign-Änderung: {bool(foreign_changed)}")
    print(f"Evidence: {out}")
    return 0 if report["verdict"] == "PASS 5/5" else 1


if __name__ == "__main__":
    raise SystemExit(main())
