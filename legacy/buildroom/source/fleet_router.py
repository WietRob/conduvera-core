#!/usr/bin/env python3
"""Mandatory capability router for the Hermes agent fleet.

Profile-specific routing policy lives exclusively in routing.yaml. This module
implements only generic matching, prerequisite, health, model-selection,
independence, escalation, logging, and one-shot authorization operations.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

FLEET_DIR = Path.home() / ".hermes/fleet"
ROUTING_YAML = FLEET_DIR / "routing.yaml"
HEALTH_JSON = FLEET_DIR / "model-health.json"
ROUTE_LOG = FLEET_DIR / "route-log.jsonl"


class RoutingError(RuntimeError):
    """Exact fail-closed routing blocker."""


@dataclass(frozen=True)
class TaskContext:
    intent: str
    artifact: str = ""
    owner_facing: bool = False
    governed_repo: bool = False
    buildroom_phase: str = ""
    mutation_requested: bool = False
    approved_design_evidence: bool = False
    approved_candidate: bool = False
    assigned_worktree: bool = False
    acceptance_criteria: bool = False
    test_contract: bool = False
    risk: str = "medium"
    binding_required: bool = False
    privacy_local_only: bool = False
    builder_provider: str = ""
    bounded_scope: bool = False


@dataclass(frozen=True)
class RouteDecision:
    route_id: str
    request_id: str
    profile: str
    reason_code: str
    confidence: str
    selected_provider: str
    selected_model: str
    model_health: str
    temporary_override_applied: bool
    required_preconditions: list[str] = field(default_factory=list)
    independence_result: str = "NOT_APPLICABLE"
    local_profile: str | None = None
    escalation: str | None = None
    explanation: str = ""

    @property
    def model_requirement(self) -> str:
        return "local_draft" if self.local_profile else "standard"

    @property
    def local_profile_candidate(self) -> str | None:
        return self.local_profile


# Backward-compatible name for callers that imported Route.
Route = RouteDecision

_policy_cache: dict[str, Any] | None = None
_health_cache: dict[str, Any] | None = None
_authorized_routes: dict[str, RouteDecision] = {}


def load_policy(*, force_reload: bool = False) -> dict[str, Any]:
    global _policy_cache
    if force_reload or _policy_cache is None:
        with ROUTING_YAML.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if data.get("schema") != "fleet-routing-v2":
            raise RoutingError("UNSUPPORTED_ROUTING_POLICY_SCHEMA")
        if not isinstance(data.get("routes"), list) or not data["routes"]:
            raise RoutingError("ROUTING_RULES_REQUIRED")
        _policy_cache = data
    return _policy_cache


def load_health(*, force_reload: bool = False) -> dict[str, Any]:
    global _health_cache
    if force_reload or _health_cache is None:
        if not HEALTH_JSON.exists():
            return {"checks": {}}
        with HEALTH_JSON.open(encoding="utf-8") as handle:
            _health_cache = json.load(handle)
    return _health_cache


def get_health(provider: str, model: str, *, health: dict[str, Any] | None = None) -> str:
    data = health if health is not None else load_health()
    check = data.get("checks", {}).get(f"{provider}/{model}", {})
    status = str(check.get("status", "UNKNOWN"))
    expires = check.get("expires_at")
    if not expires:
        return "UNKNOWN" if status == "HEALTHY" else status
    try:
        expiry = datetime.fromisoformat(str(expires))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry:
            return "STALE"
    except ValueError:
        return "UNKNOWN"
    return status


def is_healthy(provider: str, model: str, *, health: dict[str, Any] | None = None) -> bool:
    return get_health(provider, model, health=health) == "HEALTHY"


def provider_family(provider: str, policy: dict[str, Any]) -> str:
    for item in policy.get("approved_providers", []):
        if item.get("id") == provider:
            return str(item.get("family", provider))
    return provider


def _field(ctx: TaskContext, name: str) -> Any:
    if not hasattr(ctx, name):
        raise RoutingError(f"UNKNOWN_CONTEXT_FIELD:{name}")
    return getattr(ctx, name)


def _matches(rule: dict[str, Any], ctx: TaskContext) -> bool:
    match = rule.get("match") or {}
    if match.get("always"):
        return True
    intent = ctx.intent.casefold()
    phrases = [str(value).casefold() for value in match.get("any_phrases", [])]
    if phrases and not any(phrase in intent for phrase in phrases):
        return False
    excluded = [str(value).casefold() for value in match.get("exclude_phrases", [])]
    if excluded and any(phrase in intent for phrase in excluded):
        return False
    all_true = match.get("all_true_flags", [])
    if any(not bool(_field(ctx, flag)) for flag in all_true):
        return False
    any_true = match.get("any_true_flags", [])
    if any_true and not any(bool(_field(ctx, flag)) for flag in any_true):
        # any_true_flags broadens phrase matching only when there are no phrases;
        # with phrases it is an additional admissible signal, not a requirement.
        if not phrases:
            return False
    false_flags = match.get("false_flags", [])
    if any(bool(_field(ctx, flag)) for flag in false_flags):
        return False
    equals = match.get("field_equals", {})
    if any(_field(ctx, key) != value for key, value in equals.items()):
        return False
    return True


def _select_rule(ctx: TaskContext, policy: dict[str, Any]) -> dict[str, Any]:
    rules = sorted(policy["routes"], key=lambda item: int(item.get("priority", 0)), reverse=True)
    for rule in rules:
        if _matches(rule, ctx):
            missing = [name for name in rule.get("required_preconditions", []) if not bool(_field(ctx, name))]
            if missing:
                blocker = str(rule.get("on_missing") or "ROUTING_PRECONDITION_MISSING")
                raise RoutingError(f"{blocker}:{','.join(missing)}")
            return rule
    raise RoutingError("NO_ROUTE_MATCHED")


def _override_for(profile: str, policy: dict[str, Any]) -> dict[str, str] | None:
    override = policy.get("temporary_override") or {}
    if not override.get("enabled") or profile not in override.get("profiles", []):
        return None
    if profile in override.get("excluded_profiles", []):
        return None
    expires = override.get("expires_at")
    if not expires:
        return None
    try:
        expiry = datetime.fromisoformat(str(expires))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expiry:
            return None
    except ValueError:
        return None
    return {"provider": str(override["provider"]), "model": str(override["model"])}


def _candidate_models(profile: str, policy: dict[str, Any]) -> list[dict[str, str]]:
    local = policy.get("local_profiles", {}).get(profile)
    if local:
        return [{"provider": str(local["provider"]), "model": str(local["model"])}]
    preferences = policy.get("canonical_preferences", {}).get(profile)
    if not preferences:
        raise RoutingError(f"MODEL_PREFERENCE_MISSING:{profile}")
    result = [dict(preferences["preferred"])]
    result.extend(dict(item) for item in preferences.get("fallbacks", []))
    return result


def canonical_identity(profile: str, *, policy: dict[str, Any] | None = None) -> tuple[str, str]:
    """Read a profile's canonical provider/model identity from routing.yaml."""
    effective = policy if policy is not None else load_policy()
    candidate = _candidate_models(profile, effective)[0]
    return str(candidate["provider"]), str(candidate["model"])


