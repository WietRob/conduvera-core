#!/usr/bin/env python3
"""Repo-agnostic Buildroom project-pack primitives.

This module contains only generic ProjectPack loading and derived path helpers.
Project-specific defaults belong in YAML files under ~/.hermes/buildroom/projects/,
not in this core module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildroom_backend_policy import BackendPolicyError, require_backend_enabled
from buildroom_review_convergence import ReviewConvergencePolicy

try:
    import yaml
except ImportError:  # pragma: no cover - validated at runtime
    yaml = None

PROJECTS_DIR = Path.home() / ".hermes/buildroom/projects"
EVIDENCE_PATTERNS = {
    "RESEARCHER": "researcher/researcher-cycle-{cycle}-{date}.md",
    "DREAMER": "dreamer/dreamer-cycle-{cycle}-{date}.md",
    "BUILDER": "builder/builder-cycle-{cycle}-{candidate}-{date}.md",
    "REVIEWER": "reviewer/reviewer-cycle-{cycle}-{date}.md",
    "REPORTER": "reporter/reporter-cycle-{cycle}-{date}.md",
}
PHASES_WITH_LOCKS = ("RESEARCHER", "DREAMER", "BUILDER", "REVIEWER")
ALL_PHASES = ("RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER")
DELIVERY_MODES = ("disabled", "research_only", "full", "engineering_finish_line")
EXECUTION_BACKENDS = ("native", "codex_cli", "opencode_cli")
EXECUTION_MODES = ("native", "pilot", "external")


class ProjectPackError(ValueError):
    """Raised when a project pack cannot be loaded or validated."""


@dataclass(frozen=True)
class ExecutionObservation:
    """Independent repository/test observation used to verify backend evidence."""

    branch: str
    files_changed: tuple[str, ...]
    test_command: str
    test_exit_code: int
    base_commit: str


@dataclass(frozen=True)
class ExecutionCommand:
    """Backend-neutral command description. The Buildroom retains authority."""

    role: str
    backend: str
    argv: tuple[str, ...]
    workdir: Path
    output_path: Path | None
    use_pty: bool = False
    allowed_mutations: tuple[str, ...] = ("assigned_worktree",)

    def option_pair(self, option: str) -> tuple[str, str]:
        try:
            index = self.argv.index(option)
            return self.argv[index], self.argv[index + 1]
        except (ValueError, IndexError) as exc:
            raise ProjectPackError(f"COMMAND_OPTION_MISSING: {option}") from exc


@dataclass(frozen=True)
class ProjectPack:
    """Repo-agnostic project configuration loaded from YAML."""

    project_name: str
    repo_path: Path
    evidence_dir: Path
    default_branch: str = "main"
    test_command: str = "pytest -q"
    builder_branch_prefix: str = "autonomy"
    project_pack: str = ""
    github_repo: str = ""
    kanban_board: str = "default"
    researcher_focus_areas: str = ""
    dreamer_epic_hints: str = ""
    strategy_files: tuple[str, ...] = field(default_factory=tuple)
    candidate_sources: tuple[str, ...] = field(default_factory=tuple)
    reviewer_require_no_secrets: bool = True
    reviewer_require_tests: bool = True
    merge_require_approve_merge: bool = True
    merge_require_clean_test_baseline: bool = True
    policy_defined: bool = False
    autopilot_enabled: bool = False
    delivery_mode: str = "disabled"
    allowed_phases: tuple[str, ...] = field(default_factory=tuple)
    researcher_profile: str = ""
    dreamer_profile: str = ""
    builder_profile: str = ""
    reviewer_profile: str = ""
    reporter_profile: str = ""
    builder_backend: str = "native"
    reviewer_backend: str = "native"
    builder_model: str | None = None
    reviewer_model: str | None = None
    builder_fallbacks: tuple[str, ...] = field(default_factory=tuple)
    reviewer_fallbacks: tuple[str, ...] = field(default_factory=tuple)
    independence_owner_approved: bool = False
    independence_owner_approval_ref: str = ""
    source_path: Path | None = None
    execution_mode: str = "native"
    pilot_enabled: bool = False
    pilot_id: str | None = None
    pilot_allowed_roles: tuple[str, ...] = field(default_factory=tuple)
    pilot_allowed_cycles: tuple[int, ...] = field(default_factory=tuple)
    pilot_expires_at: str | None = None
    review_convergence: ReviewConvergencePolicy = field(
        default_factory=ReviewConvergencePolicy
    )

    @property
    def state_file(self) -> Path:
        return self.evidence_dir / "orchestrator-state.json"

    @property
    def lock_file(self) -> Path:
        return self.evidence_dir / ".orchestrator-lock"

    @property
    def baseline_file(self) -> Path:
        return self.evidence_dir / "test-baseline.json"

    @property
    def evidence_patterns(self) -> dict[str, str]:
        return dict(EVIDENCE_PATTERNS)

    @property
    def phase_locks(self) -> dict[str, Path]:
        return {phase: self.evidence_dir / f".{phase.lower()}-running" for phase in PHASES_WITH_LOCKS}

    def evidence_path(self, phase: str, *, cycle: int, date: str, candidate: str | None = None) -> Path:
        """Return the evidence path for a phase without touching the filesystem."""
        phase_key = phase.upper()
        try:
            pattern = EVIDENCE_PATTERNS[phase_key]
        except KeyError as exc:
            raise ProjectPackError(f"Unknown evidence phase: {phase}") from exc
        if "{candidate}" in pattern and not candidate:
            raise ProjectPackError(f"Candidate is required for {phase_key} evidence path")
        return self.evidence_dir / pattern.format(cycle=cycle, date=date, candidate=candidate or "")

    def phase_allowed(self, phase: str) -> bool:
        return phase.upper() in self.allowed_phases

    def require_phase(self, phase: str) -> None:
        phase_key = phase.upper()
        if not self.policy_defined:
            raise ProjectPackError("OPERATING_POLICY_REQUIRED")
        if phase_key not in self.allowed_phases:
            raise ProjectPackError(f"PHASE_NOT_ALLOWED: {phase_key}")
        if self.delivery_mode == "research_only" and phase_key != "RESEARCHER":
            raise ProjectPackError(f"PHASE_NOT_ALLOWED_RESEARCH_ONLY: {phase_key}")

    def require_autonomous_phase(self, phase: str) -> None:
        if not self.autopilot_enabled:
            raise ProjectPackError("AUTOPILOT_DISABLED")
        self.require_phase(phase)

    def profile_for(self, role: str) -> str:
        role_key = role.upper()
        profiles = {
            "RESEARCHER": self.researcher_profile,
            "DREAMER": self.dreamer_profile,
            "BUILDER": self.builder_profile,
            "REVIEWER": self.reviewer_profile,
            "REPORTER": self.reporter_profile,
        }
        try:
            profile = profiles[role_key]
        except KeyError as exc:
            raise ProjectPackError(f"UNKNOWN_PROFILE_ROLE: {role_key}") from exc
        if not profile:
            raise ProjectPackError(f"PROFILE_NOT_CONFIGURED: {role_key}")
        return profile

    def backend_for(self, role: str) -> str:
        role_key = role.upper()
        if role_key == "BUILDER":
            backend = self.builder_backend
        elif role_key == "REVIEWER":
            backend = self.reviewer_backend
        else:
            raise ProjectPackError(f"EXECUTION_BACKEND_NOT_APPLICABLE: {role_key}")
        try:
            require_backend_enabled(backend)
        except BackendPolicyError as exc:
            raise ProjectPackError(str(exc)) from exc
        return backend

    def model_for(self, role: str) -> str | None:
        role_key = role.upper()
        if role_key == "BUILDER":
            return self.builder_model
        if role_key == "REVIEWER":
            return self.reviewer_model
        raise ProjectPackError(f"EXECUTION_MODEL_NOT_APPLICABLE: {role_key}")

    def backend_identity(self, role: str) -> tuple[str, str]:
        role_key = role.upper()
        backend = self.backend_for(role_key)
        model = self.model_for(role_key)
        if backend == "native":
            identity = model.strip().lower() if model else f"profile:{self.profile_for(role_key)}"
            return backend, identity
        return backend, model or "unspecified-model"

    def authorize_external_execution(
        self,
        *,
        role: str,
        cycle: int,
        pilot_id: str | None = None,
        activation_token: str | None = None,
    ) -> dict[str, Any] | None:
        """Return an authorization envelope or None for native execution."""
        role_key = role.upper()
        if self.execution_mode == "native":
            if self.backend_for(role_key) != "native":
                raise ProjectPackError("EXTERNAL_EXECUTION_NOT_AUTHORIZED")
            return None
        if self.execution_mode == "pilot":
            if not self.pilot_enabled:
                raise ProjectPackError("PILOT_NOT_ENABLED")
            if not self.pilot_id:
                raise ProjectPackError("PILOT_ID_REQUIRED")
            if not self.pilot_expires_at:
                raise ProjectPackError("PILOT_EXPIRY_REQUIRED")
            try:
                expiry = datetime.fromisoformat(self.pilot_expires_at)
            except (ValueError, TypeError) as exc:
                raise ProjectPackError(f"INVALID_PILOT_EXPIRY: {self.pilot_expires_at}") from exc
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expiry:
                raise ProjectPackError("PILOT_EXPIRED")
            if cycle not in self.pilot_allowed_cycles:
                raise ProjectPackError("CYCLE_NOT_AUTHORIZED")
            if role_key not in self.pilot_allowed_roles:
                raise ProjectPackError("ROLE_NOT_AUTHORIZED")
            if pilot_id != self.pilot_id:
                raise ProjectPackError("PILOT_ID_MISMATCH")
            return {
                "role": role_key,
                "backend": self.backend_for(role_key),
                "provider": "pilot-configured-provider",
                "model": self.model_for(role_key) or "unspecified-model",
                "pilot_id": self.pilot_id,
                "pilot_expires_at": self.pilot_expires_at,
                "cycle": cycle,
            }
        if self.execution_mode == "external":
            if not activation_token:
                raise ProjectPackError("EXTERNAL_MODE_ACTIVATION_TOKEN_REQUIRED")
            return {
                "role": role_key,
                "backend": self.backend_for(role_key),
                "provider": "external-configured-provider",
                "model": self.model_for(role_key) or "unspecified-model",
                "mode": "external",
                "activation_token": activation_token,
                "cycle": cycle,
            }
        raise ProjectPackError(f"UNKNOWN_EXECUTION_MODE: {self.execution_mode}")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProjectPack":
        """Load and validate a project pack from YAML."""
        if yaml is None:
            raise ProjectPackError("PyYAML is required for project pack loading")

        pack_path = Path(path).expanduser().resolve()
        if not pack_path.exists():
            raise ProjectPackError(f"Project pack not found: {pack_path}")

        with pack_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ProjectPackError(f"Project pack must be a YAML mapping: {pack_path}")

        return cls.from_mapping(data, source_path=pack_path)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, source_path: Path | None = None) -> "ProjectPack":
        """Build a ProjectPack from already-parsed YAML data."""
        required = ("project_name", "repo_path", "evidence_dir")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ProjectPackError(f"Missing required project pack field(s): {', '.join(missing)}")

        builder = data.get("builder") or {}
        reviewer = data.get("reviewer") or {}
        merge = data.get("merge") or {}
        review_convergence_raw = data.get("review_convergence") or {}
        if not isinstance(builder, dict) or not isinstance(reviewer, dict) or not isinstance(merge, dict):
            raise ProjectPackError("builder/reviewer/merge sections must be mappings")
        if not isinstance(review_convergence_raw, dict):
            raise ProjectPackError("review_convergence must be a mapping")

        policy_keys = ("autopilot_enabled", "delivery_mode", "allowed_phases", "profiles", "execution")
        present_policy_keys = [key for key in policy_keys if key in data]
        policy_defined = len(present_policy_keys) == len(policy_keys)
        if present_policy_keys and not policy_defined:
            missing_policy_keys = [key for key in policy_keys if key not in data]
            raise ProjectPackError(f"INCOMPLETE_OPERATING_POLICY: missing {', '.join(missing_policy_keys)}")

        if policy_defined:
            profiles = data["profiles"]
            execution = data["execution"]
            allowed_raw = data["allowed_phases"]
            if not isinstance(profiles, dict) or not isinstance(execution, dict):
                raise ProjectPackError("profiles/execution sections must be mappings")
            if not isinstance(allowed_raw, list):
                raise ProjectPackError("allowed_phases must be a list")
            delivery_mode = str(data["delivery_mode"])
            if delivery_mode not in DELIVERY_MODES:
                raise ProjectPackError(f"UNKNOWN_DELIVERY_MODE: {delivery_mode}")
            allowed_phases = tuple(dict.fromkeys(str(item).upper() for item in allowed_raw))
            unknown_phases = [phase for phase in allowed_phases if phase not in ALL_PHASES]
            if unknown_phases:
                raise ProjectPackError(f"UNKNOWN_PHASE: {', '.join(unknown_phases)}")
            if delivery_mode == "research_only" and any(phase != "RESEARCHER" for phase in allowed_phases):
                raise ProjectPackError("RESEARCH_ONLY_PHASE_VIOLATION")

            builder_backend = str(execution.get("builder_backend", ""))
            reviewer_backend = str(execution.get("reviewer_backend", ""))
            for backend_name in (builder_backend, reviewer_backend):
                if backend_name not in EXECUTION_BACKENDS:
                    raise ProjectPackError(f"UNKNOWN_EXECUTION_BACKEND: {backend_name}")
                try:
                    require_backend_enabled(backend_name)
                except BackendPolicyError as exc:
                    raise ProjectPackError(str(exc)) from exc
            builder_model_raw = execution.get("builder_model")
            reviewer_model_raw = execution.get("reviewer_model")
            builder_model = str(builder_model_raw) if builder_model_raw is not None else None
            reviewer_model = str(reviewer_model_raw) if reviewer_model_raw is not None else None
            independence_exception = execution.get("reviewer_independence_exception") or {}
            if not isinstance(independence_exception, dict):
                raise ProjectPackError("reviewer_independence_exception must be a mapping")
            owner_approved = bool(
                execution.get("independence_owner_approved", independence_exception.get("approved", False))
            )
            owner_ref = str(execution.get("independence_owner_approval_ref", ""))
            if not owner_ref and independence_exception:
                approved_by = str(independence_exception.get("approved_by", ""))
                approved_at = str(independence_exception.get("approved_at", ""))
                if approved_by and approved_at:
                    owner_ref = f"{approved_by}@{approved_at}"
            builder_profile = str(profiles.get("builder", ""))
            reviewer_profile = str(profiles.get("reviewer", ""))
            if "BUILDER" in allowed_phases and not builder_profile:
                raise ProjectPackError("PROFILE_NOT_CONFIGURED: BUILDER")
            if "REVIEWER" in allowed_phases and not reviewer_profile:
                raise ProjectPackError("PROFILE_NOT_CONFIGURED: REVIEWER")

            builder_identity = (
                builder_backend,
                builder_model.strip().lower()
                if builder_backend == "native" and builder_model
                else f"profile:{builder_profile}"
                if builder_backend == "native"
                else (builder_model or "unspecified-model").strip().lower(),
            )
            reviewer_identity = (
                reviewer_backend,
                reviewer_model.strip().lower()
                if reviewer_backend == "native" and reviewer_model
                else f"profile:{reviewer_profile}"
                if reviewer_backend == "native"
                else (reviewer_model or "unspecified-model").strip().lower(),
            )
            if builder_identity == reviewer_identity and not (owner_approved and owner_ref):
                raise ProjectPackError("BUILDER_REVIEWER_NOT_INDEPENDENT")
        else:
            profiles = {}
            execution = {}
            delivery_mode = "disabled"
            allowed_phases = ()
            builder_backend = "native"
            reviewer_backend = "native"
            builder_model = None
            reviewer_model = None
            owner_approved = False
            owner_ref = ""

        return cls(
            project_name=str(data["project_name"]),
            repo_path=Path(str(data["repo_path"])).expanduser().resolve(),
            evidence_dir=Path(str(data["evidence_dir"])).expanduser().resolve(),
            default_branch=str(data.get("default_branch", "main")),
            test_command=str(data.get("test_command", "pytest -q")),
            builder_branch_prefix=str(builder.get("branch_prefix", "autonomy")),
            project_pack=str(data.get("project_pack", data["project_name"])),
            github_repo=str(data.get("github_repo", "")),
            kanban_board=str(data.get("kanban_board", "default")),
            researcher_focus_areas=str(data.get("researcher_focus_areas", "")),
            dreamer_epic_hints=str(data.get("dreamer_epic_hints", "")),
            strategy_files=tuple(str(item) for item in data.get("strategy_files", []) or ()),
            candidate_sources=tuple(str(item) for item in data.get("candidate_sources", []) or ()),
            reviewer_require_no_secrets=bool(reviewer.get("require_no_secrets", True)),
            reviewer_require_tests=bool(reviewer.get("require_tests", True)),
            merge_require_approve_merge=bool(merge.get("require_approve_merge", True)),
            merge_require_clean_test_baseline=bool(merge.get("require_clean_test_baseline", True)),
            policy_defined=policy_defined,
            autopilot_enabled=bool(data.get("autopilot_enabled", False)) if policy_defined else False,
            delivery_mode=delivery_mode,
            allowed_phases=allowed_phases,
            researcher_profile=str(profiles.get("researcher", "")),
            dreamer_profile=str(profiles.get("dreamer", "")),
            builder_profile=str(profiles.get("builder", "")),
            reviewer_profile=str(profiles.get("reviewer", "")),
            reporter_profile=str(profiles.get("reporter", "")),
            builder_backend=builder_backend,
            reviewer_backend=reviewer_backend,
            builder_model=builder_model,
            reviewer_model=reviewer_model,
            builder_fallbacks=tuple(str(item) for item in execution.get("builder_fallbacks", []) or ()),
            reviewer_fallbacks=tuple(str(item) for item in execution.get("reviewer_fallbacks", []) or ()),
            independence_owner_approved=owner_approved,
            independence_owner_approval_ref=owner_ref,
            source_path=source_path,
            execution_mode=str(execution.get("mode", "native")),
            pilot_enabled=bool((execution.get("pilot") or {}).get("enabled", False)),
            pilot_id=str(pid) if (pid := (execution.get("pilot") or {}).get("pilot_id")) is not None else None,
            pilot_allowed_roles=tuple(str(item) for item in (execution.get("pilot") or {}).get("allowed_roles", []) or ()),
            pilot_allowed_cycles=tuple(int(item) for item in (execution.get("pilot") or {}).get("allowed_cycles", []) or ()),
            pilot_expires_at=str(expires) if (expires := (execution.get("pilot") or {}).get("expires_at")) is not None else None,
            review_convergence=ReviewConvergencePolicy.from_mapping(
                review_convergence_raw
            ),
        )


def project_pack_path(project_arg: str, *, projects_dir: Path = PROJECTS_DIR) -> Path:
    """Resolve a project name or YAML path to a concrete YAML path."""
    if not project_arg:
        raise ProjectPackError("PROJECT_PACK_REQUIRED")

    named_path = projects_dir / f"{project_arg}.yaml"
    if named_path.exists():
        return named_path.resolve()

    explicit_path = Path(project_arg).expanduser()
    if explicit_path.exists():
        return explicit_path.resolve()

    raise ProjectPackError(f"Project '{project_arg}' not found in {projects_dir} or as path")


def resolve_project(project_arg: str | None, *, projects_dir: Path = PROJECTS_DIR) -> ProjectPack:
    """Resolve and load a project pack.

    Generic mode is intentionally strict: callers must pass --project. The old
    PeekXD fallback lives only in buildroom_loop.py's explicit --legacy-peekxd mode.
    """
    if not project_arg:
        raise ProjectPackError("PROJECT_PACK_REQUIRED")
    return ProjectPack.from_yaml(project_pack_path(project_arg, projects_dir=projects_dir))


def format_pack_summary(pack: ProjectPack) -> str:
    """Human-readable pack summary for dry runs and diagnostics."""
    lines = [
        f"Project: {pack.project_name}",
        f"  Repo: {pack.repo_path}",
        f"  Evidence: {pack.evidence_dir}",
        f"  State: {pack.state_file}",
        f"  Baseline: {pack.baseline_file}",
        f"  Branch: {pack.default_branch}",
        f"  Branch prefix: {pack.builder_branch_prefix}",
        f"  GitHub repo: {pack.github_repo or '(none)'}",
        f"  Test: {pack.test_command}",
        f"  Strategy files: {len(pack.strategy_files)}",
        f"  Candidate sources: {len(pack.candidate_sources)}",
        f"  Operating policy: {'defined' if pack.policy_defined else 'missing (fail-closed)'}",
        f"  Autopilot: {'enabled' if pack.autopilot_enabled else 'disabled'}",
        f"  Delivery mode: {pack.delivery_mode}",
        f"  Allowed phases: {', '.join(pack.allowed_phases) or '(none)'}",
        f"  Builder: {pack.builder_profile or '(none)'} via {pack.builder_backend}",
        f"  Reviewer: {pack.reviewer_profile or '(none)'} via {pack.reviewer_backend}",
        f"  Review convergence: {'enabled' if pack.review_convergence.enabled else 'disabled'}",
    ]
    return "\n".join(lines)


def build_execution_command(
    pack: ProjectPack,
    *,
    role: str,
    workdir: str | Path,
    prompt: str,
    output_path: str | Path,
    schema_path: str | Path | None = None,
) -> ExecutionCommand:
    """Build a command after canonical policy authorization.

    External branches below are dormant compatibility code while Owner policy
    disables ``codex_cli`` and ``opencode_cli``.
    """
    role_key = role.upper()
    if role_key not in ("BUILDER", "REVIEWER"):
        raise ProjectPackError(f"EXECUTION_ROLE_UNSUPPORTED: {role_key}")
    backend = pack.backend_for(role_key)
    model = pack.model_for(role_key)
    cwd = Path(workdir).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()

    if backend == "native":
        return ExecutionCommand(role_key, backend, (), cwd, output)

    if backend == "codex_cli":
        if schema_path is None:
            raise ProjectPackError("CODEX_OUTPUT_SCHEMA_REQUIRED")
        schema = Path(schema_path).expanduser().resolve()
        argv = [
            "codex", "exec",
            "--sandbox", "workspace-write",
            "--json",
            "--output-schema", str(schema),
            "--output-last-message", str(output),
            "-C", str(cwd),
        ]
        if model:
            argv.extend(("--model", model))
        argv.append(prompt)
        return ExecutionCommand(role_key, backend, tuple(argv), cwd, output)

    if backend == "opencode_cli":
        if not model:
            raise ProjectPackError("OPENCODE_MODEL_REQUIRED")
        model_lower = model.lower()
        if role_key == "REVIEWER" and any(token in model_lower for token in ("openai", "codex", "gpt-")):
            raise ProjectPackError("REVIEWER_MODEL_NOT_INDEPENDENT")
        agent = "plan" if role_key == "REVIEWER" else "build"
        argv = (
            "opencode", "run",
            "--dir", str(cwd),
            "--agent", agent,
            "--format", "json",
            "--model", model,
            prompt,
        )
        return ExecutionCommand(role_key, backend, argv, cwd, output)

    raise ProjectPackError(f"UNKNOWN_EXECUTION_BACKEND: {backend}")


def execution_evidence_schema() -> dict[str, Any]:
    """Return the canonical execution-evidence-v1 JSON Schema."""
    required = [
        "schema", "role", "backend", "provider", "model", "backend_version",
        "run_id", "repo", "base_commit", "branch", "files_changed",
        "commands_run", "tests", "result", "blocker",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "execution-evidence-v1",
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": {
            "schema": {"const": "execution-evidence-v1"},
            "role": {"enum": ["BUILDER", "REVIEWER"]},
            "backend": {"enum": list(EXECUTION_BACKENDS)},
            "provider": {"type": "string", "minLength": 1},
            "model": {"type": "string", "minLength": 1},
            "backend_version": {"type": "string", "minLength": 1},
            "run_id": {"type": "string", "minLength": 1},
            "repo": {"type": "string", "minLength": 1},
            "base_commit": {"type": "string", "minLength": 1},
            "branch": {"type": "string", "minLength": 1},
            "files_changed": {"type": "array", "items": {"type": "string"}},
            "commands_run": {"type": "array", "items": {"type": "string"}},
            "tests": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "passed", "failed", "exit_code"],
                "properties": {
                    "command": {"type": "string"},
                    "passed": {"type": "integer", "minimum": 0},
                    "failed": {"type": "integer", "minimum": 0},
                    "exit_code": {"type": "integer"},
                },
            },
            "result": {"enum": ["COMPLETE", "BLOCKED"]},
            "blocker": {"type": ["string", "null"]},
        },
    }


def validate_delegation_permissions(*, read_only: bool, allowed_mutations: tuple[str, ...]) -> None:
    """Reject mutation authority on an explicitly read-only delegation."""
    if read_only and allowed_mutations:
        raise ProjectPackError("READ_ONLY_DELEGATION_MUTATION_FORBIDDEN")


def validate_execution_evidence(
    record: dict[str, Any],
    *,
    expected_role: str,
    expected_repo: str,
    observation: ExecutionObservation | None,
) -> dict[str, Any]:
    """Validate backend evidence and require independent disk/test observation."""
    required = execution_evidence_schema()["required"]
    missing = [field for field in required if field not in record]
    if missing:
        raise ProjectPackError(f"MISSING_EXECUTION_EVIDENCE_FIELD: {', '.join(missing)}")
    if record["schema"] != "execution-evidence-v1":
        raise ProjectPackError("INVALID_EXECUTION_EVIDENCE_SCHEMA")
    role_key = expected_role.upper()
    if record["role"] != role_key:
        raise ProjectPackError("EXECUTION_EVIDENCE_ROLE_MISMATCH")
    if record["backend"] not in EXECUTION_BACKENDS:
        raise ProjectPackError("UNKNOWN_EXECUTION_BACKEND")
    try:
        require_backend_enabled(str(record["backend"]))
    except BackendPolicyError as exc:
        raise ProjectPackError(str(exc)) from exc
    if record["repo"] != expected_repo:
        raise ProjectPackError("EXECUTION_EVIDENCE_REPO_MISMATCH")
    for field in ("provider", "model", "backend_version", "run_id", "base_commit", "branch"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise ProjectPackError(f"INVALID_EXECUTION_EVIDENCE_FIELD: {field}")
    if not isinstance(record["files_changed"], list) or not all(
        isinstance(item, str) for item in record["files_changed"]
    ):
        raise ProjectPackError("INVALID_EXECUTION_EVIDENCE_FIELD: files_changed")
    if not isinstance(record["commands_run"], list) or not all(
        isinstance(item, str) for item in record["commands_run"]
    ):
        raise ProjectPackError("INVALID_EXECUTION_EVIDENCE_FIELD: commands_run")
    tests = record["tests"]
    if not isinstance(tests, dict) or any(
        key not in tests for key in ("command", "passed", "failed", "exit_code")
    ):
        raise ProjectPackError("INVALID_EXECUTION_EVIDENCE_FIELD: tests")
    if record["result"] not in ("COMPLETE", "BLOCKED"):
        raise ProjectPackError("INVALID_EXECUTION_RESULT")
    if record["result"] == "BLOCKED":
        if not record["blocker"]:
            raise ProjectPackError("BLOCKED_EXECUTION_REQUIRES_BLOCKER")
        return record
    if record["blocker"] is not None:
        raise ProjectPackError("COMPLETE_EXECUTION_HAS_BLOCKER")
    if observation is None:
        raise ProjectPackError("EVIDENCE_OBSERVATION_REQUIRED")
    mismatched = (
        record["branch"] != observation.branch
        or record["base_commit"] != observation.base_commit
        or tuple(sorted(record["files_changed"])) != tuple(sorted(observation.files_changed))
        or tests["command"] != observation.test_command
        or tests["exit_code"] != observation.test_exit_code
        or observation.test_exit_code != 0
        or tests["failed"] != 0
    )
    if mismatched:
        raise ProjectPackError("EVIDENCE_DISK_MISMATCH")
    return record
