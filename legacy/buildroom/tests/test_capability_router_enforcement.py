"""Capability Router mandatory enforcement tests."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPTS = Path.home() / ".hermes/scripts"
sys.path.insert(0, str(SCRIPTS))

import fleet_router
import peekxd_buildroom_loop_v20 as v20
from fleet_router import RoutingError, TaskContext


def policy() -> dict:
    return fleet_router.load_policy(force_reload=True)


def healthy(*pairs: tuple[str, str]) -> dict:
    return {
        "observed_at": "test",
        "checks": {
            f"{provider}/{model}": {
                "status": "HEALTHY",
                "observed_at": "2099-01-01T00:00:00+00:00",
                "expires_at": "2099-01-01T01:00:00+00:00",
            }
            for provider, model in pairs
        },
    }


def test_routing_rules_exist_only_in_yaml() -> None:
    import orchestrator_router_bridge

    source = inspect.getsource(fleet_router)
    bridge_source = inspect.getsource(orchestrator_router_bridge)
    assert "designer_triggers" not in source
    assert "programmer_triggers" not in source
    assert "researcher_triggers" not in source
    for profile_name in (
        "designer", "programmer", "researcher", "dreamer", "builder",
        "reviewer", "frontend", "backend", "ops", "pm", "analyst",
        "writer", "local-qwen-prod", "local-qwen-max",
        "local-gemma-vision-short",
    ):
        assert f'profile == "{profile_name}"' not in source
    assert "keyword heuristics" not in bridge_source
    assert "_triggers" not in bridge_source
    p = policy()
    assert p["routes"]
    assert all("id" in rule and "profile" in rule and "match" in rule for rule in p["routes"])


def test_programmer_override_selects_real_model() -> None:
    h = healthy(("openai-codex", "gpt-5.6-sol"))
    decision = fleet_router.route_and_authorize(
        TaskContext(intent="help me refactor this function", owner_facing=True),
        request_id="req-programmer",
        policy=policy(),
        health=h,
    )
    assert decision.profile == "programmer"
    assert decision.selected_provider == "openai-codex"
    assert decision.selected_model == "gpt-5.6-sol"
    assert decision.temporary_override_applied is True
    assert decision.route_id


def test_designer_canonical_without_active_override() -> None:
    p = policy()
    p = json.loads(json.dumps(p))
    p["temporary_override"]["enabled"] = False
    h = healthy(("zai", "glm-5.2"))
    decision = fleet_router.route_and_authorize(
        TaskContext(intent="design a user flow for login"),
        request_id="req-designer",
        policy=p,
        health=h,
    )
    assert decision.profile == "designer"
    assert decision.selected_provider == "zai"
    assert decision.selected_model == "glm-5.2"
    assert decision.temporary_override_applied is False


def test_frontend_without_design_is_blocked() -> None:
    with pytest.raises(RoutingError, match="NEEDS_DESIGNER_HANDOFF"):
        fleet_router.route_and_authorize(
            TaskContext(intent="implement the frontend dashboard", approved_design_evidence=False),
            request_id="req-frontend",
            policy=policy(),
            health=healthy(("openai-codex", "gpt-5.6-sol")),
        )


def test_reviewer_independence_selects_non_codex() -> None:
    h = healthy(("kimi-coding", "kimi-k2.6"), ("deepseek", "deepseek-v4-pro"))
    decision = fleet_router.route_and_authorize(
        TaskContext(intent="review this PR", builder_provider="openai-codex"),
        request_id="req-reviewer",
        policy=policy(),
        health=h,
    )
    assert decision.profile == "reviewer"
    assert decision.selected_provider != "openai-codex"
    assert decision.independence_result == "PASSED"


def test_gemma_unavailable_is_blocked_runtime() -> None:
    with pytest.raises(RoutingError, match="LOCAL_GEMMA_UNAVAILABLE"):
        fleet_router.route_and_authorize(
            TaskContext(intent="analyze this screenshot locally", privacy_local_only=True),
            request_id="req-gemma",
            policy=policy(),
            health=healthy(("custom", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf")),
        )


def test_qwen_profiles_have_distinct_runtime_contracts() -> None:
    p = policy()
    prod = p["local_profiles"]["local-qwen-prod"]
    maxp = p["local_profiles"]["local-qwen-max"]
    assert prod["runtime_contract"] != maxp["runtime_contract"]
    assert prod["runtime_contract"]["experimental"] is False
    assert maxp["runtime_contract"]["experimental"] is True
    assert maxp["runtime_contract"]["max_turns"] > prod["runtime_contract"]["max_turns"]

    profiles = Path.home() / ".hermes/profiles"
    prod_cfg = json.loads(json.dumps(__import__("yaml").safe_load(
        (profiles / "local-qwen-prod/config.yaml").read_text()
    )))
    max_cfg = json.loads(json.dumps(__import__("yaml").safe_load(
        (profiles / "local-qwen-max/config.yaml").read_text()
    )))
    assert prod_cfg["agent"]["max_turns"] == prod["runtime_contract"]["max_turns"]
    assert max_cfg["agent"]["max_turns"] == maxp["runtime_contract"]["max_turns"]
    assert prod_cfg["toolsets"] == ["hermes-cli", *prod["runtime_contract"]["tools"]]
    assert max_cfg["toolsets"] == ["hermes-cli", *maxp["runtime_contract"]["tools"]]


def test_runtime_profile_models_match_router_policy() -> None:
    import yaml

    p = policy()
    profiles = Path.home() / ".hermes/profiles"
    for profile in ("designer", "programmer", "reviewer"):
        configured = yaml.safe_load((profiles / profile / "config.yaml").read_text())["model"]
        expected = p["canonical_preferences"][profile]["preferred"]
        override = p.get("temporary_override") or {}
        if (
            override.get("enabled")
            and profile in override.get("profiles", [])
            and profile not in override.get("excluded_profiles", [])
        ):
            expected = {"provider": override["provider"], "model": override["model"]}
        assert configured["provider"] == expected["provider"]
        assert configured["default"] == expected["model"]


def test_direct_dispatch_without_route_id_fails_closed() -> None:
    o = object.__new__(v20.BuildroomOrchestrator)
    o.kanban_create = MagicMock()
    with pytest.raises(RoutingError, match="AUTHORIZED_ROUTE_ID_REQUIRED"):
        o.dispatch_profile(
            profile="researcher",
            provider="kimi-coding",
            model="kimi-k2.6",
            authorized_route_id="",
            title="test",
            body="test",
            phase="RESEARCHER",
        )
    o.kanban_create.assert_not_called()


def test_authorization_is_single_use_and_identity_bound() -> None:
    h = healthy(("openai-codex", "gpt-5.6-sol"))
    decision = fleet_router.route_and_authorize(
        TaskContext(intent="help me refactor this function", owner_facing=True),
        request_id="req-bound",
        policy=policy(),
        health=h,
    )
    fleet_router.consume_route_authorization(
        decision.route_id,
        profile="programmer",
        provider="openai-codex",
        model="gpt-5.6-sol",
    )
    with pytest.raises(RoutingError, match="ROUTE_AUTHORIZATION_NOT_FOUND"):
        fleet_router.consume_route_authorization(
            decision.route_id,
            profile="programmer",
            provider="openai-codex",
            model="gpt-5.6-sol",
        )


def test_real_orchestrator_phase_methods_use_mandatory_hook() -> None:
    source = inspect.getsource(v20.BuildroomOrchestrator)
    assert "def dispatch_role_execution(" in source
    assert "def dispatch_profile(" in source
    for method_name in (
        "_dispatch_researcher",
        "_dispatch_dreamer",
        "_dispatch_compliance_retry",
        "phase_builder_with_profile",
        "phase_reviewer_with_profile",
    ):
        method_source = inspect.getsource(getattr(v20.BuildroomOrchestrator, method_name))
        assert "dispatch_role_execution" in method_source
        assert "create_task_with_verify" not in method_source


def test_route_log_has_required_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "routes.jsonl"
    monkeypatch.setattr(fleet_router, "ROUTE_LOG", log)
    h = healthy(("openai-codex", "gpt-5.6-sol"))
    decision = fleet_router.route_and_authorize(
        TaskContext(intent="help me refactor this function", owner_facing=True),
        request_id="req-log",
        policy=policy(),
        health=h,
    )
    record = json.loads(log.read_text().splitlines()[-1])
    for key in (
        "route_id", "request_id", "profile", "reason_code", "confidence",
        "selected_provider", "selected_model", "model_health",
        "temporary_override_applied", "required_preconditions",
        "independence_result", "local_profile", "escalation",
    ):
        assert key in record
    assert record["route_id"] == decision.route_id
