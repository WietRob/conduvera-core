"""Delivery domain tests (SHIP-CONDUVERA-DELIVERY).

Covers:
- WS-A DeliveryStore persistence + append-only history + restart reconstruction;
- WS-B fail-closed pre-publish gate (structured negative codes);
- WS-C GitHub provider (dry-run) publish + idempotency;
- WS-D base-drift classification;
- WS-G status sync state mapping;
- WS-H cleanup retention (durable kept, disposable removed).
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.control_plane.delivery_store import DeliveryStore
from conduvera.control_plane.delivery_service import DeliveryService
from conduvera.control_plane.evidence_store import EvidenceStore
from conduvera.control_plane.github_provider import GitHubDeliveryProvider


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return repo, base


class _FakeJob:
    def __init__(self, job_id, repo, base_commit, state="COMPLETED", harness="opencode_cli"):
        self.job_id = job_id
        self.repo = repo
        self.base_commit = base_commit
        self.state = type("S", (), {"value": state})()
        self.harness = harness


class _FakeAttempt:
    def __init__(self, attempt_id, job_id, state="COMPLETED"):
        self.attempt_id = attempt_id
        self.job_id = job_id
        self.state = type("S", (), {"value": state})()


class _FakeSession:
    def __init__(self, session_id, worktree, ownership="MANAGED", attempt_id="a1"):
        self.session_id = session_id
        self.worktree = worktree
        self.ownership_class = type("O", (), {"value": ownership})()
        self.managed = ownership == "MANAGED"
        self.attempt_id = attempt_id


class _FakeScheduler:
    def __init__(self, jobs=None, attempts=None):
        self._jobs = jobs or {}
        self._attempts = attempts or {}

    @property
    def store(self):
        return self

    def get_job(self, job_id):
        return self._jobs.get(job_id)

    def get_attempt(self, attempt_id):
        return self._attempts.get(attempt_id)

    def all_attempts(self):
        return list(self._attempts.values())


class _FakeService:
    def __init__(self, scheduler, registry):
        self.scheduler = scheduler
        self.registry = registry


class _FakeRegistry:
    def __init__(self):
        self._s = {}

    def get(self, sid):
        return self._s.get(sid)

    def all(self):
        return list(self._s.values())


class TestDeliveryStore:
    def test_persist_and_restart_reconstruction(self, tmp_path):
        store = DeliveryStore(tmp_path / "delivery")
        rec = {"delivery_id": "dlv_abc", "job_id": "job_1", "attempt_id": "a1",
               "delivery_state": "NOT_READY"}
        store.save(rec)
        store.append_event("dlv_abc", {"seq": None, "event": "created",
                                       "state": "NOT_READY", "at": "t"})
        store.append_event("dlv_abc", {"seq": None, "event": "published",
                                       "state": "PR_OPEN", "at": "t2"})
        # restart: new store instance reads the same files
        store2 = DeliveryStore(tmp_path / "delivery")
        got = store2.get("dlv_abc")
        assert got["delivery_id"] == "dlv_abc"
        assert got["job_id"] == "job_1"
        hist = store2.history("dlv_abc")
        assert len(hist) == 2
        assert hist[0]["seq"] == 1 and hist[1]["seq"] == 2
        assert hist[1]["event"] == "published"

    def test_idempotent_save_same_delivery_id(self, tmp_path):
        store = DeliveryStore(tmp_path / "d")
        store.save({"delivery_id": "dlv_x", "delivery_state": "NOT_READY"})
        store.save({"delivery_id": "dlv_x", "delivery_state": "PR_OPEN"})
        assert store.get("dlv_x")["delivery_state"] == "PR_OPEN"
        assert len(store.all()) == 1


class TestPreflightGate:
    def _svc(self, tmp_path):
        state = tmp_path / "state"
        store = DeliveryStore(state / "delivery")
        ev = EvidenceStore(state / "evidence")
        # write a valid evidence bundle (exit + artifacts -> validate_evidence VALID)
        ev.put({"bundle_id": "ev_job_1_a1", "job_id": "job_1", "attempt_id": "a1",
                "evidence_status": "VALID", "schema_version": "CONDUVERA-EVIDENCE",
                "exit_code": 0,
                "artifacts": [{"path": "/tmp/ev_art", "sha256": "sha256:" + "0" * 64}]})
        return store, ev

    def test_gate_blocks_unsupported_nonterminal(self, tmp_path):
        store, ev = self._svc(tmp_path)
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234", state="FAILED")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        res = dlv.preflight("job_1")
        assert res["ok"] is False
        codes = [r["code"] for r in res["reasons"]]
        assert "JOB_NOT_COMPLETED" in codes

    def test_gate_blocks_external_session(self, tmp_path):
        store, ev = self._svc(tmp_path)
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        registry._s["mxs_ext"] = _FakeSession("mxs_ext", str(wt), ownership="EXTERNAL_UNKNOWN")
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        res = dlv.preflight("job_1")
        codes = [r["code"] for r in res["reasons"]]
        assert "EXTERNAL_SESSION_NOT_PUBLISHABLE" in codes

    def test_gate_empty_changeset(self, tmp_path):
        store, ev = self._svc(tmp_path)
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        # git worktree with no changes (clean)
        subprocess.run(["git", "init", "-q", str(wt)], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.name", "t"], check=True)
        (wt / "f").write_text("x\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)
        head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        # no new changes -> empty changeset
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", head)},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        res = dlv.preflight("job_1")
        codes = [r["code"] for r in res["reasons"]]
        assert "EMPTY_CHANGESET" in codes

    def test_gate_forbidden_path(self, tmp_path):
        store, ev = self._svc(tmp_path)
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(wt)], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.name", "t"], check=True)
        (wt / "f").write_text("x\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)
        # add a forbidden path (untracked .env)
        (wt / ".env").write_text("API_KEY=secret12345\n")
        (wt / "change.txt").write_text("ok\n")
        (wt / "x2.txt").write_text("change\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", head)},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        res = dlv.preflight("job_1")
        codes = [r["code"] for r in res["reasons"]]
        assert "FORBIDDEN_PATH" in codes or "SECRET_PATTERN_DETECTED" in codes

    def test_gate_forbidden_runtime_artefacts(self, tmp_path):
        """WS-B: generated runtime/session artefacts (fixture-status.json,
        mxs_*.stdout.txt) are forbidden in a deliverable change set."""
        store, ev = self._svc(tmp_path)
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(wt)], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(wt), "config", "user.name", "t"], check=True)
        (wt / "f").write_text("x\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)
        head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        # runtime artefacts + a real change
        (wt / "fixture-status.json").write_text("{\"status\":\"ok\"}\n")
        (wt / "mxs_abc.stdout.txt").write_text("log line\n")
        (wt / "real.txt").write_text("real\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", head)},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        res = dlv.preflight("job_1")
        codes = [r["code"] for r in res["reasons"]]
        assert "FORBIDDEN_PATH" in codes


class TestCleanupRetention:
    def test_resolve_target_reuses_existing_delivery(self, tmp_path):
        """DOD-08 idempotency: resolving a job with an existing bound delivery
        returns the SAME record, not a new one."""
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        rec = dlv._new_record("job_1", "a1")
        rec["delivery_state"] = "PR_OPEN"
        rec["pull_request_number"] = 42
        store.save(rec)
        got, jid, aid = dlv._resolve_target("job_1")
        assert got["delivery_id"] == rec["delivery_id"]
        assert got["pull_request_number"] == 42
        assert jid == "job_1" and aid == "a1"

    def test_cleanup_keeps_durable(self, tmp_path):
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        # create a record bound to the worktree, mark PR_OPEN (published)
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["delivery_state"] = "PR_OPEN"
        store.save(rec)
        # cleanup (published delivery is safe to clean)
        r = dlv.cleanup(rec["delivery_id"])
        assert r["ok"] is True
        assert r["removed"] == [str(wt)]
        assert not wt.exists()
        # durable truth stays
        assert store.get(rec["delivery_id"]) is not None
        assert r["durable_kept"]["delivery_record"] is True
        # evidence bundle not touched by product cleanup
        assert r["durable_kept"]["evidence"] is True
        # second cleanup idempotent
        r2 = dlv.cleanup(rec["delivery_id"])
        assert r2["ok"] is True
        assert r2["removed"] == []

    def test_unsafe_delivery_preserves_worktree(self, tmp_path):
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        wt = tmp_path / "worktrees" / "w1"
        wt.mkdir(parents=True)
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["delivery_state"] = "NEEDS_REBASE"
        store.save(rec)
        # safe_only cleanup must NOT remove the worktree of an unsafe delivery
        r = dlv.cleanup(rec["delivery_id"], safe_only=True)
        assert r["ok"] is False
        assert wt.exists()


class TestDrift:
    """DOD-08: MATCH / BEHIND / AHEAD / DIVERGED / UNAVAILABLE (defect 9)."""

    def _drift_svc(self, tmp_path, base_sha, remote_sha, repo=None):
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", base_sha)},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        # the worktree must be a git repo containing the recorded commits so
        # ancestry checks resolve
        wt = repo if repo is not None else tmp_path / "worktrees" / "w1"
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        # wire provider remote_base_sha to the recorded remote
        dlv.provider.remote_base_sha = lambda repository, base_branch: remote_sha
        return dlv, wt

    def _make_repo_wt(self, tmp_path):
        repo = tmp_path / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        (repo / "a.txt").write_text("v1\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c1"], check=True)
        c1 = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
        (repo / "a.txt").write_text("v2\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c2"], check=True)
        c2 = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
        return c1, c2, repo

    def test_drift_match(self, tmp_path):
        c1, _, repo = self._make_repo_wt(tmp_path)
        dlv, wt = self._drift_svc(tmp_path, c1, c1, repo)
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["github_repository"] = "R/r"
        rec["base_commit"] = c1
        assert dlv.classify_drift(rec) == "MATCH"

    def test_drift_behind(self, tmp_path):
        c1, c2, repo = self._make_repo_wt(tmp_path)
        dlv, wt = self._drift_svc(tmp_path, c1, c2, repo)
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["github_repository"] = "R/r"
        rec["base_commit"] = c1
        # recorded base c1 is ancestor of remote c2 -> BEHIND
        assert dlv.classify_drift(rec) == "BEHIND"

    def test_drift_ahead(self, tmp_path):
        c1, c2, repo = self._make_repo_wt(tmp_path)
        dlv, wt = self._drift_svc(tmp_path, c2, c1, repo)
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["github_repository"] = "R/r"
        rec["base_commit"] = c2
        # recorded base c2 is AHEAD of remote c1 -> AHEAD
        assert dlv.classify_drift(rec) == "AHEAD"

    def test_drift_unavailable(self, tmp_path):
        c1, _, repo = self._make_repo_wt(tmp_path)
        dlv, wt = self._drift_svc(tmp_path, c1, None, repo)
        rec = dlv._new_record("job_1", "a1")
        rec["worktree"] = str(wt)
        rec["github_repository"] = "R/r"
        rec["base_commit"] = c1
        assert dlv.classify_drift(rec) == "UNAVAILABLE"


class TestCheckDetails:
    """WS H dogfood feature: operator-visible check/review/mergeability detail."""

    def _svc_check(self, tmp_path, checks, reviews, pr):
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        dlv.provider.pr_view = lambda repo, num: pr
        dlv.provider.list_checks = lambda repo, sha: checks
        dlv.provider.list_reviews = lambda repo, num: reviews
        return dlv

    def test_check_details_has_checks_reviews_timeline(self, tmp_path):
        dlv = self._svc_check(
            tmp_path,
            checks=[{"name": "delivery-tests", "status": "completed",
                     "conclusion": "success", "started_at": "2026-01-01T00:00:00Z",
                     "completed_at": "2026-01-01T00:01:00Z",
                     "details_url": "https://github.com/r/r/runs/1", "app": "GitHub",
                     "required": True}],
            reviews=[{"state": "APPROVED", "user": {"login": "w"}, "submitted_at": "2026-01-01T00:00:00Z"}],
            pr={"state": "OPEN", "headRefOid": "h" * 40, "baseRefOid": "b" * 40,
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"})
        # persist a delivery record with github identity so sync resolves
        rec = dlv._new_record("job_1", "a1")
        rec["github_repository"] = "R/r"
        rec["pull_request_number"] = 1
        dlv.store.save(rec)
        r = dlv.check_details("job_1")
        assert r["ok"] is True
        assert r["checks"][0]["name"] == "delivery-tests"
        assert r["checks"][0]["required"] is True
        assert r["checks"][0]["conclusion"] == "success"
        assert r["reviews"][0]["state"] == "APPROVED"
        assert "timeline" in r
        assert r.get("availability", {}).get("checks") == "available"

    def test_latest_review_wins(self, tmp_path):
        """DOD-13 review2: a later approval by the same reviewer overrides an
        earlier CHANGES_REQUESTED (must not keep the delivery stuck)."""
        dlv = self._svc_check(
            tmp_path,
            checks=[],
            reviews=[
                {"state": "CHANGES_REQUESTED", "user": {"login": "w"},
                 "submitted_at": "2026-01-01T00:00:00Z"},
                {"state": "APPROVED", "user": {"login": "w"},
                 "submitted_at": "2026-01-02T00:00:00Z"},
            ],
            pr={"state": "OPEN", "headRefOid": "h" * 40, "baseRefOid": "b" * 40,
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"})
        rec = dlv._new_record("job_1", "a1")
        rec["github_repository"] = "R/r"
        rec["pull_request_number"] = 1
        dlv.store.save(rec)
        r = dlv.check_details("job_1")
        # effective latest = APPROVED, not CHANGES_REQUESTED
        summary = r["record"]["reviews_summary"]
        assert summary["approved"] == 1
        assert summary["changes_requested"] == 0

    def test_provider_failure_is_unavailable_not_success(self, tmp_path):
        """Befund 11: a provider fetch failure must render as stale, never as
        a clean empty success result."""
        dlv = self._svc_check(tmp_path, checks=[], reviews=[],
                              pr={"state": "OPEN", "headRefOid": "h" * 40,
                                  "baseRefOid": "b" * 40, "mergeable": "UNKNOWN",
                                  "mergeStateStatus": "UNKNOWN"})
        # provider raises -> sync marks the detail surface stale
        from conduvera.control_plane.github_provider import GitHubDeliveryError
        def _raise(*a, **k):
            raise GitHubDeliveryError("PROVIDER_FAILURE", "provider failure")
        dlv.provider.list_checks = _raise
        dlv.provider.list_reviews = _raise
        rec = dlv._new_record("job_1", "a1")
        rec["github_repository"] = "R/r"
        rec["pull_request_number"] = 1
        dlv.store.save(rec)
        r = dlv.check_details("job_1")
        assert r["ok"] is True
        # the per-source availability is stale (provider failed), not available
        assert r["availability"]["checks"] == "stale"
        assert r["availability"]["reviews"] == "stale"


class TestPublishAuthority:
    """PR A: publish REQUIRES the authoritative candidate_id; no auto-approval."""

    def _dlv(self, tmp_path):
        store, ev = DeliveryStore(tmp_path / "d"), EvidenceStore(tmp_path / "e")
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees",
                              delivery_store_dir=str(store.dir))
        return dlv

    def test_publish_requires_candidate_id(self, tmp_path):
        dlv = self._dlv(tmp_path)
        r = dlv.publish("job_1")
        # publish without a candidate_id is rejected
        assert r["ok"] is False
        assert r["reasons"][0]["code"] == "CANDIDATE_REQUIRED"

    def test_publish_rejects_unknown_candidate(self, tmp_path):
        dlv = self._dlv(tmp_path)
        r = dlv.publish("job_1", candidate_id="cand_nonexistent")
        assert r["ok"] is False
        assert r["reasons"][0]["code"] == "UNKNOWN_CANDIDATE"

    def test_publish_rejects_unapproved_candidate(self, tmp_path):
        dlv = self._dlv(tmp_path)
        repo, base = _make_repo(tmp_path / "x")
        wt = tmp_path / "wts" / "w1"
        subprocess.run(["git", "clone", "-q", str(repo), str(wt)], check=True)
        (wt / "a.txt").write_text("v2\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)
        c = dlv.candidate_service.build_candidate(
            job_id="job_1", attempt_id="a1", session_id="s", delivery_id="d",
            repo_id="fixture", github_repository="R/r", base_branch="main",
            base_commit=base, worktree=str(wt), evidence_refs=[],
            named_tests=[], named_gates=[])
        # not approved -> publish fails; no auto-approval by "conduvera"
        r = dlv.publish("job_1", candidate_id=c["candidate_id"])
        assert r["ok"] is False
        assert r["reasons"][0]["code"] == "CANDIDATE_NOT_APPROVED"
        # the candidate was NOT auto-approved
        stored = dlv.candidate_store.get(c["candidate_id"])
        assert not stored["approved_at"]

    def test_publish_idempotent_same_candidate(self, tmp_path):
        dlv = self._dlv(tmp_path)
        repo, base = _make_repo(tmp_path / "x")
        wt = tmp_path / "wts" / "w1"
        subprocess.run(["git", "clone", "-q", str(repo), str(wt)], check=True)
        (wt / "a.txt").write_text("v2\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "c"], check=True)
        # register the MANAGED session bound to the worktree
        dlv.service.registry._s["mxs_s"] = type("S", (), {
            "session_id": "mxs_s", "attempt_id": "a1",
            "worktree": str(wt), "ownership_class": "MANAGED"})()
        c = dlv.candidate_service.build_candidate(
            job_id="job_1", attempt_id="a1", session_id="mxs_s", delivery_id="d",
            repo_id="fixture", github_repository="R/r", base_branch="main",
            base_commit=base, worktree=str(wt), evidence_refs=[],
            named_tests=[], named_gates=[])
        dlv.candidate_service.approve(c["candidate_id"], approved_by="operator")
        # monkeypatch provider to a fake publish that returns a PR
        dlv.provider.find_pr = lambda repo, branch, base: None
        dlv.provider.remote_branch_sha = lambda repo, branch: None
        dlv.provider.remote_base_sha = lambda repo, branch: base
        dlv.provider.create_pr = lambda repo, branch, base, title, body: {
            "number": 7, "url": "https://github.com/R/r/pull/7",
            "headRefOid": "h" * 40, "baseRefOid": base, "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN"}
        dlv._push = lambda wt, repo, branch, head_sha=None: None
        r1 = dlv.publish("job_1", candidate_id=c["candidate_id"])
        assert r1["ok"] is True
        # repeat publish with the same candidate returns the same identity
        r2 = dlv.publish("job_1", candidate_id=c["candidate_id"])
        assert r2.get("ok") is True
        assert r1.get("record", {}).get("delivery_id") == \
            r2.get("record", {}).get("delivery_id")
        assert r1.get("record", {}).get("candidate_id") == \
            r2.get("record", {}).get("candidate_id")


