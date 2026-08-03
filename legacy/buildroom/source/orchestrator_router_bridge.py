#!/usr/bin/env python3
"""Normalize explicit task context and invoke the mandatory fleet router."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
from fleet_router import RouteDecision, TaskContext, route_and_authorize


def classify_task(owner_request: str, buildroom_context: dict = None) -> TaskContext:
    """Normalize explicit context fields; all intent rules remain in routing.yaml."""
    ctx = buildroom_context or {}

    return TaskContext(
        intent=owner_request,
        owner_facing=ctx.get("owner_facing", True),
        governed_repo=ctx.get("governed_repo", False),
        buildroom_phase=ctx.get("buildroom_phase", ""),
        mutation_requested=ctx.get("mutation_requested", False),
        approved_design_evidence=ctx.get("approved_design_evidence", False),
        approved_candidate=ctx.get("approved_candidate", False),
        assigned_worktree=ctx.get("assigned_worktree", False),
        acceptance_criteria=ctx.get("acceptance_criteria", False),
        test_contract=ctx.get("test_contract", False),
        risk=ctx.get("risk", "medium"),
        binding_required=ctx.get("binding_required", False),
        privacy_local_only=ctx.get("privacy_local_only", False),
        builder_provider=ctx.get("builder_provider", ""),
        bounded_scope=ctx.get("bounded_scope", False),
    )


def dispatch_and_log(owner_request: str, buildroom_context: dict = None,
                     request_id: str = "") -> RouteDecision:
    """Compatibility intake: normalize then call the mandatory router API."""
    ctx = classify_task(owner_request, buildroom_context)
    return route_and_authorize(ctx, request_id=request_id)


# ── Direct integration entry point ──

if __name__ == "__main__":
    # Test: UX concept request
    result = dispatch_and_log(
        "design a user flow for the login page",
        {"owner_facing": True},
        "smoke-ux-001"
    )
    print(f"Route: {result.profile} ({result.reason_code}) — {result.explanation}")

    # Test: Governed implementation with full envelope
    result = dispatch_and_log(
        "implement the approved feature in the worktree",
        {
            "governed_repo": True,
            "approved_candidate": True,
            "assigned_worktree": True,
            "acceptance_criteria": True,
            "test_contract": True,
            "bounded_scope": True,
        },
        "smoke-builder-001"
    )
    print(f"Route: {result.profile} ({result.reason_code}) — {result.explanation}")

    print("\nRoute authorization issued by fleet_router.route_and_authorize()")
