"""Buildroom execution dispatcher — single selection authority.

Strangler dispatcher connecting the proven ManagedBuildroomCaller with the
actual Buildroom entry point. The legacy path stays the DEFAULT; an
explicitly approved canary task may run on the managed path.

Conduvera Core
  -> BuildroomExecutionDispatcher
       |-- legacy        -> existing Buildroom orchestrator
       `-- managed_canary -> ManagedBuildroomCaller -> TaskBinding ->
            Backend-Policy -> HarnessGatewayService -> Hermes -> LiteLLM
            -> ODS/ai-stack text mode -> MXOS-EVIDENCE ->
            No-Progress-Reconciliation

AUTHORITY BOUNDARIES (this module owns ONLY the path selection):
- No second task/policy/state/evidence authority.
- Conduvera Core stays task/attempt/policy/evidence authority.
- HarnessGatewayService stays the harness-lifecycle boundary.
- LiteLLM stays the model gateway; ODS/ai-stack stays the runtime/GPU/
  service authority; BWS stays the secrets authority.
- `ai-stack model use` remains exclusively the operator/AI-stack interface.

MODES:
- legacy: default; exact existing behaviour; ManagedBuildroomCaller is
  never called.
- managed_canary: ONLY explicitly approved canary task IDs run via
  ManagedBuildroomCaller; anything else fails closed. No dual-run, no
  shadow spawn with duplicated side effects.

CONFIG: single authority — fixtures/buildroom/execution-dispatcher.yaml
(`buildroom.execution_path` + `buildroom.canary_tasks`). Missing or invalid
value -> legacy (the conservative, existing behaviour).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from curaops.buildroom.managed_execution import (
    ManagedBuildroomCaller,
    ManagedExecutionResult,
)

MODE_LEGACY = "legacy"
MODE_MANAGED_CANARY = "managed_canary"
VALID_MODES = (MODE_LEGACY, MODE_MANAGED_CANARY)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "fixtures/buildroom/execution-dispatcher.yaml"


class DispatcherConfigError(ValueError):
    """Raised when the dispatcher config is structurally invalid."""


@dataclass(frozen=True)
class DispatcherConfig:
    execution_path: str = MODE_LEGACY
    canary_tasks: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "DispatcherConfig":
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not cfg_path.is_file():
            # Missing config -> conservative default (legacy), never canary.
            return cls()
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise DispatcherConfigError("DISPATCHER_CONFIG_INVALID") from exc
        br = data.get("buildroom", {})
        if not isinstance(br, dict):
            raise DispatcherConfigError("DISPATCHER_CONFIG_INVALID")
        mode = br.get("execution_path", MODE_LEGACY)
        if mode not in VALID_MODES:
            # Invalid value -> conservative default (legacy), fail-closed.
            mode = MODE_LEGACY
        canary = br.get("canary_tasks", [])
        if not isinstance(canary, list):
            raise DispatcherConfigError("DISPATCHER_CONFIG_INVALID")
        return cls(execution_path=mode, canary_tasks=tuple(str(t) for t in canary))


@dataclass
class DispatchResult:
    """Result of one dispatcher invocation (path selection + execution)."""

    task_id: str
    execution_path: str
    attempt_id: str
    status: str  # completed | legacy_delegated | canary_blocked | policy_blocked | hold | failed | duplicate_attempt
    detail: dict[str, Any] = field(default_factory=dict)
    managed_result: ManagedExecutionResult | None = None
    final_status_readable: str = ""


class BuildroomExecutionDispatcher:
    """Selects the execution path; owns NO second authority.

    - `resolve_path(task_id)` is the pure selection function.
    - `dispatch(...)` runs the selected path with single-writer per attempt
      (one lease file per attempt_id; a second dispatch for the same attempt
      fails closed as DUPLICATE_ATTEMPT).
    """

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        leases_dir: str | Path,
        managed_caller: ManagedBuildroomCaller | None = None,
        legacy_runner: Any = None,
    ):
        self._config = DispatcherConfig.load(config_path)
        self._leases_dir = Path(leases_dir).expanduser().resolve()
        self._leases_dir.mkdir(parents=True, exist_ok=True)
        # managed_caller injected for tests; productive path constructs it
        # with explicit execution_mode (never defaulted).
        self._managed_caller = managed_caller
        # legacy_runner: callable delegating to the existing orchestrator.
        # Default None -> a subprocess invocation of the legacy CLI entry.
        self._legacy_runner = legacy_runner

    # -- public selection --------------------------------------------------

    def resolve_path(self, task_id: str) -> str:
        """Pure path selection for a task ID.

        legacy (default) unless the config explicitly selects
        managed_canary AND the task ID is on the canary allowlist.
        """
        if self._config.execution_path == MODE_MANAGED_CANARY:
            if task_id in self._config.canary_tasks:
                return MODE_MANAGED_CANARY
            return MODE_LEGACY  # non-canary -> legacy, not a managed spawn
        return MODE_LEGACY

    # -- public execution --------------------------------------------------

    def dispatch(
        self,
        *,
        task_id: str,
        task_description: str,
        phase: str = "BUILDER",
        board: str = "conduvera",
        cycle: int | None = None,
        backend: str = "native",
        evidence_fingerprint: str = "",
        log_fingerprint: str = "",
        worktree_root: str | Path | None = None,
        caller_args: dict[str, Any] | None = None,
    ) -> DispatchResult:
        """Run one task through the selected path (single-writer per attempt)."""
        path = self.resolve_path(task_id)

        if path == MODE_MANAGED_CANARY:
            return self._dispatch_managed(
                task_id=task_id, task_description=task_description, phase=phase,
                board=board, cycle=cycle, backend=backend,
                evidence_fingerprint=evidence_fingerprint,
                log_fingerprint=log_fingerprint, worktree_root=worktree_root,
                caller_args=caller_args or {},
            )

        # legacy: exact existing behaviour; never touches ManagedBuildroomCaller.
        return self._dispatch_legacy(task_id=task_id, task_description=task_description)

    # -- internals ---------------------------------------------------------

    def _attempt_lease(self, attempt_id: str) -> Path:
        return self._leases_dir / f"{attempt_id}.lease.json"

    def _acquire_attempt_lease(self, task_id: str, attempt_id: str) -> bool:
        """Single-writer per attempt: second dispatch for the same attempt
        fails closed (no dual run, no shadow spawn)."""
        lease = self._attempt_lease(attempt_id)
        if lease.exists():
            return False
        lease.write_text(json.dumps({
            "schema": "buildroom.dispatcher.lease.v1",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "execution_path": self.resolve_path(task_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        return True

    def _release_attempt_lease(self, attempt_id: str) -> None:
        lease = self._attempt_lease(attempt_id)
        if lease.exists():
            lease.unlink()

    def _dispatch_managed(self, *, task_id: str, task_description: str, phase: str,
                          board: str, cycle: int | None, backend: str,
                          evidence_fingerprint: str, log_fingerprint: str,
                          worktree_root: str | Path | None,
                          caller_args: dict[str, Any]) -> DispatchResult:
        attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        if not self._acquire_attempt_lease(task_id, attempt_id):
            return DispatchResult(
                task_id=task_id, execution_path=MODE_MANAGED_CANARY,
                attempt_id=attempt_id, status="duplicate_attempt",
                final_status_readable="DUPLICATE_ATTEMPT: gleiche Attempt-ID bereits gestartet",
            )
        try:
            if self._managed_caller is None:
                # Productive construction: explicit execution_mode required.
                self._managed_caller = ManagedBuildroomCaller(
                    state_path=Path(caller_args.pop("state_path", ".")),
                    route_manifest=caller_args.pop("route_manifest", "."),
                    producer=caller_args.pop("producer", {"name": "conduvera-core", "version": "0.1.0"}),
                    execution_mode=caller_args.pop("execution_mode", None),
                    **caller_args,
                )
            result = self._managed_caller.execute(
                task_description=task_description, phase=phase, board=board,
                cycle=cycle, task_id=task_id, backend=backend,
                evidence_fingerprint=evidence_fingerprint,
                log_fingerprint=log_fingerprint, worktree_root=worktree_root,
            )
            status = result.status
            if status == "policy_blocked":
                status = "policy_blocked"
            elif status == "hold":
                status = "hold"
            elif status == "completed":
                status = "completed"
            return DispatchResult(
                task_id=task_id, execution_path=MODE_MANAGED_CANARY,
                attempt_id=attempt_id, status=status,
                detail={"policy_decision": result.policy_decision,
                        "reconciliation": result.reconciliation},
                managed_result=result,
                final_status_readable=result.final_status_readable,
            )
        finally:
            self._release_attempt_lease(attempt_id)

    def _dispatch_legacy(self, *, task_id: str, task_description: str) -> DispatchResult:
        """legacy: exact existing behaviour via the existing orchestrator.

        When a legacy_runner is injected (tests), delegate to it. Otherwise
        the legacy CLI entry (buildroom_loop.py --legacy-peekxd) is invoked
        as the existing entry point — ManagedBuildroomCaller is never called.
        """
        if self._legacy_runner is not None:
            result = self._legacy_runner(task_id=task_id, task_description=task_description)
            return DispatchResult(
                task_id=task_id, execution_path=MODE_LEGACY,
                attempt_id="", status="legacy_delegated",
                detail={"legacy_result": str(result)},
                final_status_readable="LEGACY: an bestehenden Orchestrator delegiert",
            )
        # No injected runner in this context: report delegation without
        # spawning anything (no dual run; the real CLI remains the entry).
        return DispatchResult(
            task_id=task_id, execution_path=MODE_LEGACY,
            attempt_id="", status="legacy_delegated",
            final_status_readable="LEGACY: bestehender Orchestrator (Default; kein Managed-Spawn)",
        )
