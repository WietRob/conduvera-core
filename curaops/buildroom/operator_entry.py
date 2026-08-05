"""Buildroom operator entry — the SINGLE installed operator-side entry point.

The actual operator/autopilot/cron entry calls THIS CLI, which calls the
BuildroomExecutionDispatcher exactly once. The dispatcher then selects
exactly ONE branch:

  legacy          -> existing buildroom_loop.py subprocess (unchanged)
  managed_canary  -> ManagedBuildroomCaller (allowlisted task ids only)

Default is legacy. No general managed cutover happens in this goal.

Usage (installed package):
  python -m curaops.buildroom.operator_entry --project <pack> [--legacy-peekxd]
  python -m curaops.buildroom.operator_entry --canary <task-id> --description <text>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from curaops.buildroom.dispatcher import (
    BuildroomExecutionDispatcher,
    DispatcherConfig,
    DispatcherConfigError,
    _run_legacy_entrypoint,
)
from curaops.buildroom.managed_execution import ManagedBuildroomCaller
from curaops.harness.gateway import HarnessGatewayService
from curaops.harness.registry import ExecutionMode


def _resolve_harness_registry() -> Path:
    """Deterministische Registry-Auflösung für den installierten Einstieg.

    1. package resource curaops/harness/contracts/harness-registry.yaml
       (installierte Distribution — DOD-07)
    2. repo-relative fixtures/harness-registry.yaml (source checkout)
    Nie cwd-abhängig; wirft DispatcherConfigError wenn nichts gefunden.
    """
    try:
        from importlib import resources

        pkg_res = resources.files("curaops.harness") / "contracts/harness-registry.yaml"
        if pkg_res.is_file():
            return Path(str(pkg_res))
    except Exception:
        pass
    checkout = Path(__file__).resolve().parents[2] / "fixtures/harness-registry.yaml"
    if checkout.is_file():
        return checkout
    raise DispatcherConfigError(
        "CONFIG_INVALID: harness registry nicht auflösbar (package resource "
        "und checkout fehlen)")


def _build_dispatcher(canary: bool = False) -> BuildroomExecutionDispatcher:
    """Construct the dispatcher from the canonical config layer.

    B2 (Legacy lazy): managed_canary-Komponenten (Route-Manifest, Registry,
    ManagedBuildroomCaller) werden NUR konstruiert, wenn der managed_canary-
    Zweig tatsächlich gewählt wird. Für legacy wird der Dispatcher ohne
    managed_caller gebaut — legacy braucht weder local-mode.yaml, noch
    Harness-Registry, noch LiteLLM, noch ODS.
    """
    if canary:
        # Nur der managed-Zweig braucht die produktive Route (workload/local)
        # und die Registry — B1/B2-Vertrag.
        live_manifest = Path.home() / ".local/share/ai-stack/routes/local-mode.yaml"
        if not live_manifest.is_file():
            raise DispatcherConfigError(
                "CONFIG_INVALID: route manifest fehlt "
                f"({live_manifest}) — ai-stack local-mode nicht installiert")

        caller = ManagedBuildroomCaller(
            state_path=Path.home() / ".hermes/buildroom/dispatcher/managed-state.json",
            route_manifest=live_manifest,
            gateway=HarnessGatewayService(
                registry_path=_resolve_harness_registry(),
                execution_mode=ExecutionMode.LIVE.value,
            ),
            producer={"name": "conduvera-core", "version": "0.1.0"},
            execution_mode=ExecutionMode.LIVE.value,
        )
        return BuildroomExecutionDispatcher(
            config_path=None,  # canonical resolution
            leases_dir=Path.home() / ".hermes/buildroom/dispatcher/leases",
            managed_caller=caller,
        )
    # legacy: KEINE AI-Stack-/Registry-/Caller-Abhängigkeit. Der Dispatcher
    # läuft ohne managed_caller; der legacy-Zweig ruft buildroom_loop.py als
    # Subprozess (B2-Negativtest: exit 0 ohne Route-Manifest/Registry).
    return BuildroomExecutionDispatcher(
        config_path=None,  # canonical resolution
        leases_dir=Path.home() / ".hermes/buildroom/dispatcher/leases",
        managed_caller=None,
    )


def _run_legacy_operator(*, project: str | None, legacy_peekxd: bool, live: bool) -> int:
    """Run the real legacy path via the dispatcher in legacy mode.

    The legacy branch executes the actual buildroom_loop.py as a subprocess.
    --live: productive tick against the real ~/.hermes state (installed
    autopilot behaviour). Default: isolated proof run (separate HOME).
    B2: legacy konstruiert KEINE managed/AI-Stack-Komponenten.
    """
    dispatcher = _build_dispatcher(canary=False)
    task_id = "legacy-operator-tick"
    result = dispatcher.dispatch(
        task_id=task_id,
        task_description=f"legacy operator tick (project={project or 'peekxd'})",
        live=live,
    )
    # The dispatcher legacy branch already runs the real subprocess; the
    # detail carries the full report.
    detail = result.detail if isinstance(result.detail, dict) else {}
    print(json.dumps({
        "execution_path": result.execution_path,
        "status": result.status,
        "entrypoint": detail.get("entrypoint"),
        "exit_code": detail.get("exit_code"),
        "isolated_home": detail.get("isolated_home"),
        "state_phase": (detail.get("state_after") or {}).get("phase"),
    }, indent=2, ensure_ascii=False))
    return 0 if result.status == "legacy_completed" else 1


def _run_canary(*, task_id: str, description: str) -> int:
    """Run one allowlisted canary task via the dispatcher (managed branch)."""
    dispatcher = _build_dispatcher(canary=True)
    result = dispatcher.dispatch(task_id=task_id, task_description=description)
    print(json.dumps({
        "task_id": task_id,
        "execution_path": result.execution_path,
        "status": result.status,
        "final_status": result.final_status_readable,
    }, indent=2, ensure_ascii=False))
    return 0 if result.status == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buildroom operator entry (dispatcher)")
    parser.add_argument("--project", "-p", default=None, help="Legacy project pack name")
    parser.add_argument("--legacy-peekxd", action="store_true",
                        help="Legacy compatibility orchestrator path")
    parser.add_argument("--canary", default=None, help="Allowlisted canary task id")
    parser.add_argument("--description", default="canary task", help="Task description")
    parser.add_argument("--live", action="store_true",
                        help="Produktiver Tick gegen echten ~/.hermes-State "
                             "(Default: isolierter Beweis-Lauf)")
    args = parser.parse_args(argv)

    try:
        if args.canary:
            return _run_canary(task_id=args.canary, description=args.description)
        return _run_legacy_operator(project=args.project,
                                    legacy_peekxd=args.legacy_peekxd,
                                    live=args.live)
    except DispatcherConfigError as exc:
        print(f"CONFIG_INVALID: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — operator entry must never crash silently
        print(f"OPERATOR_ENTRY_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
