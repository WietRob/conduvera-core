#!/usr/bin/env python3
"""Buildroom v0.23 — Repo-Agnostic Core with Project Pack support

v0.23: ProjectPack class from buildroom_core replaces hardcoded PeekXD paths.
Use --project <name> to load a project pack, or default to PeekXD legacy paths.
"""

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from buildroom_kanban_paths import resolve_task_log
from buildroom_no_progress import observe_reconciliation
from buildroom_task_terminal import (
    PhaseEvidenceExpectation,
    TaskCheckResult,
    TaskTerminalState,
    classify_kanban_status,
    evaluate_phase_completion,
    load_task_evidence,
    parse_kanban_show,
)
from buildroom_task_binding import (
    TaskBinding,
    binding_for_phase,
    clear_task_binding,
    kanban_argv,
    store_task_binding,
)
from buildroom_cycle49_preflight import WorkerObservation, classify_worker
from buildroom_review_convergence import (
    ReviewConvergenceError,
    authorize_push,
    ensure_review_epoch,
    mark_prepush_sweep,
    require_session_mutation_allowed,
    run_pre_push_gates,
)
from fleet_router import (
    RoutingError,
    TaskContext,
    canonical_identity,
    consume_route_authorization,
    route_and_authorize,
)

# v0.23: Import ProjectPack and resolve_project from buildroom_core
try:
    from buildroom_core import (
        ExecutionObservation,
        ProjectPack,
        ProjectPackError,
        resolve_project,
        validate_execution_evidence,
    )
    HAS_PROJECT_PACK = True
except ImportError:
    HAS_PROJECT_PACK = False

# Legacy PeekXD hardcoded paths — used when no project pack is loaded
REPO_PATH = Path.home() / "projects/peekxd-linux-computer-use"
EVIDENCE_DIR = Path.home() / ".hermes/research-vault/ops/peekxd-buildroom-v09"
KANBAN = "curaops-vrp"
STATE_FILE = EVIDENCE_DIR / "orchestrator-state.json"
LOCK_FILE = EVIDENCE_DIR / ".orchestrator-lock"
MISSION = "COMPUTER_USE_CORE_V1"
BASELINE_FILE = EVIDENCE_DIR / "test-baseline.json"

PHASE_LOCKS = {
    "RESEARCHER": EVIDENCE_DIR / ".researcher-running",
    "DREAMER": EVIDENCE_DIR / ".dreamer-running",
    "BUILDER": EVIDENCE_DIR / ".builder-running",
    "REVIEWER": EVIDENCE_DIR / ".reviewer-running",
}

EVIDENCE_PATTERNS = {
    "RESEARCHER": "researcher/researcher-cycle-{cycle}-{date}.md",
    "DREAMER": "dreamer/dreamer-cycle-{cycle}-{date}.md",
    "BUILDER": "builder/builder-cycle-{cycle}-{candidate}-{date}.md",
    "REVIEWER": "reviewer/reviewer-cycle-{cycle}-{date}.md",
    "REPORTER": "reporter/reporter-cycle-{cycle}-{date}.md",
}

FORBIDDEN_SLUGS = {"green", "yellow", "red", "hold", "reject", "candidate", "build", "unknown", "none", "skip"}
VALID_SLUG_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)+$')


class BuildroomRunResult(str, Enum):
    PHASE_EXECUTED = "PHASE_EXECUTED"
    PHASE_ALREADY_TERMINAL = "PHASE_ALREADY_TERMINAL"
    LOCK_UNAVAILABLE = "LOCK_UNAVAILABLE"
    PROJECTPACK_BLOCKED = "PROJECTPACK_BLOCKED"
    STATE_MISMATCH = "STATE_MISMATCH"
    DISPATCH_BLOCKED = "DISPATCH_BLOCKED"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

PROVIDER_QUOTA_PATTERNS = [
    r"quota (exhausted|exceeded|limit)",
    r"usage limit",
    r"billing cycle",
    r"HTTP 403.*(?:quota|limit|billing)",
    r"HTTP 429.*(?:rate limit|quota)",
]
PROVIDER_AUTH_PATTERNS = [
    r"invalid API key",
    r"auth.*(?:missing|fail|invalid|error)",
    r"HTTP 401",
    r"access_token",
    r"token expired",
]

MAX_ATTEMPTS_PER_PHASE = 5

# v0.17: Modes that restrict what the state machine may do
RESTRICTED_MODES = {
    "RESEARCHER_DREAMER_ONLY": {
        "allowed_phases": {"RESEARCHER", "DREAMER"},
        "blocked_actions": {"BUILDER", "PR_CREATE", "MERGE"},
    },
    "BUILDER_PR_REVIEWER_ONLY": {
        "allowed_phases": {"BUILDER", "REVIEWER"},
        "blocked_actions": {"MERGE", "REPORTER"},
    },
    "MERGE_REPORTER_ONLY": {
        "allowed_phases": {"MERGE", "REPORTER"},
        "blocked_actions": {"BUILDER", "PR_CREATE", "RESEARCHER", "DREAMER"},
    },
}

FALLBACK_POLICY = {
    "RESEARCHER": [
        ("researcher", "researcher (primary)"),
        ("researcher", "researcher/deepseek"),
        ("analyst",  "analyst/codex-spark"),
        ("researcher", "researcher/deepseek-flash"),
        ("analyst",  "analyst/codex-gpt55"),
    ],
    "DREAMER": [
        ("dreamer", "dreamer (primary)"),
        ("dreamer", "dreamer/deepseek"),
        ("writer",  "writer/codex-spark"),
        ("dreamer", "dreamer/deepseek-flash"),
    ],
    "BUILDER": [
        ("builder", "builder (primary)"),
        ("builder", "builder/deepseek"),
        ("backend", "backend/codex-spark"),
        ("backend", "backend/deepseek-flash"),
    ],
    "REVIEWER": [
        ("reviewer", "reviewer (primary)"),
        ("reviewer", "reviewer/codex-spark"),
        ("reviewer", "reviewer/deepseek"),
        ("reviewer", "reviewer/codex-gpt55"),
    ],
}

# v0.17: Repo-side strategy documents for directive discovery
REPO_STRATEGY_FILES = [
    "docs/adr/ADR-0006-v0.4.0-priorisierung-cua-driver-differenzierung.md",
    "docs/adr/ADR-0005-peekaboo-v3-parity-roadmap.md",
    "docs/adr/ADR-0001-softbox-ghost-mode.md",
    "docs/adr/ADR-0002-softbox-shadow-mode.md",
    "docs/adr/ADR-0003-softbox-ghost-live-overlay.md",
    "docs/adr/ADR-0004-confirmable-ghost-actions.md",
    "docs/strategy/PEEKABOO_V3_PARITY_AUDIT.md",
]

# v0.18: Directive compliance validation
MAX_COMPLIANCE_RETRIES = 1  # one retry per phase before HOLD_FOR_BOSS

RESEARCHER_EPIC_KEYWORDS = {
    "safety-moat mcp": ["safety-moat", "safety moat", "safetyguard", "safety guard",
                         "mcp server safety", "mcp safety", "ghost", "shadow", "zone", "audit"],
    "snapshot-element-id": ["snapshot", "snapshotstore", "element-id", "element id",
                             "snapshot_id", "element_id", "see --json"],
    "at-spi2 action-first": ["at-spi", "at_spi", "pyatspi", "set-value", "set_value",
                              "do_action", "perform-action", "perform_action"],
    "wayland-wslg": ["wayland", "wslg", "grim", "slurp", "wtype", "ydotool",
                      "wayland hardening"],
}

DREAMER_EPIC_KEYWORDS = {
    "safety-moat mcp": ["safety-moat", "safety moat", "mcp-exposition", "mcp exposition",
                         "safetyguard", "ghost", "zone", "audit", "safety middleware"],
    "snapshot-element-id": ["snapshot", "snapshotstore", "element-id", "element id",
                             "snapshot_id", "snapshot skeleton"],
}


