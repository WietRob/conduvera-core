#!/usr/bin/env python3
"""Authority-plane issuer for one-shot manual Buildroom capabilities."""

from __future__ import annotations

import argparse
import sys

from buildroom_core import ALL_PHASES, ProjectPackError, resolve_project
from manual_authorization import ManualAuthorizationError, issue_manual_authorization


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue bounded manual Buildroom authorization")
    subparsers = parser.add_subparsers(dest="command", required=True)
    issue = subparsers.add_parser("issue")
    issue.add_argument("--project", "-p", required=True)
    issue.add_argument("--phase", choices=ALL_PHASES, required=True)
    issue.add_argument("--request-id", required=True)
    issue.add_argument("--ttl-seconds", type=int, default=300)
    issue.add_argument("--dry-run-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        pack = resolve_project(args.project)
        authorization_id = issue_manual_authorization(
            pack,
            phase=args.phase,
            request_id=args.request_id,
            dry_run_only=args.dry_run_only,
            ttl_seconds=args.ttl_seconds,
        )
    except (ProjectPackError, ManualAuthorizationError) as exc:
        print(str(exc), file=sys.stderr)
        return 4
    print(authorization_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
