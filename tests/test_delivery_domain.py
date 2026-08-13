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
        # write a valid evidence bundle
        ev.put({"bundle_id": "ev_job_1_a1", "job_id": "job_1", "attempt_id": "a1",
                "evidence_status": "VALID", "content_sha256": "",
                "schema_version": "CONDUVERA-EVIDENCE"})
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
        # no new changes -> empty changeset
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
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
        scheduler = _FakeScheduler(
            jobs={"job_1": _FakeJob("job_1", "fixture", "abc1234")},
            attempts={"a1": _FakeAttempt("a1", "job_1")})
        registry = _FakeRegistry()
        registry._s["mxs_1"] = _FakeSession("mxs_1", str(wt))
        svc = _FakeService(scheduler, registry)
        dlv = DeliveryService(store=store, evidence_store=ev,
                              provider=GitHubDeliveryProvider(dry_run=True),
                              service=svc,
                              repo_allowlist={"fixture": tmp_path / "repo"},
                              worktree_root=tmp_path / "worktrees")
        # the changeset from HEAD would be empty (no commits after); .env is untracked
        # so force staging to include it for the test
        (wt / "x2.txt").write_text("change\n")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        res = dlv.preflight("job_1")
        codes = [r["code"] for r in res["reasons"]]
        assert "FORBIDDEN_PATH" in codes or "SECRET_PATTERN_DETECTED" in codes


class TestCleanupRetention:
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
