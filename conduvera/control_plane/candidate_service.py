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


def _git_env(args: list[str], env: dict, cwd: str | Path,
             stdin: bytes | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), env=env,
                       capture_output=True, input=stdin,
                       text=(stdin is None))
    if r.returncode != 0:
        raise CandidateError("GIT_FAILED", f"git {' '.join(args)}: {r.stderr.strip()}")
    if stdin is not None:
        return r.stdout.decode() if isinstance(r.stdout, bytes) else r.stdout
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
        # uncommitted changes incl. untracked (standard porcelain lines:
        # "XY path", "R  a.txt -> b.txt", "?? untracked")
        status = _git("status", "--porcelain", "--untracked-files=all",
                      cwd=wt)
        for line in status.splitlines():
            if not line:
                continue
            xy = line[:2]
            rest = line[3:]
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
        # `git diff --name-status -z` yields NUL-separated tokens: the status
        # ("M","A","D","R100","C100","T") and the path are separate tokens;
        # rename/copy emit status, old, new.
        status_map = {"A": "added", "M": "modified", "D": "deleted",
                      "R": "renamed", "C": "copied", "T": "typechange"}
        parts = [p for p in raw.split("\0") if p]
        i = 0
        while i < len(parts):
            tok = parts[i]
            if tok and tok[0].isalpha() and tok[0] in "MADRCUT" \
                    and len(tok) <= 4:
                xy = tok
                path = parts[i + 1] if i + 1 < len(parts) else ""
                i += 2
                if xy[0] in "RC" and i < len(parts):
                    # rename/copy: old path then new path
                    old = path
                    path = parts[i]
                    i += 1
                    entries[path] = {
                        "xy": xy, "src": old,
                        "status": status_map.get(xy[0], "modified"),
                    }
                else:
                    entries[path] = {
                        "xy": xy, "src": path,
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
            out = _git("ls-files", "-s", "--", rel, cwd=wt)
            if out.strip():
                return out.split()[0].split(":")[0]
        except CandidateError:
            pass
        # untracked/new file: derive mode from the actual filesystem mode
        p = wt / rel
        try:
            st = p.stat()
            if st.st_mode & 0o111:
                return "100755"
            if p.is_symlink():
                return "120000"
        except OSError:
            pass
        return "100644"

    def _operation_of(self, info: dict) -> str:
        status = info.get("status", "")
        xy = info.get("xy", "")
        if status == "untracked":
            return "add"
        if xy and xy[0] == "R":
            return "rename"
        if xy and xy[0] == "C":
            return "copy"
        if xy and xy[0] == "T":
            return "type_change"
        # deletion (staged "D " or unstaged " D")
        if status == "deleted" or (len(xy) >= 2 and xy[1] == "D") \
                or (xy and xy[0] == "D"):
            return "delete"
        if status in ("added", "staged") and len(xy) >= 2 and xy[1] == "A":
            return "add"
        return "modify"

    @staticmethod
    def _manifest_hash(files: list, excluded: list) -> str:
        """Deterministic SHA-256 over the complete ordered operation set."""
        canonical = {
            "operations": sorted(files, key=lambda f: f["path"]),
            "excluded": sorted(excluded, key=lambda e: e["path"]),
        }
        return hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()).hexdigest()

    def _canonical_patch(self, files: list, wt: Path) -> bytes:
        """Deterministic canonical patch binding the complete candidate,
        including originally-untracked content, so a non-empty candidate can
        never carry the empty hash e3b0c442..."""
        out = []
        for f in sorted(files, key=lambda f: f["path"]):
            rel = f["path"]
            op = f["operation"]
            target = f.get("symlink_target") or ""
            content = target.encode() if f.get("symlink_target") else ""
            if not f.get("symlink_target") and op != "delete":
                p = wt / rel
                try:
                    content = p.read_bytes()
                except OSError:
                    content = b""
            out.append(f"{op}\t{rel}\t{f.get('old_path','')}\t"
                       f"{f.get('mode_before','')}\t{f.get('mode_after','')}\t")
            out.append(content)
        return b"\n".join(x if isinstance(x, bytes) else x.encode()
                          for x in out)

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
        excluded = []
        for rel, info in sorted(inv.items()):
            path = wt / rel
            decision = self._decide(rel, info["status"])
            if not decision["allow"]:
                if decision.get("exclude"):
                    excluded.append({"path": rel, "reason": decision["reason"]})
                else:
                    denied.append({"path": rel, "reason": decision["reason"]})
                continue
            op = self._operation_of(info)
            is_file = path.is_file()
            is_symlink = path.is_symlink()
            # content_sha256 is a REAL SHA-256 over the approved bytes; for a
            # symlink we hash the link-target bytes WITHOUT dereferencing.
            content = b""
            if is_symlink:
                try:
                    content = os.readlink(path).encode()
                except OSError:
                    content = b""
            elif is_file:
                content = path.read_bytes()
            content_sha256 = hashlib.sha256(content).hexdigest()
            git_blob_oid = ""
            if is_file and not is_symlink:
                git_blob_oid = _git("hash-object", str(path), cwd=wt).strip()
            st = path.stat() if (is_file or is_symlink) else None
            files.append({
                "operation": op,
                "path": rel,
                "old_path": info["src"] if info["src"] != rel else "",
                "mode_before": "",
                "mode_after": self._mode_of(wt, rel) if (is_file or is_symlink) else "100644",
                "content_sha256": content_sha256,
                "git_blob_oid": git_blob_oid,
                "symlink_target": os.readlink(path) if is_symlink else "",
                "size": st.st_size if st else 0,
                "binary": self._is_binary(path),
                "additions": 0,
                "deletions": 0,
            })

        # a forbidden path in the deliverable set fails closed
        if denied:
            raise CandidateError("FORBIDDEN_PATH",
                                 "forbidden path(s): " + ", ".join(d["path"] for d in denied))

        # Phase E (worktree fidelity): a PublishCandidate must carry a real,
        # non-empty changeset. Logs/prose alone never become a candidate.
        if not files:
            raise CandidateError(
                "EMPTY_CHANGESET",
                "worktree has no file changes relative to base_commit "
                f"{base_commit}; cannot publish a candidate from logs alone")

        # exact hashes (DOD canonical manifest)
        index_tree = _git("write-tree", cwd=wt)
        worktree_tree = _git("rev-parse", "HEAD^{tree}", cwd=wt)
        head_sha = _git("rev-parse", "HEAD", cwd=wt)
        # canonical_manifest_sha256 binds ALL operations deterministically
        canonical_manifest_sha256 = self._manifest_hash(files, excluded)
        # canonical_patch_sha256 binds the COMPLETE candidate including
        # originally-untracked content (never base..HEAD, never empty when
        # the candidate is non-empty)
        patch_blob = self._canonical_patch(files, wt)
        canonical_patch_sha256 = hashlib.sha256(patch_blob).hexdigest()

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
            "canonical_manifest_sha256": canonical_manifest_sha256,
            "canonical_patch_sha256": canonical_patch_sha256,
            "files": files,
            "excluded_paths": excluded,
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

    # -- path policy (DOD path policy) ------------------------------------
    # runtime exclusions remain explicit and path-specific; legitimate approved
    # paths (.github/workflows/*, .github/curaops-allowlist.yaml, .gitignore)
    # are NEVER excluded as untracked metadata.
    RUNTIME_EXCLUDE_PARTS = (
        "mxs_",  # session stdout/stderr logs (checked below)
        "fixture-status.json",
        ".ai/worktrees/",
        ".curaops/control/",
        "outbox.jsonl",
        "control-plane.sock",
        # pure runtime artefacts — never code changes, always excluded
        "__pycache__/", ".pyc", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
        ".hermes/", "hermes-home/",
    )

    def _decide(self, rel: str, status: str) -> dict:
        low = rel.lower()
        # 1) session-log runtime artefacts are EXCLUDED (never published,
        #    recorded in the EvidenceBundle) — they do not block the change
        if low.startswith("mxs_") and (low.endswith(".stdout.txt")
                                       or low.endswith(".stderr.txt")):
            return {"allow": False, "exclude": True,
                    "reason": "session log excluded"}
        # 2) explicit runtime-path exclusions (never published)
        for part in self.RUNTIME_EXCLUDE_PARTS:
            if part.lower() in low:
                return {"allow": False, "exclude": True,
                        "reason": f"runtime path excluded ({part})"}
        # 3) forbidden secrets/large-binary patterns fail closed
        if _is_forbidden(rel):
            return {"allow": False, "reason": "FORBIDDEN_PATH"}
        # 4) everything else — including legitimate untracked additions such
        #    as .github/workflows/*, .github/curaops-allowlist.yaml, .gitignore,
        #    and real feature files — is ALLOWED
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
        # re-hash every candidate file (content_sha256 is real SHA-256)
        for f in candidate.get("files", []):
            rel = f["path"]
            op = f.get("operation", "modify")
            p = wt / rel
            # delete: the file is intentionally absent in the worktree
            if op == "delete":
                if p.exists():
                    return f"file not deleted: {rel}"
                continue
            if f.get("symlink_target") is not None and f.get("symlink_target") != "":
                # symlink: hash link-target bytes without dereferencing
                try:
                    cur = os.readlink(p).encode()
                except OSError:
                    return f"file missing: {rel}"
                if hashlib.sha256(cur).hexdigest() != f.get("content_sha256"):
                    return f"file modified: {rel}"
                continue
            if not p.is_file():
                return f"file missing: {rel}"
            if hashlib.sha256(p.read_bytes()).hexdigest() != f.get("content_sha256"):
                return f"file modified: {rel}"
        # evidence re-hash
        for ref, h in (candidate.get("evidence_hashes") or {}).items():
            ev = self.evidence_store.get(ref)
            if ev is None or _sha256_bytes(json.dumps(ev, sort_keys=True).encode()) != h:
                return f"evidence changed: {ref}"
        # a new forbidden/secret untracked artefact must not silently enter;
        # runtime paths (mxs_*, fixture-status, .ai/worktrees, .curaops/control)
        # are EXCLUDED, not stale — they never enter the commit
        for rel, info in self._pathspec_inventory(wt, "").items():
            if info["status"] != "untracked":
                continue
            if self._decide(rel, "untracked")["allow"] is False \
                    and self._decide(rel, "untracked").get("exclude") is True:
                continue  # excluded runtime path, not stale
            if _is_forbidden(rel):
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

        # build a temporary index that starts from the base tree (so existing
        # repository content is preserved) and applies EXACTLY the candidate
        # operations (never `git add -A`)
        with tempfile.TemporaryDirectory(prefix="cand-idx-") as tmp:
            idx = str(Path(tmp) / "index")
            env = dict(os.environ, GIT_INDEX_FILE=idx)
            # seed the index from the recorded base tree (preserve existing files)
            _git_env(["read-tree", f"{base}^{{tree}}"], env, wt)
            for f in candidate.get("files", []):
                rel = f["path"]
                op = f.get("operation", "modify")
                p = wt / rel
                mode = f.get("mode_after") or "100644"
                # delete: remove from the index
                if op == "delete":
                    _git_env(["update-index", "--remove", "--", rel], env, wt)
                    continue
                # symlink: hash the link-target bytes WITHOUT dereferencing
                if f.get("symlink_target") not in (None, ""):
                    if not p.is_symlink():
                        raise CandidateError("CANDIDATE_STALE",
                                             f"expected symlink: {rel}")
                    target = os.readlink(p)
                    blob = _git_env(
                        ["hash-object", "-w", "--stdin"], env, wt,
                        stdin=f"link\0{target}".encode()).strip()
                    mode = "120000"
                    _git_env(["update-index", "--add", "--cacheinfo",
                              f"{mode},{blob},{rel}"], env, wt)
                    continue
                if not p.is_file():
                    raise CandidateError("CANDIDATE_STALE", f"file missing: {rel}")
                # rename/copy: remove the old path first
                old = f.get("old_path") or ""
                if op in ("rename", "copy") and old and old != rel:
                    _git_env(["update-index", "--remove", "--", old], env, wt)
                # exact blob + mode
                blob = _git_env(["hash-object", "-w", "--path", rel, str(p)],
                                env, wt).strip()
                _git_env(["update-index", "--add", "--cacheinfo",
                          f"{mode},{blob},{rel}"], env, wt)
            tree = _git_env(["write-tree"], env, wt).strip()
        # create the commit on top of base with the manifest tree
        commit = _git("commit-tree", tree, "-p", base, "-m", message, cwd=wt)
        return {"commit_sha": commit.strip(), "tree_sha": tree.strip()}

    def candidate_branch(self, candidate: dict, delivery_id: str,
                         attempt_id: str) -> str:
        task = re.sub(r"[^A-Za-z0-9._-]", "-", candidate.get("job_id", "job"))
        att = re.sub(r"[^A-Za-z0-9._-]", "-", attempt_id)
        return f"conduvera/{task}/{att}"
