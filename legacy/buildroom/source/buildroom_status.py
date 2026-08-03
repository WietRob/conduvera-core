#!/usr/bin/env python3
"""Convenience command: select project, validate state/adapters, and print operator summary."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".hermes" / "buildroom-state"


def run(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=ROOT
    ).stdout.strip()


def load(rel: str) -> dict:
    return json.loads((STATE / rel).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", metavar="REPO_ID", help="select active project (optional)")
    parser.add_argument("--mode", default="planning_only", help="mode when selecting (default: planning_only)")
    parser.add_argument("--selected-by", default="operator", help="who selects")
    parser.add_argument("--reason", default="", help="selection reason")
    parser.add_argument("--job", help="path to a job room to summarize after status")
    parser.add_argument("--no-summary", action="store_true", help="skip operator summary even if job is given")
    args = parser.parse_args()

    if args.select:
        cmd = [
            sys.executable, "scripts/select_project.py", "select", args.select,
            "--mode", args.mode,
            "--selected-by", args.selected_by,
        ]
        if args.reason:
            cmd += ["--reason", args.reason]
        out = run(cmd)
        print(out)
        if "FAIL" in out:
            return 1

    print(run([sys.executable, "scripts/validate_state.py"]))
    print(run([sys.executable, "scripts/validate_adapters.py"]))
    print(run([sys.executable, "scripts/list_projects.py"]))

    if args.job and not args.no_summary:
        job = Path(args.job).expanduser().resolve()
        out = run([sys.executable, "scripts/build_operator_summary.py", str(job)])
        print(out)
        summary = job / "operator" / "operator-summary.md"
        if summary.exists():
            print("\n--- Operator Summary ---\n")
            print(summary.read_text(encoding="utf-8"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
