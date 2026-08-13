"""DeliveryService (SHIP-CONDUVERA-DELIVERY, Workstreams A/B/C/D/G/H).

Turns a completed managed code-change Attempt into a reviewable GitHub PR.

Owns the DeliveryRecord state machine, the fail-closed pre-publish gate, the
GitHub publishing flow, base-drift classification, GitHub status sync and the
disposable-vs-durable cleanup boundary. All authority lives in the
Control-Plane-owned DeliveryStore; the GitHub provider is shell-free.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from conduvera.control_plane.candidate_service import CandidateError
from conduvera.control_plane.delivery_store import DeliveryStore
from conduvera.control_plane.evidence_store import EvidenceStore
from conduvera.control_plane.github_provider import (
    GitHubDeliveryError, GitHubDeliveryProvider, sanitize_branch_segment,
)

# ---- delivery states -----------------------------------------------------
NOT_READY = "NOT_READY"
READY_TO_PUBLISH = "READY_TO_PUBLISH"
PUBLISHING = "PUBLISHING"
PR_OPEN = "PR_OPEN"
CI_PENDING = "CI_PENDING"
CI_FAILED = "CI_FAILED"
REVIEW_CHANGES_REQUESTED = "REVIEW_CHANGES_REQUESTED"
NEEDS_REBASE = "NEEDS_REBASE"
MERGE_CONFLICT = "MERGE_CONFLICT"
MERGE_READY = "MERGE_READY"
MERGED = "MERGED"
PR_CLOSED = "PR_CLOSED"
DELIVERY_FAILED = "DELIVERY_FAILED"

DELIVERY_STATES = frozenset({
    NOT_READY, READY_TO_PUBLISH, PUBLISHING, PR_OPEN, CI_PENDING, CI_FAILED,
    REVIEW_CHANGES_REQUESTED, NEEDS_REBASE, MERGE_CONFLICT, MERGE_READY,
    MERGED, PR_CLOSED, DELIVERY_FAILED,
})

# ---- gate negative codes -------------------------------------------------
GATE_CODES = frozenset({
    "JOB_NOT_COMPLETED", "ATTEMPT_NOT_SELECTED", "EXTERNAL_SESSION_NOT_PUBLISHABLE",
    "WORKTREE_NOT_OWNED", "BASE_COMMIT_INVALID", "EMPTY_CHANGESET",
    "FORBIDDEN_PATH", "SECRET_PATTERN_DETECTED", "EVIDENCE_MISSING",
    "EVIDENCE_INVALID", "DELIVERY_ALREADY_BOUND", "BASE_DRIFT_REQUIRES_REBASE",
})

# ---- drift classification ------------------------------------------------
DRIFT_MATCH = "MATCH"
DRIFT_BEHIND = "BEHIND"
DRIFT_AHEAD = "AHEAD"
DRIFT_DIVERGED = "DIVERGED"
DRIFT_UNAVAILABLE = "UNAVAILABLE"

# forbidden path patterns for the pre-publish gate (WS-B #7)
FORBIDDEN_PATH_PARTS = (
    ".git/", ".git$", ".env", "secrets.env", ".venv/", "__pycache__/",
    "node_modules/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    "*.pyc", "*.log", ".local/", "*.secret", "credentials", ".ssh/",
    ".config/", "coverage/", "dist/", "build/", ".hermes/",
    # generated runtime / session artefacts (WS-B: no generated runtime
    # state or repository metadata in a deliverable change set)
    "fixture-status.json", "fixture_out", "*.stdout.txt", "*.stderr.txt",
    "mxs_", ".ai/worktrees/", ".ai/state/", ".worktrees/", ".sisyphus/",
    "control-plane.sock", "outbox.jsonl",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|credential)\s*[=:]\s*\S{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"LITELLM_[A-Z_]+"),
)

FORBIDDEN_BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".zip",
                        ".tar", ".gz", ".bin", ".exe", ".so", ".o", ".db"}


def _git_dir_exists(wt: Path) -> bool:
    return (wt / ".git").is_dir() or (wt / ".git").is_file()


class DeliveryError(Exception):
    """Structured delivery error."""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


class DeliveryService:
    """Delivery domain service."""

    def __init__(
        self,
        store: DeliveryStore,
        evidence_store: EvidenceStore,
        provider: GitHubDeliveryProvider | None = None,
        *,
        service: Any = None,
        repo_allowlist: dict[str, Path] | None = None,
        worktree_root: str | Path | None = None,
        delivery_store_dir: str | Path | None = None,
        time_fn: Callable[[], str] = lambda: time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    ):
        self.store = store
        self.evidence_store = evidence_store
        self.provider = provider or GitHubDeliveryProvider(dry_run=True)
        self.service = service
        self._repo_allowlist = repo_allowlist or {}
        self._worktree_root = Path(worktree_root) if worktree_root else None
        self._time_fn = time_fn
        self.candidate_service: Any = None
        if delivery_store_dir is not None:
            self._bind_candidate_service(delivery_store_dir)

    def _bind_candidate_service(self, delivery_store_dir) -> None:
        from conduvera.control_plane.candidate_store import PublishCandidateStore
        from conduvera.control_plane.candidate_service import PublishCandidateService
        croot = Path(delivery_store_dir) / "candidates"
        self.candidate_store = PublishCandidateStore(croot)
        self.candidate_service = PublishCandidateService(
            self.candidate_store, self.evidence_store,
            worktree_root=self._worktree_root or Path.cwd())

    # -- record helpers ----------------------------------------------------
    def _new_record(self, job_id: str, attempt_id: str) -> dict:
        now = self._time_fn()
        return {
            "delivery_id": f"dlv_{uuid.uuid4().hex[:12]}",
            "job_id": job_id, "attempt_id": attempt_id, "session_id": "",
            "repo_id": "", "base_commit": "", "worktree": "",
            "delivery_state": NOT_READY, "branch_name": "", "branch_head_sha": "",
            "github_repository": "", "pull_request_number": None,
            "pull_request_url": "", "pull_request_head_sha": "",
            "pull_request_base_sha": "", "checks_summary": {},
            "reviews_summary": {}, "mergeability": "",
            "attention_reasons": [], "evidence_refs": [], "gate_result": None,
            "created_at": now, "updated_at": now, "published_at": None,
            "last_synced_at": None, "terminal_reason": "",
        }

    def _persist(self, record: dict, event: str, **payload: Any) -> dict:
        record["updated_at"] = self._time_fn()
        self.store.save(record)
        self.store.append_event(record["delivery_id"], {
            "seq": None, "event": event, "state": record.get("delivery_state"),
            "at": self._time_fn(), **payload,
        })
        # publish to the live event stream for UI updates (WS-F)
        try:
            if self.service is not None and hasattr(self.service, "event_bus"):
                self.service.event_bus.publish(
                    "delivery." + event,
                    {"delivery_id": record.get("delivery_id"),
                     "job_id": record.get("job_id"),
                     "attempt_id": record.get("attempt_id"),
                     "delivery_state": record.get("delivery_state")})
        except Exception:  # noqa: BLE001 - never break the control path
            pass
        return record

    # -- lookup ------------------------------------------------------------
    def get(self, delivery_id: str) -> dict | None:
        return self.store.get(delivery_id)

    def find_by_job_attempt(self, job_id: str, attempt_id: str) -> dict | None:
        for r in self.store.all():
            if r.get("job_id") == job_id and r.get("attempt_id") == attempt_id:
                return r
        return None

    def list(self) -> list[dict]:
        return self.store.all()

    def history(self, delivery_id: str) -> list[dict]:
        return self.store.history(delivery_id)

    # -- resolve job/attempt/session from a delivery or job id -------------
    def _resolve_target(self, job_or_delivery: str,
                        attempt_id: str | None = None) -> tuple[dict, str, str]:
        """Return (record, job_id, attempt_id) for a delivery_id OR job_id.

        A delivery_id resolves its own record. A job_id resolves an explicitly
        selected COMPLETED attempt (WS A): if `attempt_id` is given it must be
        a COMPLETED attempt of the job; otherwise the persisted selection is
        used; otherwise ATTEMPT_NOT_SELECTED fails closed when the job has
        multiple COMPLETED attempts.
        """
        rec = self.store.get(job_or_delivery)
        if rec is not None:
            return rec, rec["job_id"], rec["attempt_id"]
        # job_id path
        if self.service is None:
            raise DeliveryError("NO_SERVICE", "service not bound")
        job = self.service.scheduler.store.get_job(job_or_delivery)
        if job is None:
            raise DeliveryError("UNKNOWN_JOB", f"unknown job {job_or_delivery}")
        attempts = [a for a in self.service.scheduler.store.all_attempts()
                    if a.job_id == job.job_id]
        completed = [a for a in attempts
                     if getattr(a, "state", None) and a.state.value == "COMPLETED"]
        if not completed:
            raise DeliveryError("JOB_NOT_COMPLETED",
                                "no completed attempt to deliver")
        if attempt_id:
            if attempt_id not in {a.attempt_id for a in completed}:
                raise DeliveryError("ATTEMPT_NOT_SELECTED",
                                    f"attempt {attempt_id} not a COMPLETED attempt")
            selected = next(a for a in completed if a.attempt_id == attempt_id)
        else:
            # persisted selection
            persisted = self._persisted_selection(job.job_id)
            if persisted and persisted in {a.attempt_id for a in completed}:
                selected = next(a for a in completed
                                if a.attempt_id == persisted)
            elif len(completed) == 1:
                selected = completed[0]
            else:
                raise DeliveryError(
                    "ATTEMPT_NOT_SELECTED",
                    "job has multiple completed attempts; select one explicitly")
        # DOD-08 idempotency: reuse an existing DeliveryRecord bound to this
        # exact (job, attempt) so a repeated Publish returns the same record,
        # branch and PR instead of a new delivery.
        existing = self.find_by_job_attempt(job.job_id, selected.attempt_id)
        if existing is not None:
            return existing, job.job_id, selected.attempt_id
        return (self._new_record(job.job_id, selected.attempt_id),
                job.job_id, selected.attempt_id)

    def _persisted_selection(self, job_id: str) -> str | None:
        """Return the persisted selected attempt_id for a job, if any."""
        sel = self.store.dir / "selection.json"
        if sel.is_file():
            try:
                return json.loads(sel.read_text()).get(job_id)
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def select_attempt(self, job_id: str, attempt_id: str) -> dict:
        """Persist the explicit delivery-source Attempt selection (WS A)."""
        # validate the attempt is a COMPLETED attempt of the job
        self._resolve_target(job_id, attempt_id=attempt_id)
        sel = self.store.dir / "selection.json"
        data = {}
        if sel.is_file():
            try:
                data = json.loads(sel.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}
        data[job_id] = attempt_id
        sel.write_text(json.dumps(data, sort_keys=True))
        return {"ok": True, "job_id": job_id, "selected_attempt_id": attempt_id}

    def candidate_approve(self, candidate_id: str, approved_by: str = "operator") -> dict:
        if self.candidate_service is None:
            raise DeliveryError("NO_CANDIDATE_SERVICE", "candidate service not bound")
        c = self.candidate_service.approve(candidate_id, approved_by=approved_by)
        return {"ok": True, "candidate_id": c["candidate_id"],
                "approved_at": c.get("approved_at"), "approved_by": approved_by}

    def candidate_list(self) -> list[dict]:
        if self.candidate_service is None:
            return []
        return self.candidate_store.list_summary()

    def candidate_get(self, candidate_id: str) -> dict | None:
        if self.candidate_service is None:
            return None
        return self.candidate_store.get(candidate_id)


    # -- state machine helpers --------------------------------------------
    def _transition(self, record: dict, new_state: str, *,
                    event: str, reason: str = "", attention: list[str] | None = None,
                    **extra: Any) -> dict:
        old = record.get("delivery_state")
        record["delivery_state"] = new_state
        if reason:
            record["terminal_reason"] = reason
        if attention:
            record["attention_reasons"] = attention
        record.update(extra)
        self._persist(record, event, from_state=old, to_state=new_state,
                      reason=reason)
        return record

    # ======================================================================
    # WORKSTREAM B — FAIL-CLOSED PRE-PUBLISH GATE
    # ======================================================================
    def preflight(self, job_or_delivery: str,
                  attempt_id: str | None = None) -> dict:
        """Run the pre-publish gate; return {ok, reasons[], state, record,
        candidate?}. Creates the immutable PublishCandidate (WS B) when the
        gate is clean."""
        try:
            record, job_id, attempt_id_r = self._resolve_target(
                job_or_delivery, attempt_id)
            attempt_id = attempt_id_r
        except DeliveryError as e:
            return {"ok": False, "reasons": [{"code": e.code, "message": str(e)}],
                    "state": NOT_READY, "record": None}
        reasons = self._gate(record, job_id, attempt_id)
        ok = not reasons
        state = READY_TO_PUBLISH if ok else NOT_READY
        candidate = None
        if ok and self.candidate_service is not None:
            candidate = self._build_candidate(record, job_id, attempt_id)
            record["candidate_id"] = candidate.get("candidate_id")
        record = self._persist(dict(record), "preflight",
                               gate_result={"ok": ok, "reasons": reasons})
        record["delivery_state"] = state
        record["gate_result"] = {"ok": ok, "reasons": reasons}
        self.store.save(record)
        return {"ok": ok, "reasons": reasons, "state": state,
                "record": record, "candidate": candidate}

    def _build_candidate(self, record: dict, job_id: str, attempt_id: str) -> dict:
        """Build the immutable PublishCandidate from the exact Attempt (WS B)."""
        # gather named test/gate results from the EvidenceBundle
        named_tests, named_gates = self._named_results(job_id, attempt_id)
        return self.candidate_service.build_candidate(
            job_id=job_id, attempt_id=attempt_id,
            session_id=record.get("session_id", ""),
            delivery_id=record.get("delivery_id", ""),
            repo_id=record.get("repo_id", ""),
            github_repository=record.get("github_repository", ""),
            base_branch=record.get("base_branch", "main"),
            base_commit=record.get("base_commit", ""),
            worktree=record.get("worktree", ""),
            evidence_refs=record.get("evidence_refs", []) or [],
            named_tests=named_tests, named_gates=named_gates,
        )

    def _named_results(self, job_id: str, attempt_id: str) -> tuple[list, list]:
        """Extract named test/gate results from the selected Attempt's evidence."""
        tests, gates = [], []
        for ref in self._evidence_refs(job_id, attempt_id):
            ev = self.evidence_store.get(ref)
            if not isinstance(ev, dict):
                continue
            test_result = ev.get("test_result")
            if isinstance(test_result, dict) and test_result.get("name"):
                tests.append({
                    "name": test_result.get("name"),
                    "result": test_result.get("result", "UNKNOWN"),
                    "duration_s": test_result.get("duration_s"),
                })
            elif isinstance(test_result, str) and test_result:
                tests.append({"name": "job-tests", "result": test_result,
                              "duration_s": None})
        return tests, gates


    def _gate(self, record: dict, job_id: str, attempt_id: str) -> list[dict]:
        reasons: list[dict] = []
        if self.service is None:
            return [{"code": "NO_SERVICE", "message": "service not bound"}]
        svc = self.service
        # 1. job type supported + terminal COMPLETED
        job = svc.scheduler.store.get_job(job_id)
        if job is None:
            reasons.append({"code": "JOB_NOT_COMPLETED", "message": "job missing"})
            return reasons
        if job.state is None or job.state.value != "COMPLETED":
            reasons.append({"code": "JOB_NOT_COMPLETED",
                            "message": f"job state {getattr(job.state,'value','?')}"})
            return reasons
        # 2. selected attempt terminal COMPLETED
        attempt = svc.scheduler.store.get_attempt(attempt_id)
        if attempt is None or attempt.state.value != "COMPLETED":
            reasons.append({"code": "ATTEMPT_NOT_SELECTED",
                            "message": "selected attempt not COMPLETED"})
            return reasons
        # 3. session MANAGED
        session = self._find_session(attempt_id)
        from conduvera.harness.managed_session import OwnershipClass
        if session is None:
            reasons.append({"code": "WORKTREE_NOT_OWNED",
                            "message": "no managed session for attempt"})
        elif session.ownership_class is not OwnershipClass.MANAGED:
            reasons.append({"code": "EXTERNAL_SESSION_NOT_PUBLISHABLE",
                            "message": "external session not publishable"})
        # 4. worktree owned by exact attempt + beneath root
        wt = session.worktree if session is not None else record.get("worktree", "")
        if not wt:
            reasons.append({"code": "WORKTREE_NOT_OWNED", "message": "no worktree"})
            return reasons
        wt_path = Path(wt)
        if self._worktree_root and not wt_path.is_relative_to(self._worktree_root):
            reasons.append({"code": "WORKTREE_NOT_OWNED",
                            "message": "worktree outside root"})
            return reasons
        if not (wt_path / ".git").is_dir() and not _git_dir_exists(wt_path):
            reasons.append({"code": "WORKTREE_NOT_OWNED",
                            "message": "worktree not a git worktree"})
        # 5. base commit known + allowlisted repo
        repo_id = record.get("repo_id") or (job.repo if hasattr(job, "repo") else "")
        base_commit = record.get("base_commit") or getattr(job, "base_commit", "")
        if not base_commit or base_commit == "0" * 40 or len(base_commit) < 7:
            reasons.append({"code": "BASE_COMMIT_INVALID",
                            "message": "base commit unknown"})
        if repo_id and repo_id not in self._repo_allowlist and \
                self._repo_allowlist:
            reasons.append({"code": "BASE_COMMIT_INVALID",
                            "message": "repo not allowlisted"})
        # 6. non-empty tracked change set (diff against the owned base commit)
        changes = self._changeset(wt_path, base_commit)
        if changes is None:
            reasons.append({"code": "WORKTREE_NOT_OWNED",
                            "message": "cannot compute changeset"})
        elif not changes:
            reasons.append({"code": "EMPTY_CHANGESET",
                            "message": "no tracked changes in worktree"})
        # 7. forbidden paths + secrets + binaries
        forbidden = self._forbidden(changes or [])
        for f in forbidden:
            reasons.append({"code": f["code"], "message": f["message"]})
        # 8. EvidenceBundle exists + passes validation
        ev = self._evidence_ok(job_id, attempt_id)
        if ev.get("missing"):
            reasons.append({"code": "EVIDENCE_MISSING", "message": ev["missing"]})
        if ev.get("invalid"):
            reasons.append({"code": "EVIDENCE_INVALID", "message": ev["invalid"]})
        # 9-10. test/gate evidence + diff/tree hash match publish receipt
        if self._tree_hash(wt_path) is None:
            reasons.append({"code": "EVIDENCE_INVALID",
                            "message": "cannot hash worktree tree"})
        # 11. raw prompt not copied into commit/PR (handled in provider)
        # 12. worktree not bound to a different DeliveryRecord
        bound = self._bound_elsewhere(record.get("delivery_id") or "", wt)
        if bound:
            reasons.append({"code": "DELIVERY_ALREADY_BOUND", "message": bound})
        return reasons

    # -- gate helpers ------------------------------------------------------
    def _changeset(self, wt: Path, base_commit: str = "") -> list[str] | None:
        """Return the tracked change set of the owned worktree.

        Includes committed changes (base->HEAD), staged, unstaged AND
        untracked paths (real harnesses leave the feature change untracked in
        the owned worktree), so forbidden/empty detection sees every path.
        """
        try:
            from conduvera.control_plane.github_provider import _git
            changes: list[str] = []
            if base_commit and len(base_commit) >= 7:
                try:
                    out = _git("diff", "--name-only", base_commit, "HEAD", cwd=wt)
                    changes += [f for f in out.splitlines() if f.strip()]
                except GitHubDeliveryError:
                    pass
            # staged + unstaged
            try:
                changes += [f for f in
                            _git("diff", "--name-only", "HEAD", cwd=wt).splitlines()
                            if f.strip()]
            except GitHubDeliveryError:
                pass
            try:
                changes += [f for f in
                            _git("diff", "--cached", "--name-only", cwd=wt).splitlines()
                            if f.strip()]
            except GitHubDeliveryError:
                pass
            # untracked (real harness leaves the change untracked)
            try:
                porcelain = _git("status", "--porcelain", "--untracked-files=all",
                                 cwd=wt)
                for line in porcelain.splitlines():
                    if line.startswith("??"):
                        changes.append(line[3:].strip())
                    elif line[:2] in ("A ", " M", "M ", "R ", "D ", "T "):
                        changes.append(line[3:].strip())
            except GitHubDeliveryError:
                pass
            # dedupe preserving order
            seen = set()
            out = []
            for f in changes:
                if f and f not in seen:
                    seen.add(f)
                    out.append(f)
            return out
        except Exception:
            return None

    def _forbidden(self, changes: list[str]) -> list[dict]:
        found = []
        for f in changes:
            low = f.lower()
            # session-log runtime artefacts (mxs_*.stdout/stderr.txt) are
            # excluded, not blocked — they never enter the commit (candidate
            # manifest) and remain recorded in the EvidenceBundle
            if low.startswith("mxs_") and (low.endswith(".stdout.txt")
                                           or low.endswith(".stderr.txt")):
                continue
            if any(part in low for part in FORBIDDEN_PATH_PARTS):
                found.append({"code": "FORBIDDEN_PATH",
                              "message": f"forbidden path {f}"})
            if Path(f).suffix.lower() in FORBIDDEN_BINARY_EXT:
                found.append({"code": "FORBIDDEN_PATH",
                              "message": f"oversized/binary file {f}"})
            if any(p.search(f) for p in SECRET_PATTERNS):
                found.append({"code": "SECRET_PATTERN_DETECTED",
                              "message": f"secret-like path {f}"})
        return found

    def _evidence_ok(self, job_id: str, attempt_id: str) -> dict:
        from conduvera.control_plane.evidence_store import validate_evidence
        refs = self._evidence_refs(job_id, attempt_id)
        if not refs:
            return {"missing": "no EvidenceBundle for attempt"}
        for ref in refs:
            bundle = self.evidence_store.get(ref)
            if bundle is None:
                return {"missing": f"evidence bundle {ref} not found"}
            # authoritative fail-closed validation (schema + exit + artifacts)
            vstatus = validate_evidence(bundle)
            if vstatus["status"] != "VALID":
                return {"invalid": f"evidence bundle {ref}: {vstatus.get('reason','INVALID')}"}
        return {}

    def _evidence_refs(self, job_id: str, attempt_id: str) -> list[str]:
        refs = []
        if self.service is None:
            return refs
        for ev in self.evidence_store.dir.glob("ev_*.json"):
            try:
                b = json.loads(ev.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if b.get("job_id") == job_id and b.get("attempt_id") == attempt_id:
                refs.append(ev.stem)
        return refs

    def _tree_hash(self, wt: Path) -> str | None:
        try:
            from conduvera.control_plane.github_provider import _git
            return _git("rev-parse", "HEAD^{tree}", cwd=wt)
        except Exception:
            return None

    def _find_session(self, attempt_id: str):
        if self.service is None:
            return None
        reg = getattr(self.service, "registry", None)
        if reg is None:
            return None
        # registry.get by session_id (from a bound record) or scan by attempt
        for s in reg.all():
            if getattr(s, "attempt_id", "") == attempt_id:
                return s
        return None

    def _bound_elsewhere(self, delivery_id: str, wt: str) -> str | None:
        for r in self.store.all():
            if r.get("delivery_id") != delivery_id and r.get("worktree") == wt:
                return f"worktree already bound to {r['delivery_id']}"
        return None

    # ======================================================================
    # WORKSTREAM D — BASE DRIFT
    # ======================================================================
    def classify_drift(self, record: dict) -> str:
        # base branch is derived from the github repo default in _remote_base
        remote_base = self._remote_base(record)
        if remote_base is None:
            return DRIFT_UNAVAILABLE
        recorded_base = record.get("pull_request_base_sha") or record.get("base_commit")
        if not recorded_base or len(recorded_base) < 7:
            return DRIFT_UNAVAILABLE
        if remote_base == recorded_base:
            return DRIFT_MATCH
        # local ancestry: is recorded base an ancestor of remote base (BEHIND)
        # or is the remote base an ancestor of the recorded base (AHEAD)?
        anc = self._is_ancestor(recorded_base, remote_base, record)
        if anc is True:
            return DRIFT_BEHIND
        if anc is False:
            # try the reverse: remote base ancestor of recorded base -> AHEAD
            rev = self._is_ancestor(remote_base, recorded_base, record)
            if rev is True:
                return DRIFT_AHEAD
            return DRIFT_DIVERGED
        return DRIFT_UNAVAILABLE

    def _remote_base(self, record: dict) -> str | None:
        repo = record.get("github_repository")
        if not repo:
            return None
        try:
            return self.provider.remote_base_sha(repo, "main")
        except GitHubDeliveryError:
            return None

    def _is_ancestor(self, ancestor: str, descendant: str, record: dict) -> bool | None:
        wt = Path(record.get("worktree") or "")
        if not wt.exists():
            return None
        try:
            from conduvera.control_plane.github_provider import _git
            _git("cat-file", "-e", f"{ancestor}^{{commit}}", cwd=wt)
            _git("cat-file", "-e", f"{descendant}^{{commit}}", cwd=wt)
            _git("merge-base", "--is-ancestor", ancestor, descendant, cwd=wt)
            return True
        except Exception:
            # fetch the remote base into the worktree then retry
            try:
                from conduvera.control_plane.github_provider import _git
                _git("fetch", "origin", "main", cwd=wt)
                _git("merge-base", "--is-ancestor", ancestor, descendant, cwd=wt)
                return True
            except Exception:
                return False

    # ======================================================================
    # WORKSTREAM C — PUBLISH
    # ======================================================================
    def publish(self, job_or_delivery: str, *, base_branch: str = "main",
                force: bool = False, attempt_id: str | None = None,
                candidate_id: str | None = None) -> dict:
        """Run the gate, create exactly one task branch + PR, persist record."""
        if candidate_id:
            cand = self.candidate_store.get(candidate_id)
            if cand is None:
                return {"ok": False, "state": NOT_READY,
                        "reasons": [{"code": "UNKNOWN_CANDIDATE",
                                     "message": f"unknown candidate {candidate_id}"}],
                        "message": "unknown candidate"}
            if not cand.get("approved_at"):
                return {"ok": False, "state": NOT_READY,
                        "reasons": [{"code": "CANDIDATE_NOT_APPROVED",
                                     "message": "candidate not approved"}],
                        "message": "candidate not approved"}
            attempt_id = cand.get("attempt_id")
        pre = self.preflight(job_or_delivery, attempt_id=attempt_id)
        if not pre["ok"]:
            return {"ok": False, "state": NOT_READY,
                    "reasons": pre["reasons"],
                    "message": "pre-publish gate failed"}
        record = pre["record"]
        job_id = record["job_id"]
        attempt_id = record["attempt_id"]
        # resolve the MANAGED session for this attempt (never fall back to the
        # core checkout / CWD — that would commit into the wrong repository)
        session = self._find_session(attempt_id)
        wt = Path(session.worktree) if session and session.worktree else (
            Path(record.get("worktree") or ""))
        if not wt or str(wt) in ("", "."):
            return self._transition(record, DELIVERY_FAILED,
                                    event="publish_no_worktree",
                                    reason="no owned worktree for attempt",
                                    attention=["remote publication failure"],
                                    branch_name="", pull_request_url="")

        # resolve repo/github/base BEFORE drift classification (the remote
        # base SHA depends on github_repository being known)
        record["repo_id"] = record.get("repo_id") or self._job_repo(job_id)
        github_repo = self._github_repo(record["repo_id"])
        record["github_repository"] = github_repo
        record["base_commit"] = self._job_base(job_id) or record.get("base_commit")
        record["worktree"] = str(wt)
        record["session_id"] = session.session_id if session else ""

        # base drift must be MATCH or BEHIND (clean rebase possible) — never
        # publish over a diverged/unavailable base.
        drift = self.classify_drift(record)
        if drift in (DRIFT_DIVERGED, DRIFT_UNAVAILABLE):
            return self._transition(record, DELIVERY_FAILED,
                                    event="publish_blocked_drift",
                                    reason=f"base drift {drift}",
                                    attention=["base drift"],
                                    branch_name="", pull_request_url="")
        if drift == DRIFT_BEHIND and not force:
            # safe rebase in the owned worktree then re-gate
            self._safe_rebase(record, wt)
            pre = self.preflight(job_or_delivery)
            if not pre["ok"]:
                return {"ok": False, "state": NOT_READY,
                        "reasons": pre["reasons"], "message": "rebase gate failed"}

        record = self._transition(record, PUBLISHING, event="publish_start")
        branch = self._branch_name(record)
        record["branch_name"] = branch
        record["evidence_refs"] = self._evidence_refs(job_id, attempt_id)

        # idempotent: existing PR on same branch/base -> return it
        existing = self.provider.find_pr(github_repo, branch, base_branch)
        if existing is not None:
            return self._record_existing_pr(record, existing, job_id, attempt_id, wt)

        # remote branch presence: fail closed on unexpected SHA
        remote_sha = self.provider.remote_branch_sha(github_repo, branch)
        if remote_sha is not None and remote_sha != self._tree_hash(wt):
            return self._transition(record, DELIVERY_FAILED,
                                    event="publish_remote_sha_mismatch",
                                    reason="remote branch unexpected SHA",
                                    attention=["remote publication failure"])

        # create commit containing ONLY the approved candidate manifest (atomic,
        # never `git add -A`). If no candidate exists yet, build+approve it now.
        if self.candidate_service is not None:
            candidate = self._candidate_for(record, job_id, attempt_id)
            if candidate is None:
                return self._transition(record, DELIVERY_FAILED,
                                        event="publish_no_candidate",
                                        reason="no approved candidate for attempt",
                                        attention=["remote publication failure"])
            try:
                msg = (f"conduvera: delivery {record['delivery_id']} "
                       f"candidate {candidate['candidate_id']} "
                       f"attempt {attempt_id}")
                commit = self.candidate_service.commit_candidate(candidate, message=msg)
                head_sha = commit["commit_sha"]
            except CandidateError as e:
                return self._transition(record, DELIVERY_FAILED,
                                        event="publish_candidate_failed",
                                        reason=f"{e.code}: {e.message}",
                                        attention=["remote publication failure"])
        else:
            # fallback legacy path (no candidate service bound) — not used in prod
            try:
                self._create_commit(wt, record)
            except DeliveryError as e:
                return self._transition(record, DELIVERY_FAILED,
                                        event="publish_commit_failed",
                                        reason=str(e),
                                        attention=["remote publication failure"])
            head_sha = self._head_sha(wt)
        record["branch_head_sha"] = head_sha

        # push without force (idempotent: no force)
        self._push(wt, github_repo, branch, head_sha=head_sha)
        record["branch_head_sha"] = head_sha

        body = self._build_body(record, wt, candidate=candidate)
        pr = self.provider.create_pr(github_repo, branch, base_branch,
                                     self._pr_title(record), body)
        return self._record_pr(record, pr, job_id, attempt_id, wt)

    def _candidate_for(self, record: dict, job_id: str, attempt_id: str):
        """Return the approved PublishCandidate for this attempt (build if none)."""
        cand = self.candidate_store.find_by_job_attempt(job_id, attempt_id)
        if cand is not None and cand.get("approved_at"):
            return cand
        if cand is not None:
            raise CandidateError("CANDIDATE_NOT_APPROVED",
                                 f"candidate {cand['candidate_id']} not approved")
        # build + approve (operator approved via preflight path normally)
        c = self._build_candidate(record, job_id, attempt_id)
        return self.candidate_service.approve(c["candidate_id"], approved_by="conduvera")


    def _record_pr(self, record: dict, pr: dict, job_id: str,
                   attempt_id: str, wt: Path) -> dict:
        record["pull_request_number"] = pr.get("number")
        record["pull_request_url"] = pr.get("url")
        record["pull_request_head_sha"] = pr.get("headRefOid")
        record["pull_request_base_sha"] = pr.get("baseRefOid")
        record["branch_head_sha"] = pr.get("headRefOid") or self._head_sha(wt)
        record["github_repository"] = record.get("github_repository", "")
        record["mergeability"] = pr.get("mergeable", "")
        record["published_at"] = self._time_fn()
        # sync once to get checks/reviews
        synced = self._sync_record(record)
        rec = self._transition(record, self._state_from_sync(synced),
                               event="published",
                               attention=synced.get("attention_reasons", []),
                               branch_name=record["branch_name"],
                               pull_request_number=record["pull_request_number"],
                               pull_request_url=record["pull_request_url"],
                               pull_request_head_sha=record["pull_request_head_sha"],
                               pull_request_base_sha=record["pull_request_base_sha"],
                               last_synced_at=self._time_fn())
        return {"ok": True, "state": rec["delivery_state"], "record": rec}

    def _record_existing_pr(self, record: dict, existing: dict, job_id: str,
                            attempt_id: str, wt: Path) -> dict:
        record["pull_request_number"] = existing.get("number")
        record["pull_request_url"] = existing.get("url")
        record["pull_request_head_sha"] = existing.get("headRefOid")
        record["pull_request_base_sha"] = existing.get("baseRefOid")
        record["branch_head_sha"] = existing.get("headRefOid")
        record["mergeability"] = existing.get("mergeable", "")
        return self._record_pr(record, existing, job_id, attempt_id, wt)

    # -- publish helpers ---------------------------------------------------
    def _job_repo(self, job_id: str) -> str:
        job = self.service.scheduler.store.get_job(job_id)
        return getattr(job, "repo", "") if job else ""

    def _job_base(self, job_id: str) -> str:
        job = self.service.scheduler.store.get_job(job_id)
        return getattr(job, "base_commit", "") if job else ""

    def _github_repo(self, repo_id: str) -> str:
        # map local repo id to its GitHub repo. Defaults for known ids.
        mapping = {
            "conduvera-core": "WietRob/conduvera-core",
            "conduvera-adapter": "WietRob/conduvera-hermes-adapter",
            "conduvera-platform": "WietRob/conduvera-platform",
            "conduit-fixture": "WietRob/conduit-fixture",
        }
        return mapping.get(repo_id, f"WietRob/{repo_id}")

    def _branch_name(self, record: dict) -> str:
        task = sanitize_branch_segment(record["job_id"])
        att = sanitize_branch_segment(record["attempt_id"])
        base = f"conduvera/{task}/{att}"
        # collision-safe deterministic suffix vs other delivery records
        if self._branch_taken(base, record.get("delivery_id")):
            base += f"-{record.get('delivery_id', '')[-6:]}"
        return base

    def _branch_taken(self, branch: str, delivery_id: str | None) -> bool:
        for r in self.store.all():
            if r.get("branch_name") == branch and \
                    r.get("delivery_id") != delivery_id:
                return True
        return False

    def _create_commit(self, wt: Path, record: dict) -> None:
        from conduvera.control_plane.github_provider import _git
        # branch from current worktree head (owned), stage all approved changes
        try:
            _git("add", "-A", cwd=wt)
        except GitHubDeliveryError as e:
            raise DeliveryError("GIT_ADD_FAILED", str(e))
        # deterministic non-secret message (WS-B #11: no raw prompt)
        msg = f"conduvera: delivery {record['delivery_id']} attempt {record['attempt_id']}"
        try:
            _git("commit", "-m", msg, cwd=wt)
        except GitHubDeliveryError as e:
            raise DeliveryError("GIT_COMMIT_FAILED", str(e))

    def _head_sha(self, wt: Path) -> str:
        from conduvera.control_plane.github_provider import _git
        return _git("rev-parse", "HEAD", cwd=wt)

    def _push(self, wt: Path, github_repo: str, branch: str,
              head_sha: str | None = None) -> None:
        from conduvera.control_plane.github_provider import _git
        remote = f"https://github.com/{github_repo}.git"
        # use an explicit delivery remote so we never mutate the owned
        # worktree's canonical origin as a persistent side effect
        try:
            orig_url = _git("remote", "get-url", "delivery", cwd=wt)
        except GitHubDeliveryError:
            orig_url = ""
        if orig_url != remote:
            try:
                _git("remote", "remove", "delivery", cwd=wt)
            except GitHubDeliveryError:
                pass
            _git("remote", "add", "delivery", remote, cwd=wt)
        # push the exact candidate commit SHA (never a moving HEAD) to the task
        # branch; no force.
        src = head_sha if head_sha else "HEAD"
        _git("push", "delivery", f"{src}:refs/heads/{branch}", cwd=wt)

    def _safe_rebase(self, record: dict, wt: Path) -> None:
        from conduvera.control_plane.github_provider import _git
        try:
            _git("fetch", "origin", "main", cwd=wt)
            _git("rebase", "origin/main", cwd=wt)
        except GitHubDeliveryError as e:
            raise DeliveryError("REBASE_FAILED", str(e))

    def _build_body(self, record: dict, wt: Path,
                    candidate: dict | None = None) -> str:
        """PR body from the immutable candidate + publication receipt only
        (WS D). No recomputed diff, no generic statement."""
        lines = []
        lines.append(f"## Conduvera Delivery `{record['delivery_id']}`")
        lines.append("")
        lines.append(f"- Job: `{record['job_id']}`")
        lines.append(f"- Attempt: `{record['attempt_id']}`")
        lines.append(f"- Session: `{record.get('session_id') or '—'}`")
        lines.append(f"- Delivery: `{record['delivery_id']}`")
        lines.append(f"- Candidate: `{(candidate or {}).get('candidate_id') or '—'}`")
        lines.append(f"- Repository: `{record.get('repo_id') or '—'}`")
        lines.append(f"- Base commit: `{record.get('base_commit') or '—'}`")
        lines.append(f"- Branch head: `{record.get('branch_head_sha') or '—'}`")
        lines.append(f"- Diff SHA-256: `{(candidate or {}).get('diff_sha256') or '—'}`")
        lines.append(f"- Harness: `{self._job_harness(record['job_id'])}`")
        lines.append("")
        # changed files from the candidate manifest (exact, with stats)
        files = (candidate or {}).get("files") or []
        lines.append("## Changed files")
        lines.append("")
        for f in files[:100]:
            lines.append(f"- `{f.get('status')}` `{f.get('path')}` "
                         f"(+{f.get('additions', 0)}/-{f.get('deletions', 0)}, "
                         f"size {f.get('size', 0)})")
        if not files:
            lines.append("- (no changed files in candidate)")
        lines.append("")
        # named tests/gates from the candidate
        tests = (candidate or {}).get("named_test_results") or []
        gates = (candidate or {}).get("named_gate_results") or []
        lines.append("## Tests")
        lines.append("")
        for t in tests:
            dur = f" ({t.get('duration_s')}s)" if t.get("duration_s") else ""
            lines.append(f"- `{t.get('name')}`: **{t.get('result', 'UNKNOWN')}**{dur}")
        if not tests:
            lines.append("- No named tests recorded in EvidenceBundle.")
        lines.append("")
        lines.append("## Gates")
        lines.append("")
        lines.append(f"- Gate contract: `{(candidate or {}).get('gate_contract_version') or '—'}`")
        for g in gates:
            lines.append(f"- `{g.get('name')}`: **{g.get('result', 'UNKNOWN')}**")
        lines.append("")
        # evidence
        lines.append("## Evidence")
        lines.append("")
        for ref in (candidate or {}).get("evidence_refs") or []:
            h = ((candidate or {}).get("evidence_hashes") or {}).get(ref, "—")
            lines.append(f"- EvidenceBundle: `{ref}` (sha256 `{h}`)")
        lines.append("")
        lines.append("## Notes")
        lines.append("- Merge is an explicit **human action** in v1.")
        lines.append("- This PR was produced by the Conduvera Delivery Workspace.")
        return "\n".join(lines)

    def _pr_title(self, record: dict) -> str:
        return f"Conduvera delivery {record['delivery_id']} (attempt {record['attempt_id']})"

    def _job_harness(self, job_id: str) -> str:
        job = self.service.scheduler.store.get_job(job_id)
        return getattr(job, "harness", "") if job else ""

    # ======================================================================
    # WORKSTREAM G — GITHUB STATUS SYNC
    # ======================================================================
    def sync(self, job_or_delivery: str) -> dict:
        try:
            record, _, _ = self._resolve_target(job_or_delivery)
        except DeliveryError as e:
            return {"ok": False, "message": str(e), "code": e.code}
        if not record.get("pull_request_number"):
            return {"ok": False, "message": "no PR to sync", "record": record}
        synced = self._sync_record(record)
        state = self._state_from_sync(synced)
        self._transition(record, state, event="sync",
                         attention=synced.get("attention_reasons", []),
                         checks_summary=synced.get("checks_summary", {}),
                         reviews_summary=synced.get("reviews_summary", {}),
                         mergeability=synced.get("mergeability", ""),
                         pull_request_head_sha=synced.get("head_sha", record.get("pull_request_head_sha")),
                         pull_request_base_sha=synced.get("base_sha", record.get("pull_request_base_sha")),
                         last_synced_at=self._time_fn())
        return {"ok": True, "state": state, "record": record,
                "sync": synced}

    def _sync_record(self, record: dict) -> dict:
        repo = record.get("github_repository")
        num = record.get("pull_request_number")
        if not repo or not num:
            return {"attention_reasons": ["lost GitHub synchronization"]}
        try:
            pr = self.provider.pr_view(repo, int(num))
        except GitHubDeliveryError:
            return {"attention_reasons": ["lost GitHub synchronization"]}
        state = pr.get("state", "").upper()
        head_sha = pr.get("headRefOid")
        base_sha = pr.get("baseRefOid")
        mergeable = pr.get("mergeable", "")
        merge_state = pr.get("mergeStateStatus", "")
        checks = self.provider.list_checks(repo, head_sha) if head_sha else []
        reviews = self.provider.list_reviews(repo, int(num))
        checks_summary = self._checks_summary(checks)
        reviews_summary = self._reviews_summary(reviews)
        attention = []
        if state == "MERGED":
            pass
        elif state == "CLOSED":
            pass
        elif merge_state in ("DIRTY",) or mergeable == "CONFLICTING":
            attention.append("rebase/merge conflict")
        elif merge_state in ("BEHIND", "BEHIND_BY_COMMITS", "BLOCKED"):
            attention.append("base drift")
        if checks_summary.get("failed"):
            attention.append("CI/check failure")
        if reviews_summary.get("changes_requested"):
            attention.append("review changes requested")
        return {
            "state": state, "head_sha": head_sha, "base_sha": base_sha,
            "mergeable": mergeable, "merge_state": merge_state,
            "checks_summary": checks_summary,
            "reviews_summary": reviews_summary,
            "attention_reasons": attention,
        }

    def _checks_summary(self, checks: list[dict]) -> dict:
        by = {"pending": 0, "success": 0, "failure": 0, "other": 0}
        names = []
        details = []
        for c in checks:
            conc = (c.get("conclusion") or "").lower()
            status = (c.get("status") or "").lower()
            names.append(c.get("name", ""))
            if status == "completed" and conc == "success":
                by["success"] += 1
            elif status == "completed" and conc in ("failure", "timed_out", "cancelled", "action_required"):
                by["failure"] += 1
            elif status in ("queued", "in_progress"):
                by["pending"] += 1
            else:
                by["other"] += 1
            # operator-visible per-check detail (WS H dogfood feature)
            details.append({
                "name": c.get("name", ""),
                "status": status,
                "conclusion": conc,
                "started_at": c.get("started_at"),
                "completed_at": c.get("completed_at"),
                "details_url": c.get("details_url"),
                "app": c.get("app"),
                "required": bool(c.get("required")),
            })
        return {"by_status": by, "names": names[:20],
                "details": details,
                "failed": by["failure"] > 0, "pending": by["pending"] > 0}

    def _reviews_summary(self, reviews: list[dict]) -> dict:
        states = {}
        details = []
        for r in reviews:
            s = (r.get("state") or "").upper()
            states[s] = states.get(s, 0) + 1
            details.append({
                "state": s,
                "author": r.get("user", {}).get("login") if isinstance(r.get("user"), dict) else "",
                "submitted_at": r.get("submitted_at"),
                "commit_id": r.get("commit_id"),
                "body_excerpt": (r.get("body") or "")[:120],
            })
        return {"by_state": states,
                "approved": states.get("APPROVED", 0),
                "changes_requested": states.get("CHANGES_REQUESTED", 0),
                "details": details}

    def check_details(self, job_or_delivery: str) -> dict:
        """WS H: expose the full check/review/mergeability detail surface."""
        try:
            record, job_id, attempt_id = self._resolve_target(job_or_delivery)
        except DeliveryError as e:
            return {"ok": False, "code": e.code, "message": str(e)}
        synced = self._sync_record(record)
        record.update({k: v for k, v in synced.items()
                       if k in ("checks_summary", "reviews_summary",
                                "mergeable", "merge_state", "state",
                                "head_sha", "base_sha", "attention_reasons")})
        # ordered delivery event timeline
        timeline = self.history(record.get("delivery_id", "")) \
            if record.get("delivery_id") else []
        return {"ok": True, "record": record,
                "checks": synced.get("checks_summary", {}).get("details", []),
                "reviews": synced.get("reviews_summary", {}).get("details", []),
                "mergeable": synced.get("mergeable"),
                "merge_state": synced.get("merge_state"),
                "attention": synced.get("attention_reasons", []),
                "timeline": timeline}


    def _state_from_sync(self, synced: dict) -> str:
        pr_state = synced.get("state", "").upper()
        checks = synced.get("checks_summary", {})
        reviews = synced.get("reviews_summary", {})
        if pr_state == "MERGED":
            return MERGED
        if pr_state == "CLOSED":
            return PR_CLOSED
        if synced.get("merge_state") in ("DIRTY",) or \
                synced.get("mergeable") == "CONFLICTING":
            return MERGE_CONFLICT
        if reviews.get("changes_requested"):
            return REVIEW_CHANGES_REQUESTED
        if checks.get("failed"):
            return CI_FAILED
        if checks.get("pending"):
            return CI_PENDING
        # all available conditions green (or no checks configured)
        if not checks.get("names") and not checks.get("by_status", {}).get("pending"):
            return PR_OPEN  # NO_REQUIRED_CHECKS surfaced as attention, not green
        return MERGE_READY

    # ======================================================================
    # WORKSTREAM H — CLEANUP + RETENTION
    # ======================================================================
    def cleanup(self, job_or_delivery: str, *, safe_only: bool = True) -> dict:
        """Remove disposable resources only; durable product truth stays.

        Disposable: owned worktree (when safe), transient staging files.
        Durable (never removed): EvidenceBundle, DeliveryRecord + history,
        GitHub branch/PR identity.
        """
        try:
            record, _, _ = self._resolve_target(job_or_delivery)
        except DeliveryError as e:
            return {"ok": False, "message": str(e)}
        wt = Path(record.get("worktree") or "")
        removed = []
        # a failed/conflicted unpublished delivery preserves worktree for
        # operator recovery unless safe_only is explicitly disabled.
        unsafe = record.get("delivery_state") in (NOT_READY, NEEDS_REBASE,
                                                  MERGE_CONFLICT, DELIVERY_FAILED)
        if unsafe and safe_only:
            return {"ok": False,
                    "message": "unpublished/unclean delivery preserves worktree; "
                               "use explicit safe cleanup",
                    "removed": [], "record": record}
        if wt.exists() and self._worktree_root and wt.is_relative_to(self._worktree_root):
            import shutil
            shutil.rmtree(wt, ignore_errors=True)
            removed.append(str(wt))
        # durable truth (evidence, delivery record, PR/branch) is NOT removed
        self._persist(record, "cleanup", removed=removed)
        return {"ok": True, "message": "cleanup completed",
                "removed": removed, "record": record,
                "durable_kept": {"evidence": True, "delivery_record": True,
                                 "github_branch_pr": True}}
