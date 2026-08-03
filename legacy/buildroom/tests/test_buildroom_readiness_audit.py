"""Read-only ProjectPack operational-readiness audit tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from buildroom_readiness_audit import audit_projectpacks


ALL_PHASES = ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"]


def init_repo(path: Path, origin: str = "git@github.com:Owner/repo.git") -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Audit"], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True)
    (path / "README.md").write_text("# Strategy\n")
    (path / "tests").mkdir()
    (path / "tests/test_smoke.py").write_text("def test_ok():\n    assert True\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def write_pack(packs: Path, repo: Path, name: str, *, autopilot=False, command="python3 -m pytest -q", strategy=None):
    data = {
        "project_name": name,
        "repo_path": str(repo),
        "evidence_dir": str(packs.parent / "evidence" / name),
        "default_branch": "main",
        "test_command": command,
        "github_repo": "Owner/repo",
        "autopilot_enabled": autopilot,
        "delivery_mode": "full" if autopilot else "engineering_finish_line",
        "allowed_phases": ALL_PHASES,
        "profiles": {
            "researcher": "researcher",
            "dreamer": "dreamer",
            "builder": "builder",
            "reviewer": "reviewer",
            "reporter": "orchestrator",
        },
        "execution": {
            "builder_backend": "native",
            "reviewer_backend": "native",
            "builder_model": "openai-codex/gpt-5.6-sol",
            "reviewer_model": "openai-codex/gpt-5.6-sol",
            "reviewer_independence_exception": {
                "approved": True,
                "approved_by": "owner",
                "approved_at": "2026-07-15",
            },
        },
        "strategy_files": ["README.md"] if strategy is None else strategy,
        "candidate_sources": [],
        "reviewer": {"require_no_secrets": True, "require_tests": True},
        "merge": {"require_approve_merge": True, "require_clean_test_baseline": True},
    }
    packs.mkdir(parents=True, exist_ok=True)
    (packs / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


def by_name(report, name):
    return next(item for item in report["projects"] if item["project_name"] == name)


def test_valid_manual_and_autonomous_packs_are_classified_truthfully(tmp_path):
    packs = tmp_path / "packs"
    manual_repo = tmp_path / "manual"
    peek_repo = tmp_path / "peek"
    init_repo(manual_repo, "git@github.com:Owner/manual.git")
    init_repo(peek_repo, "git@github.com:Owner/peek.git")
    write_pack(packs, manual_repo, "manual")
    write_pack(packs, peek_repo, "peekxd", autopilot=True)

    before = subprocess.check_output(["git", "status", "--porcelain"], cwd=manual_repo, text=True)
    report = audit_projectpacks(packs, projects_root=tmp_path)
    after = subprocess.check_output(["git", "status", "--porcelain"], cwd=manual_repo, text=True)

    assert report["summary"]["total"] == 2
    assert report["summary"]["autonomous_projects"] == ["peekxd"]
    assert "MANUAL_DRY_RUN_READY" in by_name(report, "manual")["classifications"]
    assert "POLICY_READY" in by_name(report, "peekxd")["classifications"]
    assert "MANUAL_DRY_RUN_READY" not in by_name(report, "peekxd")["classifications"]
    assert before == after == ""


def test_same_model_pair_is_not_described_as_independent(tmp_path):
    packs = tmp_path / "packs"
    repo = tmp_path / "repo"
    init_repo(repo)
    write_pack(packs, repo, "manual")
    review = by_name(audit_projectpacks(packs), "manual")["reviewer"]
    assert review["independent"] is False
    assert review["exception"] == "SAME_MODEL_TEMPORARY_OWNER_EXCEPTION"
    assert review["recommended_independent_model"] == "zai/glm-5.2"


def test_duplicate_projectpack_origins_are_blocked(tmp_path):
    packs = tmp_path / "packs"
    first = tmp_path / "first"
    second = tmp_path / "second"
    origin = "git@github.com:Owner/shared.git"
    init_repo(first, origin)
    init_repo(second, origin)
    write_pack(packs, first, "first")
    write_pack(packs, second, "second")
    report = audit_projectpacks(packs, projects_root=tmp_path)
    assert report["summary"]["duplicate_origin_packs"] == 2
    assert all("DUPLICATE_ORIGIN" in item["classifications"] for item in report["projects"])


def test_implausible_test_command_blocks_readiness(tmp_path):
    packs = tmp_path / "packs"
    repo = tmp_path / "repo"
    init_repo(repo)
    write_pack(packs, repo, "bad-test", command="definitely-missing-command --test")
    item = by_name(audit_projectpacks(packs), "bad-test")
    assert item["classifications"] == ["BLOCKED_TEST_COMMAND"]


def test_missing_strategy_input_blocks_readiness(tmp_path):
    packs = tmp_path / "packs"
    repo = tmp_path / "repo"
    init_repo(repo)
    write_pack(packs, repo, "bad-strategy", strategy=["missing.md"])
    item = by_name(audit_projectpacks(packs), "bad-strategy")
    assert item["classifications"] == ["BLOCKED_STRATEGY_INPUT"]


def test_candidate_source_may_resolve_from_evidence_directory(tmp_path):
    packs = tmp_path / "packs"
    repo = tmp_path / "repo"
    init_repo(repo)
    write_pack(packs, repo, "evidence-candidate")
    pack_path = packs / "evidence-candidate.yaml"
    data = yaml.safe_load(pack_path.read_text())
    data["candidate_sources"] = ["dreamer/candidate.md"]
    pack_path.write_text(yaml.safe_dump(data, sort_keys=False))
    candidate = packs.parent / "evidence" / "evidence-candidate" / "dreamer/candidate.md"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("candidate\n")

    item = by_name(audit_projectpacks(packs), "evidence-candidate")
    assert "POLICY_READY" in item["classifications"]
    assert item["missing_candidate_sources"] == []
