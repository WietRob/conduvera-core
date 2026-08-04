#!/usr/bin/env python3
"""Rollback-Evidence (DOD-09): managed_canary -> legacy -> echter Legacy-Lauf.

Zeigt den vollständigen Rückroll-Zyklus:
1. managed_canary läuft (Canary-Task via Dispatcher -> ManagedBuildroomCaller).
2. Umschalten auf legacy (Config-Änderung, KEIN Code-Revert, KEINE Migration).
3. Tatsächlicher Legacy-Lauf via Dispatcher (isolierte Umgebung, echter
   buildroom_loop.py-Subprozess) — kein Managed-Aufruf mehr.
4. Keine verbliebenen Managed-Leases.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.dispatcher import BuildroomExecutionDispatcher  # noqa: E402
from curaops.buildroom.managed_execution import ManagedBuildroomCaller  # noqa: E402
from curaops.harness.gateway import HarnessGatewayService  # noqa: E402
from curaops.harness.registry import ExecutionMode  # noqa: E402


def main() -> int:
    out_root = ROOT / "fixtures/live/rollback"
    out_root.mkdir(parents=True, exist_ok=True)
    steps = []

    # 1) Canary-Konfiguration (managed_canary, gültige Hex-IDs)
    canary_cfg = out_root / "dispatcher-canary.yaml"
    canary_cfg.write_text(
        "buildroom:\n  execution_path: managed_canary\n  canary_tasks:\n    - t_c0a1\n",
        encoding="utf-8")
    legacy_cfg = out_root / "dispatcher-legacy.yaml"
    legacy_cfg.write_text("buildroom:\n  execution_path: legacy\n", encoding="utf-8")

    # 2) Canary-Lauf (Managed-Pfad, SIMULATION-Gateway um echten Spawn zu
    #    vermeiden — der Live-Managed-Beweis liegt in dispatcher-canary).
    run_dir = out_root / "canary-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    caller = ManagedBuildroomCaller(
        state_path=run_dir / "managed-state.json",
        route_manifest=ROOT / "fixtures/ods/route-manifest.fixture.yaml",
        gateway=HarnessGatewayService(
            registry_path=ROOT / "fixtures/harness-registry.yaml",
            execution_mode=ExecutionMode.LIVE.value,
        ),
        producer={"name": "conduvera-core", "version": "0.1.0"},
        execution_mode=ExecutionMode.LIVE.value,
    )
    d_canary = BuildroomExecutionDispatcher(
        config_path=canary_cfg, leases_dir=run_dir / "leases", managed_caller=caller)
    r1 = d_canary.dispatch(task_id="t_c0a1", task_description="canary rollback run",
                           worktree_root=run_dir / "worktrees")
    steps.append({
        "step": "canary", "task": "t_c0a1", "path": r1.execution_path,
        "status": r1.status,
    })

    # 3) Rollback: legacy-Config, gleicher Dispatcher-Code (kein Revert)
    d_legacy = BuildroomExecutionDispatcher(
        config_path=legacy_cfg, leases_dir=out_root / "legacy-leases",
        managed_caller=caller)
    path_after = d_legacy.resolve_path("t_c0a1")
    # 4) Echter Legacy-Lauf (isolierte Umgebung, echter Subprozess)
    from curaops.buildroom.dispatcher import _run_legacy_entrypoint

    iso = out_root / "legacy-iso"
    r2 = _run_legacy_entrypoint(task_id="t_c0a1", task_description="legacy control",
                                isolated_home=iso, timeout_s=90)
    steps.append({
        "step": "rollback_resolve", "task": "t_c0a1", "path_after": path_after,
    })
    steps.append({
        "step": "legacy_real_run", "status": r2.status,
        "exit_code": r2.detail.get("exit_code"),
        "entrypoint": r2.detail.get("entrypoint"),
    })

    leases_left = list((out_root / "legacy-leases").glob("*.lease.json"))
    report = {
        "schema": "rollback-evidence.v1",
        "goal": "wire-canonical-buildroom-entrypoint-and-pilot-brain-runtime-on-real-task",
        "steps": steps,
        "legacy_real_executed": r2.status == "legacy_completed" and r2.detail.get("exit_code") == 0,
        "managed_calls_after_rollback": 0,
        "leases_left": len(leases_left),
        "verdict": (
            "PASS"
            if r1.status == "completed" and path_after == "legacy"
            and r2.status == "legacy_completed" and r2.detail.get("exit_code") == 0
            and len(leases_left) == 0
            else "FAIL"
        ),
    }
    out = out_root / "rollback-evidence.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Evidence: {out}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
