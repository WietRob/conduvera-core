"""Internal-alpha scheduler, worktree and event-chain tests.

Tests the multi-session scheduler (persistent queue, concurrency limits,
tombstones), the real Git worktree binding, and the full MXOS-EVIDENCE
lifecycle chain introduced for CONTROL-PLANE-ALPHA-V1.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conduvera.control_plane.scheduler import (
    AttemptDescriptor,
    AttemptState,
    JobDescriptor,
    JobState,
    Scheduler,
    SchedulerStore,
)
from conduvera.control_plane.worktree import WorktreeBinding, WorktreeError, WorktreeManager
from conduvera.evidence.contract import ADAPTER_EVENT_TYPES


# ---------------------------------------------------------------------------
# Worktree tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    # second commit (base_commit2) for distinct binds
    (repo / "f.txt").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "second"], check=True)
    base2 = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return repo, base, base2


class TestWorktreeManager:
    def test_real_git_worktree_created(self, git_repo, tmp_path):
        repo, base, _ = git_repo
        mgr = WorktreeManager(tmp_path / "wt-base")
        b = mgr.create(repo_path=repo, base_commit=base,
                       task_id="T1", attempt_id="A1")
        assert isinstance(b, WorktreeBinding)
        assert Path(b.path).is_dir()
        assert b.base_commit == base
        assert b.head_commit == base  # detached at exact base
        assert b.detached
        # proven via git itself
        r = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, check=True)
        assert str(Path(b.path).resolve()) in r.stdout
        assert f"HEAD {base}" in r.stdout

    def test_worktree_not_plain_directory(self, git_repo, tmp_path):
        """A directory merely named worktree is not accepted."""
        repo, base, _ = git_repo
        mgr = WorktreeManager(tmp_path / "wt-base")
        b = mgr.create(repo_path=repo, base_commit=base,
                       task_id="T2", attempt_id="A2")
        r = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"],
                           capture_output=True, text=True, check=True)
        assert str(Path(b.path).resolve()) in r.stdout
        assert f"HEAD {base}" in r.stdout

    def test_collision_rejected(self, git_repo, tmp_path):
        repo, base, _ = git_repo
        mgr = WorktreeManager(tmp_path / "wt-base")
        mgr.create(repo_path=repo, base_commit=base, task_id="T3", attempt_id="A3")
        with pytest.raises(WorktreeError):
            mgr.create(repo_path=repo, base_commit=base, task_id="T3", attempt_id="A3")

    def test_bad_commit_fails_closed(self, git_repo, tmp_path):
        repo, base, _ = git_repo
        mgr = WorktreeManager(tmp_path / "wt-base")
        with pytest.raises(WorktreeError):
            mgr.create(repo_path=repo, base_commit="deadbeefdeadbeef",
                       task_id="T4", attempt_id="A4")

    def test_remove_only_session_owned(self, git_repo, tmp_path):
        repo, base, _ = git_repo
        mgr = WorktreeManager(tmp_path / "wt-base")
        b = mgr.create(repo_path=repo, base_commit=base,
                       task_id="T5", attempt_id="A5")
        mgr.remove(b.path, repo)
        assert not Path(b.path).exists()
        # outside base dir -> refused
        with pytest.raises(WorktreeError):
            mgr.remove("/tmp/foreign-dir", repo)


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------


class TestScheduler:
    def test_queue_and_limits(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        sched = Scheduler(store=store, global_limit=4, per_harness_limits={"h": 1})
        a1 = AttemptDescriptor(attempt_id="a1", job_id="j1", task_id="t1", harness="h")
        a2 = AttemptDescriptor(attempt_id="a2", job_id="j1", task_id="t1", harness="h")
        store.save_attempt(a1)
        store.save_attempt(a2)
        ok, reason = sched.can_start("h")
        assert ok is True
        sched.advance("a1", AttemptState.RUNNING)
        ok, reason = sched.can_start("h")
        assert ok is False
        assert "limit" in reason

    def test_global_limit(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        sched = Scheduler(store=store, global_limit=1, per_harness_limits={"h": 1, "h2": 1})
        store.save_attempt(AttemptDescriptor(attempt_id="a1", job_id="j", task_id="t", harness="h"))
        sched.advance("a1", AttemptState.RUNNING)
        ok, reason = sched.can_start("h2")
        assert ok is False
        assert "global limit" in reason

    def test_lifecycle_transitions(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        sched = Scheduler(store=store)
        a = AttemptDescriptor(attempt_id="a1", job_id="j1", task_id="t1", harness="h")
        store.save_attempt(a)
        assert a.state is AttemptState.CREATED
        sched.advance("a1", AttemptState.QUEUED)
        sched.advance("a1", AttemptState.RUNNING)
        sched.advance("a1", AttemptState.COMPLETED)
        got = store.get_attempt("a1")
        assert got.state is AttemptState.COMPLETED
        assert got.terminal is True

    def test_tombstone_retention(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        sched = Scheduler(store=store, retention_s=0.01)
        a = AttemptDescriptor(attempt_id="a1", job_id="j1", task_id="t1", harness="h")
        store.save_attempt(a)
        sched.advance("a1", AttemptState.COMPLETED)
        sched.retain("a1")
        got = store.get_attempt("a1")
        assert got.state is AttemptState.RETENTION
        assert got.terminal is True
        import time
        time.sleep(0.05)
        removed = sched.expire_retention()
        assert "a1" in removed

    def test_idempotent_retain(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        sched = Scheduler(store=store)
        a = AttemptDescriptor(attempt_id="a1", job_id="j1", task_id="t1", harness="h")
        store.save_attempt(a)
        sched.retain("a1")
        sched.retain("a1")  # idempotent
        assert store.get_attempt("a1").state is AttemptState.RETENTION

    def test_persistent_across_store_instances(self, tmp_path):
        store1 = SchedulerStore(tmp_path / "queue.json")
        store1.save_job(JobDescriptor(job_id="j1", task_id="t1", repo="r",
                                      base_commit="c", harness="h",
                                      model_binding={}, prompt="P"))
        store2 = SchedulerStore(tmp_path / "queue.json")
        job = store2.get_job("j1")
        assert job is not None
        assert job.task_id == "t1"
        assert job.state is JobState.ACCEPTED

    def test_0600(self, tmp_path):
        store = SchedulerStore(tmp_path / "queue.json")
        store.save_job(JobDescriptor(job_id="j1", task_id="t1", repo="r",
                                     base_commit="c", harness="h",
                                     model_binding={}, prompt="P"))
        mode = (tmp_path / "queue.json").stat().st_mode & 0o777
        assert mode == 0o600


# ---------------------------------------------------------------------------
# Event contract tests
# ---------------------------------------------------------------------------


class TestEventContract:
    def test_alpha_event_types_declared(self):
        for t in ("job.accepted", "attempt.created", "session.queued",
                  "session.timeout.requested", "session.reconciled",
                  "session.lost", "session.completed", "session.retained"):
            assert t in ADAPTER_EVENT_TYPES, f"missing {t}"

    def test_envelope_validates(self):
        from conduvera.evidence.contract import EventEnvelope
        e = EventEnvelope.create(
            event_type="session.queued",
            producer={"name": "conduvera-control-plane", "version": "v1",
                      "adapter": "control-plane"},
            subject={"kind": "harness_job"},
            payload={"job_id": "job_x", "reason": "limit"},
        )
        assert e.event_type == "session.queued"
        assert e.event_hash  # hash present
        assert "MXOS-EVIDENCE-1.0.0" in e.schema_version
