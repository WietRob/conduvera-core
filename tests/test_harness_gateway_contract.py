"""Tests for the Matrix OS generic Harness/Gateway contract."""

from __future__ import annotations

import pytest

from curaops.harness.gateway import (
    HarnessGatewayRegistry,
    list_editor_surfaces,
    list_gateway_capabilities,
    list_runners,
    list_tools,
)


def test_gateway_registry_lists_generic_runner_families_without_runtime_execution() -> None:
    registry = HarnessGatewayRegistry.default()

    assert {runner.runner_id for runner in registry.runners} == {
        "hermes",
        "opencode",
        "local-shell",
    }
    assert all(runner.execution_status == "future-adapter-contract-only" for runner in registry.runners)
    assert all(not runner.runtime_enabled for runner in registry.runners)
    assert all("not executed by Matrix OS" in runner.external_boundary for runner in registry.runners)


def test_gateway_capabilities_answer_launch_observe_approve_convert_boundaries() -> None:
    capability_map = {capability.capability_id: capability for capability in list_gateway_capabilities()}

    assert capability_map["launch"].owned_by_matrix_os == "descriptor only"
    assert capability_map["observe"].owned_by_matrix_os == "evidence contract"
    assert capability_map["approve_block"].owned_by_matrix_os == "policy decision boundary only"
    assert capability_map["convert_evidence"].owned_by_matrix_os == "translation adapter contract"
    assert all(not capability.runtime_implemented for capability in capability_map.values())


def test_gateway_registry_is_runner_agnostic_for_zed_mcp_and_computer_use_tools() -> None:
    registry = HarnessGatewayRegistry.default()

    assert {surface.surface_id for surface in registry.editor_surfaces} == {
        "matrix-ui-code-editor",
        "zed-mcp-future",
    }
    assert registry.get_editor_surface("zed-mcp-future").owner == "Zed/editor integration remains external"
    assert registry.get_tool("peekxd").tool_family == "computer-use"
    assert registry.get_tool("safety-guard").can_block is True
    assert registry.get_tool("agent-evidence-plane").can_emit_evidence is True
    assert registry.get_tool("failure-driven-loop").can_emit_evidence is True


def test_gateway_external_projects_remain_standalone() -> None:
    registry = HarnessGatewayRegistry.default()
    external = registry.external_project_boundaries()

    assert external["hermes"] == "standalone; future runner adapter only"
    assert external["opencode"] == "standalone; future runner adapter only"
    assert external["zed-mcp"] == "standalone editor/plugin/runtime; no hardcoded CCC/AAL/Evidence logic"
    assert external["peekxd"] == "standalone computer-use tool; future capability descriptor only"
    assert external["agent-evidence-plane"] == "standalone evidence producer; translation-only adapter exists"
    assert external["safety-guard"] == "standalone safety producer; translation-only adapter exists"
    assert external["failure-driven-loop"] == "standalone failure-loop producer; translation-only adapter exists"


def test_gateway_unknown_lookup_fails_closed() -> None:
    registry = HarnessGatewayRegistry.default()

    with pytest.raises(KeyError):
        registry.get_runner("zed")
    with pytest.raises(KeyError):
        registry.get_tool("ai-router")
    with pytest.raises(KeyError):
        registry.get_editor_surface("vscode")


def test_gateway_module_level_lists_are_stable_views() -> None:
    assert len(list_runners()) == 3
    assert len(list_tools()) == 4
    assert len(list_editor_surfaces()) == 2
