"""Minimal HTTP bridge for the Control-Plane Activity workspace.

A Browser cannot speak the Unix-socket JSON protocol directly, so this module
exposes the SAME service records and dispatch path over plain HTTP on a
local-only TCP port. It is a pure adapter: it calls the identical
ControlPlaneDaemon._dispatch() used by the Unix socket, so there is exactly
one state authority and one code path for every method.

Endpoints (JSON):
  GET  /api/health                    -> health
  GET  /api/console                   -> console_view (activity records)
  GET  /api/console?limit=N           -> console_view, newest-first, capped
  POST /api/action                    -> body {"method": "...", "params": {...}}
  GET  /ui/                           -> static activity.html (workspace)
  GET  /ui/<asset>                    -> static asset under conduvera/ui/

Security: binds loopback only. No auth (local operator surface); never echoes
raw prompts or secrets (all responses come from service redaction).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class _Handler(BaseHTTPRequestHandler):
    # silence default stderr logging
    def log_message(self, *args: Any) -> None:  # noqa: ARG002
        pass

    @property
    def _bridge(self) -> "HttpBridge":
        return self.server.bridge  # type: ignore[attr-defined]

    def _send_json(self, obj: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel: str, status: int = 200) -> None:
        # normalize and forbid path traversal
        rel = rel.lstrip("/")
        target = (_UI_DIR / rel).resolve()
        if not target.is_relative_to(_UI_DIR.resolve()) or not target.is_file():
            self._send_json({"ok": False, "error": {"code": "NOT_FOUND",
                                                    "message": rel}}, 404)
            return
        ctype = "text/html" if target.suffix == ".html" else \
                "application/javascript" if target.suffix == ".js" else \
                "text/css" if target.suffix == ".css" else "application/octet-stream"
        data = target.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _stream_events(self, qs: str) -> None:
        """SSE event stream with Last-Event-ID resume and heartbeat."""
        last_id = 0
        for kv in qs.split("&"):
            if kv.startswith("last_event_id="):
                try:
                    last_id = int(kv.split("=", 1)[1])
                except ValueError:
                    last_id = 0
        bus = getattr(self._bridge, "event_bus", None)
        if bus is None:
            self._send_json({"ok": False, "error": {"code": "NO_EVENT_BUS"}}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                events = bus.events_since(last_id)
                for e in events:
                    self.wfile.write(self._sse_line(e))
                    last_id = e["id"]
                self.wfile.flush()
                if not events:
                    events = bus.wait_for_events(last_id, timeout=10.0)
                    if not events:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:  # noqa: BLE001 - close stream on error
            return

    def _sse_line(self, event: dict) -> bytes:
        import json as _json
        lines = [f"id: {event['id']}", f"event: {event['event']}"]
        lines.append(f"data: {_json.dumps(event.get('data') or {}, sort_keys=True)}")
        return ("\n".join(lines) + "\n\n").encode("utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        qs = self.path.split("?")[1] if "?" in self.path else ""
        if path == "/api/health":
            self._send_json({"ok": True, "status": "ok"})
        elif path == "/api/events":
            self._stream_events(qs)
        elif path == "/api/console":
            limit = None
            if qs:
                for kv in qs.split("&"):
                    if kv.startswith("limit="):
                        try:
                            limit = int(kv.split("=", 1)[1])
                        except ValueError:
                            limit = None
            params = {"limit": limit} if limit else {}
            resp = self._bridge.dispatch("console", params)
            self._send_json(resp)
        elif path == "/" or path == "/ui":
            self._send_static("activity.html")
        elif path.startswith("/ui/"):
            rel = path[len("/ui/"):]
            if not rel or rel.endswith("/"):
                rel = "activity.html"
            self._send_static(rel)
        else:
            self._send_json({"ok": False, "error": {"code": "NOT_FOUND",
                                                    "message": path}}, 404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, json.JSONDecodeError):
            self._send_json({"ok": False, "error": {"code": "BAD_JSON"}}, 400)
            return
        method = body.get("method", "")
        params = body.get("params", {}) or {}
        if not method:
            self._send_json({"ok": False, "error": {"code": "MISSING_METHOD"}}, 400)
            return
        try:
            resp = self._bridge.dispatch(method, params)
        except Exception as exc:  # noqa: BLE001 - never drop the connection
            self._send_json({"ok": False, "error": {"code": "DISPATCH_ERROR",
                                                    "message": str(exc)}}, 500)
            return
        self._send_json(resp)


class HttpBridge:
    """HTTP adapter over the control-plane daemon's single dispatch path."""

    def __init__(self, daemon: Any, port: int = 8791,
                 bind: str = "127.0.0.1") -> None:
        self.daemon = daemon
        self.port = port
        self.bind = bind
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def event_bus(self):
        """Expose the control-plane event stream bus for SSE (WS-F)."""
        svc = getattr(self.daemon, "service", None)
        if svc is None:
            return None
        return getattr(svc, "event_bus", None)

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req: dict[str, Any] = {"method": method, "params": params}
        return self.daemon._dispatch(req)

    def start(self) -> None:
        server = ThreadingHTTPServer((self.bind, self.port), _Handler)
        server.bridge = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever,
                                        daemon=True, name="http-bridge")
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
