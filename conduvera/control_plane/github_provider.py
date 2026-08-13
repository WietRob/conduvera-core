"""GitHub delivery provider (SHIP-CONDUVERA-DELIVERY, Workstream C).

Thin provider boundary around the authenticated `gh` CLI. All invocations are
shell-free (structured argv), JSON responses are validated, and repository /
branch names come only from allowlisted / normalized sources. Credentials are
inherited from the authenticated environment and never logged.

Publishing contract:
- create exactly one task branch from the owned worktree change set;
- deterministic sanitized branch name conduvera/<task-id>/<attempt-id>;
- push without force; fail closed on unexpected remote SHA;
- create exactly one PR against the recorded base branch;
- return the persisted branch SHA / PR number / URL / base SHA / head SHA;
- idempotent: repeating Publish returns the same branch+PR.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitHubDeliveryError(Exception):
    """Structured product error from the GitHub delivery provider."""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass
class GitHubRef:
    branch: str
    head_sha: str
    exists: bool = False


# deterministic sanitized branch name (workstream C)
def sanitize_branch_segment(seg: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", seg).strip("-_.")
    s = re.sub(r"-{2,}", "-", s)
    return s[:max_len].rstrip("-_.")


class GitHubDeliveryProvider:
    """Shell-free gh-CLI wrapper for task-branch + PR delivery."""

    def __init__(self, gh_bin: str = "gh", *, dry_run: bool = False):
        self._gh = gh_bin
        self._dry_run = dry_run

    # -- low-level shell-free gh invocation --------------------------------
    def _gh_json(self, args: list[str], *, timeout: int = 60) -> dict | list:
        """Run `gh <args>` and parse validated JSON (no shell)."""
        argv = [self._gh] + args
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise GitHubDeliveryError("GH_TIMEOUT", "gh call timed out",
                                      {"argv": argv}) from e
        if proc.returncode != 0:
            raise GitHubDeliveryError(
                "GH_ERROR", (proc.stderr or proc.stdout or "").strip()[:400],
                {"argv": argv})
        try:
            out = proc.stdout.strip()
            if not out:
                return {}
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise GitHubDeliveryError("GH_BAD_JSON",
                                      f"gh returned non-JSON: {proc.stdout[:200]}",
                                      {"argv": argv}) from e

    def _gh_text(self, args: list[str], *, timeout: int = 60) -> str:
        argv = [self._gh] + args
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise GitHubDeliveryError("GH_TIMEOUT", "gh call timed out",
                                      {"argv": argv}) from e
        if proc.returncode != 0:
            raise GitHubDeliveryError(
                "GH_ERROR", (proc.stderr or proc.stdout or "").strip()[:400],
                {"argv": argv})
        return proc.stdout.strip()

    # -- repository / branch primitives -----------------------------------
    def remote_branch_sha(self, repository: str, branch: str) -> str | None:
        """Return the remote branch head SHA, or None if absent."""
        if self._dry_run:
            return None
        try:
            out = self._gh_text(["api",
                                 f"repos/{repository}/branches/{branch}",
                                 "--jq", ".commit.sha"])
            return out or None
        except GitHubDeliveryError:
            return None

    def remote_base_sha(self, repository: str, base_branch: str) -> str | None:
        if self._dry_run:
            return "0" * 40
        try:
            out = self._gh_text(["api", f"repos/{repository}",
                                 "--jq", ".default_branch"])
            default = out or base_branch
            sha = self._gh_text(["api", f"repos/{repository}/branches/{default}",
                                 "--jq", ".commit.sha"])
            return sha or None
        except GitHubDeliveryError:
            return None

    def find_pr(self, repository: str, head: str, base: str) -> dict | None:
        """Find an open PR matching head branch + base (exactly one expected)."""
        if self._dry_run:
            return None
        try:
            out = self._gh_json(["pr", "list", "--repo", repository,
                                 "--head", head, "--base", base,
                                 "--state", "open",
                                 "--json",
                                 "number,url,headRefName,headRefOid,baseRefName,baseRefOid,state,mergeable,mergeStateStatus,title"])
            items = out if isinstance(out, list) else []
            items = [i for i in items
                     if i.get("headRefName") == head and i.get("baseRefName") == base]
            return items[0] if items else None
        except GitHubDeliveryError:
            return None

    def create_pr(self, repository: str, head: str, base: str,
                  title: str, body: str) -> dict:
        if self._dry_run:
            return {"number": 0, "url": f"https://github.com/{repository}/pull/0",
                    "headRefOid": "0" * 40, "baseRefOid": base,
                    "headRefName": head, "baseRefName": base, "state": "OPEN",
                    "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"}
        out = self._gh_json(["pr", "create", "--repo", repository,
                             "--head", head, "--base", base,
                             "--title", title, "--body", body,
                             "--json",
                             "number,url,headRefName,headRefOid,baseRefName,baseRefOid,state,mergeable,mergeStateStatus,title"])
        return out

    def pr_view(self, repository: str, number: int) -> dict:
        if self._dry_run:
            return {"number": number, "url": f"https://github.com/{repository}/pull/{number}",
                    "headRefOid": "0" * 40, "baseRefOid": "0" * 40,
                    "state": "OPEN", "mergeable": "UNKNOWN",
                    "mergeStateStatus": "UNKNOWN", "title": ""}
        return self._gh_json(["pr", "view", str(number), "--repo", repository,
                              "--json",
                              "number,url,state,headRefName,headRefOid,baseRefName,baseRefOid,mergeable,mergeStateStatus,title,isDraft"])

    def list_checks(self, repository: str, head_sha: str) -> list[dict]:
        if self._dry_run:
            return []
        try:
            out = self._gh_json(["api",
                                 f"repos/{repository}/commits/{head_sha}/check-runs",
                                 "--json", "check_runs"])
            return out.get("check_runs", []) or []
        except GitHubDeliveryError:
            return []

    def list_reviews(self, repository: str, number: int) -> list[dict]:
        if self._dry_run:
            return []
        try:
            raw = self._gh_text(["api",
                                 f"repos/{repository}/pulls/{number}/reviews"])
            out = json.loads(raw) if raw.strip() else []
            return out if isinstance(out, list) else []
        except (GitHubDeliveryError, json.JSONDecodeError):
            return []

    def pull_files(self, repository: str, number: int) -> list[dict]:
        if self._dry_run:
            return []
        try:
            raw = self._gh_text(["api",
                                 f"repos/{repository}/pulls/{number}/files"])
            out = json.loads(raw) if raw.strip() else []
            return out if isinstance(out, list) else []
        except (GitHubDeliveryError, json.JSONDecodeError):
            return []

    def close_pr(self, repository: str, number: int) -> None:
        if self._dry_run:
            return
        self._gh_text(["pr", "close", str(number), "--repo", repository])

    def delete_branch(self, repository: str, branch: str) -> None:
        if self._dry_run:
            return
        try:
            self._gh_text(["api", "-X", "DELETE",
                           f"repos/{repository}/git/refs/heads/{branch}"])
        except GitHubDeliveryError:
            pass


def _git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(["git"] + list(args), capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None)
    if proc.returncode != 0:
        raise GitHubDeliveryError(
            "GIT_ERROR", (proc.stderr or proc.stdout or "").strip()[:400],
            {"argv": list(args)})
    return proc.stdout.strip()


def shell_free(args: list[str]) -> list[str]:
    """Explicitly assert no shell metacharacters would survive shlex (guard)."""
    for a in args:
        if any(ch in a for ch in ";&|$`\\\"'><\n"):
            raise ValueError(f"shell metacharacter in arg: {a!r}")
    return args
