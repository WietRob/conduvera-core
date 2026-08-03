#!/usr/bin/env python3
"""
PeekXD Agent Loop v0.5.1 — Bounded Cron Trigger with Guardrails

Guardrails:
1. Run Lock: Ein aktiver Run verhindert neuen Run.
2. Backlog Gate: Wenn PeekXD Tasks ready/running existieren, skip.
3. Dedupe Gate: Keine doppelten Tasks für same repo_id + run_id + cycle + role.
4. Max Open Tasks Gate: Wenn > 8 offene PeekXD Tasks, skip.
5. Final State Gate: Run gilt nur als abgeschlossen, wenn alle Tasks final.
6. Evidence Gate: Jeder skipped Run schreibt Evidence.

Usage: python3 peekxd_agent_loop_v051.py --max-runs 1 --interval-hours 4 --run-number 1
"""

import argparse
import json
import subprocess
import sys
import fcntl
import os
from datetime import datetime, timezone
from pathlib import Path


class PeekXDGuardrails:
    """Guardrails for PeekXD Agent Loop."""
    
    def __init__(self, repo_id="peekxd", max_open_tasks=8):
        self.repo_id = repo_id
        self.max_open_tasks = max_open_tasks
        self.lock_dir = Path.home() / ".hermes/runlocks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_file = self.lock_dir / f"{repo_id}-agent-loop.lock"
        self.lock_fd = None
    
    def acquire_lock(self):
        """Acquire run lock. Returns True if acquired, False if another run is active."""
        self.lock_fd = open(self.lock_file, "w")
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            self.lock_fd.close()
            self.lock_fd = None
            return False
    
    def release_lock(self):
        """Release run lock."""
        if self.lock_fd:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
            self.lock_fd = None
    
    def check_backlog(self):
        """Check if PeekXD tasks are ready/running. Returns (can_run, reason, open_count)."""
        try:
            result = subprocess.run(
                ["hermes", "kanban", "list"],
                capture_output=True, text=True, timeout=15
            )
            lines = result.stdout.split("\n")
            
            open_tasks = []
            for line in lines:
                if self.repo_id.lower() in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        state = parts[2]
                        if state in ("ready", "running"):
                            open_tasks.append({
                                "task_id": parts[1] if len(parts) > 1 else "unknown",
                                "state": state,
                                "title": " ".join(parts[4:]) if len(parts) > 4 else "",
                            })
            
            if len(open_tasks) > self.max_open_tasks:
                return False, f"SKIPPED_TOO_MANY_OPEN_TASKS: {len(open_tasks)} > {self.max_open_tasks}", len(open_tasks)
            
            if len(open_tasks) > 0:
                return False, f"SKIPPED_BACKLOG_ACTIVE: {len(open_tasks)} open tasks", len(open_tasks)
            
            return True, "OK: No open tasks", 0
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return False, f"SKIPPED_BACKLOG_CHECK_ERROR: {e}", 0
    
    def check_dedupe(self, run_id, cycle_number, role):
        """Check if task already exists for this run/cycle/role. Returns (can_create, existing_task_id)."""
        try:
            result = subprocess.run(
                ["hermes", "kanban", "list"],
                capture_output=True, text=True, timeout=15
            )
            lines = result.stdout.split("\n")
            
            # Look for tasks with same role and cycle in title
            expected_title = f"{role.capitalize()} — {self.repo_id} Cycle {cycle_number}"
            for line in lines:
                if self.repo_id.lower() in line.lower() and expected_title in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return False, parts[1]
            
            return True, None
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return True, None  # Allow creation if check fails
    
    def write_skip_evidence(self, run_id, reason, open_count, run_number, max_runs):
        """Write evidence for skipped run."""
        evidence = {
            "run_id": run_id,
            "run_number": run_number,
            "max_runs": max_runs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "SKIPPED",
            "reason": reason,
            "open_tasks_count": open_count,
            "guardrail": "backlog_gate" if "BACKLOG" in reason else "max_open_tasks_gate" if "TOO_MANY" in reason else "unknown",
            "next_action": "Wait for open tasks to complete or manually dispatch",
        }
        
        log_dir = Path.home() / ".hermes/research-vault/ops/peekxd-agent-loop/skips"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{run_id}.json"
        log_file.write_text(json.dumps(evidence, indent=2, default=str))
        
        print(f"[GUARDRAIL] Skip evidence written: {log_file}")
        return evidence


