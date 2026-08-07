"""
Gate Runner — Deterministic gate enforcement for CuraOps-Control.

Runs gates based on change-class profiles. No agent may declare READY
without passing all required gates for its profile.

Gate profiles are loaded from .conduvera/control/policies/gates.yaml.
Skipped gates are NEVER treated as PASS.

This module does NOT implement gate logic — it orchestrates existing
scripts/tools and collects results.
"""

import subprocess
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any


class GateStatus(str, Enum):
    """Result of a single gate check."""
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"       # Explicitly skipped (counts as NOT pass)
    ERROR = "error"           # Gate script crashed
    NOT_RUN = "not_run"       # Not yet executed


@dataclass
class GateResult:
    """Result of running a single gate."""
    gate_name: str
    status: GateStatus
    message: str = ""
    detail: dict = field(default_factory=dict)
    duration_ms: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "message": self.message,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class GateProfile:
    """A named set of gate requirements."""
    name: str
    required: List[str]       # Gate names that MUST pass
    not_required: List[str]   # Gates that are explicitly not required for this profile
    description: str = ""

    @classmethod
    def from_yaml_dict(cls, name: str, data: dict) -> "GateProfile":
        return cls(
            name=name,
            required=data.get("required", []),
            not_required=data.get("not_required", []),
            description=data.get("description", ""),
        )


@dataclass
class GateRunResult:
    """Result of running all gates for an agent."""
    agent_id: str
    profile_name: str
    gates: List[GateResult] = field(default_factory=list)
    overall_pass: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def failed_gates(self) -> List[GateResult]:
        return [g for g in self.gates if not g.passed]

    @property
    def passed_gates(self) -> List[GateResult]:
        return [g for g in self.gates if g.passed]

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "profile_name": self.profile_name,
            "gates": [g.to_dict() for g in self.gates],
            "overall_pass": self.overall_pass,
            "timestamp": self.timestamp,
        }


# ── Gate Implementations ──────────────────────────────────────────
# Each gate is a callable that takes agent info and returns GateResult.
# Gates call existing scripts/tools — they do NOT implement logic.

class BaseGate:
    """Base class for gate implementations."""
    name: str = "base"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        raise NotImplementedError


class DirtyWorktreeGate(BaseGate):
    """Check worktree is not dirty or has untracked files."""
    name = "dirty_worktree"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        if not worktree:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message="No worktree path provided",
            )
        wt = Path(worktree)
        if not wt.exists():
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=f"Worktree does not exist: {worktree}",
            )
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(wt),
                capture_output=True, text=True, timeout=30,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            if lines:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    message=f"Worktree has {len(lines)} dirty/untracked files",
                    detail={"files": lines[:20]},
                )
            return GateResult(
                gate_name=self.name,
                status=GateStatus.PASS,
                message="Worktree is clean",
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=str(e),
            )


class ScopeCheckGate(BaseGate):
    """Verify agent only changed files within its declared scope."""
    name = "scope_check"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        scope_files = agent_record.get("scope_files", [])
        if not scope_files:
            # No scope restriction = pass
            return GateResult(
                gate_name=self.name,
                status=GateStatus.PASS,
                message="No scope restriction defined",
            )
        if not worktree:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message="No worktree path provided",
            )
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(worktree),
                capture_output=True, text=True, timeout=30,
            )
            changed = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            out_of_scope = [f for f in changed if f not in scope_files]
            if out_of_scope:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    message=f"{len(out_of_scope)} files changed outside scope",
                    detail={"out_of_scope": out_of_scope},
                )
            return GateResult(
                gate_name=self.name,
                status=GateStatus.PASS,
                message=f"All {len(changed)} changed files within scope",
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=str(e),
            )


class FinishGateGate(BaseGate):
    """Run the existing agent-finish-gate.sh script."""
    name = "finish_gate"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        script = Path.cwd() / "scripts" / "captain" / "agent-finish-gate.sh"
        if not script.exists():
            # Script not present = skip (but explicitly, not as pass)
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="agent-finish-gate.sh not found",
            )
        return self._run_script(str(script), worktree)

    def _run_script(self, script: str, worktree: str) -> GateResult:
        try:
            env_override = {}
            if worktree:
                env_override["GIT_DIR"] = str(Path(worktree) / ".git")
            result = subprocess.run(
                ["bash", script],
                capture_output=True, text=True, timeout=120,
                cwd=worktree or None,
                env={**__import__("os").environ, **env_override} if env_override else None,
            )
            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message=result.stdout.strip()[-500:] if result.stdout.strip() else "OK",
                )
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=result.stderr.strip()[-500:] if result.stderr.strip() else f"Exit code {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message="Gate script timed out (120s)",
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=str(e),
            )


