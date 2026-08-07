"""
Worktree Safety Sentinel — Read-only inspection of agent worktrees.

Core principle: Active agent worktrees are agent-owned.
Captain may only inspect read-only. Mutating operations require
explicit permission or must run in isolated checkouts.

Classification: CAPTAIN_CAUSED vs AGENT_WIP vs UNKNOWN contamination.
"""

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict


class ContaminationClass(str, Enum):
    """Who caused the worktree state."""
    CLEAN = "CLEAN"
    CAPTAIN_CAUSED = "CAPTAIN_CAUSED"
    AGENT_WIP = "AGENT_WIP"
    UNKNOWN = "UNKNOWN"


class OperationRisk(str, Enum):
    """Risk level of an operation."""
    READ_ONLY = "READ_ONLY"
    MUTATING = "MUTATING"
    DESTRUCTIVE = "DESTRUCTIVE"


# Operations classified by risk
READ_ONLY_OPERATIONS = {
    "git status", "git diff --name-status", "git diff --stat",
    "git log", "cat", "read", "ls", "find", "head", "tail",
    "grep", "rg", "wc", "file", "stat",
}

MUTATING_OPERATIONS = {
    "pytest", "sonar", "npm install", "pip install",
    "format", "black", "ruff", "prettier",
    "mypy", "pylint", "flake8",
    "codegen", "generate", "build", "compile",
    "git add", "git stash", "git restore", "git clean",
    "git checkout", "git reset", "git commit",
    "sed -i", "awk -i", "python script",
}

DESTRUCTIVE_OPERATIONS = {
    "rm", "git clean -fd", "git reset --hard",
    "prune", "delete", "truncate",
}


@dataclass
class WorktreeFile:
    """A single file in the worktree state."""
    path: str
    status: str  # e.g. "M", "A ", "??", " D"
    classification: ContaminationClass = ContaminationClass.UNKNOWN


@dataclass
class WorktreeReport:
    """Full read-only inspection of a worktree."""
    agent_id: str
    worktree_path: str
    exists: bool = False
    is_git_repo: bool = False
    current_branch: str = ""
    head_sha: str = ""
    dirty_files: List[WorktreeFile] = field(default_factory=list)
    untracked_files: List[WorktreeFile] = field(default_factory=list)
    total_dirty: int = 0
    total_untracked: int = 0
    overall_classification: ContaminationClass = ContaminationClass.CLEAN
    errors: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.total_dirty == 0 and self.total_untracked == 0


class WorktreeSentinel:
    """
    Read-only worktree inspector with safety checks.

    Uses the Agent Registry to know which agents are active.
    Active agents' worktrees are protected from mutating operations.
    """

    def __init__(self, control_dir: Optional[Path] = None):
        from conduvera.control.registry import AgentRegistry
        self._registry = AgentRegistry(control_dir=control_dir)

    def _is_agent_active(self, agent_id: str) -> bool:
        """Check if an agent is currently active."""
        from conduvera.control.registry import AgentStatus
        record = self._registry.get(agent_id)
        if record is None:
            return False
        return record.status in (AgentStatus.ACTIVE, AgentStatus.BOOTING, AgentStatus.READY)

    def inspect(self, agent_id: str) -> WorktreeReport:
        """Read-only inspection of an agent's worktree."""
        record = self._registry.get(agent_id)
        worktree = record.worktree if record else ""
        wt = Path(worktree) if worktree else None

        report = WorktreeReport(
            agent_id=agent_id,
            worktree_path=worktree,
            exists=wt is not None and wt.exists(),
        )

        if not report.exists:
            report.errors.append(f"Worktree does not exist: {worktree}")
            return report

        # Check if it's a git repo
        git_dir = wt / ".git"
        report.is_git_repo = git_dir.exists()
        if not report.is_git_repo:
            report.errors.append("Not a git repository")
            return report

        # Get branch and HEAD
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(wt), capture_output=True, text=True, timeout=10,
            )
            report.current_branch = result.stdout.strip()
        except Exception as e:
            report.errors.append(f"Cannot get branch: {e}")

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(wt), capture_output=True, text=True, timeout=10,
            )
            report.head_sha = result.stdout.strip()[:12]
        except Exception:
            pass

        # Get dirty/untracked files
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(wt), capture_output=True, text=True, timeout=10,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]

            for line in lines:
                status = line[:2].strip()
                filepath = line[3:].strip()
                classification = self._classify_file(filepath, status)

                wf = WorktreeFile(
                    path=filepath,
                    status=status,
                    classification=classification,
                )

                if status == "??":
                    report.untracked_files.append(wf)
                else:
                    report.dirty_files.append(wf)

            report.total_dirty = len(report.dirty_files)
            report.total_untracked = len(report.untracked_files)

        except Exception as e:
            report.errors.append(f"Cannot inspect files: {e}")

        # Overall classification
        if report.is_clean:
            report.overall_classification = ContaminationClass.CLEAN
        else:
            classes = {f.classification for f in report.dirty_files + report.untracked_files}
            if ContaminationClass.CAPTAIN_CAUSED in classes:
                report.overall_classification = ContaminationClass.CAPTAIN_CAUSED
            elif ContaminationClass.AGENT_WIP in classes:
                report.overall_classification = ContaminationClass.AGENT_WIP
            else:
                report.overall_classification = ContaminationClass.UNKNOWN

        return report

    def can_mutate(self, agent_id: str, operation: str) -> bool:
        """Check if a mutating operation is allowed on an agent's worktree."""
        op_lower = operation.lower().strip()

        # Check if operation is read-only — always allowed
        for ro_op in READ_ONLY_OPERATIONS:
            if op_lower.startswith(ro_op.lower()):
                return True

        # Check if operation is destructive — never auto-allowed
        for d_op in DESTRUCTIVE_OPERATIONS:
            if op_lower.startswith(d_op.lower()):
                return False

        # Mutating operations: allowed only if agent is NOT active
        return not self._is_agent_active(agent_id)

    def _classify_file(self, filepath: str, status: str) -> ContaminationClass:
        """Classify who likely caused this file state."""
        # Captain artifacts
        captain_patterns = [
            ".captain-", "captain-", ".agent-state/",
            "local-gate-", "sonar-", "test-results-",
        ]
        for pattern in captain_patterns:
            if pattern in filepath:
                return ContaminationClass.CAPTAIN_CAUSED

        # Agent WIP indicators
        agent_patterns = [
            "TODO", "WIP", ".tmp", ".bak",
            "scratch", "debug", "test_debug",
        ]
        for pattern in agent_patterns:
            if pattern.lower() in filepath.lower():
                return ContaminationClass.AGENT_WIP

        # Default: if it's tracked and modified, it's agent WIP
        if status not in ("??",):
            return ContaminationClass.AGENT_WIP

        return ContaminationClass.UNKNOWN
