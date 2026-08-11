"""Real Git worktree manager for MANAGED sessions (INTERNAL-ALPHA-V1).

Every MANAGED repository task receives a REAL Git worktree created from an
exact base commit via `git worktree add --detach <path> <base-commit>`.
The association is proven through Git itself (`git worktree list --porcelain`,
repository identity, exact bound commit). A directory merely named "worktree"
is not accepted.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    """Raised when a real Git worktree cannot be created/proven."""


@dataclass
class WorktreeBinding:
    """Proven Git worktree association."""

    path: str
    repo: str
    base_commit: str
    worktree_id: str
    head_commit: str
    detached: bool = True

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "repo": self.repo,
                "base_commit": self.base_commit, "worktree_id": self.worktree_id,
                "head_commit": self.head_commit, "detached": str(self.detached)}


class WorktreeManager:
    """Creates and proves real Git worktrees from exact base commits."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _run(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(list(args), capture_output=True, text=True,
                              timeout=60, cwd=str(cwd) if cwd else None)

    def create(
        self,
        *,
        repo_path: str | Path,
        base_commit: str,
        task_id: str,
        attempt_id: str,
    ) -> WorktreeBinding:
        """Create a real detached Git worktree at the exact base commit."""
        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists() and not (repo / ".git").is_file():
            raise WorktreeError(f"not a Git repository: {repo}")
        # Resolve the exact commit (fail closed if the object is missing)
        r = self._run("git", "-C", str(repo), "rev-parse", base_commit + "^{commit}")
        if r.returncode != 0:
            raise WorktreeError(f"base commit {base_commit} not resolvable in {repo}")
        exact = r.stdout.strip()

        wt_path = self.base_dir / f"{task_id}-{attempt_id}"
        if wt_path.exists():
            # Collision protection: never reuse an existing worktree.
            raise WorktreeError(f"worktree path already exists: {wt_path}")
        r = self._run("git", "-C", str(repo), "worktree", "add", "--detach",
                      str(wt_path), exact)
        if r.returncode != 0:
            raise WorktreeError(f"git worktree add failed: {r.stderr.strip()[:200]}")

        binding = self.prove(repo, wt_path, exact)
        return binding

    def prove(self, repo: Path, wt_path: Path, base_commit: str) -> WorktreeBinding:
        """Prove the association through Git itself (--porcelain)."""
        r = self._run("git", "-C", str(repo), "worktree", "list", "--porcelain")
        if r.returncode != 0 or str(wt_path.resolve()) not in r.stdout:
            raise WorktreeError(
                f"worktree {wt_path} not listed by git worktree list --porcelain")
        # worktree ID
        wid = ""
        head = ""
        current_block = ""
        for line in r.stdout.splitlines():
            if line.startswith("worktree "):
                current_block = line[len("worktree "):].strip()
            elif line.startswith("id "):
                wid = line[len("id "):].strip()
            elif line.startswith("HEAD "):
                if current_block and Path(current_block).resolve() == wt_path.resolve():
                    head = line[len("HEAD "):].strip()
        if not head:
            raise WorktreeError(f"worktree {wt_path} has no HEAD in --porcelain")
        # HEAD must equal the exact base commit (detached)
        if head != base_commit:
            # Allow rev-parse equivalence (base may be a short SHA)
            r2 = self._run("git", "-C", str(repo), "rev-parse", head)
            if r2.returncode != 0 or r2.stdout.strip() != base_commit:
                raise WorktreeError(
                    f"worktree HEAD {head} != base commit {base_commit}")
        return WorktreeBinding(
            path=str(wt_path),
            repo=str(repo),
            base_commit=base_commit,
            worktree_id=wid,
            head_commit=head,
        )

    def remove(self, wt_path: str | Path, repo_path: str | Path) -> None:
        """Remove a session-owned worktree (never a foreign path)."""
        wt = Path(wt_path).expanduser().resolve()
        if not wt.is_relative_to(self.base_dir):
            raise WorktreeError(f"refusing to remove outside base dir: {wt}")
        repo = Path(repo_path).expanduser().resolve()
        self._run("git", "-C", str(repo), "worktree", "remove", "--force", str(wt))
        self._run("git", "-C", str(repo), "worktree", "prune")
