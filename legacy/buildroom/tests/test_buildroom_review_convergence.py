from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from buildroom_review_convergence import (
    ReviewConvergenceError,
    ReviewConvergencePolicy,
    assert_product_lane_paths,
    authorize_push,
    ensure_review_epoch,
    mark_prepush_sweep,
    require_session_mutation_allowed,
    run_pre_push_gates,
)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def initialized_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "review-convergence@example.invalid")
    git(repo, "config", "user.name", "Review Convergence Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "PC-0001: base")
    return repo, git(repo, "rev-parse", "HEAD")


def epoch(head: str = "a" * 40) -> dict:
    state: dict = {}
    return ensure_review_epoch(
        state,
        scope={"files": ["src/a.py"]},
        contract={"goal": "finish"},
        initial_head=head,
    )


def test_second_unauthorized_initial_push_is_blocked() -> None:
    policy = ReviewConvergencePolicy(enabled=True)
    data = epoch()
    mark_prepush_sweep(data, head="b" * 40, approved=True)
    authorize_push(data, policy, head="b" * 40, kind="initial")
    with pytest.raises(ReviewConvergenceError, match="PUSH_BUDGET_EXHAUSTED"):
        authorize_push(data, policy, head="b" * 40, kind="initial")


def test_second_correction_round_is_blocked() -> None:
    policy = ReviewConvergencePolicy(enabled=True)
    data = epoch()
    mark_prepush_sweep(data, head="b" * 40, approved=True)
    authorize_push(data, policy, head="b" * 40, kind="initial")
    mark_prepush_sweep(data, head="c" * 40, approved=True)
    authorize_push(data, policy, head="c" * 40, kind="correction")
    mark_prepush_sweep(data, head="d" * 40, approved=True)
    with pytest.raises(ReviewConvergenceError, match="CORRECTION_BUDGET_EXHAUSTED"):
        authorize_push(data, policy, head="d" * 40, kind="correction")


@pytest.mark.parametrize("state_change", [{"task_id": "new-task"}, {"goal": "solve and finish"}])
def test_new_task_or_solve_and_finish_does_not_reset_budget(state_change: dict) -> None:
    state: dict = {}
    data = ensure_review_epoch(
        state,
        scope={"files": ["src/a.py"]},
        contract={"goal": "finish"},
        initial_head="a" * 40,
    )
    data["push_count"] = 1
    state.update(state_change)
    again = ensure_review_epoch(
        state,
        scope={"files": ["src/a.py"]},
        contract={"goal": "finish"},
        initial_head="b" * 40,
    )
    assert again is data
    assert again["initial_head"] == "a" * 40
    assert again["push_count"] == 1


def test_commit_without_reference_is_blocked_before_push(tmp_path: Path) -> None:
    repo, base = initialized_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature/no-ref")
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    git(repo, "commit", "-qam", "fix: missing reference")
    head = git(repo, "rev-parse", "HEAD")
    data = epoch(base)
    with pytest.raises(ReviewConvergenceError, match="COMMIT_REFERENCE_GATE_FAILED"):
        run_pre_push_gates(
            repo=repo,
            branch="feature/no-ref",
            base_ref=base,
            head=head,
            epoch=data,
            policy=ReviewConvergencePolicy(
                enabled=True,
                require_worktree_lease=False,
                require_remote_inventory=False,
            ),
        )
    assert data["commit_reference_status"] == "FAILED"


def test_immutable_remote_metadata_failure_requires_clean_replacement(tmp_path: Path) -> None:
    repo, base = initialized_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature/no-ref")
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    git(repo, "commit", "-qam", "fix: missing reference")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/feature/no-ref", head)
    with pytest.raises(ReviewConvergenceError, match="CLEAN_REPLACEMENT_REQUIRED"):
        run_pre_push_gates(
            repo=repo,
            branch="feature/no-ref",
            base_ref=base,
            head=head,
            epoch=epoch(base),
            policy=ReviewConvergencePolicy(
                enabled=True,
                require_worktree_lease=False,
                require_remote_inventory=False,
            ),
        )


def test_product_lane_cannot_change_self_improvement_files() -> None:
    with pytest.raises(
        ReviewConvergenceError, match="PRODUCT_LANE_SELF_IMPROVEMENT_FORBIDDEN"
    ):
        assert_product_lane_paths(
            ["src/product.py", "skills/hermes-buildroom/SKILL.md"],
            ReviewConvergencePolicy(enabled=True),
        )


def test_session_compression_boundary_stops_mutation() -> None:
    data = epoch()
    data["compression_count"] = 2
    with pytest.raises(ReviewConvergenceError, match="SESSION_HANDOFF_REQUIRED"):
        require_session_mutation_allowed(
            data, ReviewConvergencePolicy(enabled=True, max_compressions=2)
        )
    assert data["handoff_status"] == "REQUIRED"


def test_session_ninety_minute_boundary_stops_mutation() -> None:
    now = datetime.now(timezone.utc)
    data = epoch()
    data["started_at"] = (now - timedelta(minutes=90)).isoformat()
    with pytest.raises(ReviewConvergenceError, match="SESSION_HANDOFF_REQUIRED"):
        require_session_mutation_allowed(
            data, ReviewConvergencePolicy(enabled=True), now=now
        )


def test_green_candidate_runs_configured_range_gates(tmp_path: Path) -> None:
    repo, base = initialized_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "fix/cr-0317")
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    git(repo, "commit", "-qam", "fix(CR-0317): candidate")
    head = git(repo, "rev-parse", "HEAD")
    data = epoch(base)
    files = run_pre_push_gates(
        repo=repo,
        branch="fix/cr-0317",
        base_ref=base,
        head=head,
        epoch=data,
        policy=ReviewConvergencePolicy(
            enabled=True,
            require_worktree_lease=False,
            require_remote_inventory=False,
            pre_push_gate_commands=("git diff --check {range}",),
        ),
    )
    assert files == ("README.md",)
    assert data["commit_reference_status"] == "PASSED"
    assert data["commit_reference_head"] == head
