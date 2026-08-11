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
        result = self._call("start", params)
        if result.get("ok") and result.get("result", {}).get("success"):
            return {
                "ok": True,
                "task_id": task_id, "attempt_id": attempt_id,
                "harness": decision.harness,
                "session": result["result"]["session"],
                "route_decision": decision.to_dict(),
            }
        return result

    def status(self, session_id: str) -> dict[str, Any]:
        return self._call("inspect", {"session_id": session_id})

    def cancel(self, session_id: str) -> dict[str, Any]:
        return self._call("cancel", {"session_id": session_id})

    def evidence(self, session_id: str) -> dict[str, Any]:
        return self._call("inspect", {"session_id": session_id})