def _select_model(
    profile: str,
    ctx: TaskContext,
    policy: dict[str, Any],
    health: dict[str, Any],
    *,
    independence_required: bool = False,
    unavailable_code: str = "",
) -> tuple[str, str, str, bool, str]:
    override = _override_for(profile, policy)
    candidates = _candidate_models(profile, policy)
    if override:
        candidates.insert(0, override)
    builder_family = provider_family(ctx.builder_provider, policy) if ctx.builder_provider else None
    independence_result = "NOT_APPLICABLE"
    unhealthy: list[str] = []
    for candidate in candidates:
        provider = str(candidate["provider"])
        model = str(candidate["model"])
        status = get_health(provider, model, health=health)
        if status != "HEALTHY":
            unhealthy.append(f"{provider}/{model}:{status}")
            continue
        if independence_required and builder_family:
            if provider_family(provider, policy) == builder_family:
                continue
            independence_result = "PASSED"
        applied = bool(override and provider == override["provider"] and model == override["model"])
        return provider, model, status, applied, independence_result
    if unavailable_code:
        raise RoutingError(unavailable_code)
    if independence_required and builder_family:
        raise RoutingError("REVIEWER_INDEPENDENCE_UNAVAILABLE")
    raise RoutingError(f"MODEL_HEALTH_NOT_CURRENT:{profile}:{'|'.join(unhealthy)}")


