"""Control plane daemon — Unix-socket JSON API (localhost-only).

Serves the ControlPlaneService over a Unix domain socket with a JSON-RPC-like
protocol:

  request:  {"method": "...", "params": {...}}
  response: {"ok": true, "result": {...}} | {"ok": false, "error": {...}}

Methods: doctor, health, start, list, inspect, cancel, cleanup, reconcile,
capabilities, stop.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any

from conduvera.control_plane.service import ControlPlaneService


class ControlPlaneDaemon:
    """Minimal persistent Unix-socket daemon (single-connection, thread-safe)."""

    def __init__(
        self,
        *,
        service: ControlPlaneService,
        socket_path: str | Path,
    ):
        self.service = service
        self.socket_path = Path(socket_path)
        self._server: socket.socket | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self._server.listen(16)
        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

    def serve_forever(self) -> None:
        assert self._server is not None
        while self._running:
            try:
                conn, _ = self._server.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            data = b""
            conn.settimeout(30)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 1024 * 1024:
                    break
                if data.rstrip().endswith(b"}"):
                    break
            if not data.strip():
                return
            req = json.loads(data.decode("utf-8"))
            response = self._dispatch(req)
            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - protocol error response
            try:
                conn.sendall(json.dumps({
                    "ok": False, "error": {"code": "PROTOCOL_ERROR",
                                           "message": str(exc)}}).encode("utf-8"))
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, req: dict[str, Any]) -> dict[str, Any]:
        method = req.get("method", "")
        params = req.get("params", {}) or {}
        with self._lock:
            if method == "doctor":
                return {"ok": True, "result": self.service.doctor()}
            if method == "health":
                return {"ok": True, "result": {"status": "ok",
                                               "state_dir": str(self.service.config.state_dir)}}
            if method == "start":
                r = self.service.start(**params)
                return {"ok": r.get("success", False), "result": r}
            if method == "submit":
                r = self.service.submit_job(**params)
                return {"ok": r.get("success", False), "result": r}
            if method == "queue":
                return {"ok": True, "result": {
                    "attempts": [a.to_dict()
                                 for a in self.service.scheduler.store.all_attempts()],
                    "jobs": [j.to_dict()
                             for j in self.service.scheduler.store.all_jobs()],
                }}
            if method == "console":
                return {"ok": True, "result": self.service.console_view(
                    limit=params.get("limit"))}
            if method == "list":
                return {"ok": True, "result": {"sessions": self.service.list_sessions(),
                                               "jobs": self.service.list_jobs()}}
            if method == "inspect":
                r = self.service.status(params.get("session_id", ""))
                return {"ok": r.get("success", False), "result": r}
            if method == "cancel":
                r = self.service.cancel(params.get("session_id", ""))
                return {"ok": r.get("success", False), "result": r}
            if method == "cleanup":
                r = self.service.cleanup(params.get("session_id", ""))
                return {"ok": r.get("success", False), "result": r}
            if method == "retry":
                r = self.service.retry_job(params.get("job_id", ""),
                                           params.get("attempt_id"),
                                           idempotency_key=params.get("idempotency_key"))
                return {"ok": r.get("success", False), "result": r}
            if method == "reconcile":
                return {"ok": True, "result": self.service.reconcile()}
            if method == "observe_external":
                r = self.service.observe_external(pid=params.get("pid", 0),
                                                  label=params.get("label", ""),
                                                  classification=params.get(
                                                      "classification", "EXTERNAL_UNKNOWN"))
                return {"ok": r.get("success", False), "result": r}
            # ---- Delivery domain (SHIP-CONDUVERA-DELIVERY) ----
            if method == "delivery_list":
                return {"ok": True, "result": {"deliveries": self.service.delivery.list()}}
            if method == "delivery_inspect":
                rec = self.service.delivery.get(params.get("delivery_id", ""))
                if rec is None:
                    return {"ok": False, "result": {
                        "success": False, "code": "UNKNOWN_DELIVERY",
                        "message": "unknown delivery"}}
                return {"ok": True, "result": {
                    "success": True, "record": rec,
                    "history": self.service.delivery.history(rec["delivery_id"])}}
            if method == "delivery_preflight":
                try:
                    r = self.service.delivery.preflight(params.get("job_or_delivery", ""))
                except Exception as exc:  # noqa: BLE001 - surface structured error
                    import traceback
                    traceback.print_exc()
                    return {"ok": False, "result": {"ok": False,
                            "reasons": [{"code": "DELIVERY_ERROR", "message": str(exc)}]}}
                return {"ok": r["ok"], "result": r}
            if method == "delivery_publish":
                r = self.service.delivery.publish(
                    params.get("job_or_delivery", ""),
                    base_branch=params.get("base_branch", "main"),
                    force=bool(params.get("force", False)))
                return {"ok": r.get("ok", False), "result": r}
            if method == "delivery_sync":
                r = self.service.delivery.sync(params.get("job_or_delivery", ""))
                return {"ok": r.get("ok", False), "result": r}
            if method == "delivery_cleanup":
                r = self.service.delivery.cleanup(
                    params.get("job_or_delivery", ""),
                    safe_only=params.get("safe_only", True))
                return {"ok": r.get("ok", False), "result": r}
            if method == "capabilities":
                return {"ok": True, "result": self.service.capabilities(
                    params.get("harness", "hermes"))}
            if method == "stop":
                threading.Thread(target=self.stop, daemon=True).start()
                return {"ok": True, "result": {"stopping": True}}
            return {"ok": False, "error": {"code": "UNKNOWN_METHOD",
                                           "message": method}}
