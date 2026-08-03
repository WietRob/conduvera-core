"""Explicit terminal result contract for every Buildroom run outcome."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from buildroom_core import ProjectPack
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator, BuildroomRunResult


ALL_PHASES = ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"]


def make_pack(tmp_path: Path) -> ProjectPack:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return ProjectPack.from_mapping(
        {
            "project_name": "synthetic-results",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
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
        }
    )


def orchestrator(tmp_path: Path, monkeypatch) -> BuildroomOrchestrator:
    instance = BuildroomOrchestrator(make_pack(tmp_path))
    monkeypatch.setattr(instance, "acquire_lock", lambda: True)
    monkeypatch.setattr(instance, "release_lock", lambda: None)
    monkeypatch.setattr(instance, "reconcile_state", lambda: None)
    monkeypatch.setattr(
        instance,
        "safety_checks",
        lambda: {
            "main_green": True,
            "open_prs": True,
            "active_builders": True,
            "no_revert_policy": True,
            "no_revert_missing_profiles": [],
        },
    )
    instance.state.update({"cycle": 1, "phase": "RESEARCHER", "status": "NEXT_CYCLE"})
    return instance


def test_result_enum_is_exact():
    assert {item.value for item in BuildroomRunResult} == {
        "PHASE_EXECUTED",
        "PHASE_ALREADY_TERMINAL",
        "LOCK_UNAVAILABLE",
        "PROJECTPACK_BLOCKED",
        "STATE_MISMATCH",
        "DISPATCH_BLOCKED",
        "DISPATCH_FAILED",
        "INTERNAL_ERROR",
    }


def test_run_source_has_no_bare_or_implicit_return():
    source = Path(BuildroomOrchestrator.run.__code__.co_filename).read_text()
    tree = ast.parse(source)
    run = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run")
    returns = [node for node in ast.walk(run) if isinstance(node, ast.Return)]
    assert returns
    assert all(node.value is not None for node in returns)
    assert isinstance(run.body[-1], ast.Try)
    assert isinstance(run.body[-1].finalbody[-1], ast.Expr) or run.body[-1].finalbody


def test_lock_unavailable_is_explicit(tmp_path, monkeypatch):
    instance = BuildroomOrchestrator(make_pack(tmp_path))
    monkeypatch.setattr(instance, "acquire_lock", lambda: False)
    assert instance.run() is BuildroomRunResult.LOCK_UNAVAILABLE


def test_state_mismatch_and_terminal_are_explicit(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    assert instance.run(autonomous=False, phase_limit="DREAMER", reconcile=False) is BuildroomRunResult.STATE_MISMATCH
    instance.state["phase"] = "STOPPED_AFTER_RESEARCHER"
    assert instance.run(autonomous=False, phase_limit="STOPPED_AFTER_RESEARCHER", reconcile=False) is BuildroomRunResult.PHASE_ALREADY_TERMINAL


def test_projectpack_and_safety_blocks_are_explicit(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    monkeypatch.setattr(instance, "require_pack_phase", lambda *_args, **_kwargs: False)
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.PROJECTPACK_BLOCKED

    instance = orchestrator(tmp_path / "safety", monkeypatch)
    monkeypatch.setattr(
        instance,
        "safety_checks",
        lambda: {
            "main_green": False,
            "open_prs": True,
            "active_builders": True,
            "no_revert_policy": True,
            "no_revert_missing_profiles": [],
        },
    )
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.PROJECTPACK_BLOCKED


def test_dispatch_failure_and_no_progress_are_explicit(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    monkeypatch.setattr(instance, "load_cycle_directive", lambda _cycle: {})
    monkeypatch.setattr(instance, "build_researcher_body", lambda *_args: "body")
    monkeypatch.setattr(instance, "phase_researcher_with_body", lambda *_args: False)
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.DISPATCH_FAILED

    instance = orchestrator(tmp_path / "waiting", monkeypatch)
    instance.state["status"] = "WAITING"
    monkeypatch.setattr(instance, "check_phase_complete", lambda *_args: (False, "TASK_PENDING"))
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.DISPATCH_BLOCKED


def test_successful_single_dispatch_is_phase_executed(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(instance, "load_cycle_directive", lambda _cycle: {})
    monkeypatch.setattr(instance, "build_researcher_body", lambda *_args: "body")
    monkeypatch.setattr(instance, "phase_researcher_with_body", lambda cycle, *_args: calls.append(cycle) or True)
    assert instance.run(autonomous=False, phase_limit="RESEARCHER", reconcile=False) is BuildroomRunResult.PHASE_EXECUTED
    assert calls == [1]
    assert instance.state["status"] == "WAITING"


def test_pending_manual_phase_does_not_consume_authorization(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    instance.state["status"] = "WAITING"
    consumed = []
    monkeypatch.setattr(instance, "check_phase_complete", lambda *_args: (False, "TASK_PENDING"))
    result = instance.run(
        autonomous=False,
        phase_limit="RESEARCHER",
        reconcile=False,
        before_phase_side_effect=lambda: consumed.append(True),
    )
    assert result is BuildroomRunResult.DISPATCH_BLOCKED
    assert consumed == []


def test_missing_directive_does_not_consume_authorization(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    consumed = []
    monkeypatch.setattr(instance, "load_cycle_directive", lambda _cycle: {})
    monkeypatch.setattr(instance, "build_researcher_body", lambda *_args: "__BLOCKED_MISSING_DIRECTIVE__")
    result = instance.run(
        autonomous=False,
        phase_limit="RESEARCHER",
        reconcile=False,
        before_phase_side_effect=lambda: consumed.append(True),
    )
    assert result is BuildroomRunResult.DISPATCH_BLOCKED
    assert consumed == []


def test_denied_next_phase_transition_is_not_false_success(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    instance.state["status"] = "WAITING"
    monkeypatch.setattr(instance, "check_phase_complete", lambda *_args: (True, "DONE"))
    monkeypatch.setattr(instance, "transition_to_phase", lambda _phase: False)
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.PROJECTPACK_BLOCKED


def test_failed_compliance_retry_dispatch_is_not_false_success(tmp_path, monkeypatch):
    instance = orchestrator(tmp_path, monkeypatch)
    instance.state.update({"status": "WAITING", "compliance_required": True})
    monkeypatch.setattr(instance, "check_phase_complete", lambda *_args: (True, "DONE"))
    monkeypatch.setattr(instance, "check_bound_evidence", lambda *_args: (True, tmp_path / "evidence.md"))
    monkeypatch.setattr(
        instance,
        "validate_researcher_directive_compliance",
        lambda _path: (False, "NONCOMPLIANT", {}),
    )
    monkeypatch.setattr(instance, "_dispatch_compliance_retry", lambda *_args: False)
    assert instance.run(autonomous=False, reconcile=False) is BuildroomRunResult.DISPATCH_FAILED


def test_internal_exception_returns_internal_error_and_releases_lock(tmp_path, monkeypatch):
    instance = BuildroomOrchestrator(make_pack(tmp_path))
    released = []
    monkeypatch.setattr(instance, "acquire_lock", lambda: True)
    monkeypatch.setattr(instance, "release_lock", lambda: released.append(True))
    monkeypatch.setattr(instance, "reconcile_state", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert instance.run() is BuildroomRunResult.INTERNAL_ERROR
    assert released == [True]
