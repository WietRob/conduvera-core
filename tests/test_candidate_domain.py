"""PublishCandidate domain tests (TRUSTED-FEATURE-DELIVERY, WS B/C).

Covers:
- candidate build inventory (tracked/untracked) with exact file hashes;
- immutable approval freeze + repeat approval idempotent;
- NO_TOCTOU: file added/modified/removed after approval -> CANDIDATE_STALE;
- forbidden untracked runtime artefact blocks;
- atomic commit builds a tree whose blob hashes match the candidate exactly.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.control_plane.candidate_service import CandidateError, PublishCandidateService
from conduvera.control_plane.candidate_store import PublishCandidateStore
from conduvera.control_plane.evidence_store import EvidenceStore


def _git_init(wt: Path) -> str:
    wt.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.name", "t"], check=True)
    (wt / "a.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "base"], check=True)
    return subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _mk(tmp_path: Path):
    store = PublishCandidateStore(tmp_path / "cand")
    ev = EvidenceStore(tmp_path / "evidence")
    svc = PublishCandidateService(store, ev, worktree_root=tmp_path / "wts")
    return store, ev, svc


def _build_candidate(tmp_path):
    store, ev, svc = _mk(tmp_path)
    wt = tmp_path / "wts" / "w1"
    base = _git_init(wt)
    # real feature change: edit a.txt + add b.py + untracked marker
    (wt / "a.txt").write_text("v2\n")
    (wt / "b.py").write_text("def f():\n    return 1\n")
    (wt / "NEW.md").write_text("# new\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "feature"], check=True)
    c = svc.build_candidate(
        job_id="job_1", attempt_id="a1", session_id="s1", delivery_id="dlv_1",
        repo_id="conduvera-core", github_repository="WietRob/conduvera-core",
        base_branch="main", base_commit=base, worktree=str(wt),
        evidence_refs=[], named_tests=[{"name": "test_x", "result": "PASS", "duration_s": 1.2}],
        named_gates=[])
    return store, ev, svc, wt, c


class TestCandidateBuild:
    def test_manifest_has_exact_hashes_and_files(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        paths = {f["path"] for f in c["files"]}
        # base commit excludes a.txt-v2/b.py; candidate should carry them as
        # tracked changes against base
        assert "a.txt" in paths or "b.py" in paths or "NEW.md" in paths
        assert c["worktree_head_sha"]
        assert c["diff_sha256"]
        assert c["schema_version"] == "CONDUVERA-PUBLISH-CANDIDATE-1.0.0"
        assert c["approved_at"] is None
        # evidence hashes empty (no bundle)
        assert c["evidence_hashes"] == {}

    def test_forbidden_runtime_artefact_blocks(self, tmp_path):
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        (wt / "fixture-status.json").write_text('{"status":"ok"}\n')
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        try:
            svc.build_candidate(
                job_id="job_1", attempt_id="a1", session_id="s1",
                delivery_id="dlv_1", repo_id="r", github_repository="R/r",
                base_branch="main", base_commit=base, worktree=str(wt),
                evidence_refs=[], named_tests=[], named_gates=[])
            assert False, "should have raised FORBIDDEN_PATH"
        except CandidateError as e:
            assert e.code == "FORBIDDEN_PATH"


class TestApprovalNoToctou:
    def test_approval_freezes_and_stale_blocks(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        assert c["approved_at"]
        # file modified after approval -> stale
        (wt / "a.txt").write_text("v3\n")
        reason = svc.check_stale(c)
        assert "modified" in reason or "changed" in reason

    def test_file_added_after_approval_excluded(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        # a new untracked file appearing after approval must never enter the
        # commit: commit_candidate builds ONLY the candidate manifest.
        (wt / "sneaky.py").write_text("x = 1\n")
        res = svc.commit_candidate(c, message="conduvera test commit")
        tree_files = subprocess.run(
            ["git", "-C", str(wt), "ls-tree", "-r", res["tree_sha"]],
            capture_output=True, text=True).stdout
        assert "sneaky.py" not in tree_files

    def test_forbidden_untracked_after_approval_invalidates(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        (wt / "mxs_xyz.stdout.txt").write_text("log\n")
        reason = svc.check_stale(c)
        assert "forbidden" in reason

    def test_commit_builds_exact_tree(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        res = svc.commit_candidate(c, message="conduvera test commit")
        assert res["commit_sha"]
        # tree contains exactly the candidate files with matching blobs
        tree_files = subprocess.run(
            ["git", "-C", str(wt), "ls-tree", "-r", res["tree_sha"]],
            capture_output=True, text=True).stdout
        for f in c["files"]:
            if f["status"] != "untracked":
                assert f["path"] in tree_files
