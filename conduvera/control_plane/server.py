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
    svc = ControlPlaneService(
        registry=registry,
        gateway_service=gateway,
        config=config,
        global_concurrency=int(os.environ.get("CONDUVERA_GLOBAL_CONCURRENCY", "4")),
    )
    from conduvera.control_plane.outbox import EventOutbox
    svc.set_outbox(EventOutbox(config.outbox_path, webhook_url=None))
    return svc

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conduvera-control-plane")
    parser.add_argument("--state-dir", default=None, help="override state directory")
    parser.add_argument("--socket", default=None, help="override socket path")
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
    print(f"conduvera-control-plane listening on {config.socket_path} "
          f"(engine: dispatcher+monitor)", flush=True)
    daemon.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
