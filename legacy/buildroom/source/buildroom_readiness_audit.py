#!/usr/bin/env python3
"""Read-only operational readiness audit for canonical Buildroom ProjectPacks."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from buildroom_core import ALL_PHASES, ProjectPack, ProjectPackError


DEFAULT_PROJECTS_DIR = Path.home() / ".hermes/buildroom/projects"
DEFAULT_PROJECTS_ROOT = Path.home() / "projects"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode, result.stdout.strip()


def normalize_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    value = origin.strip()
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
        normalized = f"{host}/{path}"
    elif "://" in value:
        parsed = urlparse(value)
        normalized = f"{parsed.hostname or ''}{parsed.path}"
    else:
        normalized = value
    return normalized.removesuffix(".git").rstrip("/").lower()


def _origin(repo: Path) -> str | None:
    code, output = _git(repo, "remote", "get-url", "origin")
    return output if code == 0 and output else None


def _test_command_readiness(repo: Path, command: str) -> dict:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return {"plausible": False, "reason": f"parse-error:{type(exc).__name__}"}
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens.pop(0)
    if not tokens:
        return {"plausible": False, "reason": "empty-command"}
    commands = [tokens[0]]
    commands.extend(tokens[index + 1] for index, token in enumerate(tokens[:-1]) if token in {"&&", ";"})
    missing = [executable for executable in commands if shutil.which(executable) is None]
    if missing:
        return {"plausible": False, "reason": f"missing-executable:{','.join(missing)}"}
    if tokens[:2] == ["npm", "test"]:
        package = repo / "package.json"
        if not package.exists():
            return {"plausible": False, "reason": "npm-test-without-package-json"}
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except (json.JSONDecodeError, OSError):
            return {"plausible": False, "reason": "invalid-package-json"}
        if "test" not in scripts:
            return {"plausible": False, "reason": "npm-test-script-missing"}
    if "pytest" in tokens and not (repo / "tests").exists():
        return {"plausible": False, "reason": "pytest-tests-directory-missing"}
    if tokens[:2] == ["cargo", "test"] and not (repo / "Cargo.toml").exists():
        return {"plausible": False, "reason": "cargo-manifest-missing"}
    if tokens[0] == "cmake" and not (repo / "CMakeLists.txt").exists():
        return {"plausible": False, "reason": "cmake-project-missing"}
    return {"plausible": True, "reason": "command-and-project-seam-present"}


def _checkout_origin_inventory(projects_root: Path) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    if not projects_root.is_dir():
        return grouped
    for candidate in sorted(projects_root.iterdir()):
        if not candidate.is_dir() or not (candidate / ".git").exists():
            continue
        origin = normalize_origin(_origin(candidate))
        if origin:
            grouped.setdefault(origin, []).append(str(candidate.resolve()))
    return {origin: paths for origin, paths in grouped.items() if len(paths) > 1}


def audit_projectpacks(
    projects_dir: Path = DEFAULT_PROJECTS_DIR,
    *,
    projects_root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict:
    """Inspect ProjectPacks and repositories without modifying either."""
    projects_dir = Path(projects_dir).expanduser().resolve()
    loaded: list[tuple[Path, ProjectPack]] = []
    projects: list[dict] = []
    for path in sorted(projects_dir.glob("*.yaml")):
        try:
            loaded.append((path, ProjectPack.from_yaml(path)))
        except ProjectPackError as exc:
            projects.append(
                {
                    "project_name": path.stem,
                    "project_pack": str(path),
                    "classifications": ["BLOCKED_REPO_CONFIG"],
                    "blocker": str(exc),
                }
            )

    origins: dict[str, list[str]] = {}
    pack_origins: dict[str, str | None] = {}
    for _, pack in loaded:
        normalized = normalize_origin(_origin(pack.repo_path))
        pack_origins[pack.project_name] = normalized
        if normalized:
            origins.setdefault(normalized, []).append(pack.project_name)

    duplicate_pack_names = {
        name
        for names in origins.values()
        if len(names) > 1
        for name in names
    }
    full_phases = set(ALL_PHASES)
    for path, pack in loaded:
        repo_exists = pack.repo_path.is_dir()
        git_metadata = (pack.repo_path / ".git").exists() if repo_exists else False
        origin = _origin(pack.repo_path) if git_metadata else None
        status_code, status = _git(pack.repo_path, "status", "--porcelain") if git_metadata else (1, "")
        branch_code, current_branch = _git(pack.repo_path, "branch", "--show-current") if git_metadata else (1, "")
        test = _test_command_readiness(pack.repo_path, pack.test_command) if repo_exists else {
            "plausible": False,
            "reason": "repository-missing",
        }
        missing_strategy = [item for item in pack.strategy_files if not (pack.repo_path / item).exists()]
        missing_candidates = [
            item
            for item in pack.candidate_sources
            if not (pack.repo_path / item).exists() and not (pack.evidence_dir / item).exists()
        ]
        same_model = bool(pack.builder_model and pack.builder_model == pack.reviewer_model)
        exception = (
            "SAME_MODEL_TEMPORARY_OWNER_EXCEPTION"
            if same_model and pack.independence_owner_approved
            else None
        )
        reviewer = {
            "profile": pack.reviewer_profile,
            "backend": pack.reviewer_backend,
            "model": pack.reviewer_model or "profile-configured-model",
            "builder_model": pack.builder_model or "profile-configured-model",
            "independent": not same_model,
            "exception": exception,
            "exception_reference": pack.independence_owner_approval_ref or None,
            "require_no_secrets": pack.reviewer_require_no_secrets,
            "require_tests": pack.reviewer_require_tests,
            "recommended_independent_model": "zai/glm-5.2",
        }
        classifications: list[str]
        blocker = None
        if pack.project_name in duplicate_pack_names:
            classifications = ["DUPLICATE_ORIGIN"]
            blocker = pack_origins[pack.project_name]
        elif not repo_exists or not git_metadata or status_code != 0 or not pack.policy_defined:
            classifications = ["BLOCKED_REPO_CONFIG"]
            blocker = "repository, git metadata, status, or operating policy unavailable"
        elif not test["plausible"]:
            classifications = ["BLOCKED_TEST_COMMAND"]
            blocker = test["reason"]
        elif missing_strategy or missing_candidates:
            classifications = ["BLOCKED_STRATEGY_INPUT"]
            blocker = f"missing strategy={missing_strategy}; candidates={missing_candidates}"
        else:
            classifications = ["POLICY_READY"]
            if (
                not pack.autopilot_enabled
                and pack.delivery_mode == "engineering_finish_line"
                and set(pack.allowed_phases) == full_phases
            ):
                classifications.append("MANUAL_DRY_RUN_READY")
        projects.append(
            {
                "project_name": pack.project_name,
                "project_pack": str(path),
                "canonical_repository_path": str(pack.repo_path),
                "repository_exists": repo_exists,
                "git_origin": origin,
                "normalized_origin": pack_origins[pack.project_name],
                "duplicate_origin": pack.project_name in duplicate_pack_names,
                "default_branch": pack.default_branch,
                "current_branch": current_branch if branch_code == 0 else None,
                "delivery_mode": pack.delivery_mode,
                "autopilot_enabled": pack.autopilot_enabled,
                "allowed_phases": list(pack.allowed_phases),
                "profiles": {
                    "researcher": pack.researcher_profile,
                    "dreamer": pack.dreamer_profile,
                    "builder": pack.builder_profile,
                    "reviewer": pack.reviewer_profile,
                    "reporter": pack.reporter_profile,
                },
                "test_command": pack.test_command,
                "test_command_readiness": test,
                "strategy_files": list(pack.strategy_files),
                "missing_strategy_files": missing_strategy,
                "candidate_sources": list(pack.candidate_sources),
                "missing_candidate_sources": missing_candidates,
                "merge_policy": {
                    "require_approve_merge": pack.merge_require_approve_merge,
                    "require_clean_test_baseline": pack.merge_require_clean_test_baseline,
                },
                "reviewer": reviewer,
                "working_tree": {
                    "status_read_succeeded": status_code == 0,
                    "clean": status_code == 0 and not status,
                    "porcelain_lines": len(status.splitlines()) if status else 0,
                },
                "classifications": classifications,
                "blocker": blocker,
            }
        )

    projects.sort(key=lambda item: item["project_name"])
    blocked_labels = {
        "BLOCKED_REPO_CONFIG",
        "BLOCKED_TEST_COMMAND",
        "BLOCKED_STRATEGY_INPUT",
        "DUPLICATE_ORIGIN",
    }
    summary = {
        "total": len(projects),
        "POLICY_READY": sum("POLICY_READY" in item["classifications"] for item in projects),
        "MANUAL_DRY_RUN_READY": sum("MANUAL_DRY_RUN_READY" in item["classifications"] for item in projects),
        "blocked": sum(bool(blocked_labels.intersection(item["classifications"])) for item in projects),
        "duplicate_origin_packs": sum("DUPLICATE_ORIGIN" in item["classifications"] for item in projects),
        "autonomous_projects": [item["project_name"] for item in projects if item.get("autopilot_enabled")],
    }
    return {
        "schema": "projectpack-readiness-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only_repository_audit": True,
        "summary": summary,
        "duplicate_checkout_origins": _checkout_origin_inventory(Path(projects_root).expanduser().resolve()),
        "reviewer_truth": {
            "current_pairing": "openai-codex/gpt-5.6-sol for Builder and Reviewer",
            "independence": False,
            "exception": "SAME_MODEL_TEMPORARY_OWNER_EXCEPTION",
            "recommended_independent_model": "zai/glm-5.2",
        },
        "projects": projects,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_projectpacks(args.projects_dir, projects_root=args.projects_root)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().resolve().write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["summary"]["blocked"] == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
