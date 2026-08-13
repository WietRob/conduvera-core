"""PublishCandidateService (TRUSTED-FEATURE-DELIVERY, WS B/C).

Builds an immutable PublishCandidate manifest from the exact selected Attempt
and the owned worktree, freezes it on approval, and publishes the EXACT
manifest atomically (temporary index + commit-tree, never `git add -A`).

Candidate creation inventory covers tracked/staged/unstaged/untracked paths
with an explicit allow/deny decision, content hashes, exact diff/tree hashes,
EvidenceBundle hashes and named test/gate outcomes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

CANDIDATE_SCHEMA = "CONDUVERA-PUBLISH-CANDIDATE-1.0.0"
GATE_CONTRACT = "CONDUVERA-DELIVERY-GATE-1.0.0"


class CandidateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str, cwd: str | Path) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True)
    if r.returncode != 0:
        raise CandidateError("GIT_FAILED", f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def _git_env(args: list[str], env: dict, cwd: str | Path) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise CandidateError("GIT_FAILED", f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


# runtime/session artefacts that must never be delivered to a public repo
_FORBIDDEN = (
    ".git/", ".git$", ".env", "secrets.env", ".venv/", "__pycache__/",
    "node_modules/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    "*.pyc", "*.log", ".local/", "*.secret", "credentials", ".ssh/",
    ".config/", "coverage/", "dist/", "build/", ".hermes/",
    "fixture-status.json", "fixture_out", "*.stdout.txt", "*.stderr.txt",
    "mxs_", ".ai/worktrees/", ".ai/state/", ".worktrees/", ".sisyphus/",
    "control-plane.sock", "outbox.jsonl",
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential)\s*[=:]\s*\S{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"LITELLM_[A-Z_]+"),
)


def _is_forbidden(path: str) -> bool:
    low = path.lower()
    return any(part in low for part in _FORBIDDEN)


def _blob_sha(path: str | Path) -> str:
    # git blob hash = sha1("blob <len>\0" + content)
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class PublishCandidateService:
    def __init__(self, store, evidence_store, *, worktree_root: str | Path):
        self.store = store
        self.evidence_store = evidence_store
        self.worktree_root = Path(worktree_root)

    # -- inventory ---------------------------------------------------------
    def _pathspec_inventory(self, wt: Path, base_commit: str) -> dict:
        """Full inventory of tracked/staged/unstaged/untracked paths relative
        to base_commit. `git status --porcelain` shows uncommitted; `git diff
        base_commit` adds committed changes since the owned base."""
        entries = {}
        # committed changes since the base
        if base_commit:
            try:
                diff = _git("diff", "--name-status", "-z", base_commit, "HEAD",
                            cwd=wt)
                self._parse_diff(entries, diff)
            except CandidateError:
                pass
        # uncommitted changes incl. untracked
        status = _git("status", "--porcelain", "-z", "--untracked-files=all",
                      cwd=wt)
        for rec in status.split("\0"):
            if not rec:
                continue
            xy = rec[:2]
            rest = rec[3:]
            if " -> " in rest:
                src, dst = rest.split(" -> ", 1)
            else:
                src, dst = rest, rest
            entries[dst] = {
                "xy": xy,
                "src": src,
                "status": self._status_word(xy),
            }
        return entries

    def _parse_diff(self, entries: dict, raw: str) -> None:
        # `git diff --name-status -z` yields NUL-separated tokens; the status
        # letter(s) and the path are separate tokens: "M", "a.txt", "A",
        # "b.py", ... (rename/copy emit "R100", "old", "new").
        status_map = {"A": "added", "M": "modified", "D": "deleted",
                      "R": "renamed", "C": "copied", "T": "typechange"}
        parts = [p for p in raw.split("\0") if p]
        i = 0
        while i < len(parts):
            tok = parts[i]
            # a status token is a short alpha/num string (e.g. M, A, R100)
            if (tok[0].isalpha() and len(tok) <= 4) and (
                    tok[0] in "MADRCUT"):
                xy = tok
                # next token(s) are the path(s)
                path = parts[i + 1] if i + 1 < len(parts) else ""
                i += 2
                # rename/copy: skip the extra "score" is in xy; second path
                if xy[0] in "RC" and i < len(parts):
                    i += 1
                entries[path] = {
                    "xy": xy,
                    "src": path,
                    "status": status_map.get(xy[0], "modified"),
                }
            else:
                i += 1


    @staticmethod
    def _status_word(xy: str) -> str:
        x, y = xy[0], xy[1]
        if x == "?":
            return "untracked"
        if y != " ":
            return "staged"
        if x in ("M", "A", "D", "R", "C", "T"):
            return "unstaged"
        return "clean"

    def _mode_of(self, wt: Path, rel: str) -> str:
        try:
            return _git("ls-files", "-s", "--", rel, cwd=wt).split()[0].split(":")[0] \
                if _git("ls-files", "-s", "--", rel, cwd=wt).strip() else "100644"
        except CandidateError:
            return "100644"

    def build_candidate(self, *, job_id, attempt_id, session_id, delivery_id,
                        repo_id, github_repository, base_branch, base_commit,
                        worktree, evidence_refs, named_tests, named_gates,
                        approved_by="") -> dict:
        wt = Path(worktree)
        if not wt.is_dir() or not (wt / ".git").exists():
            raise CandidateError("WORKTREE_NOT_OWNED", f"worktree missing: {worktree}")
        inv = self._pathspec_inventory(wt, base_commit)

        files = []
        denied = []
        for rel, info in sorted(inv.items()):
            path = wt / rel
            decision = self._decide(rel, info["status"])
            if not decision["allow"]:
                denied.append({"path": rel, "reason": decision["reason"]})
                continue
            blob_sha = _blob_sha(path) if path.is_file() else ""
            st = path.stat() if path.is_file() else None
            files.append({
                "path": rel,
                "status": info["status"],
                "old_path": info["src"] if info["src"] != rel else "",
                "mode": info["status"] == "untracked" and "100644" or self._mode_of(wt, rel),
                "blob_sha256": blob_sha,
                "size": st.st_size if st else 0,
                "binary": self._is_binary(path),
                "additions": 0,
                "deletions": 0,
            })

        # if any forbidden path is in the deliverable set -> fail closed
        if denied:
            raise CandidateError("FORBIDDEN_PATH",
                                 "forbidden path(s): " + ", ".join(d["path"] for d in denied))

        # exact hashes
        index_tree = _git("write-tree", cwd=wt)
        worktree_tree = _git("rev-parse", "HEAD^{tree}", cwd=wt)
        diff = _git("diff", "--binary", base_commit, "HEAD", cwd=wt) \
            if base_commit else ""
        diff_sha = _sha256_bytes(diff.encode())
        head_sha = _git("rev-parse", "HEAD", cwd=wt)

        # evidence hashes
        evidence_hashes = {}
        for ref in evidence_refs or []:
            ev = self.evidence_store.get(ref)
            if ev is not None:
                evidence_hashes[ref] = _sha256_bytes(
                    json.dumps(ev, sort_keys=True).encode())

        candidate = {
            "candidate_id": f"cand_{uuid.uuid4().hex[:16]}",
            "schema_version": CANDIDATE_SCHEMA,
            "delivery_id": delivery_id,
            "job_id": job_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "repo_id": repo_id,
            "github_repository": github_repository,
            "base_branch": base_branch,
            "base_commit": base_commit,
            "worktree": str(wt),
            "worktree_head_sha": head_sha,
            "worktree_tree_sha": worktree_tree,
            "index_tree_sha": index_tree,
            "diff_sha256": diff_sha,
            "files": files,
            "evidence_refs": evidence_refs or [],
            "evidence_hashes": evidence_hashes,
            "named_test_results": named_tests or [],
            "named_gate_results": named_gates or [],
            "gate_contract_version": GATE_CONTRACT,
            "created_at": _utc(),
            "approved_at": None,
            "approved_by": approved_by or "",
            "invalidated_at": None,
            "invalidation_reason": "",
        }
        self.store.put(candidate)
        return candidate

    def _decide(self, rel: str, status: str) -> dict:
        if _is_forbidden(rel):
            return {"allow": False, "reason": "FORBIDDEN_PATH"}
        if status == "untracked" and not rel.startswith("."):
            return {"allow": True, "reason": "untracked"}
        return {"allow": True, "reason": ""}

    def _is_binary(self, path: Path) -> bool:
        if not path.is_file():
            return False
        data = path.read_bytes()
        return b"\0" in data[:1024]

    # -- approval ----------------------------------------------------------
    def approve(self, candidate_id: str, approved_by: str) -> dict:
        c = self.store.get(candidate_id)
        if c is None:
            raise CandidateError("UNKNOWN_CANDIDATE", f"unknown candidate {candidate_id}")
        if c.get("approved_at"):
            return c
        if c.get("invalidated_at"):
            raise CandidateError("CANDIDATE_INVALID", c.get("invalidation_reason", ""))
        c["approved_at"] = _utc()
        c["approved_by"] = approved_by
        self.store.put(c)
        return c

    def check_stale(self, candidate: dict) -> str:
        """Return invalidation reason if the worktree/evidence diverged from
        the frozen manifest, else '' (still valid)."""
        wt = Path(candidate["worktree"])
        try:
            head = _git("rev-parse", "HEAD", cwd=wt)
            tree = _git("rev-parse", "HEAD^{tree}", cwd=wt)
        except CandidateError:
            return "worktree unavailable"
        if head != candidate.get("worktree_head_sha"):
            return "worktree head changed"
        if tree != candidate.get("worktree_tree_sha"):
            return "worktree tree changed"
        # re-hash every candidate file
        for f in candidate.get("files", []):
            p = wt / f["path"]
            if not p.is_file():
                return f"file missing: {f['path']}"
            if _blob_sha(p) != f.get("blob_sha256"):
                return f"file modified: {f['path']}"
        # evidence re-hash
        for ref, h in (candidate.get("evidence_hashes") or {}).items():
            ev = self.evidence_store.get(ref)
            if ev is None or _sha256_bytes(json.dumps(ev, sort_keys=True).encode()) != h:
                return f"evidence changed: {ref}"
        # a new forbidden untracked artefact must not silently enter
        for rel, info in self._pathspec_inventory(wt, "").items():
            if info["status"] == "untracked" and _is_forbidden(rel):
                return f"forbidden untracked artefact: {rel}"
        return ""

    # -- atomic exact-changeset commit (WS C) ------------------------------
    def commit_candidate(self, candidate: dict, *, message: str) -> dict:
        """Commit EXACTLY the candidate manifest using a temporary index and
        commit-tree. Never `git add -A`. Returns {commit_sha, tree_sha}."""
        if not candidate.get("approved_at"):
            raise CandidateError("CANDIDATE_NOT_APPROVED",
                                 "candidate must be approved before publish")
        stale = self.check_stale(candidate)
        if stale:
            raise CandidateError("CANDIDATE_STALE", stale)

        wt = Path(candidate["worktree"])
        # resolve the base tree from the recorded base commit
        base = candidate.get("base_commit") or ""
        if base:
            _git("rev-parse", f"{base}^{{tree}}", cwd=wt)  # existence check
        else:
            base = _git("rev-parse", "HEAD", cwd=wt).strip()

        # build a temporary index that contains EXACTLY the candidate files
        with tempfile.TemporaryDirectory(prefix="cand-idx-") as tmp:
            idx = str(Path(tmp) / "index")
            env = dict(os.environ, GIT_INDEX_FILE=idx)
            for f in candidate.get("files", []):
                rel = f["path"]
                p = wt / rel
                if not p.is_file():
                    raise CandidateError("CANDIDATE_STALE", f"file missing: {rel}")
                # hash-object -w writes the blob into the object db and returns
                # its exact git sha; use that (not a re-derived sha) so the
                # index references an object that actually exists.
                blob = _git_env(["hash-object", "-w", "--path", rel, str(p)],
                                env, wt).strip()
                _git_env(["update-index", "--add", "--cacheinfo",
                          f"{f.get('mode') or '100644'},{blob},{rel}"],
                         env, wt)
            tree = _git_env(["write-tree"], env, wt).strip()
        # create the commit on top of base with the manifest tree
        commit = _git("commit-tree", tree, "-p", base, "-m", message, cwd=wt)
        return {"commit_sha": commit.strip(), "tree_sha": tree.strip()}

    def candidate_branch(self, candidate: dict, delivery_id: str,
                         attempt_id: str) -> str:
        task = re.sub(r"[^A-Za-z0-9._-]", "-", candidate.get("job_id", "job"))
        att = re.sub(r"[^A-Za-z0-9._-]", "-", attempt_id)
        return f"conduvera/{task}/{att}"
