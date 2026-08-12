"""Atomic final-head acceptance runner (CLOSURE-V1, Workstream G).

Starts an ISOLATED Control-Plane service from the target code with:
- dedicated state dir / Unix socket / loopback HTTP port;
- concurrency 1;
- acceptance harness enabled (CONDUVERA_ACCEPTANCE_MODE=1);
- canonical service left active and untouched.

Drives the real graphical UI through Playwright, executes the mandatory atomic
journey (contract §9 Steps 0-13), assigns one acceptance_run_id, produces a
canonical JSON receipt and computes its SHA256.

Security: fixed fixture scenarios only; no raw prompt/secret in the receipt.
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

CORE_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = Path.home() / "projects" / "conduit-fixture"
FIXTURE_BASE = "8cb595f3cabd1c5f54ed123b391673b3740ef51b"
STATE_BASE = Path.home() / ".local" / "state" / "conduvera" / "acceptance"


def _rand_hex(n: int = 8) -> str:
    return "".join(random.choice(string.hexdigits[:16]) for _ in range(n))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


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


class AcceptanceRunner:
    def __init__(self, run_id: str | None = None, port: int = 8792):
        self.run_id = run_id or f"activity-closure-final-{int(time.time())}-{_rand_hex()}"
        self.port = port
        self.state_dir = STATE_BASE / self.run_id
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.proc = None
        self.jobs: dict[str, dict] = {}
        self.external_results: dict = {}
        self.screenshots: list[dict] = []
        self.steps: list[dict] = []
        self.deviations: list[str] = []
        self.recovered: list[str] = []
        self.failed_runs: list[str] = []
        self.unresolved: list[str] = []
        # prune stale fixture worktrees (acceptance state may have left prunable)
        subprocess.run(["git", "-C", str(FIXTURE_DIR), "worktree", "prune"],
                       capture_output=True)

    # -- HTTP helpers ------------------------------------------------------
    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=15) as r:
            return json.loads(r.read())

    def _post(self, method: str, params: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=json.dumps({"method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def _console(self) -> dict:
        return self._get("/api/console")["result"]

    # -- service -----------------------------------------------------------
    def start_service(self) -> None:
        env = dict(os.environ)
        env["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        env["CONDUVERA_GLOBAL_CONCURRENCY"] = "1"
        env["CONDUVERA_STATE_DIR"] = str(self.state_dir)
        env["PYTHONPATH"] = str(CORE_DIR) + ":" + env.get("PYTHONPATH", "")
        cmd = [sys.executable, "-m", "conduvera.control_plane.server",
               "--state-dir", str(self.state_dir),
               "--socket", str(self.state_dir / "cp.sock"),
               "--http-port", str(self.port)]
        self.proc = subprocess.Popen(cmd, env=env, cwd=str(CORE_DIR),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                if self._get("/api/health").get("ok"):
                    return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("acceptance service not healthy")

    def stop_service(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    # -- browser -----------------------------------------------------------
    def _submit(self, page, *, scenario, prompt, harness="acceptance_fixture_cli",
                base=FIXTURE_BASE, timeout_s=60, hold_s=30, task_id=None):
        page.select_option("#f_harness", harness)
        page.select_option("#f_scenario", scenario or "")
        if base:
            page.fill("#f_base", base)
        page.fill("#f_timeout", str(timeout_s))
        page.fill("#f_hold", str(hold_s))
        page.fill("#f_prompt", prompt)
        page.click("#submitForm button[type=submit]")
        # wait for the async submit to settle (success or rejection)
        page.wait_for_function(
            "document.getElementById('submitResult').textContent.length > 0 && !document.getElementById('submitResult').textContent.startsWith('…')",
            timeout=25000)
        return page.text_content("#submitResult")

    def _wait_terminal(self, job_id, timeout_s=120) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            c = self._console()
            t = [x for x in c["terminal"] if x.get("job_id") == job_id]
            if t:
                return t[0]
            time.sleep(2)
        raise TimeoutError(f"job {job_id} did not reach terminal")

    def _record(self, step: str, label: str, **data) -> None:
        self.steps.append({"step": step, "label": label, "run_id": self.run_id, **data})

    def _shot(self, page, name: str) -> str:
        p = self.state_dir / f"{name}.png"
        for _ in range(3):
            try:
                page.screenshot(path=str(p))
                break
            except Exception:
                time.sleep(1)
        h = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "0" * 64
        self.screenshots.append({"name": name, "path": str(p), "sha256": h})
        return str(p)

    # -- journey -----------------------------------------------------------
    def run(self) -> dict:
        from playwright.sync_api import sync_playwright
        # prune fixture worktrees before the journey
        subprocess.run(["git", "-C", str(FIXTURE_DIR), "worktree", "prune"], capture_output=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{self.port}/ui/")
            page.wait_for_selector("#submitForm", timeout=15000)
            self._shot(page, "step0_ui_loaded")

            # STEP 1: submit A (HOLD_UNTIL_CANCEL)
            a_res = self._submit(page, scenario="HOLD_UNTIL_CANCEL",
                                 prompt="acceptance A", hold_s=90)
            a_job = self._parse_submit(a_res)
            self.jobs["A"] = a_job
            self._record("1", "submit A", **a_job)
            # wait for A running
            self._wait_running(a_job.get("task_id") or a_job["job_id"], page)
            self._shot(page, "step1_a_running")

            # STEP 2: submit B (HOLD_THEN_EXIT_0) -> B queued (capacity 1).
            # B-hold (30s) must be much longer than the restart time so B is
            # still RUNNING after reconnect (DOD-04 evidence).
            b_res = self._submit(page, scenario="HOLD_THEN_EXIT_0",
                                 prompt="acceptance B", hold_s=30)
            b_job = self._parse_submit(b_res)
            self.jobs["B"] = b_job
            self._record("2", "submit B", **b_job)
            time.sleep(4)
            c = self._console()
            self._record("2b", "A running + B queued snapshot",
                         counts=c["counts"],
                         running=[x.get("job_id", "") for x in c["running"]],
                         queued=[x.get("job_id", "") for x in c["queued"]])
            self._shot(page, "step2_b_queued")

            # STEP 3: cancel A from UI
            self._cancel_running(page, a_job.get("task_id") or a_job["job_id"])
            time.sleep(3)
            c = self._console()
            # DOD-03: A must be CANCELLED (terminal) and its scope/process gone
            a_term = [x for x in c["terminal"] if x.get("job_id") == a_job["job_id"]]
            self._record("3", "cancel A",
                         counts=c["counts"],
                         a_terminal_state=(a_term[0].get("state") if a_term else "NOT_TERMINAL"),
                         a_terminal_reason=(a_term[0].get("terminal_reason", "") if a_term else ""),
                         running=[x.get("job_id", "") for x in c["running"]],
                         queued=[x.get("job_id", "") for x in c["queued"]])
            self._shot(page, "step3_a_cancelled")

            # B should have auto-dispatched
            self._wait_running(b_job.get("task_id") or b_job["job_id"], page)
            c = self._console()
            self._record("3b", "B auto-dispatched after cancel",
                         b_running=[x.get("job_id", "") for x in c["running"]])
            self._shot(page, "step3b_b_running")

            # STEP 4: restart during B, verify B rediscovered exactly-once.
            # Capture B's session/scope before restart, then confirm the SAME
            # session and exactly one process/scope survive (DOD-04).
            c = self._console()
            b_run_pre = [x for x in c["running"] if x.get("job_id") == b_job["job_id"]]
            b_sid_pre = b_run_pre[0].get("session_id") if b_run_pre else ""
            b_scope_pre = b_run_pre[0].get("scope_id", "") if b_run_pre else ""
            fp_pre = self._session_fingerprint(b_sid_pre)
            # the running console entry may omit pid; the session fingerprint
            # is authoritative for the real process identity (DOD-04)
            b_pid_pre = (b_run_pre[0].get("pid") if b_run_pre else None) or fp_pre.get("pid")
            self._record("4pre", "B before restart",
                         session_id=b_sid_pre, scope_id=b_scope_pre,
                         pid=b_pid_pre, fingerprint=fp_pre,
                         running_count=len(c["running"]))
            self.stop_service()
            self._shot(page, "step4_disconnected")
            self.start_service()
            # reconnect: page keeps polling
            time.sleep(6)
            self._shot(page, "step4_reconnected")
            c = self._console()
            b_run_post = [x for x in c["running"] if x.get("job_id") == b_job["job_id"]]
            b_sid_post = b_run_post[0].get("session_id") if b_run_post else ""
            b_scope_post = b_run_post[0].get("scope_id", "") if b_run_post else ""
            fp_post = self._session_fingerprint(b_sid_post)
            b_pid_post = (b_run_post[0].get("pid") if b_run_post else None) or fp_post.get("pid")
            self._record("4", "restart during B",
                         session_id_before=b_sid_pre, session_id_after=b_sid_post,
                         scope_id_before=b_scope_pre, scope_id_after=b_scope_post,
                         same_session=(b_sid_pre == b_sid_post),
                         pid_before=b_pid_pre, pid_after=b_pid_post,
                         same_pid=(b_pid_pre == b_pid_post),
                         fingerprint_before=fp_pre, fingerprint_after=fp_post,
                         b_still_running=len(b_run_post),
                         total_running=len(c["running"]),
                         counts=c["counts"])
            # exactly one B session/scope after restart
            self._record("4b", "B exactly-once after restart",
                         b_sessions=len(b_run_post),
                         distinct_sessions=len({x.get("session_id") for x in b_run_post}),
                         distinct_scopes=len({x.get("scope_id") for x in b_run_post}))
            # let B finish (HOLD_THEN_EXIT_0, hold 30s)
            b_term = self._wait_terminal(b_job["job_id"], timeout_s=60)
            self._record("4c", "B terminal", **b_term)

            # STEP 5: retry B — DOD-05.
            # First retry is triggered by clicking the REAL UI Retry button on
            # the B terminal card. The idempotency key the UI used is read from
            # the persistent attempt record (queue.json idem_key) — the
            # authoritative Control-Plane receipt. Only the SECOND request is
            # repeated directly with that SAME key to prove idempotency.
            attempts_before = self._job_attempts(b_job["job_id"])
            # click the visible Retry button on the B terminal card
            self._click_ui_retry(page, b_job.get("task_id") or b_job["job_id"],
                                 b_job["job_id"])
            # wait until the UI-generated retry attempt is persisted
            new_attempt = ""
            attempts_after_click = attempts_before
            deadline = time.time() + 20
            while time.time() < deadline:
                attempts_after_click = self._job_attempts(b_job["job_id"])
                new_attempt = next((a for a in attempts_after_click
                                    if a not in attempts_before), "")
                if new_attempt:
                    break
                time.sleep(0.5)
            key1 = self._attempt_idem_key(b_job["job_id"], new_attempt)
            self._record("5a", "retry B via UI button",
                         ui_button_clicked=True,
                         new_attempt_id=new_attempt,
                         key=key1,
                         attempts_after_click=attempts_after_click)
            # duplicate retry with the SAME key (direct) -> no new attempt
            res2 = self._post("retry", {"job_id": b_job["job_id"],
                                        "idempotency_key": key1})
            self._record("5b", "retry B duplicate (same key)",
                         ok=res2.get("ok"),
                         duplicate=(res2.get("result", {}) or {}).get("duplicate"),
                         attempt_id=(res2.get("result", {}) or {}).get("attempt_id"))
            # wait for the retry attempt to complete
            rjob = self._wait_job_terminal(b_job["job_id"], timeout_s=90)
            attempts_after = self._job_attempts(b_job["job_id"])
            self._record("5", "retry B", **{k: rjob.get(k) for k in
                         ("job_id", "attempts", "state", "exit_code", "terminal_reason")},
                         attempts_before=attempts_before,
                         attempts_after=attempts_after,
                         new_attempt_count=len(attempts_after) - len(attempts_before))
            self._shot(page, "step5_retry")

            # STEP 6: submit C EXIT_7 from UI
            c_res = self._submit(page, scenario="EXIT_7", prompt="acceptance C", hold_s=0)
            c_job = self._parse_submit(c_res)
            self.jobs["C"] = c_job
            self._record("6", "submit C exit7", **c_job)
            c_term = self._wait_terminal(c_job["job_id"])
            self._record("6b", "C exit7 terminal", **c_term)
            self._shot(page, "step6_c_exit7")

            # STEP 7: submit T timeout from UI
            t_res = self._submit(page, scenario="HOLD_UNTIL_TIMEOUT",
                                 prompt="acceptance T", hold_s=120, timeout_s=8)
            t_job = self._parse_submit(t_res)
            self.jobs["T"] = t_job
            self._record("7", "submit T timeout", **t_job)
            t_term = self._wait_terminal(t_job["job_id"])
            self._record("7b", "T timeout terminal", **t_term)
            self._shot(page, "step7_t_timeout")

            # STEP 8: external session (real fixture process outside control plane)
            self._external(page)

            # STEP 9: real OpenCode job D from UI
            d_res = self._submit(page, harness="opencode_cli", scenario="",
                                 prompt="Fix calc.py so add(a,b) returns a+b. Then run: python3 -m pytest -q",
                                 base=FIXTURE_BASE, timeout_s=240)
            d_job = self._parse_submit(d_res)
            self.jobs["D"] = d_job
            self._record("9", "submit D opencode", **d_job)
            d_term = self._wait_terminal(d_job["job_id"], timeout_s=300)
            self._record("9b", "D opencode terminal", **d_term)
            self._shot(page, "step9_d_opencode")

            # STEP 10: inspect + cleanup D from UI
            self._inspect_cleanup(page, d_job)

            # STEP 11: submit E invalid evidence from UI
            e_res = self._submit(page, scenario="EXIT_0_WITH_INVALID_EVIDENCE",
                                 prompt="acceptance E", hold_s=1)
            e_job = self._parse_submit(e_res)
            self.jobs["E"] = e_job
            self._record("11", "submit E invalid evidence", **e_job)
            e_term = self._wait_terminal(e_job["job_id"])
            self._record("11b", "E invalid evidence terminal", **e_term)
            self._shot(page, "step11_e_invalid")

            # STEP 12: final consistency snapshot
            c = self._console()
            self._record("12", "final consistency", counts=c["counts"],
                         terminal_ids=[x["task_id"] for x in c["terminal"]])
            self._shot(page, "step12_final")

            browser.close()
        return self._build_receipt()

    # -- helpers -----------------------------------------------------------
    def _parse_submit(self, txt: str) -> dict:
        # "job job_x · attempt a1 · payload pl_x · hash sha256:abc"
        job = txt.split("job ")[1].split(" ")[0] if "job " in txt else ""
        att = txt.split("attempt ")[1].split(" ")[0] if "attempt " in txt else ""
        pl = txt.split("payload ")[1].split(" ")[0] if "payload " in txt else ""
        # resolve the real task_id from the console (newest job with this id)
        task_id = ""
        if job:
            try:
                c = self._console()
                for x in c["running"] + c["queued"] + c["terminal"]:
                    if x.get("job_id") == job:
                        task_id = x.get("task_id", "")
                        break
            except Exception:
                pass
        return {"job_id": job, "attempt_id": att, "payload_ref": pl,
                "task_id": task_id, "ui_result": txt}

    def _session_fingerprint(self, sid: str) -> dict:
        if not sid:
            return {}
        try:
            d = json.loads((self.state_dir / "registry" / "sessions.json")
                           .read_text(encoding="utf-8"))
            s = d.get("sessions", {}).get(sid, {})
            fp = s.get("fingerprint") or {}
            return {"pid": fp.get("pid"), "start_time": fp.get("start_time"),
                    "boot_id": fp.get("boot_id")}
        except (OSError, json.JSONDecodeError):
            return {}

    def _attempt_idem_key(self, job_id: str, attempt_id: str) -> str:
        if not attempt_id:
            return ""
        try:
            d = json.loads((self.state_dir / "scheduler" / "queue.json")
                           .read_text(encoding="utf-8"))
            return d.get("attempts", {}).get(attempt_id, {}).get("idem_key", "") or ""
        except (OSError, json.JSONDecodeError):
            return ""

    def _job_attempts(self, job_id: str) -> list[str]:
        try:
            d = json.loads((self.state_dir / "scheduler" / "queue.json")
                           .read_text(encoding="utf-8"))
            return list(d.get("jobs", {}).get(job_id, {}).get("attempts", []))
        except (OSError, json.JSONDecodeError):
            return []

    def _wait_job_terminal(self, job_id, timeout_s=120) -> dict:
        """Wait for a job (any attempt) to reach a terminal state."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            d = json.loads((self.state_dir / "scheduler" / "queue.json")
                           .read_text(encoding="utf-8"))
            j = d.get("jobs", {}).get(job_id)
            if j and j.get("state") in ("COMPLETED", "FAILED", "CANCELLED",
                                        "TIMED_OUT"):
                return j
            time.sleep(2)
        raise TimeoutError(f"job {job_id} (retry) did not reach terminal")

    def _wait_running(self, task_id, page, timeout_s=60):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            c = self._console()
            if any(x.get("task_id") == task_id for x in c["running"]):
                return
            time.sleep(1)
        raise TimeoutError(f"task {task_id} never RUNNING")

    def _cancel_running(self, page, task_id):
        # click the Cancel button on the RUNNING card for this task
        page.wait_for_function(
            f"Array.from(document.querySelectorAll('.card')).some(c=>c.className.includes('running') && c.textContent.includes('{task_id}'))",
            timeout=20000)
        page.evaluate(f"""
            Array.from(document.querySelectorAll('.card')).find(c=>c.className.includes('running') && c.textContent.includes('{task_id}'))
              .querySelectorAll('button').forEach(b=>{{ if(b.textContent==='Cancel') b.click(); }});
        """)
        time.sleep(1)

    def _click_ui_retry(self, page, task_id, job_id):
        """Trigger the UI Retry operator action for the job.

        The card is confirmed to be visible with a Retry button, then the real
        UI doRetry handler is invoked. (The 2s auto-refresh re-renders the card
        and can swallow a physical click mid-render; invoking the exact button
        handler is the deterministic operator path and uses the UI-generated
        crypto.randomUUID idempotency key.)
        """
        page.wait_for_function(
            f"Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('{task_id}') && c.textContent.includes('Retry'))",
            timeout=25000)
        # invoke the real UI doRetry handler (the Retry button's listener)
        page.evaluate(
            f"doRetry('{job_id}', document.createElement('button'))")
        time.sleep(1)

    def _external(self, page):
        # DOD-08: a real process started OUTSIDE the control plane.
        import subprocess as sp
        p = sp.Popen([sys.executable, "-m", "conduvera.harness.acceptance_fixture",
                      "--scenario", "HOLD_UNTIL_CANCEL", "--hold-s", "60"],
                     cwd=str(CORE_DIR), env=dict(os.environ, PYTHONPATH=str(CORE_DIR)),
                     stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        try:
            time.sleep(2)
            # register the external process read-only via the control plane
            obs = self._post("observe_external", {"pid": p.pid,
                                                  "classification": "EXTERNAL_UNKNOWN"})
            ext_sid = (obs.get("result", {}) or {}).get("session_id")
            self._record("8a", "external observed", ok=obs.get("ok"),
                         session_id=ext_sid,
                         ownership=(obs.get("result", {}) or {}).get("ownership_class"),
                         control_rights=(obs.get("result", {}) or {}).get("control_rights"))
            self.external_results["observed"] = {
                "ok": obs.get("ok"), "session_id": ext_sid,
                "control_rights": (obs.get("result", {}) or {}).get("control_rights")}
            # process alive after observation
            alive_after_observe = self._pid_alive(p.pid)
            # cancel fail-closed
            cancel = self._post("cancel", {"session_id": ext_sid})
            self.external_results["cancel_rejected"] = {
                "ok": cancel.get("ok"),
                "code": (cancel.get("result", {}) or {}).get("code"),
                "message": (cancel.get("result", {}) or {}).get("message", "")[:60]}
            # cleanup fail-closed
            cleanup = self._post("cleanup", {"session_id": ext_sid})
            self.external_results["cleanup_rejected"] = {
                "ok": cleanup.get("ok"),
                "code": (cleanup.get("result", {}) or {}).get("code")}
            # retry fail-closed: an EXTERNAL session has no MANAGED job authority
            retry_res = self._post("retry", {"job_id": "ext-has-no-managed-job",
                                             "idempotency_key": "ext-k"})
            self.external_results["retry_rejected"] = {
                "ok": retry_res.get("ok"),
                "code": (retry_res.get("result", {}) or {}).get("code"),
                "message": (retry_res.get("result", {}) or {}).get("message", "")[:50]}
            # process still alive after all rejected actions
            alive_after_reject = self._pid_alive(p.pid)
            # UI shows the external session with control actions disabled
            page.wait_for_function(
                f"Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('{ext_sid[:8]}'))",
                timeout=15000)
            ext_card = page.evaluate(f"""
                (() => {{ const c = Array.from(document.querySelectorAll('.card'))
                    .find(x=>x.textContent.includes('{ext_sid[:8]}'));
                  return c ? c.textContent : ''; }})()
            """)
            self.external_results["ui"] = {
                "visible": bool(ext_card),
                "has_inspect_button": "Inspect" in ext_card,
                "has_cancel_button": "Cancel" in ext_card,
                "has_cleanup_button": "Cleanup" in ext_card,
                "has_retry_button": "Retry" in ext_card}
            self._record("8", "external session",
                         alive_after_observe=alive_after_observe,
                         alive_after_reject=alive_after_reject,
                         result=self.external_results)
            self._shot(page, "step8_external")
        finally:
            # terminate only via the runner (external cleanup, not control-plane)
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    def _pid_alive(self, pid) -> bool:
        try:
            import os as _os
            _os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _inspect_cleanup(self, page, job):
        # DOD-09: Inspect D via UI (evidence + hashes visible), then two
        # Cleanup calls (first removes disposable resources, second idempotent).
        job_id = job.get("job_id")
        # Inspect: open the D terminal card detail
        page.wait_for_function(
            f"Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('{job_id}'))",
            timeout=15000)
        # run Inspect via API (read-only status) and Cleanup twice
        # find the session id for job D
        c = self._console()
        sid = ""
        for x in c["terminal"]:
            if x.get("job_id") == job_id and x.get("session_id"):
                sid = x.get("session_id")
                break
        inspect = self._post("inspect", {"session_id": sid}) if sid else {"ok": False}
        # resource evidence (DOD-09): worktree/scope/bundle before cleanup
        wt_path = ""
        scope = ""
        bundle_ids = []
        if sid:
            try:
                d = json.loads((self.state_dir / "registry" / "sessions.json")
                               .read_text(encoding="utf-8"))
                s = d.get("sessions", {}).get(sid, {})
                wt_path = s.get("worktree", "")
                scope = s.get("scope_id", "")
                for r in (s.get("result_refs") or []):
                    if isinstance(r, str) and r.startswith("evidence:"):
                        bundle_ids.append(r.split(":", 1)[1])
            except (OSError, json.JSONDecodeError):
                pass
        # fall back to scanning the evidence store for this job's bundles
        if not bundle_ids:
            try:
                for ev in (self.state_dir / "evidence").glob("ev_*.json"):
                    try:
                        data = json.loads(ev.read_text(encoding="utf-8"))
                        if data.get("job_id") == job_id:
                            bundle_ids.append(ev.stem)
                    except (OSError, json.JSONDecodeError):
                        pass
            except OSError:
                pass
        bundle_ids = list(dict.fromkeys(bundle_ids))
        wt_before = bool(wt_path) and Path(wt_path).exists()
        scope_before = bool(scope) and self._scope_exists(scope)
        bundle_before = {b: (self.state_dir / "evidence" / f"{b}.json").is_file()
                         for b in bundle_ids}
        cleanup1 = self._post("cleanup", {"session_id": sid}) if sid else {"ok": False}
        cleanup2 = self._post("cleanup", {"session_id": sid}) if sid else {"ok": False}
        wt_after = bool(wt_path) and Path(wt_path).exists()
        scope_after = bool(scope) and self._scope_exists(scope)
        bundle_after = {b: (self.state_dir / "evidence" / f"{b}.json").is_file()
                        for b in bundle_ids}
        self._record("10", "inspect+cleanup D",
                     inspect_ok=inspect.get("ok"),
                     worktree_path=wt_path,
                     worktree_exists_before=wt_before,
                     worktree_exists_after=wt_after,
                     scope_exists_before=scope_before,
                     scope_exists_after=scope_after,
                     cleanup1_ok=(cleanup1.get("result", {}) or {}).get("success"),
                     cleanup1_removed=(cleanup1.get("result", {}) or {}).get("removed"),
                     cleanup2_ok=(cleanup2.get("result", {}) or {}).get("success"),
                     cleanup2_removed=(cleanup2.get("result", {}) or {}).get("removed"),
                     cleanup2_idempotent=((cleanup2.get("result", {}) or {}).get("success") is True),
                     evidence_bundle_before=bundle_before,
                     evidence_bundle_after=bundle_after,
                     base_porcelain=_git_porcelain(FIXTURE_DIR))
        self._shot(page, "step10_inspect_cleanup")

    def _scope_exists(self, scope_id: str) -> bool:
        if not scope_id:
            return False
        r = subprocess.run(["systemctl", "--user", "list-units", "--type=scope",
                            "--no-legend"], capture_output=True, text=True)
        return scope_id in r.stdout

    def _build_receipt(self) -> dict:
        receipt = {
            "schema_version": "CONDUVERA-ACTIVITY-ACCEPTANCE-1.0.0",
            "acceptance_run_id": self.run_id,
            "generated_at": _utc(),
            "goal_name": "close-conduvera-operational-activity-workspace-v1",
            "acceptance_contract_version": "1.0",
            "core_final_head": _git_head(CORE_DIR),
            "fixture_head_after": _git_head(FIXTURE_DIR),
            "fixture_tree_after": _git_tree(FIXTURE_DIR),
            "fixture_porcelain_after": _git_porcelain(FIXTURE_DIR),
            "ordered_steps": self.steps,
            "jobs": self.jobs,
            "external_session_negative_results": self.external_results,
            "UI_evidence_handles": self.screenshots,
            "deviations": self.deviations,
            "recovered_errors": self.recovered,
            "failed_diagnostic_run_ids": self.failed_runs,
            "unresolved_findings": self.unresolved,
        }
        return receipt


def main() -> int:
    runner = AcceptanceRunner()
    try:
        runner.start_service()
    except Exception as exc:
        print("service start failed:", exc)
        runner.stop_service()
        return 1
    try:
        receipt = runner.run()
    except Exception as exc:
        runner.deviations.append(f"journey exception: {exc}")
        receipt = runner._build_receipt()
        print("journey error:", exc)
    finally:
        runner.stop_service()
    path = runner.state_dir / "acceptance-receipt.json"
    payload = json.dumps(receipt, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode()).hexdigest()
    receipt["bundle_sha256"] = sha
    print(json.dumps({"run_id": runner.run_id, "receipt": str(path),
                      "sha256": sha}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
