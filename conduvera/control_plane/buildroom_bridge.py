"""Buildroom bridge — narrow integration with the Conduvera control plane.

Buildroom submits a JOB to the control plane (daemon socket) instead of
spawning the harness directly. The control plane routes (router), selects
the harness and model binding, runs the job and returns task/attempt/session
identifiers, status and evidence.

The legacy direct Buildroom execution path remains available behind the
explicit rollback flag `legacy_direct=True`.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from conduvera.control_plane.service import ControlPlaneConfig
from conduvera.harness.router import DeterministicRouter, NoRouteError


class BuildroomBridge:
    """Client-side bridge used by Buildroom to submit jobs."""

    def __init__(
        self,
        *,
        socket_path: str | Path | None = None,
        router: DeterministicRouter | None = None,
        legacy_direct: bool = False,
    ):
        self.socket_path = str(socket_path or ControlPlaneConfig.default().socket_path)
        self.router = router or DeterministicRouter()
        self.legacy_direct = legacy_direct

    def _call(self, method: str, params: dict | None = None) -> dict[str, Any]:
        if not Path(self.socket_path).exists():
            return {"ok": False, "error": {"code": "SERVICE_DOWN",
                                           "message": f"control plane not running ({self.socket_path})"}}
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(30)
            sock.connect(self.socket_path)
            sock.sendall(json.dumps({"method": method, "params": params or {}}).encode("utf-8"))
            data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
            return json.loads(data.decode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": {"code": "SERVICE_ERROR", "message": str(exc)}}
        finally:
            sock.close()

    def submit(
        self,
        *,
        task_id: str,
        attempt_id: str,
        task_class: str = "fixture",
        prompt: str,
        repo: str = "conduvera-core",
        base_commit: str = "",
        timeout_s: float = 120.0,
        override_harness: str | None = None,
    ) -> dict[str, Any]:
        """Route + submit one job through the control plane."""
        if self.legacy_direct:
            # Legacy direct path: no routing, no control plane (rollback flag).
            return {"ok": True, "legacy_direct": True, "task_id": task_id,
                    "attempt_id": attempt_id,
                    "message": "legacy direct execution (rollback path)"}
        try:
            decision = self.router.route(
                task_id=task_id, task_class=task_class, timeout_s=timeout_s,
                override_harness=override_harness,
            )
        except NoRouteError as exc:
            return {"ok": False, "error": {"code": "NO_ROUTE", "message": exc.reason}}
        params = {
            "task_id": task_id, "attempt_id": attempt_id,
            "harness": decision.harness,
            "repo": repo, "base_commit": base_commit,
            "model_binding": decision.model_binding.to_dict(),
            "prompt": prompt, "timeout_s": timeout_s,
        }
        result = self._call("submit", params)
        if result.get("ok") and result.get("result", {}).get("success"):
            rres = result.get("result", {})
            attempt_id = rres.get("attempt_id", attempt_id)
            session = rres.get("session", {})
            # The daemon queues the attempt; the session is created later by
            # the dispatcher. Resolve the session id from the queue state.
            if not session and attempt_id:
                q = self._call("queue")
                for a in q.get("result", {}).get("attempts", []):
                    if a.get("attempt_id") == attempt_id and a.get("session_id"):
                        session = {"session_id": a["session_id"]}
                        break
            return {
                "ok": True,
                "task_id": task_id, "attempt_id": attempt_id,
                "harness": decision.harness,
                "job_id": rres.get("job_id", ""),
                "session": session,
                "queued": rres.get("queued", True),
                "route_decision": decision.to_dict(),
            }
        return result

    def status(self, session_id: str) -> dict[str, Any]:
        return self._call("inspect", {"session_id": session_id})

    def cancel(self, session_id: str) -> dict[str, Any]:
        return self._call("cancel", {"session_id": session_id})

    def evidence(self, session_id: str) -> dict[str, Any]:
        return self._call("inspect", {"session_id": session_id})

    def wait_terminal(
        self,
        session_id: str,
        timeout_s: float = 300.0,
        poll_interval_s: float = 3.0,
        attempt_id: str = "",
    ) -> dict[str, Any]:
        """Synchronous wait/poll until the session reaches a terminal state.

        If session_id is empty but attempt_id is given, the session id is
        resolved from the queue state once it is created by the dispatcher.

        Returns the normalized EvidenceBundle (task/attempt/session IDs,
        lifecycle state, terminal result, exit code, harness/model binding,
        worktree/base-commit binding, artifact references).
        """
        import time as _time
        deadline = _time.monotonic() + timeout_s
        resolved = session_id
        while _time.monotonic() < deadline:
            if not resolved and attempt_id:
                q = self._call("queue")
                for a in q.get("result", {}).get("attempts", []):
                    if a.get("attempt_id") == attempt_id and a.get("session_id"):
                        resolved = a["session_id"]
                        break
                if not resolved:
                    _time.sleep(poll_interval_s)
                    continue
            st = self.status(resolved)
            state = st.get("result", {}).get("state", "")
            if state in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"):
                return self.build_bundle(resolved, state)
            _time.sleep(poll_interval_s)
        return {"ok": False, "error": {"code": "WAIT_TIMEOUT",
                                       "message": f"session {session_id or attempt_id} not terminal within {timeout_s}s"}}

    def build_bundle(self, session_id: str, terminal_state: str) -> dict[str, Any]:
        """Normalized EvidenceBundle for one terminal session."""
        lst = self._call("list")
        session = next((s for s in lst.get("result", {}).get("sessions", [])
                        if s.get("session_id") == session_id), None)
        q = self._call("queue")
        attempts = {a["attempt_id"]: a for a in q.get("result", {}).get("attempts", [])}
        jobs = {j["job_id"]: j for j in q.get("result", {}).get("jobs", [])}
        attempt = attempts.get((session or {}).get("attempt_id", ""), {})
        job = jobs.get(attempt.get("job_id", ""), {})
        return {
            "ok": True,
            "schema_version": "MXOS-EVIDENCE-1.0.0",
            "task_id": (session or {}).get("task_id", ""),
            "job_id": job.get("job_id", ""),
            "attempt_id": (session or {}).get("attempt_id", ""),
            "session_id": session_id,
            "lifecycle_state": terminal_state,
            "terminal_reason": attempt.get("terminal_reason", ""),
            "exit_code": attempt.get("exit_code"),
            "harness": (session or {}).get("harness_descriptor", ""),
            "model_binding": (session or {}).get("model_binding", {}),
            "worktree": (session or {}).get("worktree", ""),
            "base_commit": (session or {}).get("base_commit", ""),
            "scope_id": (session or {}).get("scope_id", ""),
            "artifact_refs": attempt.get("result_refs", []),
            "evidence_ref": f"conduvera://session/{session_id}/evidence",
        }