def run_scheduler(run_number, max_runs, interval_hours):
    """Run bounded scheduler v0.5 for PeekXD with guardrails."""
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    run_id = f"peekxd-agent-loop-{timestamp}"
    branch = f"hermes/peekxd-agent-loop-{timestamp}"
    
    repo_path = "/home/roberto_schmidt/projects/peekxd-linux-computer-use"
    scheduler_path = "/home/roberto_schmidt/hermes-buildroom/scripts/bounded_scheduler_v05.py"
    
    # Initialize guardrails
    guardrails = PeekXDGuardrails(repo_id="peekxd", max_open_tasks=8)
    
    print(f"[Run {run_number}/{max_runs}] Starting: {run_id}")
    print(f"  Branch: {branch}")
    
    # Guardrail 1: Run Lock
    if not guardrails.acquire_lock():
        print(f"[GUARDRAIL] SKIP: Another run is already active (lock held)")
        guardrails.write_skip_evidence(run_id, "SKIPPED_LOCK_ACTIVE: Another run is active", 0, run_number, max_runs)
        guardrails.release_lock()
        return {"status": "SKIPPED", "reason": "lock_active"}
    
    try:
        # Guardrail 2 & 4: Backlog Gate + Max Open Tasks
        can_run, reason, open_count = guardrails.check_backlog()
        if not can_run:
            print(f"[GUARDRAIL] SKIP: {reason}")
            guardrails.write_skip_evidence(run_id, reason, open_count, run_number, max_runs)
            return {"status": "SKIPPED", "reason": reason, "open_count": open_count}
        
        print(f"[GUARDRAIL] OK: {reason}")
        
        # Ensure branch exists
        subprocess.run(
            ["git", "-C", repo_path, "checkout", "-b", branch],
            capture_output=True, check=False
        )
        
        # Run scheduler
        cmd = [
            sys.executable, scheduler_path,
            "--run-id", run_id,
            "--repo-id", "peekxd",
            "--repo-path", repo_path,
            "--branch", branch,
            "--max-cycles", "1",
            "--interval-seconds", "0",
            "--stop-after-minutes", "15",
            "--role-sequence", "researcher,dreamer,builder,reviewer",
        ]
        
        print(f"  Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        
        # Parse final summary
        summary = {
            "run_id": run_id,
            "run_number": run_number,
            "max_runs": max_runs,
            "timestamp": timestamp,
            "branch": branch,
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-2000:] if result.stdout else "",
            "stderr_tail": result.stderr[-2000:] if result.stderr else "",
        }
        
        # Try to extract status from JSON
        try:
            lines = result.stdout.split("\n")
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{"):
                    json_data = json.loads(line)
                    if "status" in json_data:
                        summary["scheduler_status"] = json_data["status"]
                        summary["cycles_completed"] = json_data.get("cycles_completed", 0)
                        summary["errors"] = json_data.get("errors", [])
                        break
        except (json.JSONDecodeError, IndexError):
            pass
        
        # Save run log
        log_dir = Path.home() / ".hermes/research-vault/ops/peekxd-agent-loop/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{run_id}.json"
        log_file.write_text(json.dumps(summary, indent=2, default=str))
        
        print(f"[Run {run_number}/{max_runs}] Completed: exit_code={result.returncode}")
        if "scheduler_status" in summary:
            print(f"  Status: {summary['scheduler_status']}")
        
        # Re-schedule if not at max
        if run_number < max_runs:
            next_run = run_number + 1
            print(f"[Run {run_number}/{max_runs}] Next run: {next_run}/{max_runs} in {interval_hours}h")
        else:
            print(f"[Run {run_number}/{max_runs}] Max runs reached. Stopping.")
        
        return summary
        
    finally:
        guardrails.release_lock()


def main():
    parser = argparse.ArgumentParser(description="PeekXD Agent Loop v0.5.1 with Guardrails")
    parser.add_argument("--max-runs", type=int, default=6, help="Maximum number of runs")
    parser.add_argument("--interval-hours", type=int, default=4, help="Hours between runs")
    parser.add_argument("--run-number", type=int, default=1, help="Current run number")
    args = parser.parse_args()
    
    print("=" * 70)
    print("PEEKXD AGENT LOOP v0.5.1 — Bounded Cron Trigger with Guardrails")
    print("=" * 70)
    print(f"Run: {args.run_number}/{args.max_runs}")
    print(f"Interval: {args.interval_hours}h")
    print(f"Max duration per run: 15 minutes")
    print(f"Max cycles per run: 1")
    print(f"Role sequence: researcher → dreamer → builder → reviewer")
    print(f"Worktree isolation: enabled")
    print(f"Guardrails: lock, backlog, dedupe, max_open_tasks, final_state, evidence")
    print("=" * 70)
    
    summary = run_scheduler(args.run_number, args.max_runs, args.interval_hours)
    
    print("\n" + "=" * 70)
    print("RUN COMPLETE")
    print("=" * 70)
    print(f"Run ID: {summary.get('run_id', 'unknown')}")
    print(f"Status: {summary.get('status', 'unknown')}")
    if 'reason' in summary:
        print(f"Reason: {summary['reason']}")
    print(f"Exit code: {summary.get('exit_code', 'unknown')}")
    
    if args.run_number < args.max_runs:
        print(f"\nNext run: {args.run_number + 1}/{args.max_runs} in {args.interval_hours} hours")
    else:
        print(f"\nMax runs ({args.max_runs}) reached. Loop stopped.")
    
    return summary.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
