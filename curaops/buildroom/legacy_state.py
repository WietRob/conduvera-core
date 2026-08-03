"""Read-only Buildroom legacy state reader (first strangler slice).

Reads frozen legacy Buildroom state/config formats from a SUPPLIED fixture
directory and normalizes them into Matrix-OS domain types plus
MXOS-EVIDENCE-1.0.0 events.

Hard constraints (never violated):
- read-only: no state writes, no process start/stop/signal, no git/gh/
  systemd/Hermes/Codex/OpenCode/Buildroom invocation, no repo mutation,
  no live execution authority, no secret reads.
- dependency-injected paths: the caller supplies the fixture directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from ..evidence.contract import EventEnvelope, SCHEMA_VERSION

from .contracts import (
    ActiveProjectState,
    BackendPolicyEntry,
    LegacyStateSnapshot,
    ProjectPackSummary,
    ReadinessResult,
)

BACKENDS_REL = "execution-backends.yaml"
ACTIVE_PROJECT_REL = "state/active-project.json"
PROJECTS_REL = "projects"

EVENT_TYPE_INVENTORY = "buildroom.legacy.inventory.completed"
EVENT_TYPE_READINESS = "buildroom.legacy.readiness.completed"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class BuildroomLegacyStateReader:
    """Normalizes a frozen legacy Buildroom fixture directory."""

    def __init__(self, fixture_dir: str | Path):
        self.fixture_dir = Path(fixture_dir).expanduser().resolve()
        self._backend_policy: dict[str, BackendPolicyEntry] = {}
        self._active_project: ActiveProjectState | None = None
        self._project_packs: list[ProjectPackSummary] = []
        self._file_map: dict[str, str] = {}
        self._warnings: list[str] = []
        self._errors: list[str] = []

    # -- public API ------------------------------------------------------

    def read(self) -> ReadinessResult:
        """Parse the fixture directory and return a normalized snapshot."""
        self._backend_policy = {}
        self._active_project = None
        self._project_packs = []
        self._file_map = {}
        self._warnings = []
        self._errors = []

        missing: list[str] = []

        backends_path = self.fixture_dir / BACKENDS_REL
        if backends_path.is_file():
            self._read_backends(backends_path)
        else:
            missing.append(BACKENDS_REL)

        active_path = self.fixture_dir / ACTIVE_PROJECT_REL
        if active_path.is_file():
            self._read_active_project(active_path)
        else:
            missing.append(ACTIVE_PROJECT_REL)

        projects_dir = self.fixture_dir / PROJECTS_REL
        if projects_dir.is_dir():
            for yml in sorted(projects_dir.glob("*.yaml")):
                self._read_project_pack(yml)
        else:
            missing.append(PROJECTS_REL + "/")

        snapshot = LegacyStateSnapshot(
            backends=tuple(self._backend_policy.values()),
            active_project=self._active_project,
            project_packs=tuple(self._project_packs),
            raw_file_map=self._file_map,
        )

        ok = not self._errors and not missing
        return ReadinessResult(
            ok=ok,
            snapshot=snapshot,
            missing_files=tuple(missing),
            errors=tuple(self._errors),
            warnings=tuple(self._warnings),
        )

    def emit_events(self, readiness: ReadinessResult, *, producer: dict[str, Any]) -> list[EventEnvelope]:
        """Emit MXOS-EVIDENCE-1.0.0 events for inventory + readiness.

        Producer is caller-supplied (identity of the reading component).
        """
        snap = readiness.snapshot
        events: list[EventEnvelope] = []

        if snap is None:
            inventory_payload = {
                "fixture_dir": str(self.fixture_dir),
                "backends": {},
                "active_project": None,
                "project_packs": [],
                "file_count": 0,
                "error": "no snapshot produced",
            }
        else:
            backends = {b.backend: b for b in snap.backends}
            inventory_payload = {
                "fixture_dir": str(self.fixture_dir),
                "backends": {
                    name: {
                        "enabled": e.enabled,
                        "status": e.status,
                        "requires_explicit_owner_activation": e.requires_explicit_owner_activation,
                    }
                    for name, e in backends.items()
                },
                "active_project": (
                    snap.active_project.active_project_id if snap.active_project else None
                ),
                "project_packs": [p.project_name for p in snap.project_packs],
                "file_count": len(snap.raw_file_map),
            }
        events.append(
            EventEnvelope.create(
                event_type=EVENT_TYPE_INVENTORY,
                producer=producer,
                subject={"kind": "buildroom.legacy.inventory", "fixture": self.fixture_dir.name},
                payload=inventory_payload,
                severity="info",
            )
        )

        readiness_payload = {
            "ok": readiness.ok,
            "missing_files": list(readiness.missing_files),
            "errors": list(readiness.errors),
            "warnings": list(readiness.warnings),
        }
        events.append(
            EventEnvelope.create(
                event_type=EVENT_TYPE_READINESS,
                producer=producer,
                subject={"kind": "buildroom.legacy.readiness", "fixture": self.fixture_dir.name},
                payload=readiness_payload,
                severity="info" if readiness.ok else "warning",
            )
        )
        return events

    # -- parsers ---------------------------------------------------------

    def _read_backends(self, path: Path) -> None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # pragma: no cover - defensive
            self._errors.append(f"{BACKENDS_REL}: {exc}")
            return
        raw = data.get("execution_backends", data)
        if not isinstance(raw, dict):
            self._errors.append(f"{BACKENDS_REL}: expected mapping")
            return
        for backend, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            self._backend_policy[backend] = BackendPolicyEntry(
                backend=backend,
                enabled=bool(cfg.get("enabled", False)),
                status=cfg.get("status"),
                requires_explicit_owner_activation=bool(
                    cfg.get("requires_explicit_owner_activation", False)
                ),
            )
        self._file_map[BACKENDS_REL] = _sha256_bytes(path.read_bytes())

    def _read_active_project(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            self._errors.append(f"{ACTIVE_PROJECT_REL}: {exc}")
            return
        self._active_project = ActiveProjectState(
            schema_version=int(data.get("schema_version", 0)),
            active_project_id=str(data.get("active_project_id", "")),
            mode=str(data.get("mode", "")),
            selected_by=str(data.get("selected_by", "")),
            selected_at=str(data.get("selected_at", "")),
            reason=data.get("reason"),
        )
        self._file_map[ACTIVE_PROJECT_REL] = _sha256_bytes(path.read_bytes())

    def _read_project_pack(self, path: Path) -> None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # pragma: no cover - defensive
            self._errors.append(f"{PROJECTS_REL}/{path.name}: {exc}")
            return
        if not isinstance(data, dict):
            self._errors.append(f"{PROJECTS_REL}/{path.name}: expected mapping")
            return
        allowed = data.get("allowed_phases", [])
        if isinstance(allowed, str):
            allowed = [allowed]
        self._project_packs.append(
            ProjectPackSummary(
                project_name=str(data.get("project_name", path.stem)),
                repo_path=str(data.get("repo_path", "")),
                default_branch=data.get("default_branch"),
                test_command=data.get("test_command"),
                github_repo=data.get("github_repo"),
                autopilot_enabled=bool(data.get("autopilot_enabled", False)),
                delivery_mode=data.get("delivery_mode"),
                allowed_phases=tuple(str(p) for p in allowed),
                execution=dict(data.get("execution", {}) or {}),
            )
        )
        self._file_map[f"{PROJECTS_REL}/{path.name}"] = _sha256_bytes(path.read_bytes())
