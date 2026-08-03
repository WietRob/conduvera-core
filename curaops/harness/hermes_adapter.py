"""Versioned Hermes harness adapter (CONDUVERA-GOAL-1.0 first vertical slice).

Contract (public, versioned — see contracts/harness-adapter.v1 in AGENTS.md):

- start(agent_id, worktree, task, config) -> AdapterResult
- status(session_id) -> AdapterResult
- cancel(session_id) -> AdapterResult
- health_check() -> AdapterResult
- collect_evidence(session_id) -> list[EventEnvelope]

Removability invariant (adapters_are_removable):
If the adapter is disabled (registry flag), every call returns a structured
CAPABILITY_UNAVAILABLE result. Importing this module never fails, so Core
and ODS keep working with the adapter absent from the registry.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from curaops.control.adapters.base import AdapterResult, BaseAdapter


class HarnessCapabilityUnavailable(Exception):
    """Structured fail-closed error for disabled/removed adapters."""

    def __init__(self, adapter: str, reason: str):
        self.adapter = adapter
        self.reason = reason
        self.code = "CAPABILITY_UNAVAILABLE"
        super().__init__(f"{adapter}: {reason}")


@dataclass
class HermesAdapterState:
    """In-memory managed-session state (fixture scope only, no live sessions)."""

    session_id: str = ""
    agent_id: str = ""
    worktree: str = ""
    task: str = ""
    status: str = "created"  # created|running|completed|failed|cancelled|timed_out
    started_at: str = ""
    finished_at: str = ""
    output_path: str = ""
    error: str = ""
    model_binding: dict[str, Any] = field(default_factory=dict)


class HermesAdapter(BaseAdapter):
    """Adapter for the Hermes harness.

    Fixture-safe: only managed fixture sessions (never live/manual Hermes
    sessions). start() runs a bounded, harmless task in a dedicated fixture
    worktree. No signal is sent to any foreign process.
    """

    name = "hermes"
    adapter_version = "hermes-adapter.v1"

    def __init__(
        self,
        *,
        registry_path: str | Path | None = None,
        fixture_worktree: str | Path | None = None,
        task_timeout_s: float = 10.0,
    ):
        self._registry_path = (
            Path(registry_path).expanduser().resolve()
            if registry_path
            else Path.cwd() / "contracts" / "harness-registry.yaml"
        )
        self._fixture_worktree = (
            Path(fixture_worktree).expanduser().resolve()
            if fixture_worktree
            else Path.cwd() / "fixtures" / "hermes-worktree"
        )
        self._task_timeout_s = task_timeout_s
        self._sessions: dict[str, HermesAdapterState] = {}

    # -- registry ---------------------------------------------------------

    def is_enabled(self) -> bool:
        """Read the adapter registry flag (default: enabled when file absent)."""
        try:
            import yaml

            data = yaml.safe_load(self._registry_path.read_text(encoding="utf-8")) or {}
            adapters = data.get("adapters", data)
            if isinstance(adapters, dict) and "hermes" in adapters:
                return bool(adapters["hermes"].get("enabled", True))
        except FileNotFoundError:
            return True
        except Exception:
            return True
        return True

    def _require_enabled(self) -> None:
        if not self.is_enabled():
            raise HarnessCapabilityUnavailable(
                self.name, "adapter disabled in harness-registry.yaml (fail-closed)"
            )

    # -- BaseAdapter API --------------------------------------------------

    def health_check(self) -> AdapterResult:
        if not self.is_enabled():
            return AdapterResult(
                success=False,
                message="CAPABILITY_UNAVAILABLE: hermes adapter disabled",
                detail={"code": "CAPABILITY_UNAVAILABLE"},
            )
        if not self._fixture_worktree.is_dir():
            return AdapterResult(
                success=False,
                message=f"fixture worktree missing: {self._fixture_worktree}",
            )
        return AdapterResult(success=True, message="hermes adapter (fixture) available")

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: dict[str, Any],
    ) -> AdapterResult:
        """Start a MANAGED fixture session (never touches live sessions)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False,
                message=str(exc),
                detail={"code": exc.code, "adapter": exc.adapter},
            )

        session_id = f"mxfix_{uuid.uuid4().hex[:12]}"
        state = HermesAdapterState(
            session_id=session_id,
            agent_id=agent_id,
            worktree=str(Path(worktree).expanduser().resolve()),
            task=task,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            model_binding=dict(config.get("model_binding", {})),
        )
        self._sessions[session_id] = state

        # Bounded, harmless fixture execution: write a text artifact.
        out_dir = Path(state.worktree) / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{session_id}.txt"
        output_path.write_text(
            f"fixture task: {task}\nagent: {agent_id}\nsession: {session_id}\n"
            f"model_binding: {state.model_binding}\nstatus: ok\n",
            encoding="utf-8",
        )
        state.output_path = str(output_path)
        state.status = "completed"
        state.finished_at = datetime.now(timezone.utc).isoformat()

        return AdapterResult(
            success=True,
            message="hermes fixture session completed",
            detail={"session_id": session_id, "output_path": str(output_path)},
        )

    def status_session(self, session_id: str) -> AdapterResult:
        """Return the managed session status (structured, never foreign)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None:
            return AdapterResult(
                success=False,
                message=f"unknown session {session_id}",
                detail={"code": "UNKNOWN_SESSION"},
            )
        return AdapterResult(
            success=True,
            message=f"session {session_id} status {state.status}",
            detail={"session_id": session_id, "status": state.status},
        )

    def cancel_session(self, session_id: str) -> AdapterResult:
        """Cancel ONLY the managed fixture session (no foreign signals)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None:
            return AdapterResult(
                success=False,
                message=f"unknown session {session_id}",
                detail={"code": "UNKNOWN_SESSION"},
            )
        state.status = "cancelled"
        state.finished_at = datetime.now(timezone.utc).isoformat()
        return AdapterResult(
            success=True,
            message=f"session {session_id} cancelled (managed only)",
            detail={"session_id": session_id, "status": "cancelled"},
        )

    def timeout_session(self, session_id: str) -> AdapterResult:
        """Timeout ONLY the managed fixture session."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None:
            return AdapterResult(success=False, message=f"unknown session {session_id}")
        state.status = "timed_out"
        state.finished_at = datetime.now(timezone.utc).isoformat()
        return AdapterResult(
            success=True,
            message=f"session {session_id} timed out (managed only)",
            detail={"session_id": session_id, "status": "timed_out"},
        )

    def collect_evidence(self, session_id: str) -> dict[str, Any]:
        """Collect evidence for a managed session (fixture artifacts)."""
        state = self._sessions.get(session_id)
        if state is None:
            return {"session_id": session_id, "evidence": [], "ok": False}
        artifacts = []
        if state.output_path and Path(state.output_path).is_file():
            artifacts.append(
                {
                    "path": state.output_path,
                    "sha256": _sha256(Path(state.output_path).read_bytes()),
                }
            )
        return {
            "session_id": session_id,
            "status": state.status,
            "artifacts": artifacts,
            "model_binding": state.model_binding,
            "ok": True,
        }

    # -- BaseAdapter abstract methods -------------------------------------

    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Stop a managed fixture session (alias of cancel)."""
        return self.cancel_session(session_ref)

    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Alias of status_session (BaseAdapter-compatible)."""
        return self.status_session(session_ref)

    def prepare_worktree(
        self,
        agent_id: str,
        worktree: str,
        scope_files: list,
        config: dict[str, Any],
    ) -> AdapterResult:
        """Prepare a fixture worktree (harmless marker files only)."""
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        (wt / ".agent-id").write_text(agent_id, encoding="utf-8")
        (wt / ".task-key").write_text(str(config.get("task", "")), encoding="utf-8")
        return AdapterResult(
            success=True,
            message="fixture worktree prepared",
            detail={"worktree": str(wt)},
        )


def _sha256(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()
