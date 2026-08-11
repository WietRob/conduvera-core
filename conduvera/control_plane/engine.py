"""Daemon-owned scheduler dispatcher + monitor loops (BUILDROOM-PILOT-V1).

Dispatcher loop:
- deterministic FIFO dispatch within priority class;
- atomic claim/lease before dispatch (exactly one owner);
- queued attempts start automatically when capacity becomes available;
- expired claims return safely to the queue;
- restart-safe recovery of queued/claimed/running attempts.

Monitor loop:
- polls harness/session status;
- detects normal completion and actual exit code;
- distinguishes completed/failed/cancelled/timed_out/lost;
- synchronizes Job, Attempt and Session state;
- emits lifecycle events exactly once;
- enforces the declared timeout automatically:
  deadline -> session.timeout.requested -> SIGTERM to owned scope
  -> grace period -> SIGKILL to the same scope;
- releases scheduler capacity after every terminal path;
- triggers the next queued attempt.

Both loops are owned by the daemon; a human never has to invoke
`systemctl kill` or a manual reconcile for normal operation.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conduvera.control_plane.scheduler import (
    AttemptState,
    JobState,
    Scheduler,
    _utc_now,
)
from conduvera.harness.managed_session import (
    ManagedSessionRegistry,
    SessionState,
    _process_start_time,
)


class ControlPlaneEngine:
    """Owns the dispatcher + monitor loops and their shared state access."""

    def __init__(
        self,
        *,
        service: Any,
        scheduler: Scheduler,
        registry: ManagedSessionRegistry,
        claim_lease_s: float = 300.0,
        poll_interval_s: float = 2.0,
        timeout_grace_s: float = 3.0,
        dispatcher_id: str = "pilot-dispatcher",
    ):
        self.service = service
        self.scheduler = scheduler
        self.registry = registry
        self.claim_lease_s = claim_lease_s
        self.poll_interval_s = poll_interval_s
        self.timeout_grace_s = timeout_grace_s
        self.dispatcher_id = dispatcher_id
        self._running = False
        self._stop = threading.Event()
        self._dispatch_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        # set of session_ids already emitted as terminal (exactly-once events)
        self._emitted_terminal: set[str] = set()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._stop.clear()
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop, name="conduvera-dispatcher", daemon=True)
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="conduvera-monitor", daemon=True)
        self._dispatch_thread.start()
        self._monitor_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop.set()

    # -- dispatcher loop ---------------------------------------------------

    def _dispatch_loop(self) -> None:
        """FIFO dispatch: claim -> start -> capacity release on terminal."""
        while self._running:
            try:
                self._dispatch_once()
            except Exception:  # noqa: BLE001 - daemon loop must survive
                pass
            self._stop.wait(self.poll_interval_s)

    def _dispatch_once(self) -> None:
        """One dispatch pass (loop body, testable directly)."""
        # recover expired claims first (restart-safe)
        self.scheduler.recover_expired_claims(self.claim_lease_s)
        # FIFO within priority class: QUEUED attempts by created_at
        queued = sorted(
            self.scheduler.queued_attempts(),
            key=lambda a: a.created_at,
        )
        for attempt in queued:
            if not self._running:
                return
            harness = attempt.harness
            can, _reason = self.scheduler.can_start(harness)
            if not can:
                continue  # capacity full — wait for monitor release
            claimed = self.scheduler.claim(
                attempt.attempt_id, lease_s=self.claim_lease_s,
                dispatcher_id=self.dispatcher_id)
            if claimed is None:
                continue  # another dispatcher won the race
            self.service.dispatch_claimed(claimed.attempt_id)

    # -- monitor loop ------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Poll sessions, enforce deadlines, release capacity, emit events."""
        while self._running:
            try:
                self._monitor_once()
            except Exception:  # noqa: BLE001 - daemon loop must survive
                pass
            self._stop.wait(self.poll_interval_s)

    def _monitor_once(self) -> None:
        for session in list(self.registry.all()):
            if not self._running:
                return
            # external sessions are never monitored/controlled
            from conduvera.harness.managed_session import OwnershipClass
            if session.ownership_class is not OwnershipClass.MANAGED:
                continue
            sid = session.session_id
            attempt = self.scheduler.store.get_attempt(session.attempt_id) \
                if session.attempt_id else None
            if attempt is not None and attempt.terminal:
                continue  # already terminal — capacity already released
            if session.state in (SessionState.CANCELLED, SessionState.FAILED,
                                 SessionState.LOST):
                # session already terminal (e.g. cancel raced the monitor):
                # mark attempt terminal truthfully, never overwrite.
                if attempt is not None and not attempt.terminal:
                    self._finalize_attempt_from_session(session, attempt)
                continue

            fp = session.fingerprint
            if fp is None or fp.pid <= 0:
                continue

            # 1) process liveness via fingerprint
            live = self._live(fp)
            if live is None:
                # process gone: normal completion or failure
                self._handle_process_gone(session, attempt, sid)
                continue

            # 2) deadline enforcement (timeout)
            if session.timeout_s and session.started_at:
                try:
                    started = datetime.fromisoformat(session.started_at)
                    elapsed = (datetime.now(timezone.utc) - started.replace(
                        tzinfo=timezone.utc)).total_seconds()
                except ValueError:
                    elapsed = 0.0
                if elapsed > session.timeout_s:
                    self._handle_timeout(session, attempt, sid)
                    continue

            # 3) running status observed
            if session.state is not SessionState.RUNNING:
                session.state = SessionState.RUNNING
                self.registry.update(session)
            self.service.emit_observed(sid, fp)

    def _finalize_attempt_from_session(self, session: Any, attempt: Any) -> None:
        """Mark the attempt terminal matching an already-terminal session state.

        Never overwrites a terminal attempt; used when cancel/cleanup raced
        the monitor so the queue state stays truthful (CANCELLED stays
        CANCELLED, not silently COMPLETED).
        """
        from conduvera.control_plane.scheduler import AttemptState as AS
        from conduvera.control_plane.scheduler import JobState as JS
        mapping = {
            SessionState.CANCELLED: (AS.CANCELLED, JS.CANCELLED),
            SessionState.FAILED: (AS.FAILED, JS.FAILED),
            SessionState.LOST: (AS.FAILED, JS.FAILED),
            SessionState.COMPLETED: (AS.COMPLETED, JS.COMPLETED),
        }
        pair = mapping.get(session.state)
        if pair is None:
            return
        attempt_state, job_state = pair
        attempt.state = attempt_state
        attempt.terminal = True
        attempt.terminal_reason = f"session {session.state.value}"
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        job = self.scheduler.store.get_job(attempt.job_id)
        if job is not None:
            job.state = job_state
            job.terminal_reason = f"session {session.state.value}"
            job.updated_at = _utc_now()
            self.scheduler.store.save_job(job)
        self._emitted_terminal.add(session.session_id)

    def _live(self, fp: Any) -> Any:
        start = _process_start_time(fp.pid)
        if not start:
            return None
        if start != fp.start_time:
            return "reused"
        # A zombie (state Z) is a dead process whose parent has not reaped it
        # yet — classify as gone, never as running.
        try:
            stat = Path(f"/proc/{fp.pid}/stat").read_text()
            state = stat.split(")")[1].strip().split()[0] if ")" in stat else ""
            if state == "Z":
                return None
        except (OSError, IndexError):
            return None
        return "alive"

    # -- terminal handling -------------------------------------------------

    def _finalize(
        self, session: Any, attempt: Any, sid: str,
        session_state: SessionState, attempt_state: AttemptState,
        job_state: JobState, reason: str, exit_code: int | None = None,
        event_type: str | None = None,
    ) -> None:
        if sid in self._emitted_terminal:
            return  # exactly-once
        session.state = session_state
        session.ended_at = _utc_now()
        self.registry.update(session)
        if attempt is not None and not attempt.terminal:
            attempt.state = attempt_state
            attempt.terminal = True
            attempt.terminal_reason = reason
            attempt.exit_code = exit_code
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job = self.scheduler.store.get_job(attempt.job_id)
            if job is not None:
                job.state = job_state
                job.terminal_reason = reason
                job.exit_code = exit_code
                job.updated_at = _utc_now()
                self.scheduler.store.save_job(job)
        self._emitted_terminal.add(sid)
        if event_type:
            self.service.emit(event_type, {
                "session_id": sid, "task_id": session.task_id,
                "attempt_id": session.attempt_id, "reason": reason,
                "exit_code": exit_code})
        # capacity released -> dispatcher picks the next queued attempt

    def _handle_process_gone(self, session: Any, attempt: Any, sid: str) -> None:
        exit_code = None
        if session.adapter_session_id:
            try:
                ev = self.service.gateway.collect_evidence(
                    adapter_id=session.harness_descriptor or "hermes",
                    session_id=session.adapter_session_id)
                if isinstance(ev, dict) and ev.get("exit_code") is not None:
                    exit_code = int(ev["exit_code"])
            except Exception:  # noqa: BLE001
                pass
        if exit_code is not None and exit_code != 0:
            self._finalize(
                session, attempt, sid,
                SessionState.FAILED, AttemptState.FAILED, JobState.FAILED,
                f"process exited with code {exit_code}", exit_code,
                "session.failed")
            return
        self._finalize(
            session, attempt, sid,
            SessionState.COMPLETED, AttemptState.COMPLETED, JobState.COMPLETED,
            "process exited normally", exit_code, "session.completed")

    def _handle_timeout(self, session: Any, attempt: Any, sid: str) -> None:
        # session.timeout.requested -> SIGTERM -> grace -> SIGKILL
        self.service.emit("session.timeout.requested", {
            "session_id": sid, "task_id": session.task_id,
            "attempt_id": session.attempt_id, "timeout_s": session.timeout_s})
        scope = session.scope_id
        if scope and scope.endswith(".scope"):
            subprocess.run(
                ["systemctl", "--user", "kill", scope, "-s", "SIGTERM"],
                capture_output=True, text=True, timeout=15)
        else:
            try:
                os.killpg(int(session.fingerprint.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        time.sleep(self.timeout_grace_s)
        if scope and scope.endswith(".scope"):
            subprocess.run(
                ["systemctl", "--user", "kill", scope, "-s", "SIGKILL"],
                capture_output=True, text=True, timeout=15)
        else:
            try:
                os.killpg(int(session.fingerprint.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        self._finalize(
            session, attempt, sid,
            SessionState.FAILED, AttemptState.TIMED_OUT, JobState.TIMED_OUT,
            "timeout: SIGTERM -> grace -> SIGKILL applied", None,
            "session.timed_out")
