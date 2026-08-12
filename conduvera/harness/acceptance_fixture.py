"""Acceptance-only deterministic fixture harness (CONDUVERA-ACTIVITY-ACCEPTANCE).

A REAL managed harness for the isolated acceptance service. It is launched by
the normal Control-Plane submit/queue/claim/dispatch path, creates a real OS
process, runs through the registered-worktree binding and the managed
systemd-scope isolation, and its real exit code is collected by the production
evidence path.

Security model (see acceptance contract §5):
- only one fixed scenario enum is accepted (no arbitrary command / shell);
- the scenario is passed as a fixed `--scenario <ENUM>` argv element built
  internally by the adapter from config (never caller-controlled string);
- it never reads or executes a prompt, never invokes bash/sh, never accepts a
  binary path or shell string;
- it is enabled only when CONDUVERA_ACCEPTANCE_MODE=1 and the service is the
  isolated acceptance instance (separate state dir + loopback HTTP port);
- it is absent from normal doctor/default runtime.

Fixed scenarios:
  HOLD_UNTIL_CANCEL            sleep until SIGTERM/SIGKILL (expect cancel)
  HOLD_THEN_EXIT_0             sleep N then exit 0
  EXIT_7                       exit 7 immediately (optionally after short sleep)
  HOLD_UNTIL_TIMEOUT           sleep until timeout termination path kills it
  EXIT_0_WITH_INVALID_EVIDENCE exit 0 but write a corrupt/mismatched evidence
                               marker so the evidence validator fails closed
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

SCENARIOS = (
    "HOLD_UNTIL_CANCEL",
    "HOLD_THEN_EXIT_0",
    "EXIT_7",
    "HOLD_UNTIL_TIMEOUT",
    "EXIT_0_WITH_INVALID_EVIDENCE",
)


def _main() -> int:
    p = argparse.ArgumentParser(prog="conduvera-acceptance-fixture")
    p.add_argument("--scenario", required=True, choices=list(SCENARIOS))
    p.add_argument("--hold-s", type=float, default=60.0)
    p.add_argument("--out", default="", help="write a status json to this path")
    args = p.parse_args()

    if args.out:
        Path(args.out).write_text(json.dumps({
            "scenario": args.scenario,
            "pid": os.getpid(),
            "status": "started",
        }))

    if args.scenario == "EXIT_7":
        if args.hold_s and args.hold_s > 0:
            time.sleep(min(args.hold_s, 2.0))
        if args.out:
            Path(args.out).write_text(json.dumps({
                "scenario": args.scenario, "pid": os.getpid(),
                "status": "done", "exit_code": 7}))
        return 7

    if args.scenario == "EXIT_0_WITH_INVALID_EVIDENCE":
        if args.out:
            Path(args.out).write_text(json.dumps({
                "scenario": args.scenario,
                "pid": os.getpid(),
                "status": "done",
                "exit_code": 0,
                "evidence_invalid": True,
            }))
        return 0

    # HOLD_UNTIL_CANCEL / HOLD_THEN_EXIT_0 / HOLD_UNTIL_TIMEOUT
    if args.hold_s and args.hold_s > 0:
        deadline = time.monotonic() + args.hold_s
        while time.monotonic() < deadline:
            time.sleep(0.2)
    if args.scenario == "HOLD_THEN_EXIT_0":
        if args.out:
            Path(args.out).write_text(json.dumps({
                "scenario": args.scenario, "pid": os.getpid(),
                "status": "done", "exit_code": 0, "evidence_invalid": False,
            }))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
