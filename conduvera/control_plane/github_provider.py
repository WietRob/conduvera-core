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
        except OSError as e:
            raise GitHubDeliveryError(
                "GH_LAUNCH", f"gh not launchable: {e}",
                {"argv": argv}) from e
        if proc.returncode != 0:
            # expose the HTTP status so callers can distinguish a 404 from a
            # real failure
            err = (proc.stderr or proc.stdout or "").strip()[:400]
            code = "GH_ERROR"
            import re as _re
            m = _re.search(r"(?:HTTP|graphql)[^\d]*(\d{3})", err, _re.IGNORECASE)
            if m:
                code = f"GH_HTTP_{m.group(1)}"
            raise GitHubDeliveryError(code, err, {"argv": argv})
        try:
            out = proc.stdout.strip()
            if not out:
                return {}
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise GitHubDeliveryError("GH_BAD_JSON",
                                      f"gh returned non-JSON: {proc.stdout[:200]}",
                                      {"argv": argv}) from e

    def _gh_paginated_pages(self, endpoint: str, *,
                            timeout: int = 120) -> list:
        """Fetch EVERY page of a REST endpoint via `gh api --paginate --slurp`.

        The gh CLI combines all pages into one JSON array (NO internal --jq;
        --slurp and --jq are mutually exclusive). Returns the list of page
        payloads; callers parse/validate the per-endpoint shape in Python."""
        if self._dry_run:
            return []
        argv = [self._gh, "api", "--paginate", "--slurp", endpoint]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise GitHubDeliveryError("GH_TIMEOUT", "gh call timed out",
                                      {"argv": argv}) from e
        except OSError as e:
            raise GitHubDeliveryError(
                "GH_LAUNCH", f"gh not launchable: {e}",
                {"argv": argv}) from e
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:400]
            code = "GH_ERROR"
            import re as _re
            m = _re.search(r"(?:HTTP|graphql)[^\d]*(\d{3})", err, _re.IGNORECASE)
            if m:
                code = f"GH_HTTP_{m.group(1)}"
            raise GitHubDeliveryError(code, err, {"argv": argv})
        try:
            out = proc.stdout.strip()
            return json.loads(out) if out else []
        except json.JSONDecodeError as e:
            raise GitHubDeliveryError(
                "GH_BAD_JSON", f"gh returned non-JSON: {proc.stdout[:200]}",
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
        # gh pr create prints the PR URL (no --json flag on create); then
        # re-derive the structured PR data via pr view.
        url = self._gh_text(["pr", "create", "--repo", repository,
                             "--head", head, "--base", base,
                             "--title", title, "--body", body])
        number = 0
        import re as _re
        m = _re.search(r"/pull/(\d+)", url)
        if m:
            number = int(m.group(1))
        if number:
            return self.pr_view(repository, number)
        return {"number": number, "url": url, "headRefName": head,
                "baseRefName": base, "state": "OPEN"}

    def pr_view(self, repository: str, number: int) -> dict:
        if self._dry_run:
            return {"number": number, "url": f"https://github.com/{repository}/pull/{number}",
                    "headRefOid": "0" * 40, "baseRefOid": "0" * 40,
                    "state": "OPEN", "mergeable": "UNKNOWN",
                    "mergeStateStatus": "UNKNOWN", "title": ""}
        return self._gh_json(["pr", "view", str(number), "--repo", repository,
                              "--json",
                              "number,url,state,headRefName,headRefOid,baseRefName,baseRefOid,mergeable,mergeStateStatus,title,isDraft"])

    def list_checks(self, repository: str, head_sha: str,
                    base_branch: str = "main") -> list[dict]:
        """Check runs for a head SHA, combined with legacy commit statuses and
        classified against the base branch's required-check policy.

        Provider/schema failures PROPAGATE (never a clean empty success)."""
        if self._dry_run:
            return []
        checks = self._check_runs(repository, head_sha)
        checks += self._commit_statuses(repository, head_sha)
        requirements, known = self.required_status_checks(repository, base_branch)
        observed = set()
        for c in checks:
            name_v = c.get("name")
            if not isinstance(name_v, str):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-run row (non-string name)")
            name = name_v.lower()
            req_app = requirements.get(name)
            app_id = c.get("app_id")
            if name not in requirements:
                c["required"] = False
            elif req_app is None:
                c["required"] = True  # context-only (unbound) requirement
            elif c.get("app") == "commit-status":
                # a legacy status satisfies only unbound requirements
                c["required"] = False
            else:
                # app-bound: require the run's numeric app id to match
                c["required"] = bool(app_id is not None and app_id == req_app)
            c["required_known"] = known
            if c["required"]:
                observed.add(name)
        missing = sorted(set(requirements) - observed) if known else []
        for c in checks:
            c["required_missing"] = missing
        # a policy with configured requirements but no observed runs must fail
        # closed (never silently green); an unknown policy likewise.
        if not checks:
            if known and requirements:
                return [{
                    "name": "(required checks not started)",
                    "status": "queued", "conclusion": "",
                    "required": True, "required_known": True,
                    "required_missing": missing,
                    "started_at": None, "completed_at": None,
                    "details_url": "", "app": None,
                }]
            if not known:
                return [{
                    "name": "(required policy unknown)",
                    "status": "queued", "conclusion": "",
                    "required": False, "required_known": False,
                    "required_missing": [],
                    "started_at": None, "completed_at": None,
                    "details_url": "", "app": None,
                }]
        return checks

    def _check_runs(self, repository: str, head_sha: str) -> list[dict]:
        """Paginated check-runs (page objects -> .check_runs list), validated."""
        pages = self._gh_paginated_pages(
            f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100")
        runs = []
        for page in pages:
            if not isinstance(page, dict):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-runs page (not an object)")
            pruns = page.get("check_runs", [])
            if not isinstance(pruns, list):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-runs page (check_runs not a list)")
            runs.extend(pruns)
        if not all(isinstance(r, dict) for r in runs):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed check-run row (not an object)")
        out = []
        for r in runs:
            out.append({
                "name": r.get("name") or "",
                "status": r.get("status") or "",
                "conclusion": r.get("conclusion") or "",
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "details_url": r.get("details_url"),
                "app": (r.get("app") or {}).get("name") if isinstance(r.get("app"), dict) else "",
                "app_id": (r.get("app") or {}).get("id") if isinstance(r.get("app"), dict) else None,
                "check_suite_id": (r.get("check_suite") or {}).get("id") if isinstance(r.get("check_suite"), dict) else None,
            })
        return out

    def _commit_statuses(self, repository: str, head_sha: str) -> list[dict]:
        """Legacy combined commit statuses (page objects -> .statuses list),
        validated. Provider failure PROPAGATES so the checks source is stale."""
        if self._dry_run:
            return []
        pages = self._gh_paginated_pages(
            f"repos/{repository}/commits/{head_sha}/status?per_page=100")
        statuses = []
        for page in pages:
            if not isinstance(page, dict):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed commit-status page (not an object)")
            ps = page.get("statuses", [])
            if not isinstance(ps, list):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed commit-status page (statuses not a list)")
            statuses.extend(ps)
        if not all(isinstance(s, dict) for s in statuses):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed commit-status row (not an object)")
        rows = []
        for s in statuses:
            state_v = s.get("state")
            context_v = s.get("context")
            if not isinstance(state_v, str) or not isinstance(context_v, str):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed commit-status row (non-string field)")
            s_state = state_v.lower()
            # never default an unknown/unexpected state to success (non-green)
            if s_state in ("failure", "error"):
                conc = "failure"
            elif s_state in ("success", "neutral", "skipped"):
                conc = "success"
            else:
                conc = "pending"
            rows.append({
                "name": context_v,
                "status": "completed",
                "conclusion": conc,
                "started_at": s.get("updated_at"),
                "completed_at": s.get("updated_at"),
                "details_url": "",
                "app": "commit-status",
                "app_id": None,
                "check_suite_id": "",
            })
        return rows

    def required_status_checks(self, repository: str, base_branch: str) -> tuple:
        """Authoritative branch-protection required-check policy.

        Returns (requirements, known) where requirements is
        {lower_context: app_id_or_None}. After a successful branch-existence
        probe, a protection 404 is the authoritative no-required-checks result
        (known=True); every other provider/schema failure PROPAGATES so the
        checks source becomes stale. app_id == -1 means any app (unbound)."""
        from urllib.parse import quote
        branch = quote(base_branch, safe="")
        # confirm the base branch exists
        try:
            self._gh_text(["api", f"repos/{repository}/branches/{branch}",
                           "--jq", ".name"])
        except GitHubDeliveryError:
            raise
        try:
            pages = self._gh_paginated_pages(
                f"repos/{repository}/branches/{branch}/protection")
        except GitHubDeliveryError as e:
            if getattr(e, "code", "") == "GH_HTTP_404":
                # branch exists + no protection -> authoritative known empty
                return {}, True
            raise
        if not pages:
            return {}, True
        out = pages[0]
        if not isinstance(out, dict):
            raise GitHubDeliveryError(
                "GH_BAD_JSON",
                f"unexpected protection response shape: {type(out).__name__}")
        rsc = out.get("required_status_checks") or {}
        contexts = rsc.get("contexts") if isinstance(rsc, dict) else []
        checks_entries = rsc.get("checks") if isinstance(rsc, dict) else []
        if not contexts:
            contexts = []
        if not checks_entries:
            checks_entries = []
        if not isinstance(contexts, list) or not all(
                isinstance(c, str) for c in contexts):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed protection contexts (not a string list)")
        if not isinstance(checks_entries, list) or not all(
                isinstance(chk, dict) for chk in checks_entries):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed protection checks (not an object list)")
        requirements: dict = {}
        for c in contexts:
            requirements[c.lower()] = None
        for chk in checks_entries:
            if chk.get("context"):
                req_app = chk.get("app_id")
                # app_id == -1 = any app may provide this status (unbound)
                requirements[str(chk["context"]).lower()] = (
                    None if req_app == -1 else req_app)
        return requirements, True

    def list_reviews(self, repository: str, number: int) -> list[dict]:
        if self._dry_run:
            return []
        pages = self._gh_paginated_pages(
            f"repos/{repository}/pulls/{number}/reviews?per_page=100")
        # --slurp on an array endpoint yields a list of page arrays
        if pages and isinstance(pages[0], dict):
            # tolerate a single object page
            pages = [pages]
        flat = []
        for page in pages:
            if not isinstance(page, list):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed reviews page (not a list)",
                    {"path": f"repos/{repository}/pulls/{number}/reviews"})
            flat.extend(page)
        if not all(isinstance(r, dict) for r in flat):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed review row (not an object)",
                {"path": f"repos/{repository}/pulls/{number}/reviews"})
        return flat

    def pull_files(self, repository: str, number: int) -> list[dict]:
        if self._dry_run:
            return []
        pages = self._gh_paginated_pages(
            f"repos/{repository}/pulls/{number}/files?per_page=100")
        flat = []
        for page in pages:
            if not isinstance(page, list):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed pull-files page (not a list)")
            flat.extend(page)
        if not all(isinstance(f, dict) for f in flat):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed pull-file row (not an object)")
        return flat

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
