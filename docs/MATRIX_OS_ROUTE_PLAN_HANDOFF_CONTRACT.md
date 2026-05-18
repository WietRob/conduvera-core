# Matrix OS Route Plan Handoff Contract

Status: authoritative route-plan.v1 machine-readable handoff contract for the descriptor-only Harness Gateway dry-run planner.

## Purpose

The route-plan handoff contract turns an operator intent into stable JSON that future Matrix OS UI, automation, and agent-facing review surfaces can consume without scraping terminal text and without executing any runtime.

```text
operator intent
 -> descriptor-only dry-run route planner
 -> route-plan.v1 JSON
 -> future UI/automation handoff surface
```

This contract is a planning artifact only. It records candidate ranking, evidence requirements, approval gates, unknown capabilities, and non-execution boundaries.

## Schema

Current schema version:

```text
route-plan.v1
```

Every canonical JSON fixture must include:

| Field | Meaning |
|---|---|
| `schema_version` | Stable contract id; currently exactly `route-plan.v1` |
| `intent` | Original operator request metadata: `text`, `actor`, `correlation_id` |
| `chosen_candidate_id` | Selected descriptor id, or `null` when fail-closed |
| `execute_now` | Always `false` for this contract |
| `fail_closed` | Whether the planner could not safely classify the intent |
| `required_approval_gate` | Human/evidence gate required before any future execution outside this planner |
| `non_execution_boundary` | Explicit boundary describing what is not executed now |
| `required_evidence_outputs` | Evidence event/output types a future workflow must provide |
| `unknown_capabilities` | Unsupported/missing capabilities requiring human decision |
| `candidates` | Ranked descriptor candidates with `runtime_enabled=false` |
| `steps` | Planned handoff/evidence steps; every step has `execute_now=false` |

Candidate objects include:

| Field | Meaning |
|---|---|
| `candidate_id` | Descriptor id such as `hermes`, `safety-guard`, or `matrix-ui-code-editor` |
| `name` | Human-readable descriptor name |
| `candidate_type` | Descriptor family, for example runner/evidence/display surface |
| `rank` | Candidate ordering within this dry-run plan |
| `runtime_enabled` | Always `false` in current scope |
| `selection_reason` | Why the candidate matched the intent |
| `capability_matches` | Matched dry-run capabilities and reasons |
| `what_would_execute_later` | Future-only description, not current execution |
| `not_executed_now` | Explicit non-execution statement |

## Canonical fixtures

Golden fixtures live in:

```text
tests/fixtures/harness/route_plan/
```

| Fixture | Intent | Primary handoff proof |
|---|---|---|
| `agent-task.json` | `Run agent task with evidence capture` | selects `hermes`, requires CCC/AAL and `agent.run.completed` evidence |
| `dangerous-file-operation.json` | `dangerous file operation delete production database` | selects `safety-guard`, requires `safety_guard.action.blocked`, performs no shell/file deletion |
| `failed-agent-run.json` | `review failed agent run and propose rule` | selects `failure-driven-loop`, emits `failure.observed` and `rule.proposed` evidence-only |
| `operator-ui-view.json` | `operator wants UI view of harness status` | selects original Matrix UI/editor surface descriptor and makes no production dashboard claim |
| `unknown-intent.json` | `make the thing better somehow` | fail-closed with human route decision required |

Regression tests compare `route_plan_to_dict(plan)` and CLI JSON output exactly against these fixtures.

## What future UI/automation may consume

A future Matrix OS UI or automation handoff can safely consume:

- intent text and correlation metadata;
- selected descriptor id and ranked candidate list;
- evidence requirements;
- approval gate text;
- unknown capabilities;
- planned dry-run steps;
- explicit non-execution boundaries.

A future consumer must still treat this JSON as a dry-run plan. It cannot infer runtime availability, production readiness, or approval from the presence of a candidate.

## Explicit non-goals

This contract does not implement or claim:

- runtime execution;
- agent execution;
- Hermes, OpenCode, Zed, or MCP implementation;
- MCP runtime;
- Pi fork or Raspberry Pi / SSH / pi-hermes work;
- new external adapters;
- shell interception;
- destructive action;
- production dashboard;
- branch-protection or governance expansion.

## Relation to other Matrix OS docs

| Document | Relationship |
|---|---|
| `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md` | Defines the descriptor-only gateway and dry-run planner boundaries |
| `docs/MATRIX_OS_PRODUCT_COHERENCE.md` | Shows how operator intent, evidence requirements, and approval gates form product value |
| `docs/MATRIX_OS_UI_VALUE_MAP.md` | Defines how preserved Matrix UI surfaces may later display planning/evidence state without a dashboard claim |
| `docs/ADR_RUNTIME_DECISION_AND_DRY_RUN_GATEWAY.md` | Records the runtime decision: descriptor-only dry-run route planning, not runtime execution |

## Validation

`tests/test_route_plan_golden_fixtures.py` locks the route-plan.v1 handoff contract with exact golden fixture comparisons, CLI JSON comparison, output-file smoke coverage, fail-closed JSON behavior, and no-runtime assertions.
