"""Tests for Matrix OS evidence adapter registry/discovery."""

from __future__ import annotations

from typer.testing import CliRunner

import pytest

from curaops.cli.main import app
from curaops.evidence import ValidationError
from curaops.evidence.adapters.registry import (
    get_adapter_descriptor,
    list_adapter_descriptors,
)

runner = CliRunner()


def test_registry_contains_exactly_existing_two_adapters() -> None:
    descriptors = list_adapter_descriptors()

    assert [descriptor.adapter_id for descriptor in descriptors] == [
        "agent-evidence-plane",
        "safety-guard",
        "failure-loop",
    ]


def test_agent_evidence_plane_descriptor_metadata() -> None:
    descriptor = get_adapter_descriptor("agent-evidence-plane")

    assert descriptor.name == "agent-evidence-plane Thin Adapter"
    assert descriptor.source_project == "agent-evidence-plane"
    assert descriptor.module_path == "curaops.evidence.adapters.agent_evidence_plane"
    assert descriptor.docs_path == "docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md"
    assert descriptor.input_contract == "agent-evidence-plane JSONL schema_version 0.1.0"
    assert descriptor.execution_mode == "translation-only"
    assert descriptor.production_status == "local-contract-only / not-production-runtime"
    assert descriptor.external_repo_policy == "standalone; not vendored; not modified by Matrix OS"
    assert descriptor.cli_commands == (
        "python3 -m curaops.cli.main evidence convert-agent-plane INPUT.jsonl OUTPUT.jsonl",
    )
    assert descriptor.supported_event_types == (
        "agent.run.started",
        "agent.run.completed",
        "agent.run.failed",
        "failure.observed",
    )


def test_safety_guard_descriptor_metadata() -> None:
    descriptor = get_adapter_descriptor("safety-guard")

    assert descriptor.name == "Safety Guard Adapter Contract"
    assert descriptor.source_project == "CuraOps Safety Guard"
    assert descriptor.module_path == "curaops.evidence.adapters.safety_guard"
    assert descriptor.docs_path == "docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md"
    assert descriptor.input_contract == "Safety Guard result JSONL schema_version safety-guard.result.v1"
    assert descriptor.execution_mode == "translation-only"
    assert descriptor.production_status == "local-contract-only / not-production-runtime"
    assert descriptor.external_repo_policy == "standalone; not vendored; not executed by Matrix OS"
    assert descriptor.cli_commands == (
        "python3 -m curaops.cli.main evidence convert-safety-guard INPUT.jsonl OUTPUT.jsonl",
    )
    assert descriptor.supported_event_types == (
        "safety_guard.check.completed",
        "safety_guard.action.allowed",
        "safety_guard.action.blocked",
        "safety_guard.approval.required",
    )


def test_each_registered_adapter_is_translation_only() -> None:
    descriptors = list_adapter_descriptors()

    assert descriptors
    assert {descriptor.execution_mode for descriptor in descriptors} == {"translation-only"}


def test_unknown_adapter_lookup_fails_closed() -> None:
    with pytest.raises(ValidationError, match="unknown evidence adapter"):
        get_adapter_descriptor("unknown-adapter")


def test_cli_lists_registered_adapters() -> None:
    result = runner.invoke(app, ["evidence", "adapters"])

    assert result.exit_code == 0
    assert "agent-evidence-plane" in result.output
    assert "safety-guard" in result.output
    assert "failure-loop" in result.output
    assert "translation-only" in result.output
    assert "not-production-runtime" in result.output


def test_cli_show_agent_evidence_plane_descriptor() -> None:
    result = runner.invoke(app, ["evidence", "adapter", "show", "agent-evidence-plane"])

    assert result.exit_code == 0
    assert "agent-evidence-plane Thin Adapter" in result.output
    assert "agent.run.completed" in result.output
    assert "convert-agent-plane" in result.output
    assert "docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md" in result.output


def test_cli_show_safety_guard_descriptor() -> None:
    result = runner.invoke(app, ["evidence", "adapter", "show", "safety-guard"])

    assert result.exit_code == 0
    assert "Safety Guard Adapter Contract" in result.output
    assert "safety_guard.action.blocked" in result.output
    assert "convert-safety-guard" in result.output
    assert "docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md" in result.output


def test_cli_show_unknown_adapter_exits_nonzero() -> None:
    result = runner.invoke(app, ["evidence", "adapter", "show", "unknown-adapter"])

    assert result.exit_code == 1
    assert "unknown evidence adapter" in result.output
