"""Normalized domain types for the read-only Buildroom legacy slice.

These are the Matrix-OS-side projections of legacy Buildroom state/config
formats. They are deliberately minimal and schema-versioned so the reader
can emit MXOS-EVIDENCE-1.0.0 events without inventing new evidence schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BackendPolicyEntry:
    """Projection of one entry in execution-backends.yaml."""

    backend: str
    enabled: bool
    status: str | None = None
    requires_explicit_owner_activation: bool = False


@dataclass(frozen=True)
class ActiveProjectState:
    """Projection of buildroom-state/active-project.json."""

    schema_version: int
    active_project_id: str
    mode: str
    selected_by: str
    selected_at: str
    reason: str | None = None


@dataclass(frozen=True)
class ProjectPackSummary:
    """Projection of a ProjectPack YAML (read-only subset)."""

    project_name: str
    repo_path: str
    default_branch: str | None = None
    test_command: str | None = None
    github_repo: str | None = None
    autopilot_enabled: bool = False
    delivery_mode: str | None = None
    allowed_phases: tuple[str, ...] = ()
    execution: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LegacyStateSnapshot:
    """Complete read-only snapshot normalized from a fixture directory."""

    backends: tuple[BackendPolicyEntry, ...] = ()
    active_project: ActiveProjectState | None = None
    project_packs: tuple[ProjectPackSummary, ...] = ()
    raw_file_map: dict[str, str] = field(default_factory=dict)  # rel path -> sha256


@dataclass(frozen=True)
class ReadinessResult:
    """Structured readiness/inventory result of the reader."""

    ok: bool
    snapshot: LegacyStateSnapshot | None = None
    missing_files: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
