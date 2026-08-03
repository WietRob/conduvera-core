"""ProjectPack default-branch and scoped baseline truth."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from buildroom_core import ProjectPack
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator


def make_pack(tmp_path: Path, default_branch: str) -> ProjectPack:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return ProjectPack.from_mapping(
        {
            "project_name": f"project-{default_branch.replace('/', '-')}",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "github_repo": "owner/repository",
            "default_branch": default_branch,
            "test_command": "pytest -q",
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER"],
            "profiles": {"researcher": "researcher", "builder": "builder", "reviewer": "reviewer"},
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )


@pytest.mark.parametrize("default_branch", ["main", "master", "integration/stable"])
def test_main_green_uses_projectpack_default_branch(tmp_path, default_branch):
    pack = make_pack(tmp_path, default_branch)
    orchestrator = BuildroomOrchestrator(pack)
    pack.baseline_file.parent.mkdir(parents=True)
    pack.baseline_file.write_text(
        json.dumps({
            "project": pack.project_name,
            "repository": pack.github_repo,
            "default_branch": default_branch,
            "head": "abc123",
            "command": pack.test_command,
            "all_passed": True,
            "result": "PASS",
        })
    )
    results = [
        SimpleNamespace(returncode=0, stdout=f"{default_branch}\n"),
        SimpleNamespace(returncode=0, stdout="abc123\n"),
        SimpleNamespace(returncode=0, stdout="abc123\n"),
        SimpleNamespace(returncode=0, stdout=""),
    ]
    with patch("peekxd_buildroom_loop_v20.subprocess.run", side_effect=results) as run:
        assert orchestrator.check_main_green() is True
    assert run.call_args_list[2].args[0][-1] == f"origin/{default_branch}"


@pytest.mark.parametrize("default_branch", ["main", "master", "integration/stable"])
def test_baseline_is_project_scoped_and_checks_out_default_branch(
    tmp_path, monkeypatch, default_branch
):
    pack = make_pack(tmp_path, default_branch)
    orchestrator = BuildroomOrchestrator(pack)
    commands = []

    def fake_run(command, timeout=0):
        commands.append(command)
        if command == pack.test_command:
            return True, "12 passed", ""
        if command == "git rev-parse HEAD":
            return True, "abc123\n", ""
        if command == "git branch --show-current":
            return True, f"{default_branch}\n", ""
        return True, "", ""

    monkeypatch.setattr(orchestrator, "run_cmd", fake_run)
    baseline = orchestrator.verify_test_baseline()

    assert commands[:2] == [
        f"git checkout {default_branch}",
        f"git pull --ff-only origin {default_branch}",
    ]
    assert pack.baseline_file == tmp_path / "evidence" / "test-baseline.json"
    assert baseline["project"] == pack.project_name
    assert baseline["repository"] == pack.github_repo
    assert baseline["default_branch"] == default_branch
    assert baseline["head"] == "abc123"
    assert baseline["command"] == pack.test_command
    assert baseline["result"] == "PASS"
    assert json.loads(pack.baseline_file.read_text()) == baseline


def test_active_orchestrator_has_no_hardcoded_main_refs():
    source = Path(__import__(BuildroomOrchestrator.__module__).__file__).read_text()
    assert '"origin/main"' not in source
    assert '"git checkout main"' not in source
    assert 'gh pr create --base main' not in source