class BuildroomOrchestrator:
    def __init__(self, pack=None):
        # v0.23: Use ProjectPack if provided, else fall back to hardcoded globals
        if pack is not None:
            self.pack = pack
            self._repo_path = pack.repo_path
            self._evidence_dir = pack.evidence_dir
            global STATE_FILE, LOCK_FILE, BASELINE_FILE, EVIDENCE_DIR, REPO_PATH
            STATE_FILE = pack.state_file
            LOCK_FILE = pack.lock_file
            BASELINE_FILE = pack.baseline_file
            EVIDENCE_DIR = pack.evidence_dir
            REPO_PATH = pack.repo_path
        else:
            self.pack = None
            self._repo_path = REPO_PATH
            self._evidence_dir = EVIDENCE_DIR
        self.state = self.load_state()
        if "attempts" not in self.state:
            self.state["attempts"] = {}
        self.repo_path = Path(
            self.state.get("repo_path")
            or (self.pack.repo_path if self.pack else self._repo_path)
        )
        self.evidence_dir = Path(
            self.state.get("evidence_dir")
            or (self.pack.evidence_dir if self.pack else self._evidence_dir)
        )
        self.baseline_file = (
            self.pack.baseline_file if self.pack else self.evidence_dir / "test-baseline.json"
        )

    def project_label(self):
        return getattr(self.pack, "project_name", None) or self.repo_path.name

    def project_slug(self):
        return re.sub(r"[^a-z0-9-]+", "-", self.project_label().lower()).strip("-") or "project"

    def configured_profile(self, role, legacy_default):
        """Resolve phase ownership from ProjectPack without changing legacy mode."""
        if self.pack and getattr(self.pack, "policy_defined", False):
            return self.pack.profile_for(role)
        return legacy_default

    def require_pack_phase(self, phase, *, autonomous=False):
        """Fail closed before dispatch/action while leaving live state untouched."""
        if not self.pack:
            return True
        try:
            if autonomous:
                self.pack.require_autonomous_phase(phase)
            else:
                self.pack.require_phase(phase)
        except ProjectPackError as exc:
            print(f"⛔ PROJECTPACK_POLICY_BLOCK: {exc}")
            return False
        return True

    def transition_to_phase(self, phase):
        """Authorize a transition before mutating orchestrator state."""
        if not self.require_pack_phase(phase):
            return False
        self.state["phase"] = phase
        self.state["status"] = "NEXT_PHASE"
        self.save_state()
        return True

    def _review_epoch(self, *, initial_head=None):
        """Return the persistent finish-line epoch without resetting its budget."""
        if not self.pack or not self.pack.review_convergence.enabled:
            return None
        if initial_head is None:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                raise ReviewConvergenceError("REVIEW_EPOCH_INITIAL_HEAD_REQUIRED")
            initial_head = result.stdout.strip()
        epoch = ensure_review_epoch(
            self.state,
            scope={
                "project": self.project_label(),
                "candidate": self.state.get("current_candidate"),
                "builder_branch": self.state.get("builder_branch"),
            },
            contract={
                "delivery_mode": self.pack.delivery_mode,
                "allowed_phases": self.pack.allowed_phases,
                "test_command": self.pack.test_command,
                "review_convergence": self.pack.review_convergence.__dict__,
            },
            initial_head=initial_head,
        )
        self.save_state()
        return epoch

    def record_prepush_review(self, *, head, approved):
        """Bind the mandatory adversarial sweep to one exact local head."""
        epoch = self._review_epoch()
        if epoch is None:
            return
        mark_prepush_sweep(epoch, head=head, approved=approved)
        self.save_state()

    def researcher_focus_areas(self):
        if self.pack and getattr(self.pack, "researcher_focus_areas", ""):
            return self.pack.researcher_focus_areas.strip()
        return (
            "Analyze the project architecture, core modules, tests, CLI/API surfaces, and safety boundaries.\n"
            "Identify small, testable gaps with concrete file references and candidate signals.\n"
        )

    def dreamer_epic_hints(self):
        if self.pack and getattr(self.pack, "dreamer_epic_hints", ""):
            return self.pack.dreamer_epic_hints.strip()
        return (
            "Prioritize small, testable candidates mapped to researcher findings.\n"
            "Prefer core/CLI improvements before adapters, and avoid unrelated scope creep.\n"
        )

    def repo_strategy_files(self):
        if self.pack:
            return list(getattr(self.pack, "strategy_files", ()) or ())
        return list(REPO_STRATEGY_FILES)

    def build_reporter_message(self, cycle):
        candidate = self.state.get("current_candidate", "unknown")
        pr_url = self.state.get("pr_open", "none")
        return f"🤖 {self.project_label()} Buildroom Cycle {cycle}\n\nCandidate: {candidate}\nPR: {pr_url}\nVerdict: MERGED\nOrchestrator: v0.15\n"

    def load_state(self):
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except json.JSONDecodeError:
                pass
        return {
            "cycle": 1, "phase": "RESEARCHER", "status": "NEXT_CYCLE",
            "pr_open": None, "current_candidate": None, "last_run": None,
            "task_bindings": {}, "attempts": {},
        }

    def save_state(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    def acquire_lock(self):
        try:
            self.lock_fd = open(LOCK_FILE, "w")
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            return False

    def release_lock(self):
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
        except:
            pass

    # ── Safety checks ───────────────────────────────────────────────────

    def check_main_green(self):
        """Canonical clean-main truth for starting a new autonomous phase."""
        try:
            branch = subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", "--show-current"],
                capture_output=True, text=True, timeout=10,
            )
            head = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            default_branch = str(getattr(self.pack, "default_branch", "main"))
            upstream = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", f"origin/{default_branch}"],
                capture_output=True, text=True, timeout=10,
            )
            status = subprocess.run(
                ["git", "-C", str(self.repo_path), "status", "--porcelain=v1"],
                capture_output=True, text=True, timeout=10,
            )
            if any(result.returncode != 0 for result in (branch, head, upstream, status)):
                return False
            baseline = {}
            baseline_file = self.baseline_file
            if baseline_file.exists():
                baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
            return (
                branch.stdout.strip() == default_branch
                and head.stdout.strip() == upstream.stdout.strip()
                and not status.stdout.strip()
                and baseline.get("all_passed") is True
                and baseline.get("result") == "PASS"
                and baseline.get("project") == str(getattr(self.pack, "project_name", ""))
                and baseline.get("repository") == str(getattr(self.pack, "github_repo", ""))
                and baseline.get("default_branch") == default_branch
                and baseline.get("head") == head.stdout.strip()
                and baseline.get("command") == str(getattr(self.pack, "test_command", "pytest -q"))
            )
        except Exception:
            return False

    def check_working_tree_clean(self):
        try:
            status = subprocess.run(
                ["git", "-C", str(self.repo_path), "status", "--porcelain=v1"],
                capture_output=True, text=True, timeout=10,
            )
            return status.returncode == 0 and not status.stdout.strip()
        except Exception:
            return False

    def check_open_prs(self):
        try:
            repo_args = []
            github_repo = getattr(self.pack, "github_repo", "") if self.pack else ""
            if github_repo:
                repo_args = ["--repo", github_repo]
            r = subprocess.run(["gh", "pr", "list", *repo_args,
                              "--state", "open", "--limit", "1000", "--json", "number,url"],
                             capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return None, []
            prs = json.loads(r.stdout) if r.stdout.strip() else []
            return len(prs), prs
        except Exception:
            return None, []

    def check_active_builders(self):
        """Return True only for a live worker conflicting with this project.

        The historical safety field ``active_builders`` is an inverted alias:
        safety passes when this method returns False. All boards are inspected
        directly; the process-global current board is irrelevant.
        """
        try:
            home = Path.home()
            databases = [("default", home / ".hermes/kanban.db")]
            databases.extend(
                (path.parent.name, path)
                for path in (home / ".hermes/kanban/boards").glob("*/kanban.db")
            )
            completed = {
                int(item.get("cycle"))
                for item in self.state.get("completed_cycles", [])
                if isinstance(item, dict) and item.get("cycle") is not None
            }
            preserved = {
                str(item.get("task_id"))
                for item in self.state.get("historical_tasks", [])
                if isinstance(item, dict) and item.get("task_id")
            }
            observations = []
            for board, database in databases:
                if not database.exists():
                    continue
                connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id,title,assignee,status,workspace_path,current_run_id "
                    "FROM tasks WHERE status='running'"
                )
                for task in rows:
                    run = connection.execute(
                        "SELECT profile,status,worker_pid FROM task_runs "
                        "WHERE task_id=? ORDER BY id DESC LIMIT 1", (task["id"],)
                    ).fetchone()
                    pid = int(run["worker_pid"]) if run and run["worker_pid"] else None
                    alive = bool(pid and Path(f"/proc/{pid}").exists())
                    title = str(task["title"] or "")
                    cycle_match = re.search(r"Cycle\s+(\d+)", title, re.IGNORECASE)
                    cycle = int(cycle_match.group(1)) if cycle_match else None
                    workspace = str(task["workspace_path"] or "")
                    project_matches = (
                        "peekxd" in title.lower()
                        or (workspace and Path(workspace).resolve().is_relative_to(self.repo_path.resolve()))
                    )
                    observation = WorkerObservation(
                        task_id=str(task["id"]), board=board,
                        profile=str((run["profile"] if run else None) or task["assignee"] or ""),
                        task_status=str(task["status"]),
                        run_status=str(run["status"] if run else ""),
                        worker_pid=pid, worker_alive=alive, workspace=workspace or None,
                        cycle=cycle, project_matches=project_matches,
                        historical_preserved=str(task["id"]) in preserved,
                    )
                    observations.append(classify_worker(observation, completed_cycles=completed))
            self.last_worker_classifications = observations
            return any(item.conflicts_with_project for item in observations)
        except Exception:
            self.last_worker_classifications = []
            return True

    def check_no_revert_policy(self):
        profiles = ["researcher", "writer", "backend", "reviewer", "ops", "frontend", "analyst"]
        missing = []
        for p in profiles:
            soul = Path.home() / f".hermes/profiles/{p}/SOUL.md"
            if not soul.exists():
                missing.append(p); continue
            content = soul.read_text()
            if "no_revert_policy" not in content and "No-Revert" not in content:
                missing.append(p)
        return len(missing) == 0, missing

    def safety_checks(self):
        mg = self.check_main_green()
        opc, ops = self.check_open_prs()
        ab = self.check_active_builders()
        nr_ok, nr_miss = self.check_no_revert_policy()
        phase = self.state.get("phase", "")
        pr_open = self.state.get("pr_open")
        open_prs_ok = True
        delivery_mode = getattr(self.pack, "delivery_mode", "") if self.pack else ""
        if opc is None: open_prs_ok = False
        elif delivery_mode == "engineering_finish_line": open_prs_ok = True
        elif opc == 0: open_prs_ok = True
        elif opc == 1 and phase == "REVIEWER" and pr_open:
            pr_urls = [p.get("url", "") for p in ops]
            open_prs_ok = pr_open in pr_urls or any(pr_open.endswith(str(p.get("number", ""))) for p in ops)
        elif opc == 1 and phase == "MERGE": open_prs_ok = True
        elif opc > 1: open_prs_ok = False
        elif opc == 1 and phase not in ("REVIEWER", "MERGE"): open_prs_ok = False
        no_conflicting_active_workers = not ab
        return {
            "main_green": mg, "open_prs": open_prs_ok,
            "no_conflicting_active_workers": no_conflicting_active_workers,
            # Backward-compatible alias. Semantics are safety-pass, not presence.
            "active_builders": no_conflicting_active_workers,
            "no_revert_policy": nr_ok,
            "no_revert_missing_profiles": nr_miss,
        }

    # ── Evidence ────────────────────────────────────────────────────────

    def check_evidence(self, phase, cycle, candidate=None):
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        if phase == "BUILDER" and candidate:
            pattern = EVIDENCE_PATTERNS[phase].format(cycle=cycle, candidate=candidate, date=date_str)
        else:
            pattern = EVIDENCE_PATTERNS[phase].format(cycle=cycle, date=date_str)
        ep = EVIDENCE_DIR / pattern
        return ep.exists(), ep

    def check_any_evidence(self, phase, cycle, candidate=None):
        if phase == "BUILDER" and candidate:
            pattern = f"builder/builder-cycle-{cycle}-{candidate}-*.md"; ed = EVIDENCE_DIR / "builder"
        elif phase == "BUILDER":
            pattern = f"builder/builder-cycle-{cycle}-*-*.md"; ed = EVIDENCE_DIR / "builder"
        else:
            pattern = EVIDENCE_PATTERNS[phase].format(cycle=cycle, date="*")
            ed = EVIDENCE_DIR / pattern.split("/")[0]
        if not ed.exists(): return False, None
        matches = list(ed.glob(pattern.split("/")[1] if "/" in pattern else pattern))
        return len(matches) > 0, matches[0] if matches else None

    def check_bound_evidence(self, phase, cycle):
        binding = self.task_binding(phase)
        if not binding or binding.cycle != cycle or not binding.evidence_path:
            return False, None
        path = Path(binding.evidence_path)
        return path.is_file(), path

    def bound_task_verdict(self, phase, cycle):
        found, path = self.check_bound_evidence(phase, cycle)
        if not found or path is None:
            return None
        try:
            record = load_task_evidence(path)
        except (OSError, ValueError):
            return None
        return str(record.get("verdict") or "") or None

    def _extract_execution_evidence(self, evidence_path):
        """Extract the single execution-evidence-v1 JSON object from markdown."""
        text = evidence_path.read_text(encoding="utf-8")
        candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        records = []
        for raw in candidates:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("schema") == "execution-evidence-v1":
                records.append(record)
        if len(records) != 1:
            raise ProjectPackError(f"EXECUTION_EVIDENCE_RECORD_COUNT: {len(records)}")
        return records[0]

    def _worktree_for_branch(self, branch):
        """Resolve the existing assigned worktree without creating or changing it."""
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            return None
        current_path = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                current_path = Path(line.removeprefix("worktree "))
            elif line == f"branch refs/heads/{branch}" and current_path:
                return current_path
        return None

    def _observe_execution(self, record):
        """Independently observe branch diff and tests in the assigned worktree."""
        branch = record.get("branch", "")
        base_commit = record.get("base_commit", "")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
            raise ProjectPackError("INVALID_EVIDENCE_BRANCH")
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", base_commit):
            raise ProjectPackError("INVALID_EVIDENCE_BASE_COMMIT")
        worktree = self._worktree_for_branch(branch)
        if worktree is None:
            raise ProjectPackError("ASSIGNED_WORKTREE_NOT_FOUND")
        diff = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--name-only", f"{base_commit}...HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if diff.returncode != 0:
            raise ProjectPackError("INDEPENDENT_DIFF_FAILED")
        files = tuple(line.strip() for line in diff.stdout.splitlines() if line.strip())
        test_command = self.pack.test_command if self.pack else "pytest -q"
        test = subprocess.run(
            test_command, shell=True, cwd=str(worktree), capture_output=True,
            text=True, timeout=180, check=False,
        )
        return ExecutionObservation(
            branch=branch,
            files_changed=files,
            test_command=test_command,
            test_exit_code=test.returncode,
            base_commit=base_commit,
        )

    def _validate_phase_execution_evidence(self, role, evidence_path, *, binding=None):
        if not self.pack or not getattr(self.pack, "policy_defined", False):
            return True
        try:
            record = self._extract_execution_evidence(evidence_path)
            if binding is not None and record.get("run_id") != binding.task_id:
                raise ProjectPackError("EXECUTION_EVIDENCE_TASK_MISMATCH")
            expected_backend = self.pack.backend_for(role)
            if record.get("backend") != expected_backend:
                raise ProjectPackError("EXECUTION_EVIDENCE_BACKEND_MISMATCH")
            observation = self._observe_execution(record)
            validate_execution_evidence(
                record,
                expected_role=role,
                expected_repo=self.pack.github_repo,
                observation=observation,
            )
        except (OSError, subprocess.SubprocessError, ProjectPackError) as exc:
            print(f"  ⛔ EXECUTION_EVIDENCE_INVALID: {exc}")
            return False
        return True

    def check_builder_evidence(self, cycle):
        """Require the exact bound Builder report and execution evidence."""
        binding = self.task_binding("BUILDER")
        if not binding or binding.cycle != cycle or not binding.evidence_path:
            return False, None
        path = Path(binding.evidence_path)
        if not path.is_file():
            return False, path
        return self._validate_phase_execution_evidence("BUILDER", path, binding=binding), path

    def check_reviewer_evidence(self, cycle):
        """Require the exact bound Reviewer report and execution evidence."""
        binding = self.task_binding("REVIEWER")
        if not binding or binding.cycle != cycle or not binding.evidence_path:
            return False, None
        path = Path(binding.evidence_path)
        if not path.is_file():
            return False, path
        return self._validate_phase_execution_evidence("REVIEWER", path, binding=binding), path

    def validate_candidate_slug(self, slug):
        if not slug: return False, "empty slug"
        if slug.lower() in FORBIDDEN_SLUGS: return False, f"forbidden slug: {slug}"
        if not VALID_SLUG_RE.match(slug): return False, f"invalid slug format: {slug}"
        return True, "valid"

    # ── Kanban helpers ──────────────────────────────────────────────────

    def run_cmd(self, cmd, cwd=None, timeout=30):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             cwd=cwd or str(REPO_PATH), timeout=timeout)
            return r.returncode == 0, r.stdout, r.stderr
        except Exception as e:
            return False, "", str(e)

    def kanban_board(self):
        board = str(getattr(self.pack, "kanban_board", "") if self.pack else "")
        if not board:
            raise ValueError("PROJECTPACK_KANBAN_BOARD_REQUIRED")
        return board

    def task_binding(self, phase):
        return binding_for_phase(self.state, phase)

    def kanban_create(self, title, assignee, body):
        """Create on the ProjectPack board, never the process-global current board."""
        try:
            command = kanban_argv(
                "create",
                board=self.kanban_board(),
                extra=(title, "--assignee", assignee, "--body", body),
            )
            r = subprocess.run(
                command, capture_output=True, text=True, timeout=30, cwd=str(Path.home())
            )
            if r.returncode != 0:
                return None, f"kanban create failed (rc={r.returncode}): {r.stderr[:200]}"
            m = re.search(r"Created\s+(t_[a-f0-9]+)", r.stdout)
            if not m:
                return None, f"no task ID in output: {r.stdout[:200]}"
            return m.group(1), "OK"
        except Exception as exc:
            return None, f"kanban create exception: {exc}"

    def _kanban_run(self, operation, binding, *, extra=(), timeout=15):
        r = subprocess.run(
            kanban_argv(operation, binding, extra=extra),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
        )
        return r.returncode == 0, r.stdout, r.stderr

    def kanban_show(self, binding):
        ok, stdout, _ = self._kanban_run("show", binding)
        return ok, stdout

    def kanban_dispatch(self, board, max_tasks=1):
        r = subprocess.run(
            kanban_argv("dispatch", board=board, extra=("--max", str(max_tasks))),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home()),
        )
        return r.returncode == 0, r.stdout

    def kanban_comment(self, binding, text):
        result = subprocess.run(
            kanban_argv(
                "comment", binding,
                extra=("--author", "orchestrator", text),
            ),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home()),
        )
        return result.returncode == 0, result.stdout

    def _capture_dispatch_head(self):
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ProjectPackError("TASK_DISPATCH_HEAD_UNAVAILABLE")
        return result.stdout.strip()

    def _task_evidence_path(self, phase, cycle, task_id):
        stem = phase.lower()
        return self.evidence_dir / stem / f"{stem}-cycle-{cycle}-task-{task_id}.md"

    def kanban_check_task(self, binding):
        ok, stdout = self.kanban_show(binding)
        return parse_kanban_show(ok=ok, output=stdout)

    def kanban_get_task_log(self, binding):
        path = resolve_task_log(Path.home(), binding.task_id, binding.board)
        if path is None:
            return ""
        try:
            return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        except OSError:
            return ""

    def create_task_with_verify(
        self, title, assignee, body, phase, *,
        authorized_route_id="", provider="", model="",
    ):
        consume_route_authorization(
            authorized_route_id,
            profile=assignee,
            provider=provider,
            model=model,
        )
        cycle = int(self.state.get("cycle", 1))
        board = self.kanban_board()
        stem = phase.lower()
        body = (
            body
            + "\n\nTASK TERMINAL TRUTH CONTRACT:\n"
            + f"- board={board}; cycle={cycle}; phase={phase}; role={phase}\n"
            + f"- exact output: {self.evidence_dir}/{stem}/{stem}-cycle-{cycle}-task-${{KANBAN_TASK_ID}}.md\n"
            + "- include exactly one buildroom-task-evidence-v1 JSON record bound to this task and relevant Git truth\n"
            + "- for execution-evidence-v1 use run_id=${KANBAN_TASK_ID}\n"
        )
        task_id, err = self.kanban_create(title, assignee, body)
        if not task_id: return None, f"CREATE_FAILED: {err}"
        evidence_path = self._task_evidence_path(phase, cycle, task_id)
        repo = str(getattr(self.pack, "github_repo", "") or self.project_slug())
        default_branch = str(getattr(self.pack, "default_branch", "main"))
        binding = TaskBinding(
            task_id=task_id,
            board=board,
            phase=phase,
            cycle=cycle,
            created_at=datetime.now(timezone.utc).isoformat(),
            evidence_path=str(evidence_path),
            dispatched_head=self._capture_dispatch_head(),
            repo=repo,
            default_branch=default_branch,
        )
        store_task_binding(self.state, binding)
        self.save_state()
        ok, _ = self.kanban_show(binding)
        if not ok: return None, f"TASK_NOT_VISIBLE: {task_id}"
        contract = (
            "TASK_BOUND_EVIDENCE_REQUIRED: write exactly " + str(evidence_path) + ". "
            "Include one fenced JSON buildroom-task-evidence-v1 record with "
            f"task_id={task_id}, board={binding.board}, cycle={cycle}, phase={phase}, "
            f"role={phase}, repo={repo}, dispatched_head={binding.dispatched_head}, "
            "relevant git_head/git_base, verdict (Reviewer), and result=COMPLETE."
        )
        ok, _ = self.kanban_comment(binding, contract)
        if not ok: return None, f"TASK_BINDING_COMMENT_FAILED: {task_id}"
        ok, _ = self.kanban_dispatch(binding.board, max_tasks=1)
        if not ok: return None, "DISPATCH_FAILED"
        task_result = self.kanban_check_task(binding)
        if task_result.state is TaskTerminalState.MISSING:
            return None, f"TASK_NOT_VISIBLE_AFTER_DISPATCH: {task_id}"
        return task_id, "OK"

    def dispatch_profile(
        self, *, profile, provider, model, authorized_route_id,
        title, body, phase, direct_query=None, direct_cwd=None, timeout=180,
    ):
        """Consume one route authorization, then dispatch via Kanban or direct smoke."""
        if direct_query is not None:
            consume_route_authorization(
                authorized_route_id,
                profile=profile,
                provider=provider,
                model=model,
            )
            command = [
                "hermes", "-p", profile, "chat", "-q", direct_query,
                "--provider", provider, "-m", model,
                "--source", "capability-router-smoke", "-Q",
            ]
            return subprocess.run(
                command,
                cwd=str(Path(direct_cwd or Path.home()).resolve()),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        return self.create_task_with_verify(
            title,
            profile,
            body,
            phase,
            authorized_route_id=authorized_route_id,
            provider=provider,
            model=model,
        )

    def dispatch_role_execution(
        self, *, task_context, expected_profile, cycle, title, body, phase,
        direct_query=None, direct_cwd=None, timeout=180,
    ):
        """Mandatory profile/model routing seam for every Orchestrator dispatch."""
        request_id = f"{self.project_slug()}-{phase.lower()}-{cycle}-{uuid.uuid4()}"
        decision = route_and_authorize(task_context, request_id=request_id)
        if decision.profile != expected_profile:
            raise RoutingError(
                f"ROUTED_PROFILE_MISMATCH: expected={expected_profile} actual={decision.profile}"
            )
        return self.dispatch_profile(
            profile=decision.profile,
            provider=decision.selected_provider,
            model=decision.selected_model,
            authorized_route_id=decision.route_id,
            title=title,
            body=body,
            phase=phase,
            direct_query=direct_query,
            direct_cwd=direct_cwd,
            timeout=timeout,
        )

    def save_phase_status(self, phase, cycle, status, details=None):
        sd = EVIDENCE_DIR / "status"; sd.mkdir(parents=True, exist_ok=True)
        sf = sd / f"phase-{phase.lower()}-cycle-{cycle}.json"
        data = {"phase": phase, "cycle": cycle, "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details or {}}
        sf.write_text(json.dumps(data, indent=2))

    def _phase_git_truth(self, phase, binding):
        if phase == "REVIEWER":
            pr_url = str(self.state.get("pr_open") or "")
            if not pr_url:
                raise ProjectPackError("REVIEWER_PR_BINDING_MISSING")
            pr_number = pr_url.rstrip("/").split("/")[-1]
            result = subprocess.run(
                ["gh", "pr", "view", pr_number, "--repo", binding.repo,
                 "--json", "headRefOid,baseRefOid"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode != 0:
                raise ProjectPackError("REVIEWER_GIT_TRUTH_UNAVAILABLE")
            payload = json.loads(result.stdout)
            return str(payload.get("headRefOid") or ""), str(payload.get("baseRefOid") or "")
        if phase == "BUILDER":
            branch = str(self.state.get("builder_branch") or "")
            if not branch:
                raise ProjectPackError("BUILDER_BRANCH_BINDING_MISSING")
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", branch],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if result.returncode != 0:
                raise ProjectPackError("BUILDER_GIT_TRUTH_UNAVAILABLE")
            return result.stdout.strip(), binding.dispatched_head
        if not binding.dispatched_head:
            raise ProjectPackError("DISPATCHED_HEAD_BINDING_MISSING")
        return binding.dispatched_head, None

    def _normalize_task_check(self, value):
        if isinstance(value, TaskCheckResult):
            return value
        if isinstance(value, tuple) and value:
            status = str(value[0])
            raw = str(value[1]) if len(value) > 1 else ""
            return TaskCheckResult(classify_kanban_status(status), status, raw)
        return TaskCheckResult(TaskTerminalState.INCONSISTENT, "unknown", str(value))

    def check_phase_complete(self, phase, cycle):
        binding = self.task_binding(phase)
        if binding is None:
            return False, "TASK_MISSING"
        if binding.phase != phase or binding.cycle != cycle or not binding.evidence_path:
            return False, "TASK_STATE_INCONSISTENT"
        task_result = self._normalize_task_check(self.kanban_check_task(binding))
        try:
            git_head, git_base = self._phase_git_truth(phase, binding)
        except (OSError, ValueError, json.JSONDecodeError, ProjectPackError):
            return False, "TASK_STATE_INCONSISTENT"
        expected = PhaseEvidenceExpectation(
            task_id=binding.task_id,
            board=binding.board,
            cycle=cycle,
            phase=phase,
            role=phase,
            repo=str(binding.repo or ""),
            git_head=git_head,
            git_base=git_base,
            reviewer_verdict_required=phase == "REVIEWER",
        )
        completion = evaluate_phase_completion(
            task_result.kanban_status, Path(binding.evidence_path), expected
        )
        if not completion.complete:
            return False, completion.reason
        if phase in ("BUILDER", "REVIEWER") and not self._validate_phase_execution_evidence(
            phase, Path(binding.evidence_path), binding=binding
        ):
            return False, "TASK_EVIDENCE_INVALID:EXECUTION_EVIDENCE"
        return True, "PHASE_COMPLETE"

    def record_no_progress(self, phase, blocker):
        """Record one identical reconciliation failure and enter bounded hold."""
        binding = self.task_binding(phase)
        task_id = binding.task_id if binding else ""
        task_board = binding.board if binding else ""
        worker_log = self.kanban_get_task_log(binding) if binding else ""
        log_fingerprint = hashlib.sha256(worker_log.encode("utf-8")).hexdigest() if worker_log else ""
        result = observe_reconciliation(
            self.state,
            phase=phase,
            status=str(self.state.get("status", "WAITING")),
            blocker=blocker,
            task_id=task_id,
            task_board=task_board,
            evidence_fingerprint="",
            log_fingerprint=log_fingerprint,
            threshold=3,
        )
        self.save_state()
        return result

    # ── v0.14/v0.15: Failure classifier ─────────────────────────────────

    def classify_task_failure(self, phase, binding):
        log = self.kanban_get_task_log(binding)
        if not log: return "UNKNOWN", "no worker log available"
        for pat in PROVIDER_QUOTA_PATTERNS:
            if re.search(pat, log, re.IGNORECASE):
                m = re.search(r"Provider:\s*(\S+)", log) or re.search(r"provider\s+(\S+)", log)
                provider = m.group(1) if m else "unknown"
                return "PROVIDER_QUOTA", f"{provider}: quota exhausted"
        for pat in PROVIDER_AUTH_PATTERNS:
            if re.search(pat, log, re.IGNORECASE):
                return "PROVIDER_AUTH", "auth failure"
        if "protocol violation" in log.lower() or "without calling kanban_complete" in log.lower():
            return "PROTOCOL_VIOLATION", "worker exited without kanban_complete"
        if "timeout" in log.lower(): return "TIMEOUT", "task timed out"
        if "skill not found" in log.lower(): return "TOOLING_PROFILE", "skill not found"
        return "UNKNOWN", "unclassified failure"

    def select_fallback_profile(self, phase, attempt):
        if self.pack and getattr(self.pack, "policy_defined", False):
            profile = self.pack.profile_for(phase)
            return profile, f"ProjectPack owner {profile} with profile-configured model fallbacks"
        policy = FALLBACK_POLICY.get(phase, [])
        if attempt < len(policy): return policy[attempt]
        return None, None

    def maybe_retry_phase(self, phase, cycle):
        binding = self.task_binding(phase)
        if not binding: return False, "no_task_binding"
        attempts = self.state.setdefault("attempts", {}).setdefault(phase, [])
        attempt_count = len(attempts)
        failure_class, reason = self.classify_task_failure(phase, binding)
        print(f"  🔍 Failure classified: {failure_class} — {reason}")
        attempt_record = {
            "task_id": binding.task_id, "board": binding.board, "profile": phase,
            "failure_class": failure_class, "reason": reason,
            "evidence": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        attempts.append(attempt_record)
        self.save_state()
        retryable = failure_class in ("PROVIDER_QUOTA", "PROVIDER_AUTH", "PROTOCOL_VIOLATION")
        if not retryable: return False, f"non_retryable_failure:{failure_class}"
        if attempt_count >= MAX_ATTEMPTS_PER_PHASE: return False, "BLOCKED_MAX_RETRIES"
        fallback_profile, fallback_desc = self.select_fallback_profile(phase, attempt_count + 1)
        if not fallback_profile: return False, "BLOCKED_NO_FALLBACK_PROFILE"
        print(f"  🔄 Retrying with fallback: {fallback_desc}")
        self.state["status"] = "RETRYING_WITH_FALLBACK"
        self.save_state()
        retired = clear_task_binding(self.state, phase)
        if retired:
            self.state.setdefault("task_binding_history", []).append(
                {**retired.to_dict(), "disposition": "RETRY_REPLACED"}
            )
        self.save_state()
        if phase == "RESEARCHER":
            ok = self.phase_researcher_with_profile(cycle, fallback_profile, attempt_count + 1)
        elif phase == "DREAMER":
            ok = self.phase_dreamer_with_profile(cycle, fallback_profile, attempt_count + 1)
        elif phase == "BUILDER":
            ok = self.phase_builder_with_profile(cycle, fallback_profile, attempt_count + 1)
        elif phase == "REVIEWER":
            ok = self.phase_reviewer_with_profile(cycle, self.state.get("pr_open"), fallback_profile, attempt_count + 1)
        else:
            ok = False
        if ok:
            self.state["status"] = "WAITING"
            self.save_state()
            return True, "OK"
        return False, "FALLBACK_DISPATCH_FAILED"

    def handle_terminal_task_failure(self, phase, cycle, reason):
        """Retry an allowed terminal failure once or enter an immediate evidence hold."""
        if not reason.startswith("TASK_TERMINAL_FAILURE:"):
            return None
        retried, retry_reason = self.maybe_retry_phase(phase, cycle)
        if retried:
            return BuildroomRunResult.PHASE_EXECUTED
        failure_class = "UNKNOWN"
        if ":" in retry_reason:
            candidate = retry_reason.rsplit(":", 1)[-1].strip()
            if candidate:
                failure_class = candidate
        attempts = self.state.get("attempts", {}).get(phase, [])
        if attempts and isinstance(attempts[-1], dict):
            failure_class = str(attempts[-1].get("failure_class") or failure_class)
        blocker = f"{reason}:{failure_class}"
        binding = self.task_binding(phase)
        self.state["status"] = "HOLD_FOR_BOSS"
        self.state["blocker"] = blocker
        self.state["root_blocker"] = blocker
        self.state["terminal_failure"] = {
            "phase": phase,
            "cycle": cycle,
            "task_binding": binding.to_dict() if binding else None,
            "reason": reason,
            "failure_class": failure_class,
            "retry_disposition": retry_reason,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_state()
        return BuildroomRunResult.PROJECTPACK_BLOCKED

    # ── v0.17: Directive loader + strategic task body builders ──────────

    def load_cycle_directive(self, cycle: int) -> dict:
        """Load strategic directive for a cycle from state keys + fallback discovery.

        Priority order:
        1. state['directive_file'] — explicit path (used as spec if no cycle-specific spec found)
        2. state['strategy_file'] — explicit path (merged into strategy context)
        3. EVIDENCE_DIR/cycle-<N>-v0.4.0-spec.md or cycle-<N>-*.md
        4. Repo ADR files (ADR-0001 through ADR-0006)

        v0.19: directive_file content is now used as spec fallback when cycle-specific
        spec is missing. This prevents generic body fallback when an explicit directive
        is configured in state.
        """
        directive = {}

        # 1. Explicit state keys — load both directive_file and strategy_file
        directive_file_content = None
        strategy_file_content = None
        for key in ("directive_file", "strategy_file"):
            val = self.state.get(key)
            if val:
                p = Path(val)
                if p.exists():
                    content = p.read_text()
                    directive[key] = content
                    print(f"  📄 Directive loaded from state.{key}: {p.name}")
                    if key == "directive_file":
                        directive_file_content = content
                    else:
                        strategy_file_content = content
                else:
                    print(f"  ⚠️ state.{key} path not found: {val}")

        # 2. Cycle-specific spec file in evidence dir
        spec_candidates = list(EVIDENCE_DIR.glob(f"cycle-{cycle}-*.md"))
        spec_exact = EVIDENCE_DIR / f"cycle-{cycle}-v0.4.0-spec.md"
        if spec_exact.exists():
            directive["spec"] = spec_exact.read_text()
            print(f"  📄 Spec loaded: {spec_exact.name}")
        elif spec_candidates:
            directive["spec"] = spec_candidates[0].read_text()
            print(f"  📄 Spec loaded (glob): {spec_candidates[0].name}")
        elif directive_file_content:
            # v0.19: directive_file content becomes spec fallback
            directive["spec"] = directive_file_content
            print(f"  📄 Spec loaded from directive_file fallback")

        # 3. Repo strategy documents
        adr_texts = []
        for rel_path in self.repo_strategy_files():
            fpath = REPO_PATH / rel_path
            if fpath.exists():
                adr_texts.append(fpath.read_text())
        if adr_texts:
            directive["repo_adrs"] = "\n\n---\n\n".join(adr_texts)
            print(f"  📄 Loaded {len(adr_texts)} repo strategy docs")

        return directive

    def build_researcher_body(self, cycle: int, directive: dict) -> str:
        """Build a directive-aware researcher task body.

        v0.19: If directive_required=true and no directive is available, this
        returns a BLOCKED sentinel instead of a generic body. The caller must
        check for this and set HOLD_FOR_BOSS.
        """
        # v0.19: strict mode — no generic fallback when directive is required
        if self.state.get("directive_required") and (not directive or not directive.get("spec")):
            return "__BLOCKED_MISSING_DIRECTIVE__"

        if not directive or not directive.get("spec"):
            return (
                f"Analyze the {self.project_label()} codebase for gaps.\n\n"
                f"OUTPUT: Write evidence to {EVIDENCE_DIR}/researcher/researcher-cycle-{cycle}-<date>.md\n"
                f"Repo: {REPO_PATH}"
            )

        spec_text = directive.get("spec", "")
        directive_path = self.state.get("directive_file", "")
        strategy_path = self.state.get("strategy_file", "")

        body = (
            f"STRATEGIC MISSION: {self.project_label()} analysis.\n\n"
            f"=== DIRECTIVE ===\n"
            f"{spec_text[:3000]}\n\n"
            f"=== PROJECT FOCUS AREAS ===\n"
            f"{self.researcher_focus_areas()}\n\n"
            f"=== REQUIREMENTS ===\n"
            f"- Minimum 8 findings, each with affected_epic tag\n"
            f"- File:line references for every finding\n"
            f"- Risk and opportunity per finding\n"
            f"- Clear builder candidate signal per finding\n"
            f"- NO generic repair-only findings\n"
            f"- NO unrelated scope creep\n\n"
        )
        if directive_path or strategy_path:
            body += (
                f"=== STRATEGY REFERENCES ===\n"
                f"Directive: {directive_path}\n"
                f"Strategy:  {strategy_path}\n\n"
            )
        body += (
            f"OUTPUT: Write evidence to {EVIDENCE_DIR}/researcher/researcher-cycle-{cycle}-<date>.md\n"
            f"Repo: {REPO_PATH}\n\n"
            f"=== CRITICAL: CANONICAL SCHEMA REQUIRED ===\n\n"
            f"Your output MUST include exactly ONE fenced YAML block with the following format:\n\n"
            f"```buildroom-researcher-v1\n"
            f"schema: researcher-evidence-v1\n"
            f"cycle: {cycle}\n"
            f"directive_used: true\n"
            f"covered_epics:\n"
            f"  safety_moat_mcp: true\n"
            f"  snapshot_element_id: true\n"
            f"  atspi_action_first: true\n"
            f"  wayland_wslg: true\n"
            f"non_compliant_tactical_findings: 0\n"
            f"findings:\n"
            f"  - id: R1\n"
            f"    affected_epic: safety_moat_mcp\n"
            f"    file_refs:\n"
            f"      - src/module.py:123\n"
            f"    risk: medium\n"
            f"    opportunity: expose SafetyGuard\n"
            f"    candidate_signal: mcp-action-safetyguard-gateway\n"
            f"```\n\n"
            f"RULES:\n"
            f"1. The fenced block MUST start with ```buildroom-researcher-v1 on its own line\n"
            f"2. The fenced block MUST end with ``` on its own line\n"
            f"3. The YAML inside MUST be valid and parseable\n"
            f"4. Markdown outside the block is optional and ignored\n"
            f"5. If the fenced block is missing, the task FAILS\n"
            f"6. Do NOT use bold headings like **Schema:** — use the YAML block only\n"
            f"7. Do NOT use tables for findings — use the YAML list format\n\n"
            f"=== ANALYSIS INSTRUCTIONS ===\n"
            f"Analyze the codebase against the directive.\n"
            f"For each finding, provide: id, affected_epic, file_refs, risk, opportunity, candidate_signal.\n"
            f"Ensure all 4 epics are covered.\n"
        )
        return body

    def build_dreamer_body(self, cycle: int, research_evidence_path: str, directive: dict) -> str:
        """Build a directive-aware dreamer task body with epic constraints.

        v0.19: If directive_required=true and no directive is available, this
        returns a BLOCKED sentinel instead of a generic body.
        """
        # v0.19: strict mode — no generic fallback when directive is required
        if self.state.get("directive_required") and (not directive or not directive.get("spec")):
            return "__BLOCKED_MISSING_DIRECTIVE__"

        has_directive = bool(directive and directive.get("spec"))

        if not has_directive:
            return (
                f"Classify Top 5 candidates from Researcher evidence.\n\n"
                f"Input: {research_evidence_path}\n"
                f"OUTPUT: {EVIDENCE_DIR}/dreamer/dreamer-cycle-{cycle}-<date>.md\n"
                f"Requirements: GREEN/YELLOW/RED, valid slugs (feature-name), no color names, min 1 GREEN"
            )

        body = (
            f"Classify candidates from Researcher evidence using project strategy.\n\n"
            f"Input: {research_evidence_path}\n\n"
            f"=== PROJECT EPIC / PRIORITY HINTS ===\n"
            f"{self.dreamer_epic_hints()}\n\n"
            f"=== CANDIDATE REQUIREMENTS ===\n"
            f"- Minimum 6 candidates\n"
            f"- Minimum 2 GREEN\n"
            f"- Candidates must map to the project strategy and researcher findings\n"
            f"- Every candidate: slug, epic, title, source, expected files, acceptance criteria, tests, risk, effort, why GREEN/YELLOW/RED, rollback idea\n"
            f"- NO unrelated scope creep candidates\n\n"
            f"OUTPUT: {EVIDENCE_DIR}/dreamer/dreamer-cycle-{cycle}-<date>.md\n\n"
            f"=== CRITICAL: CANONICAL SCHEMA REQUIRED ===\n\n"
            f"Your output MUST include exactly ONE fenced YAML block with the following format:\n\n"
            f"```buildroom-dreamer-v1\n"
            f"schema: dreamer-candidates-v1\n"
            f"cycle: {cycle}\n"
            f"epic_coverage:\n"
            f"  safety_moat_mcp: true\n"
            f"  snapshot_element_id: true\n"
            f"  atspi_action_first: true\n"
            f"  wayland_wslg: true\n"
            f"candidates:\n"
            f"  - id: D1\n"
            f"    slug: mcp-action-safetyguard-gateway\n"
            f"    priority: GREEN\n"
            f"    epic: safety_moat_mcp\n"
            f"    title: MCP SafetyGuard gateway\n"
            f"    source_finding: R1\n"
            f"    expected_files:\n"
            f"      - src/module.py\n"
            f"    acceptance_criteria:\n"
            f"      - MCP click/type/drag pass through SafetyGuard\n"
            f"    tests:\n"
            f"      - tests/test_mcp_safety.py\n"
            f"    risk: medium\n"
            f"    effort: medium\n"
            f"    rollback: remove middleware hook and MCP tool registration\n"
            f"```\n\n"
            f"RULES:\n"
            f"1. The fenced block MUST start with ```buildroom-dreamer-v1 on its own line\n"
            f"2. The fenced block MUST end with ``` on its own line\n"
            f"3. The YAML inside MUST be valid and parseable\n"
            f"4. Markdown outside the block is optional and ignored\n"
            f"5. If the fenced block is missing, the task FAILS\n"
            f"6. Do NOT use bold headings like **Schema:** — use the YAML block only\n"
            f"7. Do NOT use tables for candidates — use the YAML list format\n\n"
            f"=== YAML QUOTING REQUIREMENT ===\n"
            f"Your fenced YAML MUST parse with PyYAML safe_load.\n"
            f"Every free-text string in YAML MUST be quoted with double quotes.\n"
            f"This is mandatory for: summary, rationale, opportunity, acceptance_criteria,\n"
            f"implementation_notes, tests, rollback, and any item containing ':' or '#'.\n"
            f"Invalid:\n"
            f"  acceptance_criteria:\n"
            f"    - build_semantic_snapshot writes metadata: cache_id\n"
            f"Valid:\n"
            f"  acceptance_criteria:\n"
            f"    - \"build_semantic_snapshot writes metadata: cache_id\"\n\n"
            f"=== CANDIDATE INSTRUCTIONS ===\n"
            f"Classify candidates from Researcher evidence.\n"
            f"For each candidate, provide: id, slug, priority, epic, title, source_finding, expected_files, acceptance_criteria, tests, risk, effort, rollback.\n"
            f"Ensure all 4 epics are covered.\n"
        )
        return body

    # ── v0.19.1: Strict Fenced YAML Block Parsers ───────────────────────────

    def extract_fenced_block(self, text: str, block_name: str) -> str | None:
        """Extract a fenced code block with the given identifier.

        Looks for ```block_name ... ``` blocks.
        Returns the content inside the block (without the fences), or None if not found.

        v0.19.1: Also accepts ```yaml blocks as fallback.
        """
        import re
        # Primary: exact block name
        pattern = rf'```\s*{re.escape(block_name)}\s*\n(.*?)```'
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Fallback: any ```yaml block
        pattern_yaml = rf'```\s*yaml\s*\n(.*?)```'
        m = re.search(pattern_yaml, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    def _safe_yaml_load(self, yaml_text: str) -> dict:
        """Parse canonical fenced YAML schema using PyYAML.

        v0.19.1: Replaced custom parser with yaml.safe_load for correctness.
        """
        try:
            import yaml
        except Exception as e:
            raise RuntimeError(f"PyYAML required for canonical schema parsing: {e}") from e

        try:
            data = yaml.safe_load(yaml_text)
        except Exception as e:
            raise ValueError(f"Invalid canonical YAML schema: {e}") from e

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"Canonical schema must parse to dict, got {type(data).__name__}")
        return data

    def parse_researcher_schema(self, evidence_path) -> dict:
        """Parse researcher evidence using strict fenced YAML block.

        v0.19.1: ONLY reads the ```buildroom-researcher-v1 block.
        Markdown outside the block is ignored.
        """
        content = evidence_path.read_text()
        block = self.extract_fenced_block(content, "buildroom-researcher-v1")
        if not block:
            return {"schema": None, "error": "MISSING_FENCED_BLOCK"}

        data = self._safe_yaml_load(block)
        data["schema"] = data.get("schema", "researcher-evidence-v1")

        # Normalize field names for compatibility with worker variations
        if "schema_version" in data and "schema" not in data:
            data["schema"] = data["schema_version"]
        if "directive_compliance" in data and "directive_used" not in data:
            dc = data["directive_compliance"]
            if isinstance(dc, dict):
                data["directive_used"] = dc.get("directive_used", False)
                if "epics_covered" in dc and "covered_epics" not in data:
                    epics = dc["epics_covered"]
                    if isinstance(epics, list):
                        data["covered_epics"] = {}
                        for e in epics:
                            if isinstance(e, dict):
                                epic_key = e.get("epic", "").lower().replace(" ", "_").replace("-", "_")
                                # Map epic names to canonical keys
                                epic_map = {
                                    "safety_moat_mcp_exposition": "safety_moat_mcp",
                                    "snapshot/element_id_core": "snapshot_element_id",
                                    "at_spi2_action_first": "atspi_action_first",
                                    "wayland/wslg_hardening": "wayland_wslg",
                                }
                                canonical = epic_map.get(epic_key, epic_key)
                                data["covered_epics"][canonical] = e.get("covered", False)
                if "non_compliant_findings" in dc and "non_compliant_tactical_findings" not in data:
                    data["non_compliant_tactical_findings"] = dc["non_compliant_findings"]
        # Also normalize if directive_used is at top level but directive_compliance is nested differently
        if "directive_used" not in data and "directive_compliance" not in data:
            # Check if directive_used is nested under a different key
            for key in list(data.keys()):
                if isinstance(data[key], dict):
                    if "directive_used" in data[key]:
                        data["directive_used"] = data[key]["directive_used"]
                    if "epics_covered" in data[key] and "covered_epics" not in data:
                        epics = data[key]["epics_covered"]
                        if isinstance(epics, list):
                            data["covered_epics"] = {}
                            for e in epics:
                                if isinstance(e, dict):
                                    epic_key = e.get("epic", "").lower().replace(" ", "_").replace("-", "_")
                                    epic_map = {
                                        "safety_moat_mcp_exposition": "safety_moat_mcp",
                                        "snapshot/element_id_core": "snapshot_element_id",
                                        "at_spi2_action_first": "atspi_action_first",
                                        "wayland/wslg_hardening": "wayland_wslg",
                                    }
                                    canonical = epic_map.get(epic_key, epic_key)
                                    data["covered_epics"][canonical] = e.get("covered", False)
                    if "non_compliant_findings" in data[key] and "non_compliant_tactical_findings" not in data:
                        data["non_compliant_tactical_findings"] = data[key]["non_compliant_findings"]

        return data

    def parse_dreamer_schema(self, evidence_path) -> dict:
        """Parse dreamer evidence using strict fenced YAML block.

        v0.19.1: ONLY reads the ```buildroom-dreamer-v1 block.
        Markdown outside the block is ignored.
        """
        content = evidence_path.read_text()
        block = self.extract_fenced_block(content, "buildroom-dreamer-v1")
        if not block:
            return {"schema": None, "error": "MISSING_FENCED_BLOCK"}

        data = self._safe_yaml_load(block)
        data["schema"] = data.get("schema", "dreamer-candidates-v1")

        # Parse candidates list if present
        candidates = data.get("candidates", [])
        parsed_candidates = []
        for c in candidates:
            if isinstance(c, dict):
                parsed_candidates.append(c)
            elif isinstance(c, str):
                # Simple string candidate — not valid
                continue
        data["candidates"] = parsed_candidates

        return data

    def validate_researcher_schema(self, data: dict) -> tuple:
        """Validate parsed researcher schema data.

        Returns: (compliant: bool, reason: str, details: dict)
        """
        if not data:
            return False, "NO_SCHEMA_DATA", {}
        if data.get("schema") != "researcher-evidence-v1":
            return False, f"WRONG_SCHEMA: {data.get('schema')}", {}
        if not data.get("directive_used"):
            return False, "DIRECTIVE_NOT_USED", {}
        covered = data.get("covered_epics", {})
        total = sum(1 for v in covered.values() if v)
        has_safety = covered.get("safety_moat_mcp", False)
        has_snapshot = covered.get("snapshot_element_id", False)
        if total < 3:
            return False, f"INSUFFICIENT_EPICS: {total}/4", {"covered": covered}
        if not has_safety:
            return False, "MISSING_SAFETY_MOAT", {"covered": covered}
        if not has_snapshot:
            return False, "MISSING_SNAPSHOT", {"covered": covered}
        tactical = data.get("non_compliant_tactical")
        if tactical is not None and tactical > 0:
            return False, f"TACTICAL_FINDINGS: {tactical}", {}
        findings = data.get("findings", [])
        if len(findings) < 8:
            return False, f"INSUFFICIENT_FINDINGS: {len(findings)} < 8", {}
        return True, "OK", {"covered": covered, "findings_count": len(findings)}

    def validate_dreamer_schema(self, data: dict) -> tuple:
        """Validate parsed dreamer schema data.

        Returns: (compliant: bool, reason: str, details: dict)
        """
        if not data:
            return False, "NO_SCHEMA_DATA", {}
        if data.get("schema") != "dreamer-candidates-v1":
            return False, f"WRONG_SCHEMA: {data.get('schema')}", {}
        candidates = data.get("candidates", [])
        if len(candidates) < 6:
            return False, f"INSUFFICIENT_CANDIDATES: {len(candidates)} < 6", {}
        # v0.19: Accept P1/P2/P3 as priority indicators, or GREEN/YELLOW/RED
        green_count = sum(1 for c in candidates if c.get("priority", "").upper() in ("GREEN", "P1"))
        if green_count < 2:
            return False, f"INSUFFICIENT_GREEN: {green_count} < 2", {}
        has_safety = any(c.get("epic", "").lower().startswith("safety") or c.get("epic", "").lower() == "epic 1" for c in candidates)
        has_snapshot = any(c.get("epic", "").lower().startswith("snapshot") or c.get("epic", "").lower() == "epic 2" for c in candidates)
        if not has_safety:
            return False, "MISSING_SAFETY_MOAT_CANDIDATE", {}
        if not has_snapshot:
            return False, "MISSING_SNAPSHOT_CANDIDATE", {}
        # Check forbidden slugs and required fields
        forbidden = {"green", "yellow", "red", "hold", "reject", "candidate", "build", "unknown", "none", "skip"}
        for c in candidates:
            slug = c.get("slug", "")
            if not slug:
                return False, "MISSING_SLUG", {"candidate": c}
            if slug.lower() in forbidden:
                return False, f"FORBIDDEN_SLUG: {slug}", {}
            if not VALID_SLUG_RE.match(slug):
                return False, f"INVALID_SLUG: {slug}", {}
            for req in ("epic", "expected_files", "tests", "rollback"):
                if not c.get(req):
                    return False, f"MISSING_{req.upper()}: {slug}", {}
        return True, "OK", {"candidate_count": len(candidates), "green_count": green_count}

    # ── v0.18: Directive compliance validators (legacy — kept for backward compat) ──

    def _text_contains_any(self, text: str, keywords: list) -> bool:
        """Check if text contains any keyword (case-insensitive substring)."""
        lower = text.lower()
        return any(kw.lower() in lower for kw in keywords)

    def _find_directive_section(self, evidence: str) -> str:
        """Extract the Directive Compliance section from evidence text."""
        import re
        m = re.search(r'#+\s*Directive Compliance.*?(?=#+\s|\Z)', evidence,
                      re.DOTALL | re.IGNORECASE)
        return m.group(0) if m else ""

    def validate_researcher_directive_compliance(self, evidence_path) -> tuple:
        """Validate researcher evidence against ADR-0006 epic requirements.

        v0.19: First tries canonical schema validation. Falls back to legacy
        free-text heuristic only if canonical_schema_required is not set.
        """
        if not evidence_path:
            return False, "NO_EVIDENCE", {}

        # v0.19: canonical schema first
        if self.state.get("canonical_schema_required"):
            try:
                data = self.parse_researcher_schema(evidence_path)
            except Exception as e:
                err_msg = str(e)
                snippet = ""
                if "mapping values" in err_msg.lower() or "scanner" in err_msg.lower():
                    import re
                    m = re.search(r'in \"<unicode string>\", line (\d+)', err_msg)
                    line_no = int(m.group(1)) if m else 0
                    lines = evidence_path.read_text().splitlines()
                    if line_no and line_no <= len(lines):
                        snippet = lines[line_no - 1].strip()[:120]
                    return False, f"YAML_PARSE_ERROR: {err_msg[:120]}", {
                        "error_type": "YAML_PARSE_ERROR",
                        "line": line_no,
                        "snippet": snippet,
                        "guidance": "Researcher evidence contains unquoted YAML. Quote all free-text scalars containing colons, hashes, or code-like text in double quotes."
                    }
                raise
            compliant, reason, details = self.validate_researcher_schema(data)
            return compliant, reason, details

        # Legacy free-text heuristic (v0.18)
        content = evidence_path.read_text()
        directive_section = self._find_directive_section(content)

        epic_hits = {}
        for epic, keywords in RESEARCHER_EPIC_KEYWORDS.items():
            epic_hits[epic] = self._text_contains_any(content, keywords)

        covered = sum(1 for v in epic_hits.values() if v)
        has_safety = epic_hits.get("safety-moat mcp", False)
        has_snapshot = epic_hits.get("snapshot-element-id", False)

        if covered < 3:
            return False, f"DIRECTIVE_COMPLIANCE: only {covered}/4 epics covered", epic_hits
        if not has_safety:
            return False, "DIRECTIVE_COMPLIANCE: Safety-Moat MCP-Exposition not covered", epic_hits
        if not has_snapshot:
            return False, "DIRECTIVE_COMPLIANCE: Snapshot/Element-ID Core not covered", epic_hits
        if not directive_section:
            return False, "DIRECTIVE_COMPLIANCE: no 'Directive Compliance' section found", epic_hits

        return True, "OK", epic_hits

    def validate_dreamer_directive_compliance(self, evidence_path) -> tuple:
        """Validate dreamer candidate evidence against ADR-0006 requirements.

        v0.19: First tries canonical schema validation. Falls back to legacy
        free-text heuristic only if canonical_schema_required is not set.
        """
        if not evidence_path:
            return False, "NO_EVIDENCE", {}

        # v0.19: canonical schema first
        if self.state.get("canonical_schema_required"):
            # v0.25.1: catch YAML parse errors for targeted retry
            try:
                data = self.parse_dreamer_schema(evidence_path)
            except Exception as e:
                err_msg = str(e)
                if "ScannerError" in err_msg or "ParserError" in err_msg or "YAMLError" in err_msg:
                    # Extract line/column if available
                    import re
                    lm = re.search(r'line (\d+).*column (\d+)', err_msg)
                    line_info = f" line={lm.group(1)} col={lm.group(2)}" if lm else ""
                    snippet = ""
                    if lm:
                        try:
                            lines = evidence_path.read_text().splitlines()
                            ln = int(lm.group(1)) - 1
                            if 0 <= ln < len(lines):
                                snippet = lines[ln][:120]
                        except Exception:
                            pass
                    return False, f"YAML_PARSE_ERROR{line_info}: {err_msg[:200]}", {
                        "error_type": "YAML_PARSE_ERROR",
                        "line": int(lm.group(1)) if lm else None,
                        "column": int(lm.group(2)) if lm else None,
                        "snippet": snippet,
                        "guidance": "Quote every free-text scalar with double quotes. Use quotes for values containing ':' or technical punctuation."
                    }
                # Check if wrapped error is actually a YAML syntax error
                if "scan" in err_msg.lower() or "mapping values" in err_msg.lower() or "scanner" in err_msg.lower():
                    return False, f"YAML_PARSE_ERROR: {err_msg[:200]}", {
                        "error_type": "YAML_PARSE_ERROR",
                        "guidance": "Quote every free-text scalar with double quotes. Use quotes for values containing ':' or technical punctuation."
                    }
                return False, f"SCHEMA_PARSE_ERROR: {err_msg[:200]}", {"error_type": "SCHEMA_PARSE_ERROR"}
            compliant, reason, details = self.validate_dreamer_schema(data)
            return compliant, reason, details

        # Legacy free-text heuristic (v0.18.1)
        content = evidence_path.read_text()
        lower = content.lower()

        import re
        candidate_count = len([l for l in content.splitlines()
                              if l.strip().startswith("##") and
                                 re.search(r'`([a-z][a-z0-9-]+)`', l)])
        green_count = len([l for l in content.splitlines()
                          if l.strip().startswith("##") and
                             re.search(r'`([a-z][a-z0-9-]+)`', l) and
                             (("GREEN" in l) or
                              ("**GREEN**" in l.lower()))])
        if green_count == 0:
            green_count = len(re.findall(r'\*\*GREEN\*\*', content))

        has_safety = False
        has_snapshot = False
        for epic, keywords in DREAMER_EPIC_KEYWORDS.items():
            if self._text_contains_any(content, keywords):
                if "safety" in epic:
                    has_safety = True
                if "snapshot" in epic:
                    has_snapshot = True

        forbidden = {"green", "yellow", "red", "hold", "reject", "candidate",
                      "build", "unknown", "none", "skip"}
        has_forbidden = False
        for line in content.splitlines():
            strip = line.strip()
            if strip.startswith("##"):
                slug_match = re.search(r'`([a-z0-9-]+)`', strip)
                if slug_match:
                    slug = slug_match.group(1).lower()
                    if slug in forbidden:
                        has_forbidden = True
                        break
                    break

        details = {
            "candidate_count": candidate_count,
            "green_count": green_count,
            "safety_moat": has_safety,
            "snapshot": has_snapshot,
            "forbidden_slug": has_forbidden,
        }

        if has_forbidden:
            return False, "DIRECTIVE_COMPLIANCE: forbidden slug detected", details
        if candidate_count < 5:
            return False, f"DIRECTIVE_COMPLIANCE: only {candidate_count} candidates (need ≥5)", details
        if green_count < 1:
            return False, f"DIRECTIVE_COMPLIANCE: only {green_count} GREEN (need ≥1)", details
        if not has_safety:
            return False, "DIRECTIVE_COMPLIANCE: no Safety-Moat-MCP candidate", details
        if not has_snapshot:
            return False, "DIRECTIVE_COMPLIANCE: no Snapshot/Element-ID candidate", details

        return True, "OK", details

    def _dispatch_compliance_retry(self, phase: str, cycle: int, fail_reason: str):
        """Dispatch a compliance-enforced retry task."""
        profile = "researcher" if phase == "RESEARCHER" else "dreamer"
        if phase == "RESEARCHER":
            directive = self.load_cycle_directive(cycle)
            base = self.build_researcher_body(cycle, directive)
            body = (
                f"YOUR PREVIOUS OUTPUT FAILED DIRECTIVE COMPLIANCE: {fail_reason}\n\n"
                f"Do not produce generic tactical code gaps.\n"
                f"You MUST use the canonical schema 'researcher-evidence-v1'.\n"
                f"Structure findings by the four ADR-0006 epics.\n"
                f"Only re-read the target files; produce a new evidence file.\n\n"
                f"{base}"
            )
            title = f"Researcher — {self.project_label()} Cycle {cycle} [v0.19 compliance retry]"
        else:
            has_ev, ep = self.check_bound_evidence("RESEARCHER", cycle)
            directive = self.load_cycle_directive(cycle)
            base = self.build_dreamer_body(cycle, str(ep) if ep else "", directive)
            body = (
                f"YOUR PREVIOUS OUTPUT FAILED DIRECTIVE COMPLIANCE: {fail_reason}\n\n"
                f"You MUST use the canonical schema 'dreamer-candidates-v1'.\n"
                f"You MUST include Safety-Moat-MCP and Snapshot/Element-ID candidates.\n"
                f"Every candidate MUST have an epic tag.\n\n"
                f"{base}"
            )
            title = f"Dreamer — {self.project_label()} Cycle {cycle} [v0.19 compliance retry]"
        intent = (
            "analyze codebase and produce evidence"
            if phase == "RESEARCHER"
            else "synthesize candidates from research evidence"
        )
        task_id, err = self.dispatch_role_execution(
            task_context=TaskContext(intent=intent),
            expected_profile=profile,
            cycle=cycle,
            title=title,
            body=body,
            phase=phase,
        )
        if task_id:
            print(f"  📝 Compliance retry dispatched — {task_id}")
            return True
        else:
            print(f"  ❌ Compliance retry dispatch failed: {err}")
            return False

    # ── Phase methods ───────────────────────────────────────────────────

    def phase_researcher(self, cycle):
        return self.phase_researcher_with_profile(cycle, self.configured_profile("RESEARCHER", "researcher"), 0)
    def phase_dreamer(self, cycle):
        return self.phase_dreamer_with_profile(cycle, self.configured_profile("DREAMER", "dreamer"), 0)

    def phase_researcher_with_body(self, cycle, directive, body):
        """v0.19: Dispatch researcher with pre-built body (directive already resolved)."""
        profile = self.configured_profile("RESEARCHER", "researcher")
        return self._dispatch_researcher(cycle, profile, 0, directive, body)

    def phase_dreamer_with_body(self, cycle, evidence_path, directive, body):
        """v0.19: Dispatch dreamer with pre-built body (directive already resolved)."""
        profile = self.configured_profile("DREAMER", "dreamer")
        return self._dispatch_dreamer(cycle, profile, 0, evidence_path, directive, body)

    def _dispatch_researcher(self, cycle, profile, attempt, directive, body):
        title = f"Researcher — {self.project_label()} Cycle {cycle} [v0.19 attempt {attempt}]"
        task_id, err = self.dispatch_role_execution(
            task_context=TaskContext(intent="analyze codebase and produce evidence"),
            expected_profile=profile,
            cycle=cycle,
            title=title,
            body=body,
            phase="RESEARCHER",
        )
        if not task_id: return False
        print(f"  📝 Researcher dispatched — {task_id}")
        return True

    def _dispatch_dreamer(self, cycle, profile, attempt, evidence_path, directive, body):
        title = f"Dreamer — {self.project_label()} Cycle {cycle} [v0.19]"
        task_id, err = self.dispatch_role_execution(
            task_context=TaskContext(intent="synthesize candidates from research evidence"),
            expected_profile=profile,
            cycle=cycle,
            title=title,
            body=body,
            phase="DREAMER",
        )
        if not task_id: return False
        print(f"  📝 Dreamer dispatched — {task_id}")
        return True

    def phase_researcher_with_profile(self, cycle, profile, attempt):
        # v0.17/v0.19: directive-aware task body
        directive = self.load_cycle_directive(cycle)
        body = self.build_researcher_body(cycle, directive)
        if body == "__BLOCKED_MISSING_DIRECTIVE__":
            return False
        return self._dispatch_researcher(cycle, profile, attempt, directive, body)

    def phase_dreamer_with_profile(self, cycle, profile, attempt):
        has_evidence, ep = self.check_bound_evidence("RESEARCHER", cycle)
        if not has_evidence: return False
        # v0.17/v0.19: directive-aware task body
        directive = self.load_cycle_directive(cycle)
        body = self.build_dreamer_body(cycle, str(ep), directive)
        if body == "__BLOCKED_MISSING_DIRECTIVE__":
            return False
        return self._dispatch_dreamer(cycle, profile, attempt, str(ep), directive, body)

    def phase_builder_with_profile(self, cycle, profile, attempt):
        candidate = self.state.get("current_candidate", "unknown")
        execution_backend = self.pack.backend_for("BUILDER") if self.pack else "native"
        execution_model = self.pack.model_for("BUILDER") if self.pack else None
        # v0.20: Record builder branch in state for later PR orchestration
        branch_prefix = getattr(self.pack, "builder_branch_prefix", f"autonomy/{self.project_slug()}") if self.pack else f"autonomy/{self.project_slug()}"
        branch_name = f"{branch_prefix}/{candidate}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        self.state["builder_branch"] = branch_name
        self.save_state()
        try:
            epoch = self._review_epoch()
            if epoch is not None:
                require_session_mutation_allowed(
                    epoch, self.pack.review_convergence
                )
        except ReviewConvergenceError as exc:
            self.state["status"] = str(exc)
            self.save_state()
            return False
        title = f"Builder — {self.project_label()} Cycle {cycle}: build {candidate}"
        body = (
            f"Build {candidate} for Cycle {cycle}.\n\n"
            f"1. Create branch: {branch_name}\n"
            f"2. Implement, test, write evidence, commit\n"
            f"3. Do NOT push/PR — orchestrator handles it\n"
            f"4. Record the branch name in builder evidence\n\n"
            f"OUTPUT: {EVIDENCE_DIR}/builder/builder-cycle-{cycle}-{candidate}-<date>.md\n"
            f"Repo: {REPO_PATH}\n\n"
            f"BUILDER EVIDENCE CONTRACT (MUST include in output):\n"
            f"- selected candidate slug: {candidate}\n"
            f"- source dreamer evidence path\n"
            f"- planned files\n"
            f"- actual files changed\n"
            f"- tests run\n"
            f"- test result (pass/fail)\n"
            f"- branch name: {branch_name}\n"
            f"- commit hash\n"
            f"- no direct main commit\n"
            f"- rollback note\n"
            f"- no secret leakage\n"
            f"- builder_verdict: BUILD_COMPLETE or BUILD_FAILED\n\n"
            f"EXECUTION CONTRACT:\n"
            f"- backend: {execution_backend}\n"
            f"- configured model: {execution_model or 'profile-configured-model'}\n"
            f"- Include exactly one fenced JSON object with schema execution-evidence-v1\n"
            f"- Required: role, backend, provider, model, backend_version, run_id, repo, "
            f"base_commit, branch, files_changed, commands_run, tests, result, blocker\n"
            f"- Self-report alone is invalid; disk diff/branch/tests are independently verified\n"
            f"- External adapters may modify only the assigned worktree and never state or merge\n"
            f"- Product finish lines may not modify skills, profiles, memory, routing, or Buildroom core"
        )
        task_id, err = self.dispatch_role_execution(
            task_context=TaskContext(
                intent="implement approved buildroom candidate",
                governed_repo=True,
                approved_candidate=True,
                assigned_worktree=True,
                acceptance_criteria=True,
                test_contract=True,
                bounded_scope=True,
            ),
            expected_profile=profile,
            cycle=cycle,
            title=title,
            body=body,
            phase="BUILDER",
        )
        if not task_id: return False
        print(f"  📝 Builder dispatched — {task_id}")
        return True

    def phase_reviewer_with_profile(self, cycle, pr_url, profile, attempt):
        candidate = self.state.get("current_candidate", "unknown")
        execution_backend = self.pack.backend_for("REVIEWER") if self.pack else "native"
        execution_model = self.pack.model_for("REVIEWER") if self.pack else None
        title = f"Reviewer — {self.project_label()} Cycle {cycle}: review {pr_url}"
        body = (
            f"Review: {pr_url} (candidate: {candidate})\n\n"
            f"1. Read diff, check tests, verify no revert/secrets\n"
            f"2. Verdict must be one of: APPROVE_MERGE, REQUEST_FIX, BLOCK, HOLD_FOR_BOSS\n"
            f"3. For this proof: APPROVE_MERGE means 'Reviewer bestanden' — merge remains FORBIDDEN\n"
            f"4. Write structured evidence with verdict and reasoning\n\n"
            f"OUTPUT: {EVIDENCE_DIR}/reviewer/reviewer-cycle-{cycle}-<date>.md\n\n"
            f"REVIEWER EVIDENCE CONTRACT (MUST include):\n"
            f"- pr_url: {pr_url}\n"
            f"- candidate: {candidate}\n"
            f"- files_reviewed: list of files\n"
            f"- tests_checked: yes/no\n"
            f"- no_secrets: yes/no\n"
            f"- no_revert_violations: yes/no\n"
            f"- verdict: APPROVE_MERGE / REQUEST_FIX / BLOCK / HOLD_FOR_BOSS\n"
            f"- reasoning: detailed review notes\n"
            f"- reviewer_verdict: REVIEW_COMPLETE\n\n"
            f"EXECUTION CONTRACT:\n"
            f"- backend: {execution_backend}\n"
            f"- configured model: {execution_model or 'profile-configured-model'}\n"
            f"- Include exactly one fenced JSON object with schema execution-evidence-v1\n"
            f"- Required: role, backend, provider, model, backend_version, run_id, repo, "
            f"base_commit, branch, files_changed, commands_run, tests, result, blocker\n"
            f"- Builder/external self-reports are not evidence; inspect diff, branch, tests, and security directly"
        )
        builder_profile = self.configured_profile("BUILDER", "builder")
        builder_provider, _ = canonical_identity(builder_profile)
        task_id, err = self.dispatch_role_execution(
            task_context=TaskContext(
                intent="review this PR with independent verification",
                builder_provider=builder_provider,
                binding_required=True,
            ),
            expected_profile=profile,
            cycle=cycle,
            title=title,
            body=body,
            phase="REVIEWER",
        )
        if not task_id: return False
        print(f"  📝 Reviewer dispatched — {task_id}")
        return True

    # ── v0.15: PR Orchestration ─────────────────────────────────────────

    def find_builder_branch(self, candidate):
        """Find the branch the builder created for this candidate.

        v0.20.6: Also strip '+' prefix (git worktree checked-out indicator).
        """
        ok, stdout, _ = self.run_cmd(f"git branch | grep {candidate}", timeout=10)
        if ok and stdout.strip():
            return stdout.strip().lstrip("* +")
        # Try with glob
        ok, stdout, _ = self.run_cmd(f"git branch --list '*{candidate}*'", timeout=10)
        if ok and stdout.strip():
            lines = stdout.strip().split("\n")
            return lines[0].strip().lstrip("* +")
        return None

    def verify_test_baseline(self):
        """Record baseline test results on main before builder work.
        This lets us distinguish pre-existing failures from builder-introduced ones.
        """
        default_branch = str(getattr(self.pack, "default_branch", "main"))
        self.run_cmd(f"git checkout {default_branch}", timeout=15)
        self.run_cmd(f"git pull --ff-only origin {default_branch}", timeout=15)
        test_command = str(getattr(self.pack, "test_command", "pytest -q"))
        ok, stdout, stderr = self.run_cmd(test_command, timeout=180)
        _, head, _ = self.run_cmd("git rev-parse HEAD", timeout=10)
        _, branch, _ = self.run_cmd("git branch --show-current", timeout=10)
        baseline = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project": str(getattr(self.pack, "project_name", "")),
            "repository": str(getattr(self.pack, "github_repo", "")),
            "default_branch": default_branch,
            "all_passed": ok,
            "result": "PASS" if ok else "FAIL",
            "command": test_command,
            "head": head.strip(),
            "branch": branch.strip(),
            "output": stdout[-500:] if stdout else "",
            "stderr": stderr[-500:] if stderr else "",
        }
        if not ok:
            m = re.findall(r'FAILED\s+(\S+)', stdout)
            baseline["pre_existing_failures"] = m
            baseline["total_failed"] = len(m)
            m2 = re.search(r'(\d+)\s+passed', stdout)
            baseline["total_passed"] = int(m2.group(1)) if m2 else 0
        baseline_file = self.baseline_file
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(json.dumps(baseline, indent=2))
        return baseline

    def orchestrator_push_and_create_pr(self, candidate, cycle):
        """v0.15: Auto-detect branch, push, create PR, set state. No manual steps."""
        print(f"  🚀 PR Orchestration: candidate={candidate} cycle={cycle}")
        default_branch = str(getattr(self.pack, "default_branch", "main"))

        if not self.require_pack_phase("REVIEWER"):
            return None, "PHASE_NOT_ALLOWED_REVIEWER"

        # v0.16: mode safety gate — PR_CREATE blocked?
        if self.is_action_blocked_by_mode("PR_CREATE"):
            print(f"  ⛔ MODE_VIOLATION: PR_CREATE blocked by mode={self.state.get('mode')}")
            self.state["status"] = "BLOCKED_MODE_VIOLATION"
            self.save_state()
            return None, "BLOCKED_MODE_VIOLATION"

        # Step 1: Find branch
        branch = self.find_builder_branch(candidate)
        if not branch:
            print(f"  ❌ No branch found for candidate {candidate}")
            self.state["status"] = "BLOCKED_NO_BRANCH"
            self.save_state()
            return None, "BLOCKED_NO_BRANCH"

        # Step 2: Check dirty tree
        if not self.check_working_tree_clean():
            print(f"  ❌ Working tree not clean")
            self.state["status"] = "BLOCKED_DIRTY_TREE"
            self.save_state()
            return None, "BLOCKED_DIRTY_TREE"

        # Step 3: Enforce the persisted convergence epoch before any push.
        if self.pack and self.pack.review_convergence.enabled:
            head_result = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", branch],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if head_result.returncode != 0:
                self.state["status"] = "COMMIT_REFERENCE_GATE_FAILED"
                self.save_state()
                return None, "COMMIT_REFERENCE_GATE_FAILED"
            head = head_result.stdout.strip()
            try:
                epoch = self._review_epoch()
                require_session_mutation_allowed(
                    epoch, self.pack.review_convergence
                )
                run_pre_push_gates(
                    repo=self.repo_path,
                    branch=branch,
                    base_ref=f"origin/{default_branch}",
                    head=head,
                    epoch=epoch,
                    policy=self.pack.review_convergence,
                )
                push_kind = (
                    "initial"
                    if int(epoch.get("push_count", 0)) == 0
                    else "correction"
                )
                authorize_push(
                    epoch,
                    self.pack.review_convergence,
                    head=head,
                    kind=push_kind,
                )
                self.save_state()
            except ReviewConvergenceError as exc:
                self.state["status"] = str(exc)
                self.save_state()
                return None, str(exc)

        # Step 4: Push branch
        ok, _, stderr = self.run_cmd(f"git push -u origin {branch}", timeout=30)
        if not ok:
            print(f"  ❌ Push failed: {stderr[:200]}")
            if "Permission" in stderr or "403" in stderr or "auth" in stderr.lower():
                self.state["status"] = "BLOCKED_GH_AUTH"
            else:
                self.state["status"] = "BLOCKED_PUSH_FAILED"
            self.save_state()
            return None, "BLOCKED_PUSH_FAILED"

        # Step 5: Create PR
        title = f"autonomy: {candidate} — buildroom cycle {cycle}"
        body = f"Builder changes for candidate: {candidate}\n\n- Cycle: {cycle}\n- Orchestrator: v0.15\n- Branch: {branch}"
        ok, stdout, stderr = self.run_cmd(
            f'gh pr create --base {default_branch} --head {branch} --title "{title}" --body "{body}"',
            timeout=30
        )
        if not ok:
            print(f"  ❌ PR creation failed: {stderr[:200]}")
            self.state["status"] = "BLOCKED_PR_CREATE_FAILED"
            self.save_state()
            return None, "BLOCKED_PR_CREATE_FAILED"

        pr_url = stdout.strip()
        print(f"  ✅ PR created: {pr_url}")

        # Step 6: Set state
        self.state["pr_open"] = pr_url
        if not self.transition_to_phase("REVIEWER"):
            return None, "PHASE_NOT_ALLOWED_REVIEWER"
        print(f"  ✅ State: REVIEWER")

        return pr_url, "OK"

    # ── v0.15: Merge Conflict Detection ─────────────────────────────────

    def detect_merge_conflict(self, pr_url):
        """Check if a PR is mergeable.
        Returns: MERGEABLE, CONFLICT, UNKNOWN, or GH_AUTH_BLOCKED
        """
        pr_number = pr_url.split("/")[-1]
        ok, stdout, stderr = self.run_cmd(
            f"gh pr view {pr_number} --json mergeable,mergeStateStatus 2>&1",
            timeout=15
        )
        if not ok:
            if "auth" in stderr.lower() or "403" in stderr or "401" in stderr:
                return "GH_AUTH_BLOCKED", stderr
            return "UNKNOWN", stderr

        try:
            data = json.loads(stdout)
            mergeable = data.get("mergeable", "UNKNOWN")
            status = data.get("mergeStateStatus", "UNKNOWN")
            if mergeable == "MERGEABLE" and status == "CLEAN":
                return "MERGEABLE", f"mergeable={mergeable} status={status}"
            elif status in ("BLOCKED", "DIRTY", "BEHIND", "UNSTABLE"):
                return "CONFLICT", f"status={status}"
            elif mergeable == "CONFLICTING":
                return "CONFLICT", "mergeable=CONFLICTING"
            return "UNKNOWN", f"mergeable={mergeable} status={status}"
        except:
            return "UNKNOWN", f"parse error: {stdout[:100]}"

    # ── Dreamer candidate parsing (v0.14, unchanged) ─────────────────────

    def parse_dreamer_candidates(self, cycle):
        """Parse dreamer candidates from evidence.

        v0.20: First tries canonical schema (fenced YAML), then falls back to legacy heuristics.
        """
        ok, evidence_path = self.check_bound_evidence("DREAMER", cycle)
        if not ok: return [], "NO_DREAMER_EVIDENCE"

        # v0.20: Try canonical schema first
        data = self.parse_dreamer_schema(evidence_path)
        if data.get("schema") == "dreamer-candidates-v1" and "candidates" in data:
            candidates = []
            for c in data.get("candidates", []):
                if isinstance(c, dict):
                    slug = c.get("slug", "")
                    valid, _ = self.validate_candidate_slug(slug)
                    if valid:
                        candidates.append({
                            "slug": slug,
                            "risk": c.get("priority", "").upper(),
                            "title": c.get("title", ""),
                            "source": str(evidence_path),
                        })
            green = [c for c in candidates if c.get("risk") == "GREEN"]
            if green:
                return green, "OK"
            if candidates:
                return candidates, "NO_GREEN_CANDIDATE"

        # Legacy fallback: heuristic parsing
        content = evidence_path.read_text()
        candidates = []
        current = None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("### Candidate:") or line.startswith("### ") or line.startswith("#### "):
                if line.startswith("### Candidate:"):
                    parts = line.split(":", 1)
                    slug = parts[1].strip().lower() if len(parts) > 1 else None
                else:
                    parts = line.split(".", 1)
                    slug = parts[1].strip().lower() if len(parts) > 1 else None
                if slug:
                    valid, _ = self.validate_candidate_slug(slug)
                    if valid:
                        current = {"slug": slug, "risk": None, "title": "", "source": str(evidence_path)}
                        candidates.append(current)
            elif line.startswith("## Candidate "):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    sp = parts[1].strip()
                    sp = sp.replace("`", "")
                    risk = None
                    if "(" in sp and ")" in sp:
                        rp = sp.split("(")[1].split(")")[0].strip().upper()
                        risk = rp if rp in ("GREEN", "YELLOW", "RED") else None
                        slug = sp.split("(")[0].strip().lower()
                    elif "—" in sp or "--" in sp:
                        sep = "—" if "—" in sp else "--"
                        parts2 = sp.split(sep, 1)
                        slug = parts2[0].strip().lower()
                        risk_part = parts2[1].strip().upper() if len(parts2) > 1 else ""
                        risk = risk_part if risk_part in ("GREEN", "YELLOW", "RED") else None
                    else:
                        slug = sp.lower()
                    valid, _ = self.validate_candidate_slug(slug)
                    if valid:
                        current = {"slug": slug, "risk": risk, "title": "", "source": str(evidence_path)}
                        candidates.append(current)
            if current and "risk" in line.lower() and "GREEN" in line.upper():
                current["risk"] = "GREEN"
        green = [c for c in candidates if c.get("risk") == "GREEN"]
        if not green: return [], "NO_GREEN_CANDIDATE"
        return green, "OK"

    def select_candidate(self, cycle):
        candidates, status = self.parse_dreamer_candidates(cycle)
        if status != "OK": return None, status
        return candidates[0]["slug"], "OK"

    def phase_builder(self, cycle):
        # v0.20.4: Support candidate_source from different cycle (e.g., cycle 22 evidence for cycle 25)
        candidate_source = self.state.get("candidate_source")
        if candidate_source:
            source_path = Path(candidate_source)
            if source_path.exists():
                has_evidence = True
                evidence_path = source_path
            else:
                has_evidence = False
        else:
            has_evidence, evidence_path = self.check_bound_evidence("DREAMER", cycle)
        if not has_evidence:
            print(f"  ⛔ Dreamer evidence missing")
            return False
        # v0.20: Use pre-selected candidate from state if available
        candidate = self.state.get("current_candidate")
        if not candidate:
            candidate, status = self.select_candidate(cycle)
            if status != "OK":
                print(f"  ⛔ Candidate selection: {status}")
                return False
        print(f"  🎯 Candidate: {candidate}")
        self.state["current_candidate"] = candidate
        self.save_state()
        profile = self.configured_profile("BUILDER", "builder")
        return self.phase_builder_with_profile(cycle, profile, 0)

    # ── v0.15: Merge with conflict gate ─────────────────────────────────

    def phase_merge(self, cycle, pr_url):
        default_branch = str(getattr(self.pack, "default_branch", "main"))
        # v0.16: mode safety gate — MERGE blocked?
        if self.is_action_blocked_by_mode("MERGE"):
            print(f"  ⛔ MODE_VIOLATION: MERGE blocked by mode={self.state.get('mode')}")
            self.state["status"] = "BLOCKED_MODE_VIOLATION"
            self.save_state()
            return False

        reviewer_complete, reviewer_reason = self.check_phase_complete("REVIEWER", cycle)
        if not reviewer_complete:
            print(f"  ⛔ Reviewer terminal/evidence gate failed: {reviewer_reason}")
            self.state["status"] = f"BLOCKED_REVIEWER_GATE:{reviewer_reason}"
            self.save_state()
            return False
        reviewer_verdict = self.bound_task_verdict("REVIEWER", cycle)
        if reviewer_verdict != "APPROVE_MERGE":
            print(f"  ⛔ Reviewer verdict does not authorize merge: {reviewer_verdict}")
            self.state["status"] = f"BLOCKED_REVIEWER_VERDICT:{reviewer_verdict or 'MISSING'}"
            self.save_state()
            return False

        # Check mergeable
        conflict_status, conflict_reason = self.detect_merge_conflict(pr_url)
        if conflict_status == "CONFLICT":
            print(f"  ⛔ Merge conflict: {conflict_reason}")
            self.state["status"] = "BLOCKED_MERGE_CONFLICT"
            self.save_state()
            return False
        elif conflict_status != "MERGEABLE":
            print(f"  ⚠️ Merge status unknown: {conflict_status}")
            self.state["status"] = f"BLOCKED_MERGE_{conflict_status}"
            self.save_state()
            return False

        # ── v0.24.2: Merge Gate Truth Hardening ─────────────────────
        # 1. Dirty tree check (unstaged changes only — committed PR changes are expected)
        ok_dirty, stdout_dirty, _ = self.run_cmd("git diff --name-only", timeout=30)
        if ok_dirty and stdout_dirty.strip():
            # Check if the dirty files are relevant to the PR
            pr_files = self.run_cmd(f"git diff --name-only origin/{default_branch}...HEAD", timeout=30)[1] if False else ""
            dirty_files = [l.strip() for l in stdout_dirty.strip().splitlines() if l.strip()]
            # If any test file is dirty, that taints the test result
            test_dirty = [f for f in dirty_files if f.startswith("tests/") or f.endswith("test") or f.startswith("test")]
            if test_dirty:
                print(f"  ⛔ Dirty test files detected: {test_dirty}")
                self.state["status"] = "BLOCKED_DIRTY_TREE"
                self.save_state()
                return False
            print(f"  ⚠️ Working tree dirty (non-test files): {dirty_files}")

        # 2. Checkout PR branch
        pr_number = pr_url.split("/")[-1]
        ok_co, _, _ = self.run_cmd(f"gh pr checkout {pr_number}", timeout=60)
        if not ok_co:
            print(f"  ⛔ Cannot checkout PR branch for testing")
            self.state["status"] = "BLOCKED_CANNOT_CHECKOUT_PR_BRANCH"
            self.save_state()
            return False

        # 3. Check test baseline
        # Use ProjectPack test_command if available, else fallback
        test_cmd = getattr(self.pack, "test_command", "pytest tests/ -q") if self.pack else "pytest tests/ -q"
        ok, stdout, stderr = self.run_cmd(test_cmd, timeout=120)
        if not ok:
            # Check if failures are pre-existing
            baseline = None
            baseline_file = self.baseline_file
            if baseline_file.exists():
                try:
                    baseline = json.loads(baseline_file.read_text())
                except:
                    pass
            if baseline and baseline.get("pre_existing_failures"):
                current_failures = re.findall(r'FAILED\s+(\S+)', stdout)
                pre_failures = set(baseline["pre_existing_failures"])
                new_failures = [f for f in current_failures if f not in pre_failures]
                if new_failures:
                    print(f"  ⛔ New test failures: {new_failures}")
                    self.state["status"] = "BLOCKED_NEW_TEST_FAILURES"
                    self.save_state()
                    return False
                else:
                    print(f"  ⚠️ Pre-existing failures only — allowing merge")
            else:
                print(f"  ⛔ Tests not green, no baseline")
                self.state["status"] = "BLOCKED_TESTS_NOT_GREEN"
                self.save_state()
                return False

        # No admin merge — standard squash merge
        pr_number = pr_url.split("/")[-1]
        ok, _, stderr = self.run_cmd(f"gh pr merge {pr_number} --squash", timeout=60)
        if not ok:
            print(f"  ❌ Merge failed: {stderr[:200]}")
            self.state["status"] = "BLOCKED_MERGE_FAILED"
            self.save_state()
            return False

        print(f"  ✅ PR #{pr_number} merged")
        self.state["pr_open"] = None
        self.save_state()
        self.run_cmd(f"git checkout {default_branch}", timeout=30)
        self.run_cmd(f"git pull --ff-only origin {default_branch}", timeout=30)
        return True

    # ── Reporter (unchanged) ────────────────────────────────────────────

    def phase_reporter(self, cycle):
        msg = self.build_reporter_message(cycle)
        print(msg)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rp = EVIDENCE_DIR / f"reporter/reporter-cycle-{cycle}-{date_str}.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(msg)
        self.save_phase_status("REPORTER", cycle, "COMPLETE")
        return True

    def reconcile_state(self):
        try:
            r = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", "20",
                              "--json", "number,url,mergeCommit"],
                             capture_output=True, text=True, timeout=15)
            merged = json.loads(r.stdout) if r.stdout.strip() else []
            print(f"  📊 Merged PRs: {[p['number'] for p in merged][:10]}")
        except Exception as e:
            print(f"  ⚠️ Reconcile: {e}")

    # ── v0.16: stop_after_phase guard + mode safety gate ────────────────

    def should_stop_after_phase(self, completed_phase: str) -> bool:
        """Return True if completed_phase matches the configured stop boundary."""
        return self.state.get("stop_after_phase") == completed_phase

    def is_action_blocked_by_mode(self, action: str) -> bool:
        """Return True if the current mode's policy blocks this action.

        Actions: 'BUILDER' (builder task creation), 'PR_CREATE', 'MERGE'.
        """
        mode = self.state.get("mode")
        if not mode:
            return False
        policy = RESTRICTED_MODES.get(mode)
        if not policy:
            return False
        return action in policy.get("blocked_actions", set())

    def is_phase_blocked_by_mode(self, target_phase: str) -> bool:
        """Return True if the current mode forbids transitioning to target_phase."""
        mode = self.state.get("mode")
        if not mode:
            return False
        policy = RESTRICTED_MODES.get(mode)
        if not policy:
            return False
        return target_phase not in policy.get("allowed_phases", set())

    def enter_stopped_state(self, completed_phase: str):
        """Transition to the STOPPED_AFTER_<PHASE> terminal state.

        - Sets phase/status so no further tasks are dispatched
        - Preserves task_bindings and evidence
        - Writes a proof-complete status file
        """
        stop_label = f"STOPPED_AFTER_{completed_phase}"
        self.state["phase"] = stop_label
        self.state["status"] = "PROOF_COMPLETE"
        self.save_state()
        self.save_phase_status(completed_phase, self.state["cycle"], "PROOF_COMPLETE",
                               {"stop_after_phase": completed_phase,
                                "mode": self.state.get("mode", "none")})
        print(f"  🛑 stop_after_phase={completed_phase} → {stop_label} / PROOF_COMPLETE")

    # ── Main run loop ───────────────────────────────────────────────────

    def run(
        self,
        *,
        autonomous=True,
        phase_limit=None,
        reconcile=True,
        before_phase_side_effect=None,
    ) -> BuildroomRunResult:
        if not self.acquire_lock():
            print("⏳ Another instance is running")
            return BuildroomRunResult.LOCK_UNAVAILABLE
        try:
            if reconcile:
                self.reconcile_state()
            cycle = self.state["cycle"]
            phase = self.state["phase"]
            status = self.state["status"]
            print(f"=== Buildroom v0.20 Cycle {cycle} Phase {phase} ===")
            print(f"Mission: {MISSION}")

            if phase_limit is not None and phase != phase_limit:
                print("⛔ PROJECTPACK_NOT_READY: requested manual phase does not match current state")
                return BuildroomRunResult.STATE_MISMATCH

            # v0.16: terminal stop state — no further action
            if phase.startswith("STOPPED_AFTER_"):
                print(f"🛑 Proof complete — phase={phase}, status={status}")
                print(f"   stop_after_phase={self.state.get('stop_after_phase')}")
                return BuildroomRunResult.PHASE_ALREADY_TERMINAL

            if self.pack and not self.require_pack_phase(phase, autonomous=autonomous):
                return BuildroomRunResult.PROJECTPACK_BLOCKED

            if status == "HOLD_FOR_BOSS":
                print(f"⏸️ HOLD_FOR_BOSS: {self.state.get('blocker', 'manual review required')}")
                return BuildroomRunResult.PROJECTPACK_BLOCKED

            # v0.16: mode safety gate — BUILDER forbidden in restricted modes
            if phase == "BUILDER" and self.is_phase_blocked_by_mode("BUILDER"):
                print(f"⛔ MODE_VIOLATION: phase=BUILDER blocked by mode={self.state.get('mode')}")
                self.state["status"] = "BLOCKED_MODE_VIOLATION"
                self.save_state()
                return BuildroomRunResult.PROJECTPACK_BLOCKED

            # v0.20: MERGE always blocked in BUILDER_PR_REVIEWER_ONLY mode
            if phase == "MERGE" and self.is_action_blocked_by_mode("MERGE"):
                print(f"⛔ MODE_VIOLATION: phase=MERGE blocked by mode={self.state.get('mode')}")
                self.state["status"] = "BLOCKED_MODE_VIOLATION"
                self.save_state()
                return BuildroomRunResult.PROJECTPACK_BLOCKED

            if phase not in ("REVIEWER", "MERGE", "REPORTER"):
                safety = self.safety_checks()
                print(f"Safety: {safety}")
                workers_ok = safety.get(
                    "no_conflicting_active_workers", safety.get("active_builders", False)
                )
                if not all([safety["main_green"], safety["open_prs"],
                           workers_ok, safety["no_revert_policy"]]):
                    canonical_values = {
                        "main_green": safety["main_green"],
                        "open_prs": safety["open_prs"],
                        "no_conflicting_active_workers": workers_ok,
                        "no_revert_policy": safety["no_revert_policy"],
                    }
                    failed = [key for key, value in canonical_values.items() if not value]
                    print(f"⛔ Safety gates: {', '.join(failed)}")
                    observation = self.record_no_progress(
                        phase, f"SAFETY_GATES:{','.join(failed)}"
                    )
                    if observation.terminal_hold:
                        print("⏸️ HOLD_FOR_BOSS: REPEATED_NO_PROGRESS")
                    return BuildroomRunResult.PROJECTPACK_BLOCKED

            result = BuildroomRunResult.DISPATCH_BLOCKED
            if before_phase_side_effect is not None and status not in ("NEXT_CYCLE", "NEXT_PHASE"):
                return BuildroomRunResult.DISPATCH_BLOCKED

            def authorize_side_effect():
                if before_phase_side_effect is None:
                    return None
                return before_phase_side_effect()

            if phase == "RESEARCHER":
                reason = ""
                if status == "NEXT_CYCLE" or status == "NEXT_PHASE":
                    # v0.19: strict mode check before dispatch
                    directive = self.load_cycle_directive(cycle)
                    body = self.build_researcher_body(cycle, directive)
                    if body == "__BLOCKED_MISSING_DIRECTIVE__":
                        self.state["status"] = "BLOCKED_MISSING_DIRECTIVE"
                        self.save_state()
                        print(f"  ⛔ BLOCKED_MISSING_DIRECTIVE: directive_required=true but no directive available")
                        return BuildroomRunResult.DISPATCH_BLOCKED
                    authorization_result = authorize_side_effect()
                    if authorization_result is not None:
                        return authorization_result
                    ok = self.phase_researcher_with_body(cycle, directive, body)
                    if not ok:
                        self.state["status"] = "BLOCKED_RESEARCHER_DISPATCH_FAILED"
                        self.save_state()
                        print(f"  ⛔ BLOCKED_RESEARCHER_DISPATCH_FAILED: kanban dispatch returned no task")
                        return BuildroomRunResult.DISPATCH_FAILED
                    self.state["status"] = "WAITING"
                    self.save_state()
                    result = BuildroomRunResult.PHASE_EXECUTED
                elif status in ("WAITING", "RETRYING_WITH_FALLBACK"):
                    complete, reason = self.check_phase_complete("RESEARCHER", cycle)
                    if complete:
                        # v0.18: directive compliance gate
                        if self.state.get("compliance_required"):
                            has_ev, ev_path = self.check_bound_evidence("RESEARCHER", cycle)
                            if has_ev:
                                compliant, creason, chits = self.validate_researcher_directive_compliance(ev_path)
                                print(f"  📋 Researcher compliance: {creason}")
                                print(f"     Epic hits: {chits}")
                                if not compliant:
                                    cr = self.state.setdefault("compliance_retries", {}).setdefault("RESEARCHER", 0)
                                    if cr < MAX_COMPLIANCE_RETRIES:
                                        self.state["compliance_retries"]["RESEARCHER"] = cr + 1
                                        self.state["status"] = "RETRYING_COMPLIANCE"
                                        self.save_state()
                                        print(f"  🔄 Compliance retry {cr+1}/{MAX_COMPLIANCE_RETRIES} — re-dispatching with enforced prompt")
                                        if not self._dispatch_compliance_retry("RESEARCHER", cycle, creason):
                                            return BuildroomRunResult.DISPATCH_FAILED
                                        return BuildroomRunResult.PHASE_EXECUTED
                                    else:
                                        self.state["status"] = "HOLD_FOR_BOSS"
                                        self.save_state()
                                        print(f"  ⏸️ Max compliance retries — HOLD_FOR_BOSS: {creason}")
                                        return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # v0.16: stop_after_phase guard
                        if self.should_stop_after_phase("RESEARCHER"):
                            self.enter_stopped_state("RESEARCHER")
                            return BuildroomRunResult.PHASE_EXECUTED
                        print(f"✅ RESEARCHER → DREAMER")
                        if not self.transition_to_phase("DREAMER"):
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        result = BuildroomRunResult.PHASE_EXECUTED
                elif status == "RETRYING_COMPLIANCE":
                    # v0.19: compliance retry — check again after worker completes
                    complete2, reason2 = self.check_phase_complete("RESEARCHER", cycle)
                    if complete2:
                        has_ev, ev_path = self.check_bound_evidence("RESEARCHER", cycle)
                        if has_ev:
                            compliant, creason, chits = self.validate_researcher_directive_compliance(ev_path)
                            print(f"  📋 Researcher compliance (retry): {creason}")
                            if not compliant:
                                self.state["status"] = "HOLD_FOR_BOSS"
                                self.save_state()
                                print(f"  ⏸️ Compliance still failing — HOLD_FOR_BOSS: {creason}")
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # Compliance passed — transition deterministically inline
                        # v0.19: no manual WAITING reset needed; we transition directly
                        print(f"✅ Researcher compliance retry passed → transitioning")
                        if self.should_stop_after_phase("RESEARCHER"):
                            self.enter_stopped_state("RESEARCHER")
                            return BuildroomRunResult.PHASE_EXECUTED
                        print(f"✅ RESEARCHER → DREAMER")
                        if not self.transition_to_phase("DREAMER"):
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        return BuildroomRunResult.PHASE_EXECUTED
                    print(f"  ⏳ Researcher compliance retry ({reason2})")
                else:
                    terminal_result = self.handle_terminal_task_failure("RESEARCHER", cycle, reason)
                    if terminal_result is not None:
                        return terminal_result
                    print(f"⏳ Researcher ({reason})")
                    if reason == "TASK_DONE_BUT_NO_EVIDENCE":
                        observation = self.record_no_progress("RESEARCHER", reason)
                        if observation.terminal_hold:
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        ok, rreason = self.maybe_retry_phase("RESEARCHER", cycle)
                        if not ok and rreason.startswith("BLOCKED"):
                            self.state["status"] = rreason; self.save_state()
                            result = BuildroomRunResult.PROJECTPACK_BLOCKED
                        elif ok:
                            result = BuildroomRunResult.PHASE_EXECUTED

            elif phase == "DREAMER":
                reason = ""
                if status == "NEXT_PHASE":
                    # v0.19: strict mode check before dispatch
                    has_evidence, ep = self.check_bound_evidence("RESEARCHER", cycle)
                    directive = self.load_cycle_directive(cycle)
                    body = self.build_dreamer_body(cycle, str(ep) if ep else "", directive)
                    if body == "__BLOCKED_MISSING_DIRECTIVE__":
                        self.state["status"] = "BLOCKED_MISSING_DIRECTIVE"
                        self.save_state()
                        print(f"  ⛔ BLOCKED_MISSING_DIRECTIVE: directive_required=true but no directive available")
                        return BuildroomRunResult.DISPATCH_BLOCKED
                    authorization_result = authorize_side_effect()
                    if authorization_result is not None:
                        return authorization_result
                    ok = self.phase_dreamer_with_body(cycle, str(ep) if ep else "", directive, body)
                    if not ok:
                        self.state["status"] = "BLOCKED_DREAMER_DISPATCH_FAILED"
                        self.save_state()
                        print(f"  ⛔ BLOCKED_DREAMER_DISPATCH_FAILED: kanban dispatch returned no task")
                        return BuildroomRunResult.DISPATCH_FAILED
                    self.state["status"] = "WAITING"
                    self.save_state()
                    result = BuildroomRunResult.PHASE_EXECUTED
                elif status in ("WAITING", "RETRYING_WITH_FALLBACK"):
                    complete, reason = self.check_phase_complete("DREAMER", cycle)
                    if complete:
                        # v0.18: directive compliance gate
                        if self.state.get("compliance_required"):
                            has_ev, ev_path = self.check_bound_evidence("DREAMER", cycle)
                            if has_ev:
                                compliant, creason, cdetails = self.validate_dreamer_directive_compliance(ev_path)
                                print(f"  📋 Dreamer compliance: {creason}")
                                print(f"     Details: {cdetails}")
                                if not compliant:
                                    # v0.25.1: YAML parse errors get targeted retry
                                    if isinstance(cdetails, dict) and cdetails.get("error_type") == "YAML_PARSE_ERROR":
                                        cr = self.state.setdefault("compliance_retries", {}).setdefault("DREAMER_YAML_PARSE", 0)
                                        if cr < MAX_COMPLIANCE_RETRIES:
                                            self.state["compliance_retries"]["DREAMER_YAML_PARSE"] = cr + 1
                                            self.state["status"] = "RETRYING_DREAMER_YAML_PARSE"
                                            self.save_state()
                                            print(f"  🔄 YAML parse retry {cr+1}/{MAX_COMPLIANCE_RETRIES}: {cdetails.get('snippet','')[:80]}")
                                            if not self._dispatch_compliance_retry(
                                                "DREAMER",
                                                cycle,
                                                f"YAML_PARSE_ERROR: {creason}\n\nGUIDANCE: {cdetails.get('guidance','Quote all free-text scalars.')}",
                                            ):
                                                return BuildroomRunResult.DISPATCH_FAILED
                                            return BuildroomRunResult.PHASE_EXECUTED
                                        else:
                                            self.state["status"] = "BLOCKED_DREAMER_YAML_PARSE"
                                            self.save_state()
                                            print(f"  ⛔ Max YAML parse retries — BLOCKED_DREAMER_YAML_PARSE")
                                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                                    cr = self.state.setdefault("compliance_retries", {}).setdefault("DREAMER", 0)
                                    if cr < MAX_COMPLIANCE_RETRIES:
                                        self.state["compliance_retries"]["DREAMER"] = cr + 1
                                        self.state["status"] = "RETRYING_COMPLIANCE"
                                        self.save_state()
                                        print(f"  🔄 Compliance retry {cr+1}/{MAX_COMPLIANCE_RETRIES}")
                                        if not self._dispatch_compliance_retry("DREAMER", cycle, creason):
                                            return BuildroomRunResult.DISPATCH_FAILED
                                        return BuildroomRunResult.PHASE_EXECUTED
                                    else:
                                        self.state["status"] = "HOLD_FOR_BOSS"
                                        self.save_state()
                                        print(f"  ⏸️ Max compliance retries — HOLD_FOR_BOSS")
                                        return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # v0.16: stop_after_phase guard
                        if self.should_stop_after_phase("DREAMER"):
                            self.enter_stopped_state("DREAMER")
                            return BuildroomRunResult.PHASE_EXECUTED
                        # v0.16: mode safety gate — BUILDER forbidden?
                        if self.is_phase_blocked_by_mode("BUILDER"):
                            print(f"⛔ MODE_VIOLATION: BUILDER blocked by mode={self.state.get('mode')}")
                            self.state["status"] = "BLOCKED_MODE_VIOLATION"
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        print(f"✅ DREAMER → BUILDER")
                        if not self.transition_to_phase("BUILDER"):
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        result = BuildroomRunResult.PHASE_EXECUTED
                    else:
                        terminal_result = self.handle_terminal_task_failure("DREAMER", cycle, reason)
                        if terminal_result is not None:
                            return terminal_result
                        print(f"⏳ Dreamer ({reason})")
                        if reason == "TASK_DONE_BUT_NO_EVIDENCE":
                            observation = self.record_no_progress("DREAMER", reason)
                            if observation.terminal_hold:
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                elif status == "RETRYING_COMPLIANCE":
                    complete2, reason2 = self.check_phase_complete("DREAMER", cycle)
                    if complete2:
                        has_ev, ev_path = self.check_bound_evidence("DREAMER", cycle)
                        if has_ev:
                            compliant, creason, cdetails = self.validate_dreamer_directive_compliance(ev_path)
                            print(f"  📋 Dreamer compliance (retry): {creason}")
                            if not compliant:
                                self.state["status"] = "HOLD_FOR_BOSS"
                                self.save_state()
                                print(f"  ⏸️ Compliance still failing — HOLD_FOR_BOSS")
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # Compliance passed — transition deterministically inline
                        # v0.19: no manual WAITING reset needed; we transition directly
                        print(f"✅ Dreamer compliance retry passed → transitioning")
                        # v0.16: stop_after_phase guard
                        if self.should_stop_after_phase("DREAMER"):
                            self.enter_stopped_state("DREAMER")
                            return BuildroomRunResult.PHASE_EXECUTED
                        # v0.16: mode safety gate — BUILDER forbidden?
                        if self.is_phase_blocked_by_mode("BUILDER"):
                            print(f"⛔ MODE_VIOLATION: BUILDER blocked by mode={self.state.get('mode')}")
                            self.state["status"] = "BLOCKED_MODE_VIOLATION"
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        print(f"✅ DREAMER → BUILDER")
                        if not self.transition_to_phase("BUILDER"):
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        return BuildroomRunResult.PHASE_EXECUTED
                    print(f"  ⏳ Dreamer compliance retry ({reason2})")
                else:
                    terminal_result = self.handle_terminal_task_failure("DREAMER", cycle, reason)
                    if terminal_result is not None:
                        return terminal_result
                    if status.startswith("BLOCKED"):
                        print(f"⛔ Dreamer BLOCKED: {status}")
                        return BuildroomRunResult.PROJECTPACK_BLOCKED
                    print(f"⏳ Dreamer ({reason})")
                    if reason == "TASK_DONE_BUT_NO_EVIDENCE":
                        observation = self.record_no_progress("DREAMER", reason)
                        if observation.terminal_hold:
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        ok, rreason = self.maybe_retry_phase("DREAMER", cycle)
                        if not ok and rreason.startswith("BLOCKED"):
                            self.state["status"] = rreason; self.save_state()
                            result = BuildroomRunResult.PROJECTPACK_BLOCKED
                        elif ok:
                            result = BuildroomRunResult.PHASE_EXECUTED

            elif phase == "BUILDER":
                if status == "NEXT_PHASE":
                    authorization_result = authorize_side_effect()
                    if authorization_result is not None:
                        return authorization_result
                    ok = self.phase_builder(cycle)
                    if not ok:
                        self.state["status"] = "BLOCKED_BUILDER_DISPATCH_FAILED"
                        self.save_state()
                        print(f"  ⛔ BLOCKED_BUILDER_DISPATCH_FAILED: phase_builder returned False")
                        return BuildroomRunResult.DISPATCH_FAILED
                    self.state["status"] = "WAITING"
                    self.save_state()
                    result = BuildroomRunResult.PHASE_EXECUTED
                elif status in ("WAITING", "RETRYING_WITH_FALLBACK"):
                    complete, reason = self.check_phase_complete("BUILDER", cycle)
                    if complete:
                        # v0.20: Builder evidence contract check
                        bev_ok, bev_path = self.check_builder_evidence(cycle)
                        if not bev_ok:
                            print(f"❌ BUILDER_EVIDENCE_MISSING: no builder evidence found")
                            self.state["status"] = "BLOCKED_BUILDER_EVIDENCE_MISSING"
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # v0.20: Branch check
                        branch = self.state.get("builder_branch")
                        if not branch:
                            print(f"❌ BLOCKED_BUILDER_BRANCH_MISSING: no branch recorded")
                            self.state["status"] = "BLOCKED_BUILDER_BRANCH_MISSING"
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        # v0.15: Auto push + PR create
                        candidate = self.state.get("current_candidate")
                        pr_url, pr_err = self.orchestrator_push_and_create_pr(candidate, cycle)
                        if pr_url:
                            print(f"✅ Builder → REVIEWER (PR created)")
                            self.state["pr_open"] = pr_url
                            self.save_state()
                            result = BuildroomRunResult.PHASE_EXECUTED
                        else:
                            print(f"❌ PR orchestration failed: {pr_err}")
                            self.state["status"] = "BLOCKED_PR_CREATE_FAILED"
                            self.save_state()
                            return BuildroomRunResult.DISPATCH_FAILED
                    else:
                        terminal_result = self.handle_terminal_task_failure("BUILDER", cycle, reason)
                        if terminal_result is not None:
                            return terminal_result
                        print(f"⏳ Builder ({reason})")
                        if reason == "TASK_DONE_BUT_NO_EVIDENCE":
                            observation = self.record_no_progress("BUILDER", reason)
                            if observation.terminal_hold:
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                            ok, rreason = self.maybe_retry_phase("BUILDER", cycle)
                            if not ok and rreason.startswith("BLOCKED"):
                                self.state["status"] = rreason; self.save_state()
                                result = BuildroomRunResult.PROJECTPACK_BLOCKED
                            elif ok:
                                result = BuildroomRunResult.PHASE_EXECUTED

            elif phase == "REVIEWER":
                if status == "NEXT_PHASE":
                    pr_url = self.state.get("pr_open")
                    if pr_url:
                        profile = self.configured_profile("REVIEWER", "reviewer")
                        authorization_result = authorize_side_effect()
                        if authorization_result is not None:
                            return authorization_result
                        ok = self.phase_reviewer_with_profile(cycle, pr_url, profile, 0)
                        if ok:
                            self.state["status"] = "WAITING"
                            self.save_state()
                            result = BuildroomRunResult.PHASE_EXECUTED
                        else:
                            self.state["status"] = "BLOCKED_REVIEWER_DISPATCH_FAILED"
                            self.save_state()
                            return BuildroomRunResult.DISPATCH_FAILED
                    else:
                        print(f"❌ REVIEWER: no PR URL in state")
                        self.state["status"] = "BLOCKED_REVIEWER_NO_PR"
                        self.save_state()
                        return BuildroomRunResult.DISPATCH_BLOCKED
                elif status in ("WAITING", "RETRYING_WITH_FALLBACK"):
                    complete, reason = self.check_phase_complete("REVIEWER", cycle)
                    if complete:
                        # v0.20: Reviewer evidence check
                        rev_ok, rev_path = self.check_reviewer_evidence(cycle)
                        if not rev_ok:
                            print(f"❌ REVIEWER_EVIDENCE_MISSING: no reviewer evidence found")
                            self.state["status"] = "BLOCKED_REVIEWER_EVIDENCE_MISSING"
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        verdict = self.bound_task_verdict("REVIEWER", cycle)
                        if verdict != "APPROVE_MERGE":
                            self.state["status"] = "HOLD_FOR_BOSS"
                            self.state["blocker"] = f"REVIEWER_VERDICT:{verdict or 'MISSING'}"
                            self.state["root_blocker"] = self.state["blocker"]
                            self.save_state()
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        self.state.pop("no_progress", None)
                        # v0.20: stop_after_phase guard for REVIEWER
                        if self.should_stop_after_phase("REVIEWER"):
                            self.enter_stopped_state("REVIEWER")
                            return BuildroomRunResult.PHASE_EXECUTED
                        print(f"✅ REVIEWER → MERGE")
                        if not self.transition_to_phase("MERGE"):
                            return BuildroomRunResult.PROJECTPACK_BLOCKED
                        result = BuildroomRunResult.PHASE_EXECUTED
                    else:
                        terminal_result = self.handle_terminal_task_failure("REVIEWER", cycle, reason)
                        if terminal_result is not None:
                            return terminal_result
                        print(f"⏳ Reviewer ({reason})")
                        if reason == "TASK_DONE_BUT_NO_EVIDENCE":
                            observation = self.record_no_progress("REVIEWER", reason)
                            if observation.terminal_hold:
                                print("⏸️ HOLD_FOR_BOSS: REPEATED_NO_PROGRESS")
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                            ok, rreason = self.maybe_retry_phase("REVIEWER", cycle)
                            if not ok and rreason.startswith("BLOCKED"):
                                self.state["status"] = rreason; self.save_state()
                                result = BuildroomRunResult.PROJECTPACK_BLOCKED
                            elif ok:
                                result = BuildroomRunResult.PHASE_EXECUTED

            elif phase == "MERGE":
                if status == "NEXT_PHASE":
                    pr_url = self.state.get("pr_open")
                    if pr_url:
                        authorization_result = authorize_side_effect()
                        if authorization_result is not None:
                            return authorization_result
                        ok = self.phase_merge(cycle, pr_url)
                        if ok:
                            # v0.21: Check stop_after_phase for MERGE
                            if self.should_stop_after_phase("MERGE"):
                                self.enter_stopped_state("MERGE")
                                print(f"🛑 stop_after_phase=MERGE → STOPPED_AFTER_MERGE / PROOF_COMPLETE")
                                return BuildroomRunResult.PHASE_EXECUTED
                            if not self.transition_to_phase("REPORTER"):
                                return BuildroomRunResult.PROJECTPACK_BLOCKED
                            result = BuildroomRunResult.PHASE_EXECUTED
                        else:
                            return BuildroomRunResult.DISPATCH_FAILED

            elif phase == "REPORTER":
                if status == "NEXT_PHASE":
                    authorization_result = authorize_side_effect()
                    if authorization_result is not None:
                        return authorization_result
                    self.phase_reporter(cycle)
                    result = BuildroomRunResult.PHASE_EXECUTED
                    # v0.21: Check stop_after_phase for REPORTER
                    if self.should_stop_after_phase("REPORTER"):
                        self.enter_stopped_state("REPORTER")
                        print(f"🛑 stop_after_phase=REPORTER → STOPPED_AFTER_REPORTER / PROOF_COMPLETE")
                        return BuildroomRunResult.PHASE_EXECUTED
                    if not self.require_pack_phase("RESEARCHER"):
                        return BuildroomRunResult.PROJECTPACK_BLOCKED
                    self.state["cycle"] = cycle + 1; self.state["phase"] = "RESEARCHER"
                    self.state["status"] = "NEXT_CYCLE"
                    self.state["current_candidate"] = None; self.state["pr_open"] = None
                    active_bindings = self.state.get("task_bindings", {})
                    if isinstance(active_bindings, dict):
                        history = self.state.setdefault("task_binding_history", [])
                        for raw in active_bindings.values():
                            if isinstance(raw, dict):
                                history.append({**raw, "disposition": "CYCLE_COMPLETED"})
                    self.state["task_bindings"] = {}
                    self.state.pop("task_ids", None)
                    self.state.pop("task_boards", None)
                    self.state["attempts"] = {}
                    self.save_state()
                    print(f"✅ Cycle {cycle} complete → {cycle+1}")

            elif phase == "BLOCKED_RUNTIME_FIX":
                print(f"⛔ Blocked: Runtime fix required")
                result = BuildroomRunResult.PROJECTPACK_BLOCKED

            elif status and status.startswith("BLOCKED"):
                print(f"⛔ Cycle blocked: {status}")
                result = BuildroomRunResult.PROJECTPACK_BLOCKED

            elif status == "HOLD_FOR_BOSS":
                print(f"⏸️ HOLD_FOR_BOSS: manual review required for cycle {cycle}")
                print(f"   Check evidence and compliance status")
                result = BuildroomRunResult.PROJECTPACK_BLOCKED

            elif status == "BLOCKED_DIRECTIVE_NONCOMPLIANCE":
                print(f"⛔ BLOCKED_DIRECTIVE_NONCOMPLIANCE: evidence does not meet directive requirements")
                print(f"   Cycle {cycle} — manual review needed")
                result = BuildroomRunResult.PROJECTPACK_BLOCKED

            return result
        except Exception as exc:
            print(f"⛔ INTERNAL_ERROR: {type(exc).__name__}")
            return BuildroomRunResult.INTERNAL_ERROR

        finally:
            self.release_lock()


if __name__ == "__main__":
    # v0.23: Support --project flag for repo-agnostic project packs
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Buildroom Orchestrator v0.23")
    parser.add_argument("--project", "-p", help="Project name or path to project pack YAML")
    parser.add_argument("--dry-run", action="store_true", help="Validate project pack, don't run")
    args = parser.parse_args()

    pack = None
    if args.project and HAS_PROJECT_PACK:
        pack = resolve_project(args.project)
        if args.dry_run:
            print(f"Project: {pack.project_name}")
            print(f"  Repo: {pack.repo_path}")
            print(f"  Evidence: {pack.evidence_dir}")
            print(f"  State: {pack.state_file}")
            sys.exit(0)

    orchestrator = BuildroomOrchestrator(pack)
    orchestrator.run()
