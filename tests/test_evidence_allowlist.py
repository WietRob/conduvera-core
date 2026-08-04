"""Evidence-Allowlist-Test (DOD-04, baseline-goal).

Every committed file must either match an allowed pattern or be source/
documentation. Every forbidden pattern must have zero committed matches.
The allowlist is machine-readable (evidence/evidence-allowlist.yaml).
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "evidence/evidence-allowlist.yaml"

# Source/docs that are always committable (not generated evidence).
SOURCE_PREFIXES = (
    "curaops/",
    "tests/",
    "docs/",
    "scripts/",
    "contracts/",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Makefile",
    "AGENTS.md",
    ".cursorrules",
    ".gitignore",
    "README.md",
    "frontend/",
)


def committed_files() -> list[str]:
    r = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=ROOT,
    )
    return [l for l in r.stdout.splitlines() if l.strip()]


def test_allowlist_is_machine_readable():
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))
    assert data["schema"] == "evidence-allowlist.v1"
    assert isinstance(data["allowed_patterns"], list)
    assert isinstance(data["forbidden_patterns"], list)
    assert len(data["allowed_patterns"]) > 0
    assert len(data["forbidden_patterns"]) > 0


def test_no_forbidden_artifacts_in_tree():
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))
    violations = []
    for f in committed_files():
        for pat in data["forbidden_patterns"]:
            if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f, pat.replace("**", "*")):
                violations.append((f, pat))
    assert not violations, f"Forbidden artifacts committed: {violations}"


def test_all_evidence_files_are_allowlisted():
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8"))
    unlisted = []
    for f in committed_files():
        if f.startswith("fixtures/live/") or f.startswith("fixtures/run/"):
            ok = any(fnmatch.fnmatch(f, pat) for pat in data["allowed_patterns"])
            if not ok:
                unlisted.append(f)
    assert not unlisted, f"Live/run fixtures not in allowlist: {unlisted}"
