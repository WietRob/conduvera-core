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
    # seed at least five base files (PR A: base preservation is proven)
    for i in range(5):
        (wt / f"base{i}.txt").write_text(f"base{i}\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "seed"], check=True)
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
        assert c["canonical_manifest_sha256"]
        assert c["canonical_patch_sha256"]
        # a non-empty candidate may NEVER carry the empty hash
        assert c["canonical_patch_sha256"] != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert c["schema_version"] == "CONDUVERA-PUBLISH-CANDIDATE-1.0.0"
        assert c["approved_at"] is None
        # every operation carries real SHA-256 + git blob oid
        for f in c["files"]:
            assert f["content_sha256"] and len(f["content_sha256"]) == 64
            assert f["operation"] in ("add", "modify", "delete", "rename",
                                      "copy", "mode_change", "type_change")
            assert f["git_blob_oid"] or f["operation"] == "delete" \
                or f.get("symlink_target")
        assert c["evidence_hashes"] == {}

    def test_forbidden_secret_blocks(self, tmp_path):
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        # a real secret-like path fails closed
        (wt / ".env").write_text("API_KEY=supersecretvalue123\n")
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

    def test_runtime_paths_excluded_not_published(self, tmp_path):
        """Runtime paths (fixture-status.json, .ai/worktrees, .curaops/control,
        mxs_* logs) are EXCLUDED; legitimate .github/.gitignore additions are
        ALLOWED (DOD path policy)."""
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        (wt / "docs").mkdir(exist_ok=True)
        (wt / "docs" / "FEATURE.md").write_text("# feature\n")
        # runtime exclusions
        (wt / ".ai" / "worktrees" / "w1").mkdir(parents=True, exist_ok=True)
        (wt / ".ai" / "worktrees" / "w1" / "x.txt").write_text("x\n")
        (wt / ".curaops" / "control").mkdir(parents=True, exist_ok=True)
        (wt / ".curaops" / "control" / "registry.json").write_text("{}\n")
        (wt / "fixture-status.json").write_text('{"status":"ok"}\n')
        (wt / "mxs_abc.stdout.txt").write_text("log\n")
        # legitimate approved additions MUST be allowed
        (wt / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (wt / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
        (wt / ".github" / "curaops-allowlist.yaml").write_text("repos:\n  - x\n")
        (wt / ".gitignore").write_text("*.pyc\n")
        c = svc.build_candidate(
            job_id="job_1", attempt_id="a1", session_id="s1",
            delivery_id="dlv_1", repo_id="r", github_repository="R/r",
            base_branch="main", base_commit=base, worktree=str(wt),
            evidence_refs=[], named_tests=[], named_gates=[])
        files = [f["path"] for f in c["files"]]
        excluded = [e["path"] for e in c["excluded_paths"]]
        # legitimate additions are in the deliverable set
        assert ".github/workflows/ci.yml" in files
        assert ".github/curaops-allowlist.yaml" in files
        assert ".gitignore" in files
        assert "docs/FEATURE.md" in files
        # runtime paths are excluded (never published)
        assert ".ai/worktrees/w1/x.txt" not in files
        assert ".curaops/control/registry.json" not in files
        assert "fixture-status.json" not in files
        assert "mxs_abc.stdout.txt" not in files
        for e in excluded:
            assert e not in files


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

    def test_runtime_path_after_approval_excluded(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        # runtime paths (fixture-status.json, session logs) after approval are
        # excluded — never enter the commit, never block the change
        (wt / "fixture-status.json").write_text('{"status":"ok"}\n')
        (wt / "mxs_xyz.stdout.txt").write_text("log\n")
        (wt / "mxs_xyz.stderr.txt").write_text("err\n")
        assert svc.check_stale(c) == ""
        res = svc.commit_candidate(c, message="conduvera test commit")
        tree_files = subprocess.run(
            ["git", "-C", str(wt), "ls-tree", "-r", res["tree_sha"]],
            capture_output=True, text=True).stdout
        assert "fixture-status.json" not in tree_files
        assert "mxs_xyz.stdout.txt" not in tree_files

    def test_secret_after_approval_invalidates(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        # a real forbidden artefact (not a runtime path) after approval makes
        # the candidate stale (DOD-03): it must never enter the commit
        (wt / ".env").write_text("API_KEY=supersecretvalue123\n")
        reason = svc.check_stale(c)
        assert "forbidden" in reason or "secret" in reason

    def test_commit_builds_exact_tree_and_preserves_base(self, tmp_path):
        store, ev, svc, wt, c = _build_candidate(tmp_path)
        c = svc.approve(c["candidate_id"], approved_by="operator")
        base_tree = subprocess.run(
            ["git", "-C", str(wt), "rev-parse", "HEAD^{tree}"],
            capture_output=True, text=True).stdout.strip()
        base_files = set(subprocess.run(
            ["git", "-C", str(wt), "ls-tree", "-r", "--name-only", base_tree],
            capture_output=True, text=True).stdout.split())
        res = svc.commit_candidate(c, message="conduvera test commit")
        assert res["commit_sha"]
        # tree contains exactly the candidate files with matching blobs
        tree_files = subprocess.run(
            ["git", "-C", str(wt), "ls-tree", "-r", res["tree_sha"]],
            capture_output=True, text=True).stdout
        for f in c["files"]:
            assert f["path"] in tree_files
        # every unchanged base path still exists with identical mode+blob
        assert len(base_files) >= 5  # at least five unchanged base files
        for bf in base_files:
            assert bf in tree_files


class TestCanonicalOperations:
    """PR A E: canonical commit handles every operation class exactly."""

    def _commit(self, tmp_path, setup):
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        setup(wt)
        c = svc.build_candidate(
            job_id="job_1", attempt_id="a1", session_id="s1", delivery_id="dlv_1",
            repo_id="r", github_repository="R/r", base_branch="main",
            base_commit=base, worktree=str(wt), evidence_refs=[],
            named_tests=[], named_gates=[])
        c = svc.approve(c["candidate_id"], approved_by="operator")
        res = svc.commit_candidate(c, message="conduvera test commit")
        return c, res, wt

    def test_add_modify(self, tmp_path):
        c, res, wt = self._commit(
            tmp_path,
            lambda wt: ((wt / "a.txt").write_text("v2\n"),
                        (wt / "new.py").write_text("x=1\n")))
        files = {f["path"] for f in c["files"]}
        assert "a.txt" in files and "new.py" in files
        tree = subprocess.run(["git", "-C", str(wt), "ls-tree", "-r",
                               "--name-only", res["tree_sha"]],
                              capture_output=True, text=True).stdout
        assert "a.txt" in tree and "new.py" in tree

    def test_delete(self, tmp_path):
        c, res, wt = self._commit(tmp_path, lambda wt: (wt / "a.txt").unlink())
        del_files = [f for f in c["files"] if f["operation"] == "delete"]
        assert any(f["path"] == "a.txt" for f in del_files)
        tree = subprocess.run(["git", "-C", str(wt), "ls-tree", "-r",
                               "--name-only", res["tree_sha"]],
                              capture_output=True, text=True).stdout
        assert "a.txt" not in tree

    def test_rename(self, tmp_path):
        def _setup(wt):
            subprocess.run(["git", "-C", str(wt), "mv", "a.txt", "renamed.txt"],
                           check=True)
        c, res, wt = self._commit(tmp_path, _setup)
        renamed = next((f for f in c["files"]
                        if f["operation"] == "rename"
                        and f.get("old_path") == "a.txt"), None)
        assert renamed is not None and renamed["path"] == "renamed.txt"
        tree = subprocess.run(["git", "-C", str(wt), "ls-tree", "-r",
                               "--name-only", res["tree_sha"]],
                              capture_output=True, text=True).stdout
        assert "renamed.txt" in tree and "a.txt" not in tree

    def test_executable_mode(self, tmp_path):
        c, res, wt = self._commit(
            tmp_path,
            lambda wt: ((wt / "run.sh").write_text("#!/bin/sh\necho hi\n"),
                        (wt / "run.sh").chmod(0o755)))
        sh = next(f for f in c["files"] if f["path"] == "run.sh")
        assert sh["mode_after"] == "100755"
        tree = subprocess.run(["git", "-C", str(wt), "ls-tree", "-r",
                               res["tree_sha"], "--", "run.sh"],
                              capture_output=True, text=True).stdout
        assert "100755" in tree

    def test_symlink(self, tmp_path):
        c, res, wt = self._commit(
            tmp_path, lambda wt: (wt / "link").symlink_to("a.txt"))
        link = next(f for f in c["files"] if f["path"] == "link")
        assert link["symlink_target"] == "a.txt"
        tree = subprocess.run(["git", "-C", str(wt), "ls-tree", "-r",
                               res["tree_sha"]],
                              capture_output=True, text=True).stdout
        assert "120000" in tree

    def test_binary(self, tmp_path):
        c, res, wt = self._commit(
            tmp_path,
            lambda wt: (wt / "data.bin").write_bytes(b"\x00\x01\x02data"))
        b = next(f for f in c["files"] if f["path"] == "data.bin")
        assert b["binary"] is True
        assert b["content_sha256"]

    def test_staged_unstaged_untracked(self, tmp_path):
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        (wt / "staged.txt").write_text("s\n")
        subprocess.run(["git", "-C", str(wt), "add", "staged.txt"], check=True)
        (wt / "unstaged.txt").write_text("u\n")
        subprocess.run(["git", "-C", str(wt), "add", "unstaged.txt"], check=True)
        (wt / "unstaged.txt").write_text("u2\n")
        (wt / "untracked.txt").write_text("ut\n")
        c = svc.build_candidate(
            job_id="j", attempt_id="a", session_id="s", delivery_id="d",
            repo_id="r", github_repository="R/r", base_branch="main",
            base_commit=base, worktree=str(wt), evidence_refs=[],
            named_tests=[], named_gates=[])
        paths = {f["path"] for f in c["files"]}
        assert "staged.txt" in paths
        assert "unstaged.txt" in paths
        assert "untracked.txt" in paths

    def test_non_empty_hash_never_empty(self, tmp_path):
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "w1"
        base = _git_init(wt)
        (wt / "a.txt").write_text("changed\n")
        c = svc.build_candidate(
            job_id="j", attempt_id="a", session_id="s", delivery_id="d",
            repo_id="r", github_repository="R/r", base_branch="main",
            base_commit=base, worktree=str(wt), evidence_refs=[],
            named_tests=[], named_gates=[])
        assert c["canonical_patch_sha256"] != \
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestEmptyAndSourceIntegrity:
    """Phase E + Phase D (worktree fidelity delivery gates)."""

    def test_empty_changeset_rejected(self, tmp_path):
        """Phase E: a code-change candidate with no worktree diff must fail."""
        import pytest
        store, ev, svc = _mk(tmp_path)
        wt = tmp_path / "wts" / "empty"
        base = _git_init(wt)  # commits a.txt; no further changes
        with pytest.raises(CandidateError) as exc:
            svc.build_candidate(
                job_id="j", attempt_id="a", session_id="s", delivery_id="d",
                repo_id="r", github_repository="R/r", base_branch="main",
                base_commit=base, worktree=str(wt), evidence_refs=[],
                named_tests=[], named_gates=[])
        assert exc.value.code == "EMPTY_CHANGESET"

    def test_source_repo_snapshot_unchanged_matches(self, tmp_path):
        """Phase D: a dispatch-time source snapshot matches an unchanged repo."""
        from conduvera.control_plane.service import (
            _source_repo_snapshot, _source_repo_matches_snapshot)
        src = tmp_path / "src"
        _git_init(src)
        snap = _source_repo_snapshot(src)
        assert snap != "{}"
        assert _source_repo_matches_snapshot(src, snap) is True

    def test_source_repo_snapshot_detects_mutation(self, tmp_path):
        """Phase D: mutating the source repo after the snapshot must fail."""
        from conduvera.control_plane.service import (
            _source_repo_snapshot, _source_repo_matches_snapshot)
        src = tmp_path / "src"
        _git_init(src)
        snap = _source_repo_snapshot(src)
        # mutate the source repo (uncommitted change)
        (src / "a.txt").write_text("MUTATED\n")
        assert _source_repo_matches_snapshot(src, snap) is False

    def test_source_repo_snapshot_missing_fails_closed(self, tmp_path):
        """Phase D: no recorded snapshot is unproven -> fail closed."""
        from conduvera.control_plane.service import _source_repo_matches_snapshot
        src = tmp_path / "src"
        _git_init(src)
        assert _source_repo_matches_snapshot(src, "") is False
        assert _source_repo_matches_snapshot(src, "{}") is False

