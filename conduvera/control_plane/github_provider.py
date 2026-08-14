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
            if not out:
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "gh returned empty --paginate --slurp output",
                    {"argv": argv})
            data = json.loads(out)
        except json.JSONDecodeError as e:
            raise GitHubDeliveryError(
                "GH_BAD_JSON", f"gh returned non-JSON: {proc.stdout[:200]}",
                {"argv": argv}) from e
        # --paginate --slurp always yields a top-level JSON array; anything
        # else is a schema anomaly (review finding 2)
        if not isinstance(data, list):
            raise GitHubDeliveryError(
                "GH_BAD_JSON",
                f"unexpected --paginate --slurp shape: {type(data).__name__}",
                {"argv": argv})
        return data

    def _gh_text(self, args: list[str], *, timeout: int = 60) -> str:
        argv = [self._gh] + args
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise GitHubDeliveryError("GH_TIMEOUT", "gh call timed out",
                                      {"argv": argv}) from e
        except OSError as e:
            # B1: a launch failure must reach the per-source stale path
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
        # requirements is a list of (lower_context, binding) where binding is
        # "legacy-ok" | "any-app" | <int app id>. A row satisfies a requirement
        # by matching context AND the binding's producer rules.
        observed = set()
        for c in checks:
            name_v = c.get("name")
            if not isinstance(name_v, str):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-run row (non-string name)")
            name = name_v.lower()
            app_id = c.get("app_id")
            # B4: producer kind comes from a structural marker, never the
            # mutable/display app name (a real App named 'commit-status' is
            # still a check run)
            is_legacy = bool(c.get("is_legacy"))
            satisfied = []
            for (req_ctx, binding) in requirements:
                if req_ctx != name:
                    continue
                if binding == "legacy-ok":
                    satisfied.append((req_ctx, binding))
                elif binding == "any-app":
                    # any real check run from a valid GitHub App (app_id=-1
                    # means any app, but the run must still carry an app id)
                    if not is_legacy and app_id is not None:
                        satisfied.append((req_ctx, binding))
                else:
                    # app-bound: require the run's numeric app id to match
                    if not is_legacy and app_id is not None and app_id == binding:
                        satisfied.append((req_ctx, binding))
            c["required"] = bool(satisfied)
            c["required_known"] = known
            for s in satisfied:
                observed.add(s)
        # review finding 1: missing must represent the unsatisfied bindings at
        # the (context, app_id) identity level — one matching run for a shared
        # context must not hide an unsatisfied binding of the same context.
        if known:
            missing = sorted(
                f"{ctx}@{binding}" for (ctx, binding) in requirements
                if (ctx, binding) not in observed)
        else:
            missing = []
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
            if "check_runs" not in page or not isinstance(page.get("check_runs"), list):
                # a valid check-runs page must carry a check_runs list
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-runs page (missing/empty check_runs)")
            runs.extend(page["check_runs"])
        if not all(isinstance(r, dict) for r in runs):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed check-run row (not an object)")
        out = []
        for r in runs:
            # B3: validate scalar fields; a present-but-wrong-typed value is a
            # schema failure, not normalized into usable evidence
            name = r.get("name")
            status = r.get("status")
            conclusion = r.get("conclusion")
            if not isinstance(name, str) or not isinstance(status, str) \
                    or not isinstance(conclusion, str):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed check-run row (non-string scalar)")
            app_obj = r.get("app")
            app_name = ""
            app_id = None
            if app_obj is not None:
                if not isinstance(app_obj, dict):
                    raise GitHubDeliveryError(
                        "GH_BAD_JSON", "malformed check-run app (not an object)")
                if not isinstance(app_obj.get("id"), int) \
                        or isinstance(app_obj.get("id"), bool):
                    raise GitHubDeliveryError(
                        "GH_BAD_JSON", "malformed check-run app id (not an int)")
                app_id = app_obj.get("id")
                app_name = app_obj.get("name") if isinstance(app_obj.get("name"), str) else ""
            suite = r.get("check_suite")
            suite_id = None
            if suite is not None:
                if not isinstance(suite, dict) or not isinstance(suite.get("id"), int) \
                        or isinstance(suite.get("id"), bool):
                    raise GitHubDeliveryError(
                        "GH_BAD_JSON", "malformed check-run suite id")
                suite_id = suite.get("id")
            out.append({
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "details_url": r.get("details_url"),
                "app": app_name,
                "app_id": app_id,
                "is_legacy": False,
                "check_suite_id": suite_id,
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
            if "statuses" not in page or not isinstance(page.get("statuses"), list):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed commit-status page (missing/empty statuses)")
            statuses.extend(page["statuses"])
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
                "is_legacy": True,
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
        # confirm the base branch exists; an EMPTY or malformed successful
        # branch response is a schema failure (B2), not proof of existence
        try:
            branch_name = self._gh_text(
                ["api", f"repos/{repository}/branches/{branch}", "--jq", ".name"])
        except GitHubDeliveryError:
            raise
        if not branch_name:
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "empty branch-existence probe response")
        try:
            pages = self._gh_paginated_pages(
                f"repos/{repository}/branches/{branch}/protection")
        except GitHubDeliveryError as e:
            if getattr(e, "code", "") == "GH_HTTP_404":
                # branch exists + no protection -> authoritative known empty
                return [], True
            raise
        if not pages:
            # an empty slurp on a known-existing branch is a schema/provider
            # anomaly, not authoritative known-empty (review finding 1)
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "empty branch-protection response")
        out = pages[0]
        if not isinstance(out, dict):
            raise GitHubDeliveryError(
                "GH_BAD_JSON",
                f"unexpected protection response shape: {type(out).__name__}")
        rsc = out.get("required_status_checks")
        if rsc is None:
            # a successful protection response must carry required_status_checks;
            # its absence is structurally incomplete (review finding 1)
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "missing required_status_checks in protection response")
        if not isinstance(rsc, dict):
            raise GitHubDeliveryError(
                "GH_BAD_JSON",
                f"malformed required_status_checks (not an object): {type(rsc).__name__}")
        contexts = rsc.get("contexts")
        checks_entries = rsc.get("checks")
        # review finding 2: a present-but-wrong-typed member is a schema
        # failure; only an ABSENT member is treated as empty
        if contexts is None:
            contexts = []
        if checks_entries is None:
            checks_entries = []
        if not isinstance(contexts, list) or not all(
                isinstance(c, str) for c in contexts):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed protection contexts (not a string list)")
        if not isinstance(checks_entries, list) or not all(
                isinstance(chk, dict) for chk in checks_entries):
            raise GitHubDeliveryError(
                "GH_BAD_JSON", "malformed protection checks (not an object list)")
        requirements = []  # list of (lower_context, binding)
        # binding: "legacy-ok" (context-only, a legacy status may satisfy it),
        #          "any-app"  (checks[].app_id == -1, only a real check run),
        #          <int>      (app-bound, only a check run from that app)
        for c in contexts:
            requirements.append((c.lower(), "legacy-ok"))
        for chk in checks_entries:
            # review finding 2: a checks[] entry must have a string context and a
            # numeric app_id; malformed data propagates, never weakens policy
            if not isinstance(chk.get("context"), str):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed protection check (non-string context)")
            req_app = chk.get("app_id")
            if req_app is None or not isinstance(req_app, int) \
                    or isinstance(req_app, bool):
                raise GitHubDeliveryError(
                    "GH_BAD_JSON", "malformed protection check (missing/non-int app_id)")
            # app_id == -1 = any app may provide this status (but still a real
            # check run, NOT a legacy commit status) — review finding 1
            binding = "any-app" if req_app == -1 else req_app
            requirements.append((chk["context"].lower(), binding))
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
