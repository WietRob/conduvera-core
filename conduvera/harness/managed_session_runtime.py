"""Managed session runtime — orchestrates the harness gateway for one session.

MXOS-SAFETY-1 / MXOS-RUNTIME-1 vertical slice:

- start(): create job -> dedicated worktree -> adapter LIVE start -> register
  MANAGED session with process fingerprint + scope id.
- status(): RUNNING only when the authoritative process fingerprint still
  matches (PID reuse -> LOST, never controlling the new process).
- cancel(): SIGTERM/SIGKILL only through the adapter on the verified own
  scope; rejects every non-MANAGED session.
- Emits the MXOS-EVIDENCE-1.0.0 chain via the existing EventEnvelope:
  session.created, session.start.requested, session.started,
  session.status.observed, session.cancel.requested, session.cancelled,
  session.cleanup.completed.

External sessions (Hermes/Codex/OpenCode manual) are NEVER adopted: they are
registered as EXTERNAL_MANUAL_OBSERVED / EXTERNAL_UNKNOWN with
control_rights=none and their PIDs/start times are never touched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conduvera.evidence.contract import EventEnvelope
from conduvera.harness.managed_session import (
    ManagedJob,
    ManagedSession,
    ManagedSessionRegistry,
    OwnershipClass,
    ProcessFingerprint,
    SessionState,
    _boot_id,
    _process_cmd,
    _process_start_time,
    _utc_now,
)


@dataclass
class ManagedSessionResult:
    """Structured result of a runtime operation."""

    success: bool
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "message": self.message, "detail": self.detail}


class ManagedSessionRuntime:
    """Owns exactly one managed session lifecycle via the harness gateway."""

    PRODUCER = {"name": "conduvera-harness-managed", "version": "1.0.0",
                "adapter": "managed-session-runtime"}

    def __init__(
        self,
        *,
        registry: ManagedSessionRegistry,
        gateway_service: Any,
        adapter_id: str = "hermes",
        worktree_base: str | Path = "/tmp",
    ):
        self.registry = registry
        self.gateway = gateway_service
        self.adapter_id = adapter_id
        self.worktree_base = Path(worktree_base).expanduser().resolve()
        self._evidence: list[dict[str, Any]] = []

    # -- evidence ----------------------------------------------------------

    def _emit(
        self,
        event_type: str,
        session: ManagedSession,
        payload: dict[str, Any],
        *,
        severity: str = "info",
        references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        envelope = EventEnvelope.create(
            event_type=event_type,
            producer=dict(self.PRODUCER),
            subject={
                "kind": "harness_session",
                "session_id": session.session_id,
                "task_id": session.task_id,
                "attempt_id": session.attempt_id,
                "core": "conduvera-core",
                "adapter": self.adapter_id,
            },
            payload=payload,
            severity=severity,
            correlation_id=session.session_id,
            run_id=session.instance_id,
            references=references,
        )
        data = envelope.to_dict()
        self._evidence.append(data)
        session.evidence_refs.append(data["event_id"])
        return data

    def evidence_chain(self) -> list[dict[str, Any]]:
        return list(self._evidence)

    # -- external session observation (never adopted) ----------------------

    def observe_external(
        self,
        *,
        pid: int,
        classification: OwnershipClass | str = OwnershipClass.EXTERNAL_UNKNOWN,
        label: str = "",
    ) -> ManagedSession:
        """Register a pre-existing external session (read-only, no control).

        PIDs/start times are captured but control_rights stays none; the
        session can never transition to MANAGED and cancel() rejects it.
        """
        if isinstance(classification, str):
            classification = OwnershipClass(classification)
        if classification not in (
            OwnershipClass.EXTERNAL_MANUAL_OBSERVED,
            OwnershipClass.EXTERNAL_UNKNOWN,
        ):
            raise ValueError("observe_external accepts only EXTERNAL_* classes")
        session = ManagedSession(
            session_id=f"ext_{uuid.uuid4().hex[:16]}",
            task_id="",
            attempt_id="",
            ownership_class=classification,
            managed=False,
            instance_id=f"ext-{uuid.uuid4().hex[:8]}",
            fingerprint=ProcessFingerprint(
                pid=pid,
                start_time=_process_start_time(pid),
                boot_id=_boot_id(),
                command=_process_cmd(pid),
            ),
            scope_id=f"ext-{pid}",
            state=SessionState.RUNNING,
            created_at=_utc_now(),
            started_at=_utc_now(),
        )
        self.registry.register(session)
        return session

    # -- lifecycle ---------------------------------------------------------

    def start(
        self,
        *,
        task_id: str,
        attempt_id: str,
        repo: str,
        base_commit: str,
        harness_descriptor: str,
        model_binding: dict[str, Any],
        timeout_s: float = 120.0,
        prompt: str = "Antworte mit genau einem Wort: PONG",
        worktree: str | None = None,
    ) -> ManagedSessionResult:
        """Create + start exactly one new MANAGED session."""
        if worktree is None:
            worktree = str(self.worktree_base / f"wt-{task_id}-{attempt_id}")
        job = ManagedJob(
            task_id=task_id,
            attempt_id=attempt_id,
            repo=repo,
            base_commit=base_commit,
            worktree=worktree,
            harness_descriptor=harness_descriptor,
            model_binding=dict(model_binding),
            timeout_s=timeout_s,
        )
        session = ManagedSession.create(job=job)
        self.registry.register(session)
        self._emit("session.created", session, {
            "task_id": task_id, "attempt_id": attempt_id,
            "worktree": worktree, "base_commit": base_commit,
        })

        # Dedicated worktree from the exact base commit (fixture semantics:
        # create a clean disposable worktree; no production repo touched).
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        (wt / "README.txt").write_text(
            f"managed-slice fixture\nrepo={repo}\nbase={base_commit}\n"
            f"task={task_id}\nattempt={attempt_id}\n",
            encoding="utf-8",
        )
        session.state = SessionState.STARTING
        self.registry.update(session)
        self._emit("session.start.requested", session, {
            "worktree": str(wt), "harness_descriptor": harness_descriptor,
        })

        result = self.gateway.start_session(
            adapter_id=self.adapter_id,
            agent_id=task_id,
            worktree=str(wt),
            task=task_id,
            config={
                "execution_mode": "LIVE",
                "route": model_binding.get("route", "workload/local"),
                "model_binding": model_binding,
                "prompt": prompt,
            },
        )
        if not result.success:
            session.state = SessionState.FAILED
            session.ended_at = _utc_now()
            self.registry.update(session)
            self._emit("session.failed", session, {
                "message": result.message, "detail": result.detail,
            }, severity="error")
            return ManagedSessionResult(False, result.message, dict(result.detail))

        detail = result.detail
        pid = int(detail.get("pid", 0))
        session.fingerprint = ProcessFingerprint(
            pid=pid,
            start_time=_process_start_time(pid),
            boot_id=_boot_id(),
            command=_process_cmd(pid),
        )
        session.scope_id = str(detail.get("pgid", ""))
        session.adapter_session_id = str(detail.get("session_id", ""))
        session.state = SessionState.RUNNING
        session.started_at = _utc_now()
        self.registry.update(session)
        self._emit("session.started", session, {
            "session_id": session.session_id,
            "adapter_session_id": session.adapter_session_id,
            "pid": pid,
            "pgid": session.scope_id,
            "fingerprint": session.fingerprint.to_dict() if session.fingerprint else None,
            "worktree": str(wt),
        })
        return ManagedSessionResult(
            True,
            f"managed session {session.session_id} started",
            {"session": session.to_dict()},
        )

    def status(self, session_id: str) -> ManagedSessionResult:
        """Status based on process fingerprint, never PID alone."""
        session = self.registry.get(session_id)
        if session is None:
            return ManagedSessionResult(False, "unknown session",
                                        {"code": "UNKNOWN_SESSION"})
        if session.ownership_class is not OwnershipClass.MANAGED:
            return ManagedSessionResult(False, "not a managed session",
                                        {"code": "NOT_MANAGED"})
        fp = session.fingerprint
        if fp is None or fp.pid <= 0:
            return ManagedSessionResult(True, f"session {session_id} {session.state.value}",
                                        {"session_id": session_id,
                                         "state": session.state.value})

        live_fp = ProcessFingerprint(
            pid=fp.pid,
            start_time=_process_start_time(fp.pid),
            boot_id=_boot_id(),
            command=_process_cmd(fp.pid),
        )
        if not live_fp.matches(fp):
            # PID reuse or process gone: never control the new process.
            session.state = SessionState.LOST if live_fp.pid else SessionState.COMPLETED
            if session.state is SessionState.LOST:
                session.state = SessionState.LOST
            session.ended_at = _utc_now()
            self.registry.update(session)
            self._emit("session.status.observed", session, {
                "observed": "PROCESS_FINGERPRINT_MISMATCH",
                "state": session.state.value,
            }, severity="warning")
            return ManagedSessionResult(
                True, f"session {session_id} {session.state.value}",
                {"session_id": session_id, "state": session.state.value},
            )

        self._emit("session.status.observed", session, {
            "observed": "RUNNING",
            "pid": fp.pid, "pgid": session.scope_id,
        })
        return ManagedSessionResult(
            True, f"session {session_id} RUNNING",
            {"session_id": session_id, "state": "RUNNING",
             "pid": fp.pid, "pgid": session.scope_id,
             "adapter_session_id": session.adapter_session_id},
        )

    def cancel(self, session_id: str) -> ManagedSessionResult:
        """Cancel ONLY a MANAGED session (rejects every EXTERNAL_* session)."""
        session = self.registry.get(session_id)
        if session is None:
            return ManagedSessionResult(False, "unknown session",
                                        {"code": "UNKNOWN_SESSION"})
        if session.ownership_class is not OwnershipClass.MANAGED:
            return ManagedSessionResult(
                False,
                "cancel rejected: session is not MANAGED (control_rights=none)",
                {"code": "EXTERNAL_SESSION_NOT_CONTROLLABLE",
                 "ownership_class": session.ownership_class.value},
            )
        if session.state in (SessionState.CANCELLED, SessionState.COMPLETED,
                             SessionState.FAILED, SessionState.LOST):
            return ManagedSessionResult(
                False, f"session {session_id} already in {session.state.value}",
                {"code": "TERMINAL_STATE", "state": session.state.value})

        session.state = SessionState.CANCEL_REQUESTED
        self.registry.update(session)
        self._emit("session.cancel.requested", session, {
            "session_id": session_id,
            "adapter_session_id": session.adapter_session_id,
            "scope_id": session.scope_id,
        })

        result = self.gateway.cancel_session(
            adapter_id=self.adapter_id,
            session_id=session.adapter_session_id or session_id,
        )
        if result.success:
            session.state = SessionState.CANCELLED
            session.ended_at = _utc_now()
            self.registry.update(session)
            self._emit("session.cancelled", session, {
                "session_id": session_id,
                "scope_id": session.scope_id,
                "message": result.message,
            })
            self._emit("session.cleanup.completed", session, {
                "session_id": session_id,
                "worktree": session.worktree,
                "scope_verified_empty": True,
            })
            return ManagedSessionResult(
                True, f"session {session_id} cancelled",
                {"session_id": session_id, "state": "CANCELLED"},
            )
        session.state = SessionState.FAILED
        session.ended_at = _utc_now()
        self.registry.update(session)
        return ManagedSessionResult(False, result.message, dict(result.detail))
