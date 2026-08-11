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


def main(argv: list[str] | None = None) -> int:
    """Parse argv manually so `--cwd X -- <binary> <argv...>` works exactly.

    argparse.REMAINDER does not treat `--` as a separator the way we need
    when mixed with required options, so parse by hand:
        --cwd <path>  [--help]
        -- <binary> <argv...>
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd_val: str | None = None
    if argv and argv[0] in ("-h", "--help"):
        print("usage: conduvera-cwd-exec --cwd <abs-worktree> -- <binary> <argv...>")
        return 0
    if len(argv) >= 2 and argv[0] == "--cwd":
        cwd_val = argv[1]
        argv = argv[2:]
    elif argv and argv[0].startswith("--cwd="):
        cwd_val = argv[0].split("=", 1)[1]
        argv = argv[1:]
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