class TypecheckGate(BaseGate):
    """Run type checking."""
    name = "typecheck"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        wt = worktree or str(Path.cwd())
        try:
            result = subprocess.run(
                ["python", "-m", "mypy", "--no-error-summary", "-q", "."],
                capture_output=True, text=True, timeout=120,
                cwd=wt,
            )
            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="No type errors",
                )
            errors = result.stdout.strip().split("\n")[:10]
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Type errors found: {len(result.stdout.strip().splitlines())}",
                detail={"sample": errors},
            )
        except FileNotFoundError:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="mypy not installed",
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=str(e),
            )


class ClassTestGate(BaseGate):
    """Run change-class-based tests."""
    name = "class_tests"

    def run(self, agent_record: dict, worktree: str = "") -> GateResult:
        wt = worktree or str(Path.cwd())
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-x", "-q", "--tb=short"],
                capture_output=True, text=True, timeout=300,
                cwd=wt,
            )
            output = result.stdout.strip()
            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="All tests passed",
                    detail={"output_tail": output[-300:] if output else ""},
                )
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message="Tests failed",
                detail={"output_tail": output[-500:] if output else ""},
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message="Test run timed out (300s)",
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.ERROR,
                message=str(e),
            )


# ── Gate Registry ─────────────────────────────────────────────────

BUILTIN_GATES: Dict[str, BaseGate] = {
    "dirty_worktree": DirtyWorktreeGate(),
    "scope_check": ScopeCheckGate(),
    "finish_gate": FinishGateGate(),
    "typecheck": TypecheckGate(),
    "class_tests": ClassTestGate(),
}


class GateRunner:
    """
    Orchestrates gate runs based on profiles.

    Loads profiles from YAML, runs the required gates, collects results.
    SKIPPED is never treated as PASS.
    """

    def __init__(self, control_dir: Optional[Path] = None):
        if control_dir is None:
            control_dir = Path.cwd() / ".conduvera" / "control"
        self._control_dir = control_dir
        self._gates_path = control_dir / "policies" / "gates.yaml"
        self._profiles: Optional[Dict[str, GateProfile]] = None

    def _load_profiles(self) -> Dict[str, GateProfile]:
        if self._profiles is not None:
            return self._profiles
        if not self._gates_path.exists():
            self._profiles = {}
            return self._profiles
        with open(self._gates_path, "r") as f:
            data = yaml.safe_load(f) or {}
        profiles = {}
        for name, pdata in data.get("gate_profiles", {}).items():
            profiles[name] = GateProfile.from_yaml_dict(name, pdata)
        self._profiles = profiles
        return self._profiles

    def reload_profiles(self):
        """Force reload of profiles from disk."""
        self._profiles = None
        return self._load_profiles()

    def get_profile(self, name: str) -> Optional[GateProfile]:
        profiles = self._load_profiles()
        return profiles.get(name)

    def list_profiles(self) -> List[str]:
        return list(self._load_profiles().keys())

    def run_for_agent(
        self,
        agent_record: dict,
        profile_name: Optional[str] = None,
        extra_gates: Optional[List[str]] = None,
    ) -> GateRunResult:
        """
        Run all required gates for an agent.

        agent_record: dict (from AgentRecord.to_dict())
        profile_name: override profile (defaults to agent's gate_profile)
        extra_gates: additional gates to run beyond profile
        """
        pname = profile_name or agent_record.get("gate_profile", "default")
        profile = self.get_profile(pname)

        worktree = agent_record.get("worktree", "")

        # Determine which gates to run
        if profile:
            gate_names = list(profile.required)
        else:
            # No profile found = run core gates only
            gate_names = ["dirty_worktree", "scope_check"]

        if extra_gates:
            gate_names.extend(g for g in extra_gates if g not in gate_names)

        # Run gates
        results: List[GateResult] = []
        for gate_name in gate_names:
            gate = BUILTIN_GATES.get(gate_name)
            if gate is None:
                results.append(GateResult(
                    gate_name=gate_name,
                    status=GateStatus.ERROR,
                    message=f"Unknown gate: {gate_name}",
                ))
                continue
            results.append(gate.run(agent_record, worktree))

        # Determine overall pass
        # SKIPPED gates do NOT count as pass for required gates
        required_passed = all(
            r.status == GateStatus.PASS
            for r in results
            if r.gate_name in (profile.required if profile else gate_names)
        )

        return GateRunResult(
            agent_id=agent_record.get("agent_id", "unknown"),
            profile_name=pname,
            gates=results,
            overall_pass=required_passed,
        )
