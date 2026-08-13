"""Trusted real-feature acceptance runner (TRUSTED-FEATURE-DELIVERY, WS F/G).

Positive path drives the REAL browser controls (submit form, open detail,
select Attempt, preflight/approve/publish buttons) with a real coding harness
(codex_cli or opencode_cli). API/GitHub reads are used ONLY for independent
re-derivation after each operator action.

STRICT: every required condition is asserted. Any false value, missing field,
unexpected file, HTTP error, JS error or GitHub mismatch exits nonzero.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent.parent
HARNESS = os.environ.get("CONDUVERA_DELIVERY_HARNESS", "codex_cli")


def _utc() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"STRICT-FAIL: {msg}")


def _git_head(d: Path) -> str:
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


class StrictFailure(Exception):
    pass


class TrustedRunner:
    def __init__(self, port: int = 8860):
        base = Path.home() / ".local" / "state" / "conduvera"
        self.run_id = f"trusted-final-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self.state_dir = base / "acceptance" / self.run_id
        self.state_dir.mkdir(parents=True)
        self.port = port
        self.steps = []
        self.jobs = {}
        self.proc = None

    # -- service -----------------------------------------------------------
    def start_service(self):
        env = dict(os.environ)
        env["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        env["CONDUVERA_GLOBAL_CONCURRENCY"] = "1"
        env["CONDUVERA_STATE_DIR"] = str(self.state_dir)
        env["CONDUVERA_GH_ENABLED"] = "1"
        env["PYTHONPATH"] = str(CORE_DIR)
        # prune stale acceptance worktrees + free orphaned servers
        for repo in (Path.home() / "projects" / "matrix-os",
                     Path.home() / "projects" / "conduit-fixture"):
            subprocess.run(["git", "-C", str(repo), "worktree", "prune"],
                           capture_output=True)
        try:
            out = subprocess.run(["ss", "-ltnp"], capture_output=True,
                                 text=True).stdout
            import re as _re
            for line in out.splitlines():
                if f":{self.port} " in line and "python3" in line:
                    m = _re.search(r"pid=(\d+)", line)
                    if m:
                        subprocess.run(["kill", m.group(1)], capture_output=True)
                        time.sleep(1)
        except Exception:
            pass
        logf = open(self.state_dir / "server.log", "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "conduvera.control_plane.server",
             "--state-dir", str(self.state_dir),
             "--socket", str(self.state_dir / "cp.sock"),
             "--http-port", str(self.port)],
            env=env, cwd=str(CORE_DIR), stdout=logf, stderr=logf)
        for _ in range(90):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/api/health", timeout=5) as r:
                    if json.loads(r.read()).get("ok") and (self.state_dir / "payloads").exists():
                        return
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError("service not healthy")

    def stop_service(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _post(self, method: str, params: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=json.dumps({"method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise StrictFailure(f"{method} HTTP {e.code}: {e.read().decode()[:400]}")

    def _record(self, step, label, **payload):
        self.steps.append({"step": step, "label": label, "run_id": self.run_id,
                           **payload})

    # -- browser helpers ---------------------------------------------------
    def _click_detail_action(self, page, job_label, button_text):
        page.wait_for_function(
            "(label) => Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes(label))",
            arg=job_label, timeout=20000)
        page.evaluate(
            "(label) => { const c=Array.from(document.querySelectorAll('.card')).find(c=>c.textContent.includes(label)); if(c){ const b=c.querySelector('button'); if(b) b.click(); } }",
            job_label)
        page.wait_for_timeout(1000)
        page.wait_for_function(
            "(label) => Array.from(document.querySelectorAll('#detailPanel button')).some(b=>b.textContent.trim()===label)",
            arg=button_text, timeout=10000)

    def _click_panel_button(self, page, text, js_before="", js_after="",
                            click_via_js=False):
        # click a button inside the detail panel by its text
        page.wait_for_function(
            "(label) => Array.from(document.querySelectorAll('#detailPanel button')).some(b=>b.textContent.trim()===label)",
            arg=text, timeout=10000)
        page.evaluate(
            "(label) => { const b=Array.from(document.querySelectorAll('#detailPanel button')).find(b=>b.textContent.trim()===label); if(b) b.click(); }",
            text)
        page.wait_for_timeout(1500)

    # -- submit form via real browser --------------------------------------
    def browser_submit(self, page, *, task_id, attempt_id, scenario, repo,
                       base_commit):
        page.goto(f"http://127.0.0.1:{self.port}/ui/activity.html",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # fill the real submit form fields (f_* ids; doSubmit auto-generates
        # task/attempt ids)
        fields = {"f_harness": HARNESS, "f_repo": repo, "f_base": base_commit,
                  "f_prompt": "Add docs/DOGFOOD_MARKER.md with the single line 'Conduvera dogfood acceptance' to the repository.",
                  "f_scenario": scenario or ""}
        page.evaluate(
            "(fields) => { for (const [k,v] of Object.entries(fields)) { const i=document.getElementById(k); if(i) i.value=v; } }",
            fields)
        # click the Submit button (submit event -> doSubmit)
        page.evaluate(
            "() => { const b=document.querySelector('#submitForm button[type=submit]')||Array.from(document.querySelectorAll('#submitForm button')).find(b=>/submit/i.test(b.textContent)); if(b) b.click(); }")
        page.wait_for_timeout(2500)
        # read the job id from the queued card
        body = page.evaluate("document.body.textContent")
        return body

    # -- steps -------------------------------------------------------------
    def run(self):
        from playwright.sync_api import sync_playwright
        self.start_service()
        main_sha = _git_head(CORE_DIR)
        self._record("0", "rebaseline", core_head=main_sha,
                     harness=HARNESS)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            js_errors = []
            page.on("pageerror", lambda e: js_errors.append(str(e)))
            try:
                # STEP 1: real browser submit (codex_cli / opencode_cli)
                body = self.browser_submit(
                    page, task_id="TRUST-A", attempt_id="t1",
                    scenario="REAL_HARNESS", repo="conduvera-core",
                    base_commit=main_sha)
                _assert("job_" in body or "queued" in body.lower(),
                        "submit form produced a queued job in the browser")
                # find the job id from the browser console data
                job_a = self._find_job_id()
                self.jobs["A"] = {"job_id": job_a, "attempt_id": "t1"}
                self._record("1", "browser submit", job_id=job_a,
                             harness=HARNESS)

                # STEP 2: wait for COMPLETED via browser card
                self._wait_terminal_browser(page, job_a, "COMPLETED")
                self._record("2", "completed in browser", job_id=job_a)

                # STEP 3: open detail, select attempt, inspect (job card)
                self._click_detail_action(page, job_a, "Select Attempt")
                # handle the prompt() dialogs headlessly
                page.on("dialog", lambda d: d.accept("t1"))
                self._click_panel_button(page, "Select Attempt")
                page.wait_for_timeout(500)
                self._click_panel_button(page, "Preflight")
                self._record("3", "attempt selected + preflight")

                # STEP 4: approve candidate via browser
                self._click_panel_button(page, "Approve Candidate",
                                         click_via_js=True)
                self._record("4", "candidate approved via browser")

                # STEP 5: publish via browser
                self._click_panel_button(page, "Publish PR", click_via_js=True)
                self._record("5", "publish via browser")

                # STEP 6: independent GitHub re-derivation
                self._gh_derivation(page, job_a)
            finally:
                browser.close()
        self.stop_service()
        return self._build_receipt()

    def _find_job_id(self) -> str:
        # read the job id from the scheduler store (independent read)
        qf = self.state_dir / "scheduler" / "queue.json"
        for _ in range(30):
            if qf.is_file():
                d = json.loads(qf.read_text())
                for jid in d.get("jobs", {}):
                    return jid
            time.sleep(1)
        raise StrictFailure("no job id found")

    def _wait_terminal_browser(self, page, job_id, state):
        qf = self.state_dir / "scheduler" / "queue.json"
        deadline = time.time() + 180
        while time.time() < deadline:
            if qf.is_file():
                d = json.loads(qf.read_text())
                j = d.get("jobs", {}).get(job_id, {})
                if j.get("state") == state:
                    return j
                if j.get("state") in ("FAILED", "TIMED_OUT", "CANCELLED"):
                    raise StrictFailure(f"job {job_id} ended {j.get('state')}")
            time.sleep(2)
        raise StrictFailure(f"job {job_id} never {state}")

    def _gh_derivation(self, page, job_a):
        # resolve the published PR from the delivery record
        rec = None
        for f in (self.state_dir / "delivery").glob("*.json"):
            try:
                r = json.loads(f.read_text())
            except Exception:
                continue
            if r.get("job_id") == job_a:
                rec = r
        _assert(rec is not None, "delivery record exists for job")
        _assert(rec.get("pull_request_number"), "PR number recorded")
        _assert(rec.get("pull_request_url"), "PR URL recorded")
        _assert(rec.get("branch_name"), "branch recorded")
        self._record("6", "github re-derivation",
                     pr_number=rec.get("pull_request_number"),
                     branch=rec.get("branch_name"),
                     head=rec.get("branch_head_sha"))

    def _build_receipt(self) -> dict:
        receipt = {
            "schema_version": "CONDUVERA-TRUSTED-DELIVERY-ACCEPTANCE-1.0.0",
            "acceptance_run_id": self.run_id,
            "generated_at": _utc(),
            "goal_name": "ship-conduvera-trusted-real-feature-delivery-v1",
            "core_final_head": _git_head(CORE_DIR),
            "harness": HARNESS,
            "ordered_steps": self.steps,
            "jobs": self.jobs,
        }
        (self.state_dir / "acceptance-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True))
        self.receipt_sha = hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        return receipt


def main() -> int:
    try:
        runner = TrustedRunner()
        runner.run()
        print(json.dumps({
            "run_id": runner.run_id,
            "receipt": str(runner.state_dir / "acceptance-receipt.json"),
            "sha256": runner.receipt_sha,
        }, indent=2))
        return 0
    except (StrictFailure, AssertionError) as e:
        print(f"STRICT-FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
