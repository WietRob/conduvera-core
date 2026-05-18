# Matrix OS Route-Plan Viewer Outputs

Status: stable operator snapshot contract for the read-only `harness route-plan-view` command.

## Purpose

The route-plan viewer output is a stable operator snapshot for reviewing an existing `route-plan.v1` JSON handoff artifact. It lets tests, future UI panels, and operator workflows consume the same visible summary without scraping unstable ad-hoc terminal text.

The path is:

```text
route-plan.v1 JSON -> read-only viewer -> future Matrix UI panel model
```

The viewer does not plan routes itself and does not execute any candidate. It only renders an already-created, validated route-plan JSON artifact.

## Stable fixture list

Canonical golden outputs live under `tests/fixtures/harness/route_plan_view/`:

| Fixture | Source JSON | Purpose |
|---|---|---|
| `agent-task.txt` | `tests/fixtures/harness/route_plan/agent-task.json` | Agent-task handoff with Hermes/OpenCode/Pi Agent Harness descriptors, evidence requirements, and CCC/AAL approval gate |
| `dangerous-file-operation.txt` | `tests/fixtures/harness/route_plan/dangerous-file-operation.json` | Safety Guard route for destructive-action intent; proves blocked/safety evidence and no execution |
| `failed-agent-run.txt` | `tests/fixtures/harness/route_plan/failed-agent-run.json` | Failure-loop route with `failure.observed` and `rule.proposed`; rule proposal remains evidence-only |
| `operator-ui-view.txt` | `tests/fixtures/harness/route_plan/operator-ui-view.json` | Matrix UI/editor display route; proves future UI handoff boundary without dashboard claim |
| `unknown-intent.txt` | `tests/fixtures/harness/route_plan/unknown-intent.json` | Fail-closed unknown intent; requires human route decision |

## Stable output fields

The snapshot contract intentionally stabilizes these visible lines:

- heading: `Matrix UI Route Plan Viewer Stub`
- viewer schema and source schema
- operator intent
- chosen candidate, or `none`
- candidate ranking
- evidence requirements
- approval gate
- fail-closed state
- unknown capabilities
- `Execute now: no`
- `Runtime execution: no`
- `Production dashboard claim: no`
- non-execution boundary
- display boundary
- operator snapshot note

Future UI models can consume the same JSON fixture and assert the same operator-facing fields without enabling runtime behavior.

## What is not implemented

This contract does not implement:

- live UI panel integration,
- Textual widget rendering,
- runtime execution,
- agent execution,
- Hermes/OpenCode/Zed/MCP execution,
- adapter expansion,
- shell interception,
- destructive actions,
- production dashboard behavior.

## Validation

`tests/test_route_plan_viewer_golden_outputs.py` verifies:

- every canonical `route-plan.v1` JSON fixture has a matching viewer output fixture,
- `render_route_plan_view(build_route_plan_view(...))` exactly matches each golden output,
- CLI `harness route-plan-view --input ...` exactly matches each golden output,
- all fixtures keep `Runtime execution: no` and `Production dashboard claim: no`,
- the unknown-intent output remains fail-closed,
- the output pack avoids runtime, shell, SSH, Raspberry Pi, and pi-hermes claims.

## Future path

A future non-interactive Textual route-plan panel can consume the same `route-plan.v1` JSON fixture/output contract. That future slice should stay display-only until a separate reviewed runtime-execution ADR and implementation exists.
