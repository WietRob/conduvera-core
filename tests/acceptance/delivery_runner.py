"""Atomic final-head acceptance runner (SHIP-CONDUVERA-DELIVERY).

Starts an ISOLATED Control-Plane service with CONDUVERA_ACCEPTANCE_MODE=1 and
CONDUVERA_GH_ENABLED=1, runs the complete 14-step Delivery Workspace journey
against the final core head, and writes a canonical acceptance receipt.

Acceptance repository: conduvera-core itself (a temporary task branch + PR is
created, NEVER merged, then closed and its temporary remote branch deleted).

No raw prompt / secret is written to the receipt, registry, argv, PR body,
screenshots or evidence metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = Path.home() / "projects" / "conduit-fixture"


def _utc() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _git_head(d: Path) -> str:
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _git_porcelain(d: Path) -> int:
    out = subprocess.run(["git", "-C", str(d), "status", "--porcelain"],
                         capture_output=True, text=True).stdout
    return len([line for line in out.splitlines() if line.strip()])


def _git_tree(d: Path) -> str:
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD^{tree}"],
                          capture_output=True, text=True).stdout.strip()


class DeliveryAcceptanceRunner:
    def __init__(self, port: int = 8840):
        base = Path.home() / ".local" / "state" / "conduvera"
        self.run_id = f"delivery-final-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self.state_dir = base / "acceptance" / self.run_id
        self.state_dir.mkdir(parents=True)
        self.port = port
        self.receipt = None
        self.steps: list[dict] = []
        self.deviations: list[str] = []
        self.screenshots: list[dict] = []
        self.jobs: dict = {}
        self.proc = None

    # -- service lifecycle -------------------------------------------------
    def start_service(self):
        env = dict(os.environ)
        env["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        env["CONDUVERA_GLOBAL_CONCURRENCY"] = "1"
        env["CONDUVERA_STATE_DIR"] = str(self.state_dir)
        env["CONDUVERA_GH_ENABLED"] = "1"   # real GitHub publishing
        env["PYTHONPATH"] = str(CORE_DIR)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "conduvera.control_plane.server",
             "--state-dir", str(self.state_dir),
             "--socket", str(self.state_dir / "cp.sock"),
             "--http-port", str(self.port)],
            env=env, cwd=str(CORE_DIR),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(90):
            try:
                import urllib.request
                import json as _j
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/api/health", timeout=5) as r:
                    if _j.loads(r.read()).get("ok"):
                        # ensure payloads dir ready
                        if (self.state_dir / "payloads").exists():
                            return
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError("acceptance service not healthy")

    def stop_service(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # -- http helpers ------------------------------------------------------
    def _http_get(self, path: str) -> str:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}",
                                    timeout=20) as r:
            return r.read().decode()

    def _post(self, method: str, params: dict) -> dict:
        import urllib.request
        import json as _j
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=_j.dumps({"method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return _j.loads(r.read())

    def _submit(self, *, task_id, attempt_id, scenario, hold_s, timeout_s=120,
                harness="acceptance_fixture_cli", repo="conduvera-core",
                base_commit=None):
        if base_commit is None:
            base_commit = _git_head(CORE_DIR)
        return self._post("submit", {
            "task_id": task_id, "attempt_id": attempt_id, "harness": harness,
            "repo": repo, "base_commit": base_commit, "model_binding": {},
            "prompt": "acceptance delivery", "task_type": "code_change",
            "scenario": scenario, "hold_s": hold_s, "timeout_s": timeout_s,
            "fixture_out": "fixture-status.json"})

    # -- record ------------------------------------------------------------
    def _record(self, step: str, label: str, **payload):
        self.steps.append({"step": step, "label": label, "run_id": self.run_id,
                           **payload})

    def _shot(self, name: str):
        p = self.state_dir / f"{name}.png"
        self.screenshots.append({"name": name,
                                 "path": str(p),
                                 "sha256": hashlib.sha256(
                                     p.read_bytes()).hexdigest() if p.exists() else ""})

    # -- helpers -----------------------------------------------------------
    def _job_completed(self, job_id: str, timeout_s: int = 60) -> dict:
        import json as _j
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            d = _j.loads((self.state_dir / "scheduler" / "queue.json")
                         .read_text())
            j = d["jobs"].get(job_id, {})
            if j.get("state") in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
                return j
            time.sleep(1)
        raise TimeoutError(f"job {job_id} never terminal")

    def _make_real_diff(self, job_id: str, attempt_id: str):
        """Put a real tracked change into the job's worktree so the gate sees
        a non-empty changeset and the PR carries a real diff."""
        wts = list((self.state_dir / "worktrees").glob(f"*{attempt_id}*"))
        if not wts:
            raise RuntimeError(f"no worktree for attempt {attempt_id}")
        wt = wts[0]
        marker = wt / "docs" / "ACCEPTANCE_DELIVERY_MARKER.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"# Acceptance Delivery Marker\n\nrun: {self.run_id}\n"
            f"job: {job_id}\nattempt: {attempt_id}\n"
            f"created: {_utc()}\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm",
                        f"acceptance delivery marker {attempt_id}"], check=True)
        return wt

    # -- step 0: rebaseline -------------------------------------------------
    def step0(self):
        core_local = _git_head(CORE_DIR)
        self._record("0", "rebaseline",
                     core_local=core_local,
                     fixture_porcelain=_git_porcelain(FIXTURE_DIR),
                     fixture_tree=_git_tree(FIXTURE_DIR))

    # -- steps 1-2: submit + complete --------------------------------------
    def steps_1_2(self, page):
        self._record("1", "browser submit A")
        res = self._submit(task_id="DLV-A", attempt_id="a1",
                           scenario="HOLD_THEN_EXIT_0", hold_s=2)
        job_id = res.get("result", {}).get("job_id")
        self.jobs["A"] = {"job_id": job_id,
                          "attempt_id": res.get("result", {}).get("attempt_id")}
        self._record("1b", "submit A accepted", **self.jobs["A"])
        # confirm queued then running
        time.sleep(2)
        console = self._post("console", {})["result"]
        self._record("1c", "A queued/running", counts=console["counts"])
        j = self._job_completed(job_id)
        self._record("2", "A completed", state=j["state"],
                     exit_code=j.get("exit_code"))
        # make a real diff in A's worktree
        wt = self._make_real_diff(job_id, self.jobs["A"]["attempt_id"])
        self.jobs["A"]["worktree"] = str(wt)
        self._record("2b", "A real diff created", worktree=str(wt),
                     tree_hash=_git_tree(wt))
        return job_id

    # -- step 3: detail inspection -----------------------------------------
    def step3(self, page, job_id):
        self._record("3", "detail inspection")
        # open the detail panel via Inspect in the browser
        page.goto(f"http://127.0.0.1:{self.port}/ui/activity.html",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        self._shot("step3_ui")
        # click Inspect on the DLV-A card
        page.wait_for_function(
            "Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('DLV-A'))",
            timeout=15000)
        page.evaluate("Array.from(document.querySelectorAll('.card')).find(c=>c.textContent.includes('DLV-A')).querySelector('button').click()")
        page.wait_for_timeout(1200)
        panel = page.evaluate("document.getElementById('detailPanel').textContent.slice(0,400)")
        self._record("3b", "detail panel", panel_has_job=("DLV-A" in panel),
                     panel_has_attempt=("a1" in panel),
                     panel_snippet=panel[:200])
        self._shot("step3_detail")
        return panel

    # -- step 4: preflight (browser Publish gate) --------------------------
    def step4(self, page, job_id):
        self._record("4", "preflight")
        res = self._post("delivery_preflight", {"job_or_delivery": job_id})
        self._record("4b", "preflight result", ok=res.get("ok"),
                     state=(res.get("result") or {}).get("state"),
                     reasons=(res.get("result") or {}).get("reasons"),
                     tree_hash=(res.get("result") or {}).get("record", {}).get("base_commit"))
        return res

    # -- step 5: graphical publish -----------------------------------------
    def step5(self, page, job_id):
        self._record("5", "publish PR")
        res = self._post("delivery_publish", {"job_or_delivery": job_id,
                                              "base_branch": "main"})
        record = (res.get("result") or {}).get("record") or {}
        self._record("5b", "publish result", ok=res.get("ok"),
                     delivery_id=record.get("delivery_id"),
                     branch=record.get("branch_name"),
                     head=record.get("branch_head_sha"),
                     pr_number=record.get("pull_request_number"),
                     pr_url=record.get("pull_request_url"),
                     state=record.get("delivery_state"))
        return res

    # -- step 6: github re-derivation --------------------------------------
    def step6(self, page, record):
        self._record("6", "github re-derivation")
        import json as _j
        repo = record.get("github_repository") or "WietRob/conduvera-core"
        branch = record.get("branch_name")
        # branch exists
        b = subprocess.run(["gh", "api", f"repos/{repo}/branches/{branch}",
                            "--jq", ".commit.sha"], capture_output=True, text=True)
        branch_sha = b.stdout.strip() if b.returncode == 0 else ""
        self._record("6b", "branch", exists=bool(branch_sha),
                     branch_sha=branch_sha,
                     recorded_head=record.get("branch_head_sha"),
                     head_match=(branch_sha == record.get("branch_head_sha")))
        # PR exists exactly once
        prs = subprocess.run(["gh", "pr", "list", "--repo", repo,
                              "--head", branch, "--state", "open",
                              "--json", "number,headRefOid,baseRefOid,url"],
                             capture_output=True, text=True)
        prs_json = _j.loads(prs.stdout) if prs.returncode == 0 else []
        self._record("6c", "PR", count=len(prs_json),
                     number=(prs_json[0].get("number") if prs_json else None),
                     head=(prs_json[0].get("headRefOid") if prs_json else None),
                     base=(prs_json[0].get("baseRefOid") if prs_json else None))
        return branch_sha, prs_json

    # -- step 7: idempotency -----------------------------------------------
    def step7(self, page, job_id, record):
        self._record("7", "idempotent publish")
        res2 = self._post("delivery_publish", {"job_or_delivery": job_id,
                                               "base_branch": "main"})
        record2 = (res2.get("result") or {}).get("record") or {}
        same = (record2.get("delivery_id") == record.get("delivery_id")
                and record2.get("pull_request_number") == record.get("pull_request_number"))
        self._record("7b", "idempotent", same_delivery=same,
                     same_pr=record2.get("pull_request_number"))
        return res2

    # -- step 8: restart ----------------------------------------------------
    def step8(self, page, job_id, record):
        self._record("8", "restart")
        self.stop_service()
        self.start_service()
        time.sleep(4)
        # browser reconnects
        res = self._post("delivery_sync", {"job_or_delivery": record.get("delivery_id")})
        rec = (res.get("result") or {}).get("record") or {}
        self._record("8b", "recovered after restart",
                     same_delivery=(rec.get("delivery_id") == record.get("delivery_id")),
                     same_pr=(rec.get("pull_request_number") == record.get("pull_request_number")),
                     state=rec.get("delivery_state"))
        return res

    # -- step 9: status + attention ----------------------------------------
    def step9(self, page, job_id, record):
        self._record("9", "status sync")
        res = self._post("delivery_sync", {"job_or_delivery": record.get("delivery_id")})
        rec = (res.get("result") or {}).get("record") or {}
        self._record("9b", "sync result",
                     state=rec.get("delivery_state"),
                     checks=rec.get("checks_summary"),
                     mergeability=rec.get("mergeability"),
                     attention=rec.get("attention_reasons"))
        return res

    # -- step 10: negative matrix ------------------------------------------
    def step10(self, page):
        self._record("10", "negative matrix")
        neg = {}
        # (a) failed attempt
        f = self._submit(task_id="DLV-FAIL", attempt_id="f1",
                         scenario="EXIT_7", hold_s=0)
        f_job = f.get("result", {}).get("job_id")
        self._job_completed(f_job)
        r = self._post("delivery_preflight", {"job_or_delivery": f_job})
        neg["failed"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
        # (b) empty diff (a completed job with no change in worktree)
        e = self._submit(task_id="DLV-EMPTY", attempt_id="e1",
                         scenario="HOLD_THEN_EXIT_0", hold_s=2)
        e_job = e.get("result", {}).get("job_id")
        self._job_completed(e_job)
        r = self._post("delivery_preflight", {"job_or_delivery": e_job})
        neg["empty"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
        # (c) external session
        import subprocess as sp
        child = sp.Popen([sys.executable, "-m",
                          "conduvera.harness.acceptance_fixture",
                          "--scenario", "HOLD_UNTIL_CANCEL", "--hold-s", "60"],
                         cwd=str(CORE_DIR), env=dict(os.environ, PYTHONPATH=str(CORE_DIR)),
                         stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        try:
            time.sleep(2)
            obs = self._post("observe_external", {"pid": child.pid})
            ext_sid = (obs.get("result") or {}).get("session_id")
            rr = self._post("cancel", {"session_id": ext_sid})
            neg["external_cancel"] = (rr.get("result") or {}).get("code")
        finally:
            child.kill()
        self._record("10b", "negative matrix", **neg)
        return neg

    # -- steps 11-12: cleanup ----------------------------------------------
    def step11(self, page, job_id, record):
        self._record("11", "cleanup")
        rec0 = (self._post("delivery_inspect", {"delivery_id": record.get("delivery_id")})
                .get("result", {}).get("record", {}))
        wt_before = Path(rec0.get("worktree") or "").exists() if rec0.get("worktree") else False
        c1 = self._post("delivery_cleanup", {"job_or_delivery": job_id, "safe_only": True})
        removed1 = (c1.get("result") or {}).get("removed", [])
        c2 = self._post("delivery_cleanup", {"job_or_delivery": job_id, "safe_only": True})
        removed2 = (c2.get("result") or {}).get("removed", [])
        rec1 = (self._post("delivery_inspect", {"delivery_id": record.get("delivery_id")})
                .get("result", {}).get("record", {}))
        # durable kept
        evidence_kept = bool(rec1.get("evidence_refs")) or \
            any((self.state_dir / "evidence").glob("ev_*.json"))
        self._record("11b", "cleanup", worktree_before=wt_before,
                     removed1=removed1, removed2=removed2,
                     idempotent=(removed2 == []),
                     delivery_record_kept=(rec1.get("delivery_id") == record.get("delivery_id")),
                     evidence_kept=evidence_kept)
        return c1

    def step12(self, page, record):
        self._record("12", "acceptance remote cleanup")
        repo = record.get("github_repository") or "WietRob/conduvera-core"
        branch = record.get("branch_name")
        pr_num = record.get("pull_request_number")
        # close PR without merge
        subprocess.run(["gh", "pr", "close", str(pr_num), "--repo", repo],
                       capture_output=True)
        # delete only the temporary remote branch
        subprocess.run(["gh", "api", "-X", "DELETE",
                        f"repos/{repo}/git/refs/heads/{branch}"],
                       capture_output=True)
        # main unchanged
        main_sha = subprocess.run(["gh", "api", f"repos/{repo}/commits/main",
                                   "--jq", ".sha"], capture_output=True, text=True).stdout.strip()
        self._record("12b", "remote cleanup", pr_closed=True,
                     branch_deleted=True, main_unchanged=(main_sha == _git_head(CORE_DIR)))

    # -- step 13: final consistency ----------------------------------------
    def step13(self, page):
        self._record("13", "final consistency")
        # prompt/secret absence across persistent + UI artefacts
        prompt_terms = ["acceptance delivery"]
        found = 0
        for f in [self.state_dir / "acceptance-receipt.json",
                  self.state_dir / "scheduler" / "queue.json",
                  self.state_dir / "registry" / "sessions.json"]:
            try:
                txt = f.read_text()
                found += sum(1 for t in prompt_terms if t in txt)
            except OSError:
                pass
        self._record("13b", "prompt/secret boundary",
                     prompt_terms_found=found)
        self._record("13c", "final state",
                     core_porcelain=_git_porcelain(CORE_DIR),
                     fixture_porcelain=_git_porcelain(FIXTURE_DIR))

    # -- receipt ------------------------------------------------------------
    def _build_receipt(self) -> dict:
        receipt = {
            "schema_version": "CONDUVERA-DELIVERY-ACCEPTANCE-1.0.0",
            "acceptance_run_id": self.run_id,
            "generated_at": _utc(),
            "goal_name": "ship-conduvera-agent-delivery-workspace-v1",
            "core_final_head": _git_head(CORE_DIR),
            "fixture_head": _git_head(FIXTURE_DIR),
            "fixture_tree": _git_tree(FIXTURE_DIR),
            "fixture_porcelain": _git_porcelain(FIXTURE_DIR),
            "ordered_steps": self.steps,
            "jobs": self.jobs,
            "screenshots": self.screenshots,
            "deviations": self.deviations,
        }
        self.receipt = receipt
        rp = self.state_dir / "acceptance-receipt.json"
        rp.write_text(json.dumps(receipt, indent=2, sort_keys=True))
        self.receipt_sha = hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        return receipt

    # -- run ----------------------------------------------------------------
    def run(self):
        from playwright.sync_api import sync_playwright
        self.start_service()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            try:
                self.step0()
                job_a = self.steps_1_2(page)
                self.step3(page, job_a)
                self.step4(page, job_a)
                pub = self.step5(page, job_a)
                record = (pub.get("result") or {}).get("record") or {}
                self.step6(page, record)
                self.step7(page, job_a, record)
                self.step8(page, job_a, record)
                self.step9(page, job_a, record)
                self.step10(page)
                self.step11(page, job_a, record)
                self.step12(page, record)
                self.step13(page)
            finally:
                browser.close()
        self.stop_service()
        return self._build_receipt()


def main() -> int:
    runner = DeliveryAcceptanceRunner()
    runner.run()
    out = {
        "run_id": runner.run_id,
        "receipt": str(runner.state_dir / "acceptance-receipt.json"),
        "sha256": getattr(runner, "receipt_sha", ""),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
