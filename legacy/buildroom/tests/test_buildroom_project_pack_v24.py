"""v0.24 ProjectPack repo-agnostic field tests."""

from __future__ import annotations

import textwrap

from types import SimpleNamespace
from unittest.mock import patch

from buildroom_core import ProjectPack, resolve_project


def _write_pack(tmp_path):
    yaml_path = tmp_path / "test-proj.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            f"""\
            project_name: test-proj
            repo_path: {tmp_path}/repo
            evidence_dir: {tmp_path}/evidence
            github_repo: MyOrg/test-repo
            researcher_focus_areas: |
              Analyze custom/repo/core.py and custom/repo/api.py.
            dreamer_epic_hints: |
              Priority A — Custom API hardening.
              Priority B — CLI workflow cleanup.
            strategy_files:
              - docs/strategy/custom.md
            builder:
              branch_prefix: autonomy/test-proj
            """
        ),
        encoding="utf-8",
    )
    return resolve_project(str(yaml_path))


def test_project_pack_loads_github_repo_field(tmp_path):
    yaml_path = tmp_path / "test-proj.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            project_name: test-proj
            repo_path: /tmp/test-repo
            evidence_dir: /tmp/test-evidence
            github_repo: MyOrg/test-repo
            """
        ),
        encoding="utf-8",
    )

    pack = resolve_project(str(yaml_path))

    assert pack.github_repo == "MyOrg/test-repo"


def test_project_pack_loads_repo_agnostic_template_fields(tmp_path):
    yaml_path = tmp_path / "test-proj.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            project_name: test-proj
            repo_path: /tmp/test-repo
            evidence_dir: /tmp/test-evidence
            researcher_focus_areas: |
              Analyze core safety and API boundaries.
            dreamer_epic_hints: |
              Prefer CLI-first candidates.
            """
        ),
        encoding="utf-8",
    )

    pack = resolve_project(str(yaml_path))

    assert pack.researcher_focus_areas.strip() == "Analyze core safety and API boundaries."
    assert pack.dreamer_epic_hints.strip() == "Prefer CLI-first candidates."


def test_orchestrator_uses_pack_paths_and_github_repo(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)

    orchestrator = v20.BuildroomOrchestrator(pack)

    assert orchestrator.pack.github_repo == "MyOrg/test-repo"
    assert orchestrator.repo_path == tmp_path / "repo"
    assert orchestrator.evidence_dir == tmp_path / "evidence"


def test_check_open_prs_uses_project_pack_github_repo(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)

    with patch.object(v20.subprocess, "run") as run:
        run.return_value.stdout = "[]"
        orchestrator.check_open_prs()

    args = run.call_args.args[0]
    assert "--repo" in args
    assert args[args.index("--repo") + 1] == "MyOrg/test-repo"
    assert args[args.index("--limit") + 1] == "1000"


def test_check_open_prs_fails_closed_when_inventory_command_errors(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)

    with patch.object(v20.subprocess, "run", side_effect=OSError("gh unavailable")):
        count, prs = orchestrator.check_open_prs()

    assert count is None
    assert prs == []


def test_engineering_finish_line_does_not_require_zero_open_prs(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(
        {
            "project_name": "test-proj",
            "repo_path": str(tmp_path / "repo"),
            "evidence_dir": str(tmp_path / "evidence"),
            "github_repo": "MyOrg/test-repo",
            "autopilot_enabled": True,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"],
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
            },
        }
    )
    orchestrator = v20.BuildroomOrchestrator(pack)
    open_prs = [{"number": number, "url": f"https://example.test/pull/{number}"} for number in range(1, 35)]

    with (
        patch.object(orchestrator, "check_main_green", return_value=True),
        patch.object(orchestrator, "check_open_prs", return_value=(34, open_prs)),
        patch.object(orchestrator, "check_active_builders", return_value=False),
        patch.object(orchestrator, "check_no_revert_policy", return_value=(True, [])),
    ):
        safety = orchestrator.safety_checks()

    assert safety["open_prs"] is True


def test_main_check_rejects_untracked_even_when_synced(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(
        {
            "project_name": "test-proj",
            "repo_path": str(tmp_path / "repo"),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": True,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER"],
            "profiles": {"researcher": "researcher", "builder": "builder", "reviewer": "reviewer"},
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )
    orchestrator = v20.BuildroomOrchestrator(pack)
    results = [
        SimpleNamespace(returncode=0, stdout="main\n"),
        SimpleNamespace(returncode=0, stdout="abc123\n"),
        SimpleNamespace(returncode=0, stdout="abc123\n"),
        SimpleNamespace(returncode=0, stdout="?? local-control-plane\n"),
    ]

    with patch.object(v20.subprocess, "run", side_effect=results) as run:
        assert orchestrator.check_main_green() is False

    assert all("--untracked-files=no" not in call.args[0] for call in run.call_args_list)


def test_engineering_finish_line_main_check_rejects_outdated_main(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(
        {
            "project_name": "test-proj",
            "repo_path": str(tmp_path / "repo"),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": True,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER"],
            "profiles": {"researcher": "researcher", "builder": "builder", "reviewer": "reviewer"},
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )
    orchestrator = v20.BuildroomOrchestrator(pack)
    results = [
        SimpleNamespace(returncode=0, stdout="main\n"),
        SimpleNamespace(returncode=0, stdout="old\n"),
        SimpleNamespace(returncode=0, stdout="new\n"),
        SimpleNamespace(returncode=0, stdout=""),
    ]

    with patch.object(v20.subprocess, "run", side_effect=results):
        assert orchestrator.check_main_green() is False


def test_builder_branch_prefix_comes_from_project_pack(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)
    orchestrator.state.update({"current_candidate": "safe-candidate"})

    with patch.object(orchestrator, "dispatch_role_execution", return_value=("t_mock", "OK")):
        orchestrator.phase_builder_with_profile(7, "builder", 0)

    assert orchestrator.state["builder_branch"].startswith("autonomy/test-proj/safe-candidate-")


def test_custom_project_researcher_body_uses_pack_focus_areas(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)
    body = orchestrator.build_researcher_body(7, {"spec": "Custom spec"})

    assert "Analyze custom/repo/core.py" in body
    assert "PeekXD analysis" not in body


def test_custom_project_dreamer_body_uses_pack_epic_hints(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)
    body = orchestrator.build_dreamer_body(7, "/tmp/research.md", {"spec": "Custom spec"})

    assert "Priority A — Custom API hardening" in body
    assert "ADR-0006" not in body


def test_custom_project_reporter_uses_project_name(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = _write_pack(tmp_path)
    orchestrator = v20.BuildroomOrchestrator(pack)
    orchestrator.state.update({"current_candidate": "safe-candidate", "pr_open": "https://example/pr/1"})

    assert "test-proj Buildroom Cycle" in orchestrator.build_reporter_message(7)
    assert "PeekXD Buildroom" not in orchestrator.build_reporter_message(7)
