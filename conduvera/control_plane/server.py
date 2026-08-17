"""Control plane daemon entry point (systemd service / CLI).

Usage:
  python -m conduvera.control_plane.server [--state-dir DIR] [--registry PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from conduvera.control_plane.daemon import ControlPlaneDaemon
from conduvera.control_plane.service import ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry
from conduvera.harness.gateway import HarnessGatewayService


def build_service(state_dir: str | None = None) -> ControlPlaneService:
    config = ControlPlaneConfig.default(state_dir)
    registry = PersistentSessionRegistry(config.registry_path)
    gateway = HarnessGatewayService(
        registry_path=Path(__file__).resolve().parent.parent / "harness" / "contracts" / "harness-registry.yaml",
        execution_mode="LIVE",
    )
    # Acceptance-only fixture harness is enabled ONLY under
    # CONDUVERA_ACCEPTANCE_MODE=1 on the isolated acceptance service. It is
    # never part of the normal doctor/default runtime.
    adapter_ids = ("hermes_scoped", "codex_cli", "opencode_cli", "hermes")
    if os.environ.get("CONDUVERA_ACCEPTANCE_MODE") == "1":
        adapter_ids = adapter_ids + ("acceptance_fixture_cli",)
    svc = ControlPlaneService(
        registry=registry,
        gateway_service=gateway,
        config=config,
        adapter_ids=adapter_ids,
        global_concurrency=int(os.environ.get("CONDUVERA_GLOBAL_CONCURRENCY", "4")),
        # B5/multi-session: under the isolated acceptance service let the
        # fixture harness run up to the global concurrency so two controlled
        # MANAGED sessions can coexist simultaneously (never changes the
        # normal per-harness default of 1).
        per_harness_limits=(
            {"acceptance_fixture_cli": int(os.environ.get(
                "CONDUVERA_GLOBAL_CONCURRENCY", "4"))}
            if os.environ.get("CONDUVERA_ACCEPTANCE_MODE") == "1" else None),
    )
    from conduvera.control_plane.outbox import EventOutbox
    svc.set_outbox(EventOutbox(config.outbox_path, webhook_url=None))
    return svc

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conduvera-control-plane")
    parser.add_argument("--state-dir", default=None, help="override state directory")
    parser.add_argument("--socket", default=None, help="override socket path")
    parser.add_argument("--http-port", type=int, default=0,
                        help="expose the Activity HTTP bridge on this TCP port "
                             "(0 disables)")
    parser.add_argument("--once", action="store_true", help="run one request then exit (health probe)")
    args = parser.parse_args(argv)

    config = ControlPlaneConfig.default(args.state_dir)
    if args.socket:
        config.socket_path = Path(args.socket)
    service = build_service(args.state_dir)
    engine = None

    daemon = ControlPlaneDaemon(service=service, socket_path=config.socket_path)
    daemon.start()

    if args.once:
        # health probe: doctor and exit
        print(json.dumps({"ok": True, "doctor": service.doctor()}, indent=2))
        daemon.stop()
        return 0

    def _shutdown(signum, frame):  # noqa: ARG001
        daemon.stop()
        if http_bridge is not None:
            http_bridge.stop()
        if engine is not None:
            engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Daemon-owned dispatcher + monitor loops (BUILDROOM-PILOT-V1)
    from conduvera.control_plane.engine import ControlPlaneEngine
    engine = ControlPlaneEngine(
        service=service,
        scheduler=service.scheduler,
        registry=service.registry,
    )
    engine.start()

    http_bridge = None
    if args.http_port:
        from conduvera.control_plane.http_bridge import HttpBridge
        http_bridge = HttpBridge(daemon=daemon, port=args.http_port)
        http_bridge.start()
        print(f"conduvera-activity http bridge on http://127.0.0.1:{args.http_port}/ui/",
              flush=True)

    print(f"conduvera-control-plane listening on {config.socket_path} "
          f"(engine: dispatcher+monitor)", flush=True)
    daemon.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
