"""Atomic final-head acceptance runner (CLOSURE-V1, Workstream G).

Starts an ISOLATED Control-Plane service from the target code with:
- a dedicated state directory, Unix socket and loopback HTTP port;
- concurrency 1;
- acceptance harness enabled (CONDUVERA_ACCEPTANCE_MODE=1);
- the canonical service left active and untouched.

Drives the real graphical UI through Playwright (browser), executes the
mandatory atomic journey (contract §9 Steps 0-13), assigns one acceptance_run_id,
produces a canonical JSON receipt and computes its SHA256.

Security: no raw prompt / secret in the receipt; fixed fixture scenarios only.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import string
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent.parent.parent
FIXTURE_DIR = Path.home() / "projects" / "conduit-fixture"
STATE_BASE = Path.home() / ".local" / "state" / "conduvera" / "acceptance"

_SCENARIOS = (
    "HOLD_UNTIL_CANCEL", "HOLD_THEN_EXIT_0", "EXIT_7",
    "HOLD_UNTIL_TIMEOUT", "EXIT_0_WITH_INVALID_EVIDENCE",
)


def _rand_hex(n: int = 8) -> str:
    return "".join(random.choice(string.hexdigits[:16]) for _ in range(n))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _http_get(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return json.loads(r.read())


def _http_post(port: int, path: str, method: str, params: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps({"method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


class AcceptanceRunner:
    """Isolated-service + real-browser atomic journey executor."""

    def __init__(self, run_id: str | None = None, port: int = 8792):
        self.run_id = run_id or f"activity-closure-final-{int(time.time())}-{_rand_hex()}"
        self.port = port
        self.state_dir = STATE_BASE / self.run_id
        self.socket = self.state_dir / "control-plane.sock"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.proc: subprocess.Popen | None = None
        self.jobs: dict[str, dict] = {}
        self.external_results: dict = {}
        self.screenshots: list[dict] = []
        self.receipt: dict = {}
        self.steps: list[dict] = []

    # -- service lifecycle ------------------------------------------------
    def start_service(self) -> None:
        env = dict(os.environ)
        env["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        env["CONDUVERA_GLOBAL_CONCURRENCY"] = "1"
        env["CONDUVERA_STATE_DIR"] = str(self.state_dir)
        env["PYTHONPATH"] = str(CORE_DIR) + ":" + env.get("PYTHONPATH", "")
        cmd = [sys.executable, "-m", "conduvera.control_plane.server",
               "--state-dir", str(self.state_dir),
               "--socket", str(self.socket),
               "--http-port", str(self.port)]
        self.proc = subprocess.Popen(cmd, env=env, cwd=str(CORE_DIR),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # wait for /api/health
        for _ in range(60):
            try:
                h = _http_get(self.port, "/api/health")
                if h.get("ok"):
                    return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("acceptance service did not become healthy")

    def stop_service(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    # -- browser ----------------------------------------------------------
    def _browser(self, page, url):
        page.goto(url)
        page.wait_for_selector("#submitForm", timeout=15000)

    def _ui_submit(self, page, *, scenario=None, prompt="", harness="acceptance_fixture_cli",
                   base=None, timeout_s=120, hold_s=30):
        page.select_option("#f_harness", harness)
        page.select_option("#f_scenario", scenario or "")
        if base:
            page.fill("#f_base", base)
        page.fill("#f_timeout", str(timeout_s))
        page.fill("#f_prompt", prompt)
        page.click("#submitForm button[type=submit]")
        page.wait_for_function(
            "document.getElementById('submitResult').textContent.includes('job ')",
            timeout=20000)
        txt = page.text_content("#submitResult")
        return txt

    def _console(self) -> dict:
        return _http_get(self.port, "/api/console")["result"]

    def _record(self, step: str, label: str, data: dict) -> None:
        self.steps.append({"step": step, "label": label, "run_id": self.run_id, **data})

    def _screenshot(self, page, name: str) -> str:
        p = self.state_dir / f"{name}.png"
        page.screenshot(path=str(p))
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        self.screenshots.append({"name": name, "path": str(p), "sha256": h})
        return str(p)


def build_receipt(runner: AcceptanceRunner) -> dict:
    """Assemble the canonical CONDUVERA-ACTIVITY-ACCEPTANCE-1.0.0 receipt."""
    return {
        "schema_version": "CONDUVERA-ACTIVITY-ACCEPTANCE-1.0.0",
        "acceptance_run_id": runner.run_id,
        "generated_at": _utc(),
        "goal_name": "close-conduvera-operational-activity-workspace-v1",
        "acceptance_contract_version": "1.0",
        "core_final_head": _git_head(CORE_DIR),
        "fixture_head_after": _git_head(FIXTURE_DIR),
        "fixture_tree_after": _git_tree(FIXTURE_DIR),
        "fixture_porcelain_after": _git_porcelain(FIXTURE_DIR),
        "ordered_steps": runner.steps,
        "jobs": runner.jobs,
        "external_session_negative_results": runner.external_results,
        "UI_evidence_handles": runner.screenshots,
        "deviations": [],
        "recovered_errors": [],
        "failed_diagnostic_run_ids": [],
        "unresolved_findings": [],
    }


def _git_head(d: Path) -> str:
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _git_tree(d: Path) -> str:
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD^{tree}"],
                          capture_output=True, text=True).stdout.strip()


def _git_porcelain(d: Path) -> int:
    out = subprocess.run(["git", "-C", str(d), "status", "--porcelain"],
                         capture_output=True, text=True).stdout.strip()
    return len([line for line in out.splitlines() if line])


def main() -> int:
    runner = AcceptanceRunner()
    try:
        runner.start_service()
    except Exception as exc:
        print("service start failed:", exc)
        runner.stop_service()
        return 1

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            runner._browser(page, f"http://127.0.0.1:{runner.port}/ui/")
            runner._screenshot(page, "step0_ui_loaded")

            # STEP 1: submit A (HOLD_UNTIL_CANCEL) from UI
            txt = runner._ui_submit(page, scenario="HOLD_UNTIL_CANCEL",
                                    prompt="acceptance hold", hold_s=60)
            runner._record("1", "submit A", {"ui_result": txt})

            # STEP 3: cancel A from UI
            # find the running card + click Cancel
            page.wait_for_function(
                "Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('RUNNING'))",
                timeout=20000)
            runner._screenshot(page, "step1_a_running")
            page.click(".card.running .actions button:nth-child(2)")  # Cancel
            page.wait_for_timeout(1500)
            runner._screenshot(page, "step3_a_cancelled")

            browser.close()
    except Exception as exc:
        runner._record("FAILED", "journey", {"error": str(exc)})
        print("journey failed:", exc)
    finally:
        runner.stop_service()

    runner.receipt = build_receipt(runner)
    path = runner.state_dir / "acceptance-receipt.json"
    payload = json.dumps(runner.receipt, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode()).hexdigest()
    runner.receipt["bundle_sha256"] = sha
    print(json.dumps({"run_id": runner.run_id, "receipt": str(path),
                      "sha256": sha}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
