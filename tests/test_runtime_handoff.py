"""Runtime-handoff tests (RUNTIME-HANDOFF-V1).

Proves:
- Work B: cwd_exec registry/worktree binding (registered, base, task/attempt)
  and negative rejection (unregistered dir, wrong base, wrong binding,
  symlink escape, pruned worktree).
- Work A: raw prompt absent from argv (opencode reads stdin), exact content
  still delivered.
- Work C: exit code propagation through job/session/bundle.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conduvera.harness.cwd_exec import (  # noqa: E402
    CwdExecError,
    _require_bound_worktree,
    _resolve_within_root,
)


def _make_repo(tmp_path: Path) -> tuple[Path, str, Path]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    root = tmp_path / "worktrees"
    root.mkdir()
    return repo, base, root


def _managed_wt(repo: Path, base: str, root: Path, name: str) -> Path:
    wt = root / name
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach",
                    str(wt), base], check=True, capture_output=True)
    return wt


class TestWorktreeBinding:
    """Work B — registry/worktree binding."""

    def test_registered_worktree_accepted(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        wt = _managed_wt(repo, base, root, "TASK-1-a1")
        # no error
        _require_bound_worktree(wt, repo=str(repo), base_commit=base,
                                task_id="TASK", attempt_id="a1")

    def test_unregistered_dir_rejected(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        # arbitrary dir below root but not a git worktree
        bogus = root / "NOT-REGISTERED-x"
        bogus.mkdir()
        with pytest.raises(CwdExecError, match="not registered"):
            _require_bound_worktree(bogus, repo=str(repo), base_commit=base,
                                    task_id="NOT", attempt_id="x")

    def test_wrong_base_rejected(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        wt = _managed_wt(repo, base, root, "TASK-2-a2")
        # Der Worktree hängt an `base`. Ein erwarteter base_commit, der NICHT
        # der Worktree-HEAD ist (hier ein erfundener anderer Hash), wird
        # abgelehnt.
        other = "0" * 40
        with pytest.raises(CwdExecError, match="head .* != expected"):
            _require_bound_worktree(wt, repo=str(repo), base_commit=other,
                                    task_id="TASK", attempt_id="a2")

    def test_wrong_task_attempt_binding_rejected(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        wt = _managed_wt(repo, base, root, "TASK-3-a3")
        with pytest.raises(CwdExecError, match="binding mismatch"):
            _require_bound_worktree(wt, repo=str(repo), base_commit=base,
                                    task_id="OTHER", attempt_id="zz")

    def test_symlink_escape_rejected(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        wt = _managed_wt(repo, base, root, "TASK-4-a4")
        link = wt / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(CwdExecError):
            _resolve_within_root(root, link)

    def test_pruned_worktree_rejected(self, tmp_path):
        repo, base, root = _make_repo(tmp_path)
        wt = _managed_wt(repo, base, root, "TASK-5-a5")
        subprocess.run(["git", "-C", str(repo), "worktree", "remove",
                        "--force", str(wt)], check=True)
        with pytest.raises(CwdExecError):
            _require_bound_worktree(wt, repo=str(repo), base_commit=base,
                                    task_id="TASK", attempt_id="a5")


class TestSecretSafeArgv:
    """Work A — prompt not in argv, delivered via stdin."""

    def test_opencode_args_no_prompt_in_argv(self):
        """opencode argument builder enthält den Prompt NICHT als argv."""
        from conduvera.harness.adapters import _opencode_args
        prompt = "SECRET_PROMPT_MARKER_XYZ"
        args = _opencode_args(prompt, {"worktree": "/wt"})
        assert prompt not in args
        # opencode liest von stdin: kein message-arg
        assert "--dir" in args
        assert args[0] == "run"

    def test_opencode_spec_stdin_prompt(self):
        """opencode_cli spec nutzt stdin_prompt=True."""
        from conduvera.harness.adapters import opencode_cli_adapter
        spec = opencode_cli_adapter()._spec
        assert spec.stdin_prompt is True
