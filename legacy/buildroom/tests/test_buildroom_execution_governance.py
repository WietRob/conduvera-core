"""Execution-governance tests for repo-safe Buildroom backends and policy."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from buildroom_core import (
    ExecutionObservation,
    ProjectPack,
    ProjectPackError,
    build_execution_command,
    execution_evidence_schema,
    resolve_project,
    validate_delegation_permissions,
    validate_execution_evidence,
)


def _mapping(tmp_path: Path, **overrides):
    data = {
        "project_name": "governed",
        "repo_path": str(tmp_path / "repo"),
        "evidence_dir": str(tmp_path / "evidence"),
        "github_repo": "Owner/governed",
        "autopilot_enabled": True,
        "delivery_mode": "full",
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
            "builder_model": None,
            "reviewer_model": None,
            "builder_fallbacks": [],
            "reviewer_fallbacks": [],
        },
    }
    data.update(overrides)
    return data


def _evidence(**overrides):
    record = {
        "schema": "execution-evidence-v1",
        "role": "BUILDER",
        "backend": "native",
        "provider": "openai-codex",
        "model": "gpt-5.6-sol",
        "backend_version": "hermes-native",
        "run_id": "run-123",
        "repo": "Owner/governed",
        "base_commit": "abc123",
        "branch": "autonomy/governed/candidate",
        "files_changed": ["src/a.py"],
        "commands_run": ["pytest -q"],
        "tests": {"command": "pytest -q", "passed": 3, "failed": 0, "exit_code": 0},
        "result": "COMPLETE",
        "blocker": None,
    }
    record.update(overrides)
    return record


def test_missing_operating_policy_fails_closed(tmp_path):
    pack = ProjectPack.from_mapping(
        {"project_name": "legacy", "repo_path": str(tmp_path / "repo"), "evidence_dir": str(tmp_path / "ev")}
    )
    assert pack.policy_defined is False
    assert pack.autopilot_enabled is False
    assert pack.allowed_phases == ()
    with pytest.raises(ProjectPackError, match="AUTOPILOT_DISABLED"):
        pack.require_autonomous_phase("RESEARCHER")


def test_disabled_autopilot_prevents_start(tmp_path):
    pack = ProjectPack.from_mapping(_mapping(tmp_path, autopilot_enabled=False))
    with pytest.raises(ProjectPackError, match="AUTOPILOT_DISABLED"):
        pack.require_autonomous_phase("RESEARCHER")


def test_research_only_blocks_every_phase_after_researcher(tmp_path):
    pack = ProjectPack.from_mapping(
        _mapping(
            tmp_path,
            autopilot_enabled=False,
            delivery_mode="research_only",
            allowed_phases=["RESEARCHER"],
        )
    )
    assert pack.phase_allowed("RESEARCHER")
    for phase in ("DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"):
        assert not pack.phase_allowed(phase)
        with pytest.raises(ProjectPackError, match="PHASE_NOT_ALLOWED"):
            pack.require_phase(phase)


def test_unknown_backend_is_rejected(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {**data["execution"], "builder_backend": "unknown"}
    with pytest.raises(ProjectPackError, match="UNKNOWN_EXECUTION_BACKEND"):
        ProjectPack.from_mapping(data)


def test_same_external_backend_and_model_is_disabled_by_owner(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {
        **data["execution"],
        "builder_backend": "codex_cli",
        "reviewer_backend": "codex_cli",
        "builder_model": "openai/codex",
        "reviewer_model": "openai/codex",
    }
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        ProjectPack.from_mapping(data)


def test_old_structured_owner_exception_does_not_activate_external_backend(tmp_path):
    data = _mapping(tmp_path)
    data["delivery_mode"] = "engineering_finish_line"
    data["execution"] = {
        **data["execution"],
        "builder_backend": "codex_cli",
        "reviewer_backend": "codex_cli",
        "builder_model": "openai/codex",
        "reviewer_model": "openai/codex",
        "reviewer_independence_exception": {
            "approved": True,
            "approved_by": "owner",
            "approved_at": "2026-07-12",
            "reason": "Separate current-head owner gate remains mandatory.",
        },
    }

    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        ProjectPack.from_mapping(data)


def test_native_backend_is_independent_when_profiles_differ(tmp_path):
    pack = ProjectPack.from_mapping(_mapping(tmp_path))
    assert pack.builder_profile == "builder"
    assert pack.reviewer_profile == "reviewer"
    assert pack.backend_identity("BUILDER") != pack.backend_identity("REVIEWER")


def test_distinct_native_profiles_same_explicit_model_require_owner_exception(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {
        **data["execution"],
        "builder_model": "openai-codex/gpt-5.6-sol",
        "reviewer_model": "openai-codex/gpt-5.6-sol",
    }
    with pytest.raises(ProjectPackError, match="BUILDER_REVIEWER_NOT_INDEPENDENT"):
        ProjectPack.from_mapping(data)


def test_same_native_profile_is_rejected(tmp_path):
    data = _mapping(tmp_path)
    data["profiles"] = {**data["profiles"], "reviewer": "builder"}
    with pytest.raises(ProjectPackError, match="BUILDER_REVIEWER_NOT_INDEPENDENT"):
        ProjectPack.from_mapping(data)


def test_codex_command_is_noninteractive_sandboxed_and_structured(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {
        **data["execution"],
        "builder_backend": "codex_cli",
        "builder_model": "gpt-codex",
    }
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        ProjectPack.from_mapping(data)


def test_opencode_reviewer_requires_non_openai_model(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {
        **data["execution"],
        "reviewer_backend": "opencode_cli",
        "reviewer_model": "openai/gpt-codex",
    }
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:opencode_cli$"):
        ProjectPack.from_mapping(data)


def test_opencode_reviewer_command_is_structured_and_read_only_role(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {
        **data["execution"],
        "reviewer_backend": "opencode_cli",
        "reviewer_model": "deepseek/deepseek-v4-pro",
    }
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:opencode_cli$"):
        ProjectPack.from_mapping(data)


def test_complete_evidence_requires_independent_observation():
    with pytest.raises(ProjectPackError, match="EVIDENCE_OBSERVATION_REQUIRED"):
        validate_execution_evidence(
            _evidence(), expected_role="BUILDER", expected_repo="Owner/governed", observation=None
        )


def test_evidence_must_match_observed_disk_and_tests():
    observation = ExecutionObservation(
        branch="autonomy/governed/candidate",
        files_changed=("src/a.py",),
        test_command="pytest -q",
        test_exit_code=0,
        base_commit="abc123",
    )
    validated = validate_execution_evidence(
        _evidence(), expected_role="BUILDER", expected_repo="Owner/governed", observation=observation
    )
    assert validated["schema"] == "execution-evidence-v1"

    with pytest.raises(ProjectPackError, match="EVIDENCE_DISK_MISMATCH"):
        validate_execution_evidence(
            _evidence(files_changed=["src/other.py"]),
            expected_role="BUILDER",
            expected_repo="Owner/governed",
            observation=observation,
        )


@pytest.mark.parametrize("backend", ["codex_cli", "opencode_cli"])
def test_canonical_evidence_rejects_owner_disabled_backend(backend):
    observation = ExecutionObservation(
        branch="autonomy/governed/candidate",
        files_changed=("src/a.py",),
        test_command="pytest -q",
        test_exit_code=0,
        base_commit="abc123",
    )
    with pytest.raises(ProjectPackError, match=rf"^BACKEND_DISABLED_BY_OWNER:{backend}$"):
        validate_execution_evidence(
            _evidence(backend=backend),
            expected_role="BUILDER",
            expected_repo="Owner/governed",
            observation=observation,
        )


def test_malformed_evidence_is_rejected():
    broken = _evidence()
    del broken["run_id"]
    with pytest.raises(ProjectPackError, match="MISSING_EXECUTION_EVIDENCE_FIELD"):
        validate_execution_evidence(
            broken,
            expected_role="BUILDER",
            expected_repo="Owner/governed",
            observation=ExecutionObservation(
                branch="autonomy/governed/candidate",
                files_changed=("src/a.py",),
                test_command="pytest -q",
                test_exit_code=0,
                base_commit="abc123",
            ),
        )


def test_external_backend_contract_never_grants_state_or_merge_authority(tmp_path):
    data = _mapping(tmp_path)
    data["execution"] = {**data["execution"], "builder_backend": "codex_cli", "builder_model": "gpt-codex"}
    with pytest.raises(ProjectPackError, match="^BACKEND_DISABLED_BY_OWNER:codex_cli$"):
        ProjectPack.from_mapping(data)


def test_read_only_delegation_cannot_receive_mutation_authority():
    validate_delegation_permissions(read_only=True, allowed_mutations=())
    with pytest.raises(ProjectPackError, match="READ_ONLY_DELEGATION_MUTATION_FORBIDDEN"):
        validate_delegation_permissions(read_only=True, allowed_mutations=("files",))


def test_canonical_execution_schema_contains_required_backend_neutral_fields():
    schema = execution_evidence_schema()
    assert schema["title"] == "execution-evidence-v1"
    assert set(schema["properties"]["backend"]["enum"]) == {"native", "codex_cli", "opencode_cli"}
    for field in (
        "role", "provider", "model", "backend_version", "run_id", "repo",
        "base_commit", "branch", "files_changed", "commands_run", "tests", "result", "blocker",
    ):
        assert field in schema["required"]


def test_real_peekxd_pack_retains_full_autonomous_policy():
    pack = resolve_project("peekxd")
    assert pack.autopilot_enabled is True
    assert pack.delivery_mode == "full"
    assert pack.allowed_phases == ("RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER")
    assert pack.builder_backend == "native"
    assert pack.reviewer_backend == "native"
    assert pack.model_for("BUILDER") == pack.model_for("REVIEWER")
    assert pack.independence_owner_approved is True


def test_real_curaops_pack_has_authorized_engineering_finish_line():
    pack = resolve_project("curaops-vrp")
    assert pack.autopilot_enabled is False
    assert pack.delivery_mode == "engineering_finish_line"
    assert pack.allowed_phases == ("RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER")
    with pytest.raises(ProjectPackError, match="AUTOPILOT_DISABLED"):
        pack.require_autonomous_phase("RESEARCHER")
    pack.require_phase("RESEARCHER")
    pack.require_phase("BUILDER")
    pack.require_phase("MERGE")


def test_profile_contracts_contain_required_hard_rules():
    root = Path.home() / ".hermes/profiles"
    builder = (root / "builder/SOUL.md").read_text()
    reviewer = (root / "reviewer/SOUL.md").read_text()
    pm = (root / "pm/SOUL.md").read_text()
    orchestrator = (root / "orchestrator/SOUL.md").read_text()

    for marker in (
        "CAPABILITIES:", "ALLOWED MUTATIONS:", "PROHIBITED MUTATIONS:", "kanban_block",
        "orchestrator-state.json", "Never merge", "external worker self-report",
        "disk diff", "backend version", "session/run ID", "post-task skill-learning review",
    ):
        assert marker.lower() in builder.lower(), marker
    for marker in (
        "independent Reviewer", "CAPABILITIES:", "No product implementation by default",
        "orchestrator-state.json", "kanban_block", "APPROVE_MERGE", "REQUEST_FIX", "BLOCK",
        "Self-reports", "security boundaries", "post-task skill-learning review",
    ):
        assert marker.lower() in reviewer.lower(), marker
    for marker in (
        "OUTPUT / EVIDENCE CONTRACT", "kanban_complete", "kanban_block",
        "No product implementation authority", "No PR merge", "history rewrite",
    ):
        assert marker.lower() in pm.lower(), marker
    for marker in (
        "OUTPUT / EVIDENCE CONTRACT", "No product implementation by default", "BACKEND ROUTING CONTRACT",
        "Runtime Unblock", "Product Engineering", "Buildroom Core Change", "Certification",
        "Read-only delegated audit/review tasks may not mutate files", "POST-INCIDENT LEARNING",
    ):
        assert marker.lower() in orchestrator.lower(), marker


def test_profile_preloads_match_declared_execution_contracts():
    root = Path.home() / ".hermes/profiles"
    builder = yaml.safe_load((root / "builder/config.yaml").read_text())
    reviewer = yaml.safe_load((root / "reviewer/config.yaml").read_text())
    pm = yaml.safe_load((root / "pm/config.yaml").read_text())
    orchestrator = yaml.safe_load((root / "orchestrator/config.yaml").read_text())
    for config in (builder, reviewer, orchestrator):
        assert {"codex", "opencode"}.isdisjoint(config["preload_skills"])
    assert set(pm["preload_skills"]) == {
        "hermes-agent", "github-issues", "github-pr-workflow", "plan", "obsidian"
    }


def test_governed_task_envelopes_require_execution_evidence_without_real_dispatch(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(_mapping(tmp_path))
    captured = {}

    def fake_create(title, profile, body, phase, **routing_authorization):
        assert routing_authorization["authorized_route_id"].startswith("route-")
        assert routing_authorization["provider"]
        assert routing_authorization["model"]
        captured[phase] = {"title": title, "profile": profile, "body": body}
        return f"t_{phase.lower()}", "OK"

    with (
        patch.object(v20, "STATE_FILE", tmp_path / "state.json"),
        patch.object(v20, "LOCK_FILE", tmp_path / "lock"),
        patch.object(v20, "BASELINE_FILE", tmp_path / "baseline.json"),
        patch.object(v20, "EVIDENCE_DIR", tmp_path / "evidence"),
        patch.object(v20, "REPO_PATH", tmp_path / "repo"),
    ):
        orchestrator = v20.BuildroomOrchestrator(pack)
        orchestrator.state.update({"cycle": 7, "current_candidate": "safe-candidate"})
        orchestrator.create_task_with_verify = fake_create
        orchestrator.dispatch_role_execution = lambda **kwargs: fake_create(
            kwargs["title"],
            kwargs["expected_profile"],
            kwargs["body"],
            kwargs["phase"],
            authorized_route_id=f"route-{kwargs['phase'].lower()}-test",
            provider="test-provider",
            model="test-model",
        )
        assert orchestrator.phase_builder_with_profile(7, "builder", 0)
        assert orchestrator.phase_reviewer_with_profile(7, "https://example/pr/1", "reviewer", 0)

    assert "execution-evidence-v1" in captured["BUILDER"]["body"]
    assert "execution-evidence-v1" in captured["REVIEWER"]["body"]
    assert captured["BUILDER"]["profile"] == "builder"
    assert captured["REVIEWER"]["profile"] == "reviewer"


def test_native_backend_is_represented_by_same_command_contract(tmp_path):
    pack = ProjectPack.from_mapping(_mapping(tmp_path))
    command = build_execution_command(
        pack,
        role="BUILDER",
        workdir=tmp_path / "worktree",
        prompt="native task envelope",
        output_path=tmp_path / "evidence.json",
    )
    assert command.backend == "native"
    assert command.argv == ()
    assert command.use_pty is False
    assert command.allowed_mutations == ("assigned_worktree",)


def test_real_native_builder_and_reviewer_models_use_temporary_owner_exception():
    root = Path.home() / ".hermes/profiles"
    builder = yaml.safe_load((root / "builder/config.yaml").read_text())["model"]
    reviewer = yaml.safe_load((root / "reviewer/config.yaml").read_text())["model"]
    assert (builder["provider"], builder["default"]) == (reviewer["provider"], reviewer["default"])
    pack = resolve_project("curaops-vrp")
    assert pack.independence_owner_approved is True
    assert pack.independence_owner_approval_ref


def test_malformed_execution_markdown_blocks_phase_gate(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(_mapping(tmp_path))
    evidence = tmp_path / "builder.md"
    evidence.write_text("# Self report only\nBUILD_COMPLETE\n")
    with (
        patch.object(v20, "STATE_FILE", tmp_path / "state.json"),
        patch.object(v20, "LOCK_FILE", tmp_path / "lock"),
        patch.object(v20, "BASELINE_FILE", tmp_path / "baseline.json"),
        patch.object(v20, "EVIDENCE_DIR", tmp_path / "evidence"),
        patch.object(v20, "REPO_PATH", tmp_path / "repo"),
    ):
        orchestrator = v20.BuildroomOrchestrator(pack)
        assert orchestrator._validate_phase_execution_evidence("BUILDER", evidence) is False


def test_valid_phase_evidence_requires_and_accepts_independent_observation(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    pack = ProjectPack.from_mapping(_mapping(tmp_path))
    record = _evidence(backend="native")
    observation = ExecutionObservation(
        branch=record["branch"],
        files_changed=tuple(record["files_changed"]),
        test_command=record["tests"]["command"],
        test_exit_code=0,
        base_commit=record["base_commit"],
    )
    with (
        patch.object(v20, "STATE_FILE", tmp_path / "state.json"),
        patch.object(v20, "LOCK_FILE", tmp_path / "lock"),
        patch.object(v20, "BASELINE_FILE", tmp_path / "baseline.json"),
        patch.object(v20, "EVIDENCE_DIR", tmp_path / "evidence"),
        patch.object(v20, "REPO_PATH", tmp_path / "repo"),
    ):
        orchestrator = v20.BuildroomOrchestrator(pack)
        with (
            patch.object(orchestrator, "_extract_execution_evidence", return_value=record),
            patch.object(orchestrator, "_observe_execution", return_value=observation),
        ):
            assert orchestrator._validate_phase_execution_evidence("BUILDER", tmp_path / "builder.md") is True


def test_disallowed_transition_does_not_mutate_orchestrator_state(tmp_path):
    import peekxd_buildroom_loop_v20 as v20

    data = _mapping(
        tmp_path,
        autopilot_enabled=False,
        delivery_mode="research_only",
        allowed_phases=["RESEARCHER"],
    )
    pack = ProjectPack.from_mapping(data)
    with (
        patch.object(v20, "STATE_FILE", tmp_path / "state.json"),
        patch.object(v20, "LOCK_FILE", tmp_path / "lock"),
        patch.object(v20, "BASELINE_FILE", tmp_path / "baseline.json"),
        patch.object(v20, "EVIDENCE_DIR", tmp_path / "evidence"),
        patch.object(v20, "REPO_PATH", tmp_path / "repo"),
    ):
        orchestrator = v20.BuildroomOrchestrator(pack)
        orchestrator.state.update({"phase": "RESEARCHER", "status": "WAITING"})
        before = dict(orchestrator.state)
        assert orchestrator.transition_to_phase("BUILDER") is False
        assert orchestrator.state == before
