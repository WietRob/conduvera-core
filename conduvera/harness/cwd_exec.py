"""Shell-free cwd executor (SHELLFREE-CWD-EXECUTOR-V1).

Replaces the bash -c worktree wrapper with a minimal Python executable that:

- validates --cwd is an absolute, existing, registered Conduvera worktree
  that resolves below the configured worktree root (no symlink escape);
- executes the target binary directly via os.chdir + os.execvpe, passing the
  argv through UNCHANGED (no shell, no string concatenation, no evaluation).

It must never invoke bash/sh, concatenate argv into a command string,
evaluate shell syntax, modify the prompt, or persist raw prompts.

Invocation (through systemd-run as ordinary argv elements):

    python3 -m conduvera.harness.cwd_exec --cwd <abs-worktree> -- <binary> <argv...>
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _worktree_root() -> Path:
    """Conduvera managed-worktree root (state_dir/worktrees)."""
    env = os.environ.get("CONDUVERA_STATE_DIR")
    if env:
        return Path(env).expanduser() / "worktrees"
    return Path.home() / ".local" / "state" / "conduvera" / "worktrees"


class CwdExecError(Exception):
    """Rejected invocation (boundary or argv violation)."""


def _resolve_within_root(root: Path, cwd: Path) -> Path:
    """Resolve a candidate cwd below root, rejecting symlink escape."""
    # Reject relative paths outright (must be an absolute worktree path).
    if not cwd.is_absolute():
        raise CwdExecError(f"cwd not absolute: {cwd}")
    root_r = root.resolve()
    # Realpath the candidate; a symlink that points outside the root
    # resolves to a path not under root -> rejected.
    try:
        cwd_r = cwd.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise CwdExecError(f"cwd does not resolve: {cwd}: {exc}") from exc
    try:
        cwd_r.relative_to(root_r)
    except ValueError as exc:
        raise CwdExecError(
            f"cwd resolves outside worktree root: {cwd}") from exc
    if not cwd_r.is_dir():
        raise CwdExecError(f"cwd is not a directory: {cwd}")
    return cwd_r


def _require_bound_worktree(
    cwd: Path,
    *,
    repo: str = "",
    base_commit: str = "",
    task_id: str = "",
    attempt_id: str = "",
) -> None:
    """Registry/worktree binding: the path must be a REAL managed worktree.

    Rejects arbitrary directories merely below the worktree root. Requires:
    - the path appears in `git worktree list --porcelain` for the allowlisted
      repository (repo_path);
    - the worktree HEAD equals the expected base_commit;
    - the task/attempt binding is reflected in the path (task_id-attempt_id).
    """
    if not repo or not Path(repo).is_dir():
        raise CwdExecError(f"repo_path not usable: {repo!r}")
    if base_commit and len(base_commit) != 40:
        raise CwdExecError(f"invalid base_commit: {base_commit!r}")

    r = subprocess.run(
        ["git", "-C", repo, "worktree", "list", "--porcelain"],
        capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise CwdExecError(f"git worktree list failed in {repo}: {r.stderr[:120]}")

    entries = _parse_worktree_porcelain(r.stdout)
    cwd_str = str(cwd.resolve())
    if cwd_str not in entries:
        raise CwdExecError(
            f"worktree not registered for {repo}: {cwd}")
    head = entries[cwd_str]
    if base_commit and head != base_commit:
        raise CwdExecError(
            f"worktree head {head[:10]} != expected base {base_commit[:10]}")

    # task/attempt binding must be reflected in the worktree dir name
    if task_id and attempt_id and (task_id not in cwd.name
                                   or attempt_id not in cwd.name):
        raise CwdExecError(
            f"task/attempt binding mismatch: {cwd.name!r} vs {task_id}/{attempt_id}")


def _parse_worktree_porcelain(text: str) -> dict[str, str]:
    """Parse `git worktree list --porcelain` -> {path: head_commit}."""
    out: dict[str, str] = {}
    cur_path = None
    cur_head = ""
    for line in text.splitlines():
        if line.startswith("worktree "):
            if cur_path:
                out[cur_path] = cur_head
            cur_path = line[len("worktree "):]
            cur_head = ""
        elif line.startswith("HEAD ") and cur_path:
            cur_head = line[len("HEAD "):]
    if cur_path:
        out[cur_path] = cur_head
    return out


def main(argv: list[str] | None = None) -> int:
    """Parse argv manually so `--cwd X -- <binary> <argv...>` works exactly.

    argparse.REMAINDER does not treat `--` as a separator the way we need
    when mixed with required options, so parse by hand:
        --cwd <path>  [--task-id T] [--attempt-id A] [--repo R] [--base B]
                      [--help]
        -- <binary> <argv...>
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd_val: str | None = None
    task_id = ""
    attempt_id = ""
    repo = ""
    base_commit = ""

    def _consume(flag: str) -> str | None:
        nonlocal argv
        if len(argv) >= 2 and argv[0] == flag:
            v = argv[1]
            argv = argv[2:]
            return v
        if argv and argv[0].startswith(flag + "="):
            v = argv[0].split("=", 1)[1]
            argv = argv[1:]
            return v
        return None

    if argv and argv[0] in ("-h", "--help"):
        print("usage: conduvera-cwd-exec --cwd <abs-worktree> "
              "[--task-id T] [--attempt-id A] [--repo R] [--base B] "
              "-- <binary> <argv...>")
        return 0
    if argv and argv[0] == "--cwd":
        cwd_val = argv[1]
        argv = argv[2:]
    elif argv and argv[0].startswith("--cwd="):
        cwd_val = argv[0].split("=", 1)[1]
        argv = argv[1:]
    task_id = _consume("--task-id") or ""
    attempt_id = _consume("--attempt-id") or ""
    repo = _consume("--repo") or ""
    base_commit = _consume("--base") or ""
    if cwd_val is None:
        raise CwdExecError("missing --cwd")
    if not argv or argv[0] != "--":
        raise CwdExecError("expected '--' separator before the command")
    cmd = argv[1:]
    if not cmd:
        raise CwdExecError("empty argv: no binary to execute")

    cwd = Path(cwd_val)
    root = _worktree_root()
    resolved = _resolve_within_root(root, cwd)
    if repo or base_commit or task_id or attempt_id:
        _require_bound_worktree(
            resolved, repo=repo, base_commit=base_commit,
            task_id=task_id, attempt_id=attempt_id)

    binary = cmd[0]
    if "/" in binary:
        bp = Path(binary)
        if not bp.is_file() or not os.access(bp, os.X_OK):
            raise CwdExecError(f"binary not executable: {binary}")
        binary_path = binary
    else:
        binary_path = binary

    os.chdir(resolved)
    # argv[0] is the program name as the child expects it; execvpe does a
    # PATH lookup for bare names and NEVER invokes a shell.
    os.execvpe(binary_path, cmd, os.environ)
    return 0  # unreachable


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CwdExecError as exc:
        print(f"conduvera-cwd-exec: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
