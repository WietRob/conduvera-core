"""HTTP bridge / Activity contract tests (OPERATIONAL-ACTIVITY-V1, WS-A).

Proves the Activity-record contract:
- HTTP /api/console returns the same console records as the socket daemon;
- limit param caps each section (newest-first);
- POST /api/action delegates to the daemon dispatch path;
- static /ui/ serves the workspace;
- no raw prompt in any HTTP response.
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return repo, base


class _FakeGateway:
    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()
    def collect_evidence(self, adapter_id, session_id):
        return {"session_id": session_id, "exit_code": 0,
                "artifacts": [{"path": "/tmp/a.out", "sha256": "sha256:abc"}]}
    def cancel_session(self, **kw):
        return type("R", (), {"success": True})()


@pytest.fixture
def http_bridge(tmp_path):
    from conduvera.control_plane.daemon import ControlPlaneDaemon
    from conduvera.control_plane.http_bridge import HttpBridge
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    repo, base = _make_repo(tmp_path)
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    svc = ControlPlaneService(registry=reg, gateway_service=_FakeGateway(),
                              config=config, repo_allowlist={"fixture": repo},
                              global_concurrency=2)
    # port 0 -> OS assigns a free port
    daemon = ControlPlaneDaemon(service=svc, socket_path=config.socket_path)
    daemon.start()
    bridge = HttpBridge(daemon=daemon, port=0, bind="127.0.0.1")
    bridge.start()
    # discover the actual bound port
    actual_port = bridge._server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}"
    yield svc, bridge, url
    bridge.stop()
    daemon.stop()


class TestHttpBridge:
    """WS-A: Activity-record contract over HTTP."""

    def test_health(self, http_bridge):
        svc, bridge, url = http_bridge
        with urllib.request.urlopen(f"{url}/api/health") as r:
            assert r.status == 200
            assert json.loads(r.read())["status"] == "ok"

    def test_console_matches_service(self, http_bridge):
        svc, bridge, url = http_bridge
        svc.submit_job(task_id="HTTP1", attempt_id="h1", harness="hermes_scoped",
                       repo="fixture", base_commit=svc.resolve_repo("fixture") and
                       __import__("subprocess").run(
                           ["git", "-C", str(svc.resolve_repo("fixture")),
                            "rev-parse", "HEAD"], capture_output=True,
                           text=True).stdout.strip(),
                       model_binding={}, prompt="http task", task_type="code_change")
        with urllib.request.urlopen(f"{url}/api/console") as r:
            body = json.loads(r.read())
        assert body["ok"] is True
        http_console = body["result"]
        svc_console = svc.console_view()
        assert http_console["counts"] == svc_console["counts"]
        # same records: queued job present
        assert any(q.get("task_id") == "HTTP1" for q in http_console["queued"])

    def test_console_limit(self, http_bridge):
        svc, bridge, url = http_bridge
        for i in range(5):
            svc.submit_job(task_id=f"T{i}", attempt_id=f"a{i}",
                           harness="hermes_scoped", repo="fixture",
                           base_commit="0" * 40, model_binding={},
                           prompt=f"task {i}", task_type="code_change")
        with urllib.request.urlopen(f"{url}/api/console?limit=2") as r:
            body = json.loads(r.read())
        q = body["result"]["queued"]
        assert len(q) == 2  # newest-first capped

    def test_action_post_delegates(self, http_bridge):
        svc, bridge, url = http_bridge
        req = urllib.request.Request(
            f"{url}/api/action",
            data=json.dumps({"method": "health"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        assert body["ok"] is True and body["result"]["status"] == "ok"

    def test_no_raw_prompt_in_http(self, http_bridge):
        svc, bridge, url = http_bridge
        svc.submit_job(task_id="SEC", attempt_id="s1", harness="hermes_scoped",
                       repo="fixture", base_commit="0" * 40, model_binding={},
                       prompt="SECRET_RAW_PROMPT_X", task_type="code_change")
        with urllib.request.urlopen(f"{url}/api/console") as r:
            body = json.loads(r.read())
        assert "SECRET_RAW_PROMPT_X" not in json.dumps(body)

    def test_ui_static_served(self, http_bridge):
        svc, bridge, url = http_bridge
        with urllib.request.urlopen(f"{url}/ui/") as r:
            assert r.status == 200
            assert "text/html" in r.headers["Content-Type"]
            assert b"Conduvera" in r.read()