def _log_decision(decision: RouteDecision) -> None:
    ROUTE_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = asdict(decision)
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    with ROUTE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def route_and_authorize(
    ctx: TaskContext,
    *,
    request_id: str,
    policy: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> RouteDecision:
    if not request_id.strip():
        raise RoutingError("REQUEST_ID_REQUIRED")
    effective_policy = policy if policy is not None else load_policy()
    effective_health = health if health is not None else load_health(force_reload=True)
    rule = _select_rule(ctx, effective_policy)
    profile = str(rule["profile"])
    local_contract = effective_policy.get("local_profiles", {}).get(profile, {})
    provider, model, model_health, override, independence = _select_model(
        profile,
        ctx,
        effective_policy,
        effective_health,
        independence_required=bool(rule.get("independence_required")),
        unavailable_code=str(local_contract.get("unavailable_code", "")),
    )
    route_id = f"route-{uuid.uuid4()}"
    decision = RouteDecision(
        route_id=route_id,
        request_id=request_id,
        profile=profile,
        reason_code=str(rule.get("reason_code", rule["id"])),
        confidence=str(rule.get("confidence", "medium")),
        selected_provider=provider,
        selected_model=model,
        model_health=model_health,
        temporary_override_applied=override,
        required_preconditions=list(rule.get("required_preconditions", [])),
        independence_result=independence,
        local_profile=profile if profile in effective_policy.get("local_profiles", {}) else None,
        escalation=rule.get("escalation"),
        explanation=f"Matched canonical route {rule['id']}",
    )
    _authorized_routes[route_id] = decision
    _log_decision(decision)
    return decision


def route_task(
    ctx: TaskContext,
    policy: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> RouteDecision:
    """Compatibility wrapper. New dispatch code must call route_and_authorize."""
    return route_and_authorize(
        ctx,
        request_id=f"compat-{uuid.uuid4()}",
        policy=policy,
        health=health,
    )


def consume_route_authorization(
    route_id: str,
    *,
    profile: str,
    provider: str,
    model: str,
) -> RouteDecision:
    if not route_id:
        raise RoutingError("AUTHORIZED_ROUTE_ID_REQUIRED")
    decision = _authorized_routes.pop(route_id, None)
    if decision is None:
        raise RoutingError("ROUTE_AUTHORIZATION_NOT_FOUND")
    if (decision.profile, decision.selected_provider, decision.selected_model) != (profile, provider, model):
        raise RoutingError("ROUTE_AUTHORIZATION_IDENTITY_MISMATCH")
    return decision


def record_health(
    provider: str,
    model: str,
    status: str,
    evidence: str = "",
    *,
    ttl_minutes: int = 60,
) -> None:
    global _health_cache
    data = load_health(force_reload=True)
    now = datetime.now(timezone.utc)
    expires = now.timestamp() + ttl_minutes * 60
    expiry = datetime.fromtimestamp(expires, timezone.utc)
    data.setdefault("checks", {})[f"{provider}/{model}"] = {
        "status": status,
        "evidence": evidence,
        "observed_at": now.isoformat(),
        "expires_at": expiry.isoformat(),
    }
    data["observed_at"] = now.isoformat()
    tmp = HEALTH_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(HEALTH_JSON)
    _health_cache = data
