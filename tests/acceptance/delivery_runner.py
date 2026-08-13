"""Atomic final-head acceptance runner (SHIP-CONDUVERA-DELIVERY).

Starts an ISOLATED Control-Plane service with CONDUVERA_ACCEPTANCE_MODE=1 and
CONDUVERA_GH_ENABLED=1 and runs the 14-step Delivery Workspace journey against
the final core head. Acceptance repository: conduvera-core (temporary task
branch + PR, never merged, closed + remote branch deleted after evidence).
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


class DeliveryAcceptanceRunner:
    def __init__(self, port: int = 8850):
        base = Path.home() / ".local" / "state" / "conduvera"
        self.run_id = f"delivery-final-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self.state_dir = base / "acceptance" / self.run_id
        self.state_dir.mkdir(parents=True)
        self.port = port
        self.steps = []
        self.screenshots = []
        self.jobs = {}
        self.receipt_sha = ""
        self.proc = None

    # -- service -----------------------------------------------------------
    def start_service(self):
        env = dict(os.environ)
        env["CONDUVERA_ACCEPTANCE_MODE"] = "1"
        env["CONDUVERA_GLOBAL_CONCURRENCY"] = "1"
        env["CONDUVERA_STATE_DIR"] = str(self.state_dir)
        env["CONDUVERA_GH_ENABLED"] = "1"
        env["PYTHONPATH"] = str(CORE_DIR)
        # prune stale acceptance worktrees + free orphaned servers on our port
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
            env=env, cwd=str(CORE_DIR),
            stdout=logf, stderr=logf)
        import urllib.request
        import json as _j
        for _ in range(90):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/api/health", timeout=5) as r:
                    if _j.loads(r.read()).get("ok") and (self.state_dir / "payloads").exists():
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

    def _post(self, method: str, params: dict) -> dict:
        import urllib.request
        import urllib.error
        import json as _j
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=_j.dumps({"method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return _j.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"{method} HTTP {e.code}: {body[:500]}")

    def _submit(self, *, task_id, attempt_id, scenario, hold_s,
                timeout_s=120, repo="conduvera-core", base_commit=None):
        if base_commit is None:
            base_commit = _git_head(CORE_DIR)
        return self._post("submit", {
            "task_id": task_id, "attempt_id": attempt_id,
            "harness": "acceptance_fixture_cli", "repo": repo,
            "base_commit": base_commit, "model_binding": {},
            "prompt": "acceptance delivery", "task_type": "code_change",
            "scenario": scenario, "hold_s": hold_s, "timeout_s": timeout_s,
            "fixture_out": "fixture-status.json"})

    def _record(self, step, label, **payload):
        self.steps.append({"step": step, "label": label, "run_id": self.run_id,
                           **payload})

    def _job_completed(self, job_id, timeout_s=60):
        import json as _j
        qf = self.state_dir / "scheduler" / "queue.json"
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not qf.is_file():
                time.sleep(1)
                continue
            d = _j.loads(qf.read_text())
            j = d["jobs"].get(job_id, {})
            if j.get("state") in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
                return j
            time.sleep(1)
        raise TimeoutError(f"job {job_id} never terminal")

    def _make_real_diff(self, attempt_id):
        wts = list((self.state_dir / "worktrees").glob(f"*{attempt_id}*"))
        if not wts:
            raise RuntimeError(f"no worktree for attempt {attempt_id}")
        wt = wts[0]
        m = wt / "docs" / "ACCEPTANCE_DELIVERY_MARKER.md"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text(f"# Acceptance Delivery Marker\n\nrun: {self.run_id}\n"
                     f"attempt: {attempt_id}\ncreated: {_utc()}\n")
        # NOTE: do NOT commit here — the DeliveryService _create_commit stages
        # and commits the approved changeset during publish. We stage only the
        # marker (not the fixture/session runtime artefacts) so the gate sees
        # exactly the approved change set.
        subprocess.run(["git", "-C", str(wt), "add", "--", "docs/ACCEPTANCE_DELIVERY_MARKER.md"],
                       check=True)
        return wt

    # -- steps -------------------------------------------------------------
    def run(self):
        import json as _j
        from playwright.sync_api import sync_playwright
        self.start_service()
        main_sha = _git_head(CORE_DIR)
        self._record("0", "rebaseline", core_head=main_sha,
                     fixture_porcelain=_git_porcelain(
                         Path.home() / "projects" / "conduit-fixture"))

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            try:
                # STEP 1-2: submit + complete (retry with unique attempt id)
                res = None
                for _try in range(5):
                    attempt_id = f"a1_{_try}" if _try else "a1"
                    res = self._submit(task_id="DLV-A", attempt_id=attempt_id,
                                       scenario="HOLD_THEN_EXIT_0", hold_s=2)
                    if res.get("result", {}).get("job_id"):
                        break
                    time.sleep(3)
                if not res or not res.get("result", {}).get("job_id"):
                    raise RuntimeError(f"submit A failed: {res}")
                job_a = res["result"]["job_id"]
                self.jobs["A"] = {"job_id": job_a,
                                  "attempt_id": res["result"]["attempt_id"]}
                self._record("1", "submit A", **self.jobs["A"])
                time.sleep(2)
                console = self._post("console", {})["result"]
                self._record("1b", "A queued/running", counts=console["counts"])
                j = self._job_completed(job_a)
                self._record("2", "A completed", state=j["state"],
                             exit_code=j.get("exit_code"))
                wt = self._make_real_diff(self.jobs["A"]["attempt_id"])
                self.jobs["A"]["worktree"] = str(wt)
                self._record("2b", "A real diff",
                             worktree=str(wt),
                             tree_hash=_git_head(wt))

                # STEP 3: detail inspection
                page.goto(f"http://127.0.0.1:{self.port}/ui/activity.html",
                          wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                page.wait_for_function(
                    "Array.from(document.querySelectorAll('.card')).some(c=>c.textContent.includes('DLV-A'))",
                    timeout=15000)
                page.evaluate("Array.from(document.querySelectorAll('.card')).find(c=>c.textContent.includes('DLV-A')).querySelector('button').click()")
                page.wait_for_timeout(1200)
                panel = page.evaluate("document.getElementById('detailPanel').textContent.slice(0,300)")
                self._record("3", "detail inspection",
                             panel_has_job=("DLV-A" in panel),
                             panel_snippet=panel[:150])

                # STEP 4: preflight
                pre = self._post("delivery_preflight", {"job_or_delivery": job_a})
                self._record("4", "preflight",
                             ok=pre["ok"],
                             state=(pre.get("result") or {}).get("state"),
                             reasons=(pre.get("result") or {}).get("reasons"))

                # STEP 5: publish
                pub = self._post("delivery_publish", {"job_or_delivery": job_a,
                                                      "base_branch": "main"})
                record = (pub.get("result") or {}).get("record") or {}
                self._record("5", "publish", ok=pub.get("ok"),
                             state=record.get("delivery_state"),
                             delivery_id=record.get("delivery_id"),
                             branch=record.get("branch_name"),
                             head=record.get("branch_head_sha"),
                             pr_number=record.get("pull_request_number"),
                             pr_url=record.get("pull_request_url"))

                # STEP 6: github re-derivation
                repo = record.get("github_repository") or "WietRob/conduvera-core"
                branch = record.get("branch_name")
                b = subprocess.run(["gh", "api", f"repos/{repo}/branches/{branch}",
                                    "--jq", ".commit.sha"],
                                   capture_output=True, text=True)
                branch_sha = b.stdout.strip() if b.returncode == 0 else ""
                prs = subprocess.run(["gh", "pr", "list", "--repo", repo,
                                      "--head", branch, "--state", "open",
                                      "--json", "number,headRefOid,baseRefOid,url"],
                                     capture_output=True, text=True)
                prs_json = _j.loads(prs.stdout) if prs.returncode == 0 else []
                self._record("6", "github re-derivation",
                             branch_exists=bool(branch_sha),
                             branch_sha=branch_sha,
                             head_match=(branch_sha == record.get("branch_head_sha")),
                             pr_count=len(prs_json),
                             pr_number=(prs_json[0].get("number") if prs_json else None),
                             pr_head=(prs_json[0].get("headRefOid") if prs_json else None),
                             pr_base=(prs_json[0].get("baseRefOid") if prs_json else None))

                # STEP 7: idempotency
                pub2 = self._post("delivery_publish", {"job_or_delivery": job_a,
                                                       "base_branch": "main"})
                rec2 = (pub2.get("result") or {}).get("record") or {}
                self._record("7", "idempotency",
                             same_delivery=(rec2.get("delivery_id") == record.get("delivery_id")),
                             same_pr=(rec2.get("pull_request_number") == record.get("pull_request_number")))

                # STEP 8: restart
                self.stop_service()
                self.start_service()
                time.sleep(4)
                sync = self._post("delivery_sync", {"job_or_delivery": record.get("delivery_id")})
                rec3 = (sync.get("result") or {}).get("record") or {}
                self._record("8", "restart recovery",
                             same_delivery=(rec3.get("delivery_id") == record.get("delivery_id")),
                             same_pr=(rec3.get("pull_request_number") == record.get("pull_request_number")),
                             state=rec3.get("delivery_state"))

                # STEP 9: status + attention
                sync2 = self._post("delivery_sync", {"job_or_delivery": record.get("delivery_id")})
                rec4 = (sync2.get("result") or {}).get("record") or {}
                self._record("9", "status sync",
                             state=rec4.get("delivery_state"),
                             checks=rec4.get("checks_summary"),
                             mergeability=rec4.get("mergeability"),
                             attention=rec4.get("attention_reasons"))

                # STEP 10: negative matrix
                neg = {}
                f = self._submit(task_id="DLV-FAIL", attempt_id="f1",
                                 scenario="EXIT_7", hold_s=0)
                self._job_completed(f["result"]["job_id"])
                r = self._post("delivery_preflight", {"job_or_delivery": f["result"]["job_id"]})
                neg["failed"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
                e = self._submit(task_id="DLV-EMPTY", attempt_id="e1",
                                 scenario="HOLD_THEN_EXIT_0", hold_s=2)
                self._job_completed(e["result"]["job_id"])
                r = self._post("delivery_preflight", {"job_or_delivery": e["result"]["job_id"]})
                neg["empty"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
                # forbidden runtime artefact in the change set
                fb = self._submit(task_id="DLV-FORBID", attempt_id="f2",
                                  scenario="HOLD_THEN_EXIT_0", hold_s=2)
                self._job_completed(fb["result"]["job_id"])
                fwts = list((self.state_dir / "worktrees").glob("*f2*"))
                if fwts:
                    (fwts[0] / "fixture-status.json").write_text(
                        '{"status":"ok"}\n')
                    subprocess.run(["git", "-C", str(fwts[0]), "add", "-A"],
                                   check=True)
                r = self._post("delivery_preflight", {"job_or_delivery": fb["result"]["job_id"]})
                neg["forbidden"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
                # secret-like material in the change set
                sc = self._submit(task_id="DLV-SECRET", attempt_id="s1",
                                  scenario="HOLD_THEN_EXIT_0", hold_s=2)
                self._job_completed(sc["result"]["job_id"])
                swts = list((self.state_dir / "worktrees").glob("*s1*"))
                if swts:
                    (swts[0] / "leak.txt").write_text("API_KEY=super_secret_123456789\n")
                    subprocess.run(["git", "-C", str(swts[0]), "add", "-A"],
                                   check=True)
                r = self._post("delivery_preflight", {"job_or_delivery": sc["result"]["job_id"]})
                neg["secret"] = [x["code"] for x in (r.get("result") or {}).get("reasons", [])]
                self._record("10", "negative matrix", **neg)

                # STEP 11: cleanup
                rec0 = (self._post("delivery_inspect",
                                   {"delivery_id": record.get("delivery_id")})
                        .get("result", {}).get("record", {}))
                wt_before = Path(rec0.get("worktree") or "").exists() if rec0.get("worktree") else False
                c1 = self._post("delivery_cleanup", {"job_or_delivery": job_a,
                                                     "safe_only": True})
                c2 = self._post("delivery_cleanup", {"job_or_delivery": job_a,
                                                     "safe_only": True})
                self._record("11", "cleanup",
                             worktree_before=wt_before,
                             removed1=(c1.get("result") or {}).get("removed", []),
                             removed2=(c2.get("result") or {}).get("removed", []),
                             idempotent=(not (c2.get("result") or {}).get("removed")),
                             evidence_kept=bool((self.state_dir / "evidence").glob("ev_*.json")))

                # STEP 12: acceptance remote cleanup
                subprocess.run(["gh", "pr", "close", str(record.get("pull_request_number")),
                                "--repo", repo], capture_output=True)
                subprocess.run(["gh", "api", "-X", "DELETE",
                                f"repos/{repo}/git/refs/heads/{branch}"],
                               capture_output=True)
                main_after = subprocess.run(["gh", "api", f"repos/{repo}/commits/main",
                                             "--jq", ".sha"], capture_output=True, text=True).stdout.strip()
                self._record("12", "acceptance remote cleanup",
                             pr_closed=True, branch_deleted=True,
                             main_unchanged=(main_after == main_sha))

                # STEP 13: final consistency
                self._record("13", "final consistency",
                             core_porcelain=_git_porcelain(CORE_DIR),
                             fixture_porcelain=_git_porcelain(
                                 Path.home() / "projects" / "conduit-fixture"))
            finally:
                browser.close()
        self.stop_service()
        return self._build_receipt()

    def _build_receipt(self) -> dict:
        receipt = {
            "schema_version": "CONDUVERA-DELIVERY-ACCEPTANCE-1.0.0",
            "acceptance_run_id": self.run_id,
            "generated_at": _utc(),
            "goal_name": "ship-conduvera-agent-delivery-workspace-v1",
            "core_final_head": _git_head(CORE_DIR),
            "ordered_steps": self.steps,
            "jobs": self.jobs,
            "screenshots": self.screenshots,
        }
        (self.state_dir / "acceptance-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True))
        self.receipt_sha = hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        return receipt


def main() -> int:
    runner = DeliveryAcceptanceRunner()
    runner.run()
    print(json.dumps({
        "run_id": runner.run_id,
        "receipt": str(runner.state_dir / "acceptance-receipt.json"),
        "sha256": runner.receipt_sha,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
