#!/usr/bin/env python3
"""Fail-closed review-convergence policy for Buildroom engineering finish lines."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


class ReviewConvergenceError(RuntimeError):
    """A bounded finish-line invariant was violated."""


@dataclass(frozen=True)
class ReviewConvergencePolicy:
    enabled: bool = False
    require_prepush_sweep: bool = True
    max_initial_pushes: int = 1
    max_correction_rounds: int = 1
    max_review_pairs: int = 2
    max_compressions: int = 2
    max_session_minutes: int = 90
    require_worktree_lease: bool = True
    require_remote_inventory: bool = True
    remote_inventory_exempt_prs: tuple[int, ...] = ()
    commit_reference_pattern: str = r"\b(?:CR|ADR|PC)-\d{3,5}\b"
    protected_change_classes: tuple[str, ...] = (
        "B2",
        "SECURITY",
        "TENANT",
        "AUDIT",
        "MIGRATION",
    )
    pre_push_gate_commands: tuple[str, ...] = ()
    self_improvement_prefixes: tuple[str, ...] = (
        ".hermes/",
        "buildroom/",
        "profiles/",
        "skills/",
        "memories/",
        "routing/",
    )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ReviewConvergencePolicy":
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            require_prepush_sweep=bool(data.get("require_prepush_sweep", True)),
            max_initial_pushes=int(data.get("max_initial_pushes", 1)),
            max_correction_rounds=int(data.get("max_correction_rounds", 1)),
            max_review_pairs=int(data.get("max_review_pairs", 2)),
            max_compressions=int(data.get("max_compressions", 2)),
            max_session_minutes=int(data.get("max_session_minutes", 90)),
            require_worktree_lease=bool(data.get("require_worktree_lease", True)),
            require_remote_inventory=bool(data.get("require_remote_inventory", True)),
            remote_inventory_exempt_prs=tuple(
                int(item) for item in data.get("remote_inventory_exempt_prs", ())
            ),
            commit_reference_pattern=str(
                data.get("commit_reference_pattern", cls.commit_reference_pattern)
            ),
            protected_change_classes=tuple(
                str(item).upper()
                for item in data.get("protected_change_classes", cls.protected_change_classes)
            ),
            pre_push_gate_commands=tuple(
                str(item) for item in data.get("pre_push_gate_commands", ())
            ),
            self_improvement_prefixes=tuple(
                str(item)
                for item in data.get(
                    "self_improvement_prefixes", cls.self_improvement_prefixes
                )
            ),
        )


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def new_review_epoch(
    *,
    scope: Any,
    contract: Any,
    initial_head: str,
    started_at: str | None = None,
) -> dict[str, Any]:
    if not initial_head:
        raise ReviewConvergenceError("REVIEW_EPOCH_INITIAL_HEAD_REQUIRED")
    return {
        "scope_hash": stable_hash(scope),
        "contract_hash": stable_hash(contract),
        "initial_head": initial_head,
        "push_count": 0,
        "correction_rounds_used": 0,
        "review_pair_count": 0,
        "reviewed_head": None,
        "prepush_sweep_status": "PENDING",
        "commit_reference_status": "PENDING",
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "compression_count": 0,
        "handoff_status": "NOT_REQUIRED",
        "terminal_status": None,
    }


def ensure_review_epoch(
    state: dict[str, Any],
    *,
    scope: Any,
    contract: Any,
    initial_head: str,
) -> dict[str, Any]:
    """Create once; task IDs, goal wording, and later heads never reset the budget."""
    existing = state.get("review_epoch")
    if existing is None:
        existing = new_review_epoch(
            scope=scope, contract=contract, initial_head=initial_head
        )
        state["review_epoch"] = existing
        return existing
    if existing.get("scope_hash") != stable_hash(scope):
        raise ReviewConvergenceError("REVIEW_EPOCH_SCOPE_CHANGED")
    if existing.get("contract_hash") != stable_hash(contract):
        raise ReviewConvergenceError("REVIEW_EPOCH_CONTRACT_CHANGED")
    return existing


def mark_prepush_sweep(epoch: dict[str, Any], *, head: str, approved: bool) -> None:
    epoch["prepush_sweep_status"] = "APPROVE_MERGE" if approved else "REQUEST_FIX"
    epoch["prepush_sweep_head"] = head


def authorize_push(
    epoch: dict[str, Any],
    policy: ReviewConvergencePolicy,
    *,
    head: str,
    kind: str,
) -> None:
    if epoch.get("terminal_status"):
        raise ReviewConvergenceError("GATE_BLOCKED:REVIEW_EPOCH_TERMINAL")
    if policy.require_prepush_sweep and (
        epoch.get("prepush_sweep_status") != "APPROVE_MERGE"
        or epoch.get("prepush_sweep_head") != head
    ):
        raise ReviewConvergenceError("PREPUSH_ADVERSARIAL_SWEEP_REQUIRED")
    push_kind = kind.lower()
    if push_kind == "initial":
        if int(epoch.get("push_count", 0)) >= policy.max_initial_pushes:
            raise ReviewConvergenceError("GATE_BLOCKED:PUSH_BUDGET_EXHAUSTED")
    elif push_kind == "correction":
        if int(epoch.get("push_count", 0)) < 1:
            raise ReviewConvergenceError("INITIAL_PUSH_REQUIRED")
        if int(epoch.get("correction_rounds_used", 0)) >= policy.max_correction_rounds:
            raise ReviewConvergenceError("GATE_BLOCKED:CORRECTION_BUDGET_EXHAUSTED")
        epoch["correction_rounds_used"] = int(
            epoch.get("correction_rounds_used", 0)
        ) + 1
    else:
        raise ReviewConvergenceError(f"UNKNOWN_PUSH_KIND:{kind}")
    epoch["push_count"] = int(epoch.get("push_count", 0)) + 1
    epoch["last_pushed_head"] = head


def record_review_pair(
    epoch: dict[str, Any],
    policy: ReviewConvergencePolicy,
    *,
    head: str,
    green: bool,
) -> None:
    count = int(epoch.get("review_pair_count", 0))
    if count >= policy.max_review_pairs:
        raise ReviewConvergenceError("GATE_BLOCKED:REVIEW_PAIR_BUDGET_EXHAUSTED")
    epoch["review_pair_count"] = count + 1
    epoch["reviewed_head"] = head
    if green:
        epoch["terminal_status"] = "DONE"
    elif epoch["review_pair_count"] >= policy.max_review_pairs:
        epoch["terminal_status"] = "GATE_BLOCKED"


def assert_product_lane_paths(
    paths: Iterable[str], policy: ReviewConvergencePolicy
) -> None:
    offenders = sorted(
        path
        for path in paths
        if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in policy.self_improvement_prefixes)
    )
    if offenders:
        raise ReviewConvergenceError(
            "PRODUCT_LANE_SELF_IMPROVEMENT_FORBIDDEN:" + ",".join(offenders)
        )


def require_session_mutation_allowed(
    epoch: dict[str, Any],
    policy: ReviewConvergencePolicy,
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(timezone.utc)
    started = datetime.fromisoformat(str(epoch["started_at"]))
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed_minutes = (current - started).total_seconds() / 60
    if (
        int(epoch.get("compression_count", 0)) >= policy.max_compressions
        or elapsed_minutes >= policy.max_session_minutes
    ):
        epoch["handoff_status"] = "REQUIRED"
        epoch["terminal_status"] = "GATE_BLOCKED"
        raise ReviewConvergenceError("GATE_BLOCKED:SESSION_HANDOFF_REQUIRED")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _fail_for_immutable_remote_metadata(
    repo: Path, branch: str, offending_commits: Iterable[str]
) -> None:
    remote_ref = f"refs/remotes/origin/{branch}"
    if _git(repo, "show-ref", "--verify", "--quiet", remote_ref).returncode != 0:
        return
    for sha in offending_commits:
        if _git(repo, "merge-base", "--is-ancestor", sha, remote_ref).returncode == 0:
            raise ReviewConvergenceError("CLEAN_REPLACEMENT_REQUIRED")


def _worktree_for_branch(repo: Path, branch: str) -> Path | None:
    result = _git(repo, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        return None
    current: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = Path(line.removeprefix("worktree ")).resolve()
        elif line == f"branch refs/heads/{branch}" and current is not None:
            return current
    return None


def _assert_remote_inventory(
    *,
    cwd: Path,
    branch: str,
    candidate_files: tuple[str, ...],
    candidate_subjects: str,
    policy: ReviewConvergencePolicy,
) -> None:
    inventory = subprocess.run(
        [
            "gh", "pr", "list", "--state", "open", "--limit", "1000",
            "--json", "number,title,headRefName",
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if inventory.returncode != 0:
        raise ReviewConvergenceError("UNVERIFIED_PR_INVENTORY")
    try:
        pull_requests = json.loads(inventory.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewConvergenceError("UNVERIFIED_PR_INVENTORY") from exc
    references = set(re.findall(policy.commit_reference_pattern, candidate_subjects))
    candidate_set = set(candidate_files)
    for pull_request in pull_requests:
        number = int(pull_request["number"])
        if number in policy.remote_inventory_exempt_prs or pull_request.get("headRefName") == branch:
            continue
        title_refs = set(re.findall(
            policy.commit_reference_pattern, str(pull_request.get("title", ""))
        ))
        if references & title_refs:
            raise ReviewConvergenceError(f"ID_COLLISION:PR_{number}")
        details = subprocess.run(
            ["gh", "pr", "view", str(number), "--json", "files"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        if details.returncode != 0:
            raise ReviewConvergenceError("UNVERIFIED_PR_INVENTORY")
        try:
            paths = {item["path"] for item in json.loads(details.stdout)["files"]}
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ReviewConvergenceError("UNVERIFIED_PR_INVENTORY") from exc
        overlap = sorted(candidate_set & paths)
        if overlap:
            raise ReviewConvergenceError(
                f"SCOPE_OVERLAP:PR_{number}:" + ",".join(overlap)
            )


def run_pre_push_gates(
    *,
    repo: str | Path,
    branch: str,
    base_ref: str,
    head: str,
    epoch: dict[str, Any],
    policy: ReviewConvergencePolicy,
) -> tuple[str, ...]:
    root = Path(repo).resolve()
    command_cwd = root
    if policy.require_worktree_lease:
        command_cwd = _worktree_for_branch(root, branch) or root
        if command_cwd == root:
            raise ReviewConvergenceError("WORKTREE_LEASE_REQUIRED")
    candidate_range = f"{base_ref}..{head}"
    if _git(root, "merge-base", "--is-ancestor", base_ref, head).returncode != 0:
        raise ReviewConvergenceError("BRANCH_BEHIND_CURRENT_MAIN")
    files_result = _git(root, "diff", "--name-only", candidate_range)
    if files_result.returncode != 0:
        raise ReviewConvergenceError("CANDIDATE_SCOPE_DIFF_FAILED")
    files = tuple(line for line in files_result.stdout.splitlines() if line)
    assert_product_lane_paths(files, policy)

    subjects = _git(root, "log", "--format=%H%x00%s", candidate_range)
    if subjects.returncode != 0:
        raise ReviewConvergenceError("COMMIT_SUBJECT_SCAN_FAILED")
    offending: list[str] = []
    pattern = re.compile(policy.commit_reference_pattern)
    for line in subjects.stdout.splitlines():
        sha, _, subject = line.partition("\x00")
        if not pattern.search(subject):
            offending.append(sha)
    if offending:
        epoch["commit_reference_status"] = "FAILED"
        _fail_for_immutable_remote_metadata(root, branch, offending)
        raise ReviewConvergenceError("COMMIT_REFERENCE_GATE_FAILED")

    if policy.require_remote_inventory:
        _assert_remote_inventory(
            cwd=command_cwd,
            branch=branch,
            candidate_files=files,
            candidate_subjects=subjects.stdout,
            policy=policy,
        )

    for command in policy.pre_push_gate_commands:
        rendered = command.format(range=candidate_range, base=base_ref, head=head, branch=branch)
        result = subprocess.run(
            rendered,
            cwd=command_cwd,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            epoch["commit_reference_status"] = "FAILED"
            _fail_for_immutable_remote_metadata(root, branch, _git(root, "rev-list", candidate_range).stdout.split())
            raise ReviewConvergenceError(
                f"PRE_PUSH_GATE_FAILED:{rendered}:{result.stderr.strip() or result.stdout.strip()}"
            )
    epoch["commit_reference_status"] = "PASSED"
    epoch["commit_reference_head"] = head
    return files
