#!/usr/bin/env python3
"""Generic Hermes Buildroom loop entry point.

v0.23.1 hardening rules:
- Generic mode requires --project.
- Legacy PeekXD fallback is explicit via --legacy-peekxd only.
- This file contains no hardcoded PeekXD filesystem paths; legacy behavior is
  delegated to peekxd_buildroom_loop_v20.py only when explicitly requested.
"""

from __future__ import annotations

import argparse
import sys

from buildroom_core import ALL_PHASES, ProjectPackError, format_pack_summary, resolve_project
from manual_authorization import ManualAuthorizationError, consume_manual_authorization
from peekxd_buildroom_loop_v20 import BuildroomRunResult


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes Buildroom Orchestrator v0.23.1")
    parser.add_argument("--project", "-p", help="Project pack name or YAML path")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize configuration without running")
    parser.add_argument("--manual", action="store_true", help="Use the explicit bounded manual entry path")
    parser.add_argument("--authorization-id", help="Previously issued one-shot manual authorization ID")
    parser.add_argument("--phase", choices=ALL_PHASES, default="RESEARCHER", help="One explicitly requested phase")
    parser.add_argument(
        "--legacy-peekxd",
        action="store_true",
        help="Explicit compatibility mode for the old PeekXD-coupled orchestrator path",
    )
    return parser.parse_args(argv)


def load_orchestrator_class():
    """Import the compatibility orchestrator only after config validation."""
    from peekxd_buildroom_loop_v20 import BuildroomOrchestrator

    return BuildroomOrchestrator


def validate_manual_entry(pack, args: argparse.Namespace) -> str | None:
    """Return an exact policy blocker before one-shot capability consumption."""
    if not (args.authorization_id or "").strip():
        return "MANUAL_AUTHORIZATION_REQUIRED"
    if pack.autopilot_enabled or pack.delivery_mode != "engineering_finish_line":
        return "MANUAL_MODE_NOT_ALLOWED"
    try:
        pack.require_phase(args.phase)
    except ProjectPackError as exc:
        if str(exc).startswith("PHASE_NOT_ALLOWED"):
            return "PHASE_NOT_ALLOWED"
        return "PROJECTPACK_NOT_READY"
    if not pack.repo_path.is_dir() or not (pack.repo_path / ".git").exists():
        return "PROJECTPACK_NOT_READY"
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.project and args.legacy_peekxd:
        print("ERROR: --project and --legacy-peekxd are mutually exclusive", file=sys.stderr)
        return 2

    if args.manual and args.legacy_peekxd:
        print("MANUAL_MODE_NOT_ALLOWED", file=sys.stderr)
        return 4

    if not args.manual and args.authorization_id:
        print("AUTOPILOT_ONLY_PATH", file=sys.stderr)
        return 4

    if not args.project and not args.legacy_peekxd:
        print("PROJECT_PACK_REQUIRED", file=sys.stderr)
        return 2

    if args.legacy_peekxd:
        if args.dry_run:
            print("Legacy PeekXD compatibility mode")
            print("  Orchestrator: peekxd_buildroom_loop_v20.py")
            print("  ProjectPack: disabled")
            print("  Generic mode: false")
            return 0
        orchestrator_cls = load_orchestrator_class()
        orchestrator = orchestrator_cls()
        orchestrator.run()
        return 0

    try:
        pack = resolve_project(args.project)
    except ProjectPackError as exc:
        if args.manual:
            print("PROJECTPACK_NOT_READY", file=sys.stderr)
            return 4
        print(str(exc), file=sys.stderr)
        return 2

    if args.manual:
        blocker = validate_manual_entry(pack, args)
        if blocker:
            print(blocker, file=sys.stderr)
            return 4
        if args.dry_run:
            try:
                authorization = consume_manual_authorization(
                    args.authorization_id.strip(),
                    pack=pack,
                    phase=args.phase,
                    dry_run=True,
                )
            except ManualAuthorizationError as exc:
                print(str(exc), file=sys.stderr)
                return 4
            print(format_pack_summary(pack))
            print("  Generic mode: true")
            print("MANUAL_DRY_RUN_READY")
            print(f"  Requested phase: {args.phase}")
            print(f"  Issuer: {authorization['issuer']}")
            print(f"  Request ID: {authorization['request_id']}")
            print("  Automatic continuation: disabled")
            return 0

        orchestrator_cls = load_orchestrator_class()
        orchestrator = orchestrator_cls(pack)
        orchestrator.reconcile_state()
        if orchestrator.state.get("phase") != args.phase:
            print("PROJECTPACK_NOT_READY", file=sys.stderr)
            return 4
        authorization_blocker: list[str] = []

        def consume_before_side_effect():
            try:
                authorization = consume_manual_authorization(
                    args.authorization_id.strip(),
                    pack=pack,
                    phase=args.phase,
                    dry_run=False,
                )
            except ManualAuthorizationError as exc:
                authorization_blocker.append(str(exc))
                return BuildroomRunResult.PROJECTPACK_BLOCKED
            orchestrator.state["manual_request_id"] = authorization["request_id"]
            orchestrator.state["manual_authorization_id"] = authorization["id"]
            orchestrator.state["manual_authorization_issuer"] = authorization["issuer"]
            orchestrator.state["manual_phase_limit"] = args.phase
            return None

        result = orchestrator.run(
            autonomous=False,
            phase_limit=args.phase,
            reconcile=False,
            before_phase_side_effect=consume_before_side_effect,
        )
        if authorization_blocker:
            print(authorization_blocker[0], file=sys.stderr)
            return 4
        if result is not BuildroomRunResult.PHASE_EXECUTED:
            print(result.value, file=sys.stderr)
            return 4
        print(BuildroomRunResult.PHASE_EXECUTED.value)
        return 0

    if args.dry_run:
        print(format_pack_summary(pack))
        print("  Generic mode: true")
        return 0

    try:
        pack.require_autonomous_phase("RESEARCHER")
    except ProjectPackError as exc:
        print(f"PROJECTPACK_POLICY_BLOCK: {exc}", file=sys.stderr)
        return 3

    orchestrator_cls = load_orchestrator_class()
    orchestrator = orchestrator_cls(pack)
    orchestrator.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
